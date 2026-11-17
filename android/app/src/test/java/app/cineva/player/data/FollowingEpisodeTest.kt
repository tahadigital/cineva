package app.cineva.player.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class FollowingEpisodeTest {
    private val series = MediaItem("series:15", "15", "Dizi", MediaKind.SERIES)
    private fun episode(id: String, season: Int, number: Int, title: String = id) =
        MediaItem("episode:$id", id, title, MediaKind.EPISODE, season = season, episode = number, parentId = series.id)

    @Test fun ordersEpisodesAcrossSeasonsAndSkipsDuplicateVariants() {
        val first = episode("a", 1, 1)
        val duplicate = episode("alternate", 1, 1, "Yedek ses")
        val later = episode("b", 1, 3)
        val finale = episode("c", 3, 1)
        val detail = MediaDetail(series, listOf(Season(3, "", listOf(finale)), Season(1, "", listOf(later, duplicate, first))))
        assertEquals(later, detail.followingEpisode(first))
        assertEquals(later, detail.followingEpisode(duplicate))
        assertEquals(finale, detail.followingEpisode(later))
        assertNull(detail.followingEpisode(finale))
    }

    @Test fun unavailableEpisodeAndMoviesHaveNoSuccessor() {
        val first = episode("a", 1, 1)
        val detail = MediaDetail(series, listOf(Season(1, "", listOf(first))))
        assertNull(detail.followingEpisode(episode("missing", 1, 1)))
        assertNull(detail.followingEpisode(first.copy(parentId = "series:99")))
        assertNull(detail.followingEpisode(first.copy(kind = MediaKind.VOD)))
    }
}
