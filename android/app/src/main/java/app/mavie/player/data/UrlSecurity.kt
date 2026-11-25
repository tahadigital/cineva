package app.mavie.player.data

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import java.net.Inet4Address
import java.net.Inet6Address
import java.net.InetAddress
import java.util.Locale

internal object UrlSecurity {
    private val CREDENTIAL_QUERY_KEYS = setOf(
        "username", "user", "password", "pass", "token", "auth", "key", "apikey", "api_key",
    )
    private val METADATA_HOSTS = setOf("metadata.google.internal", "metadata.goog")

    fun isSafeHttpUrl(raw: String): Boolean {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return false
        val parsed = trimmed.toHttpUrlOrNull() ?: return false
        val scheme = parsed.scheme.lowercase(Locale.ROOT)
        return (scheme == "http" || scheme == "https") && parsed.host.isNotBlank()
    }

    fun isBlankOrSafeHttpUrl(raw: String): Boolean = raw.isBlank() || isSafeHttpUrl(raw)

    fun hasUrlCredentials(url: HttpUrl): Boolean {
        if (url.username.isNotEmpty() || url.password.isNotEmpty()) return true
        for (i in 0 until url.querySize) {
            if (url.queryParameterName(i).lowercase(Locale.ROOT) in CREDENTIAL_QUERY_KEYS) return true
        }
        return false
    }

    fun resolveHostSafe(host: String): List<InetAddress> {
        val clean = host.trim().trim('[', ']')
        if (clean.isEmpty()) return emptyList()
        return runCatching { InetAddress.getAllByName(clean).toList() }.getOrDefault(emptyList())
    }

    private fun extractIpv4Bytes(address: InetAddress): ByteArray? {
        if (address is Inet4Address) return address.address
        if (address is Inet6Address) {
            val bytes = address.address
            if (bytes.size == 16 &&
                bytes.slice(0..9).all { it == 0.toByte() } &&
                bytes[10] == 0xff.toByte() &&
                bytes[11] == 0xff.toByte()
            ) {
                return bytes.copyOfRange(12, 16)
            }
        }
        return null
    }

    private fun isMetadataOrLinkLocalAddress(address: InetAddress): Boolean {
        if (address.isLinkLocalAddress || address.isAnyLocalAddress || address.isMulticastAddress) return true
        val v4 = extractIpv4Bytes(address)
        if (v4 != null) {
            val b0 = v4[0].toInt() and 0xFF
            val b1 = v4[1].toInt() and 0xFF
            if (b0 == 169 && b1 == 254) return true
            if (b0 == 0) return true
            if (b0 >= 224) return true
            return false
        }
        if (address is Inet6Address) {
            val bytes = address.address
            val b0 = bytes[0].toInt() and 0xFF
            val b1 = bytes[1].toInt() and 0xFF
            if (b0 == 0xFE && (b1 and 0xC0) == 0x80) return true
            if (b0 == 0xFF) return true
        }
        return false
    }

    private fun isPrivateOrLoopbackAddress(address: InetAddress): Boolean {
        if (isMetadataOrLinkLocalAddress(address)) return true
        if (address.isLoopbackAddress || address.isSiteLocalAddress) return true
        val v4 = extractIpv4Bytes(address)
        if (v4 != null) {
            val b0 = v4[0].toInt() and 0xFF
            val b1 = v4[1].toInt() and 0xFF
            if (b0 == 127) return true
            if (b0 == 10) return true
            if (b0 == 172 && b1 in 16..31) return true
            if (b0 == 192 && b1 == 168) return true
            if (b0 == 100 && b1 in 64..127) return true
            return false
        }
        if (address is Inet6Address) {
            val bytes = address.address
            val b0 = bytes[0].toInt() and 0xFF
            if ((b0 and 0xFE) == 0xFC) return true
            if (bytes.all { it == 0.toByte() }) return true
        }
        return false
    }

    fun isCloudMetadataOrLinkLocal(
        host: String,
        addresses: List<InetAddress> = resolveHostSafe(host),
    ): Boolean {
        val clean = host.trim().trim('[', ']').lowercase(Locale.ROOT).trimEnd('.')
        if (clean in METADATA_HOSTS) return true
        if (clean.startsWith("169.254.") || clean == "0.0.0.0") return true
        return addresses.any(::isMetadataOrLinkLocalAddress)
    }

    fun isPrivateOrLoopback(
        host: String,
        addresses: List<InetAddress> = resolveHostSafe(host),
    ): Boolean {
        if (isCloudMetadataOrLinkLocal(host, addresses)) return true
        val clean = host.trim().trim('[', ']').lowercase(Locale.ROOT).trimEnd('.')
        if (clean == "localhost" || clean.endsWith(".localhost") || clean.endsWith(".local")) return true
        return addresses.any(::isPrivateOrLoopbackAddress)
    }

    fun isSafeAutoEpgUrl(
        epgUrl: HttpUrl,
        playlistUrl: HttpUrl,
        resolve: (String) -> List<InetAddress> = ::resolveHostSafe,
    ): Boolean {
        val scheme = epgUrl.scheme.lowercase(Locale.ROOT)
        if (scheme != "http" && scheme != "https") return false
        val epgAddrs = resolve(epgUrl.host)
        if (isCloudMetadataOrLinkLocal(epgUrl.host, epgAddrs)) return false
        if (isPrivateOrLoopback(epgUrl.host, epgAddrs)) {
            return epgUrl.host.equals(playlistUrl.host, ignoreCase = true)
        }
        return true
    }
}
