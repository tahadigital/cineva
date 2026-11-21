package app.mavie.player.data

import org.junit.Assert.*
import org.junit.Test

class M3uParserTest {
    @Test
    fun parsesM3uChannelsVodAndAutoEpgHeader() {
        val playlist = """
            #EXTM3U url-tvg="https://epg.example/guide.xml"
            #EXTINF:-1 tvg-logo="https://img.example/live.png" group-title="Belgesel",Open Science TV
            https://stream.example/science/index.m3u8
            #EXTINF:-1 group-title="Açık Filmler",Sample Film
            https://cdn.example/sample.mp4
        """.trimIndent()
        val parsed = M3uParser.parse(playlist)
        assertEquals("https://epg.example/guide.xml", parsed.epgUrl)
        assertEquals(2, parsed.items.size)
        assertEquals(MediaKind.LIVE, parsed.items[0].kind)
        assertEquals(MediaKind.VOD, parsed.items[1].kind)
        assertEquals("mp4", parsed.items[1].extension)
        assertEquals("https://cdn.example/sample.mp4", parsed.items[1].sourceUrl)
    }

    @Test
    fun demoCatalogContainsValidHttpsOpenMovies() {
        assertTrue(DemoCatalog.items.size >= 4)
        assertTrue(DemoCatalog.items.all { it.sourceUrl.startsWith("https://") && it.kind == MediaKind.VOD })
    }
}
