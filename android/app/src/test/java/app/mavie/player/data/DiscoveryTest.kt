package app.mavie.player.data

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.ensureActive
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate

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
    fun personalRecommendationsUseHistoryNotProviderCategories() {
        val result = result()
        val shelf = result.shelves.first { it.id == "for-you-vod" }
        assertEquals("vod:comedy", shelf.items.first().id)
        assertTrue(shelf.title.startsWith("Sana Özel"))
        assertTrue(result.shelves.first { it.id == "genre-vod-Comedy" }.items.any { it.id == "vod:comedy" })
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
    fun trendingChartsExpireAndContainZeroScrapedTrademarkNames() {
        val trending = result().shelves.filter { it.id.startsWith("trending-") }
        assertEquals(2, trending.size)
        assertFalse(trending.any { it.subtitle.contains("Netflix", ignoreCase = true) })
        assertFalse(result(date = LocalDate.of(2026, 12, 1)).shelves.any { it.id.startsWith("trending-") })
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
    fun genreAliasesKeepEnglishKeysAndInputOrder() {
        assertEquals(listOf("Sci-Fi", "Comedy", "Crime", "Action", "Thriller"),
            discoveryGenreSet("Bilim Kurgu,COMEDY/Suç|Aksiyon,Gerilim,Comedy").toList())
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
}
