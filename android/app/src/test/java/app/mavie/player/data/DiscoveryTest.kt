package app.mavie.player.data

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.time.LocalDate
import java.util.concurrent.TimeUnit
import kotlin.io.path.createTempDirectory

class DiscoveryTest {
    private val fixture = JSONObject(javaClass.classLoader!!.getResource("discovery.json")!!.readText())
    private fun items(key: String): List<MediaItem> {
        val a = fixture.getJSONArray(key)
        return (0 until a.length()).map { i ->
            val m = a.getJSONObject(i)
            val p = m.optJSONObject("progress")
            MediaItem(
                m.getString("id"), m.getString("id"), m.getString("name"),
                MediaKind.fromKey(m.getString("kind")), year = m.optString("year"),
                poster = m.optString("poster"), genres = m.optString("genre"),
                parentId = m.optString("parentId").ifBlank { null },
                progress = p?.let { WatchProgress(m.getString("id"), it.optDouble("position"), it.optDouble("duration"), it.optBoolean("completed"), timestamp(it.optString("updatedAt"))) },
            )
        }
    }

    private fun result(history: List<MediaItem> = items("history"), date: LocalDate = LocalDate.of(2026, 11, 6)) =
        buildDiscovery(items("catalog"), history, fixture.getJSONObject("feed"), date)

    @Test
    fun personalRecommendationsPromoteWatchedGenresAndOrderGenreShelves() {
        val result = result()
        val shelf = result.shelves.first { it.id == "for-you-vod" }
        assertEquals("vod:comedy", shelf.items.first().id)
        assertTrue(shelf.title.startsWith("Sana Özel"))
        assertTrue(shelf.subtitle.contains("Komedi"))

        val genreShelves = result.shelves.filter { it.id.startsWith("genre-vod-") }
        assertEquals("genre-vod-Comedy", genreShelves.first().id)
        assertTrue(genreShelves.first().subtitle.contains("öne çıkarıldı"))
        assertEquals("genre-vod-Horror", genreShelves[1].id)
        assertTrue(genreShelves[1].subtitle.isEmpty())
    }

    @Test
    fun showcaseOffersFilmsAndSeriesWithoutFutureReleases() {
        val result = result()
        assertEquals(setOf(MediaKind.VOD, MediaKind.SERIES), result.showcase.map { it.kind }.toSet())
        assertFalse(result.showcase.any { it.id in setOf("vod:future", "vod:upcoming", "vod:remake") })
    }

    @Test
    fun recommendationIdsAlwaysResolveToTheLocalCatalog() {
        val valid = items("catalog").map { it.id }.toSet()
        assertTrue(result().shelves.flatMap { it.items }.all { it.id in valid })
        assertFalse(result().shelves.first { it.id == "genre-vod-Comedy" }.items.any { it.id == "vod:remake" })
    }

    @Test
    fun netflixTurkeyTop10ShelfDisplaysAndExpiresWhenStale() {
        val turkey = result().shelves.filter { it.id.startsWith("turkey-") }
        assertEquals(2, turkey.size)
        assertTrue(turkey.first().title.contains("Türkiye’de Popüler"))
        assertTrue(turkey.first().subtitle.contains("Netflix Türkiye Top 10"))
        assertFalse(result(date = LocalDate.of(2026, 12, 1)).shelves.any { it.id.startsWith("turkey-") })
    }

    @Test
    fun parsesNetflixTudumGraphqlPayload() {
        val html = """<script>netflix.reactContext.models.graphql = JSON.parse('{"data":{"x":{"top10Video":{"title":"Never Surrender","releaseYear":2026,"videoId":81996126},"top10":{"category":"MOVIES","weeklyRank":1,"weekEndDate":"2026-11-15"}}}}');</script>"""
        val entries = parseNetflix(html)
        assertEquals(1, entries.length())
        assertEquals("vod", entries.getJSONObject(0).getString("kind"))
        assertEquals("Never Surrender", entries.getJSONObject(0).getString("name"))
        assertEquals(81996126L, entries.getJSONObject(0).getLong("netflixId"))
    }

    @Test
    fun decodeJsStringLiteralHandlesHexAndStandardEscapes() {
        val encoded = """\x7B\x22key\x22:\x22O\'Brien \\ path\/1\nline2\t\x3Cok\x3E\x22\x7D"""
        assertEquals("{\"key\":\"O'Brien \\ path/1\nline2\t<ok>\"}", decodeJsStringLiteral(encoded))
        assertEquals("trailing \\xG", decodeJsStringLiteral("trailing \\xG"))
    }

