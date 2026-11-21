package app.mavie.player.data

import android.content.Context
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import java.util.concurrent.TimeUnit
import kotlin.math.pow

internal val discoveryGenres = linkedMapOf(
    "Action" to "Aksiyon", "Adventure" to "Macera", "Animation" to "Animasyon",
    "Comedy" to "Komedi", "Crime" to "Suç", "Documentary" to "Belgesel",
    "Drama" to "Dram", "Family" to "Aile", "Fantasy" to "Fantastik",
    "Horror" to "Korku", "Mystery" to "Gizem", "Romance" to "Romantik",
    "Sci-Fi" to "Bilim Kurgu", "Thriller" to "Gerilim",
)
private val tmdbGenres = mapOf(
    28 to "Action", 12 to "Adventure", 16 to "Animation", 35 to "Comedy", 80 to "Crime",
    99 to "Documentary", 18 to "Drama", 10751 to "Family", 14 to "Fantasy", 27 to "Horror",
    9648 to "Mystery", 10749 to "Romance", 878 to "Sci-Fi", 53 to "Thriller",
    10759 to "Action", 10765 to "Sci-Fi",
)
private val discoveryPrefix = Regex("^\\s*(?:tr|en|us|uk|de|fr|es|vip)\\s*[:|]\\s*")
private val discoveryTechnicalLabels = Regex("\\b(?:19|20)\\d{2}\\b|\\b(?:tr|en|trsub|eng|turkce|altyazili|dublaj|uhd|fhd|hd|4k|1080p|720p)\\b")
private val discoveryNonAlphanumeric = Regex("[^a-z0-9]")
private val discoveryTitleSeparator = Regex("\\s+[|/]\\s+|\\s+\\([^)]*\\)\\s*")
private val discoveryGenreSeparator = Regex("[,/|]")
internal fun discoveryKey(value: String): String = fold(value)
    .replace(discoveryPrefix, "")
    .replace(discoveryTechnicalLabels, " ")
    .replace(discoveryNonAlphanumeric, "")
private fun discoveryTitles(name: String) = (listOf(name) + name.split(discoveryTitleSeparator)).map(::discoveryKey).filter { it.length >= 2 }.toSet()
private val discoveryGenreAliases = buildMap<String, String> {
    for ((english, turkish) in discoveryGenres) {
        putIfAbsent(discoveryKey(english), english)
        putIfAbsent(discoveryKey(turkish), english)
    }
}
internal fun discoveryGenreSet(value: String): Set<String> {
    if (value.isBlank()) return emptySet()
    return value.split(discoveryGenreSeparator).mapNotNull { discoveryGenreAliases[discoveryKey(it)] }.toSet()
}

data class RecommendationShelf(val id: String, val title: String, val subtitle: String, val items: List<MediaItem>)
data class DiscoveryResult(val shelves: List<RecommendationShelf> = emptyList(), val showcase: List<MediaItem> = emptyList(), val updatedAt: Long = 0)

/** Local discovery & optional official TMDB feed. Never scrapes third-party sites. */
internal class DiscoveryFeed(context: Context, private val tmdbApiKey: String = "") {
    private val file = File(context.filesDir, "discovery-public.json")
    private val client = OkHttpClient.Builder().connectTimeout(12, TimeUnit.SECONDS).readTimeout(18, TimeUnit.SECONDS).callTimeout(25, TimeUnit.SECONDS).build()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val _updates = MutableStateFlow(0L)
    val updates = _updates.asStateFlow()
    @Volatile private var data = runCatching { JSONObject(file.readText()) }.getOrDefault(JSONObject())
    @Volatile private var job: Job? = null
    private var attempt = 0L

    @Synchronized fun snapshot(): JSONObject {
        val now = System.currentTimeMillis()
        if (tmdbApiKey.isNotBlank() && now - data.optDouble("updatedAt", 0.0) * 1000 > 6 * 3600000 && job?.isActive != true && now - attempt > 900000) {
            attempt = now
            job = scope.launch { refresh() }
        }
        return data
    }

