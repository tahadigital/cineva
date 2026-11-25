package app.mavie.player.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.runBlocking
import okhttp3.Dns
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import okio.Buffer
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import org.junit.Assert.*
import org.junit.Test
import java.io.InputStream
import java.net.InetAddress
import java.net.Socket
import java.net.UnknownHostException
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLHandshakeException
import javax.net.ssl.SSLSocketFactory

class MavieRepositoryHttpTest {
    private class InMemoryAccountStore(initial: SavedAccount? = null) : AccountStore {
        var stored: SavedAccount? = initial
        override fun load(): SavedAccount? = stored
        override fun save(account: SavedAccount) {
            stored = account
        }
        override fun clear() {
            stored = null
        }
    }

    private class FakeCatalogStore(private val retainItems: Boolean = true) : CatalogStore {
        val itemsByAccount = linkedMapOf<String, MutableList<MediaItem>>()
        val categoriesByAccount = linkedMapOf<String, MutableMap<MediaKind, List<Category>>>()
        val cacheByAccount = linkedMapOf<String, MutableMap<String, Pair<String, Long>>>()
        val favoritesByAccount = linkedMapOf<String, MutableSet<String>>()
        val trackPrefsByAccount = linkedMapOf<String, MutableMap<String, TrackPreference>>()
        val batchSizes = mutableListOf<Int>()
        var committedItemCount = 0
        var discoveryCatalogQueryCount = 0

        override fun replaceCatalog(account: String, kind: MediaKind, categories: List<Category>, items: List<MediaItem>) {
            categoriesByAccount.getOrPut(account) { linkedMapOf() }[kind] = categories
            val list = itemsByAccount.getOrPut(account) { mutableListOf() }
            list.removeAll { it.kind == kind }
            if (retainItems) list.addAll(items)
            committedItemCount = if (retainItems) list.size else committedItemCount + items.size
            cacheByAccount.getOrPut(account) { linkedMapOf() }["catalog:${kind.key}"] = "{}" to System.currentTimeMillis()
        }

        override fun replaceAllCatalogsStream(
            account: String,
            stream: (onBatch: (List<MediaItem>) -> Unit) -> M3uStreamSummary,
        ): M3uStreamSummary {
            val stagedItems = mutableListOf<MediaItem>()
            var stagedCount = 0
            val summary = stream { batch ->
                if (batch.isNotEmpty()) {
                    batchSizes.add(batch.size)
                    stagedCount += batch.size
                    if (retainItems) stagedItems.addAll(batch)
                }
            }
            if (stagedCount == 0 || summary.itemCount == 0) {
                throw IptvException("M3U listesinde geçerli yayın bulunamadı.")
            }
            categoriesByAccount[account] = summary.categories.toMutableMap()
            itemsByAccount[account] = stagedItems
            committedItemCount = stagedCount
            val cache = cacheByAccount.getOrPut(account) { linkedMapOf() }
            listOf(MediaKind.LIVE, MediaKind.VOD, MediaKind.SERIES).forEach { kind ->
                cache["catalog:${kind.key}"] = "{}" to System.currentTimeMillis()
            }
            return summary
        }

        override fun putItems(account: String, items: List<MediaItem>) {
            itemsByAccount.getOrPut(account) { mutableListOf() }.addAll(items)
        }

        override fun items(
            account: String,
            where: String,
            args: List<String>,
            order: String,
            limit: Int,
            offset: Int,
            checkCancelled: () -> Unit,
        ): List<MediaItem> {
            val favs = favoritesByAccount[account].orEmpty()
            val all = itemsByAccount[account].orEmpty().map { item ->
                if (item.id in favs) item.copy(isFavorite = true) else item
            }
            val filtered = when {
                where == "i.kind IN ('vod','series')" -> all.filter { it.kind == MediaKind.VOD || it.kind == MediaKind.SERIES }
                where == "i.kind='vod'" -> all.filter { it.kind == MediaKind.VOD }
                where == "i.kind='series'" -> all.filter { it.kind == MediaKind.SERIES }
                where == "f.item_id IS NOT NULL" -> all.filter { it.id in favs }
                where == "p.item_id IS NOT NULL OR f.item_id IS NOT NULL" -> all.filter { it.id in favs || it.progress != null }
                where.contains("p.position>0") -> emptyList()
                else -> all
            }
            return filtered.drop(offset).take(limit)
        }

        override fun slimItems(
            account: String,
            where: String,
            args: List<String>,
            order: String,
            limit: Int,
            offset: Int,
            checkCancelled: () -> Unit,
        ): List<MediaItem> {
            if (where == "i.kind IN ('vod','series')") discoveryCatalogQueryCount++
            return items(account, where, args, order, limit, offset, checkCancelled)
        }

