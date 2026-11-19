package app.vrelio.player.data

import android.content.Context
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/** Native network + database layer. No desktop or local web server is involved. */
class VrelioRepository(context: Context) {
    private val discoveryFeed=DiscoveryFeed(context.applicationContext)
    val discoveryUpdates=discoveryFeed.updates
    private val database=LocalDatabase(context.applicationContext)
    private val credentials=CredentialStore(context.applicationContext)
    @Volatile private var current: SavedAccount?=credentials.load()
    private val _account=MutableStateFlow(current?.info)
    val account: StateFlow<AccountInfo?> = _account.asStateFlow()
    private val _syncState=MutableStateFlow(SyncState())
    val syncState: StateFlow<SyncState> = _syncState.asStateFlow()
    private val syncMutex=Mutex()
    private val loginMutex=Mutex()
    private val client=OkHttpClient.Builder().connectTimeout(20,TimeUnit.SECONDS).readTimeout(45,TimeUnit.SECONDS)
        .callTimeout(65,TimeUnit.SECONDS).retryOnConnectionFailure(true).build()

    fun getConnectionInfo(): AccountInfo?=account.value
    private fun saved(): SavedAccount=current?:throw IptvException("Önce IPTV hesabını bu telefona ekle.")
    private fun savedFor(item: MediaItem): SavedAccount = saved().also {
        if(item.accountId!=null&&item.accountId!=it.info.id)throw IptvException("Hesap değişti. İçeriği yeni hesabının kütüphanesinden aç.")
    }
    private fun sameAccount(account: SavedAccount) {
        if(current?.info?.id!=account.info.id)throw IptvException("Hesap değişti. İçeriği yeniden aç.")
    }

    suspend fun loginDemo(): AccountInfo = withContext(Dispatchers.IO) {
        loginMutex.withLock {
            val id = "demo_open_cinema"
            val settings = ConnectionSettings(sourceType = SourceMode.DEMO)
            val info = AccountInfo(id, "demo", "", name = "Açık Sinema (Demo)", status = "Demo", sourceType = SourceMode.DEMO)
            val account = SavedAccount(settings, info)
            credentials.save(account)
            database.replaceCatalog(id, MediaKind.VOD, DemoCatalog.categories, DemoCatalog.items)
            database.replaceCatalog(id, MediaKind.LIVE, emptyList(), emptyList())
            database.replaceCatalog(id, MediaKind.SERIES, emptyList(), emptyList())
            current = account
            _account.value = info
            info
        }
    }