    private fun get(url: String): String = client.newCall(Request.Builder().url(url).header("User-Agent", "Mavie/2.1").build()).execute().use {
        if (!it.isSuccessful) error("Discovery unavailable")
        val body = it.body ?: error("Empty discovery")
        body.byteStream().use { stream ->
            val buffer = java.io.ByteArrayOutputStream()
            val chunk = ByteArray(8192)
            while (true) {
                val n = stream.read(chunk)
                if (n < 0) break
                if (buffer.size() + n > 5 * 1024 * 1024) error("Discovery too large")
                buffer.write(chunk, 0, n)
            }
            buffer.toString("UTF-8")
        }
    }

    private suspend fun refresh() = coroutineScope {
        if (tmdbApiKey.isBlank()) return@coroutineScope
        val week = LocalDate.now(ZoneId.of("UTC")).toString()
        val specs = listOf("movie" to "trending/movie/week", "tv" to "trending/tv/week")
        val results = specs.map { (type, endpoint) ->
            async {
                runCatching {
                    val json = JSONObject(get("https://api.themoviedb.org/3/$endpoint?api_key=$tmdbApiKey&language=tr-TR"))
                    type to json.optJSONArray("results")
                }.getOrNull()
            }
        }.awaitAll().filterNotNull()
        val metas = JSONArray()
        val charts = JSONArray()
        for ((type, rows) in results) {
            if (rows == null) continue
            for (i in 0 until rows.length()) {
                val row = rows.optJSONObject(i) ?: continue
                val id = row.optLong("id")
                if (id <= 0) continue
                val parsed = normalizeTmdbItem(row, type, i + 1, week)
                metas.put(parsed)
                charts.put(parsed)
            }
        }
        if (metas.length() == 0) return@coroutineScope
        val updated = JSONObject().put("version", 2).put("updatedAt", System.currentTimeMillis() / 1000.0)
            .put("metas", metas).put("charts", charts)
        val temp = File(file.path + ".tmp")
        temp.writeText(updated.toString())
        if (!temp.renameTo(file)) return@coroutineScope
        data = updated
        _updates.value = System.currentTimeMillis()
    }
}

internal fun normalizeTmdbItem(row: JSONObject, mediaType: String, rank: Int = 999, week: String = ""): JSONObject {
    val kind = if ((row.optString("media_type").ifBlank { mediaType }) == "tv") "series" else "vod"
    val title = row.optString("title", row.optString("name"))
    val original = row.optString("original_title", row.optString("original_name"))
    val released = row.optString("release_date", row.optString("first_air_date")).take(10)
    val genres = JSONArray()
    row.optJSONArray("genre_ids")?.let { ids ->
        for (i in 0 until ids.length()) tmdbGenres[ids.optInt(i)]?.let(genres::put)
    }
    return JSONObject()
        .put("id", "tmdb:$kind:${row.optLong("id")}")
        .put("moviedb_id", row.optLong("id").toString())
        .put("kind", kind)
        .put("name", original.ifBlank { title })
        .put("aliases", JSONArray().apply { if (title.isNotBlank()) put(title) })
        .put("genres", genres)
        .put("year", released.take(4))
        .put("released", released)
        .put("globalRank", rank)
        .put("rank", rank)
        .put("week", week)
}

