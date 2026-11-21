package app.mavie.player.data

import java.security.MessageDigest
import java.util.Locale

internal data class M3uParseResult(val epgUrl: String, val categories: Map<MediaKind, List<Category>>, val items: List<MediaItem>)

internal object M3uParser {
    private val attrRegex = Regex("""([A-Za-z0-9_-]+)="([^"]*)"""")
    private val extRegex = Regex("""\.([a-z0-9]{2,5})(?:[?#]|$)""", RegexOption.IGNORE_CASE)

    private fun shortHash(value: String): String = MessageDigest.getInstance("SHA-1")
        .digest(value.toByteArray(Charsets.UTF_8)).take(8).joinToString("") { "%02x".format(it) }

    fun parse(text: String): M3uParseResult {
        var epgUrl = ""
        val items = mutableListOf<MediaItem>()
        val categorySets = mutableMapOf<MediaKind, LinkedHashMap<String, Category>>()

        data class Pending(val name: String, val poster: String, val group: String, val type: String)
        var pending: Pending? = null

        for (rawLine in text.lineSequence()) {
            val line = rawLine.trim()
            if (line.isBlank()) continue
            if (line.startsWith("#EXTM3U", ignoreCase = true)) {
                val attrs = attrRegex.findAll(line).associate { it.groupValues[1].lowercase(Locale.ROOT) to it.groupValues[2] }
                epgUrl = attrs["url-tvg"] ?: attrs["x-tvg-url"] ?: ""
                continue
            }
            if (line.startsWith("#EXTINF:", ignoreCase = true)) {
                val attrs = attrRegex.findAll(line).associate { it.groupValues[1].lowercase(Locale.ROOT) to it.groupValues[2] }
                val title = line.substringAfter(',', "").trim().take(500).ifBlank { attrs["tvg-name"].orEmpty() }.ifBlank { "Adsız Yayın" }
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
                val isVod = meta.type in setOf("movie", "vod") || ext in setOf("mp4", "mkv", "avi", "mov", "webm")
                val kind = if (isVod) MediaKind.VOD else MediaKind.LIVE
                val pid = "m3u_${shortHash("${kind.key}:$line")}"
                val catId = shortHash(meta.group)
                categorySets.getOrPut(kind) { linkedMapOf() }.putIfAbsent(catId, Category(catId, meta.group, kind))
                items.add(
                    MediaItem(
                        id = "${kind.key}:$pid",
                        providerId = pid,
                        name = meta.name,
                        kind = kind,
                        categoryId = catId,
                        categoryName = meta.group,
                        poster = meta.poster,
                        extension = ext.take(12),
                        addedAt = System.currentTimeMillis() / 1000,
                        sourceUrl = line,
                    )
                )
            }
        }
        return M3uParseResult(epgUrl, categorySets.mapValues { it.value.values.toList() }, items)
    }
}
