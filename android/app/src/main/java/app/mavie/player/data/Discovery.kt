package app.mavie.player.data

import android.content.Context
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withLock
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

private val IstanbulZone: ZoneId = ZoneId.of("Europe/Istanbul")

internal val discoveryGenres = linkedMapOf(
    "Action" to "Aksiyon", "Adventure" to "Macera", "Animation" to "Animasyon",
    "Comedy" to "Komedi", "Crime" to "Suç", "Documentary" to "Belgesel",
    "Drama" to "Dram", "Family" to "Aile", "Fantasy" to "Fantastik",
    "Horror" to "Korku", "Mystery" to "Gizem", "Romance" to "Romantik",
    "Sci-Fi" to "Bilim Kurgu", "Thriller" to "Gerilim",
)
private val extraGenreAliases = mapOf(
    "dramalar" to "Drama",
    "drama" to "Drama",
    "komediler" to "Comedy",
    "gerilimler" to "Thriller",
    "korkular" to "Horror",
    "korkufilmleri" to "Horror",
    "belgeseller" to "Documentary",
    "aksiyonvemacera" to "Action",
    "bilimkurguvefantastik" to "Sci-Fi",
    "bilimkurgu" to "Sci-Fi",
    "scifi" to "Sci-Fi",
    "sciencefiction" to "Sci-Fi",
    "sucdizileri" to "Crime",
    "sucfilmleri" to "Crime",
    "romantikfilmler" to "Romance",
    "romantikdiziler" to "Romance",
    "ailevecocuk" to "Family",
    "cocukveaile" to "Family",
    "animasyonlar" to "Animation",
    "anime" to "Animation",
    "fantastikfilmler" to "Fantasy",
    "gizemli" to "Mystery",
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
private val discoveryGenreSeparator = Regex("[,/|&]")

internal fun discoveryKey(value: String): String = fold(value)
    .replace(discoveryPrefix, "")
    .replace(discoveryTechnicalLabels, " ")
    .replace(discoveryNonAlphanumeric, "")

private fun discoveryTitles(name: String) =
    (listOf(name) + name.split(discoveryTitleSeparator)).map(::discoveryKey).filter { it.length >= 2 }.toSet()

private val discoveryGenreAliases = buildMap<String, String> {
    for ((english, turkish) in discoveryGenres) {
        putIfAbsent(discoveryKey(english), english)
        putIfAbsent(discoveryKey(turkish), english)
    }
    for ((alias, english) in extraGenreAliases) {
        putIfAbsent(alias, english)
    }
}

internal fun discoveryGenreSet(value: String): Set<String> {
    if (value.isBlank()) return emptySet()
    return value.split(discoveryGenreSeparator).mapNotNull { discoveryGenreAliases[discoveryKey(it)] }.toSet()
}

data class RecommendationShelf(val id: String, val title: String, val subtitle: String, val items: List<MediaItem>)
data class DiscoveryResult(val shelves: List<RecommendationShelf> = emptyList(), val showcase: List<MediaItem> = emptyList(), val updatedAt: Long = 0)

/** Downloads only public discovery catalogs (Cinemeta + Netflix Türkiye Top 10 + optional TMDB).
 * Viewing history and IPTV credentials never leave the device. */
internal class DiscoveryFeed internal constructor(
    private val file: File,
    baseClient: OkHttpClient = MavieBaseHttpClient,
    private val tmdbApiKey: String = "",
    private val cinemetaBaseUrl: String = "https://v3-cinemeta.strem.io",
    private val netflixBaseUrl: String = "https://www.netflix.com",
) {
    constructor(
        context: Context,
        tmdbApiKey: String = "",
        baseClient: OkHttpClient = MavieBaseHttpClient,
    ) : this(File(context.filesDir, "discovery-public.json"), baseClient, tmdbApiKey)

    private val client = baseClient.newBuilder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(18, TimeUnit.SECONDS)
        .callTimeout(25, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .retryOnConnectionFailure(true)
        .build()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val refreshMutex = Mutex()
    private val stateLock = Any()
    private val _updates = MutableStateFlow(0L)
    val updates = _updates.asStateFlow()
    private var data = runCatching { JSONObject(file.readText()) }.getOrDefault(JSONObject())
    private var job: Job? = null
    private var attempt = 0L

    fun snapshot(): JSONObject = synchronized(stateLock) {
        val now = System.currentTimeMillis()
        if (scope.isActive && now - data.optDouble("updatedAt", 0.0) * 1000 > 6 * 3600000 && job?.isActive != true && now - attempt > 900000) {
            attempt = now
            job = scope.launch { refresh() }
        }
        data
    }

    fun close() {
        synchronized(stateLock) {
            job?.cancel()
            job = null
        }
        scope.cancel()
    }

    private suspend fun get(url: String): String = client.newCall(
        Request.Builder().url(url).header("User-Agent", "Mozilla/5.0 Mavie/2.2").build()
    ).readCancellable {
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

    internal suspend fun refreshNow() = refresh()

    private suspend fun refresh() = refreshMutex.withLock {
        coroutineScope {
            val previousData = synchronized(stateLock) { data }
            val year = LocalDate.now(IstanbulZone).year
            val specs = listOf("movie", "series").flatMap { kind ->
                listOf(Triple(kind, "top", ""), Triple(kind, "year", "/genre=$year"), Triple(kind, "year", "/genre=${year - 1}")) +
                    listOf("Comedy", "Drama", "Action", "Crime", "Sci-Fi", "Horror", "Romance", "Animation")
                        .map { Triple(kind, "top", "/genre=$it") }
            }
            val gate = Semaphore(4)
            val cinemetaBase = cinemetaBaseUrl.trimEnd('/')
            val netflixBase = netflixBaseUrl.trimEnd('/')
            val cinemetaResults = specs.map { (kind, catalog, extra) ->
                async {
                    gate.acquire()
                    try {
                        try {
                            Triple(
                                kind,
                                catalog == "top" && extra.isEmpty(),
                                JSONObject(get("$cinemetaBase/catalog/$kind/$catalog$extra.json")).getJSONArray("metas"),
                            )
                        } catch (cancel: CancellationException) {
                            throw cancel
                        } catch (_: Exception) {
                            null
                        }
                    } finally {
                        gate.release()
                    }
                }
            }.awaitAll().filterNotNull()

            val metas = linkedMapOf<String, JSONObject>()
            previousData.optJSONArray("metas")?.let { a ->
                for (i in 0 until a.length()) a.optJSONObject(i)?.let { metas[it.optString("id")] = it }
            }
            for ((kind, top, rows) in cinemetaResults) {
                for (i in 0 until rows.length()) {
                    val raw = rows.optJSONObject(i) ?: continue
                    val id = raw.optString("id")
                    if (id.isBlank()) continue
                    val m = JSONObject()
                    for (key in listOf("id", "imdb_id", "moviedb_id", "name", "genres", "genre", "year", "releaseInfo", "released", "poster", "background")) {
                        if (raw.has(key)) m.put(key, raw.opt(key))
                    }
                    m.put("kind", if (kind == "movie") "vod" else "series")
                    m.put("globalRank", if (top) i + 1 else metas[id]?.optInt("globalRank", 999) ?: 999)
                    metas[id] = m
                }
            }

            val charts = JSONArray()
            for (url in listOf("$netflixBase/tudum/top10/turkey", "$netflixBase/tudum/top10/turkey/tv")) {
                val parsed = try {
                    parseNetflix(get(url))
                } catch (cancel: CancellationException) {
                    throw cancel
                } catch (_: Exception) {
                    null
                }
                parsed?.let { a ->
                    for (i in 0 until a.length()) charts.put(a.getJSONObject(i))
                }
            }
            val localizedCharts = (0 until charts.length()).map { index ->
                async {
                    gate.acquire()
                    try {
                        val entry = charts.getJSONObject(index)
                        try {
                            val html = get("$netflixBase/tr/title/${entry.optLong("netflixId")}")
                            val block = Regex("""<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>""", RegexOption.DOT_MATCHES_ALL)
                                .find(html)?.groupValues?.get(1)
                            if (block != null) {
                                val info = JSONObject(block)
                                if (info.optString("name").isNotBlank()) {
                                    entry.put("aliases", JSONArray().put(info.optString("name")))
                                }
                                if (info.optString("genre").isNotBlank()) {
                                    entry.put("genre", info.optString("genre"))
                                }
                            }
                        } catch (cancel: CancellationException) {
                            throw cancel
                        } catch (_: Exception) {
                            // Best-effort title localization; keep original Netflix entry.
                        }
                        entry
                    } finally {
                        gate.release()
                    }
                }
            }.awaitAll()

            val tmdbCharts = mutableListOf<JSONObject>()
            if (tmdbApiKey.isNotBlank()) {
                val week = LocalDate.now(IstanbulZone).toString()
                val tmdbResults = listOf("movie" to "trending/movie/week", "tv" to "trending/tv/week").map { (type, endpoint) ->
                    async {
                        try {
                            val json = JSONObject(get("https://api.themoviedb.org/3/$endpoint?api_key=$tmdbApiKey&language=tr-TR"))
                            type to json.optJSONArray("results")
                        } catch (cancel: CancellationException) {
                            throw cancel
                        } catch (_: Exception) {
                            null
                        }
                    }
                }.awaitAll().filterNotNull()
                for ((type, rows) in tmdbResults) {
                    if (rows == null) continue
                    for (i in 0 until rows.length()) {
                        val row = rows.optJSONObject(i) ?: continue
                        val id = row.optLong("id")
                        if (id <= 0) continue
                        val parsed = normalizeTmdbItem(row, type, i + 1, week)
                        metas[parsed.optString("id")] = parsed
                        tmdbCharts.add(parsed)
                    }
                }
            }

            val finalCharts = when {
                localizedCharts.isNotEmpty() -> JSONArray(localizedCharts)
                tmdbCharts.isNotEmpty() -> JSONArray(tmdbCharts)
                else -> previousData.optJSONArray("charts") ?: JSONArray()
            }
            val chartSource = when {
                localizedCharts.isNotEmpty() -> "netflix"
                tmdbCharts.isNotEmpty() -> "tmdb"
                else -> previousData.optString("chartSource", "netflix")
            }
            if (cinemetaResults.isEmpty() && localizedCharts.isEmpty() && tmdbCharts.isEmpty()) return@coroutineScope
            val updated = JSONObject()
                .put("version", 3)
                .put("updatedAt", System.currentTimeMillis() / 1000.0)
                .put("metas", JSONArray(metas.values.toList()))
                .put("charts", finalCharts)
                .put("chartSource", chartSource)
            val temp = File(file.path + ".tmp")
            temp.writeText(updated.toString())
            if (!temp.renameTo(file)) return@coroutineScope
            synchronized(stateLock) {
                data = updated
            }
            _updates.value = System.currentTimeMillis()
        }
    }
}

internal fun decodeJsStringLiteral(raw: String): String {
    if ('\\' !in raw) return raw
    val out = StringBuilder(raw.length)
    var i = 0
    while (i < raw.length) {
        val ch = raw[i]
        if (ch == '\\' && i + 1 < raw.length) {
            when (val next = raw[i + 1]) {
                '\\' -> { out.append('\\'); i += 2 }
                '\'' -> { out.append('\''); i += 2 }
                '"' -> { out.append('"'); i += 2 }
                '/' -> { out.append('/'); i += 2 }
                'n' -> { out.append('\n'); i += 2 }
                'r' -> { out.append('\r'); i += 2 }
                't' -> { out.append('\t'); i += 2 }
                'b' -> { out.append('\b'); i += 2 }
                'f' -> { out.append('\u000C'); i += 2 }
                'x' -> {
                    val code = if (i + 3 < raw.length) raw.substring(i + 2, i + 4).toIntOrNull(16) else null
                    if (code != null) {
                        out.append(code.toChar())
                        i += 4
                    } else {
                        out.append('\\')
                        i++
                    }
                }
                else -> {
                    out.append(next)
                    i += 2
                }
            }
        } else {
            out.append(ch)
            i++
        }
    }
    return out.toString()
}

private fun extractNetflixGraphqlArg(html: String): String? {
    val prefixRegex = Regex("""netflix\.reactContext\.models\.graphql\s*=\s*JSON\.parse\(\s*'""")
    val match = prefixRegex.find(html) ?: return null
    val start = match.range.last + 1
    var i = start
    while (i < html.length) {
        when (html[i]) {
            '\\' -> i += 2
            '\'' -> return html.substring(start, i)
            else -> i++
        }
    }
    return null
}

internal fun parseNetflix(html: String): JSONArray {
    val raw = extractNetflixGraphqlArg(html) ?: error("Chart format changed")
    val decoded = decodeJsStringLiteral(raw)
    val data = JSONObject(decoded).getJSONObject("data")
    val result = JSONArray()
    val seen = hashSetOf<Triple<String, String, String>>()
    for (key in data.keys()) {
        val value = data.optJSONObject(key) ?: continue
        val info = value.optJSONObject("top10Video") ?: continue
        val chart = value.optJSONObject("top10") ?: continue
        val kind = if (chart.optString("category") == "MOVIES") "vod" else "series"
        val title = info.optJSONObject("parentShow")?.optString("title")?.ifBlank { null } ?: info.optString("title")
        val week = chart.optString("weekEndDate")
        if (!seen.add(Triple(kind, title, week))) continue
        result.put(
            JSONObject()
                .put("kind", kind)
                .put("name", title)
                .put("year", info.optInt("releaseYear").takeIf { it > 0 }?.toString().orEmpty())
                .put("rank", chart.optInt("weeklyRank"))
                .put("week", week)
                .put("netflixId", info.optJSONObject("parentShow")?.optLong("videoId")?.takeIf { it > 0 } ?: info.optLong("videoId"))
                .put("source", "netflix")
        )
    }
    return result
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
        .put("source", "tmdb")
}

internal fun buildDiscovery(
    catalog: List<MediaItem>,
    history: List<MediaItem>,
    feed: JSONObject,
    today: LocalDate = LocalDate.now(IstanbulZone),
    checkCancelled: () -> Unit = {},
): DiscoveryResult {
    checkCancelled()
    val candidates = catalog.filter { it.kind == MediaKind.VOD || it.kind == MediaKind.SERIES }
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
            meta.optString("released").takeIf { it.length >= 10 && it != "null" }?.let { releaseDates[item.id] = it.take(10) }
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
            val d = java.time.Instant.ofEpochMilli(it).atZone(IstanbulZone).toLocalDate()
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
    val chartObjs = (0 until charts.length()).mapNotNull { charts.optJSONObject(it) }
    val latestWeek = chartObjs.mapNotNull { it.optString("week").takeIf { w -> w.length >= 10 } }.maxOrNull()
    val chartFresh = latestWeek != null && runCatching { ChronoUnit.DAYS.between(LocalDate.parse(latestWeek), today) in 0..21 }.getOrDefault(false)
    val isTmdbChart = feed.optString("chartSource") == "tmdb" ||
        (chartObjs.isNotEmpty() && chartObjs.all { it.optString("source") == "tmdb" })

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

    val topGenreLabels = weights.entries.sortedByDescending { it.value }.mapNotNull { discoveryGenres[it.key] }.take(2)
    val shelves = mutableListOf<RecommendationShelf>()
    fun shelf(id: String, title: String, subtitle: String, rows: List<MediaItem>) {
        if (rows.isNotEmpty()) shelves.add(RecommendationShelf(id, title, subtitle, rows.take(20)))
    }
    for ((kind, label) in listOf(MediaKind.VOD to "Filmler", MediaKind.SERIES to "Diziler")) {
        checkCancelled()
        if (chartFresh) {
            val used = hashSetOf<String>()
            val rows = chartObjs
                .filter { it.optString("week") == latestWeek && ((it.optString("kind") == "series") == (kind == MediaKind.SERIES)) }
                .sortedBy { it.optInt("rank", 99) }
                .mapNotNull { meta -> match(meta)?.takeIf { used.add(it.id) } }
            val chartSubtitle = if (isTmdbChart) "Haftalık trend listesi · $latestWeek" else "Netflix Türkiye Top 10 · $latestWeek haftası"
            shelf("turkey-${kind.key}", "Türkiye’de Popüler $label", chartSubtitle, rows)
        }
        shelf("new-${kind.key}", "Yeni Çıkan $label", "Yayın yılı ve çıkış tarihine göre", fresh.filter { it.kind == kind })
        val genreHint = if (topGenreLabels.isNotEmpty()) " · ${topGenreLabels.joinToString(", ")}" else ""
        shelf(
            "for-you-${kind.key}",
            if (weights.isNotEmpty()) "Sana Özel $label" else "Keşfet: $label",
            seeds.firstOrNull()?.let { "${it.name} ve izleme geçmişine göre$genreHint" } ?: "Türler ve güncel keşif listeleriyle",
            personalByKind[kind].orEmpty(),
        )
    }
    val orderedGenres = discoveryGenres.entries.sortedWith(
        compareByDescending<Map.Entry<String, String>> { weights[it.key] ?: 0.0 }
    )
    for ((genre, label) in orderedGenres) {
        val promoted = if ((weights[genre] ?: 0.0) > 0.0) "İzleme geçmişine göre öne çıkarıldı" else ""
        for ((kind, name) in listOf(MediaKind.VOD to "Filmleri", MediaKind.SERIES to "Dizileri")) {
            shelf("genre-${kind.key}-$genre", "$label $name", promoted, byGenre[kind to genre].orEmpty())
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
    return DiscoveryResult(shelves, showcase, (feed.optDouble("updatedAt", 0.0) * 1000).toLong())
}
