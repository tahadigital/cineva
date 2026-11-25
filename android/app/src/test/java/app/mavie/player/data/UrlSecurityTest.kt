package app.mavie.player.data

import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress

class UrlSecurityTest {
    @Test
    fun safeHttpUrlAllowsOnlyHttpAndHttpsWithHost() {
        assertTrue(UrlSecurity.isSafeHttpUrl("http://cdn.example.test/list.m3u"))
        assertTrue(UrlSecurity.isSafeHttpUrl("  HTTPS://cdn.example.test:8443/stream.mp4  "))
        assertFalse(UrlSecurity.isSafeHttpUrl(""))
        assertFalse(UrlSecurity.isSafeHttpUrl("   "))
        assertFalse(UrlSecurity.isSafeHttpUrl("file:///etc/passwd"))
        assertFalse(UrlSecurity.isSafeHttpUrl("content://media/external/video/1"))
        assertFalse(UrlSecurity.isSafeHttpUrl("javascript:alert(1)"))
        assertFalse(UrlSecurity.isSafeHttpUrl("ftp://cdn.example.test/a.mp4"))

        assertTrue(UrlSecurity.isBlankOrSafeHttpUrl(""))
        assertTrue(UrlSecurity.isBlankOrSafeHttpUrl("   "))
        assertFalse(UrlSecurity.isBlankOrSafeHttpUrl("file:///tmp/x.mp4"))
    }

    @Test
    fun detectsCloudMetadataAndLinkLocalAddressesIncludingIpv6MappedIpv4() {
        assertTrue(UrlSecurity.isCloudMetadataOrLinkLocal("metadata.google.internal", emptyList()))
        assertTrue(UrlSecurity.isCloudMetadataOrLinkLocal("metadata.goog.", emptyList()))
        assertTrue(UrlSecurity.isCloudMetadataOrLinkLocal("169.254.169.254", emptyList()))
        assertTrue(UrlSecurity.isCloudMetadataOrLinkLocal("0.0.0.0", emptyList()))

        val linkLocalV4 = InetAddress.getByAddress(byteArrayOf(169.toByte(), 254.toByte(), 169.toByte(), 254.toByte()))
        val ipv6MappedMetadata = InetAddress.getByAddress(
            byteArrayOf(
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xff.toByte(), 0xff.toByte(),
                169.toByte(), 254.toByte(), 169.toByte(), 254.toByte(),
            ),
        )
        val linkLocalV6 = InetAddress.getByAddress(byteArrayOf(0xfe.toByte(), 0x80.toByte(), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1))
        val publicIp = InetAddress.getByAddress(byteArrayOf(93.toByte(), 184.toByte(), 216.toByte(), 34))

        assertTrue(UrlSecurity.isCloudMetadataOrLinkLocal("evil.example.test", listOf(linkLocalV4)))
        assertTrue(UrlSecurity.isCloudMetadataOrLinkLocal("evil.example.test", listOf(ipv6MappedMetadata)))
        assertTrue(UrlSecurity.isCloudMetadataOrLinkLocal("evil.example.test", listOf(linkLocalV6)))
        assertFalse(UrlSecurity.isCloudMetadataOrLinkLocal("example.test", listOf(publicIp)))
    }

