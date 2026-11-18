package app.cineva.player

import android.app.Application
import android.net.Uri
import android.provider.OpenableColumns
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import app.cineva.player.data.*
import app.cineva.player.sports.SportsChannels
import app.cineva.player.ui.*
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

private val FullHdChannel = Regex("\\b(?:fhd|1080p)\\b")
private val HdChannel = Regex("\\b(?:hd|720p)\\b")
private val TurkishChannel = Regex("^\\s*(?:(?:vip\\s+)?tr|turkey)\\s*[:|➤\\-]")

data class PlayingItem(
    val item: MediaItem,
    val url: String,
    val positionMs: Long,
    val preference: TrackPreference,
    val accountId: String,
    val generation: Long,
    val nextEpisode: MediaItem? = null,
    val episodes: List<Pair<String, String>> = emptyList(),
    val isLocalUri: Boolean = false,
)

class MainViewModel(application: Application) : AndroidViewModel(application) {
    val repository = AkisRepository(application)
    val cloudClient = CloudClient(application)
    val account = repository.account
    var cloudState by mutableStateOf(cloudClient.current()); private set
    var library by mutableStateOf(LibraryUiState(loading = true)); private set
    var detail by mutableStateOf<DetailUiState?>(null); private set
    var settings by mutableStateOf(false)
    var player by mutableStateOf<PlayingItem?>(null); private set
    var setupLoading by mutableStateOf(false); private set
    var setupError by mutableStateOf<String?>(null); private set
    var notice by mutableStateOf<String?>(null)
    var collections by mutableStateOf<List<UiCollection>>(emptyList()); private set
    var collectionTarget by mutableStateOf<UiMedia?>(null)
    var showCollectionPicker by mutableStateOf(false)
    var profiles by mutableStateOf<List<UserProfile>>(emptyList()); private set
    var activeProfile by mutableStateOf(UserProfile("default", "Ana Profil", "#FF4B45", active = true)); private set
    var showProfilePicker by mutableStateOf(false)
    var profileError by mutableStateOf<String?>(null)
    private var page = 0
    private var currentCollection: String? = null
    private var loadJob: Job? = null
    private var detailJob: Job? = null
    private var playJob: Job? = null
    private var playGeneration = 0L
    private val progressWrites = Mutex()
    private val knownItems = mutableMapOf<String, MediaItem>()

