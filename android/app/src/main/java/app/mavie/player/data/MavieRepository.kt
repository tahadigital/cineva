package app.mavie.player.data

import android.content.Context
import app.mavie.player.limitBytes
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
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.IOException
import java.io.InputStream
import java.io.InputStreamReader
import java.security.MessageDigest
import java.time.LocalDate
import java.time.ZoneId
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

private const val MAX_M3U_BYTES = 200L * 1024 * 1024
private val STREAM_CATALOG_ACTIONS = setOf("get_live_streams", "get_vod_streams", "get_series")
private val REDIRECT_CODES = setOf(301, 302, 303, 307, 308)
private val IstanbulZone: ZoneId = ZoneId.of("Europe/Istanbul")

/** Native network + database layer. No desktop or local web server is involved. */
class MavieRepository internal constructor(
    private val database: CatalogStore,
    private val credentials: AccountStore,
    val discoveryUpdates: StateFlow<Long>,
    private val discoverySnapshot: () -> JSONObject,
    private val client: OkHttpClient = MavieBaseHttpClient,
    private val streamClient: OkHttpClient = MavieStreamHttpClient,
    private val jsonParser: (InputStream) -> Any = ::readProviderJson,
    private val onClose: () -> Unit = {},
) {
    private constructor(
        database: CatalogStore,
        credentials: AccountStore,
        discoveryFeed: DiscoveryFeed,
    ) : this(
        database = database,
        credentials = credentials,
        discoveryUpdates = discoveryFeed.updates,
        discoverySnapshot = { discoveryFeed.snapshot() },
        onClose = {
            discoveryFeed.close()
            database.close()
        },
    )

    constructor(context: Context) : this(
        database = LocalDatabase(context.applicationContext),
        credentials = CredentialStore(context.applicationContext),
        discoveryFeed = DiscoveryFeed(context.applicationContext, baseClient = MavieBaseHttpClient),
    )

    private val initialLoad = credentials.loadResult()
    @Volatile private var current: SavedAccount? = (initialLoad as? CredentialLoadResult.Loaded)?.account
    private val _account = MutableStateFlow(current?.info)
    val account: StateFlow<AccountInfo?> = _account.asStateFlow()
    private val _credentialError = MutableStateFlow((initialLoad as? CredentialLoadResult.Failed)?.error)
    val credentialError: StateFlow<IptvException?> = _credentialError.asStateFlow()
    private val _syncState = MutableStateFlow(SyncState())
    val syncState: StateFlow<SyncState> = _syncState.asStateFlow()
    private val syncMutex = Mutex()
    private val loginMutex = Mutex()
    private val stateMutex = Mutex()
    private val catalogVersion = AtomicLong(0L)
    private val historyVersion = AtomicLong(0L)

    private data class DiscoveryCacheKey(
        val accountId: String,
        val profileId: String,
        val isKids: Boolean,
        val catalogVersion: Long,
        val historyVersion: Long,
        val discoveryUpdatedTick: Long,
        val feedUpdatedAt: Double,
        val day: LocalDate,
    )
    @Volatile private var cachedDiscovery: Pair<DiscoveryCacheKey, DiscoveryResult>? = null

    fun clearCredentialError() {
        _credentialError.value = null
    }

    fun close() {
        cachedDiscovery = null
        onClose()
    }

    internal fun newLanClient(): OkHttpClient = client.newBuilder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .callTimeout(20, TimeUnit.SECONDS)
        .followRedirects(false)
        .followSslRedirects(false)
        .build()

    private sealed interface ResilienceStep<out T> {
        data class Redirect(val nextUrl: HttpUrl) : ResilienceStep<Nothing>
        data class Done<T>(val value: T) : ResilienceStep<T>
    }

    fun getConnectionInfo(): AccountInfo? = account.value
    private fun saved(): SavedAccount = current ?: throw IptvException("Önce IPTV hesabını bu telefona ekle.", MavieErrorCode.AUTH_REJECTED)
    private fun savedFor(item: MediaItem): SavedAccount = saved().also {
        if (item.accountId != null && item.accountId != it.info.id) {
            throw IptvException("Hesap değişti. İçeriği yeni hesabının kütüphanesinden aç.", MavieErrorCode.INVALID_INPUT)
        }
    }
    private fun sameAccount(account: SavedAccount) {
        if (current?.info?.id != account.info.id) {
            throw IptvException("Hesap değişti. İçeriği yeniden aç.", MavieErrorCode.INVALID_INPUT)
        }
    }

    private fun sha256(value: String): String =
        MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

    suspend fun loginDemo(): AccountInfo = withContext(Dispatchers.IO) {
        loginMutex.withLock {
            val id = "demo_open_cinema"
            val settings = ConnectionSettings(sourceType = SourceMode.DEMO)
            val info = AccountInfo(id, "demo", "", name = "Açık Sinema (Demo)", status = "Demo", sourceType = SourceMode.DEMO)
            val account = SavedAccount(settings, info)
            stateMutex.withLock {
                credentials.save(account)
                database.replaceCatalog(id, MediaKind.VOD, DemoCatalog.categories, DemoCatalog.items)
                database.replaceCatalog(id, MediaKind.LIVE, emptyList(), emptyList())
                database.replaceCatalog(id, MediaKind.SERIES, emptyList(), emptyList())
                current = account
                _account.value = info
                _credentialError.value = null
                catalogVersion.incrementAndGet()
                cachedDiscovery = null
            }
            info
        }
    }

    private data class M3uPersistResult(val effectiveUrl: HttpUrl, val summary: M3uStreamSummary)
    private data class ApiResult(val payload: Any, val effectiveBaseUrl: HttpUrl)

    internal fun validateRedirectHop(currentUrl: HttpUrl, location: String?): HttpUrl {
        val raw = location?.trim()?.takeIf { it.isNotEmpty() }
            ?: throw IptvException("Yönlendirme adresi geçersiz.", MavieErrorCode.UNSAFE_URL)
        val nextUrl = currentUrl.resolve(raw)
            ?: throw IptvException("Güvenli olmayan yönlendirme adresi engellendi.", MavieErrorCode.UNSAFE_URL)
        if (nextUrl.scheme !in setOf("http", "https") || nextUrl.host.isBlank()) {
            throw IptvException("Güvenli olmayan yönlendirme adresi engellendi.", MavieErrorCode.UNSAFE_URL)
        }
        if (UrlSecurity.hasUrlCredentials(currentUrl)) {
            if (!nextUrl.host.equals(currentUrl.host, ignoreCase = true)) {
                throw IptvException("Kimlik bilgisi içeren farklı sunucuya yönlendirme engellendi.", MavieErrorCode.UNSAFE_URL)
            }
            if (currentUrl.scheme == "https" && nextUrl.scheme == "http") {
                throw IptvException("HTTPS bağlantısından güvensiz HTTP yönlendirmesi engellendi.", MavieErrorCode.TLS_FAILED)
            }
        }
        val nextAddrs = UrlSecurity.resolveHostSafe(nextUrl.host)
        if (UrlSecurity.isCloudMetadataOrLinkLocal(nextUrl.host, nextAddrs)) {
            throw IptvException("Güvenli olmayan yönlendirme adresi engellendi.", MavieErrorCode.UNSAFE_URL)
        }
        val currentWasPublic = !UrlSecurity.isPrivateOrLoopback(currentUrl.host)
        if (currentWasPublic && UrlSecurity.isPrivateOrLoopback(nextUrl.host, nextAddrs)) {
            throw IptvException("Güvenli olmayan yerel ağ yönlendirmesi engellendi.", MavieErrorCode.UNSAFE_URL)
        }
        return nextUrl
    }

    private suspend fun <T> executeWithResilience(
        targetClient: OkHttpClient,
        initialUrl: HttpUrl,
        isM3u: Boolean,
        acceptHeader: String? = null,
        block: (effectiveUrl: HttpUrl, response: Response) -> T,
    ): T {
        if (UrlSecurity.isCloudMetadataOrLinkLocal(initialUrl.host)) {
            throw IptvException("Bu sunucu adresine güvenlik nedeniyle bağlanılamaz.", MavieErrorCode.UNSAFE_URL)
        }
        val callClient = targetClient.newBuilder()
            .followRedirects(false)
            .followSslRedirects(false)
            .build()
        var currentUrl = initialUrl
        var userAgent = MaviePrimaryUserAgent
        var uaRetried = false
        var redirectCount = 0
        val opContext = currentCoroutineContext()
        while (true) {
            opContext.ensureActive()
            var bodyStarted = false
            try {
                val builder = Request.Builder().url(currentUrl).header("User-Agent", userAgent)
                if (acceptHeader != null) builder.header("Accept", acceptHeader)
                val step = callClient.newCall(builder.build()).readCancellable { response ->
                    if (response.code in REDIRECT_CODES) {
                        val nextUrl = validateRedirectHop(currentUrl, response.header("Location"))
                        ResilienceStep.Redirect(nextUrl)
                    } else {
                        if (!response.isSuccessful) throw HttpStatusException(response.code)
                        bodyStarted = true
                        ResilienceStep.Done(block(currentUrl, response))
                    }
                }
                when (step) {
                    is ResilienceStep.Redirect -> {
                        if (++redirectCount > 5) {
                            throw IptvException("Sunucu çok fazla yönlendirme yaptı.", MavieErrorCode.HTTP_ERROR)
                        }
                        currentUrl = step.nextUrl
                        continue
                    }
                    is ResilienceStep.Done -> return step.value
                }
            } catch (cancel: CancellationException) {
                throw cancel
            } catch (http: HttpStatusException) {
                if (!uaRetried && (http.code == 403 || http.code == 406)) {
                    uaRetried = true
                    userAgent = MavieFallbackUserAgent
                    continue
                }
                throw classifyHttpError(http.code, isM3u)
            } catch (error: IptvException) {
                throw error
            } catch (error: IOException) {
                if (!bodyStarted && !uaRetried && isUaFallbackEligible(error)) {
                    uaRetried = true
                    userAgent = MavieFallbackUserAgent
                    continue
                }
                throw classifyIoException(error)
            } catch (err: Exception) {
                throw IptvException(
                    if (isM3u) "M3U listesi işlenemedi." else "IPTV sunucusu geçerli bir yanıt göndermedi.",
                    MavieErrorCode.INVALID_RESPONSE,
                    err,
                )
            }
        }
    }

    private suspend fun fetchAndPersistM3u(
        playlistUrl: HttpUrl,
        resolveAccountId: (HttpUrl) -> String,
    ): M3uPersistResult {
        val opContext = currentCoroutineContext()
        return executeWithResilience(streamClient, playlistUrl, isM3u = true) { effectiveUrl, response ->
            val body = response.body ?: throw IptvException("M3U adresi boş yanıt döndürdü.", MavieErrorCode.INVALID_RESPONSE)
            if (body.contentLength() > MAX_M3U_BYTES) {
                throw IptvException("M3U listesi çok büyük (200 MB sınırı aşıldı).", MavieErrorCode.PAYLOAD_TOO_LARGE)
            }
            val accountId = resolveAccountId(effectiveUrl)
            val summary = body.byteStream()
                .limitBytes(MAX_M3U_BYTES, "M3U listesi çok büyük (200 MB sınırı aşıldı).", MavieErrorCode.PAYLOAD_TOO_LARGE)
                .use { limited ->
                    BufferedReader(InputStreamReader(limited, Charsets.UTF_8), 64 * 1024).use { reader ->
                        database.replaceAllCatalogsStream(accountId) { onBatch ->
                            M3uParser.parseStream(
                                reader = reader,
                                batchSize = 500,
                                checkCancelled = { opContext.ensureActive() },
                                onBatch = onBatch,
                            )
                        }
                    }
                }
            M3uPersistResult(effectiveUrl, summary)
        }
    }

    private fun validateUserEpgUrl(raw: String): String {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return ""
        val parsed = normalizedHttpUrl(trimmed)
        if (UrlSecurity.isCloudMetadataOrLinkLocal(parsed.host)) {
            throw IptvException("EPG adresi güvenlik nedeniyle kabul edilemiyor.", MavieErrorCode.UNSAFE_URL)
        }
        return parsed.toString()
    }

    private fun safeParsedEpgUrl(raw: String, playlistUrl: HttpUrl): String {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return ""
        val parsed = runCatching { normalizedHttpUrl(trimmed) }.getOrNull() ?: return ""
        return if (UrlSecurity.isSafeAutoEpgUrl(parsed, playlistUrl)) parsed.toString() else ""
    }

    suspend fun loginM3u(name: String, m3uUrl: String, epgUrl: String = ""): AccountInfo = withContext(Dispatchers.IO) {
        loginMutex.withLock {
            val playlistUrl = normalizedHttpUrl(m3uUrl)
            val cleanEpg = validateUserEpgUrl(epgUrl)
            val persisted = fetchAndPersistM3u(playlistUrl) { effectiveUrl -> sha256("m3u\n$effectiveUrl") }
            val effectiveUrl = persisted.effectiveUrl
            val id = sha256("m3u\n$effectiveUrl")
            val parsedEpg = safeParsedEpgUrl(persisted.summary.epgUrl, effectiveUrl)
            val resolvedEpg = cleanEpg.ifBlank { parsedEpg }
            val settings = ConnectionSettings(sourceType = SourceMode.M3U, m3uUrl = effectiveUrl.toString(), epgUrl = resolvedEpg)
            val info = AccountInfo(id, "m3u", effectiveUrl.host, name = name.ifBlank { "M3U Listesi" }, status = "Active", sourceType = SourceMode.M3U, epgUrl = resolvedEpg)
            val account = SavedAccount(settings, info)
            stateMutex.withLock {
                credentials.save(account)
                current = account
                _account.value = info
                _credentialError.value = null
                catalogVersion.incrementAndGet()
                cachedDiscovery = null
            }
            info
        }
    }

    suspend fun login(settings: ConnectionSettings): AccountInfo = withContext(Dispatchers.IO) {
        loginMutex.withLock {
            val normalized = normalizeConnection(settings)
            val cleanEpg = validateUserEpgUrl(normalized.epgUrl)
            val apiResult = apiWithEffectiveUrl(normalized)
            val data = apiResult.payload as? JSONObject ?: throw IptvException("Sağlayıcı geçerli bir hesap yanıtı göndermedi.", MavieErrorCode.INVALID_RESPONSE)
            val user = data.optJSONObject("user_info") ?: throw IptvException("Hesap doğrulanamadı.", MavieErrorCode.AUTH_REJECTED)
            val status = user.text("status", "Active")
            if (user.optInt("auth", 0) != 1) throw IptvException("Kullanıcı adı veya parola doğrulanamadı.", MavieErrorCode.AUTH_REJECTED)
            if (!status.equals("Active", true)) throw IptvException("Aboneliğin etkin görünmüyor. Sağlayıcınla kontrol et.", MavieErrorCode.SUBSCRIPTION_INACTIVE)
            val effectiveHost = apiResult.effectiveBaseUrl.toString().trimEnd('/')
            val effectiveSettings = (if (effectiveHost != normalized.host) normalized.copy(host = effectiveHost) else normalized)
                .copy(epgUrl = cleanEpg)
            val id = sha256(effectiveSettings.host + "\n" + effectiveSettings.username)
            val info = AccountInfo(
                id,
                effectiveSettings.username,
                effectiveSettings.host,
                name = settings.host.removePrefix("https://").removePrefix("http://"),
                status = status,
                expiresAt = user.text("exp_date").toLongOrNull()?.takeIf { it > 0 },
                maxConnections = user.optInt("max_connections", 1).coerceAtLeast(1),
                sourceType = SourceMode.XTREAM,
                epgUrl = cleanEpg,
            )
            val account = SavedAccount(effectiveSettings, info)
            stateMutex.withLock {
                try { credentials.save(account) } catch (error: IptvException) { throw error } catch (err: Exception) {
                    throw IptvException("Hesap bu cihazda güvenli biçimde kaydedilemedi.", MavieErrorCode.KEYSTORE_ERROR, err)
                }
                current = account
                _account.value = info
                _credentialError.value = null
                catalogVersion.incrementAndGet()
                cachedDiscovery = null
            }
            info
        }
    }

    suspend fun importConnection(json: String): AccountInfo {
        if (json.length > 1_000_000) throw IptvException("Bağlantı dosyası çok büyük.", MavieErrorCode.PAYLOAD_TOO_LARGE)
        val data = try { JSONObject(json) } catch (err: Exception) {
            throw IptvException("Geçerli bir bağlantı JSON dosyası seç.", MavieErrorCode.INVALID_INPUT, err)
        }
        val value = data.optJSONObject("connection") ?: data
        return login(ConnectionSettings(value.text("host", value.text("url")), value.text("username"), value.text("password")))
    }

    suspend fun updateEpgUrl(epgUrl: String): AccountInfo = withContext(Dispatchers.IO) {
        loginMutex.withLock {
            val cleanEpg = validateUserEpgUrl(epgUrl)
            stateMutex.withLock {
                val account = saved()
                val updatedSettings = account.settings.copy(epgUrl = cleanEpg)
                val updatedInfo = account.info.copy(epgUrl = cleanEpg)
                val updatedAccount = SavedAccount(updatedSettings, updatedInfo)
                credentials.save(updatedAccount)
                current = updatedAccount
                _account.value = updatedInfo
                updatedInfo
            }
        }
    }

    suspend fun logout() = withContext(Dispatchers.IO) {
        loginMutex.withLock {
            stateMutex.withLock {
                credentials.clear()
                current = null
                _account.value = null
                _credentialError.value = null
                _syncState.value = SyncState()
                catalogVersion.incrementAndGet()
                historyVersion.incrementAndGet()
                cachedDiscovery = null
            }
        }
    }

    suspend fun refreshCatalog() = withContext(Dispatchers.IO) {
        syncMutex.withLock {
            val account = saved()
            _syncState.value = SyncState(true, "Kütüphanen yenileniyor…")
            try {
                when (account.settings.sourceType) {
                    SourceMode.DEMO -> {
                        stateMutex.withLock {
                            sameAccount(account)
                            database.replaceCatalog(account.info.id, MediaKind.VOD, DemoCatalog.categories, DemoCatalog.items)
                            database.replaceCatalog(account.info.id, MediaKind.LIVE, emptyList(), emptyList())
                            database.replaceCatalog(account.info.id, MediaKind.SERIES, emptyList(), emptyList())
                            catalogVersion.incrementAndGet()
                            cachedDiscovery = null
                        }
                    }
                    SourceMode.M3U -> {
                        val playlistUrl = normalizedHttpUrl(account.settings.m3uUrl)
                        val persisted = fetchAndPersistM3u(playlistUrl) { account.info.id }
                        stateMutex.withLock {
                            sameAccount(account)
                            val parsedEpg = safeParsedEpgUrl(persisted.summary.epgUrl, persisted.effectiveUrl)
                            val nextEpg = parsedEpg.ifBlank { account.settings.epgUrl }
                            val nextM3u = persisted.effectiveUrl.toString()
                            if (nextEpg != account.settings.epgUrl || nextM3u != account.settings.m3uUrl) {
                                val updatedSettings = account.settings.copy(m3uUrl = nextM3u, epgUrl = nextEpg)
                                val updatedInfo = account.info.copy(host = persisted.effectiveUrl.host, epgUrl = nextEpg)
                                val updatedAccount = SavedAccount(updatedSettings, updatedInfo)
                                credentials.save(updatedAccount)
                                current = updatedAccount
                                _account.value = updatedInfo
                            }
                            catalogVersion.incrementAndGet()
                            cachedDiscovery = null
                        }
                    }
                    SourceMode.XTREAM -> {
                        for ((index, kind) in listOf(MediaKind.LIVE, MediaKind.VOD, MediaKind.SERIES).withIndex()) {
                            fetchCatalog(account, kind, index * 2)
                        }
                    }
                }
                _syncState.value = SyncState(false, "Kütüphanen güncel.", 6)
            } catch (error: CancellationException) {
                _syncState.value = SyncState()
                throw error
            } catch (error: Exception) {
                val iptv = error as? IptvException
                val message = iptv?.message ?: "Kütüphane yenilenemedi. İnternet bağlantını kontrol et."
                val code = iptv?.code ?: MavieErrorCode.OFFLINE
                _syncState.value = SyncState(false, error = message)
                throw IptvException(message, code, error)
            }
        }
    }

    private suspend fun ensureCatalog(account: SavedAccount, kind: MediaKind) {
        if (kind == MediaKind.EPISODE) return
        if (account.settings.sourceType != SourceMode.XTREAM) return
        syncMutex.withLock {
            sameAccount(account)
            val old = database.cache(account.info.id, "catalog:${kind.key}")
            if (old != null && System.currentTimeMillis() - old.second < 24 * 60 * 60 * 1000L) return@withLock
            try { fetchCatalog(account, kind) }
            catch (error: CancellationException) { throw error }
            catch (error: Exception) { if (old == null) throw error }
        }
    }

    private suspend fun fetchCatalog(account: SavedAccount, kind: MediaKind, step: Int = 0) {
        sameAccount(account)
        val label = when (kind) { MediaKind.LIVE -> "Canlı kanallar"; MediaKind.VOD -> "Filmler"; else -> "Diziler" }
        if (_syncState.value.running) _syncState.value = SyncState(true, "$label kategorileri alınıyor…", step)
        val categoryAction = when (kind) { MediaKind.LIVE -> "get_live_categories"; MediaKind.VOD -> "get_vod_categories"; else -> "get_series_categories" }
        val itemAction = when (kind) { MediaKind.LIVE -> "get_live_streams"; MediaKind.VOD -> "get_vod_streams"; else -> "get_series" }
        val rawCategories = api(account.settings, categoryAction)
        val categories = when {
            rawCategories is JSONArray -> categoriesFromJson(rawCategories, kind)
            rawCategories is JSONObject && rawCategories.length() == 0 -> emptyList()
            else -> throw IptvException("$label kategorileri alınamadı.", MavieErrorCode.INVALID_RESPONSE)
        }
        if (_syncState.value.running) _syncState.value = SyncState(true, "$label hazırlanıyor…", step + 1)
        val rawData = api(account.settings, itemAction)
        val data = when {
            rawData is JSONArray -> rawData
            rawData is JSONObject && rawData.length() == 0 -> JSONArray()
            else -> throw IptvException("$label listesi alınamadı.", MavieErrorCode.INVALID_RESPONSE)
        }
        val categoryMap = categories.associate { it.id to it.name }
        val items = buildList { for (index in 0 until data.length()) data.optJSONObject(index)?.let { itemFromProvider(it, kind, categoryMap) }?.let(::add) }
        stateMutex.withLock {
            sameAccount(account)
            database.replaceCatalog(account.info.id, kind, categories, items)
            catalogVersion.incrementAndGet()
            cachedDiscovery = null
        }
    }

    suspend fun categories(kind: MediaKind): List<Category> = withContext(Dispatchers.IO) {
        val account = saved(); ensureCatalog(account, kind)
        val cats = database.categories(account.info.id, kind)
        if (database.activeProfile().isKids) cats.filterNot { AdultContentFilter.isAdult(it.name, it.name) } else cats
    }

    suspend fun catalog(kind: MediaKind, query: String = "", categoryId: String? = null, page: Int = 0, pageSize: Int = 60, onlyFavorites: Boolean = false): CatalogPage = withContext(Dispatchers.IO) {
        val account = saved(); ensureCatalog(account, kind)
        val where = mutableListOf("i.kind=?"); val args = mutableListOf(kind.key)
        if (!categoryId.isNullOrBlank()) { where += "i.category_id=?"; args += categoryId }
        if (query.isNotBlank()) { where += "i.search LIKE ? ESCAPE '\\'"; args += "%" + fold(query.trim()).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" }
        if (onlyFavorites) where += "f.item_id IS NOT NULL"
        val condition = where.joinToString(" AND "); val size = pageSize.coerceIn(1, 200); val currentPage = page.coerceIn(0, 1_000_000)
        val isKids = database.activeProfile().isKids
        if (isKids) {
            return@withContext database.kidsCatalogPage(account.info.id, kind, condition, args, currentPage, size)
        }
        val total = database.count(account.info.id, condition, args)
        val rows = database.items(account.info.id, condition, args, limit = size, offset = currentPage * size)
        CatalogPage(rows, currentPage, total, (currentPage + 1) * size < total)
    }

    suspend fun item(id: String): MediaItem? = withContext(Dispatchers.IO) { database.item(saved().info.id, id) }
    suspend fun liveChannelNames(): List<Pair<String, String>> = withContext(Dispatchers.IO) {
        val account = saved()
        ensureCatalog(account, MediaKind.LIVE)
        database.liveChannelNames(account.info.id)
    }
    suspend fun favorites(kind: MediaKind? = null): List<MediaItem> = withContext(Dispatchers.IO) {
        database.items(saved().info.id, "f.item_id IS NOT NULL" + (if (kind != null) " AND i.kind=?" else ""), if (kind != null) listOf(kind.key) else emptyList(), order = "f.created_at DESC", limit = 20000)
    }
    suspend fun home(): HomeSections = withContext(Dispatchers.IO) {
        val operationContext = currentCoroutineContext()
        val checkCancelled = { operationContext.ensureActive() }
        checkCancelled()
        val account = saved(); ensureCatalog(account, MediaKind.VOD); ensureCatalog(account, MediaKind.SERIES)
        val profile = database.activeProfile()
        val isKids = profile.isKids
        val feed = discoverySnapshot()
        val day = LocalDate.now(IstanbulZone)
        val cacheKey = DiscoveryCacheKey(
            accountId = account.info.id,
            profileId = profile.id,
            isKids = isKids,
            catalogVersion = catalogVersion.get(),
            historyVersion = historyVersion.get(),
            discoveryUpdatedTick = discoveryUpdates.value,
            feedUpdatedAt = feed.optDouble("updatedAt", 0.0),
            day = day,
        )
        val cached = cachedDiscovery
        val discovery = if (cached != null && cached.first == cacheKey) {
            cached.second
        } else {
            val allCatalog = buildList {
                var offset = 0
                do {
                    checkCancelled()
                    val rows = database.slimItems(account.info.id, "i.kind IN ('vod','series')", limit = 20000, offset = offset, checkCancelled = checkCancelled)
                    addAll(if (isKids) rows.filterNot { AdultContentFilter.isAdult(it.name, it.categoryName) } else rows)
                    offset += rows.size
                } while (rows.size == 20000)
            }
            checkCancelled()
            val history = database.slimItems(account.info.id, "p.item_id IS NOT NULL OR f.item_id IS NOT NULL", limit = 20000, checkCancelled = checkCancelled)
            checkCancelled()
            buildDiscovery(allCatalog, history, feed, today = day, checkCancelled = checkCancelled).also {
                cachedDiscovery = cacheKey to it
            }
        }
        checkCancelled()
        val watched = database.slimItems(account.info.id, "(p.position>0 OR p.completed=1) AND i.kind IN ('vod','episode')", order = "p.updated_at DESC,i.id", limit = 500, checkCancelled = checkCancelled)
        val continuing = mutableListOf<MediaItem>()
        val seenSeries = mutableSetOf<String>()
        for (row in watched) {
            checkCancelled()
            if (isKids && AdultContentFilter.isAdult(row.name, row.categoryName)) continue
            var item = row
            if (item.kind == MediaKind.EPISODE) {
                val parent = item.parentId
                val key = parent ?: item.id
                if (!seenSeries.add(key)) continue
                if (item.progress?.completed == true) {
                    val episodes = if (parent != null) database.slimItems(account.info.id, "i.parent_id=?", listOf(parent), order = "i.season,i.episode,i.name,i.id", limit = 20000, checkCancelled = checkCancelled) else emptyList()
                    val index = episodes.indexOfFirst { it.id == item.id }
                    val following = if (index >= 0) episodes.drop(index + 1).firstOrNull { next -> next.season != item.season || item.episode <= 0 || next.episode > item.episode } else null
                    if (following == null) continue
                    item = following
                }
            } else if (item.progress?.completed == true || (item.progress?.positionSeconds ?: 0.0) < 1.0) {
                continue
            }
            continuing.add(item)
            if (continuing.size == 20) break
        }
        val favs = database.slimItems(account.info.id, "f.item_id IS NOT NULL", order = "f.created_at DESC", limit = if (isKids) 100 else 24, checkCancelled = checkCancelled)
            .let { list -> if (isKids) list.filterNot { AdultContentFilter.isAdult(it.name, it.categoryName) }.take(24) else list }
        val movies = if (isKids) {
            database.kidsCatalogPage(account.info.id, MediaKind.VOD, "i.kind=?", listOf("vod"), 0, 30).items
        } else {
            database.slimItems(account.info.id, "i.kind='vod'", limit = 30, checkCancelled = checkCancelled)
        }
        val seriesList = if (isKids) {
            database.kidsCatalogPage(account.info.id, MediaKind.SERIES, "i.kind=?", listOf("series"), 0, 30).items
        } else {
            database.slimItems(account.info.id, "i.kind='series'", limit = 30, checkCancelled = checkCancelled)
        }
        HomeSections(continuing, favs, movies, seriesList, discovery)
    }

    suspend fun detail(item: MediaItem, refresh: Boolean = false): MediaDetail = withContext(Dispatchers.IO) {
        val account = savedFor(item)
        if (account.settings.sourceType != SourceMode.XTREAM) {
            return@withContext MediaDetail(database.item(account.info.id, item.id) ?: item, genres = item.genres)
        }
        val old = database.cache(account.info.id, "detail:${item.id}")
        var info = old?.let { runCatching { JSONObject(it.first) }.getOrNull() }
        if (refresh || old == null || System.currentTimeMillis() - old.second > 24 * 60 * 60 * 1000L) {
            try {
                when (item.kind) {
                    MediaKind.VOD -> {
                        val data = api(account.settings, "get_vod_info", mapOf("vod_id" to item.providerId)) as? JSONObject
                            ?: throw IptvException("Film bilgileri alınamadı.", MavieErrorCode.INVALID_RESPONSE)
                        info = data.optJSONObject("info") ?: JSONObject()
                        val updated = enrichItem(item, info!!)
                        stateMutex.withLock {
                            sameAccount(account)
                            database.putItems(account.info.id, listOf(updated))
                            database.putCache(account.info.id, "detail:${item.id}", info.toString())
                        }
                    }
                    MediaKind.SERIES -> {
                        val data = api(account.settings, "get_series_info", mapOf("series_id" to item.providerId)) as? JSONObject
                            ?: throw IptvException("Dizi bölümleri alınamadı.", MavieErrorCode.INVALID_RESPONSE)
                        info = data.optJSONObject("info") ?: JSONObject()
                        val updated = enrichItem(item, info!!); val episodes = episodesFromProvider(data, updated)
                        stateMutex.withLock {
                            sameAccount(account)
                            database.saveSeriesDetail(account.info.id, updated, episodes, info.toString())
                        }
                    }
                    else -> Unit
                }
            } catch (error: CancellationException) { throw error }
            catch (error: Exception) { if (item.kind == MediaKind.SERIES && old == null) throw error }
        }
        val fresh = database.item(account.info.id, item.id) ?: item
        val episodes = if (item.kind == MediaKind.SERIES) database.items(account.info.id, "i.parent_id=?", listOf(item.id), order = "i.season,i.episode,i.name", limit = 20000) else emptyList()
        val seasons = episodes.groupBy { it.season }.toSortedMap().map { (number, entries) -> Season(number, if (number == 0) "Özel bölümler" else "$number. Sezon", entries) }
        MediaDetail(fresh, seasons, info?.text("genre").orEmpty(), info?.text("cast").orEmpty(), info?.text("director").orEmpty())
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
        if (candidates.isEmpty()) throw IptvException("Önerilecek içerik bulunamadı.", MavieErrorCode.EMPTY_CATALOG)
        val pool = candidates.sortedByDescending { it.rating }.take(15)
        pool[java.security.SecureRandom().nextInt(pool.size)]
    }

    suspend fun profiles(): List<UserProfile> = withContext(Dispatchers.IO) { database.profiles() }
    suspend fun activeProfile(): UserProfile = withContext(Dispatchers.IO) { database.activeProfile() }
    suspend fun createProfile(name: String, color: String, isKids: Boolean, pin: String): UserProfile = withContext(Dispatchers.IO) {
        stateMutex.withLock { database.createProfile(name, color, isKids, pin) }
    }
    suspend fun switchProfile(id: String, pin: String = ""): UserProfile = withContext(Dispatchers.IO) {
        stateMutex.withLock {
            database.switchProfile(current?.info?.id, id, pin).also {
                historyVersion.incrementAndGet()
                cachedDiscovery = null
            }
        }
    }
    suspend fun deleteProfile(id: String) = withContext(Dispatchers.IO) {
        stateMutex.withLock {
            database.deleteProfile(current?.info?.id, id)
            historyVersion.incrementAndGet()
            cachedDiscovery = null
        }
    }

    fun streamUrl(item: MediaItem, liveHls: Boolean = false): String {
        if (item.kind == MediaKind.SERIES) throw IptvException("Oynatmak için bir dizi bölümü seç.", MavieErrorCode.PLAYBACK_INVALID_SOURCE)
        if (item.sourceUrl.isNotBlank()) return item.sourceUrl
        val account = savedFor(item); val settings = account.settings
        if (settings.sourceType != SourceMode.XTREAM) throw IptvException("Bu içerik için doğrudan yayın adresi bulunamadı.", MavieErrorCode.PLAYBACK_INVALID_SOURCE)
        val path = when (item.kind) { MediaKind.LIVE -> "live"; MediaKind.VOD -> "movie"; else -> "series" }
        val extension = if (item.kind == MediaKind.LIVE) { if (liveHls) "m3u8" else "ts" } else item.extension.ifBlank { "mp4" }
        return normalizedHost(settings.host).newBuilder().addPathSegment(path).addPathSegment(settings.username)
            .addPathSegment(settings.password).addPathSegment("${item.providerId}.$extension").build().toString()
    }

    suspend fun toggleFavorite(item: MediaItem): Boolean = withContext(Dispatchers.IO) {
        stateMutex.withLock {
            database.favorite(savedFor(item).info.id, item).also {
                historyVersion.incrementAndGet()
            }
        }
    }
    suspend fun progress(itemId: String): WatchProgress? = withContext(Dispatchers.IO) {
        database.progress(saved().info.id, itemId)
    }
    suspend fun saveProgress(item: MediaItem, positionSeconds: Double, durationSeconds: Double, expectedProfileId: String? = null) = withContext(Dispatchers.IO) {
        if (item.kind != MediaKind.LIVE && positionSeconds.isFinite() && positionSeconds >= 0 && durationSeconds.isFinite()) {
            stateMutex.withLock {
                val account = savedFor(item)
                if (expectedProfileId != null && database.activeProfile().id != expectedProfileId) return@withLock
                database.saveProgress(account.info.id, item, positionSeconds, durationSeconds)
                historyVersion.incrementAndGet()
            }
        }
    }
    suspend fun clearProgress(itemId: String) = withContext(Dispatchers.IO) {
        stateMutex.withLock {
            database.clearProgress(saved().info.id, itemId)
            historyVersion.incrementAndGet()
        }
    }
    suspend fun trackPreference(itemId: String): TrackPreference = withContext(Dispatchers.IO) { database.trackPreference(saved().info.id, itemId) }
    suspend fun saveTrackPreference(itemId: String, preference: TrackPreference, expectedProfileId: String? = null) = withContext(Dispatchers.IO) {
        stateMutex.withLock {
            val account = saved()
            if (expectedProfileId != null && database.activeProfile().id != expectedProfileId) return@withLock
            database.saveTrackPreference(account.info.id, itemId, preference)
        }
    }
    suspend fun playlists(includeItems: Boolean = true): List<Playlist> = withContext(Dispatchers.IO) { val account = saved().info.id; database.playlists(account).map { if (includeItems) it.copy(items = database.playlistItems(account, it.id)) else it } }
    suspend fun createPlaylist(name: String): Playlist = withContext(Dispatchers.IO) {
        stateMutex.withLock { database.createPlaylist(saved().info.id, name) }
    }
    suspend fun addToPlaylist(playlistId: String, item: MediaItem) = withContext(Dispatchers.IO) {
        stateMutex.withLock { database.addToPlaylist(savedFor(item).info.id, playlistId, item) }
    }
    suspend fun removeFromPlaylist(playlistId: String, itemId: String) = withContext(Dispatchers.IO) {
        stateMutex.withLock { database.removeFromPlaylist(saved().info.id, playlistId, itemId) }
    }
    suspend fun deletePlaylist(playlistId: String) = withContext(Dispatchers.IO) {
        stateMutex.withLock { database.deletePlaylist(saved().info.id, playlistId) }
    }
    suspend fun exportState(): String = withContext(Dispatchers.IO) { database.exportState(saved().info.id) }
    suspend fun importState(json: String) = withContext(Dispatchers.IO) {
        stateMutex.withLock {
            database.importState(saved().info.id, json)
            historyVersion.incrementAndGet()
            cachedDiscovery = null
        }
    }

    private suspend fun api(settings: ConnectionSettings, action: String? = null, parameters: Map<String, String> = emptyMap()): Any =
        apiWithEffectiveUrl(settings, action, parameters).payload

    private suspend fun apiWithEffectiveUrl(
        settings: ConnectionSettings,
        action: String? = null,
        parameters: Map<String, String> = emptyMap(),
    ): ApiResult {
        val baseHost = normalizedHost(settings.host)
        val url = baseHost.newBuilder().addPathSegment("player_api.php")
            .addQueryParameter("username", settings.username).addQueryParameter("password", settings.password).apply {
                if (action != null) addQueryParameter("action", action)
                parameters.forEach { (key, value) -> addQueryParameter(key, value) }
            }.build()
        val targetClient = if (action in STREAM_CATALOG_ACTIONS) streamClient else client
        return executeWithResilience(
            targetClient = targetClient,
            initialUrl = url,
            isM3u = false,
            acceptHeader = "application/json",
        ) { effectiveUrl, response ->
            val body = response.body ?: throw IptvException("IPTV sağlayıcısı boş bir yanıt gönderdi.", MavieErrorCode.INVALID_RESPONSE)
            if (body.contentLength() > 100 * 1024 * 1024L) {
                throw IptvException("Sağlayıcının listesi bu cihaz için çok büyük.", MavieErrorCode.PAYLOAD_TOO_LARGE)
            }
            val payload = try {
                jsonParser(body.byteStream())
            } catch (cancel: CancellationException) {
                throw cancel
            } catch (error: IptvException) {
                throw error
            } catch (error: IOException) {
                val typeName = error.javaClass.simpleName
                if (typeName.contains("Json", ignoreCase = true) || typeName.contains("Malformed", ignoreCase = true)) {
                    throw IptvException("IPTV sunucusu geçerli bir yanıt göndermedi.", MavieErrorCode.INVALID_RESPONSE, error)
                }
                throw error
            } catch (err: Exception) {
                throw IptvException("IPTV sunucusu geçerli bir yanıt göndermedi.", MavieErrorCode.INVALID_RESPONSE, err)
            }
            val effectiveBase = effectiveUrl.newBuilder().encodedPath(baseHost.encodedPath).query(null).fragment(null).build()
            ApiResult(payload, effectiveBase)
        }
    }

    companion object {
        fun normalizeConnection(settings: ConnectionSettings): ConnectionSettings {
            val url = normalizedHost(settings.host)
            if (settings.username.isBlank() || settings.password.isBlank()) throw IptvException("Kullanıcı adı ve parola gerekli.", MavieErrorCode.INVALID_INPUT)
            if (settings.username.length > 500 || settings.password.length > 1000) throw IptvException("Bağlantı bilgileri çok uzun.", MavieErrorCode.INVALID_INPUT)
            return settings.copy(host = url.toString().trimEnd('/'), username = settings.username.trim())
        }
        internal fun normalizedHttpUrl(value: String): HttpUrl {
            val input = value.trim().let { if (it.contains("://")) it else "http://$it" }
            val url = input.toHttpUrlOrNull() ?: throw IptvException("Geçersiz bağlantı adresi.", MavieErrorCode.INVALID_INPUT)
            if (url.scheme !in setOf("http", "https") || url.host.isBlank()) {
                throw IptvException("Geçersiz bağlantı adresi.", MavieErrorCode.INVALID_INPUT)
            }
            return url
        }
        private fun normalizedHost(value: String): HttpUrl {
            val input = value.trim().let { if (it.contains("://")) it else "http://$it" }
            val url = input.toHttpUrlOrNull() ?: throw IptvException("Sunucu adresi geçersiz.", MavieErrorCode.INVALID_INPUT)
            if (url.scheme !in setOf("http", "https") || url.host.isBlank()) {
                throw IptvException("Sunucu adresi geçersiz.", MavieErrorCode.INVALID_INPUT)
            }
            if (url.username.isNotEmpty() || url.password.isNotEmpty() || url.query != null || url.fragment != null) {
                throw IptvException("Sunucu alanına yalnızca sunucu adresini gir.", MavieErrorCode.INVALID_INPUT)
            }
            return url.newBuilder().encodedPath(url.encodedPath.trimEnd('/') + "/").build()
        }
    }
}
