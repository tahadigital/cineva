package app.mavie.player

import app.mavie.player.data.IptvException
import app.mavie.player.data.MavieErrorCode
import app.mavie.player.data.MavieRepository
import app.mavie.player.data.UrlSecurity
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
            ?: throw IptvException("Masaüstü uygulamasının yerel ağ adresini gir.", MavieErrorCode.INVALID_INPUT)
        if (base.username.isNotEmpty() || base.password.isNotEmpty() || base.query != null || base.fragment != null) {
            throw IptvException("Yalnızca masaüstü uygulamasının yerel ağ adresini gir.", MavieErrorCode.INVALID_INPUT)
        }
        val addresses = try { InetAddress.getAllByName(base.host).toList() } catch (_: Exception) {
            throw IptvException("Masaüstü adresi bulunamadı.", MavieErrorCode.DNS_FAILED)
        }
        if (addresses.isEmpty() ||
            UrlSecurity.isCloudMetadataOrLinkLocal(base.host, addresses) ||
            addresses.any { !it.isSiteLocalAddress && !it.isLoopbackAddress }
        ) {
            throw IptvException("Eşitleme için aynı Wi-Fi ağındaki masaüstü adresini kullan.", MavieErrorCode.UNSAFE_URL)
        }
        if (!code.matches(Regex("[0-9]{6}"))) {
            throw IptvException("Masaüstü uygulamasındaki altı haneli eşleştirme kodunu gir.", MavieErrorCode.INVALID_INPUT)
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
                    if (response.code == 403) {
                        throw IptvException("Eşleştirme kodu yanlış.", MavieErrorCode.AUTH_REJECTED)
                    } else {
                        throw IptvException("Masaüstü ile eşleştirme tamamlanamadı.", MavieErrorCode.SYNC_PAIR_FAILED)
                    }
                }
                response.headers("Set-Cookie")
                    .firstNotNullOfOrNull { header -> header.substringBefore(';').trim().takeIf { '=' in it } }
                    ?: throw IptvException("Masaüstü eşleştirme yanıtı eksik.", MavieErrorCode.SYNC_PAIR_FAILED)
            }
            val remote = client.newCall(
                Request.Builder().url(endpoint("/api/export")).header("Cookie", cookie).build()
            ).readCancellable { response ->
                if (!response.isSuccessful) throw IptvException("Masaüstündeki kayıtlar okunamadı.", MavieErrorCode.SYNC_PAIR_FAILED)
                val bytes = response.body?.byteStream()?.use { input -> input.readBounded() }
                    ?: throw IptvException("Masaüstü boş yanıt gönderdi.", MavieErrorCode.INVALID_RESPONSE)
                if (bytes.size > 25 * 1024 * 1024) throw IptvException("Masaüstü yedeği çok büyük.", MavieErrorCode.PAYLOAD_TOO_LARGE)
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
                if (!response.isSuccessful) throw IptvException("Telefon kayıtları alındı; masaüstüne aktarım tamamlanamadı.", MavieErrorCode.SYNC_PAIR_FAILED)
            }
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (error: IptvException) {
            throw error
        } catch (_: Exception) {
            throw IptvException("Masaüstüne ulaşılamadı. Aynı Wi-Fi ağında ve Mavie'nin açık olduğundan emin ol. Telefonunda izlemeye devam edebilirsin.", MavieErrorCode.OFFLINE)
        }
    }
}