        override fun item(account: String, id: String): MediaItem? =
            itemsByAccount[account].orEmpty().firstOrNull { it.id == id }

        override fun count(account: String, where: String, args: List<String>): Int {
            val kind = args.firstOrNull()
            return itemsByAccount[account].orEmpty().count { kind == null || it.kind.key == kind }
        }

        override fun categories(account: String, kind: MediaKind): List<Category> =
            categoriesByAccount[account]?.get(kind).orEmpty()

        override fun putCache(account: String, key: String, data: String) {
            cacheByAccount.getOrPut(account) { linkedMapOf() }[key] = data to System.currentTimeMillis()
        }

        override fun cache(account: String, key: String): Pair<String, Long>? =
            cacheByAccount[account]?.get(key)

        override fun liveChannelNames(account: String): List<Pair<String, String>> =
            itemsByAccount[account].orEmpty().filter { it.kind == MediaKind.LIVE }.map { it.id to it.name }

        override fun favorite(account: String, item: MediaItem): Boolean {
            val set = favoritesByAccount.getOrPut(account) { linkedSetOf() }
            return if (set.add(item.id)) true else {
                set.remove(item.id)
                false
            }
        }
        override fun progress(account: String, itemId: String): WatchProgress? = null
        override fun saveProgress(account: String, item: MediaItem, position: Double, duration: Double) = Unit
        override fun clearProgress(account: String, itemId: String) = Unit
        override fun trackPreference(account: String, itemId: String): TrackPreference =
            trackPrefsByAccount[account]?.get(itemId) ?: TrackPreference()
        override fun saveTrackPreference(account: String, itemId: String, preference: TrackPreference) {
            trackPrefsByAccount.getOrPut(account) { linkedMapOf() }[itemId] = preference
        }
        override fun playlists(account: String): List<Playlist> = emptyList()
        override fun playlistItems(account: String, id: String): List<MediaItem> = emptyList()
        override fun createPlaylist(account: String, name: String): Playlist = Playlist("1", name, 0)
        override fun addToPlaylist(account: String, playlistId: String, item: MediaItem) = Unit
        override fun removeFromPlaylist(account: String, playlistId: String, itemId: String) = Unit
        override fun deletePlaylist(account: String, playlistId: String) = Unit
        override fun profiles(): List<UserProfile> = listOf(UserProfile("default", "Ana Profil", "#7C3AED", active = true))
        override fun activeProfile(): UserProfile = UserProfile("default", "Ana Profil", "#7C3AED", active = true)
        override fun createProfile(name: String, avatarColor: String, isKids: Boolean, pin: String): UserProfile =
            UserProfile("p1", name, avatarColor, isKids, pin.isNotEmpty(), false)
        override fun deleteProfile(account: String?, profileId: String) = Unit
        override fun switchProfile(account: String?, targetId: String, pin: String): UserProfile = activeProfile()
        override fun saveSeriesDetail(account: String, updated: MediaItem, episodes: List<MediaItem>, infoJson: String) = Unit
        override fun exportState(account: String): String = "{}"
        override fun importState(account: String, json: String) = Unit
    }

    private val jvmJsonParser: (InputStream) -> Any = { stream ->
        val raw = stream.bufferedReader(Charsets.UTF_8).readText().trimStart('\uFEFF', ' ', '\t', '\r', '\n')
        if (!raw.startsWith("{") && !raw.startsWith("[")) {
            throw org.json.JSONException("Expected JSON object or array")
        }
        JSONTokener(raw).nextValue()
    }

    private fun newRepo(
        accounts: AccountStore = InMemoryAccountStore(),
        catalog: CatalogStore = FakeCatalogStore(),
        client: OkHttpClient = MavieBaseHttpClient,
        streamClient: OkHttpClient = MavieStreamHttpClient,
    ): MavieRepository = MavieRepository(
        database = catalog,
        credentials = accounts,
        discoveryUpdates = MutableStateFlow(0L),
        discoverySnapshot = { JSONObject() },
        client = client,
        streamClient = streamClient,
        jsonParser = jvmJsonParser,
    )