    init {
        refreshProfiles()
        refreshCloudStatus()
        viewModelScope.launch { repository.discoveryUpdates.collect { if(it>0 && account.value!=null && library.tab==LibraryTab.HOME)loadLibrary() } }
        viewModelScope.launch {
            var previous: String? = null
            account.collect { current ->
                if(current?.id != previous) {
                    loadJob?.cancel();detailJob?.cancel();playJob?.cancel();playGeneration++
                    knownItems.clear();detail=null;settings=false;player=null;library=LibraryUiState(loading=current!=null)
                    previous=current?.id
                }
                if(current!=null)loadLibrary() else library=LibraryUiState()
            }
        }
    }
    private fun message(error: Exception) = if(error is IptvException) error.message ?: "İşlem tamamlanamadı." else "İşlem tamamlanamadı. Yeniden deneyebilirsin."
    private fun remember(items: List<MediaItem>): List<UiMedia> { items.forEach { knownItems[it.id]=it };return items.map(::present) }
    private fun present(item: MediaItem) = UiMedia(item.id,item.name,item.kind.key,item.poster,item.backdrop,item.year,item.categoryName,item.rating,item.plot,
        ((item.progress?.positionSeconds?:0.0)*1000).toLong(),((item.progress?.durationSeconds?:item.durationSeconds)*1000).toLong(),item.isFavorite,item.episode)
    private suspend fun resolve(item: UiMedia): MediaItem = repository.item(item.id) ?: knownItems[item.id] ?: throw IptvException("İçerik bulunamadı. Kütüphaneyi yenile.")
    fun loginDemo() {
        if (setupLoading) return
        setupLoading = true; setupError = null
        viewModelScope.launch {
            try { repository.loginDemo() }
            catch (error: Exception) { if (error is CancellationException) throw error; setupError = message(error) }
            finally { setupLoading = false }
        }
    }
    fun loginM3u(name: String, m3uUrl: String, epgUrl: String = "") {
        if (setupLoading) return
        setupLoading = true; setupError = null
        viewModelScope.launch {
            try { repository.loginM3u(name, m3uUrl, epgUrl) }
            catch (error: Exception) { if (error is CancellationException) throw error; setupError = message(error) }
            finally { setupLoading = false }
        }
    }
    fun login(host: String, username: String, password: String, epgUrl: String = "") {
        if(setupLoading)return
        setupLoading=true;setupError=null
        viewModelScope.launch { try { repository.login(ConnectionSettings(host,username,password,SourceMode.XTREAM,epgUrl=epgUrl)) }
            catch(error: Exception) { if(error is CancellationException)throw error;setupError=message(error) }
            finally { setupLoading=false } }
    }
    fun changeTab(tab: LibraryTab) { currentCollection=null;library=library.copy(tab=tab,query="",selectedCategoryId="",title="",items=emptyList(),hasMore=false);loadLibrary() }
    fun search(value: String) { library=library.copy(query=value);loadLibrary(debounce=true) }
    fun category(id: String) { library=library.copy(selectedCategoryId=id);loadLibrary() }
    fun loadMore() { if(!library.loading && library.hasMore)loadLibrary(append=true) }
    fun loadLibrary(append: Boolean=false, debounce: Boolean=false) {
        loadJob?.cancel()
        val snapshot=library
        val collection=currentCollection
        loadJob=viewModelScope.launch {
            if(debounce)delay(300)
            progressWrites.withLock {}
            library=library.copy(loading=true,error=null)
            try {
                val lists=repository.playlists(includeItems=false)
                collections=lists.map { UiCollection(it.id,it.name,it.count) }
                val kinds=when(snapshot.tab) { LibraryTab.LIVE->listOf(MediaKind.LIVE);LibraryTab.FILMS->listOf(MediaKind.VOD);LibraryTab.SERIES->listOf(MediaKind.SERIES);else->listOf(MediaKind.VOD,MediaKind.SERIES,MediaKind.LIVE) }
                val cats=if(kinds.size==1)repository.categories(kinds.first()).map { UiCategory(it.id,it.name) } else emptyList()
                if (snapshot.tab == LibraryTab.SPORTS || snapshot.tab == LibraryTab.SEARCH && snapshot.query.isBlank()) {
                    library = library.copy(items = emptyList(), categories = emptyList(), loading = false, hasMore = false, totalCount = 0)
                } else if(snapshot.tab==LibraryTab.HOME && snapshot.query.isBlank()) {
                    val home=repository.home()
                    val films=remember(home.recentMovies)
                    library=library.copy(items=films,continueWatching=remember(home.continueWatching),seriesItems=remember(home.recentSeries),favorites=remember(home.favorites),
                        showcase=remember(home.discovery.showcase),recommendations=home.discovery.shelves.map { UiRecommendationShelf(it.id,it.title,it.subtitle,remember(it.items)) },
                        featured=films.firstOrNull { it.backdrop.isNotBlank() || it.poster.isNotBlank() } ?: films.firstOrNull(),collections=collections,loading=false,hasMore=false,totalCount=films.size,categories=emptyList())
                } else if(snapshot.tab==LibraryTab.PLAYLISTS && snapshot.query.isBlank()) {
                    val list=collection?.let { id -> repository.playlists().firstOrNull { it.id==id } }
                    library=library.copy(items=remember(list?.items.orEmpty()),title=list?.name.orEmpty(),collections=collections,categories=emptyList(),totalCount=list?.count?:lists.size,loading=false,hasMore=false)
                } else if(snapshot.tab==LibraryTab.FAVORITES && snapshot.query.isBlank()) {
                    val rows=repository.favorites()
                    library=library.copy(items=remember(rows),collections=collections,loading=false,categories=emptyList(),hasMore=false,totalCount=rows.size)
                } else {
                    val requested=if(append)page+1 else 0
                    val pages=kinds.map { repository.catalog(it,snapshot.query,snapshot.selectedCategoryId.ifBlank { null },requested,60,snapshot.tab==LibraryTab.FAVORITES) }
                    page=requested
                    val rows=remember(pages.flatMap { it.items })
                    library=library.copy(items=if(append)(library.items+rows).distinctBy { it.id } else rows,categories=cats,collections=collections,loading=false,hasMore=pages.any { it.hasMore },totalCount=pages.sumOf { it.total })
                }
            } catch(error: Exception) { if(error is CancellationException)throw error;library=library.copy(loading=false,error=message(error)) }
        }
    }
    fun refresh() {
        if(library.refreshing)return
        viewModelScope.launch {
            library=library.copy(refreshing=true,error=null)
            try { repository.refreshCatalog();loadLibrary();notice="Kütüphanen güncellendi." }
            catch(error: Exception) { if(error is CancellationException)throw error;library=library.copy(error=message(error)) }
            finally { library=library.copy(refreshing=false) }
        }
    }
    fun openDetail(media: UiMedia) {
        detailJob?.cancel();detail=DetailUiState(media,loading=true)
        detailJob=viewModelScope.launch {
            try {
                progressWrites.withLock {}
                val result=repository.detail(resolve(media))
                val seasons=result.seasons.map { UiSeason(it.number.toString(),it.name,remember(it.episodes)) }
                val fresh=remember(listOf(result.item)).first()
                detail=DetailUiState(fresh,result.item.plot,result.genres,result.cast,result.director,(result.item.durationSeconds*1000).toLong(),seasons,seasons.firstOrNull()?.id.orEmpty())
            } catch(error: Exception) { if(error is CancellationException)throw error;detail=detail?.copy(loading=false,error=message(error)) }
        }
    }
    fun closeDetail() { detailJob?.cancel();detail=null }
    fun season(id: String) { detail=detail?.copy(selectedSeasonId=id) }
    fun favorite(media: UiMedia) {
        viewModelScope.launch {
            try { repository.toggleFavorite(resolve(media));detail?.takeIf { it.media.id==media.id }?.let { old -> detail=old.copy(media=present(repository.item(media.id)?:resolve(media))) };loadLibrary() }
            catch(error: Exception) { if(error is CancellationException)throw error;notice=message(error) }
        }
    }
    fun play(media: UiMedia) {
        if(media.kind=="series") { openDetail(media);return }
        startPlayback { resolve(media) }
    }

