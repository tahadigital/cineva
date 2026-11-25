package app.mavie.player.data

enum class SourceMode(val key: String) {
    XTREAM("xtream"), M3U("m3u"), DEMO("demo");
    companion object { fun fromKey(key: String?): SourceMode = entries.firstOrNull { it.key == key } ?: XTREAM }
}

/** Account secrets stay in memory or Android Keystore encrypted storage. */
data class ConnectionSettings(
    val host: String = "",
    val username: String = "",
    val password: String = "",
    val sourceType: SourceMode = SourceMode.XTREAM,
    val m3uUrl: String = "",
    val epgUrl: String = "",
) {
    override fun toString(): String = "ConnectionSettings(redacted)"
}

enum class MediaKind(val key: String) {
    LIVE("live"), VOD("vod"), SERIES("series"), EPISODE("episode");
    companion object { fun fromKey(key: String): MediaKind = entries.first { it.key == key } }
}

data class AccountInfo(
    val id: String,
    val username: String,
    val host: String,
    val name: String = "Kişisel Kütüphane",
    val status: String = "Active",
    val expiresAt: Long? = null,
    val maxConnections: Int = 1,
    val sourceType: SourceMode = SourceMode.XTREAM,
    val epgUrl: String = "",
)

data class Category(val id: String, val name: String, val kind: MediaKind)

data class WatchProgress(
    val itemId: String,
    val positionSeconds: Double,
    val durationSeconds: Double,
    val completed: Boolean,
    val updatedAt: Long = System.currentTimeMillis(),
)

data class MediaItem(
    val id: String,
    val providerId: String,
    val name: String,
    val kind: MediaKind,
    val categoryId: String = "",
    val categoryName: String = "",
    val poster: String = "",
    val backdrop: String = "",
    val year: String = "",
    val rating: Double = 0.0,
    val extension: String = "mp4",
    val durationSeconds: Double = 0.0,
    val plot: String = "",
    val season: Int = 0,
    val episode: Int = 0,
    val parentId: String? = null,
    val addedAt: Long = 0,
    val isFavorite: Boolean = false,
    val progress: WatchProgress? = null,
    val videoCodec: String = "",
    val audioCodec: String = "",
    /** Bound when read from local storage; prevents stale cross-account actions. */
    val accountId: String? = null,
    val genres: String = "",
    val sourceUrl: String = "",
)

data class CatalogPage(val items: List<MediaItem>, val page: Int, val total: Int, val hasMore: Boolean)
data class Season(val number: Int, val name: String, val episodes: List<MediaItem>)
data class MediaDetail(
    val item: MediaItem,
    val seasons: List<Season> = emptyList(),
    val genres: String = "",
    val cast: String = "",
    val director: String = "",
)

internal fun MediaDetail.followingEpisode(current: MediaItem): MediaItem? {
    if (current.kind != MediaKind.EPISODE || current.parentId != item.id) return null
    val episodes = seasons.sortedBy { it.number }.flatMap { season ->
        season.episodes.sortedWith(compareBy<MediaItem> { it.episode }.thenBy { it.name }.thenBy { it.id })
    }
    val index = episodes.indexOfFirst { it.id == current.id }
    if (index < 0) return null
    val playing = episodes[index]
    return episodes.asSequence().drop(index + 1).firstOrNull { next ->
        next.season != playing.season || playing.episode <= 0 || next.episode > playing.episode
    }
}

data class HomeSections(
    val continueWatching: List<MediaItem>,
    val favorites: List<MediaItem>,
    val recentMovies: List<MediaItem>,
    val recentSeries: List<MediaItem>,
    val discovery: DiscoveryResult = DiscoveryResult(),
)
data class TrackPreference(val audioId: Int? = null, val subtitleId: Int? = null, val subtitleOff: Boolean = true)
data class Playlist(val id: String, val name: String, val count: Int, val items: List<MediaItem> = emptyList())
data class UserProfile(val id: String, val name: String, val avatarColor: String, val isKids: Boolean = false, val hasPin: Boolean = false, val active: Boolean = false)
data class SyncState(val running: Boolean = false, val message: String = "", val completedSteps: Int = 0, val totalSteps: Int = 6, val error: String? = null)

enum class MavieErrorCode {
    UNKNOWN,
    OFFLINE,
    DNS_FAILED,
    TIMEOUT,
    TLS_FAILED,
    CONNECTION_REFUSED,
    CONNECTION_RESET,
    AUTH_REJECTED,
    SUBSCRIPTION_INACTIVE,
    NOT_FOUND,
    RATE_LIMITED,
    SERVER_ERROR,
    HTTP_ERROR,
    INVALID_RESPONSE,
    EMPTY_CATALOG,
    PAYLOAD_TOO_LARGE,
    INVALID_INPUT,
    UNSAFE_URL,
    STORAGE_ERROR,
    KEYSTORE_ERROR,
    PROFILE_NOT_FOUND,
    PROFILE_PIN_INVALID,
    PLAYBACK_INVALID_SOURCE,
    PLAYBACK_INIT_FAILED,
    PLAYBACK_STALLED,
    PLAYBACK_NETWORK_LOST,
    SYNC_PAIR_FAILED,
}

/** Only user-safe text is carried outward; never append HTTP URLs or bodies. */
class IptvException(
    message: String,
    val code: MavieErrorCode = MavieErrorCode.UNKNOWN,
    cause: Throwable? = null,
) : Exception(message, cause)
