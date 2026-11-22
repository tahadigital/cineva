package app.mavie.player.data

import app.mavie.player.limitBytes
import org.junit.Assert.*
import org.junit.Test
import java.io.BufferedReader
import java.io.ByteArrayInputStream
import java.io.Reader
import java.io.StringReader

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
    fun parsesBomPrefixedHeaderAndCommasInsideQuotedAttributes() {
        val playlist = "\uFEFF#EXTM3U url-tvg=\"https://epg.example/a.xml,http://epg.example/b.xml\"\n" +
            "#EXTINF:-1 tvg-name=\"Haber, Canlı\" group-title=\"Haberler, Ulusal\",TV 1, HD\n" +
            "http://stream.example/live/101.ts\n"
        val parsed = M3uParser.parse(playlist)
        assertEquals("https://epg.example/a.xml", parsed.epgUrl)
        assertEquals(1, parsed.items.size)
        assertEquals("TV 1, HD", parsed.items[0].name)
        assertEquals("Haberler, Ulusal", parsed.items[0].categoryName)
        assertEquals(MediaKind.LIVE, parsed.items[0].kind)
    }

    @Test
    fun streamsOver30MiBInBoundedBatchesWithoutFullStringRetention() {
        val targetBytes = 33L * 1024 * 1024
        val entryTemplate = "#EXTINF:-1 group-title=\"Sinema\",Örnek Film %d\nhttp://cdn.example.test/movie/%d.mp4\n"
        val syntheticReader = object : Reader() {
            private var emittedBytes = 0L
            private var index = 0
            private var current = "#EXTM3U url-tvg=\"http://epg.example.test/guide.xml\"\n"
            private var pos = 0

            override fun read(cbuf: CharArray, off: Int, len: Int): Int {
                if (len == 0) return 0
                var written = 0
                while (written < len) {
                    if (pos >= current.length) {
                        if (emittedBytes >= targetBytes) break
                        current = entryTemplate.format(index, index)
                        index++
                        pos = 0
                    }
                    val toCopy = minOf(len - written, current.length - pos)
                    current.toCharArray(cbuf, off + written, pos, pos + toCopy)
                    pos += toCopy
                    emittedBytes += toCopy
                    written += toCopy
                }
                return if (written == 0) -1 else written
            }

            override fun close() = Unit
        }

        val batchSizes = mutableListOf<Int>()
        var totalItems = 0
        val summary = BufferedReader(syntheticReader, 64 * 1024).use { reader ->
            M3uParser.parseStream(reader, batchSize = 500) { batch ->
                assertTrue(batch.size <= 500)
                batchSizes.add(batch.size)
                totalItems += batch.size
            }
        }
        assertTrue("Expected >350k items for >33 MiB M3U, got $totalItems", totalItems > 350_000)
        assertEquals(totalItems, summary.itemCount)
        assertEquals("http://epg.example.test/guide.xml", summary.epgUrl)
        assertTrue(batchSizes.size > 700)
        assertTrue(batchSizes.dropLast(1).all { it == 500 })
    }

    @Test
    fun limitBytesRejectsStreamsAboveCeiling() {
        val input = ByteArrayInputStream(ByteArray(2048) { 65 })
        val limited = input.limitBytes(1024, "Limit aşıldı")
        val buf = ByteArray(512)
        assertEquals(512, limited.read(buf))
        assertEquals(512, limited.read(buf))
        try {
            limited.read(buf)
            fail("Expected IptvException when exceeding limitBytes")
        } catch (ex: IptvException) {
            assertEquals("Limit aşıldı", ex.message)
        }
    }

    @Test
    fun demoCatalogContainsValidHttpsOpenMovies() {
        assertTrue(DemoCatalog.items.size >= 4)
        assertTrue(DemoCatalog.items.all { it.sourceUrl.startsWith("https://") && it.kind == MediaKind.VOD })
    }
}
