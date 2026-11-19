package app.vrelio.player.data

import android.content.Context
import android.content.SharedPreferences
import android.os.Build
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.util.UUID
import java.util.concurrent.TimeUnit

data class CloudDevice(
    val id: String,
    val name: String,
    val platform: String,
    val lastSeenAt: String = "",
)

data class CloudFeatures(
    val cloudSync: Boolean = false,
    val multiView: Boolean = false,
    val unlimitedProfiles: Boolean = false,
    val epgMatch: Boolean = false,
    val advancedTracks: Boolean = false,
    val maxDevices: Int = 1,
)

data class CloudAccountState(
    val cloudUrl: String = "",
    val email: String = "",
    val displayName: String = "",
    val emailVerified: Boolean = false,
    val pendingVerificationEmail: String = "",
    val plan: String = "normal",
    val effectivePlan: String = "normal",
    val isPro: Boolean = false,
    val trialActive: Boolean = false,
    val trialStartedAt: String = "",
    val trialEndsAt: String = "",
    val expiresAt: String = "",
    val status: String = "active",
    val maxDevices: Int = 1,
    val devices: List<CloudDevice> = emptyList(),
    val features: CloudFeatures = CloudFeatures(),
    val announcementTitle: String = "",
    val announcementMessage: String = "",
    val signedIn: Boolean = false,
)

class CloudApiException(
    message: String,
    val code: String = "",
    val httpStatus: Int = 0,
    val email: String = "",
) : Exception(message) {
    fun toIptvException(): IptvException = IptvException(message ?: "Bulut isteği başarısız.")
}

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

