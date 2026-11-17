package app.cineva.player

import app.cineva.player.data.AkisRepository
import app.cineva.player.data.IptvException
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.net.InetAddress
import java.util.concurrent.TimeUnit

/** Optional one-shot LAN merge. Playback never uses this client or a Mac URL. */
object MacSync {
    suspend fun merge(repository: AkisRepository,address: String,code: String) {
        val base=address.trim().let { if(it.contains("://"))it else "http://$it" }.toHttpUrlOrNull()?:throw IptvException("Mac'in yerel ağ adresini gir.")
        if(base.username.isNotEmpty()||base.password.isNotEmpty()||base.query!=null||base.fragment!=null)throw IptvException("Yalnızca Mac'in yerel ağ adresini gir.")
        val addresses=try { InetAddress.getAllByName(base.host).toList() } catch(_: Exception) { throw IptvException("Mac'in adresi bulunamadı.") }
        if(addresses.isEmpty()||addresses.any { !it.isSiteLocalAddress&&!it.isLoopbackAddress&&!it.isLinkLocalAddress })throw IptvException("Eşitleme için aynı Wi-Fi ağındaki Mac adresini kullan.")
        if(!code.matches(Regex("[0-9]{6}")))throw IptvException("Mac'teki altı haneli eşleştirme kodunu gir.")
        val client=OkHttpClient.Builder().connectTimeout(5,TimeUnit.SECONDS).readTimeout(15,TimeUnit.SECONDS).callTimeout(20,TimeUnit.SECONDS).followRedirects(false).build()
        val jsonType="application/json; charset=utf-8".toMediaType()
        fun endpoint(path: String)=base.newBuilder().encodedPath(path).query(null).build()
        try {
            val cookie=client.newCall(Request.Builder().url(endpoint("/api/pair")).post(JSONObject().put("code",code).toString().toRequestBody(jsonType)).build()).execute().use {
                if(!it.isSuccessful)throw IptvException(if(it.code==403)"Eşleştirme kodu yanlış." else "Mac ile eşleştirme tamamlanamadı.")
                it.header("Set-Cookie")?.substringBefore(';')?:throw IptvException("Mac eşleştirme yanıtı eksik.")
            }
            val remote=client.newCall(Request.Builder().url(endpoint("/api/export")).header("Cookie",cookie).build()).execute().use {
                if(!it.isSuccessful)throw IptvException("Mac'teki kayıtlar okunamadı.")
                val bytes=it.body?.byteStream()?.use { input -> input.readBounded() }?:throw IptvException("Mac boş yanıt gönderdi.")
                if(bytes.size>25*1024*1024)throw IptvException("Mac yedeği çok büyük.")
                bytes.toString(Charsets.UTF_8)
            }
            repository.importState(remote)
            // Native VLC IDs and Mac FFmpeg stream indices are different. Keep
            // selections local and merge only portable library/history state.
            val merged=JSONObject(repository.exportState()).apply { remove("trackPreferences");remove("nativeTrackPreferences") }
            client.newCall(Request.Builder().url(endpoint("/api/import")).header("Cookie",cookie)
                .post(JSONObject().put("data",merged).toString().toRequestBody(jsonType)).build()).execute().use {
                if(!it.isSuccessful)throw IptvException("Telefon kayıtları alındı; Mac'e aktarım tamamlanamadı.")
            }
        } catch(error: IptvException) { throw error }
        catch(_: Exception) { throw IptvException("Mac'e ulaşılamadı. Aynı Wi-Fi ağında ve Akış'ın açık olduğundan emin ol. Telefonunda izlemeye devam edebilirsin.") }
    }
}
