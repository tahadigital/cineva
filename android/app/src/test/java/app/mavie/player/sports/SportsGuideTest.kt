package app.mavie.player.sports

import app.mavie.player.data.MavieErrorCode
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.time.LocalDate
import java.util.concurrent.TimeUnit
import java.util.zip.GZIPOutputStream

class SportsGuideTest {
    private val day = LocalDate.parse("2026-11-03")
    private val sampleXmltv = """<?xml version="1.0" encoding="UTF-8"?>
        <tv>
          <channel id="ch1"><display-name>Public Sports 1</display-name></channel>
          <channel id="ch2"><display-name>World News</display-name></channel>
          <programme start="20261103204500 +0300" stop="20261103224500 +0300" channel="ch1">
            <title>City vs United</title>
            <category>Football</category>
            <category>Champions League</category>
          </programme>
          <programme start="20261103183000 +0300" stop="20261103193000 +0300" channel="ch2">
            <title>Evening News</title>
            <category>News</category>
          </programme>
          <programme start="20261104120000 +0300" stop="20261104130000 +0300" channel="ch2">
            <title>Next Day Show</title>
          </programme>
        </tv>
    """.trimIndent()

    private val sampleSporekraniModern = """<html><script>window.__INITIAL_STATE__={
        "common": {
            "eventChannels": {
                "10": {"id": 10, "name": "Bein Sports 1", "active": 1},
                "11": {"id": 11, "name": "S Sport 1", "active": 1},
                "12": {"id": 12, "name": "Yayın Yok", "active": 1}
            },
            "eventRows": [
                {"id": 100, "sport_name": "Programlar", "league_name": "Program", "event_type_name": "commentary", "name": "Spor Artı", "date_time": "2026-11-03 18:00:00", "channels": [10], "featured": 0},
                {"id": 101, "sport_name": "Futbol", "league_name": "UEFA Şampiyonlar Ligi", "event_type_name": "match", "name": "Galatasaray - Bayern", "post_fix": "Canlı", "date_time": "2026-11-03 20:45:00", "channels": [10, 12], "featured": 1},
                {"id": 102, "sport_name": "Basketbol", "league_name": "EuroLeague", "event_type_name": "match", "name": "Fenerbahçe Beko - Real Madrid", "date_time": "2026-11-03 19:30:00", "channels": [11], "featured": 0}
            ]
        }
    }</script></html>"""

    @Test
    fun parsesSporekraniModernEventRows() {
        val events = SportsGuide.parseSporekrani(sampleSporekraniModern, day)
        assertEquals(listOf("102", "101"), events.map { it.id })
        assertEquals("19:30", events[0].time)
        assertEquals(listOf("S Sport 1"), events[0].channels)
        assertEquals("Galatasaray - Bayern · Canlı", events[1].title)
        assertEquals(listOf("Bein Sports 1"), events[1].channels)
        assertTrue(events[1].featured)
    }

    @Test
    fun parsesXmltvGuidesAndGzipStreamsByDay() {
        val events = SportsGuide.parseXmltv(sampleXmltv, day)
        assertEquals(listOf("Evening News", "City vs United"), events.map { it.title })
        assertEquals(listOf("18:30", "20:45"), events.map { it.time })
        assertFalse(events.first().featured)
        assertTrue(events.last().featured)

        val gz = ByteArrayOutputStream().also { out ->
            GZIPOutputStream(out).use { it.write(sampleXmltv.toByteArray()) }
        }.toByteArray()
        assertEquals(2, SportsGuide.parseXmltv(gz, day).size)
    }

    @Test(expected = IOException::class)
    fun rejectsXmltvDoctypeOrEntityDeclarations() {
        SportsGuide.parseXmltv("<!DOCTYPE tv [<!ENTITY xxe 'bad'>]><tv/>", day)
    }

    @Test
    fun channelQualityVariantsAndTurkishAliasesNormalizeCorrectly() {
        assertEquals(SportsChannels.key("Public Sports 1"), SportsChannels.key("TR: Public Sports 1 | FHD"))
        assertEquals(SportsChannels.key("World News"), SportsChannels.key("US: World News 4K"))
        assertEquals(SportsChannels.key("S Sport 1"), SportsChannels.key("TR: S Sport FHD"))
        assertEquals(SportsChannels.key("Smart Spor HD"), SportsChannels.key("TR: Spor Smart HD"))
        assertEquals(SportsChannels.key("TRT Spor Star"), SportsChannels.key("TR: TRT Spor Yıldız HD"))
        assertNotEquals(SportsChannels.key("Public Sports 1"), SportsChannels.key("Public Sports 2"))
    }

    @Test(timeout = 10_000)
    fun loadPropagatesCancellationAndCancelsInFlightHttpCall() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            var caughtCancel = false
            val job = launch(Dispatchers.IO) {
                try {
                    SportsGuide.load(
                        day = day,
                        force = true,
                        epgUrl = server.url("/epg.xml").toString(),
                    )
                } catch (cancel: CancellationException) {
                    caughtCancel = true
                    throw cancel
                }
            }
            assertNotNull(server.takeRequest(3, TimeUnit.SECONDS))
            withTimeout(2_000) { job.cancelAndJoin() }
            assertTrue("CancellationException must propagate out of SportsGuide.load()", caughtCancel)
        }
    }

    @Test
    fun rejectsXmltvDoctypeAndEntityAfterLargeLeadingPadding() {
        val padded = " ".repeat(8192) + "<!DOCTYPE tv><tv/>"
        try {
            SportsGuide.parseXmltv(padded, day)
            fail("Expected SportsGuideException for padded <!DOCTYPE")
        } catch (ex: SportsGuideException) {
            assertEquals(MavieErrorCode.UNSAFE_URL, ex.code)
        }

        val entityPadded = " ".repeat(8192) + "<tv><!ENTITY xxe 'bad'></tv>"
        try {
            SportsGuide.parseXmltv(entityPadded, day)
            fail("Expected SportsGuideException for padded <!ENTITY")
        } catch (ex: SportsGuideException) {
            assertEquals(MavieErrorCode.UNSAFE_URL, ex.code)
        }
    }

    @Test(timeout = 10_000)
    fun loadRejectsRedirectToCloudMetadataAndLinkLocalWithUnsafeUrlCode() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(
                MockResponse()
                    .setResponseCode(302)
                    .setHeader("Location", "http://169.254.169.254/latest/meta-data/"),
            )
            try {
                SportsGuide.load(
                    day = day,
                    force = true,
                    epgUrl = server.url("/redirect-ssrf.xml").toString(),
                )
                fail("Expected redirect SSRF to be rejected")
            } catch (ex: SportsGuideException) {
                assertEquals(MavieErrorCode.UNSAFE_URL, ex.code)
            }
        }
    }

    @Test(timeout = 10_000)
    fun loadRejectsCrossHostRedirectForCredentialedEpgUrl() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(
                MockResponse()
                    .setResponseCode(302)
                    .setHeader("Location", "http://evil.example.test/steal.xml"),
            )
            try {
                SportsGuide.load(
                    day = day,
                    force = true,
                    epgUrl = server.url("/xmltv.php?username=demo_user&password=demo_pass").toString(),
                )
                fail("Expected cross-host credential redirect to be rejected")
            } catch (ex: SportsGuideException) {
                assertEquals(MavieErrorCode.UNSAFE_URL, ex.code)
            }
        }
    }
}
