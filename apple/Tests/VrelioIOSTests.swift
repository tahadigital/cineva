import XCTest
@testable import VrelioIOS

final class VrelioIOSTests: XCTestCase {

    func testDemoCatalogHasFourOpenFilms() {
        XCTAssertEqual(DemoCatalog.items.count, 4)
        XCTAssertTrue(DemoCatalog.items.allSatisfy { item in
            item.kind == .vod &&
            [item.poster, item.backdrop, item.sourceUrl].allSatisfy {
                $0.hasPrefix("https://") && !$0.contains("storage.googleapis.com")
            }
        })
        XCTAssertTrue(DemoCatalog.items.contains { $0.id == "vod:demo_bbb" })
        XCTAssertTrue(DemoCatalog.items.contains { $0.id == "vod:demo_sintel" })
        XCTAssertTrue(DemoCatalog.items.contains { $0.id == "vod:demo_tears" })
        XCTAssertTrue(DemoCatalog.items.contains { $0.id == "vod:demo_elephants" })
    }

    func testM3uParserExtractsEpgGroupsAndVodVsLive() {
        let playlist = """
        #EXTM3U url-tvg="https://epg.example.com/guide.xml"
        #EXTINF:-1 tvg-id="trt1.tr" tvg-logo="https://img.example.com/trt1.png" group-title="Ulusal",TRT 1 HD
        https://stream.example.com/live/trt1.m3u8
        #EXTINF:-1 group-title="Sinema" type="movie",Açık Film
        https://cdn.example.com/movies/film.mp4
        """
        let parsed = M3uParser.parse(playlist)
        XCTAssertEqual(parsed.epgUrl, "https://epg.example.com/guide.xml")
        XCTAssertEqual(parsed.items.count, 2)
        XCTAssertEqual(parsed.items[0].kind, .live)
        XCTAssertEqual(parsed.items[0].categoryName, "Ulusal")
        XCTAssertEqual(parsed.items[0].tvgId, "trt1.tr")
        XCTAssertEqual(parsed.items[1].kind, .vod)
        XCTAssertEqual(parsed.items[1].extensionName, "mp4")
        XCTAssertEqual(parsed.categories.count, 2)
    }

    func testXtreamParserDecodesCategoriesStreamsAndEpisodes() throws {
        let catJSON = """
        [{"category_id":"10","category_name":"Aksiyon"},{"category_id":"20","category_name":"Belgesel"}]
        """.data(using: .utf8)!
        let cats = try XtreamClient.parseCategories(data: catJSON, kind: .vod)
        XCTAssertEqual(cats.count, 2)
        XCTAssertEqual(cats[0].name, "Aksiyon")

        let streamsJSON = """
        [{"stream_id":101,"name":"Örnek Film (2024)","category_id":"10","container_extension":"mp4","rating":"8.4","stream_icon":"https://img.example.com/101.jpg"}]
        """.data(using: .utf8)!
        let items = try XtreamClient.parseStreams(data: streamsJSON, kind: .vod, categories: ["10": "Aksiyon"])
        XCTAssertEqual(items.count, 1)
        XCTAssertEqual(items[0].id, "vod:101")
        XCTAssertEqual(items[0].year, "2024")
        XCTAssertEqual(items[0].categoryName, "Aksiyon")

        let series = MediaItem(id: "series:55", providerId: "55", name: "Örnek Dizi", kind: .series)
        let seriesInfoJSON = """
        {
          "info":{"plot":"Dizi özeti","genre":"Drama","cast":"Oyuncu A"},
          "episodes":{
            "1":[{"id":"901","episode_num":1,"title":"Pilot","container_extension":"mp4"}],
            "2":[{"id":"902","episode_num":1,"title":"Yeni Sezon","container_extension":"mp4"}]
          }
        }
        """.data(using: .utf8)!
        let detail = try XtreamClient.parseSeriesDetail(data: seriesInfoJSON, series: series)
        XCTAssertEqual(detail.seasons.count, 2)
        XCTAssertEqual(detail.seasons[0].episodes.first?.id, "episode:901")
        XCTAssertEqual(detail.seasons[1].episodes.first?.id, "episode:902")
    }

