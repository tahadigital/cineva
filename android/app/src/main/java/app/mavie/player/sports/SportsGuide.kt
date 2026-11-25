package app.mavie.player.sports

import app.mavie.player.data.HttpStatusException
import app.mavie.player.data.IptvException
import app.mavie.player.data.MavieBaseHttpClient
import app.mavie.player.data.MavieErrorCode
import app.mavie.player.data.UrlSecurity
import app.mavie.player.data.classifyHttpError
import app.mavie.player.data.classifyIoException
import app.mavie.player.data.readCancellable
import app.mavie.player.readBounded
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.Request
import org.json.JSONObject
import org.json.JSONTokener
import org.w3c.dom.Element
import org.xml.sax.EntityResolver
import org.xml.sax.InputSource
import java.io.ByteArrayInputStream
import java.io.IOException
import java.io.StringReader
import java.text.Normalizer
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.zip.GZIPInputStream
import javax.xml.XMLConstants
import javax.xml.parsers.DocumentBuilderFactory

internal val Istanbul: ZoneId = ZoneId.of("Europe/Istanbul")
internal const val SporEkraniSource = "https://www.sporekrani.com/home/day/"
private const val SporEkraniMarker = "window.__INITIAL_STATE__="
private const val MaxSporEkraniBytes = 4 * 1024 * 1024
private const val MaxPageBytes = 8 * 1024 * 1024
private const val SporEkraniFreshMs = 5 * 60_000L
private const val FreshMs = 15 * 60_000L
private const val MaxStaleMs = 12 * 60 * 60_000L

internal enum class SportsSourceMode { AUTO, SPOREKRANI, XMLTV }

internal data class SportBroadcast(
    val id: String,
    val title: String,
    val sport: String,
    val league: String,
    val time: String,
    val featured: Boolean,
    val channels: List<String>,
)

internal data class SportsListings(
    val events: List<SportBroadcast>,
    val stale: Boolean = false,
    val configured: Boolean = true,
    val sourceType: String = "sporekrani",
)

internal object SportsChannels {
    private val region = Regex("^\\s*(?:(?:vip\\s+)?(?:tr|en|us|uk|de|fr|es)|turkey|intl)\\s*[:|➤\\-]\\s*")
    private val quality = Regex("(?:[\\s|\\[\\]()\\-]+(?:fhd|hd|uhd|sd|raw|hevc|h265|4k|1080p|720p)\\b[\\s|\\[\\]()\\-]*)+$")
    private val punctuation = Regex("[^a-z0-9+]")
    private val marks = Regex("\\p{M}+")
    private val aliases = mapOf(
        "ssport1" to "ssport",
        "smartsporhd" to "sporsmart",
        "smartspor" to "sporsmart",
        "smartspor2" to "sporsmart2",
        "trtsporstar" to "trtsporyildiz",
    )

    fun fold(text: String): String = Normalizer.normalize(
        text.replace('ı', 'i').replace('İ', 'i'), Normalizer.Form.NFKD
    ).replace(marks, "").lowercase(Locale.ROOT)

    fun key(name: String): String {
        val normalized = fold(name).replace(region, "").replace(quality, "").replace(punctuation, "")
        return aliases[normalized] ?: normalized
    }
}

internal class SportsGuideException(
    message: String,
    val code: MavieErrorCode,
    cause: Throwable? = null,
) : IOException(message, cause)

