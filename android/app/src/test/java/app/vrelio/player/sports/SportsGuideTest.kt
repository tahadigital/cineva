package app.vrelio.player.sports

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.time.LocalDate
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
    fun channelQualityVariantsNormalizeCorrectly() {
        assertEquals(SportsChannels.key("Public Sports 1"), SportsChannels.key("TR: Public Sports 1 | FHD"))
        assertEquals(SportsChannels.key("World News"), SportsChannels.key("US: World News 4K"))
        assertNotEquals(SportsChannels.key("Public Sports 1"), SportsChannels.key("Public Sports 2"))
    }
}