    func testFollowingEpisodeAdvancesAcrossSeasons() {
        let series = MediaItem(id: "series:7", providerId: "7", name: "Dizi", kind: .series)
        let ep1 = MediaItem(id: "episode:1", providerId: "1", name: "Bölüm 1", kind: .episode, season: 1, episode: 1, parentId: series.id)
        let ep2 = MediaItem(id: "episode:2", providerId: "2", name: "Bölüm 2", kind: .episode, season: 2, episode: 1, parentId: series.id)
        let detail = MediaDetail(
            item: series,
            seasons: [
                Season(number: 1, name: "1. Sezon", episodes: [ep1]),
                Season(number: 2, name: "2. Sezon", episodes: [ep2]),
            ]
        )
        let next = detail.followingEpisode(after: ep1)
        XCTAssertEqual(next?.id, ep2.id)
        XCTAssertNil(detail.followingEpisode(after: ep2))
    }

    func testCloudUrlValidatorNormalizesAndRejectsCredentials() throws {
        XCTAssertEqual(CloudClient.defaultPortalURL, "https://cineva-app.netlify.app")
        let validated = try CloudClient.validateBaseURL("https://cineva-app.netlify.app/")
        XCTAssertEqual(validated.absoluteString, "https://cineva-app.netlify.app")

        let localHttp = try CloudClient.validateBaseURL("http://127.0.0.1:8899/")
        XCTAssertEqual(localHttp.absoluteString, "http://127.0.0.1:8899")

        XCTAssertThrowsError(try CloudClient.validateBaseURL("http://example.com"))
        XCTAssertThrowsError(try CloudClient.validateBaseURL("https://user:pass@cineva-app.netlify.app"))
        XCTAssertThrowsError(try CloudClient.validateBaseURL("https://cineva-app.netlify.app?foo=bar"))
    }

    func testCloudUserDecodingNormalVsProTrialState() throws {
        let proTrialJSON = """
        {
          "id":"usr_1",
          "email":"test@vrelio.app",
          "displayName":"Taha",
          "role":"user",
          "emailVerified":true,
          "verifiedAt":"2026-11-19T00:00:00Z",
          "plan":"pro",
          "effectivePlan":"pro",
          "isPro":true,
          "trialActive":true,
          "trialUsed":true,
          "trialStartedAt":"2026-11-19T00:00:00Z",
          "trialEndsAt":"2026-11-22T00:00:00Z",
          "status":"active",
          "maxDevices":5,
          "expiresAt":"2026-11-22T00:00:00Z",
          "adminNote":"",
          "createdAt":"2026-11-19T00:00:00Z",
          "lastSeenAt":"2026-11-19T00:00:00Z",
          "features":{
            "cloudSync":true,
            "multiView":true,
            "unlimitedProfiles":true,
            "epgMatch":true,
            "advancedTracks":true,
            "maxDevices":5
          }
        }
        """.data(using: .utf8)!
        let user = try JSONDecoder().decode(CloudUser.self, from: proTrialJSON)
        XCTAssertTrue(user.isPro)
        XCTAssertTrue(user.trialActive)
        XCTAssertEqual(user.maxDevices, 5)
        XCTAssertTrue(user.features.cloudSync)
        let refNow = VrelioDateParser.parseISO8601("2026-11-19T12:00:00Z")!
        XCTAssertNotNil(user.trialRemainingSummary(now: refNow))
    }

    func testCloudApiErrorDecodingEmailNotVerifiedAndProRequired() {
        let verifyErrData = """
        {"error":"E-posta doğrulaması gerekli.","code":"EMAIL_NOT_VERIFIED","verificationRequired":true,"email":"a@b.com"}
        """.data(using: .utf8)!
        let verifyErr = CloudClient.decodeApiError(status: 403, data: verifyErrData)
        XCTAssertEqual(verifyErr.code, "EMAIL_NOT_VERIFIED")
        XCTAssertTrue(verifyErr.verificationRequired)
        XCTAssertEqual(verifyErr.email, "a@b.com")

        let proErrData = """
        {"error":"Bu özellik Pro plan gerektirir.","code":"PRO_REQUIRED","upgradeRequired":true}
        """.data(using: .utf8)!
        let proErr = CloudClient.decodeApiError(status: 403, data: proErrData)
        XCTAssertEqual(proErr.code, "PRO_REQUIRED")
        XCTAssertTrue(proErr.upgradeRequired)
    }