    @Test
    fun detectsPrivateAndLoopbackRangesForIpv4Ipv6AndMappedAddresses() {
        assertTrue(UrlSecurity.isPrivateOrLoopback("localhost", emptyList()))
        assertTrue(UrlSecurity.isPrivateOrLoopback("sub.localhost", emptyList()))
        assertTrue(UrlSecurity.isPrivateOrLoopback("nas.local", emptyList()))

        val privateSamples = listOf(
            byteArrayOf(127, 0, 0, 1),
            byteArrayOf(10, 0, 0, 5),
            byteArrayOf(172.toByte(), 16, 0, 1),
            byteArrayOf(172.toByte(), 31, 255.toByte(), 254.toByte()),
            byteArrayOf(192.toByte(), 168.toByte(), 1, 10),
            byteArrayOf(100, 64, 0, 1),
        )
        for (raw in privateSamples) {
            val addr = InetAddress.getByAddress(raw)
            assertTrue("Expected private for ${addr.hostAddress}", UrlSecurity.isPrivateOrLoopback("host.test", listOf(addr)))
            val mapped = InetAddress.getByAddress(
                byteArrayOf(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xff.toByte(), 0xff.toByte()) + raw,
            )
            assertTrue("Expected private for mapped ${addr.hostAddress}", UrlSecurity.isPrivateOrLoopback("host.test", listOf(mapped)))
        }

        val ulaV6 = InetAddress.getByAddress(byteArrayOf(0xfd.toByte(), 0x12, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1))
        val loopbackV6 = InetAddress.getByAddress(byteArrayOf(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1))
        assertTrue(UrlSecurity.isPrivateOrLoopback("v6.test", listOf(ulaV6)))
        assertTrue(UrlSecurity.isPrivateOrLoopback("v6.test", listOf(loopbackV6)))

        val nonPrivateA = InetAddress.getByAddress(byteArrayOf(172.toByte(), 15, 255.toByte(), 254.toByte()))
        val nonPrivateB = InetAddress.getByAddress(byteArrayOf(172.toByte(), 32, 0, 1))
        val publicIp = InetAddress.getByAddress(byteArrayOf(93.toByte(), 184.toByte(), 216.toByte(), 34))
        assertFalse(UrlSecurity.isPrivateOrLoopback("pub.test", listOf(nonPrivateA, nonPrivateB, publicIp)))
    }

    @Test
    fun safeAutoEpgUrlBlocksMetadataAndCrossHostPrivateSsrfWhileAllowingSameHostOrPublic() {
        val publicIp = listOf(InetAddress.getByAddress(byteArrayOf(93.toByte(), 184.toByte(), 216.toByte(), 34)))
        val privateIp = listOf(InetAddress.getByAddress(byteArrayOf(192.toByte(), 168.toByte(), 1, 50)))
        val metadataIp = listOf(InetAddress.getByAddress(byteArrayOf(169.toByte(), 254.toByte(), 169.toByte(), 254.toByte())))

        val publicPlaylist = "https://cdn.example.test/list.m3u".toHttpUrl()
        val sameLocalPlaylist = "http://nas.local:8080/list.m3u".toHttpUrl()

        assertTrue(
            UrlSecurity.isSafeAutoEpgUrl(
                "https://epg.example.test/guide.xml".toHttpUrl(),
                publicPlaylist,
            ) { publicIp },
        )
        assertFalse(
            UrlSecurity.isSafeAutoEpgUrl(
                "http://192.168.1.50/guide.xml".toHttpUrl(),
                publicPlaylist,
            ) { privateIp },
        )
        assertTrue(
            UrlSecurity.isSafeAutoEpgUrl(
                "http://NAS.local:8080/guide.xml".toHttpUrl(),
                sameLocalPlaylist,
            ) { privateIp },
        )
        assertFalse(
            UrlSecurity.isSafeAutoEpgUrl(
                "http://169.254.169.254/guide.xml".toHttpUrl(),
                "http://169.254.169.254/list.m3u".toHttpUrl(),
            ) { metadataIp },
        )
    }

    @Test
    fun hasUrlCredentialsDetectsBasicAuthAndSensitiveQueryKeys() {
        assertTrue(UrlSecurity.hasUrlCredentials("http://user:pass@cdn.example.test/list.m3u".toHttpUrl()))
        assertTrue(UrlSecurity.hasUrlCredentials("https://cdn.example.test/get.php?username=demo_user&password=demo_pass".toHttpUrl()))
        assertTrue(UrlSecurity.hasUrlCredentials("https://cdn.example.test/list.m3u?TOKEN=secret".toHttpUrl()))
        assertTrue(UrlSecurity.hasUrlCredentials("https://cdn.example.test/list.m3u?api_key=123".toHttpUrl()))
        assertFalse(UrlSecurity.hasUrlCredentials("https://cdn.example.test/list.m3u?type=m3u_plus&output=ts".toHttpUrl()))
    }
}