    suspend fun loginM3u(name: String, m3uUrl: String, epgUrl: String = ""): AccountInfo = withContext(Dispatchers.IO) {
        loginMutex.withLock {
            val playlistUrl = normalizedHttpUrl(m3uUrl)
            val cleanEpg = epgUrl.trim().takeIf { it.isNotBlank() }?.let { normalizedHttpUrl(it).toString() }.orEmpty()
            val text = client.newCall(Request.Builder().url(playlistUrl).header("User-Agent", "Vrelio/2.1").build()).readCancellable { response ->
                if (!response.isSuccessful) throw IptvException("M3U listesi indirilemedi (${response.code}).")
                val body = response.body ?: throw IptvException("M3U adresi boş yanıt döndürdü.")
                if (body.contentLength() > 30 * 1024 * 1024L) throw IptvException("M3U listesi çok büyük.")
                body.string()
            }
            val parsed = M3uParser.parse(text)
            if (parsed.items.isEmpty()) throw IptvException("M3U listesinde geçerli yayın bulunamadı.")
            val resolvedEpg = cleanEpg.ifBlank { parsed.epgUrl }
            val id = MessageDigest.getInstance("SHA-256").digest(("m3u\n$playlistUrl").toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
            val settings = ConnectionSettings(sourceType = SourceMode.M3U, m3uUrl = playlistUrl.toString(), epgUrl = resolvedEpg)
            val info = AccountInfo(id, "m3u", playlistUrl.host, name = name.ifBlank { "M3U Listesi" }, status = "Active", sourceType = SourceMode.M3U, epgUrl = resolvedEpg)
            val account = SavedAccount(settings, info)
            credentials.save(account)
            listOf(MediaKind.LIVE, MediaKind.VOD, MediaKind.SERIES).forEach { kind ->
                database.replaceCatalog(id, kind, parsed.categories[kind].orEmpty(), parsed.items.filter { it.kind == kind })
            }
            current = account
            _account.value = info
            info
        }
    }

    suspend fun login(settings: ConnectionSettings): AccountInfo = withContext(Dispatchers.IO) {
        loginMutex.withLock {
            val normalized=normalizeConnection(settings)
            val data=api(normalized) as? JSONObject?:throw IptvException("Sağlayıcı geçerli bir hesap yanıtı göndermedi.")
            val user=data.optJSONObject("user_info")?:throw IptvException("Hesap doğrulanamadı.")
            val status=user.text("status","Active")
            if(user.optInt("auth",0)!=1)throw IptvException("Kullanıcı adı veya parola doğrulanamadı.")
            if(!status.equals("Active",true))throw IptvException("Aboneliğin etkin görünmüyor. Sağlayıcınla kontrol et.")
            val id=MessageDigest.getInstance("SHA-256").digest((normalized.host+"\n"+normalized.username).toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
            val info=AccountInfo(id,normalized.username,normalized.host,name=settings.host.removePrefix("https://").removePrefix("http://"),status=status,expiresAt=user.text("exp_date").toLongOrNull()?.takeIf { it>0 },maxConnections=user.optInt("max_connections",1).coerceAtLeast(1),sourceType=SourceMode.XTREAM,epgUrl=settings.epgUrl)
            val account=SavedAccount(normalized,info)
            try { credentials.save(account) } catch(error: IptvException) { throw error } catch(_: Exception) { throw IptvException("Hesap bu cihazda güvenli biçimde kaydedilemedi.") }
            current=account;_account.value=info
            info
        }
    }

    suspend fun importConnection(json: String): AccountInfo {
        if(json.length>1_000_000)throw IptvException("Bağlantı dosyası çok büyük.")
        val data=try { JSONObject(json) } catch(_: Exception) { throw IptvException("Geçerli bir bağlantı JSON dosyası seç.") }
        val value=data.optJSONObject("connection")?:data
        return login(ConnectionSettings(value.text("host",value.text("url")),value.text("username"),value.text("password")))
    }

    suspend fun logout() = withContext(Dispatchers.IO) {
        loginMutex.withLock { credentials.clear();current=null;_account.value=null;_syncState.value=SyncState() }
    }

    suspend fun refreshCatalog() = withContext(Dispatchers.IO) {
        syncMutex.withLock {
            val account=saved()
            _syncState.value=SyncState(true,"Kütüphanen yenileniyor…")
            try {
                when (account.settings.sourceType) {
                    SourceMode.DEMO -> {
                        database.replaceCatalog(account.info.id, MediaKind.VOD, DemoCatalog.categories, DemoCatalog.items)
                        database.replaceCatalog(account.info.id, MediaKind.LIVE, emptyList(), emptyList())
                        database.replaceCatalog(account.info.id, MediaKind.SERIES, emptyList(), emptyList())
                    }
                    SourceMode.M3U -> {
                        val playlistUrl = normalizedHttpUrl(account.settings.m3uUrl)
                        val text = client.newCall(Request.Builder().url(playlistUrl).header("User-Agent", "Vrelio/2.1").build()).readCancellable { response ->
                            if (!response.isSuccessful) throw IptvException("M3U listesi indirilemedi.")
                            val body = response.body ?: throw IptvException("Boş M3U yanıtı.")
                            body.string()
                        }
                        val parsed = M3uParser.parse(text)
                        listOf(MediaKind.LIVE, MediaKind.VOD, MediaKind.SERIES).forEach { kind ->
                            database.replaceCatalog(account.info.id, kind, parsed.categories[kind].orEmpty(), parsed.items.filter { it.kind == kind })
                        }
                    }
                    SourceMode.XTREAM -> {
                        for((index,kind) in listOf(MediaKind.LIVE,MediaKind.VOD,MediaKind.SERIES).withIndex())fetchCatalog(account,kind,index*2)
                    }
                }
                _syncState.value=SyncState(false,"Kütüphanen güncel.",6)
            } catch(error: CancellationException) { _syncState.value=SyncState();throw error }
            catch(error: Exception) {
                val message=(error as? IptvException)?.message?:"Kütüphane yenilenemedi. İnternet bağlantını kontrol et."
                _syncState.value=SyncState(false,error=message)
                throw IptvException(message)
            }
        }
    }

    private suspend fun ensureCatalog(account: SavedAccount, kind: MediaKind) {
        if(kind==MediaKind.EPISODE)return
        if(account.settings.sourceType != SourceMode.XTREAM) return
        syncMutex.withLock {
            sameAccount(account)
            val old=database.cache(account.info.id,"catalog:${kind.key}")
            if(old!=null&&System.currentTimeMillis()-old.second<24*60*60*1000L)return@withLock
            try { fetchCatalog(account,kind) }
            catch(error: CancellationException) { throw error }
            catch(error: Exception) { if(old==null)throw error }
        }
    }

    private suspend fun fetchCatalog(account: SavedAccount, kind: MediaKind, step: Int=0) {
        sameAccount(account)
        val label=when(kind) { MediaKind.LIVE->"Canlı kanallar";MediaKind.VOD->"Filmler";else->"Diziler" }
        if(_syncState.value.running)_syncState.value=SyncState(true,"$label kategorileri alınıyor…",step)
        val categoryAction=when(kind) { MediaKind.LIVE->"get_live_categories";MediaKind.VOD->"get_vod_categories";else->"get_series_categories" }
        val itemAction=when(kind) { MediaKind.LIVE->"get_live_streams";MediaKind.VOD->"get_vod_streams";else->"get_series" }
        val categories=categoriesFromJson(api(account.settings,categoryAction) as? JSONArray?:throw IptvException("$label kategorileri alınamadı."),kind)
        if(_syncState.value.running)_syncState.value=SyncState(true,"$label hazırlanıyor…",step+1)
        val data=api(account.settings,itemAction) as? JSONArray?:throw IptvException("$label listesi alınamadı.")
        val categoryMap=categories.associate { it.id to it.name }
        val items=buildList { for(index in 0 until data.length())data.optJSONObject(index)?.let { itemFromProvider(it,kind,categoryMap) }?.let(::add) }
        sameAccount(account)
        database.replaceCatalog(account.info.id,kind,categories,items)
    }

    suspend fun categories(kind: MediaKind): List<Category> = withContext(Dispatchers.IO) {
        val account=saved();ensureCatalog(account,kind)
        val cats=database.categories(account.info.id,kind)
        if (database.activeProfile().isKids) cats.filterNot { AdultContentFilter.isAdult(it.name, it.name) } else cats
    }

    suspend fun catalog(kind: MediaKind, query: String="", categoryId: String?=null, page: Int=0, pageSize: Int=60, onlyFavorites: Boolean=false): CatalogPage = withContext(Dispatchers.IO) {
        val account=saved();ensureCatalog(account,kind)
        val where=mutableListOf("i.kind=?");val args=mutableListOf(kind.key)
        if(!categoryId.isNullOrBlank()){where+="i.category_id=?";args+=categoryId}
        if(query.isNotBlank()) { where+="i.search LIKE ? ESCAPE '\\'";args+="%"+fold(query.trim()).replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%" }
        if(onlyFavorites)where+="f.item_id IS NOT NULL"
        val condition=where.joinToString(" AND ");val size=pageSize.coerceIn(1,200);val currentPage=page.coerceIn(0,1_000_000)
        val total=database.count(account.info.id,condition,args)
        val rowsRaw=database.items(account.info.id,condition,args,limit=size,offset=currentPage*size)
        val isKids=database.activeProfile().isKids
        val rows=if (isKids) rowsRaw.filterNot { AdultContentFilter.isAdult(it.name, it.categoryName) } else rowsRaw
        CatalogPage(rows,currentPage,if (isKids) rows.size else total,(currentPage+1)*size<total)
    }

    suspend fun item(id: String): MediaItem? = withContext(Dispatchers.IO) { database.item(saved().info.id,id) }
    suspend fun liveChannelNames(): List<Pair<String, String>> = withContext(Dispatchers.IO) {
        val account = saved()
        ensureCatalog(account, MediaKind.LIVE)
        database.readableDatabase.rawQuery(
            "SELECT id,name FROM items WHERE account=? AND kind=? ORDER BY name COLLATE NOCASE,id",
            arrayOf(account.info.id, MediaKind.LIVE.key),
        ).use { cursor ->
            buildList {
                while (cursor.moveToNext()) add(cursor.getString(0) to cursor.getString(1))
            }
        }
    }
    suspend fun favorites(kind: MediaKind?=null): List<MediaItem> = withContext(Dispatchers.IO) {
        database.items(saved().info.id,"f.item_id IS NOT NULL"+(if(kind!=null)" AND i.kind=?" else ""),if(kind!=null)listOf(kind.key) else emptyList(),order="f.created_at DESC",limit=20000)
    }
    suspend fun home(): HomeSections = withContext(Dispatchers.IO) {
        val operationContext = currentCoroutineContext()
        val checkCancelled = { operationContext.ensureActive() }
        checkCancelled()
        val account=saved();ensureCatalog(account,MediaKind.VOD);ensureCatalog(account,MediaKind.SERIES)
        val isKids=database.activeProfile().isKids
        val allCatalog=buildList {
            var offset=0
            do {
                checkCancelled()
                val rows=database.items(account.info.id,"i.kind IN ('vod','series')",limit=20000,offset=offset,checkCancelled=checkCancelled)
                addAll(if (isKids) rows.filterNot { AdultContentFilter.isAdult(it.name, it.categoryName) } else rows)
                offset+=rows.size
            } while(rows.size==20000)
        }
        checkCancelled()
        val discovery=buildDiscovery(allCatalog,
            database.items(account.info.id,"p.item_id IS NOT NULL OR f.item_id IS NOT NULL",limit=20000,checkCancelled=checkCancelled),
            discoveryFeed.snapshot(),checkCancelled=checkCancelled)
        checkCancelled()
        val watched=database.items(account.info.id,"(p.position>0 OR p.completed=1) AND i.kind IN ('vod','episode')",order="p.updated_at DESC,i.id",limit=500,checkCancelled=checkCancelled)
        val continuing=mutableListOf<MediaItem>()
        val seenSeries=mutableSetOf<String>()
        for(row in watched) {
            checkCancelled()
            if (isKids && AdultContentFilter.isAdult(row.name, row.categoryName)) continue
            var item=row
            if(item.kind==MediaKind.EPISODE) {
                val parent=item.parentId
                val key=parent?:item.id
                if(!seenSeries.add(key))continue
                if(item.progress?.completed==true) {
                    val episodes=if(parent!=null)database.items(account.info.id,"i.parent_id=?",listOf(parent),order="i.season,i.episode,i.name,i.id",limit=20000,checkCancelled=checkCancelled) else emptyList()
                    val index=episodes.indexOfFirst { it.id==item.id }
                    val following=if(index>=0)episodes.drop(index+1).firstOrNull { next -> next.season!=item.season || item.episode<=0 || next.episode>item.episode } else null
                    if(following==null)continue
                    item=following
                }
            } else if(item.progress?.completed==true || (item.progress?.positionSeconds?:0.0)<1.0) {
                continue
            }
            continuing.add(item)
            if(continuing.size==20)break
        }
        val favs=database.items(account.info.id,"f.item_id IS NOT NULL",order="f.created_at DESC",limit=24,checkCancelled=checkCancelled)
        val movies=database.items(account.info.id,"i.kind='vod'",limit=30,checkCancelled=checkCancelled)
        val seriesList=database.items(account.info.id,"i.kind='series'",limit=30,checkCancelled=checkCancelled)
        HomeSections(
            continuing,
            if (isKids) favs.filterNot { AdultContentFilter.isAdult(it.name, it.categoryName) } else favs,
            if (isKids) movies.filterNot { AdultContentFilter.isAdult(it.name, it.categoryName) } else movies,
            if (isKids) seriesList.filterNot { AdultContentFilter.isAdult(it.name, it.categoryName) } else seriesList,
            discovery,
        )
    }

    suspend fun detail(item: MediaItem, refresh: Boolean=false): MediaDetail = withContext(Dispatchers.IO) {
        val account=savedFor(item)
        if (account.settings.sourceType != SourceMode.XTREAM) {
            return@withContext MediaDetail(database.item(account.info.id, item.id) ?: item, genres = item.genres)
        }
        val old=database.cache(account.info.id,"detail:${item.id}")
        var info=old?.let { runCatching { JSONObject(it.first) }.getOrNull() }
        if(refresh||old==null||System.currentTimeMillis()-old.second>24*60*60*1000L) {
            try {
                when(item.kind) {
                    MediaKind.VOD -> {
                        val data=api(account.settings,"get_vod_info",mapOf("vod_id" to item.providerId)) as? JSONObject?:throw IptvException("Film bilgileri alınamadı.")
                        info=data.optJSONObject("info")?:JSONObject()
                        val updated=enrichItem(item,info!!)
                        sameAccount(account);database.putItems(account.info.id,listOf(updated));database.putCache(account.info.id,"detail:${item.id}",info.toString())
                    }
                    MediaKind.SERIES -> {
                        val data=api(account.settings,"get_series_info",mapOf("series_id" to item.providerId)) as? JSONObject?:throw IptvException("Dizi bölümleri alınamadı.")
                        info=data.optJSONObject("info")?:JSONObject()
                        val updated=enrichItem(item,info!!);val episodes=episodesFromProvider(data,updated)
                        sameAccount(account)
                        database.transaction { db ->
                            db.delete("items","account=? AND parent_id=?",arrayOf(account.info.id,item.id))
                            database.putItems(account.info.id,listOf(updated)+episodes,db)
                            database.putCache(account.info.id,"detail:${item.id}",info.toString(),db)
                        }
                    }
                    else -> Unit
                }
            } catch(error: CancellationException) { throw error }
            catch(error: Exception) { if(item.kind==MediaKind.SERIES&&old==null)throw error }
        }
        val fresh=database.item(account.info.id,item.id)?:item
        val episodes=if(item.kind==MediaKind.SERIES)database.items(account.info.id,"i.parent_id=?",listOf(item.id),order="i.season,i.episode,i.name",limit=20000) else emptyList()
        val seasons=episodes.groupBy { it.season }.toSortedMap().map { (number,entries)->Season(number,if(number==0)"Özel bölümler" else "$number. Sezon",entries) }
        MediaDetail(fresh,seasons,info?.text("genre").orEmpty(),info?.text("cast").orEmpty(),info?.text("director").orEmpty())
    }

    suspend fun nextEpisode(episode: MediaItem): MediaItem? {
        if (episode.kind != MediaKind.EPISODE) return null
        val parent = episode.parentId?.let { item(it) } ?: return null
        return detail(parent).followingEpisode(episode)
    }

    suspend fun siblingEpisodes(episode: MediaItem): List<MediaItem> = withContext(Dispatchers.IO) {
        if (episode.kind != MediaKind.EPISODE || episode.parentId == null) return@withContext emptyList()
        val acc = saved()
        database.items(acc.info.id, "i.parent_id=?", listOf(episode.parentId), order = "i.season,i.episode,i.name,i.id", limit = 2000)
    }

    suspend fun surpriseItem(): MediaItem = withContext(Dispatchers.IO) {
        val acc = saved(); ensureCatalog(acc, MediaKind.VOD); ensureCatalog(acc, MediaKind.SERIES)
        val isKids = database.activeProfile().isKids
        val candidates = database.items(acc.info.id, "i.kind IN ('vod','series')", order = "i.added DESC", limit = 80)
            .let { list -> if (isKids) list.filterNot { AdultContentFilter.isAdult(it.name, it.categoryName) } else list }
        if (candidates.isEmpty()) throw IptvException("Önerilecek içerik bulunamadı.")
        val pool = candidates.sortedByDescending { it.rating }.take(15)
        pool[java.security.SecureRandom().nextInt(pool.size)]
    }

    suspend fun profiles(): List<UserProfile> = withContext(Dispatchers.IO) { database.profiles() }
    suspend fun activeProfile(): UserProfile = withContext(Dispatchers.IO) { database.activeProfile() }
    suspend fun createProfile(name: String, color: String, isKids: Boolean, pin: String): UserProfile = withContext(Dispatchers.IO) {
        database.createProfile(name, color, isKids, pin)
    }
    suspend fun switchProfile(id: String, pin: String = ""): UserProfile = withContext(Dispatchers.IO) {
        database.switchProfile(current?.info?.id, id, pin)
    }
    suspend fun deleteProfile(id: String) = withContext(Dispatchers.IO) {
        database.deleteProfile(current?.info?.id, id)
    }

    fun streamUrl(item: MediaItem, liveHls: Boolean=false): String {
        if(item.kind==MediaKind.SERIES)throw IptvException("Oynatmak için bir dizi bölümü seç.")
        if(item.sourceUrl.isNotBlank()) return item.sourceUrl
        val account=savedFor(item);val settings=account.settings
        if(settings.sourceType != SourceMode.XTREAM) throw IptvException("Bu içerik için doğrudan yayın adresi bulunamadı.")
        val path=when(item.kind){MediaKind.LIVE->"live";MediaKind.VOD->"movie";else->"series"}
        val extension=if(item.kind==MediaKind.LIVE) { if(liveHls)"m3u8" else "ts" } else item.extension.ifBlank { "mp4" }
        return normalizedHost(settings.host).newBuilder().addPathSegment(path).addPathSegment(settings.username)
            .addPathSegment(settings.password).addPathSegment("${item.providerId}.$extension").build().toString()
    }

    suspend fun toggleFavorite(item: MediaItem): Boolean = withContext(Dispatchers.IO) { database.favorite(savedFor(item).info.id,item) }
    suspend fun progress(itemId: String): WatchProgress? = withContext(Dispatchers.IO) {
        val account=saved().info.id
        database.readableDatabase.rawQuery("SELECT position,duration,completed,updated_at FROM progress WHERE account=? AND item_id=?",arrayOf(account,itemId)).use { c -> if(c.moveToFirst())WatchProgress(itemId,c.getDouble(0),c.getDouble(1),c.getInt(2)!=0,timestamp(c.getString(3))) else null }
    }
    suspend fun saveProgress(item: MediaItem, positionSeconds: Double, durationSeconds: Double) = withContext(Dispatchers.IO) {
        if(item.kind!=MediaKind.LIVE&&positionSeconds.isFinite()&&positionSeconds>=0&&durationSeconds.isFinite())database.saveProgress(savedFor(item).info.id,item,positionSeconds,durationSeconds)
    }
    suspend fun clearProgress(itemId: String) = withContext(Dispatchers.IO) { database.writableDatabase.delete("progress","account=? AND item_id=?",arrayOf(saved().info.id,itemId));Unit }
    suspend fun trackPreference(itemId: String): TrackPreference = withContext(Dispatchers.IO) { database.trackPreference(saved().info.id,itemId) }
    suspend fun saveTrackPreference(itemId: String, preference: TrackPreference) = withContext(Dispatchers.IO) { database.saveTrackPreference(saved().info.id,itemId,preference) }
    suspend fun playlists(includeItems: Boolean=true): List<Playlist> = withContext(Dispatchers.IO) { val account=saved().info.id;database.playlists(account).map { if(includeItems)it.copy(items=database.playlistItems(account,it.id)) else it } }
    suspend fun createPlaylist(name: String): Playlist = withContext(Dispatchers.IO) { database.createPlaylist(saved().info.id,name) }
    suspend fun addToPlaylist(playlistId: String, item: MediaItem) = withContext(Dispatchers.IO) { database.addToPlaylist(savedFor(item).info.id,playlistId,item) }
    suspend fun removeFromPlaylist(playlistId: String, itemId: String) = withContext(Dispatchers.IO) { database.removeFromPlaylist(saved().info.id,playlistId,itemId) }
    suspend fun deletePlaylist(playlistId: String) = withContext(Dispatchers.IO) { database.deletePlaylist(saved().info.id,playlistId) }
    suspend fun exportState(): String = withContext(Dispatchers.IO) { StateBackup.export(database,saved().info.id) }
    suspend fun importState(json: String) = withContext(Dispatchers.IO) { StateBackup.import(database,saved().info.id,json) }

    private suspend fun api(settings: ConnectionSettings, action: String?=null, parameters: Map<String,String> = emptyMap()): Any {
        val url=normalizedHost(settings.host).newBuilder().addPathSegment("player_api.php")
            .addQueryParameter("username",settings.username).addQueryParameter("password",settings.password).apply {
                if(action!=null)addQueryParameter("action",action)
                parameters.forEach { (key,value)->addQueryParameter(key,value) }
            }.build()
        try {
            return client.newCall(Request.Builder().url(url).header("User-Agent","VLC/3.0.21 LibVLC/3.0.21").header("Accept","application/json").build()).readCancellable { response ->
                if(!response.isSuccessful)throw IptvException(if(response.code==401||response.code==403)"IPTV hesabına erişim reddedildi." else "IPTV sağlayıcısı şu anda yanıt veremiyor. Daha sonra yeniden dene.")
                val body=response.body?:throw IptvException("IPTV sağlayıcısı boş bir yanıt gönderdi.")
                if(body.contentLength()>100*1024*1024L)throw IptvException("Sağlayıcının listesi bu cihaz için çok büyük.")
                readProviderJson(body.byteStream())
            }
        } catch(error: CancellationException) { throw error }
        catch(error: IptvException) { throw error }
        catch(_: IOException) { throw IptvException("IPTV sunucusuna ulaşılamadı. İnternet bağlantını ve sunucu adresini kontrol et.") }
        catch(_: Exception) { throw IptvException("IPTV sunucusu geçerli bir yanıt göndermedi.") }
    }

    companion object {
        fun normalizeConnection(settings: ConnectionSettings): ConnectionSettings {
            val url=normalizedHost(settings.host)
            if(settings.username.isBlank()||settings.password.isBlank())throw IptvException("Kullanıcı adı ve parola gerekli.")
            if(settings.username.length>500||settings.password.length>1000)throw IptvException("Bağlantı bilgileri çok uzun.")
            return settings.copy(host = url.toString().trimEnd('/'), username = settings.username.trim())
        }
        internal fun normalizedHttpUrl(value: String): HttpUrl {
            val input=value.trim().let { if(it.contains("://"))it else "http://$it" }
            return input.toHttpUrlOrNull()?:throw IptvException("Geçersiz bağlantı adresi.")
        }
        private fun normalizedHost(value: String): HttpUrl {
            val input=value.trim().let { if(it.contains("://"))it else "http://$it" }
            val url=input.toHttpUrlOrNull()?:throw IptvException("Sunucu adresi geçersiz.")
            if(url.username.isNotEmpty()||url.password.isNotEmpty()||url.query!=null||url.fragment!=null)throw IptvException("Sunucu alanına yalnızca sunucu adresini gir.")
            return url.newBuilder().encodedPath(url.encodedPath.trimEnd('/')+"/").build()
        }
    }
}
