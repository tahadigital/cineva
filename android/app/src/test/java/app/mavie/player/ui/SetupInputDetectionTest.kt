package app.mavie.player.ui

import app.mavie.player.data.ConnectionSettings
import app.mavie.player.data.IptvException
import app.mavie.player.data.MavieRepository
import org.junit.Assert.*
import org.junit.Test

class SetupInputDetectionTest {
    @Test
    fun detectsM3uPlusGetPhpUrlPastedIntoXtreamHostField() {
        val detected = detectXtreamOrM3uInput(
            "http://example.test:8080/get.php?username=testuser&password=testpass&type=m3u_plus&output=mpegts"
        )
        assertTrue(detected is ParsedSetupInput.UseM3u)
        assertEquals(
            "http://example.test:8080/get.php?username=testuser&password=testpass&type=m3u_plus&output=mpegts",
            (detected as ParsedSetupInput.UseM3u).m3uUrl,
        )
    }

    @Test
    fun detectsM3u8ExtensionAndSchemelessM3uUrls() {
        val detected = detectXtreamOrM3uInput("cdn.example.test/live/playlist.m3u8")
        assertTrue(detected is ParsedSetupInput.UseM3u)
        assertEquals("http://cdn.example.test/live/playlist.m3u8", (detected as ParsedSetupInput.UseM3u).m3uUrl)
    }

    @Test
    fun extractsBaseHostAndCredentialsFromPlayerApiUrl() {
        val detected = detectXtreamOrM3uInput(
            "https://panel.example.test:8443/iptv/player_api.php?username=testuser&password=testpass"
        )
        assertTrue(detected is ParsedSetupInput.UseXtream)
        val xtream = detected as ParsedSetupInput.UseXtream
        assertEquals("https://panel.example.test:8443/iptv", xtream.host)
        assertEquals("testuser", xtream.username)
        assertEquals("testpass", xtream.password)
    }

    @Test
    fun preservesNormalXtreamHostAndRepositoryStillRejectsQueriesAndUserinfo() {
        assertEquals(ParsedSetupInput.KeepXtream, detectXtreamOrM3uInput("http://sunucun:8080"))
        for (bad in listOf("http://example.test/?password=secret", "http://user:pass@example.test")) {
            try {
                MavieRepository.normalizeConnection(ConnectionSettings(bad, "testuser", "testpass"))
                fail("MavieRepository.normalizeConnection must keep rejecting $bad")
            } catch (_: IptvException) {
            }
        }
    }
}
