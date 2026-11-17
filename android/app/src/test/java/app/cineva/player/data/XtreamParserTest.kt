package app.cineva.player.data

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class XtreamParserTest {
    @Test fun turkishSearchNormalizesBothDottedAndDotlessI() {
        assertEquals("akis istanbul cagri",fold("AKIŞ İSTANBUL ÇAĞRI"))
    }
    @Test fun durationsAcceptProviderSecondsAndClockWithoutNonFiniteValues() {
        assertEquals(5403.0,seconds("01:30:03"),.01)
        assertEquals(90.0,seconds("90"),.01)
        assertEquals(0.0,seconds("NaN"),.01)
        assertEquals(0.0,seconds("-4"),.01)
    }
    @Test fun movieMetadataAndImagesAreMappedWithoutLeakingDirectSources() {
        val item=itemFromProvider(JSONObject("""{"stream_id":42,"name":"Film","stream_icon":"https://images.example.test/a.jpg","category_id":"3","container_extension":"MKV","rating":"8.4","added":"1700000000","direct_source":"http://secret.invalid/user/password","info":{"duration_secs":"180","video":{"codec_name":"hevc"},"audio":{"codec_name":"ac3"}}}"""),MediaKind.VOD,mapOf("3" to "Filmler"))!!
        assertEquals("vod:42",item.id);assertEquals("mkv",item.extension);assertEquals("Filmler",item.categoryName)
        assertEquals(180.0,item.durationSeconds,.01);assertEquals("hevc",item.videoCodec);assertEquals("ac3",item.audioCodec)
        assertFalse(item.toStoredJson().toString().contains("secret.invalid"))
    }
    @Test fun unsafePosterSchemesAndProviderIdsAreDiscarded() {
        val item=itemFromProvider(JSONObject("""{"stream_id":"7","name":"A","stream_icon":"javascript:alert(1)"}"""),MediaKind.LIVE)!!
        assertEquals("",item.poster)
        assertNull(itemFromProvider(JSONObject("""{"stream_id":"../../password","name":"A"}"""),MediaKind.VOD))
    }
    @Test fun providerSeasonDictionaryPreservesEpisodeIdsAndSourceExtensions() {
        val parent=MediaItem("series:5","5","Dizi",MediaKind.SERIES,poster="https://images.example.test/series.jpg")
        val json=JSONObject("""{"episodes":{"2":[{"id":"22","title":"İkinci bölüm","episode_num":2,"container_extension":"mkv"}],"1":[{"id":"11","title":"İlk bölüm","episode_num":1}]}}""")
        val items=episodesFromProvider(json,parent)
        assertEquals(listOf("episode:11","episode:22"),items.map { it.id })
        assertEquals(listOf(1,2),items.map { it.season });assertEquals("series:5",items[0].parentId)
        assertEquals(parent.poster,items[0].poster);assertEquals("mkv",items[1].extension)
    }
    @Test fun providerSeasonArraysAndSpecialEpisodesAreSupported() {
        val parent=MediaItem("series:5","5","Dizi",MediaKind.SERIES)
        val data=JSONObject("""{"episodes":[[{"id":"1","title":"Özel","season":0,"episode_num":1}],[{"id":"2","title":"Bölüm","season":2,"episode_num":1}]]}""")
        assertEquals(listOf(0,2),episodesFromProvider(data,parent).map { it.season })
    }
    @Test fun accountSecretsAreRedactedAndHostPathIsPreserved() {
        val connection=AkisRepository.normalizeConnection(ConnectionSettings("https://example.test/iptv/","someone","p@ss"))
        assertEquals("https://example.test/iptv",connection.host)
        assertFalse(connection.toString().contains("someone"));assertFalse(connection.toString().contains("p@ss"))
    }
    @Test fun hostRejectsEmbeddedCredentialsQueriesAndUnsupportedProtocols() {
        for(host in listOf("http://user:pass@example.test","http://example.test/?password=secret","ftp://example.test","http://example.test/#token")) {
            try { AkisRepository.normalizeConnection(ConnectionSettings(host,"demo","demo"));fail("Host should be rejected") }
            catch(_: IptvException) { }
        }
    }
    @Test fun categoriesAndStoredItemsRoundTripUnicode() {
        val categories=categoriesFromJson(JSONArray("""[{"category_id":"8","category_name":"Türkçe Filmler"}]"""),MediaKind.VOD)
        assertEquals("Türkçe Filmler",categories.single().name)
        val original=MediaItem("episode:8","8","Çağrı",MediaKind.EPISODE,parentId="series:3",season=2,episode=4,plot="Öykü")
        assertEquals(original,storedItem(original.toStoredJson()))
    }
}