    fun playNext(generation: Long) {
        val current = player?.takeIf { it.generation == generation && playGeneration == generation } ?: return
        val next = current.nextEpisode ?: return
        startPlayback { next }
    }

    suspend fun findSportsChannels(labels: List<String>): Map<String, String> {
        val requested = labels.associateWith(SportsChannels::key).filterValues { it.isNotBlank() }
        if (requested.isEmpty()) return emptyMap()
        val matches = repository.liveChannelNames().groupBy { (_, name) -> SportsChannels.key(name) }
        return buildMap {
            requested.forEach { (label, key) ->
                val channel = matches[key].orEmpty().maxWithOrNull(
                    compareBy<Pair<String, String>> { (_, name) ->
                        val folded = SportsChannels.fold(name)
                        when {
                            FullHdChannel.containsMatchIn(folded) -> 2
                            HdChannel.containsMatchIn(folded) -> 1
                            else -> 0
                        }
                    }.thenBy { (_, name) -> TurkishChannel.containsMatchIn(SportsChannels.fold(name)) }
                        .thenBy { (_, name) -> name.trim().equals(label.trim(), ignoreCase = true) },
                )
                channel?.let { (id, _) -> put(label, id) }
            }
        }
    }

    fun watchSportsChannel(id: String) = startPlayback {
        repository.item(id)?.takeIf { it.kind == MediaKind.LIVE }
            ?: throw IptvException("Bu kanal IPTV listende bulunamadı.")
    }

