package app.cineva.player.data

import org.json.JSONArray
import org.json.JSONObject
import java.text.Normalizer
import java.util.Locale

private val diacritics=Regex("\\p{M}+")
private val providerIdPattern=Regex("[A-Za-z0-9_-]+")
private val extensionPattern=Regex("[a-z0-9]{1,10}")
private val yearInTitlePattern=Regex("\\b((?:19|20)\\d{2})\\b")
private val fourDigitYearPattern=Regex("\\d{4}")
internal fun fold(value: String): String = Normalizer.normalize(value.replace('ı','i').replace('İ','i').lowercase(Locale.ROOT),Normalizer.Form.NFD).replace(diacritics,"")
internal fun JSONObject.text(key: String, fallback: String = ""): String = if(isNull(key))fallback else optString(key,fallback).takeUnless { it == "null" }?:fallback
internal fun safeImage(value: String): String = value.takeIf { it.startsWith("https://",true)||it.startsWith("http://",true) }?.take(4000)?:""
internal fun seconds(value: Any?): Double {
    if(value==null||value===JSONObject.NULL)return 0.0
    val number=if(value is String&&value.contains(':'))value.split(':').fold(0.0) { total,part -> total*60+(part.toDoubleOrNull()?:0.0) } else value.toString().toDoubleOrNull()?:0.0
    return number.finiteOrZero().coerceAtLeast(0.0)
}
internal fun categoriesFromJson(data: JSONArray, kind: MediaKind): List<Category> = buildList {
    for(index in 0 until data.length()) {
        val row=data.optJSONObject(index)?:continue
        val id=row.text("category_id");if(id.isBlank())continue
        add(Category(id,row.text("category_name","Diğer").take(500),kind))
    }
}
internal fun itemFromProvider(row: JSONObject, kind: MediaKind, categories: Map<String,String> = emptyMap(), parent: MediaItem? = null, seasonNumber: Int = 0): MediaItem? {
    val providerId=when(kind) { MediaKind.SERIES->row.text("series_id");MediaKind.EPISODE->row.text("id");else->row.text("stream_id") }
    if(providerId.isBlank()||providerId.length>100||!providerId.matches(providerIdPattern))return null
    val info=row.optJSONObject("info")?:JSONObject()
    val video=info.optJSONObject("video")?:JSONObject()
    val audio=info.optJSONObject("audio")?:JSONObject()
    val categoryId=row.text("category_id",parent?.categoryId?:"")
    val poster=sequenceOf(row.text("stream_icon"),row.text("cover"),row.text("movie_image"),info.text("movie_image"),parent?.poster?:"").firstOrNull { it.isNotBlank() }?:""
    val backdrops=row.optJSONArray("backdrop_path")?:info.optJSONArray("backdrop_path")
    val backdrop=backdrops?.optString(0)?:row.text("backdrop_path").takeUnless { it.startsWith('[') }?:""
    val name=row.text("name",row.text("title","İsimsiz içerik")).take(1000)
    val rawYear=sequenceOf(row.text("year"),row.text("releaseDate"),row.text("releasedate"),info.text("releasedate")).firstOrNull { it.isNotBlank() }?.take(4)?:""
    val year=rawYear.takeIf { it.matches(fourDigitYearPattern) }?:yearInTitlePattern.find(name)?.groupValues?.get(1)?:""
    val extension=row.text("container_extension",if(kind==MediaKind.LIVE)"ts" else "mp4").lowercase(Locale.ROOT).takeIf { it.matches(extensionPattern) }?:"mp4"
    return MediaItem(
        id="${kind.key}:$providerId",providerId=providerId,name=name,kind=kind,
        genres=info.text("genre",row.text("genre")),categoryId=categoryId,categoryName=categories[categoryId]?:parent?.categoryName?:"",poster=safeImage(poster),backdrop=safeImage(backdrop),year=year,
        rating=(row.optDouble("rating",row.optDouble("rating_5based",0.0)*2)).finiteOrZero().coerceIn(0.0,10.0),extension=extension,
        durationSeconds=seconds(info.opt("duration_secs")).takeIf { it>0 }?:seconds(info.opt("duration")),plot=info.text("plot",row.text("plot")).take(24000),
        season=row.optInt("season",seasonNumber),episode=row.optInt("episode_num",row.optInt("episode")),parentId=parent?.id,
        addedAt=row.text("added",row.text("last_modified")).toLongOrNull()?:0,videoCodec=video.text("codec_name"),audioCodec=audio.text("codec_name"),
    )
}
internal fun enrichItem(item: MediaItem, info: JSONObject): MediaItem {
    val rawBackdrop=info.optJSONArray("backdrop_path")?.optString(0)?:info.text("backdrop_path").takeUnless { it.startsWith('[') }?:""
    val backdrop=safeImage(rawBackdrop)
    val duration=seconds(info.opt("duration_secs")).takeIf { it>0 }?:seconds(info.opt("duration"))
    return item.copy(
        genres=info.text("genre",item.genres),plot=info.text("plot",item.plot).take(24000),poster=safeImage(info.text("movie_image",info.text("cover",item.poster))),
        backdrop=backdrop.ifBlank { item.backdrop },durationSeconds=duration.takeIf { it>0 }?:item.durationSeconds,
        rating=info.optDouble("rating",item.rating).finiteOrZero().coerceIn(0.0,10.0),
        year=info.text("releasedate",info.text("releaseDate",item.year)).take(4),
        videoCodec=info.optJSONObject("video")?.text("codec_name")?.ifBlank { item.videoCodec }?:item.videoCodec,
        audioCodec=info.optJSONObject("audio")?.text("codec_name")?.ifBlank { item.audioCodec }?:item.audioCodec,
    )
}
internal fun episodesFromProvider(data: JSONObject, parent: MediaItem): List<MediaItem> {
    val output=mutableListOf<MediaItem>()
    when(val groups=data.opt("episodes")) {
        is JSONObject -> for(key in groups.keys()) {
            val episodes=groups.optJSONArray(key)?:continue
            for(index in 0 until episodes.length())episodes.optJSONObject(index)?.let { itemFromProvider(it,MediaKind.EPISODE,parent=parent,seasonNumber=key.toIntOrNull()?:1) }?.let(output::add)
        }
        is JSONArray -> for(index in 0 until groups.length()) {
            when(val value=groups.opt(index)) {
                is JSONArray -> for(j in 0 until value.length())value.optJSONObject(j)?.let { itemFromProvider(it,MediaKind.EPISODE,parent=parent,seasonNumber=index+1) }?.let(output::add)
                is JSONObject -> itemFromProvider(value,MediaKind.EPISODE,parent=parent,seasonNumber=1)?.let(output::add)
            }
        }
    }
    return output.distinctBy { it.id }.sortedWith(compareBy<MediaItem> { it.season }.thenBy { it.episode }.thenBy { it.name })
}
