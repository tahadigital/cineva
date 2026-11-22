package app.mavie.player.data

import java.io.BufferedReader
import java.security.MessageDigest
import java.util.Locale

internal data class M3uParseResult(val epgUrl: String, val categories: Map<MediaKind, List<Category>>, val items: List<MediaItem>)

internal data class M3uStreamSummary(val epgUrl: String, val categories: Map<MediaKind, List<Category>>, val itemCount: Int)

internal object M3uParser {
    private val attrRegex = Regex("""([A-Za-z0-9_-]+)="([^"]*)"""")
    private val extRegex = Regex("""\.([a-z0-9]{2,5})(?:[?#]|$)""", RegexOption.IGNORE_CASE)
    private val VOD_TYPES = setOf("movie", "vod")
    private val VOD_EXTENSIONS = setOf("mp4", "mkv", "avi", "mov", "webm")
    private val HEX_CHARS = "0123456789abcdef".toCharArray()

    private fun shortHash(digest: MessageDigest, value: String): String {
        digest.reset()
        val bytes = digest.digest(value.toByteArray(Charsets.UTF_8))
        val chars = CharArray(16)
        for (i in 0 until 8) {
            val b = bytes[i].toInt() and 0xFF
            chars[i * 2] = HEX_CHARS[b ushr 4]
            chars[i * 2 + 1] = HEX_CHARS[b and 0x0F]
        }
        return String(chars)
    }

    internal fun extractExtInfTitle(line: String): String {
        var inQuotes = false
        for (i in line.indices) {
            val c = line[i]
            if (c == '"') {
                inQuotes = !inQuotes
            } else if (c == ',' && !inQuotes) {
                return line.substring(i + 1).trim()
            }
        }
        return ""
    }

    private fun pickEpgUrl(raw: String): String =
        raw.split(',')
            .map { it.trim() }
            .firstOrNull { it.startsWith("http://", ignoreCase = true) || it.startsWith("https://", ignoreCase = true) }
            .orEmpty()

    fun parse(text: String): M3uParseResult {
        val allItems = mutableListOf<MediaItem>()
        val summary = parseStream(text.reader().buffered(), batchSize = 500) { batch ->
            allItems.addAll(batch)
        }
        return M3uParseResult(summary.epgUrl, summary.categories, allItems)
    }

    fun parseStream(
        reader: BufferedReader,
        batchSize: Int = 500,
        checkCancelled: () -> Unit = {},
        onBatch: (List<MediaItem>) -> Unit,
    ): M3uStreamSummary {
        var epgUrl = ""
        val categorySets = mutableMapOf<MediaKind, LinkedHashMap<String, Category>>()
        val groupCatIds = HashMap<String, String>()
        val digest = MessageDigest.getInstance("SHA-1")
        val addedAt = System.currentTimeMillis() / 1000
        val effectiveBatchSize = batchSize.coerceAtLeast(1)
        var batch = ArrayList<MediaItem>(effectiveBatchSize)
        var itemCount = 0
        var lineCount = 0

        data class Pending(val name: String, val poster: String, val group: String, val type: String)
        var pending: Pending? = null

        while (true) {
            val rawLine = reader.readLine() ?: break
            if (++lineCount % 500 == 0) checkCancelled()
            val line = rawLine.trimStart('\uFEFF').trim()
            if (line.isBlank()) continue
            if (line.startsWith("#EXTM3U", ignoreCase = true)) {
                val attrs = attrRegex.findAll(line).associate { it.groupValues[1].lowercase(Locale.ROOT) to it.groupValues[2] }
                val candidateEpg = pickEpgUrl(attrs["url-tvg"] ?: attrs["x-tvg-url"] ?: "")
                if (candidateEpg.isNotBlank()) epgUrl = candidateEpg
                continue
            }
            if (line.startsWith("#EXTINF:", ignoreCase = true)) {
                val attrs = attrRegex.findAll(line).associate { it.groupValues[1].lowercase(Locale.ROOT) to it.groupValues[2] }
                val title = extractExtInfTitle(line).take(500).ifBlank { attrs["tvg-name"].orEmpty().trim().take(500) }.ifBlank { "Adsız Yayın" }
                pending = Pending(
                    name = title,
                    poster = safeImage(attrs["tvg-logo"].orEmpty()),
                    group = attrs["group-title"].orEmpty().trim().take(200).ifBlank { "Genel" },
                    type = attrs["type"].orEmpty().lowercase(Locale.ROOT),
                )
                continue
            }
            if (line.startsWith("#")) continue
            if (line.startsWith("http://", ignoreCase = true) || line.startsWith("https://", ignoreCase = true)) {
                val meta = pending ?: Pending(line.substringAfterLast('/').take(120).ifBlank { "Akış" }, "", "Genel", "")
                pending = null
                val ext = extRegex.find(line)?.groupValues?.get(1)?.lowercase(Locale.ROOT) ?: "m3u8"
                val isVod = meta.type in VOD_TYPES || ext in VOD_EXTENSIONS
                val kind = if (isVod) MediaKind.VOD else MediaKind.LIVE
                val pid = "m3u_${shortHash(digest, "${kind.key}:$line")}"
                val catId = groupCatIds.getOrPut(meta.group) { shortHash(digest, meta.group) }
                categorySets.getOrPut(kind) { linkedMapOf() }.putIfAbsent(catId, Category(catId, meta.group, kind))
                batch.add(
                    MediaItem(
                        id = "${kind.key}:$pid",
                        providerId = pid,
                        name = meta.name,
                        kind = kind,
                        categoryId = catId,
                        categoryName = meta.group,
                        poster = meta.poster,
                        extension = ext.take(12),
                        addedAt = addedAt,
                        sourceUrl = line,
                    )
                )
                itemCount++
                if (batch.size >= effectiveBatchSize) {
                    checkCancelled()
                    onBatch(batch)
                    batch = ArrayList(effectiveBatchSize)
                }
            }
        }
        if (batch.isNotEmpty()) {
            checkCancelled()
            onBatch(batch)
        }
        return M3uStreamSummary(epgUrl, categorySets.mapValues { it.value.values.toList() }, itemCount)
    }
}