    @Test(timeout = 20_000)
    fun streamsOver30MiBM3uFromMockWebServerInBoundedBatchesAndRejectsOver200MiB() = runBlocking {
        MockWebServer().use { server ->
            val targetBytes = 32L * 1024 * 1024
            val buffer = Buffer()
            buffer.writeUtf8("#EXTM3U url-tvg=\"http://127.0.0.1:${server.port}/epg.xml\"\n")
            var index = 0
            while (buffer.size < targetBytes) {
                buffer.writeUtf8("#EXTINF:-1 group-title=\"Sinema\",Film $index\nhttp://cdn.example.test/vod/$index.mp4\n")
                index++
            }
            server.enqueue(MockResponse().setResponseCode(200).setBody(buffer))
            server.enqueue(
                MockResponse()
                    .setResponseCode(200)
                    .setBody("#EXTM3U\n")
                    .setHeader("Content-Length", (210L * 1024 * 1024).toString()),
            )

            val catalog = FakeCatalogStore(retainItems = false)
            val accounts = InMemoryAccountStore()
            val repo = newRepo(accounts = accounts, catalog = catalog)

            val info = repo.loginM3u("Dev Liste", server.url("/get.php?username=testuser&password=testpass&type=m3u_plus").toString())
            assertEquals(SourceMode.M3U, info.sourceType)
            assertTrue("Expected >350k items, got ${catalog.committedItemCount}", catalog.committedItemCount > 350_000)
            assertTrue(catalog.batchSizes.size > 700)
            assertTrue(catalog.batchSizes.all { it <= 500 })

            try {
                repo.loginM3u("Çok Büyük", server.url("/huge.m3u").toString())
                fail("Should reject playlists above 200 MiB ceiling")
            } catch (ex: IptvException) {
                assertTrue(ex.message.orEmpty().contains("200 MB"))
            }
        }
    }

    @Test(timeout = 10_000)
    fun cleartextHttpM3uAndXtreamWithEmptyObjectCategoriesWorkCleanly() = runBlocking {
        MockWebServer().use { server ->
            val m3uBody = """
                #EXTM3U url-tvg="${server.url("/guide.xml")}"
                #EXTINF:-1 group-title="Spor",Spor Kanal 1
                http://stream.example.test/live/1.ts
                #EXTINF:-1 group-title="Filmler",Örnek Film
                http://stream.example.test/movie/2.mp4
            """.trimIndent()
            server.enqueue(MockResponse().setBody(m3uBody))

            val catalog = FakeCatalogStore()
            val accounts = InMemoryAccountStore()
            val repo = newRepo(accounts = accounts, catalog = catalog)
            val m3uUrl = server.url("/get.php?username=testuser&password=testpass&type=m3u_plus&output=mpegts").toString()
            val m3uAccount = repo.loginM3u("Test M3U", m3uUrl)
            assertEquals(2, catalog.itemsByAccount[m3uAccount.id]?.size)
            assertEquals(server.url("/guide.xml").toString(), m3uAccount.epgUrl)
            val m3uReq = server.takeRequest(2, TimeUnit.SECONDS)!!
            assertEquals("/get.php?username=testuser&password=testpass&type=m3u_plus&output=mpegts", m3uReq.path)

            server.enqueue(MockResponse().setBody("""{"user_info":{"auth":1,"status":"Active","max_connections":"2"}}"""))
            server.enqueue(MockResponse().setBody("""[{"category_id":"1","category_name":"Ulusal"}]"""))
            server.enqueue(MockResponse().setBody("""[{"stream_id":10,"name":"Kanal 10","category_id":"1"}]"""))
            server.enqueue(MockResponse().setBody("{}"))
            server.enqueue(MockResponse().setBody("{}"))
            server.enqueue(MockResponse().setBody("{}"))
            server.enqueue(MockResponse().setBody("[]"))

            val host = server.url("/").toString().trimEnd('/')
            val xtreamAccount = repo.login(ConnectionSettings(host, "testuser", "testpass"))
            assertEquals(SourceMode.XTREAM, xtreamAccount.sourceType)
            repo.refreshCatalog()
            val live = catalog.itemsByAccount[xtreamAccount.id].orEmpty().filter { it.kind == MediaKind.LIVE }
            assertEquals(1, live.size)
            assertEquals("Kanal 10", live.single().name)
        }
    }