    func testLanSyncRejectsPublicHostsAndUserinfo() throws {
        let okLan = try LanSyncClient.validateLanAddress("192.168.1.42:8844")
        XCTAssertEqual(okLan.absoluteString, "http://192.168.1.42:8844")

        let okLocalhost = try LanSyncClient.validateLanAddress("http://localhost:8844")
        XCTAssertEqual(okLocalhost.absoluteString, "http://localhost:8844")

        XCTAssertThrowsError(try LanSyncClient.validateLanAddress("8.8.8.8:8844"))
        XCTAssertThrowsError(try LanSyncClient.validateLanAddress("http://user:pass@192.168.1.42:8844"))
        XCTAssertThrowsError(try LanSyncClient.validatePairingCode("12ab"))
        XCTAssertEqual(try LanSyncClient.validatePairingCode("123456"), "123456")
    }

    @MainActor
    func testLibraryStorePlanGatingBlocksCloudSyncAndExtraProfilesOnNormal() async throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("vrelio_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let store = LibraryStore(storageDirectory: tmpDir, useKeychain: false)
        let normalUser = CloudUser(
            id: "u1",
            email: "normal@vrelio.app",
            displayName: "Normal",
            emailVerified: true,
            plan: "normal",
            effectivePlan: "normal",
            isPro: false,
            maxDevices: 1,
            features: CloudPlanFeatures(cloudSync: false, unlimitedProfiles: false, maxDevices: 1)
        )
        store.setMockCloudSessionForTesting(user: normalUser, token: "tok_normal")
        XCTAssertFalse(store.canUseCloudSync)
        XCTAssertFalse(store.canAddAnotherProfile)

        XCTAssertThrowsError(try store.addProfile(name: "İkinci Profil")) { err in
            guard case VrelioError.proRequired = err else {
                return XCTFail("Expected proRequired, got \(err)")
            }
        }

        do {
            try await store.syncWithCloud()
            XCTFail("Expected syncWithCloud to throw proRequired for Normal user")
        } catch VrelioError.proRequired {
            // Expected
        }

        let proUser = CloudUser(
            id: "u2",
            email: "pro@vrelio.app",
            displayName: "Pro",
            emailVerified: true,
            plan: "pro",
            effectivePlan: "pro",
            isPro: true,
            maxDevices: 5,
            features: CloudPlanFeatures(cloudSync: true, unlimitedProfiles: true, maxDevices: 5)
        )
        store.setMockCloudSessionForTesting(user: proUser, token: "tok_pro")
        XCTAssertTrue(store.canUseCloudSync)
        XCTAssertTrue(store.canAddAnotherProfile)
        let added = try store.addProfile(name: "Çocuk", isKids: true, pin: "1234")
        XCTAssertTrue(added.hasPin)
    }

