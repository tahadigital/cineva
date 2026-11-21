package app.mavie.player.ui

/** Presentation models: no provider address or account secret belongs here. */
data class UiMedia(
    val id: String,
    val title: String,
    val kind: String,
    val poster: String = "",
    val backdrop: String = "",
    val year: String = "",
    val category: String = "",
    val rating: Double = 0.0,
    val overview: String = "",
    val progressPositionMs: Long = 0,
    val progressDurationMs: Long = 0,
    val favorite: Boolean = false,
    val episodeNumber: Int = 0,
) {
    val progressFraction: Float
        get() = if (progressDurationMs > 0) {
            (progressPositionMs.toFloat() / progressDurationMs).coerceIn(0f, 1f)
        } else 0f
    val canResume: Boolean get() = progressPositionMs > 0 && progressFraction < .95f
}

data class UiRecommendationShelf(val id: String,val title: String,val subtitle: String,val items: List<UiMedia>)

data class UiCategory(val id: String, val title: String)
data class UiSeason(val id: String, val title: String, val episodes: List<UiMedia>)
data class UiCollection(val id: String, val title: String, val count: Int = 0)

enum class LibraryTab(val title: String) {
    HOME("Ana Sayfa"), LIVE("Canlı TV"), FILMS("Filmler"), SERIES("Diziler"),
    SPORTS("Rehber"), SEARCH("Ara"), FAVORITES("Kütüphanem"), PLAYLISTS("Listelerim")
}

data class LibraryUiState(
    val tab: LibraryTab = LibraryTab.HOME,
    val query: String = "",
    val categories: List<UiCategory> = emptyList(),
    val selectedCategoryId: String = "",
    val items: List<UiMedia> = emptyList(),
    val continueWatching: List<UiMedia> = emptyList(),
    val seriesItems: List<UiMedia> = emptyList(),
    val favorites: List<UiMedia> = emptyList(),
    val collections: List<UiCollection> = emptyList(),
    val featured: UiMedia? = null,
    val showcase: List<UiMedia> = emptyList(),
    val recommendations: List<UiRecommendationShelf> = emptyList(),
    val title: String = "",
    val totalCount: Int = 0,
    val loading: Boolean = false,
    val refreshing: Boolean = false,
    val hasMore: Boolean = false,
    val error: String? = null,
)

data class DetailUiState(
    val media: UiMedia,
    val overview: String = media.overview,
    val genre: String = "",
    val cast: String = "",
    val director: String = "",
    val durationMs: Long = media.progressDurationMs,
    val seasons: List<UiSeason> = emptyList(),
    val selectedSeasonId: String = "",
    val loading: Boolean = false,
    val error: String? = null,
)

internal fun playbackTime(ms: Long): String {
    val totalSeconds = (ms.coerceAtLeast(0) / 1000)
    val hours = totalSeconds / 3600
    val minutes = totalSeconds / 60 % 60
    val seconds = totalSeconds % 60
    return if (hours > 0) "%d:%02d:%02d".format(hours, minutes, seconds)
    else "%d:%02d".format(minutes, seconds)
}

internal fun mediaKind(kind: String): String = when (kind) {
    "live" -> "Canlı yayın"
    "series" -> "Dizi"
    "episode" -> "Bölüm"
    else -> "Film"
}