internal object SportsGuide {
    private data class Cached(val fetchedAt: Long, val events: List<SportBroadcast>)
    private val cache = ConcurrentHashMap<String, Cached>()
    private val client = MavieBaseHttpClient.newBuilder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .callTimeout(30, TimeUnit.SECONDS)
        .followRedirects(false)
        .followSslRedirects(false)
        .retryOnConnectionFailure(true)
        .build()
    private val spaces = Regex("\\s+")
    private val commentaryNoise = Regex("basin toplantisi|spor bulteni|mac (?:onu|sonu|ozel)|tekrar")
    private val startTime = Regex("(?:[01]\\d|2[0-3]):[0-5]\\d:[0-5]\\d")
    private val xmltvTs = Regex("^(\\d{4})(\\d{2})(\\d{2})(\\d{2})(\\d{2})(\\d{2})(?:\\s*([+-]\\d{4}))?")
    private val sportKeyword = Regex("\\b(sport|sports|spor|futbol|football|soccer|basketbol|basketball|tennis|tenis|motorsport|formula|racing|boxing|ufc|golf)\\b", RegexOption.IGNORE_CASE)
    private val timeFormat = DateTimeFormatter.ofPattern("HH:mm")

    private fun String.clean(max: Int): String = trim().replace(spaces, " ").take(max)

    private fun JSONObject.label(key: String, max: Int = 180): String =
        (opt(key) as? String).orEmpty().clean(max)

    /** Parse Spor Ekranı SSR embedded JSON safely (never executes scripts).
     * Supports both current (`common.eventRows` + `common.eventChannels`) and legacy (`common.events`). */
    internal fun parseSporekrani(page: String, day: LocalDate): List<SportBroadcast> {
        val markerAt = page.indexOf(SporEkraniMarker)
        if (markerAt == -1) throw SportsGuideException("Spor yayın rehberi okunamadı.", MavieErrorCode.INVALID_RESPONSE)
        val raw = page.substring(markerAt + SporEkraniMarker.length).substringBefore("</script>")
        val root = JSONTokener(raw).nextValue() as? JSONObject ?: throw SportsGuideException("Spor yayın rehberi okunamadı.", MavieErrorCode.INVALID_RESPONSE)
        val common = root.optJSONObject("common") ?: throw SportsGuideException("Spor yayın rehberi okunamadı.", MavieErrorCode.INVALID_RESPONSE)
        val rows = common.optJSONArray("eventRows") ?: common.optJSONArray("events")
            ?: throw SportsGuideException("Spor yayın rehberi okunamadı.", MavieErrorCode.INVALID_RESPONSE)
        val channelMap = common.optJSONObject("eventChannels")
        val prefix = "$day "
        var dateMatches = rows.length() == 0
        val ids = mutableSetOf<String>()
        val events = buildList {
            for (i in 0 until rows.length()) {
                val row = rows.optJSONObject(i) ?: continue
                val start = row.label("date_time")
                if (!start.startsWith(prefix)) continue
                dateMatches = true
                if (!startTime.matches(start.removePrefix(prefix))) continue
                val id = (row.opt("id") as? Number)?.toString() ?: continue
                val sport = row.label("sport_name", 50)
                val title = row.label("name")
                val type = row.label("event_type_name")
                if (title.isBlank() || sport.isBlank() || SportsChannels.fold(sport) == "programlar") continue
                if (type != "match" && (type != "commentary" || commentaryNoise.containsMatchIn(SportsChannels.fold(title)))) continue
                val rawChannels = row.optJSONArray("channels") ?: continue
                val names = (0 until rawChannels.length()).mapNotNull { index ->
                    val entry = rawChannels.opt(index)
                    val chObj = when (entry) {
                        is JSONObject -> entry
                        is Number -> channelMap?.optJSONObject(entry.toString())
                        is String -> channelMap?.optJSONObject(entry)
                        else -> null
                    } ?: return@mapNotNull null
                    if (chObj.optInt("active", 1) == 0) null
                    else chObj.label("name", 100).takeIf { it.isNotBlank() && SportsChannels.key(it) != "yayinyok" }
                }.distinct()
                if (names.isEmpty() || !ids.add(id)) continue
                val qualifier = row.label("post_fix", 90)
                val display = if (qualifier.isBlank() || title.contains(qualifier)) title else "$title · $qualifier"
                add(
                    SportBroadcast(
                        id = id,
                        title = display,
                        sport = sport,
                        league = row.label("league_name"),
                        time = start.substring(11, 16),
                        featured = row.optInt("featured") == 1,
                        channels = names,
                    )
                )
            }
        }
        if (!dateMatches) throw SportsGuideException("Yayın akışı seçilen gün için doğrulanamadı.", MavieErrorCode.INVALID_RESPONSE)
        return events.sortedWith(compareBy(SportBroadcast::time, SportBroadcast::id))
    }