internal fun buildDiscovery(
    catalog: List<MediaItem>,
    history: List<MediaItem>,
    feed: JSONObject,
    today: LocalDate = LocalDate.now(ZoneId.of("UTC")),
    checkCancelled: () -> Unit = {},
): DiscoveryResult {
    checkCancelled()
    val candidates = catalog.filter { it.kind in setOf(MediaKind.VOD, MediaKind.SERIES) }.map { it.copy() }
    val index = HashMap<Pair<MediaKind, String>, MutableList<MediaItem>>()
    for (item in candidates) {
        checkCancelled()
        for (title in discoveryTitles(item.name)) index.getOrPut(item.kind to title) { mutableListOf() }.add(item)
    }
    val extraGenres = HashMap<String, String>()
    val releaseDates = HashMap<String, String>()
    val ranks = HashMap<String, Int>()
    fun match(meta: JSONObject): MediaItem? {
        val kind = if (meta.optString("kind") == "series") MediaKind.SERIES else MediaKind.VOD
        val options = linkedMapOf<String, MediaItem>()
        val names = buildList {
            add(meta.optString("name"))
            meta.optJSONArray("aliases")?.let { a -> for (i in 0 until a.length()) add(a.optString(i)) }
        }
        for (name in names) for (title in discoveryTitles(name)) index[kind to title]?.forEach { options[it.id] = it }
        val year = meta.optString("year", meta.optString("releaseInfo")).take(4)
        return options.values.filter {
            !year.all(Char::isDigit) || year.isBlank() || !it.year.all(Char::isDigit) || it.year.isBlank() || it.year == year || kind == MediaKind.SERIES
        }.maxWithOrNull(compareBy<MediaItem> { it.poster.isNotBlank() }.thenBy { it.rating })
    }

    fun applyMeta(array: JSONArray?) {
        if (array == null) return
        for (i in 0 until array.length()) {
            checkCancelled()
            val meta = array.optJSONObject(i) ?: continue
            val item = match(meta) ?: continue
            val g = meta.optJSONArray("genres")?.let { a -> (0 until a.length()).joinToString(",") { a.optString(it) } }
                ?: meta.optString("genre")
            if (discoveryGenreSet(g).isNotEmpty()) extraGenres[item.id] = discoveryGenreSet(g).joinToString(",")
            meta.optString("released").takeIf { it.length >= 10 }?.let { releaseDates[item.id] = it.take(10) }
            meta.optInt("globalRank", 0).takeIf { it > 0 }?.let { ranks[item.id] = it }
        }
    }
    applyMeta(feed.optJSONArray("metas"))
    applyMeta(feed.optJSONArray("charts"))

    fun genresFor(item: MediaItem) = discoveryGenreSet(extraGenres[item.id] ?: item.genres)
    val unique = linkedMapOf<Triple<MediaKind, String, String>, MediaItem>()
    for (item in candidates) {
        checkCancelled()
        val token = Triple(item.kind, discoveryKey(item.name), item.year)
        val prev = unique[token]
        if (prev == null || genresFor(item).size > genresFor(prev).size) unique[token] = item
    }
    val pool = unique.values.toList()
    val byId = (catalog + pool).associateBy { it.id }
    val watched = hashSetOf<String>()
    val weights = HashMap<String, Double>()
    val seeds = mutableListOf<MediaItem>()
    for (entry in history) {
        checkCancelled()
        val p = entry.progress
        val target = entry.parentId ?: entry.id
        val item = byId[target] ?: continue
        if ((p?.positionSeconds ?: 0.0) > 0 || p?.completed == true) watched.add(target)
        if ((p?.positionSeconds ?: 0.0) < 60 && p?.completed != true && !entry.isFavorite) continue
        var affinity = 1.0 + minOf(1.0, (p?.positionSeconds ?: 0.0) / maxOf(1.0, p?.durationSeconds ?: 0.0)) + if (entry.isFavorite) 2.0 else 0.0
        val days = p?.updatedAt?.takeIf { it > 0 }?.let {
            val d = java.time.Instant.ofEpochMilli(it).atZone(ZoneId.of("UTC")).toLocalDate()
            ChronoUnit.DAYS.between(d, today).coerceAtLeast(0).toDouble()
        } ?: 30.0
        affinity *= 0.5.pow(days / 90.0)
        for (g in genresFor(item)) weights[g] = (weights[g] ?: 0.0) + affinity
        if (genresFor(item).isNotEmpty()) seeds.add(item)
    }

    fun score(item: MediaItem) = genresFor(item).sumOf { weights[it] ?: 0.0 } +
        item.rating.coerceIn(0.0, 10.0) * .08 + 1.0 / (1.0 + (ranks[item.id] ?: 999))

    val cutoff = today.minusDays(365)
    val fresh = pool.filter { item ->
        val y = item.year.toIntOrNull()
        val r = releaseDates[item.id]?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
        y != null && y in (today.year - 1)..today.year && (if (r != null) !r.isBefore(cutoff) && !r.isAfter(today) else y == today.year)
    }.sortedWith(compareByDescending<MediaItem> { releaseDates[it.id] ?: it.year }.thenBy { ranks[it.id] ?: 999 })

    val charts = feed.optJSONArray("charts") ?: JSONArray()
    val latestWeek = (0 until charts.length()).mapNotNull { charts.optJSONObject(it)?.optString("week")?.takeIf { w -> w.length >= 10 } }.maxOrNull()
    val chartFresh = latestWeek != null && runCatching { ChronoUnit.DAYS.between(LocalDate.parse(latestWeek), today) in 0..21 }.getOrDefault(false)
    val ranked = pool.sortedByDescending(::score)
    val personalByKind = hashMapOf(MediaKind.VOD to mutableListOf<MediaItem>(), MediaKind.SERIES to mutableListOf<MediaItem>())
    val byGenre = HashMap<Pair<MediaKind, String>, MutableList<MediaItem>>()
    for (item in ranked) {
        checkCancelled()
        val gs = genresFor(item)
        if (gs.isEmpty()) continue
        if (item.id !in watched) {
            personalByKind[item.kind]?.let { bucket -> if (bucket.size < 20) bucket.add(item) }
        }
        for (g in gs) {
            val bucket = byGenre.getOrPut(item.kind to g) { mutableListOf() }
            if (bucket.size < 20) bucket.add(item)
        }
    }

    val shelves = mutableListOf<RecommendationShelf>()
    fun shelf(id: String, title: String, subtitle: String, rows: List<MediaItem>) {
        if (rows.isNotEmpty()) shelves.add(RecommendationShelf(id, title, subtitle, rows.take(20)))
    }
    for ((kind, label) in listOf(MediaKind.VOD to "Filmler", MediaKind.SERIES to "Diziler")) {
        checkCancelled()
        if (chartFresh) {
            val used = hashSetOf<String>()
            val rows = (0 until charts.length()).mapNotNull { charts.optJSONObject(it) }
                .filter { it.optString("week") == latestWeek && ((it.optString("kind") == "series") == (kind == MediaKind.SERIES)) }
                .sortedBy { it.optInt("rank", 99) }
                .mapNotNull { meta -> match(meta)?.takeIf { used.add(it.id) } }
            shelf("trending-${kind.key}", "Güncel Popüler $label", "Haftalık trend listesi · $latestWeek", rows)
        }
        shelf("new-${kind.key}", "Yeni Çıkan $label", "Yayın yılı ve çıkış tarihine göre", fresh.filter { it.kind == kind })
        shelf(
            "for-you-${kind.key}",
            if (weights.isNotEmpty()) "Sana Özel $label" else "Keşfet: $label",
            seeds.firstOrNull()?.let { "${it.name} ve izleme geçmişine göre" } ?: "Türler ve güncel seçkilerle",
            personalByKind[kind].orEmpty(),
        )
    }
    for ((genre, label) in discoveryGenres) {
        for ((kind, name) in listOf(MediaKind.VOD to "Filmleri", MediaKind.SERIES to "Dizileri")) {
            shelf("genre-${kind.key}-$genre", "$label $name", "", byGenre[kind to genre].orEmpty())
        }
    }
    val films = fresh.filter { it.kind == MediaKind.VOD && it.id !in watched && it.poster.isNotBlank() }.take(4)
        .ifEmpty { ranked.filter { it.kind == MediaKind.VOD && it.poster.isNotBlank() }.take(4) }
    val shows = fresh.filter { it.kind == MediaKind.SERIES && it.id !in watched && it.poster.isNotBlank() }.take(4)
        .ifEmpty { ranked.filter { it.kind == MediaKind.SERIES && it.poster.isNotBlank() }.take(4) }
    val showcase = buildList {
        for (i in 0 until maxOf(films.size, shows.size)) {
            films.getOrNull(i)?.let(::add)
            shows.getOrNull(i)?.let(::add)
        }
    }
    return DiscoveryResult(shelves, showcase, feed.optDouble("updatedAt", 0.0).toLong())
}