class CloudClient internal constructor(
    private val prefs: SharedPreferences,
) {
    constructor(context: Context) : this(
        context.applicationContext.getSharedPreferences("vrelio_cloud_prefs", Context.MODE_PRIVATE),
    )

    private val http = OkHttpClient.Builder().connectTimeout(8, TimeUnit.SECONDS).readTimeout(10, TimeUnit.SECONDS).build()
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    fun currentDeviceId(): String = deviceId()

    private fun deviceId(): String {
        val existing = prefs.getString("device_id", null)
        if (!existing.isNullOrBlank()) return existing
        val created = "and_" + UUID.randomUUID().toString().replace("-", "").take(16)
        prefs.edit().putString("device_id", created).apply()
        return created
    }

    fun current(): CloudAccountState {
        val signedIn = !prefs.getString("cloud_token", "").isNullOrBlank()
        val effectivePlan = prefs.getString("user_effective_plan", "normal").orEmpty().ifBlank { "normal" }
        val isPro = prefs.getBoolean("user_is_pro", effectivePlan == "pro")
        val maxDevices = prefs.getInt("user_max_devices", if (isPro) 5 else 1)
        return CloudAccountState(
            cloudUrl = prefs.getString("cloud_url", "").orEmpty(),
            email = prefs.getString("user_email", "").orEmpty(),
            displayName = prefs.getString("user_name", "").orEmpty(),
            emailVerified = prefs.getBoolean("user_email_verified", false),
            pendingVerificationEmail = prefs.getString("pending_verification_email", "").orEmpty(),
            plan = prefs.getString("user_plan", effectivePlan).orEmpty().ifBlank { "normal" },
            effectivePlan = effectivePlan,
            isPro = isPro,
            trialActive = prefs.getBoolean("user_trial_active", false),
            trialStartedAt = prefs.getString("user_trial_started_at", "").orEmpty(),
            trialEndsAt = prefs.getString("user_trial_ends_at", "").orEmpty(),
            expiresAt = prefs.getString("user_expires_at", "").orEmpty(),
            status = prefs.getString("user_status", "active").orEmpty(),
            maxDevices = maxDevices,
            devices = parseDevices(prefs.getString("user_devices_json", "[]").orEmpty()),
            features = parseFeatures(prefs.getString("user_features_json", "{}").orEmpty(), isPro, maxDevices),
            signedIn = signedIn,
        )
    }

    suspend fun refreshStatus(): CloudAccountState = withContext(Dispatchers.IO) {
        val url = prefs.getString("cloud_url", "").orEmpty().takeIf { it.isNotBlank() }
            ?: return@withContext current()
        val cfg = runCatching { getJson("$url/api/v1/app-config", null) }.getOrNull()
        val ann = cfg?.optJSONObject("announcement")
        val annEnabled = ann?.optBoolean("enabled", false) == true
        val token = prefs.getString("cloud_token", "").orEmpty()
        if (token.isBlank()) {
            return@withContext current().copy(
                cloudUrl = url,
                announcementTitle = if (annEnabled) ann?.optString("title").orEmpty() else "",
                announcementMessage = if (annEnabled) ann?.optString("message").orEmpty() else "",
            )
        }
        val me = try {
            getJson("$url/api/v1/me", token).getJSONObject("user")
        } catch (err: CloudApiException) {
            if (err.httpStatus == 401) {
                prefs.edit().remove("cloud_token").apply()
            }
            throw err
        }
        saveUserState(url, token, me)
        current().copy(
            announcementTitle = if (annEnabled) ann?.optString("title").orEmpty() else "",
            announcementMessage = if (annEnabled) ann?.optString("message").orEmpty() else "",
        )
    }

    suspend fun register(
        cloudUrl: String,
        email: String,
        password: String,
        displayName: String = "",
    ): CloudAccountState = withContext(Dispatchers.IO) {
        val base = CloudUrlValidator.normalize(cloudUrl)
        val cleanEmail = email.trim().lowercase()
        val name = displayName.trim().ifBlank { cleanEmail.substringBefore('@') }
        val body = JSONObject()
            .put("email", cleanEmail)
            .put("password", password)
            .put("displayName", name)
        postJson("$base/api/v1/auth/register", null, body)
        prefs.edit()
            .putString("cloud_url", base)
            .putString("pending_verification_email", cleanEmail)
            .remove("cloud_token")
            .apply()
        current().copy(
            cloudUrl = base,
            email = cleanEmail,
            displayName = name,
            emailVerified = false,
            pendingVerificationEmail = cleanEmail,
            signedIn = false,
        )
    }

    suspend fun login(cloudUrl: String, email: String, password: String): CloudAccountState = withContext(Dispatchers.IO) {
        val base = CloudUrlValidator.normalize(cloudUrl)
        val cleanEmail = email.trim().lowercase()
        val body = JSONObject()
            .put("email", cleanEmail)
            .put("password", password)
        val res = try {
            postJson("$base/api/v1/auth/login", null, body)
        } catch (err: CloudApiException) {
            if (err.code == "EMAIL_NOT_VERIFIED") {
                val targetEmail = err.email.ifBlank { cleanEmail }
                prefs.edit()
                    .putString("cloud_url", base)
                    .putString("pending_verification_email", targetEmail)
                    .apply()
            }
            throw err
        }
        val token = res.getString("token")
        val user = res.getJSONObject("user")
        saveUserState(base, token, user)
        prefs.edit().remove("pending_verification_email").apply()
        registerCurrentDevice(base, token)
        current()
    }

    suspend fun verifyEmail(cloudUrl: String, email: String, code: String): Pair<CloudAccountState, Boolean> = withContext(Dispatchers.IO) {
        val base = CloudUrlValidator.normalize(cloudUrl.ifBlank { prefs.getString("cloud_url", "").orEmpty() })
        val cleanEmail = email.trim().lowercase()
        val body = JSONObject()
            .put("email", cleanEmail)
            .put("code", code.trim())
        val res = postJson("$base/api/v1/auth/verify-email", null, body)
        val token = res.getString("token")
        val user = res.getJSONObject("user")
        val trialActivated = res.optBoolean("trialActivated", false)
        saveUserState(base, token, user)
        prefs.edit().remove("pending_verification_email").apply()
        registerCurrentDevice(base, token)
        current() to trialActivated
    }

    suspend fun resendVerification(cloudUrl: String, email: String): String = withContext(Dispatchers.IO) {
        val base = CloudUrlValidator.normalize(cloudUrl.ifBlank { prefs.getString("cloud_url", "").orEmpty() })
        val cleanEmail = email.trim().lowercase()
        val res = postJson("$base/api/v1/auth/resend-verification", null, JSONObject().put("email", cleanEmail))
        res.optString("deliveryMode", "outbox")
    }

    suspend fun forgotPassword(cloudUrl: String, email: String): String = withContext(Dispatchers.IO) {
        val base = CloudUrlValidator.normalize(cloudUrl.ifBlank { prefs.getString("cloud_url", "").orEmpty() })
        val cleanEmail = email.trim().lowercase()
        prefs.edit().putString("cloud_url", base).apply()
        val res = postJson("$base/api/v1/auth/forgot-password", null, JSONObject().put("email", cleanEmail))
        res.optString("message").ifBlank { "Sıfırlama kodu e-posta adresinize gönderildi." }
    }

    suspend fun verifyResetCode(cloudUrl: String, email: String, code: String): Boolean = withContext(Dispatchers.IO) {
        val base = CloudUrlValidator.normalize(cloudUrl.ifBlank { prefs.getString("cloud_url", "").orEmpty() })
        val res = postJson(
            "$base/api/v1/auth/verify-reset-code",
            null,
            JSONObject().put("email", email.trim().lowercase()).put("code", code.trim()),
        )
        res.optBoolean("valid", res.optBoolean("ok", false))
    }

    suspend fun resetPassword(cloudUrl: String, email: String, code: String, newPassword: String) = withContext(Dispatchers.IO) {
        val base = CloudUrlValidator.normalize(cloudUrl.ifBlank { prefs.getString("cloud_url", "").orEmpty() })
        postJson(
            "$base/api/v1/auth/reset-password",
            null,
            JSONObject()
                .put("email", email.trim().lowercase())
                .put("code", code.trim())
                .put("newPassword", newPassword),
        )
        Unit
    }

    suspend fun redeemLicense(code: String): CloudAccountState = withContext(Dispatchers.IO) {
        val url = prefs.getString("cloud_url", "").orEmpty()
        val token = prefs.getString("cloud_token", "").orEmpty()
        if (url.isBlank() || token.isBlank()) throw IptvException("Önce Vrelio hesabına giriş yap.")
        val res = postJson("$url/api/v1/licenses/redeem", token, JSONObject().put("code", code.trim()))
        saveUserState(url, token, res.getJSONObject("user"))
        current()
    }

    suspend fun removeDevice(targetDeviceId: String): CloudAccountState = withContext(Dispatchers.IO) {
        val url = prefs.getString("cloud_url", "").orEmpty()
        val token = prefs.getString("cloud_token", "").orEmpty()
        if (url.isBlank() || token.isBlank()) throw IptvException("Önce Vrelio hesabına giriş yap.")
        val encoded = URLEncoder.encode(targetDeviceId, "UTF-8").replace("+", "%20")
        val res = deleteJson("$url/api/v1/devices/$encoded", token)
        val devicesArr = res.optJSONArray("devices")
        if (devicesArr != null) {
            prefs.edit().putString("user_devices_json", devicesArr.toString()).apply()
        } else {
            refreshStatus()
        }
        current()
    }

    suspend fun syncState(repository: VrelioRepository) = withContext(Dispatchers.IO) {
        val url = prefs.getString("cloud_url", "").orEmpty()
        val token = prefs.getString("cloud_token", "").orEmpty()
        if (url.isBlank() || token.isBlank()) throw IptvException("Önce Vrelio hesabına giriş yap.")
        val remoteRes = getJson("$url/api/v1/sync", token)
        val remoteState = remoteRes.optJSONObject("state")
        if (remoteState != null && remoteState.optInt("version", 0) == 1) {
            repository.importState(remoteState.toString())
        }
        val merged = JSONObject(repository.exportState())
        putJson("$url/api/v1/sync", token, JSONObject().put("state", merged))
    }

    fun logout() {
        prefs.edit()
            .remove("cloud_token")
            .remove("user_email")
            .remove("user_name")
            .remove("user_email_verified")
            .remove("pending_verification_email")
            .remove("user_plan")
            .remove("user_effective_plan")
            .remove("user_is_pro")
            .remove("user_trial_active")
            .remove("user_trial_started_at")
            .remove("user_trial_ends_at")
            .remove("user_expires_at")
            .remove("user_status")
            .remove("user_max_devices")
            .remove("user_devices_json")
            .remove("user_features_json")
            .apply()
    }

    private fun registerCurrentDevice(base: String, token: String) {
        runCatching {
            val deviceName = listOfNotNull(Build.MANUFACTURER, Build.MODEL)
                .joinToString(" ")
                .trim()
                .ifBlank { "Android" }
            val res = postJson(
                "$base/api/v1/devices/register",
                token,
                JSONObject()
                    .put("deviceId", deviceId())
                    .put("deviceName", deviceName)
                    .put("platform", "android"),
            )
            res.optJSONArray("devices")?.let { arr ->
                prefs.edit().putString("user_devices_json", arr.toString()).apply()
            }
        }
    }

    private fun saveUserState(url: String, token: String, user: JSONObject) {
        val rawPlan = user.optString("plan", "normal").ifBlank { "normal" }
        val effPlan = user.optString("effectivePlan", rawPlan).ifBlank { "normal" }
        val isPro = user.optBoolean("isPro", effPlan == "pro")
        val maxDevices = user.optInt("maxDevices", if (isPro) 5 else 1)
        val featuresObj = user.optJSONObject("features") ?: JSONObject()
        val devicesArr = user.optJSONArray("devices")
        val edit = prefs.edit()
            .putString("cloud_url", url)
            .putString("cloud_token", token)
            .putString("user_email", user.optString("email"))
            .putString("user_name", user.optString("displayName"))
            .putBoolean("user_email_verified", user.optBoolean("emailVerified", true))
            .putString("user_plan", rawPlan)
            .putString("user_effective_plan", effPlan)
            .putBoolean("user_is_pro", isPro)
            .putBoolean("user_trial_active", user.optBoolean("trialActive", false))
            .putString("user_trial_started_at", user.optString("trialStartedAt"))
            .putString("user_trial_ends_at", user.optString("trialEndsAt"))
            .putString("user_expires_at", user.optString("expiresAt"))
            .putString("user_status", user.optString("status", "active"))
            .putInt("user_max_devices", maxDevices)
            .putString("user_features_json", featuresObj.toString())
        if (devicesArr != null) {
            edit.putString("user_devices_json", devicesArr.toString())
        }
        edit.apply()
    }

    private fun parseDevices(raw: String): List<CloudDevice> {
        val arr = runCatching { JSONArray(raw) }.getOrNull() ?: return emptyList()
        return buildList {
            for (i in 0 until arr.length()) {
                val obj = arr.optJSONObject(i) ?: continue
                val id = obj.optString("id").ifBlank { obj.optString("deviceId") }
                if (id.isBlank()) continue
                add(
                    CloudDevice(
                        id = id,
                        name = obj.optString("name").ifBlank { obj.optString("deviceName", "Cihaz") },
                        platform = obj.optString("platform", "android"),
                        lastSeenAt = obj.optString("lastSeenAt"),
                    ),
                )
            }
        }
    }

    private fun parseFeatures(raw: String, isPro: Boolean, maxDevices: Int): CloudFeatures {
        val obj = runCatching { JSONObject(raw) }.getOrNull() ?: JSONObject()
        return CloudFeatures(
            cloudSync = obj.optBoolean("cloudSync", isPro),
            multiView = obj.optBoolean("multiView", isPro),
            unlimitedProfiles = obj.optBoolean("unlimitedProfiles", isPro),
            epgMatch = obj.optBoolean("epgMatch", isPro),
            advancedTracks = obj.optBoolean("advancedTracks", isPro),
            maxDevices = obj.optInt("maxDevices", maxDevices),
        )
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

    private fun deleteJson(url: String, token: String?): JSONObject {
        val req = Request.Builder().url(url).delete()
            .apply { if (!token.isNullOrBlank()) header("Authorization", "Bearer $token") }.build()
        return executeJson(req)
    }

    private fun executeJson(req: Request): JSONObject {
        val resp = runCatching { http.newCall(req).execute() }.getOrElse {
            throw CloudApiException("Bulut sunucusuna bağlanılamadı.", code = "NETWORK_ERROR")
        }
        return resp.use { r ->
            val raw = r.body?.string().orEmpty()
            val obj = runCatching { JSONObject(raw) }.getOrNull() ?: JSONObject()
            if (!r.isSuccessful) {
                val msg = obj.optString("error").ifBlank { "İstek reddedildi (${r.code})." }
                val code = obj.optString("code")
                val email = obj.optString("email")
                throw CloudApiException(msg, code = code, httpStatus = r.code, email = email)
            }
            obj
        }
    }
}