    @MainActor
    func testLibraryStoreTracksProgressAndFavorites() {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("vrelio_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let store = LibraryStore(storageDirectory: tmpDir, useKeychain: false)
        let item = DemoCatalog.items[0]
        XCTAssertFalse(store.isFavorite(item))
        store.toggleFavorite(item)
        XCTAssertTrue(store.isFavorite(item))

        store.saveProgress(itemId: item.id, positionSeconds: 120, durationSeconds: 600)
        XCTAssertEqual(store.continueWatchingItems.first?.id, item.id)
        XCTAssertFalse(store.progress(for: item)?.completed ?? true)

        store.saveProgress(itemId: item.id, positionSeconds: 570, durationSeconds: 600)
        XCTAssertTrue(store.progress(for: item)?.completed ?? false)
        XCTAssertTrue(store.continueWatchingItems.isEmpty)
    }

    @MainActor
    func testLibraryStoreTurkishFoldedSearchAndBackupRoundTrip() throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("vrelio_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let store = LibraryStore(storageDirectory: tmpDir, useKeychain: false)
        store.importM3uText("""
        #EXTM3U
        #EXTINF:-1 group-title="Belgesel",İstanbul Şehir Rehberi
        https://cdn.example.com/istanbul.mp4
        """)
        let found = store.searchItems(query: "istanbul sehir")
        XCTAssertEqual(found.count, 1)
        XCTAssertEqual(found.first?.name, "İstanbul Şehir Rehberi")

        store.toggleFavorite(found[0])
        let backup = try store.exportBackupJSON()

        let tmpDir2 = FileManager.default.temporaryDirectory.appendingPathComponent("vrelio_test2_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir2) }
        let restored = LibraryStore(storageDirectory: tmpDir2, useKeychain: false)
        try restored.importBackupJSON(backup)
        XCTAssertTrue(restored.isFavorite(found[0]))
    }

    func testXtreamStreamUrlBuilderGeneratesExpectedPaths() throws {
        let live = MediaItem(id: "live:42", providerId: "42", name: "Kanal", kind: .live, extensionName: "ts")
        let liveURL = try XtreamClient.buildStreamURL(host: "http://panel.local:8080", username: "ali", password: "123", item: live, preferHLSForLive: true)
        XCTAssertEqual(liveURL.absoluteString, "http://panel.local:8080/live/ali/123/42.m3u8")

        let vod = MediaItem(id: "vod:99", providerId: "99", name: "Film", kind: .vod, extensionName: "mp4")
        let vodURL = try XtreamClient.buildStreamURL(host: "http://panel.local:8080", username: "ali", password: "123", item: vod)
        XCTAssertEqual(vodURL.absoluteString, "http://panel.local:8080/movie/ali/123/99.mp4")
    }

    @MainActor
    func testServerPyV1ExportDecodeAndCanonicalReEncode() throws {
        let serverExportFixture = """
        {
          "version": 1,
          "exportedAt": "2026-11-19T04:41:55.654122+00:00",
          "favorites": [
            {"item_id": "vod:demo_bbb", "created_at": "2026-11-19T04:41:55.631440+00:00"}
          ],
          "progress": [
            {"item_id": "vod:demo_bbb", "position": 120.0, "duration": 596.0, "completed": 0, "updated_at": "2026-11-19T04:41:55.643564+00:00"}
          ],
          "playlists": [
            {"id": "m0LVaBAITrp2zwbQ", "name": "Mac Liste", "created_at": "2026-11-19T04:41:55.654122+00:00"}
          ],
          "playlistItems": [
            {"playlist_id": "m0LVaBAITrp2zwbQ", "item_id": "vod:demo_bbb", "position": 0}
          ],
          "trackPreferences": [
            {"item_id": "vod:demo_bbb", "data": "{\\"audio\\": \\"auto\\", \\"subtitle\\": \\"off\\", \\"clientAudio\\": null, \\"clientSubtitle\\": null}", "updated_at": "2026-11-19T04:41:55.654122+00:00"}
          ],
          "items": [
            {
              "id": "vod:demo_bbb",
              "providerId": "demo_bbb",
              "name": "Big Buck Bunny (Demo · 1080p)",
              "kind": "vod",
              "categoryId": "demo_anim",
              "categoryName": "Açık Sinema / Demo",
              "poster": "https://peach.blender.org/wp-content/uploads/poster_bunny_small.jpg",
              "backdrop": "https://peach.blender.org/wp-content/uploads/poster_bunny_small.jpg",
              "year": "2008",
              "rating": 8.2,
              "extension": "mp4",
              "durationSeconds": 596.0,
              "plot": "Açık kaynaklı film.",
              "season": 0,
              "episode": 0,
              "parentId": null,
              "addedAt": 4,
              "videoCodec": "",
              "audioCodec": ""
            }
          ]
        }
        """.data(using: .utf8)!

        let decodedPayload = try JSONDecoder().decode(CloudSyncPayload.self, from: serverExportFixture)
        XCTAssertEqual(decodedPayload.version, 1)
        XCTAssertEqual(decodedPayload.favorites.map(\.itemId), ["vod:demo_bbb"])
        XCTAssertEqual(decodedPayload.progress.first?.itemId, "vod:demo_bbb")
        XCTAssertEqual(decodedPayload.progress.first?.positionSeconds, 120.0)
        XCTAssertEqual(decodedPayload.progress.first?.completed, false)
        XCTAssertEqual(decodedPayload.playlists.first?.id, "m0LVaBAITrp2zwbQ")
        XCTAssertEqual(decodedPayload.playlists.first?.itemIds, ["vod:demo_bbb"])
        XCTAssertEqual(decodedPayload.trackPreferences.first?.data.audio, "auto")
        XCTAssertEqual(decodedPayload.items.first?.providerId, "demo_bbb")

        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("vrelio_v1_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }
        let store = LibraryStore(storageDirectory: tmpDir, useKeychain: false)
        try store.importBackupJSON(serverExportFixture)

        XCTAssertTrue(store.favoriteIds.contains("vod:demo_bbb"))
        XCTAssertEqual(store.progressByItem["vod:demo_bbb"]?.positionSeconds, 120.0)
        XCTAssertEqual(store.playlists.first(where: { $0.id == "m0LVaBAITrp2zwbQ" })?.itemIds, ["vod:demo_bbb"])

        let exportedData = try store.exportBackupJSON()
        let exportedJSON = try XCTUnwrap(try JSONSerialization.jsonObject(with: exportedData) as? [String: Any])
        XCTAssertEqual(exportedJSON["version"] as? Int, 1)
        XCTAssertNotNil(exportedJSON["exportedAt"] as? String)

        let favRows = try XCTUnwrap(exportedJSON["favorites"] as? [[String: Any]])
        XCTAssertEqual(favRows.first?["item_id"] as? String, "vod:demo_bbb")
        XCTAssertNotNil(favRows.first?["created_at"] as? String)

        let progRows = try XCTUnwrap(exportedJSON["progress"] as? [[String: Any]])
        XCTAssertEqual(progRows.first?["item_id"] as? String, "vod:demo_bbb")
        XCTAssertEqual(progRows.first?["position"] as? Double, 120.0)
        XCTAssertEqual(progRows.first?["duration"] as? Double, 596.0)
        XCTAssertNotNil(progRows.first?["updated_at"] as? String)

        let plRows = try XCTUnwrap(exportedJSON["playlists"] as? [[String: Any]])
        let macList = try XCTUnwrap(plRows.first { ($0["id"] as? String) == "m0LVaBAITrp2zwbQ" })
        XCTAssertNotNil(macList["created_at"] as? String)
        XCTAssertNil(macList["itemIds"])

        let plItemRows = try XCTUnwrap(exportedJSON["playlistItems"] as? [[String: Any]])
        XCTAssertTrue(plItemRows.contains {
            ($0["playlist_id"] as? String) == "m0LVaBAITrp2zwbQ" && ($0["item_id"] as? String) == "vod:demo_bbb"
        })

        let itemRows = try XCTUnwrap(exportedJSON["items"] as? [[String: Any]])
        let bbbRow = try XCTUnwrap(itemRows.first { ($0["id"] as? String) == "vod:demo_bbb" })
        XCTAssertEqual(bbbRow["providerId"] as? String, "demo_bbb")
        XCTAssertEqual(bbbRow["categoryId"] as? String, "demo_anim")
        XCTAssertEqual(bbbRow["categoryName"] as? String, "Açık Sinema / Demo")
    }

    @MainActor
    func testPullThenMergeThenPushInSyncWithCloud() async throws {
        MockCloudSyncURLProtocol.reset(remoteStateJSON: """
        {
          "state": {
            "version": 1,
            "exportedAt": "2026-11-19T05:00:00Z",
            "favorites": [{"item_id": "vod:demo_bbb", "created_at": "2026-11-19T05:00:00Z"}],
            "progress": [{"item_id": "vod:demo_bbb", "position": 180.0, "duration": 596.0, "completed": 0, "updated_at": "2026-11-19T05:00:00Z"}],
            "playlists": [{"id": "pl_remote", "name": "Uzak Liste", "created_at": "2026-11-19T05:00:00Z"}],
            "playlistItems": [{"playlist_id": "pl_remote", "item_id": "vod:demo_bbb", "position": 0}],
            "trackPreferences": [],
            "items": []
          },
          "updatedAt": "2026-11-19T05:00:00Z"
        }
        """)

        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [MockCloudSyncURLProtocol.self]
        let mockSession = URLSession(configuration: cfg)
        let client = CloudClient(session: mockSession)

        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("vrelio_sync_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let store = LibraryStore(storageDirectory: tmpDir, cloudClient: client, useKeychain: false)
        store.portalURL = "http://127.0.0.1:19999"
        let proUser = CloudUser(
            id: "u_pro",
            email: "pro@vrelio.app",
            displayName: "Pro",
            emailVerified: true,
            plan: "pro",
            effectivePlan: "pro",
            isPro: true,
            maxDevices: 5,
            features: CloudPlanFeatures(cloudSync: true, unlimitedProfiles: true, maxDevices: 5)
        )
        store.setMockCloudSessionForTesting(user: proUser, token: "tok_pro")
        store.toggleFavorite(DemoCatalog.items[1]) // vod:demo_sintel
        store.createPlaylist(name: "Yerel Liste")

        try await store.syncWithCloud()

        XCTAssertEqual(MockCloudSyncURLProtocol.recordedMethods, ["GET", "PUT"])
        XCTAssertTrue(store.favoriteIds.contains("vod:demo_bbb"))
        XCTAssertTrue(store.favoriteIds.contains("vod:demo_sintel"))
        XCTAssertEqual(store.progressByItem["vod:demo_bbb"]?.positionSeconds, 180.0)
        XCTAssertTrue(store.playlists.contains { $0.id == "pl_remote" && $0.itemIds == ["vod:demo_bbb"] })
        XCTAssertTrue(store.playlists.contains { $0.name == "Yerel Liste" })

        let pushedData = try XCTUnwrap(MockCloudSyncURLProtocol.lastPutBody)
        let pushedWrapper = try XCTUnwrap(try JSONSerialization.jsonObject(with: pushedData) as? [String: Any])
        let pushedState = try XCTUnwrap(pushedWrapper["state"] as? [String: Any])
        let pushedFavs = try XCTUnwrap(pushedState["favorites"] as? [[String: Any]])
        let pushedFavIds = Set(pushedFavs.compactMap { $0["item_id"] as? String })
        XCTAssertEqual(pushedFavIds, Set(["vod:demo_bbb", "vod:demo_sintel"]))
    }

    @MainActor
    func testSurpriseItemPrefersPlayableAndImportLocalVideoCopiesToContainer() throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("vrelio_local_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }
        let srcDir = FileManager.default.temporaryDirectory.appendingPathComponent("vrelio_src_\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: srcDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: srcDir) }

        let srcVideo = srcDir.appendingPathComponent("sample_clip.mp4")
        try Data("fake-mp4-bytes".utf8).write(to: srcVideo)

        let store = LibraryStore(storageDirectory: tmpDir, useKeychain: false)
        try store.importLocalMediaFile(from: srcVideo)

        let imported = try XCTUnwrap(store.items.first { $0.name == "sample_clip" })
        XCTAssertTrue(imported.sourceUrl.contains(tmpDir.path))
        let copiedURL = try XCTUnwrap(URL(string: imported.sourceUrl))
        XCTAssertTrue(FileManager.default.fileExists(atPath: copiedURL.path))

        // surpriseItem must prefer playable items over series
        store.importM3uText("""
        #EXTM3U
        #EXTINF:-1 group-title="Test" type="movie",Tek Film
        https://cdn.example.com/tek.mp4
        """)
        let seriesBackup = """
        {"version":1,"exportedAt":"2026-11-19T00:00:00Z","favorites":[],"progress":[],"playlists":[],"playlistItems":[],"trackPreferences":[],"items":[{"id":"series:99","providerId":"99","name":"Test Dizi","kind":"series","categoryId":"","categoryName":"","poster":"","backdrop":"","year":"","rating":0,"extension":"mp4","durationSeconds":0,"plot":"","season":0,"episode":0,"parentId":null,"addedAt":0,"videoCodec":"","audioCodec":""}]}
        """.data(using: .utf8)!
        try store.importBackupJSON(seriesBackup)
        XCTAssertTrue(store.items.contains { $0.id == "series:99" })
        for _ in 0..<20 {
            let pick = store.surpriseItem()
            XCTAssertNotNil(pick)
            XCTAssertNotEqual(pick?.id, "series:99")
            XCTAssertEqual(pick?.kind, .vod)
        }
    }

    @MainActor
    func testLegacySnakeCaseBackupStillDecodes() throws {
        let legacyJSON = """
        {
          "version": 1,
          "exportedAt": "2026-11-18T12:00:00Z",
          "favorites": ["vod:demo_bbb"],
          "progress": [
            {"itemId": "vod:demo_bbb", "positionSeconds": 42.0, "durationSeconds": 596.0, "completed": false, "updatedAt": 1700000000.0}
          ],
          "playlists": [
            {"id": "pl_legacy", "name": "Eski Liste", "createdAt": "2026-11-18T12:00:00Z", "itemIds": ["vod:demo_bbb"]}
          ],
          "items": [
            {"id": "vod:demo_bbb", "provider_id": "demo_bbb", "name": "Big Buck Bunny", "kind": "vod", "category_id": "demo", "category_name": "Demo", "poster": "", "backdrop": "", "year": "2008", "rating": 8.0, "extension": "mp4", "duration_seconds": 596, "plot": "", "season": 0, "episode": 0, "parent_id": null, "added_at": 1, "video_codec": "", "audio_codec": "", "genres": "", "source_url": "https://example.com/bbb.mp4", "tvg_id": "", "cast": "", "director": ""}
          ]
        }
        """.data(using: .utf8)!

        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("vrelio_legacy_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }
        let store = LibraryStore(storageDirectory: tmpDir, useKeychain: false)
        try store.importBackupJSON(legacyJSON)

        XCTAssertTrue(store.favoriteIds.contains("vod:demo_bbb"))
        XCTAssertEqual(store.progressByItem["vod:demo_bbb"]?.positionSeconds, 42.0)
        XCTAssertEqual(store.playlists.first(where: { $0.id == "pl_legacy" })?.itemIds, ["vod:demo_bbb"])
    }
}

private final class MockCloudSyncURLProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private static var remoteStateJSON: String = "{}"
    nonisolated(unsafe) static var recordedMethods: [String] = []
    nonisolated(unsafe) static var lastPutBody: Data?

    static func reset(remoteStateJSON: String) {
        lock.lock()
        defer { lock.unlock() }
        self.remoteStateJSON = remoteStateJSON
        self.recordedMethods = []
        self.lastPutBody = nil
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let method = request.httpMethod ?? "GET"
        var bodyData = request.httpBody
        if bodyData == nil, let stream = request.httpBodyStream {
            stream.open()
            defer { stream.close() }
            var collected = Data()
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let count = stream.read(&buffer, maxLength: buffer.count)
                if count > 0 { collected.append(buffer, count: count) } else { break }
            }
            bodyData = collected
        }

        let responseJSON: String
        Self.lock.lock()
        Self.recordedMethods.append(method)
        if method == "PUT" {
            Self.lastPutBody = bodyData
            responseJSON = Self.remoteStateJSON
        } else {
            responseJSON = Self.remoteStateJSON
        }
        Self.lock.unlock()

        let url = request.url ?? URL(string: "http://127.0.0.1:19999/api/v1/sync")!
        let resp = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(responseJSON.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
