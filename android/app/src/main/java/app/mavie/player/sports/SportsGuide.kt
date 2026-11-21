package app.mavie.player.sports

import app.mavie.player.readBounded
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.w3c.dom.Element
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
import javax.xml.parsers.DocumentBuilderFactory

internal val Istanbul: ZoneId = ZoneId.of("Europe/Istanbul")
private const val MaxPageBytes = 8 * 1024 * 1024
private const val FreshMs = 15 * 60_000L
private const val MaxStaleMs = 12 * 60 * 60_000L

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
)

internal object SportsChannels {
    private val region = Regex("^\\s*(?:(?:vip\\s+)?(?:tr|en|us|uk|de|fr|es)|turkey|intl)\\s*[:|➤\\-]\\s*")
    private val quality = Regex("(?:[\\s|\\[\\]()\\-]+(?:fhd|hd|uhd|sd|raw|hevc|h265|4k|1080p|720p)\\b[\\s|\\[\\]()\\-]*)+$")
    private val punctuation = Regex("[^a-z0-9+]")
    private val marks = Regex("\\p{M}+")

    fun fold(text: String): String = Normalizer.normalize(
        text.replace('ı', 'i').replace('İ', 'i'), Normalizer.Form.NFKD
    ).replace(marks, "").lowercase(Locale.ROOT)

    fun key(name: String): String = fold(name).replace(region, "").replace(quality, "").replace(punctuation, "")
}

internal object SportsGuide {
    private data class Cached(val fetchedAt: Long, val events: List<SportBroadcast>)
    private val cache = ConcurrentHashMap<String, Cached>()
    private val client = OkHttpClient.Builder().followRedirects(true)
        .callTimeout(18, TimeUnit.SECONDS).build()
    private val spaces = Regex("\\s+")
    private val xmltvTs = Regex("^(\\d{4})(\\d{2})(\\d{2})(\\d{2})(\\d{2})(\\d{2})(?:\\s*([+-]\\d{4}))?")
    private val sportKeyword = Regex("\\b(sport|sports|spor|futbol|football|soccer|basketbol|basketball|tennis|tenis|motorsport|formula|racing|boxing|ufc|golf)\\b", RegexOption.IGNORE_CASE)
    private val timeFormat = DateTimeFormatter.ofPattern("HH:mm")

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

    private fun String.clean(max: Int): String = trim().replace(spaces, " ").take(max)

    internal fun parseXmltv(xmlText: String, day: LocalDate, zone: ZoneId = Istanbul): List<SportBroadcast> {
        val prefix = xmlText.take(4096).uppercase(Locale.ROOT)
        if ("<!ENTITY" in prefix || "<!DOCTYPE" in prefix) {
            throw IOException("Güvenlik nedeniyle XMLTV DTD bildirimlerine izin verilmiyor.")
        }
        val factory = DocumentBuilderFactory.newInstance().apply {
            isNamespaceAware = false
            isExpandEntityReferences = false
            runCatching { setFeature("http://apache.org/xml/features/disallow-doctype-decl", true) }
        }
        val doc = try {
            factory.newDocumentBuilder().parse(InputSource(StringReader(xmlText)))
        } catch (err: Exception) {
            throw IOException("XMLTV yayın rehberi okunamadı.", err)
        }
        val root = doc.documentElement
        if (!root.tagName.equals("tv", ignoreCase = true)) {
            throw IOException("Geçerli bir XMLTV dosyası değil.")
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

    suspend fun load(day: LocalDate, force: Boolean = false, epgUrl: String = ""): SportsListings = withContext(Dispatchers.IO) {
        val url = epgUrl.trim()
        if (url.isBlank()) return@withContext SportsListings(emptyList(), stale = false, configured = false)
        val key = "$url|$day"
        val now = System.currentTimeMillis()
        val cached = cache[key]
        if (!force && cached != null && now - cached.fetchedAt < FreshMs) {
            return@withContext SportsListings(cached.events, stale = false, configured = true)
        }
        try {
            val request = Request.Builder().url(url).header("User-Agent", "Mavie/2.1 (XMLTV EPG)").build()
            val bytes = client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) throw IOException("EPG HTTP ${response.code}")
                val body = response.body ?: throw IOException("Empty EPG response")
                body.byteStream().readBounded(MaxPageBytes)
            }
            val events = parseXmltv(bytes, day)
            cache[key] = Cached(System.currentTimeMillis(), events)
            cache.entries.removeIf { now - it.value.fetchedAt > MaxStaleMs }
            SportsListings(events, stale = false, configured = true)
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (_: Exception) {
            if (cached != null && now - cached.fetchedAt <= MaxStaleMs) {
                SportsListings(cached.events, stale = true, configured = true)
            } else {
                throw IOException("XMLTV yayın rehberine ulaşılamadı. Bağlantını kontrol edip yeniden dene.")
            }
        }
    }
}
