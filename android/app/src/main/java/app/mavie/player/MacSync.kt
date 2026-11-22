package app.mavie.player

import app.mavie.player.data.IptvException
import app.mavie.player.data.MavieRepository
import app.mavie.player.data.readCancellable
import kotlinx.coroutines.CancellationException
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.net.InetAddress

/** Optional one-shot LAN merge. Playback never uses this client or a desktop URL. */
object MacSync {
    suspend fun merge(repository: MavieRepository, address: String, code: String) {
        val base = address.trim().let { if (it.contains("://")) it else "http://$it" }.toHttpUrlOrNull()
            ?: throw IptvException("Masaüstü uygulamasının yerel ağ adresini gir.")
        if (base.username.isNotEmpty() || base.password.isNotEmpty() || base.query != null || base.fragment != null) {
            throw IptvException("Yalnızca masaüstü uygulamasının yerel ağ adresini gir.")
        }
        val addresses = try { InetAddress.getAllByName(base.host).toList() } catch (_: Exception) {
            throw IptvException("Masaüstü adresi bulunamadı.")
        }
        if (addresses.isEmpty() || addresses.any { !it.isSiteLocalAddress && !it.isLoopbackAddress && !it.isLinkLocalAddress }) {
            throw IptvException("Eşitleme için aynı Wi-Fi ağındaki masaüstü adresini kullan.")
        }
        if (!code.matches(Regex("[0-9]{6}"))) {
            throw IptvException("Masaüstü uygulamasındaki altı haneli eşleştirme kodunu gir.")
        }
        val client = repository.newLanClient()
        val jsonType = "application/json; charset=utf-8".toMediaType()
        fun endpoint(path: String) = base.newBuilder().encodedPath(path).query(null).build()
        try {
            val cookie = client.newCall(
                Request.Builder().url(endpoint("/api/pair"))
                    .post(JSONObject().put("code", code).toString().toRequestBody(jsonType)).build()
            ).readCancellable { response ->
                if (!response.isSuccessful) {
                    throw IptvException(if (response.code == 403) "Eşleştirme kodu yanlış." else "Masaüstü ile eşleştirme tamamlanamadı.")
                }
                response.headers("Set-Cookie")
                    .firstNotNullOfOrNull { header -> header.substringBefore(';').trim().takeIf { '=' in it } }
                    ?: throw IptvException("Masaüstü eşleştirme yanıtı eksik.")
            }
            val remote = client.newCall(
                Request.Builder().url(endpoint("/api/export")).header("Cookie", cookie).build()
            ).readCancellable { response ->
                if (!response.isSuccessful) throw IptvException("Masaüstündeki kayıtlar okunamadı.")
                val bytes = response.body?.byteStream()?.use { input -> input.readBounded() }
                    ?: throw IptvException("Masaüstü boş yanıt gönderdi.")
                if (bytes.size > 25 * 1024 * 1024) throw IptvException("Masaüstü yedeği çok büyük.")
                bytes.toString(Charsets.UTF_8)
            }
            repository.importState(remote)
            // Native VLC IDs and desktop FFmpeg stream indices are different. Keep
            // selections local and merge only portable library/history state.
            val merged = JSONObject(repository.exportState()).apply {
                remove("trackPreferences")
                remove("nativeTrackPreferences")
            }
            client.newCall(
                Request.Builder().url(endpoint("/api/import")).header("Cookie", cookie)
                    .post(JSONObject().put("data", merged).toString().toRequestBody(jsonType)).build()
            ).readCancellable { response ->
                if (!response.isSuccessful) throw IptvException("Telefon kayıtları alındı; masaüstüne aktarım tamamlanamadı.")
            }
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (error: IptvException) {
            throw error
        } catch (_: Exception) {
            throw IptvException("Masaüstüne ulaşılamadı. Aynı Wi-Fi ağında ve Mavie'nin açık olduğundan emin ol. Telefonunda izlemeye devam edebilirsin.")
        }
    }
}