    @Test
    fun parsesNetflixGraphqlWithHexEscapesAndDeduplicates() {
        val escaped = """\x7B\x22data\x22:\x7B\x22row1\x22:\x7B\x22top10Video\x22:\x7B\x22title\x22:\x22Alpha\x22,\x22releaseYear\x22:2025,\x22videoId\x22:101\x7D,\x22top10\x22:\x7B\x22category\x22:\x22MOVIES\x22,\x22weeklyRank\x22:2,\x22weekEndDate\x22:\x222026-11-15\x22\x7D\x7D,\x22row2\x22:\x7B\x22top10Video\x22:\x7B\x22title\x22:\x22Alpha\x22,\x22releaseYear\x22:2025,\x22videoId\x22:101\x7D,\x22top10\x22:\x7B\x22category\x22:\x22MOVIES\x22,\x22weeklyRank\x22:2,\x22weekEndDate\x22:\x222026-11-15\x22\x7D\x7D,\x22row3\x22:\x7B\x22top10Video\x22:\x7B\x22title\x22:\x22Ep 1\x22,\x22parentShow\x22:\x7B\x22title\x22:\x22Show X\x22,\x22videoId\x22:202\x7D\x7D,\x22top10\x22:\x7B\x22category\x22:\x22TV\x22,\x22weeklyRank\x22:1,\x22weekEndDate\x22:\x222026-11-15\x22\x7D\x7D\x7D\x7D"""
        val html = "<script>netflix.reactContext.models.graphql = JSON.parse('$escaped');</script>"
        val entries = parseNetflix(html)
        assertEquals(2, entries.length())
        assertEquals("vod", entries.getJSONObject(0).getString("kind"))
        assertEquals("Alpha", entries.getJSONObject(0).getString("name"))
        assertEquals("series", entries.getJSONObject(1).getString("kind"))
        assertEquals("Show X", entries.getJSONObject(1).getString("name"))
        assertEquals(202L, entries.getJSONObject(1).getLong("netflixId"))
    }

    @Test
    fun noHistoryDoesNotPretendToBePersonalized() {
        assertTrue(result(emptyList()).shelves.any { it.title.startsWith("Keşfet:") })
    }

    @Test
    fun tmdbNormalizerMapsMovieAndSeriesMetadata() {
        val row = JSONObject().put("id", 77).put("media_type", "tv").put("name", "Örnek").put("original_name", "Sample").put("first_air_date", "2026-02-01")
        val normalized = normalizeTmdbItem(row, "tv", rank = 1, week = "2026-02-02")
        assertEquals("series", normalized.getString("kind"))
        assertEquals("2026", normalized.getString("year"))
    }

    @Test
    fun genreAliasesKeepEnglishKeysAndTurkishPlurals() {
        assertEquals(
            listOf("Sci-Fi", "Comedy", "Crime", "Action", "Thriller"),
            discoveryGenreSet("Bilim Kurgu,COMEDY/Suç|Aksiyon,Gerilim,Comedy").toList()
        )
        assertEquals(setOf("Drama", "Comedy", "Sci-Fi"), discoveryGenreSet("Dramalar, Komediler, Bilim Kurgu ve Fantastik"))
        assertEquals(discoveryGenres.keys.toList(), discoveryGenreSet(discoveryGenres.values.joinToString(",")).toList())
        assertEquals(discoveryGenres.keys.toList(), discoveryGenreSet(discoveryGenres.keys.joinToString("/")).toList())
    }

    @Test
    fun blankAndUnknownGenresDoNotCreateRecommendations() {
        assertTrue(discoveryGenreSet("").isEmpty())
        assertTrue(discoveryGenreSet(" \t\n").isEmpty())
        assertTrue(discoveryGenreSet("Unknown,HD|2026").isEmpty())
        assertEquals(setOf("Drama"), discoveryGenreSet("Unknown,Dram"))
    }

    @Test
    fun cancelledLargeCatalogStopsBeforeBuildingRecommendations() {
        val catalog = List(10_000) { MediaItem("vod:$it", "$it", "Film $it", MediaKind.VOD) }
        val operation = Job()
        var checks = 0
        try {
            buildDiscovery(catalog, emptyList(), JSONObject(), checkCancelled = {
                if (++checks == 100) operation.cancel()
                operation.ensureActive()
            })
            fail("A cancelled library load must stop before producing recommendations.")
        } catch (_: CancellationException) {
            assertEquals(100, checks)
        }
    }

    @Test(timeout = 10_000)
    fun discoveryFeedRefreshPropagatesCancellationWithoutSwallowing() = runBlocking {
        val tempDir = createTempDirectory("discovery-cancel").toFile()
        try {
            MockWebServer().use { server ->
                repeat(4) {
                    server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
                }
                val baseUrl = server.url("/").toString().trimEnd('/')
                val feed = DiscoveryFeed(
                    file = File(tempDir, "discovery-public.json"),
                    baseClient = OkHttpClient(),
                    cinemetaBaseUrl = baseUrl,
                    netflixBaseUrl = baseUrl,
                )
                var caughtCancel = false
                val job = launch(Dispatchers.IO) {
                    try {
                        feed.refreshNow()
                    } catch (cancel: CancellationException) {
                        caughtCancel = true
                        throw cancel
                    }
                }
                assertNotNull(server.takeRequest(3, TimeUnit.SECONDS))
                withTimeout(2_000) { job.cancelAndJoin() }
                assertTrue("CancellationException must propagate out of DiscoveryFeed.refreshNow()", caughtCancel)
            }
        } finally {
            tempDir.deleteRecursively()
        }
    }
}
