package app.mavie.player.data

import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.Call
import okhttp3.Callback
import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.Response
import java.io.EOFException
import java.io.IOException
import java.io.InterruptedIOException
import java.net.ConnectException
import java.net.Inet4Address
import java.net.InetAddress
import java.net.SocketException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.net.UnknownServiceException
import java.security.cert.CertPathValidatorException
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLException

internal const val MaviePrimaryUserAgent = "VLC/3.0.21 LibVLC/3.0.21"
internal const val MavieFallbackUserAgent = "Mavie/2.2"

internal object Ipv4FirstDns : Dns {
    override fun lookup(hostname: String): List<InetAddress> {
        val all = Dns.SYSTEM.lookup(hostname)
        val ipv4 = all.filterIsInstance<Inet4Address>()
        val other = all.filterNot { it is Inet4Address }
        return if (ipv4.isEmpty()) all else ipv4 + other
    }
}

internal val MavieBaseHttpClient: OkHttpClient by lazy {
    OkHttpClient.Builder()
        .dns(Ipv4FirstDns)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .callTimeout(45, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .retryOnConnectionFailure(true)
        .build()
}

internal val MavieStreamHttpClient: OkHttpClient by lazy {
    MavieBaseHttpClient.newBuilder()
        .readTimeout(90, TimeUnit.SECONDS)
        .callTimeout(0, TimeUnit.SECONDS)
        .build()
}

internal class HttpStatusException(val code: Int) : IOException("HTTP $code")

internal fun classifyHttpError(code: Int, isM3u: Boolean): IptvException = when (code) {
    401, 403 -> IptvException(
        "${if (isM3u) "M3U adresine" else "IPTV hesabına"} erişim reddedildi (HTTP $code). Kullanıcı adı, parola veya erişim iznini kontrol et."
    )
    404 -> IptvException(
        "${if (isM3u) "M3U listesi" else "Sunucu adresi"} bulunamadı (HTTP 404). Adresi kontrol et."
    )
    408, 504 -> IptvException("Sunucu yanıt vermekte gecikti (HTTP $code). Biraz sonra yeniden dene.")
    429 -> IptvException("Çok fazla istek gönderildi (HTTP 429). Biraz bekleyip yeniden dene.")
    in 500..599 -> IptvException("IPTV sağlayıcısı geçici sunucu hatası döndürdü (HTTP $code). Daha sonra yeniden dene.")
    else -> IptvException("İstek başarısız oldu (HTTP $code).")
}

private fun allThrowableNodes(error: Throwable): List<Throwable> {
    val visited = mutableListOf<Throwable>()
    val queue = ArrayDeque<Throwable>()
    queue.add(error)
    while (queue.isNotEmpty() && visited.size < 16) {
        val node = queue.removeFirst()
        if (visited.any { it === node }) continue
        visited += node
        node.cause?.let { queue.add(it) }
        node.suppressed.forEach { queue.add(it) }
    }
    return visited
}

internal fun classifyIoException(error: Throwable): IptvException {
    val chain = allThrowableNodes(error)
    return when {
        chain.any { it is UnknownHostException } ->
            IptvException("Sunucu adı çözümlenemedi (DNS hatası). İnternet bağlantını ve sunucu adresini kontrol et.")
        chain.any { it is SocketTimeoutException || it is InterruptedIOException } ->
            IptvException("Sunucu bağlantısı zaman aşımına uğradı. İnternet bağlantını kontrol edip yeniden dene.")
        chain.any { it is SSLException || it is CertPathValidatorException } ->
            IptvException("Güvenli HTTPS (TLS/SSL) bağlantısı kurulamadı. Sunucu http:// kullanıyor olabilir; adresi kontrol et.")
        chain.any { (it is SocketException && it !is ConnectException) || it is EOFException } ->
            IptvException("Sunucu bağlantıyı beklenmedik şekilde kesti. İnternet bağlantını kontrol edip yeniden dene.")
        chain.any { it is ConnectException } ->
            IptvException("Sunucuya bağlanılamadı (bağlantı reddedildi). Sunucu adresini ve port numarasını kontrol et.")
        chain.any { it is UnknownServiceException } ->
            IptvException("Bu adres için güvenli HTTPS bağlantısı gerekli.")
        else ->
            IptvException("IPTV sunucusuna ulaşılamadı. İnternet bağlantını ve sunucu adresini kontrol et.")
    }
}

internal fun isSslFailure(error: Throwable): Boolean =
    allThrowableNodes(error).any { it is SSLException || it is CertPathValidatorException }

internal fun isUaFallbackEligible(error: Throwable): Boolean =
    allThrowableNodes(error).any {
        (it is HttpStatusException && (it.code == 403 || it.code == 406)) ||
            (it is SocketException && it !is ConnectException) ||
            it is EOFException
    }

/** Cancellation closes an in-flight response as well as a connection awaiting headers. */
internal suspend fun <T> Call.readCancellable(read: (Response) -> T): T = suspendCancellableCoroutine { continuation ->
    continuation.invokeOnCancellation { cancel() }
    enqueue(object : Callback {
        override fun onFailure(call: Call, error: IOException) {
            continuation.resumeWith(Result.failure(error))
        }

        override fun onResponse(call: Call, response: Response) {
            val result = runCatching {
                response.use {
                    if (!continuation.isActive) return
                    read(it)
                }
            }
            continuation.resumeWith(result)
        }
    })
}