    private fun parseXmltvTime(raw: String?, zone: ZoneId): ZonedDateTime? {
        val m = xmltvTs.matchEntire(raw.orEmpty().trim()) ?: return null
        val (y, mo, d, h, mi, s, off) = m.destructured
        val ldt = runCatching { LocalDateTime.of(y.toInt(), mo.toInt(), d.toInt(), h.toInt(), mi.toInt(), s.toInt()) }.getOrNull() ?: return null
        return if (off.isNotBlank()) {
            val offset = ZoneOffset.of("${off[0]}${off.substring(1, 3)}:${off.substring(3, 5)}")
            ZonedDateTime.of(ldt, offset).withZoneSameInstant(zone)
        } else {
            ZonedDateTime.of(ldt, zone)
        }
    }

    internal fun parseXmltv(rawBytes: ByteArray, day: LocalDate, zone: ZoneId = Istanbul): List<SportBroadcast> {
        val bytes = if (rawBytes.size >= 2 && rawBytes[0] == 0x1f.toByte() && rawBytes[1] == 0x8b.toByte()) {
            GZIPInputStream(ByteArrayInputStream(rawBytes)).use { it.readBounded(MaxPageBytes * 2) }
        } else {
            rawBytes
        }
        return parseXmltv(bytes.toString(Charsets.UTF_8), day, zone)
    }