    @Test(timeout = 10_000)
    fun follows301And302And307RedirectsForM3uAndXtream() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setResponseCode(301).setHeader("Location", "/step2"))
            server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "/step3"))
            server.enqueue(MockResponse().setResponseCode(307).setHeader("Location", "/final.m3u"))
            server.enqueue(MockResponse().setBody("#EXTM3U\n#EXTINF:-1,Kanal Redirect\nhttp://stream.example.test/r.m3u8\n"))

            val catalog = FakeCatalogStore()
            val repo = newRepo(catalog = catalog)
            val info = repo.loginM3u("Redirect", server.url("/start.m3u").toString())
            assertEquals(1, catalog.itemsByAccount[info.id]?.size)
            assertEquals(4, server.requestCount)
            val lastReq = (1..4).map { server.takeRequest(2, TimeUnit.SECONDS)!! }.last()
            assertEquals("/final.m3u", lastReq.path)
            assertEquals(MaviePrimaryUserAgent, lastReq.getHeader("User-Agent"))

            server.enqueue(MockResponse().setResponseCode(307).setHeader("Location", "/alt/player_api.php?username=testuser&password=testpass"))
            server.enqueue(MockResponse().setBody("""{"user_info":{"auth":1,"status":"Active"}}"""))
            val xtream = repo.login(ConnectionSettings(server.url("/").toString().trimEnd('/'), "testuser", "testpass"))
            assertEquals("testuser", xtream.username)
        }
    }

    @Test(timeout = 10_000)
    fun fallsBackUserAgentOn403And406AndConnectionResetAndFailsOnPersistent403() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setResponseCode(403))
            server.enqueue(MockResponse().setBody("#EXTM3U\n#EXTINF:-1,Kanal 403\nhttp://stream.example.test/403.ts\n"))

            val repo = newRepo()
            repo.loginM3u("UA 403", server.url("/list.m3u").toString())
            val req1 = server.takeRequest(2, TimeUnit.SECONDS)!!
            val req2 = server.takeRequest(2, TimeUnit.SECONDS)!!
            assertEquals(MaviePrimaryUserAgent, req1.getHeader("User-Agent"))
            assertEquals(MavieFallbackUserAgent, req2.getHeader("User-Agent"))

            server.enqueue(MockResponse().setResponseCode(406))
            server.enqueue(MockResponse().setBody("""{"user_info":{"auth":1,"status":"Active"}}"""))
            repo.login(ConnectionSettings(server.url("/").toString().trimEnd('/'), "testuser", "testpass"))
            val x1 = server.takeRequest(2, TimeUnit.SECONDS)!!
            val x2 = server.takeRequest(2, TimeUnit.SECONDS)!!
            assertEquals(MaviePrimaryUserAgent, x1.getHeader("User-Agent"))
            assertEquals(MavieFallbackUserAgent, x2.getHeader("User-Agent"))

            MockWebServer().use { resetServer ->
                val seenAgents = mutableListOf<String>()
                resetServer.dispatcher = object : okhttp3.mockwebserver.Dispatcher() {
                    override fun dispatch(request: okhttp3.mockwebserver.RecordedRequest): MockResponse {
                        val ua = request.getHeader("User-Agent").orEmpty()
                        seenAgents += ua
                        return if (ua == MaviePrimaryUserAgent) {
                            MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST)
                        } else {
                            MockResponse().setBody("#EXTM3U\n#EXTINF:-1,Kanal Reset\nhttp://stream.example.test/reset.ts\n")
                        }
                    }
                }
                val resetInfo = repo.loginM3u("UA Reset", resetServer.url("/reset.m3u").toString())
                assertEquals(SourceMode.M3U, resetInfo.sourceType)
                assertTrue(seenAgents.contains(MaviePrimaryUserAgent))
                assertEquals(MavieFallbackUserAgent, seenAgents.last())
            }

            server.enqueue(MockResponse().setResponseCode(403))
            server.enqueue(MockResponse().setResponseCode(403))
            try {
                repo.login(ConnectionSettings(server.url("/").toString().trimEnd('/'), "testuser", "testpass"))
                fail("Persistent 403 must throw IptvException")
            } catch (ex: IptvException) {
                assertTrue(ex.message.orEmpty().contains("IPTV hesabına erişim reddedildi"))
            }
        }
    }

    @Test(timeout = 15_000)
    fun classifiesTimeoutDnsConnectSslHttpErrorsWithoutSilentHttpDowngrade() = runBlocking {
        // 1. Timeout classification in both loginM3u and api()
        MockWebServer().use { server ->
            val shortTimeoutClient = MavieBaseHttpClient.newBuilder()
                .connectTimeout(1, TimeUnit.SECONDS)
                .readTimeout(400, TimeUnit.MILLISECONDS)
                .callTimeout(800, TimeUnit.MILLISECONDS)
                .build()
            val timeoutRepo = newRepo(client = shortTimeoutClient, streamClient = shortTimeoutClient)

            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            try {
                timeoutRepo.loginM3u("Timeout", server.url("/slow.m3u").toString())
                fail("Expected timeout IptvException")
            } catch (ex: IptvException) {
                assertTrue(ex.message.orEmpty().contains("zaman aşımına"))
            }

            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            try {
                timeoutRepo.login(ConnectionSettings(server.url("/").toString().trimEnd('/'), "testuser", "testpass"))
                fail("Expected timeout IptvException")
            } catch (ex: IptvException) {
                assertTrue(ex.message.orEmpty().contains("zaman aşımına"))
            }
        }

        // 2. DNS failure classification in both loginM3u and api()
        val failingDns = object : Dns {
            override fun lookup(hostname: String): List<InetAddress> = throw UnknownHostException("unreachable.invalid")
        }
        val dnsClient = MavieBaseHttpClient.newBuilder().dns(failingDns).build()
        val dnsRepo = newRepo(client = dnsClient, streamClient = dnsClient)
        try {
            dnsRepo.loginM3u("DNS", "http://unreachable.invalid/list.m3u")
            fail("Expected DNS IptvException")
        } catch (ex: IptvException) {
            assertTrue(ex.message.orEmpty().contains("DNS hatası"))
        }
        try {
            dnsRepo.login(ConnectionSettings("http://unreachable.invalid", "testuser", "testpass"))
            fail("Expected DNS IptvException")
        } catch (ex: IptvException) {
            assertTrue(ex.message.orEmpty().contains("DNS hatası"))
        }

        // 3. ConnectException (refused port) classification
        val closedPort = MockWebServer().use { it.port }
        val connRepo = newRepo()
        try {
            connRepo.loginM3u("Refused", "http://127.0.0.1:$closedPort/list.m3u")
            fail("Expected ConnectException IptvException")
        } catch (ex: IptvException) {
            assertTrue(ex.message.orEmpty().contains("bağlantı reddedildi"))
        }
        try {
            connRepo.login(ConnectionSettings("http://127.0.0.1:$closedPort", "testuser", "testpass"))
            fail("Expected ConnectException IptvException")
        } catch (ex: IptvException) {
            assertTrue(ex.message.orEmpty().contains("bağlantı reddedildi"))
        }

        // 4. SSL classification on both non-443 and 443 ports (never silently downgrades https -> http)
        MockWebServer().use { server ->
            val sslFailFactory = object : SSLSocketFactory() {
                override fun getDefaultCipherSuites(): Array<String> = emptyArray()
                override fun getSupportedCipherSuites(): Array<String> = emptyArray()
                override fun createSocket(s: Socket?, host: String?, port: Int, autoClose: Boolean): Socket =
                    throw SSLHandshakeException("TLS failure")
                override fun createSocket(host: String?, port: Int): Socket = throw SSLHandshakeException("TLS failure")
                override fun createSocket(host: String?, port: Int, localHost: InetAddress?, localPort: Int): Socket =
                    throw SSLHandshakeException("TLS failure")
                override fun createSocket(host: InetAddress?, port: Int): Socket = throw SSLHandshakeException("TLS failure")
                override fun createSocket(address: InetAddress?, port: Int, localAddress: InetAddress?, localPort: Int): Socket =
                    throw SSLHandshakeException("TLS failure")
            }
            val portRedirectSocketFactory = object : javax.net.SocketFactory() {
                private fun mapPort(port: Int): Int = if (port == 443) server.port else port
                override fun createSocket(): Socket = object : Socket() {
                    override fun connect(endpoint: java.net.SocketAddress?, timeout: Int) {
                        val inet = endpoint as? java.net.InetSocketAddress
                        val mapped = if (inet != null && inet.port == 443) {
                            java.net.InetSocketAddress(inet.address ?: InetAddress.getByName("127.0.0.1"), server.port)
                        } else {
                            endpoint
                        }
                        super.connect(mapped, timeout)
                    }
                }
                override fun createSocket(host: String?, port: Int): Socket = Socket("127.0.0.1", mapPort(port))
                override fun createSocket(host: String?, port: Int, localHost: InetAddress?, localPort: Int): Socket =
                    Socket("127.0.0.1", mapPort(port), localHost, localPort)
                override fun createSocket(host: InetAddress?, port: Int): Socket = Socket(host, mapPort(port))
                override fun createSocket(address: InetAddress?, port: Int, localAddress: InetAddress?, localPort: Int): Socket =
                    Socket(address, mapPort(port), localAddress, localPort)
            }
            val sslClient = MavieBaseHttpClient.newBuilder()
                .dns(object : Dns {
                    override fun lookup(hostname: String): List<InetAddress> = listOf(InetAddress.getByName("127.0.0.1"))
                })
                .socketFactory(portRedirectSocketFactory)
                .sslSocketFactory(sslFailFactory, object : javax.net.ssl.X509TrustManager {
                    override fun checkClientTrusted(chain: Array<java.security.cert.X509Certificate>?, authType: String?) = Unit
                    override fun checkServerTrusted(chain: Array<java.security.cert.X509Certificate>?, authType: String?) = Unit
                    override fun getAcceptedIssuers(): Array<java.security.cert.X509Certificate> = emptyArray()
                })
                .build()
            val sslRepo = newRepo(client = sslClient, streamClient = sslClient)

            // Non-443 https -> must NOT silently downgrade to http://; classifies TLS_FAILED with 0 HTTP requests sent
            try {
                sslRepo.loginM3u("No Downgrade M3U", "https://127.0.0.1:${server.port}/get.php?username=testuser&password=testpass")
                fail("Non-443 HTTPS must not silently downgrade to HTTP")
            } catch (ex: IptvException) {
                assertEquals(MavieErrorCode.TLS_FAILED, ex.code)
                assertTrue(ex.message.orEmpty().contains("TLS/SSL"))
            }

            try {
                sslRepo.login(ConnectionSettings("https://127.0.0.1:${server.port}", "testuser", "testpass"))
                fail("Non-443 HTTPS must not silently downgrade to HTTP")
            } catch (ex: IptvException) {
                assertEquals(MavieErrorCode.TLS_FAILED, ex.code)
                assertTrue(ex.message.orEmpty().contains("TLS/SSL"))
            }
            assertEquals(0, server.requestCount)

            // Port 443 https -> never downgrades, classifies SSL error
            try {
                sslRepo.loginM3u("Strict 443", "https://strict.example.test:443/list.m3u")
                fail("Port 443 must not fall back to HTTP")
            } catch (ex: IptvException) {
                assertEquals(MavieErrorCode.TLS_FAILED, ex.code)
                assertTrue(ex.message.orEmpty().contains("TLS/SSL"))
            }
            try {
                sslRepo.login(ConnectionSettings("https://strict.example.test:443", "testuser", "testpass"))
                fail("Port 443 must not fall back to HTTP")
            } catch (ex: IptvException) {
                assertEquals(MavieErrorCode.TLS_FAILED, ex.code)
                assertTrue(ex.message.orEmpty().contains("TLS/SSL"))
            }

            // 5. HTTP 401, 404, 502, and invalid HTML 200 body
            server.enqueue(MockResponse().setResponseCode(401))
            try {
                connRepo.loginM3u("401", server.url("/401.m3u").toString())
                fail()
            } catch (ex: IptvException) {
                assertTrue(ex.message.orEmpty().contains("401"))
            }

            server.enqueue(MockResponse().setResponseCode(404))
            try {
                connRepo.login(ConnectionSettings(server.url("/").toString().trimEnd('/'), "testuser", "testpass"))
                fail()
            } catch (ex: IptvException) {
                assertTrue(ex.message.orEmpty().contains("404"))
            }

            server.enqueue(MockResponse().setResponseCode(502))
            try {
                connRepo.loginM3u("502", server.url("/502.m3u").toString())
                fail()
            } catch (ex: IptvException) {
                assertTrue(ex.message.orEmpty().contains("502"))
            }

            server.enqueue(MockResponse().setResponseCode(200).setBody("<html><body>Bad Gateway</body></html>"))
            try {
                connRepo.login(ConnectionSettings(server.url("/").toString().trimEnd('/'), "testuser", "testpass"))
                fail()
            } catch (ex: IptvException) {
                assertTrue(ex.message.orEmpty().contains("geçerli bir yanıt"))
            }
        }
    }

    @Test(timeout = 10_000)
    fun refreshCatalogPreservesExistingItemsOnEmptyOrHtmlAndUpdatesEpgUrlOnValidM3u() = runBlocking {
        MockWebServer().use { server ->
            val initialM3u = "#EXTM3U\n#EXTINF:-1 group-title=\"Spor\",Kanal Bir\nhttp://stream.example.test/1.ts\n"
            server.enqueue(MockResponse().setBody(initialM3u))
            val catalog = FakeCatalogStore()
            val accounts = InMemoryAccountStore()
            val repo = newRepo(accounts = accounts, catalog = catalog)

            val account = repo.loginM3u("Canlı", server.url("/playlist.m3u").toString())
            assertEquals("", account.epgUrl)
            assertEquals(1, catalog.itemsByAccount[account.id]?.size)

            // 1. HTML error 200 must NOT wipe existing catalog
            server.enqueue(MockResponse().setResponseCode(200).setBody("<html>502 Maintenance</html>"))
            try {
                repo.refreshCatalog()
                fail("HTML response must throw IptvException")
            } catch (_: IptvException) {
            }
            assertEquals(1, catalog.itemsByAccount[account.id]?.size)
            assertEquals("Kanal Bir", catalog.itemsByAccount[account.id]?.single()?.name)

            // 2. Empty #EXTM3U must NOT wipe existing catalog
            server.enqueue(MockResponse().setResponseCode(200).setBody("#EXTM3U\n"))
            try {
                repo.refreshCatalog()
                fail("Empty M3U must throw IptvException")
            } catch (_: IptvException) {
            }
            assertEquals(1, catalog.itemsByAccount[account.id]?.size)

            // 3. Valid updated M3U with new url-tvg updates catalog AND saved epgUrl
            val newEpg = server.url("/new.xml").toString()
            val updatedM3u = """
                #EXTM3U url-tvg="$newEpg"
                #EXTINF:-1 group-title="Spor",Kanal İki
                http://stream.example.test/2.ts
                #EXTINF:-1 group-title="Sinema",Film Üç
                http://stream.example.test/3.mp4
            """.trimIndent()
            server.enqueue(MockResponse().setResponseCode(200).setBody(updatedM3u))
            repo.refreshCatalog()
            assertEquals(2, catalog.itemsByAccount[account.id]?.size)
            assertEquals(newEpg, repo.account.value?.epgUrl)
            assertEquals(newEpg, accounts.stored?.settings?.epgUrl)
        }
    }

    @Test(timeout = 10_000)
    fun blocksRedirectSsrfCrossHostCredentialRedirectsAndHttpsDowngrades() = runBlocking {
        MockWebServer().use { server ->
            val repo = newRepo()

            // 1. Credentialed URL redirecting to a different host -> UNSAFE_URL
            server.enqueue(
                MockResponse()
                    .setResponseCode(302)
                    .setHeader("Location", "http://evil.example.test/steal.m3u"),
            )
            try {
                repo.loginM3u("CrossHost", server.url("/get.php?username=demo_user&password=demo_pass").toString())
                fail("Cross-host credential redirect must be rejected")
            } catch (ex: IptvException) {
                assertEquals(MavieErrorCode.UNSAFE_URL, ex.code)
            }

            // 2. Redirect to cloud metadata IP -> UNSAFE_URL
            server.enqueue(
                MockResponse()
                    .setResponseCode(302)
                    .setHeader("Location", "http://169.254.169.254/latest/meta-data/"),
            )
            try {
                repo.loginM3u("MetadataRedirect", server.url("/list.m3u").toString())
                fail("Metadata redirect must be rejected")
            } catch (ex: IptvException) {
                assertEquals(MavieErrorCode.UNSAFE_URL, ex.code)
            }

            // 3. Redirect to non-HTTP scheme -> UNSAFE_URL
            server.enqueue(
                MockResponse()
                    .setResponseCode(302)
                    .setHeader("Location", "file:///etc/passwd"),
            )
            try {
                repo.loginM3u("SchemeRedirect", server.url("/list.m3u").toString())
                fail("Non-HTTP redirect must be rejected")
            } catch (ex: IptvException) {
                assertEquals(MavieErrorCode.UNSAFE_URL, ex.code)
            }

            // 4. Initial cloud metadata URL -> UNSAFE_URL without network call
            try {
                repo.loginM3u("DirectMetadata", "http://169.254.169.254/list.m3u")
                fail("Direct metadata URL must be rejected")
            } catch (ex: IptvException) {
                assertEquals(MavieErrorCode.UNSAFE_URL, ex.code)
            }

            // 5. Direct validateRedirectHop: https -> http downgrade on credentialed URL -> TLS_FAILED
            try {
                repo.validateRedirectHop(
                    "https://cdn.example.test/get.php?username=demo_user&password=demo_pass".toHttpUrl(),
                    "http://cdn.example.test/get.php?username=demo_user&password=demo_pass",
                )
                fail("HTTPS->HTTP credential redirect must throw TLS_FAILED")
            } catch (ex: IptvException) {
                assertEquals(MavieErrorCode.TLS_FAILED, ex.code)
            }

            // Same-host HTTPS -> HTTPS redirect is allowed
            val safeHop = repo.validateRedirectHop(
                "https://cdn.example.test/start.m3u?username=demo_user&password=demo_pass".toHttpUrl(),
                "https://cdn.example.test/final.m3u?username=demo_user&password=demo_pass",
            )
            assertEquals("https://cdn.example.test/final.m3u?username=demo_user&password=demo_pass", safeHop.toString())
        }
    }

    @Test(timeout = 10_000)
    fun mapsHttpStatusAndInvalidResponsesToStructuredMavieErrorCodes() = runBlocking {
        MockWebServer().use { server ->
            val repo = newRepo()
            val cases = listOf(
                401 to MavieErrorCode.AUTH_REJECTED,
                403 to MavieErrorCode.AUTH_REJECTED,
                404 to MavieErrorCode.NOT_FOUND,
                429 to MavieErrorCode.RATE_LIMITED,
                502 to MavieErrorCode.SERVER_ERROR,
                418 to MavieErrorCode.HTTP_ERROR,
            )
            for ((status, expectedCode) in cases) {
                server.enqueue(MockResponse().setResponseCode(status))
                if (status == 403) server.enqueue(MockResponse().setResponseCode(403))
                try {
                    repo.loginM3u("Status $status", server.url("/status_$status.m3u").toString())
                    fail("Expected IptvException for HTTP $status")
                } catch (ex: IptvException) {
                    assertEquals("HTTP $status code mismatch", expectedCode, ex.code)
                }
            }

            server.enqueue(MockResponse().setResponseCode(200).setBody("<html>Not JSON</html>"))
            try {
                repo.login(ConnectionSettings(server.url("/").toString().trimEnd('/'), "testuser", "testpass"))
                fail("Expected INVALID_RESPONSE for HTML")
            } catch (ex: IptvException) {
                assertEquals(MavieErrorCode.INVALID_RESPONSE, ex.code)
            }
        }
    }

    @Test(timeout = 10_000)
    fun homeCachesDiscoveryByKeyAndInvalidatesOnHistoryOrFeedChanges() = runBlocking {
        val catalog = FakeCatalogStore()
        val updates = MutableStateFlow(1L)
        var feedUpdatedAt = 100.0
        val repo = MavieRepository(
            database = catalog,
            credentials = InMemoryAccountStore(),
            discoveryUpdates = updates,
            discoverySnapshot = { JSONObject().put("updatedAt", feedUpdatedAt) },
            jsonParser = jvmJsonParser,
        )
        repo.loginDemo()
        val firstItem = catalog.itemsByAccount.values.first().first()

        // First home() computes discovery once
        repo.home()
        assertEquals(1, catalog.discoveryCatalogQueryCount)

        // Second home() with identical versions/feed hits cache
        repo.home()
        assertEquals(1, catalog.discoveryCatalogQueryCount)

        // Toggling favorite bumps historyVersion -> invalidates cache
        repo.toggleFavorite(firstItem)
        repo.home()
        assertEquals(2, catalog.discoveryCatalogQueryCount)

        // Bumping discoveryUpdates invalidates cache
        updates.value = 2L
        repo.home()
        assertEquals(3, catalog.discoveryCatalogQueryCount)

        // Changing feed updatedAt invalidates cache
        feedUpdatedAt = 200.0
        repo.home()
        assertEquals(4, catalog.discoveryCatalogQueryCount)
    }

    @Test(timeout = 10_000)
    fun updateEpgUrlValidatesSchemesBlocksMetadataAndPersistsCleanUrl() = runBlocking {
        val accounts = InMemoryAccountStore()
        val repo = newRepo(accounts = accounts)
        repo.loginDemo()

        val updated = repo.updateEpgUrl("  https://epg.example.test/guide.xml  ")
        assertEquals("https://epg.example.test/guide.xml", updated.epgUrl)
        assertEquals("https://epg.example.test/guide.xml", repo.account.value?.epgUrl)
        assertEquals("https://epg.example.test/guide.xml", accounts.stored?.settings?.epgUrl)

        val cleared = repo.updateEpgUrl("   ")
        assertEquals("", cleared.epgUrl)

        try {
            repo.updateEpgUrl("http://169.254.169.254/epg.xml")
            fail("Metadata EPG URL must be rejected")
        } catch (ex: IptvException) {
            assertEquals(MavieErrorCode.UNSAFE_URL, ex.code)
        }

        try {
            repo.updateEpgUrl("ftp://epg.example.test/guide.xml")
            fail("FTP EPG URL must be rejected")
        } catch (ex: IptvException) {
            assertEquals(MavieErrorCode.INVALID_INPUT, ex.code)
        }
    }

    @Test(timeout = 10_000)
    fun saveTrackPreferenceIgnoresStaleProfileWrites() = runBlocking {
        val catalog = FakeCatalogStore()
        val repo = newRepo(catalog = catalog)
        repo.loginDemo()

        repo.saveTrackPreference("vod:1", TrackPreference(audioId = 2, subtitleId = 5, subtitleOff = false), expectedProfileId = "stale_profile")
        assertEquals(TrackPreference(), repo.trackPreference("vod:1"))

        repo.saveTrackPreference("vod:1", TrackPreference(audioId = 2, subtitleId = 5, subtitleOff = false), expectedProfileId = "default")
        assertEquals(TrackPreference(audioId = 2, subtitleId = 5, subtitleOff = false), repo.trackPreference("vod:1"))
    }
}