    private fun startPlayback(resolveItem: suspend () -> MediaItem) {
        playJob?.cancel()
        val generation=++playGeneration
        val accountId=account.value?.id?:return
        playJob=viewModelScope.launch {
            try {
                val item=resolveItem()
                val progress=repository.progress(item.id)
                val preference=repository.trackPreference(item.id)
                if (generation != playGeneration || account.value?.id != accountId) return@launch
                val playing = PlayingItem(
                    item, repository.streamUrl(item),
                    if (progress?.completed == true) 0 else ((progress?.positionSeconds ?: 0.0) * 1000).toLong(),
                    preference, accountId, generation,
                )
                player = playing
                if (item.kind == MediaKind.EPISODE) {
                    val next = try {
                        repository.nextEpisode(item)
                    } catch (error: CancellationException) {
                        throw error
                    } catch (_: Exception) {
                        null // Missing episode metadata must never stop the current stream.
                    }
                    val siblings = runCatching {
                        repository.siblingEpisodes(item).map { ep ->
                            val tag = if (ep.season > 0 && ep.episode > 0) "S${ep.season}·B${ep.episode} — " else ""
                            ep.id to "$tag${ep.name}"
                        }
                    }.getOrDefault(emptyList())
                    if (generation == playGeneration && account.value?.id == accountId) {
                        player = playing.copy(nextEpisode = next, episodes = siblings)
                    }
                }
            } catch(error: Exception) { if(error is CancellationException)throw error;notice=message(error) }
        }
    }
    fun closePlayer() { playJob?.cancel();playGeneration++;player=null;if(account.value!=null){loadLibrary();detail?.media?.let { openDetail(it) }} }
    fun saveProgress(accountId: String, item: MediaItem, position: Long, duration: Long) {
        if (player?.isLocalUri == true || accountId == "_local") return
        viewModelScope.launch {
            progressWrites.withLock {
                if (account.value?.id == accountId) {
                    try {
                        repository.saveProgress(item, position / 1000.0, duration / 1000.0)
                    } catch (error: CancellationException) {
                        throw error
                    } catch (_: Exception) {
                        // Playback continues if a local write fails.
                    }
                }
            }
        }
    }
    fun saveTracks(accountId: String,itemId: String,audio: Int?,subtitle: Int?) { viewModelScope.launch { if(account.value?.id==accountId)runCatching { repository.saveTrackPreference(itemId,TrackPreference(audio,subtitle,subtitle==null||subtitle<0)) } } }
    fun openCollection(collection: UiCollection) { currentCollection=collection.id;library=library.copy(tab=LibraryTab.PLAYLISTS,query="",title=collection.title);loadLibrary() }
    fun closeCollection() { currentCollection=null;library=library.copy(tab=LibraryTab.PLAYLISTS,query="",title="",items=emptyList());loadLibrary() }
    fun deleteCollection(collection: UiCollection) {
        viewModelScope.launch {
            try {
                repository.deletePlaylist(collection.id)
                if(currentCollection==collection.id)currentCollection=null
                notice="Liste silindi."
                loadLibrary()
            } catch(error: Exception) { if(error is CancellationException)throw error;notice=message(error) }
        }
    }
    fun clearProgress(media: UiMedia) {
        viewModelScope.launch {
            try {
                repository.clearProgress(media.id)
                detail?.takeIf { it.media.id==media.id }?.let { old -> detail=old.copy(media=old.media.copy(progressPositionMs=0,progressDurationMs=0)) }
                notice="İzleme kaydı sıfırlandı."
                loadLibrary()
            } catch(error: Exception) { if(error is CancellationException)throw error;notice=message(error) }
        }
    }
    fun addToCollection(item: UiMedia?) { collectionTarget=item;showCollectionPicker=true }
    fun chooseCollection(collection: UiCollection) {
        val item=collectionTarget
        showCollectionPicker=false
        if(item==null) { openCollection(collection);return }
        viewModelScope.launch { try { repository.addToPlaylist(collection.id,resolve(item));notice="${collection.title} listesine eklendi.";loadLibrary() } catch(error: Exception) { if(error is CancellationException)throw error;notice=message(error) } }
    }
    fun createCollection(name: String) {
        viewModelScope.launch { try { val list=repository.createPlaylist(name);val item=collectionTarget;if(item!=null)repository.addToPlaylist(list.id,resolve(item));showCollectionPicker=false;notice="Listen hazır.";loadLibrary() } catch(error: Exception) { if(error is CancellationException)throw error;notice=message(error) } }
    }
    fun exportTo(uri: Uri) { viewModelScope.launch { try { val json=repository.exportState();withContext(Dispatchers.IO) { getApplication<Application>().contentResolver.openOutputStream(uri,"wt")?.use { it.write(json.toByteArray()) }?:throw IptvException("Yedek dosyası yazılamadı.") };notice="Yedek kaydedildi." } catch(error: Exception) { if(error is CancellationException)throw error;notice=message(error) } } }
    fun importFrom(uri: Uri) { viewModelScope.launch { try { val json=withContext(Dispatchers.IO) { getApplication<Application>().contentResolver.openInputStream(uri)?.use { stream -> val bytes=stream.readBounded();if(bytes.size>25*1024*1024)throw IptvException("Dosya çok büyük.");bytes.toString(Charsets.UTF_8) }?:throw IptvException("Dosya okunamadı.") };repository.importState(json);notice="Yedek birleştirildi.";loadLibrary() } catch(error: Exception) { if(error is CancellationException)throw error;notice=message(error) } } }
    fun syncMac(address: String, code: String) { viewModelScope.launch { try { withContext(Dispatchers.IO) { MacSync.merge(repository,address,code) };notice="Mac ve telefondaki izleme kayıtları, favoriler ve listeler birleştirildi.";loadLibrary() } catch(error: Exception) { if(error is CancellationException)throw error;notice=message(error) } } }
    fun refreshProfiles() {
        viewModelScope.launch {
            runCatching { repository.profiles() to repository.activeProfile() }.onSuccess { (list, current) ->
                profiles = list
                activeProfile = current
            }
        }
    }
    fun createProfile(name: String, avatarColor: String, isKids: Boolean, pin: String) {
        profileError = null
        viewModelScope.launch {
            try {
                repository.createProfile(name, avatarColor, isKids, pin)
                refreshProfiles()
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                profileError = message(error)
            }
        }
    }
    fun switchProfile(id: String, pin: String = "") {
        profileError = null
        viewModelScope.launch {
            try {
                activeProfile = repository.switchProfile(id, pin)
                refreshProfiles()
                showProfilePicker = false
                detail = null
                notice = "${activeProfile.name} profili aktif."
                if (account.value != null) loadLibrary()
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                profileError = message(error)
            }
        }
    }
    fun deleteProfile(id: String) {
        profileError = null
        viewModelScope.launch {
            try {
                repository.deleteProfile(id)
                refreshProfiles()
                if (account.value != null) loadLibrary()
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                profileError = message(error)
            }
        }
    }
    fun playEpisodeById(episodeId: String) {
        startPlayback { repository.item(episodeId) ?: throw IptvException("Bölüm bulunamadı.") }
    }
    fun playLocalUri(uri: Uri) {
        playJob?.cancel()
        val generation = ++playGeneration
        val resolver = getApplication<Application>().contentResolver
        val title = runCatching {
            resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
                if (c.moveToFirst()) c.getString(0) else null
            }
        }.getOrNull()?.substringBeforeLast('.')?.takeIf { it.isNotBlank() } ?: "Yerel Video"
        val item = MediaItem("local:${uri.hashCode()}", "local", title, MediaKind.VOD, "", "Cihazım", sourceUrl = uri.toString())
        player = PlayingItem(item, uri.toString(), 0L, TrackPreference(), "_local", generation, isLocalUri = true)
    }
    fun surpriseMe() {
        viewModelScope.launch {
            try {
                val chosen = repository.surpriseItem()
                knownItems[chosen.id] = chosen
                val ui = present(chosen)
                notice = "Sürpriz seçim: ${chosen.name}"
                if (chosen.kind == MediaKind.SERIES) openDetail(ui) else startPlayback { chosen }
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                notice = message(error)
            }
        }
    }
    fun refreshCloudStatus() {
        viewModelScope.launch {
            runCatching { cloudClient.refreshStatus() }.onSuccess { cloudState = it }.onFailure { cloudState = cloudClient.current() }
        }
    }
    fun cloudAuthenticate(url: String, email: String, password: String, register: Boolean) {
        viewModelScope.launch {
            try {
                cloudState = cloudClient.authenticate(url, email, password, register)
                notice = "Cineva hesabına bağlanıldı (${cloudState.plan})."
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                notice = message(error)
            }
        }
    }
    fun cloudRedeem(code: String) {
        viewModelScope.launch {
            try {
                cloudState = cloudClient.redeemLicense(code)
                notice = "Lisans etkinleştirildi: ${cloudState.plan}"
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                notice = message(error)
            }
        }
    }
    fun cloudLogout() {
        cloudClient.logout()
        cloudState = cloudClient.current()
    }
    fun logout() { viewModelScope.launch { repository.logout();knownItems.clear() } }
}