    internal fun parseXmltv(xmlText: String, day: LocalDate, zone: ZoneId = Istanbul): List<SportBroadcast> {
        if (xmlText.contains("<!ENTITY", ignoreCase = true) || xmlText.contains("<!DOCTYPE", ignoreCase = true)) {
            throw SportsGuideException("Güvenlik nedeniyle XMLTV DTD bildirimlerine izin verilmiyor.", MavieErrorCode.UNSAFE_URL)
        }
        val factory = DocumentBuilderFactory.newInstance().apply {
            isNamespaceAware = false
            isExpandEntityReferences = false
            isXIncludeAware = false
            runCatching { setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true) }
            runCatching { setFeature("http://apache.org/xml/features/disallow-doctype-decl", true) }
            runCatching { setFeature("http://xml.org/sax/features/external-general-entities", false) }
            runCatching { setFeature("http://xml.org/sax/features/external-parameter-entities", false) }
            runCatching { setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false) }
        }
        val doc = try {
            val builder = factory.newDocumentBuilder()
            builder.setEntityResolver(EntityResolver { _, _ ->
                throw SportsGuideException("Güvenlik nedeniyle harici XML varlıklarına izin verilmiyor.", MavieErrorCode.UNSAFE_URL)
            })
            builder.parse(InputSource(StringReader(xmlText)))
        } catch (err: SportsGuideException) {
            throw err
        } catch (err: Exception) {
            throw SportsGuideException("XMLTV yayın rehberi okunamadı.", MavieErrorCode.INVALID_RESPONSE, err)
        }
        val root = doc.documentElement
        if (!root.tagName.equals("tv", ignoreCase = true)) {
            throw SportsGuideException("Geçerli bir XMLTV dosyası değil.", MavieErrorCode.INVALID_RESPONSE)
        }

        val channelNames = mutableMapOf<String, List<String>>()
        val channels = root.getElementsByTagName("channel")
        for (i in 0 until channels.length) {
            val el = channels.item(i) as? Element ?: continue
            val cid = el.getAttribute("id").clean(120)
            if (cid.isBlank()) continue
            val names = buildList {
                val dn = el.getElementsByTagName("display-name")
                for (j in 0 until dn.length) {
                    dn.item(j).textContent.orEmpty().clean(100).takeIf { it.isNotBlank() }?.let(::add)
                }
            }.distinct()
            if (names.isNotEmpty()) channelNames[cid] = names
        }

        val events = mutableListOf<SportBroadcast>()
        val seenIds = mutableSetOf<String>()
        val programmes = root.getElementsByTagName("programme")
        for (i in 0 until programmes.length) {
            val prog = programmes.item(i) as? Element ?: continue
            val start = parseXmltvTime(prog.getAttribute("start"), zone) ?: continue
            if (start.toLocalDate() != day) continue
            val chId = prog.getAttribute("channel").clean(120)
            val title = prog.getElementsByTagName("title").let { if (it.length > 0) it.item(0).textContent.orEmpty().clean(180) else "" }
            if (chId.isBlank() || title.isBlank()) continue
            val desc = prog.getElementsByTagName("desc").let { if (it.length > 0) it.item(0).textContent.orEmpty().clean(240) else "" }
            val cats = buildList {
                val cs = prog.getElementsByTagName("category")
                for (j in 0 until cs.length) cs.item(j).textContent.orEmpty().clean(60).takeIf { it.isNotBlank() }?.let(::add)
            }
            val eid = "$chId:${start.toEpochSecond()}:$i"
            if (!seenIds.add(eid)) continue
            val isSport = cats.any { sportKeyword.containsMatchIn(it) } || sportKeyword.containsMatchIn(title)
            val label = cats.firstOrNull() ?: if (isSport) "Spor" else "Canlı Yayın"
            val chs = channelNames[chId] ?: listOf(chId)
            events.add(
                SportBroadcast(
                    id = eid,
                    title = title,
                    sport = label,
                    league = cats.getOrNull(1) ?: desc.take(90),
                    time = start.format(timeFormat),
                    featured = isSport,
                    channels = chs,
                )
            )
        }
        return events.sortedWith(compareBy(SportBroadcast::time, SportBroadcast::id))
    }

    private suspend fun fetchGuideBytes(initialUrl: HttpUrl, userAgent: String, maxBytes: Int): ByteArray {
        var currentUrl = initialUrl
        val initialWasPublic = !UrlSecurity.isPrivateOrLoopback(initialUrl.host)
        for (hop in 0..5) {
            val request = Request.Builder().url(currentUrl).header("User-Agent", userAgent).build()
            val nextOrBytes = client.newCall(request).readCancellable { response ->
                if (response.code in setOf(301, 302, 303, 307, 308)) {
                    val location = response.header("Location")
                        ?: throw SportsGuideException("Yönlendirme adresi geçersiz.", MavieErrorCode.UNSAFE_URL)
                    val resolved = currentUrl.resolve(location)
                        ?: throw SportsGuideException("Yönlendirme adresi güvenli değil.", MavieErrorCode.UNSAFE_URL)
                    if (UrlSecurity.hasUrlCredentials(currentUrl)) {
                        if (!resolved.host.equals(currentUrl.host, ignoreCase = true)) {
                            throw SportsGuideException("Kimlik bilgisi içeren farklı sunucuya yönlendirme engellendi.", MavieErrorCode.UNSAFE_URL)
                        }
                        if (currentUrl.scheme == "https" && resolved.scheme == "http") {
                            throw SportsGuideException("HTTPS bağlantısından güvensiz HTTP yönlendirmesi engellendi.", MavieErrorCode.TLS_FAILED)
                        }
                    }
                    if (UrlSecurity.isCloudMetadataOrLinkLocal(resolved.host) ||
                        (initialWasPublic && UrlSecurity.isPrivateOrLoopback(resolved.host))
                    ) {
                        throw SportsGuideException("Güvenli olmayan yönlendirme engellendi.", MavieErrorCode.UNSAFE_URL)
                    }
                    return@readCancellable resolved to null
                }
                if (!response.isSuccessful) throw HttpStatusException(response.code)
                val body = response.body ?: throw SportsGuideException("Boş rehber yanıtı.", MavieErrorCode.INVALID_RESPONSE)
                null to body.byteStream().readBounded(maxBytes)
            }
            val bytes = nextOrBytes.second
            if (bytes != null) return bytes
            currentUrl = nextOrBytes.first ?: break
        }
        throw SportsGuideException("Çok fazla yönlendirme.", MavieErrorCode.HTTP_ERROR)
    }

    suspend fun load(
        day: LocalDate,
        force: Boolean = false,
        epgUrl: String = "",
        sourceMode: SportsSourceMode = SportsSourceMode.AUTO,
    ): SportsListings = withContext(Dispatchers.IO) {
        val url = epgUrl.trim()
        if (sourceMode == SportsSourceMode.XMLTV && url.isBlank()) {
            return@withContext SportsListings(emptyList(), stale = false, configured = false, sourceType = "xmltv")
        }
        val useXmltv = url.isNotBlank() && sourceMode != SportsSourceMode.SPOREKRANI
        val targetUrl = if (useXmltv) url else SporEkraniSource + day
        val sourceType = if (useXmltv) "xmltv" else "sporekrani"
        val freshMs = if (useXmltv) FreshMs else SporEkraniFreshMs
        val parsedUrl = targetUrl.toHttpUrlOrNull()
            ?: throw SportsGuideException("Geçersiz yayın rehberi adresi.", MavieErrorCode.UNSAFE_URL)
        if (UrlSecurity.isCloudMetadataOrLinkLocal(parsedUrl.host)) {
            throw SportsGuideException("Güvenli olmayan yayın rehberi adresi engellendi.", MavieErrorCode.UNSAFE_URL)
        }
        val key = "$targetUrl|$day"
        val now = System.currentTimeMillis()
        val cached = cache[key]
        if (!force && cached != null && now - cached.fetchedAt < freshMs) {
            return@withContext SportsListings(cached.events, stale = false, configured = true, sourceType = sourceType)
        }
        try {
            val ua = if (useXmltv) "Mavie/2.2 (XMLTV EPG)" else "Mavie/2.2 (sports schedule)"
            val maxBytes = if (useXmltv) MaxPageBytes else MaxSporEkraniBytes
            val bytes = fetchGuideBytes(parsedUrl, ua, maxBytes)
            val events = if (useXmltv) parseXmltv(bytes, day) else parseSporekrani(bytes.toString(Charsets.UTF_8), day)
            cache[key] = Cached(System.currentTimeMillis(), events)
            cache.entries.removeIf { now - it.value.fetchedAt > MaxStaleMs }
            SportsListings(events, stale = false, configured = true, sourceType = sourceType)
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (error: Exception) {
            val code = when (error) {
                is SportsGuideException -> error.code
                is IptvException -> error.code
                is HttpStatusException -> classifyHttpError(error.code, useXmltv).code
                is IOException -> classifyIoException(error).code
                else -> MavieErrorCode.OFFLINE
            }
            if (code !in setOf(MavieErrorCode.UNSAFE_URL, MavieErrorCode.TLS_FAILED) && cached != null && now - cached.fetchedAt <= MaxStaleMs) {
                SportsListings(cached.events, stale = true, configured = true, sourceType = sourceType)
            } else if (error is SportsGuideException) {
                throw error
            } else {
                val msg = if (useXmltv) {
                    "XMLTV yayın rehberine ulaşılamadı. Bağlantını kontrol edip yeniden dene."
                } else {
                    "Spor yayın rehberine ulaşılamadı. Biraz sonra tekrar dene."
                }
                throw SportsGuideException(msg, code, error)
            }
        }
    }
}
