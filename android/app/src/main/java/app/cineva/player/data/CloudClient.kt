package app.cineva.player.data

import android.content.Context
import android.os.Build
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

data class CloudAccountState(
    val cloudUrl: String = "",
    val email: String = "",
    val displayName: String = "",
    val plan: String = "free",
    val status: String = "active",
    val maxDevices: Int = 2,
    val announcementTitle: String = "",
    val announcementMessage: String = "",
    val signedIn: Boolean = false,
)

internal object CloudUrlValidator {
    fun normalize(raw: String): String {
        val trimmed = raw.trim().trimEnd('/')
        if (trimmed.isEmpty()) throw IptvException("Portal sunucu adresi boş olamaz.")
        val withScheme = if (trimmed.contains("://")) trimmed else "https://$trimmed"
        val parsed = withScheme.toHttpUrlOrNull() ?: throw IptvException("Sunucu adresi geçersiz.")
        if (parsed.scheme !in listOf("http", "https") || parsed.username.isNotEmpty() || parsed.password.isNotEmpty()) {
            throw IptvException("Yalnızca http:// veya https:// sunucu adresi girin.")
        }
        return withScheme.trimEnd('/')
    }
}

class CloudClient(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("cineva_cloud_prefs", Context.MODE_PRIVATE)
    private val http = OkHttpClient.Builder().connectTimeout(8, TimeUnit.SECONDS).readTimeout(10, TimeUnit.SECONDS).build()
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    private fun deviceId(): String {
        val existing = prefs.getString("device_id", null)
        if (!existing.isNullOrBlank()) return existing
        val created = "and_" + UUID.randomUUID().toString().replace("-", "").take(16)
        prefs.edit().putString("device_id", created).apply()
        return created
    }

    fun current(): CloudAccountState = CloudAccountState(
        cloudUrl = prefs.getString("cloud_url", "").orEmpty(),
        email = prefs.getString("user_email", "").orEmpty(),
        displayName = prefs.getString("user_name", "").orEmpty(),
        plan = prefs.getString("user_plan", "free").orEmpty(),
        status = prefs.getString("user_status", "active").orEmpty(),
        maxDevices = prefs.getInt("user_max_devices", 2),
        signedIn = !prefs.getString("cloud_token", "").isNullOrBlank(),
    )

    suspend fun refreshStatus(): CloudAccountState = withContext(Dispatchers.IO) {
        val url = prefs.getString("cloud_url", "").orEmpty().takeIf { it.isNotBlank() } ?: return@withContext CloudAccountState()
        val cfg = runCatching { getJson("$url/api/v1/app-config", null) }.getOrNull()
        val ann = cfg?.optJSONObject("announcement")
        val annEnabled = ann?.optBoolean("enabled", false) == true
        val token = prefs.getString("cloud_token", "").orEmpty()
        if (token.isBlank()) {
            return@withContext CloudAccountState(
                cloudUrl = url,
                announcementTitle = if (annEnabled) ann?.optString("title").orEmpty() else "",
                announcementMessage = if (annEnabled) ann?.optString("message").orEmpty() else "",
            )
        }
        val me = try {
            getJson("$url/api/v1/me", token).getJSONObject("user")
        } catch (err: IptvException) {
            prefs.edit().remove("cloud_token").apply()
            throw err
        }
        saveUserState(url, token, me)
        current().copy(
            announcementTitle = if (annEnabled) ann?.optString("title").orEmpty() else "",
            announcementMessage = if (annEnabled) ann?.optString("message").orEmpty() else "",
        )
    }

    suspend fun authenticate(cloudUrl: String, email: String, password: String, register: Boolean): CloudAccountState = withContext(Dispatchers.IO) {
        val base = CloudUrlValidator.normalize(cloudUrl)
        val endpoint = if (register) "/api/v1/auth/register" else "/api/v1/auth/login"
        val body = JSONObject().put("email", email.trim()).put("password", password).put("displayName", email.substringBefore('@'))
        val res = postJson("$base$endpoint", null, body)
        val token = res.getString("token")
        val user = res.getJSONObject("user")
        saveUserState(base, token, user)
        runCatching {
            postJson("$base/api/v1/devices/register", token, JSONObject()
                .put("deviceId", deviceId())
                .put("deviceName", "${Build.MANUFACTURER} ${Build.MODEL}".trim())
                .put("platform", "android"))
        }
        current()
    }

    suspend fun redeemLicense(code: String): CloudAccountState = withContext(Dispatchers.IO) {
        val url = prefs.getString("cloud_url", "").orEmpty()
        val token = prefs.getString("cloud_token", "").orEmpty()
        if (url.isBlank() || token.isBlank()) throw IptvException("Önce Cineva hesabına giriş yap.")
        val res = postJson("$url/api/v1/licenses/redeem", token, JSONObject().put("code", code.trim()))
        saveUserState(url, token, res.getJSONObject("user"))
        current()
    }

    suspend fun syncState(repository: AkisRepository) = withContext(Dispatchers.IO) {
        val url = prefs.getString("cloud_url", "").orEmpty()
        val token = prefs.getString("cloud_token", "").orEmpty()
        if (url.isBlank() || token.isBlank()) throw IptvException("Önce Cineva hesabına giriş yap.")
        val remoteRes = getJson("$url/api/v1/sync", token)
        val remoteState = remoteRes.optJSONObject("state")
        if (remoteState != null && remoteState.optInt("version", 0) == 1) {
            repository.importState(remoteState.toString())
        }
        val merged = JSONObject(repository.exportState())
        putJson("$url/api/v1/sync", token, JSONObject().put("state", merged))
    }

    fun logout() {
        prefs.edit().remove("cloud_token").remove("user_email").remove("user_name").remove("user_plan").remove("user_status").apply()
    }

    private fun saveUserState(url: String, token: String, user: JSONObject) {
        prefs.edit()
            .putString("cloud_url", url)
            .putString("cloud_token", token)
            .putString("user_email", user.optString("email"))
            .putString("user_name", user.optString("displayName"))
            .putString("user_plan", user.optString("effectivePlan", user.optString("plan", "free")))
            .putString("user_status", user.optString("status", "active"))
            .putInt("user_max_devices", user.optInt("maxDevices", 2))
            .apply()
    }

    private fun getJson(url: String, token: String?): JSONObject {
        val req = Request.Builder().url(url).apply { if (!token.isNullOrBlank()) header("Authorization", "Bearer $token") }.build()
        return executeJson(req)
    }

    private fun postJson(url: String, token: String?, body: JSONObject): JSONObject {
        val req = Request.Builder().url(url).post(body.toString().toRequestBody(jsonType))
            .apply { if (!token.isNullOrBlank()) header("Authorization", "Bearer $token") }.build()
        return executeJson(req)
    }

    private fun putJson(url: String, token: String?, body: JSONObject): JSONObject {
        val req = Request.Builder().url(url).put(body.toString().toRequestBody(jsonType))
            .apply { if (!token.isNullOrBlank()) header("Authorization", "Bearer $token") }.build()
        return executeJson(req)
    }

    private fun executeJson(req: Request): JSONObject {
        val resp = runCatching { http.newCall(req).execute() }.getOrElse { throw IptvException("Bulut sunucusuna bağlanılamadı.") }
        return resp.use { r ->
            val raw = r.body?.string().orEmpty()
            val obj = runCatching { JSONObject(raw) }.getOrNull() ?: JSONObject()
            if (!r.isSuccessful) throw IptvException(obj.optString("error").ifBlank { "İstek reddedildi (${r.code})." })
            obj
        }
    }
}
