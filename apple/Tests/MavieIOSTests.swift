import CryptoKit
import Darwin
import Foundation
import XCTest
@testable import MavieIOS

final class MavieIOSTests: XCTestCase {

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

    func testNavigationTabsAreFiveFreeLocalTabsIncludingSportsWithoutAccountGate() {
        XCTAssertEqual(MavieTab.allCases, [.home, .sports, .library, .search, .settings])
        XCTAssertEqual(MavieTab.allCases.count, 5)
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
    func testLibraryStoreUnlimitedProfilesAndPinAreCompletelyFree() throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let store = LibraryStore(storageDirectory: tmpDir)
        XCTAssertEqual(store.profiles.count, 1)

        let second = try store.addProfile(name: "İkinci Profil")
        let kids = try store.addProfile(name: "Çocuk", isKids: true, pin: "1234")
        let third = try store.addProfile(name: "Misafir", pin: "9876")

        XCTAssertEqual(store.profiles.count, 4)
        XCTAssertFalse(second.hasPin)
        XCTAssertTrue(kids.hasPin)
        XCTAssertTrue(kids.isKids)
        XCTAssertTrue(third.hasPin)

        XCTAssertThrowsError(try store.switchProfile(id: kids.id, pinAttempt: "0000"))
        try store.switchProfile(id: kids.id, pinAttempt: "1234")
        XCTAssertTrue(store.profiles.first(where: { $0.id == kids.id })?.active ?? false)
    }

    @MainActor
    func testLibraryStoreTracksProgressAndFavorites() {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let store = LibraryStore(storageDirectory: tmpDir)
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
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let store = LibraryStore(storageDirectory: tmpDir)
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

        let tmpDir2 = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_test2_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir2) }
        let restored = LibraryStore(storageDirectory: tmpDir2)
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

        let decodedPayload = try JSONDecoder().decode(LibrarySyncPayload.self, from: serverExportFixture)
        XCTAssertEqual(decodedPayload.version, 1)
        XCTAssertEqual(decodedPayload.favorites.map(\.itemId), ["vod:demo_bbb"])
        XCTAssertEqual(decodedPayload.progress.first?.itemId, "vod:demo_bbb")
        XCTAssertEqual(decodedPayload.progress.first?.positionSeconds, 120.0)
        XCTAssertEqual(decodedPayload.progress.first?.completed, false)
        XCTAssertEqual(decodedPayload.playlists.first?.id, "m0LVaBAITrp2zwbQ")
        XCTAssertEqual(decodedPayload.playlists.first?.itemIds, ["vod:demo_bbb"])
        XCTAssertEqual(decodedPayload.trackPreferences.first?.data.audio, "auto")
        XCTAssertEqual(decodedPayload.items.first?.providerId, "demo_bbb")

        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_v1_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }
        let store = LibraryStore(storageDirectory: tmpDir)
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
    func testSurpriseItemPrefersPlayableAndImportLocalVideoCopiesToContainer() throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_local_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }
        let srcDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_src_\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: srcDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: srcDir) }

        let srcVideo = srcDir.appendingPathComponent("sample_clip.mp4")
        try Data("fake-mp4-bytes".utf8).write(to: srcVideo)

        let store = LibraryStore(storageDirectory: tmpDir)
        try store.importLocalMediaFile(from: srcVideo)

        let imported = try XCTUnwrap(store.items.first { $0.name == "sample_clip" })
        XCTAssertTrue(imported.sourceUrl.contains(tmpDir.path))
        let copiedURL = try XCTUnwrap(URL(string: imported.sourceUrl))
        XCTAssertTrue(FileManager.default.fileExists(atPath: copiedURL.path))

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

        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_legacy_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }
        let store = LibraryStore(storageDirectory: tmpDir)
        try store.importBackupJSON(legacyJSON)

        XCTAssertTrue(store.favoriteIds.contains("vod:demo_bbb"))
        XCTAssertEqual(store.progressByItem["vod:demo_bbb"]?.positionSeconds, 42.0)
        XCTAssertEqual(store.playlists.first(where: { $0.id == "pl_legacy" })?.itemIds, ["vod:demo_bbb"])
    }

    func testDiscoveryEngineNetflixTop10AndPersonalizedGenreOrder() {
        let watchedShow = MediaItem(id: "series:gibi", providerId: "gibi", name: "Gibi", kind: .series, year: "2021", genres: "Komedi")
        let comedyMovie = MediaItem(id: "vod:comedy", providerId: "c1", name: "New Comedy |2026| TR", kind: .vod, poster: "https://example.com/c.jpg", year: "2026", rating: 7.5)
        let horrorMovie = MediaItem(id: "vod:horror", providerId: "h1", name: "New Horror (2026)", kind: .vod, poster: "https://example.com/h.jpg", year: "2026", rating: 8.5)
        let feed = DiscoveryFeedPayload(
            updatedAt: 1_793_900_000,
            metas: [
                DiscoveryFeedEntry(id: "tt1", kind: "vod", name: "New Comedy", genres: ["Comedy"], year: "2026", released: "2026-10-01", globalRank: 5),
                DiscoveryFeedEntry(id: "tt2", kind: "vod", name: "New Horror", genres: ["Horror"], year: "2026", released: "2026-10-02", globalRank: 1),
            ],
            charts: [
                DiscoveryFeedEntry(id: "nf1", kind: "vod", name: "New Comedy", year: "2026", rank: 1, week: "2026-11-01", netflixId: 123, source: "netflix")
            ]
        )
        let cal = Calendar(identifier: .gregorian)
        let today = cal.date(from: DateComponents(timeZone: DiscoveryEngine.istanbulTimeZone, year: 2026, month: 11, day: 6))!
        let progress = [
            "series:gibi": WatchProgress(itemId: "series:gibi", positionSeconds: 1200, durationSeconds: 1800, completed: false, updatedAt: today.timeIntervalSince1970 - 86400)
        ]
        let result = DiscoveryEngine.build(
            catalog: [watchedShow, comedyMovie, horrorMovie],
            progressByItem: progress,
            favoriteIds: [],
            feed: feed,
            today: today
        )
        XCTAssertTrue(result.personalized)
        XCTAssertEqual(result.shelves.first(where: { $0.id == "turkey-vod" })?.title, "Türkiye’de Popüler Filmler")
        XCTAssertEqual(result.shelves.first(where: { $0.id == "for-you-vod" })?.items.first?.id, "vod:comedy")
        let genreShelves = result.shelves.filter { $0.id.hasPrefix("genre-vod-") }
        XCTAssertEqual(genreShelves.first?.id, "genre-vod-Comedy")
        XCTAssertTrue(genreShelves.first?.subtitle.contains("öne çıkarıldı") == true)
    }

    func testSportsGuideServiceParsesModernSporekraniAndMatchesAliases() throws {
        let html = """
        <html><script>window.__INITIAL_STATE__={"common":{"eventChannels":{"10":{"id":10,"name":"S Sport 1","active":1},"11":{"id":11,"name":"Yayın Yok","active":1}},"eventRows":[{"id":501,"sport_name":"Basketbol","league_name":"EuroLeague","event_type_name":"match","name":"Fenerbahçe Beko - Real Madrid","post_fix":"Canlı","date_time":"2026-11-21 20:45:00","channels":[10,11],"featured":1}]}}</script></html>
        """
        let events = try SportsGuideService.parseSporekrani(page: html, dayIso: "2026-11-21")
        XCTAssertEqual(events.count, 1)
        XCTAssertEqual(events[0].title, "Fenerbahçe Beko - Real Madrid · Canlı")
        XCTAssertEqual(events[0].channels, ["S Sport 1"])
        let live = [MediaItem(id: "live:ssport", providerId: "1", name: "TR: S Sport FHD", kind: .live)]
        let matches = SportsChannels.matchChannels(events: events, liveItems: live)
        XCTAssertEqual(matches["S Sport 1"]?.id, "live:ssport")
    }

    func testM3uParserHandlesUtf8BomQuotedCommasPhpAndMixedKindCategories() {
        let playlist = "\u{FEFF}" + """
        #EXTM3U url-tvg="http://epg.example.test/guide.xml"
        #EXTINF:-1 tvg-id="k1" tvg-name="Haber, Canlı" group-title="Ortak Grup",Kanal 1, HD
        http://stream.example.test/get.php?username=demo&password=pass&type=m3u_plus&output=mpegts
        #EXTINF:-1 group-title="Ortak Grup" type="movie",Örnek Film (2025)
        https://cdn.example.test/movies/sample.mp4
        """
        let parsed = M3uParser.parse(playlist)
        XCTAssertEqual(parsed.epgUrl, "http://epg.example.test/guide.xml")
        XCTAssertEqual(parsed.items.count, 2)
        XCTAssertEqual(parsed.items[0].name, "Kanal 1, HD")
        XCTAssertEqual(parsed.items[0].extensionName, "ts")
        XCTAssertEqual(parsed.items[0].kind, .live)
        XCTAssertEqual(parsed.items[1].kind, .vod)
        XCTAssertEqual(parsed.categories.count, 2)
        XCTAssertTrue(parsed.categories.contains { $0.name == "Ortak Grup" && $0.kind == .live })
        XCTAssertTrue(parsed.categories.contains { $0.name == "Ortak Grup" && $0.kind == .vod })
        XCTAssertNotEqual(parsed.categories[0].id, parsed.categories[1].id)
    }

    func testXtreamStreamUrlBuilderPercentEncodesCredentialsAndDefaultsTs() throws {
        let live = MediaItem(id: "live:42", providerId: "42", name: "Kanal", kind: .live, extensionName: "mp4")
        let url = try XtreamClient.buildStreamURL(
            host: "panel.example.test:8080",
            username: "user/1",
            password: "p?a#s%s word",
            item: live,
            preferHLSForLive: false
        )
        XCTAssertEqual(url.scheme, "http")
        XCTAssertTrue(url.absoluteString.contains("/live/user%2F1/p%3Fa%23s%25s%20word/42.ts"))
    }

    @MainActor
    func testLibraryStoreRemoveProfileGuardsDefaultAndResetsActive() throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_prof_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let store = LibraryStore(storageDirectory: tmpDir)
        XCTAssertThrowsError(try store.removeProfile(id: "default"))

        let extra = try store.addProfile(name: "Misafir", pin: "2468")
        try store.switchProfile(id: extra.id, pinAttempt: "2468")
        XCTAssertTrue(store.profiles.first(where: { $0.id == extra.id })?.active ?? false)

        try store.removeProfile(id: extra.id)
        XCTAssertEqual(store.profiles.count, 1)
        XCTAssertTrue(store.profiles.first(where: { $0.id == "default" })?.active ?? false)
    }

    func testSportsGuideServiceParsesXmltvAndRejectsDtd() throws {
        let xml = """
        <?xml version="1.0" encoding="UTF-8"?>
        <tv>
          <channel id="bein1.tr"><display-name>beIN Sports 1</display-name></channel>
          <programme start="20261121170000 +0000" stop="20261121190000 +0000" channel="bein1.tr">
            <title>Galatasaray - Beşiktaş</title>
            <category>Futbol</category>
            <category>Süper Lig</category>
          </programme>
        </tv>
        """.data(using: .utf8)!

        let events = try SportsGuideService.parseXMLTV(data: xml, dayIso: "2026-11-21")
        XCTAssertEqual(events.count, 1)
        XCTAssertEqual(events[0].time, "20:00")
        XCTAssertEqual(events[0].channels, ["beIN Sports 1"])
        XCTAssertTrue(events[0].featured)

        let dtdXml = """
        <!DOCTYPE tv [<!ENTITY xxe "bad">]>
        <tv></tv>
        """.data(using: .utf8)!
        XCTAssertThrowsError(try SportsGuideService.parseXMLTV(data: dtdXml, dayIso: "2026-11-21"))
    }

    func testLanSyncIPv6DefaultPortAndCookieExtraction() throws {
        let v6 = try LanSyncClient.validateLanAddress("[::1]")
        XCTAssertEqual(v6.port, 8844)
        XCTAssertTrue(v6.host == "::1" || v6.host == "[::1]")

        let url = URL(string: "http://192.168.1.10:8844/api/pair")!
        let resp = HTTPURLResponse(
            url: url,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: ["Set-Cookie": "mavie_lan=tok123; Path=/; HttpOnly"]
        )!
        let cookie = LanSyncClient.extractCookieHeader(from: resp, url: url)
        XCTAssertEqual(cookie, "mavie_lan=tok123")
    }

    func testMavieHTTPClientRetry403FallbackAndLoopbackProxyBypass() async throws {
        XCTAssertEqual(MavieHTTPClient.loopbackSession.configuration.connectionProxyDictionary?.count, 0)
        XCTAssertEqual(MavieHTTPClient.lanSession.configuration.connectionProxyDictionary?.count, 0)
        XCTAssertEqual(MavieHTTPClient.sharedSession.configuration.requestCachePolicy, .reloadIgnoringLocalCacheData)

        let session = MavieHTTPClient.makeSession(
            bypassProxy: true,
            requestTimeout: 5,
            resourceTimeout: 10,
            protocolClasses: [MavieTestURLProtocol.self]
        )

        var attempts = 0
        MavieTestURLProtocol.handler = { req in
            attempts += 1
            let ua = req.value(forHTTPHeaderField: "User-Agent") ?? ""
            if attempts == 1 {
                XCTAssertEqual(ua, MavieHTTPClient.primaryUserAgent)
                return (HTTPURLResponse(url: req.url!, statusCode: 403, httpVersion: nil, headerFields: nil)!, Data())
            }
            if attempts == 2 {
                XCTAssertEqual(ua, MavieHTTPClient.browserUserAgent)
                return (HTTPURLResponse(url: req.url!, statusCode: 503, httpVersion: nil, headerFields: nil)!, Data())
            }
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data("OK".utf8))
        }
        defer { MavieTestURLProtocol.handler = nil }

        let req = URLRequest(url: URL(string: "http://mock.local/test")!)
        let (data, http) = try await MavieHTTPClient.fetchData(for: req, session: session, retryDelays: [0.05])
        XCTAssertEqual(http.statusCode, 200)
        XCTAssertEqual(String(data: data, encoding: .utf8), "OK")
        XCTAssertEqual(attempts, 3)
    }

    @MainActor
    func testLibraryStoreM3uAndXtreamNonDestructiveGuardsWithMockURLProtocol() async throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_mock_store_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let store = LibraryStore(storageDirectory: tmpDir)
        let initialCount = store.items.count
        XCTAssertGreaterThan(initialCount, 0)

        let session = MavieHTTPClient.makeSession(
            bypassProxy: true,
            requestTimeout: 5,
            resourceTimeout: 10,
            protocolClasses: [MavieTestURLProtocol.self]
        )

        MavieTestURLProtocol.handler = { req in
            let urlStr = req.url?.absoluteString ?? ""
            if urlStr.hasPrefix("http://") {
                throw URLError(.cannotConnectToHost)
            }
            let body = "#EXTM3U\n#EXTINF:-1,Fallback Kanal\nhttps://cdn.example.test/live/ch1.m3u8\n"
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data(body.utf8))
        }
        defer { MavieTestURLProtocol.handler = nil }

        await store.importM3uFromURL("mock.example.test/list.m3u", session: session)
        XCTAssertNil(store.lastError)
        XCTAssertEqual(store.sourceMode, .m3u)
        XCTAssertEqual(store.items.count, 1)
        XCTAssertEqual(store.connection.m3uUrl, "https://mock.example.test/list.m3u")

        // Failing Xtream stream fetches must preserve existing M3U catalog
        MavieTestURLProtocol.handler = { req in
            let q = req.url?.query ?? ""
            if !q.contains("action=") {
                let auth = #"{"user_info":{"auth":1,"status":"Active","max_connections":"1"}}"#
                return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data(auth.utf8))
            }
            return (HTTPURLResponse(url: req.url!, statusCode: 502, httpVersion: nil, headerFields: nil)!, Data())
        }

        await store.connectXtream(host: "http://xtream.example.test", username: "u1", password: "p1", session: session)
        XCTAssertNotNil(store.lastError)
        XCTAssertEqual(store.sourceMode, .m3u)
        XCTAssertEqual(store.items.count, 1)
        XCTAssertEqual(store.items.first?.name, "Fallback Kanal")
    }

    @MainActor
    func testLibraryStoreSplitsProgressFromCatalogAndPreservesOver4000Items() throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_scale_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        var lines = ["#EXTM3U"]
        for i in 1...4505 {
            lines.append("#EXTINF:-1 group-title=\"Sinema\" type=\"movie\",Film \(i)")
            lines.append("https://cdn.example.test/movies/\(i).mp4")
        }
        let playlist = lines.joined(separator: "\n")

        let store = LibraryStore(storageDirectory: tmpDir)
        store.importM3uText(playlist)
        XCTAssertEqual(store.items.count, 4505)

        let libURL = tmpDir.appendingPathComponent("library_state.json")
        let progURL = tmpDir.appendingPathComponent("progress_state.json")
        XCTAssertTrue(FileManager.default.fileExists(atPath: libURL.path))
        let libBefore = try Data(contentsOf: libURL)
        let libText = String(decoding: libBefore, as: UTF8.self)
        XCTAssertFalse(libText.contains("\"progress\":{\"vod:"))

        let attrsBefore = try FileManager.default.attributesOfItem(atPath: libURL.path)
        let mtimeBefore = attrsBefore[.modificationDate] as? Date

        let targetId = try XCTUnwrap(store.items.last?.id)
        store.saveProgress(itemId: targetId, positionSeconds: 125, durationSeconds: 600, flush: true)

        XCTAssertTrue(FileManager.default.fileExists(atPath: progURL.path))
        let attrsAfter = try FileManager.default.attributesOfItem(atPath: libURL.path)
        let mtimeAfter = attrsAfter[.modificationDate] as? Date
        XCTAssertEqual(mtimeBefore, mtimeAfter)
        let libAfter = try Data(contentsOf: libURL)
        XCTAssertEqual(libBefore, libAfter)

        let reloaded = LibraryStore(storageDirectory: tmpDir)
        XCTAssertEqual(reloaded.items.count, 4505)
        XCTAssertEqual(reloaded.progressByItem[targetId]?.positionSeconds, 125)
    }

    @MainActor
    func testLibraryStoreMigratesLegacyProgressAndQuarantinesCorruptFiles() throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_corrupt_test_\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let libURL = tmpDir.appendingPathComponent("library_state.json")
        let progURL = tmpDir.appendingPathComponent("progress_state.json")
        let legacyJSON = """
        {
          "sourceMode": "demo",
          "items": [],
          "categories": [],
          "favoriteIds": ["vod:demo_bbb"],
          "favoriteCreatedAt": {},
          "progress": {
            "vod:demo_bbb": {
              "item_id": "vod:demo_bbb",
              "position": 180.0,
              "duration": 596.0,
              "completed": 0,
              "updated_at": "2026-11-20T10:00:00Z"
            }
          },
          "playlists": [],
          "trackPreferences": [],
          "profiles": [],
          "connection": {"sourceType":"demo","host":"","username":"","password":"","m3uUrl":"","epgUrl":"","lanAddress":""},
          "account": {"id":"demo","username":"AcikSinema","host":"demo.mavie.app","name":"Demo","status":"Active","expiresAt":"","maxConnections":1,"sourceType":"demo","epgUrl":""}
        }
        """
        try Data(legacyJSON.utf8).write(to: libURL)

        let migrated = LibraryStore(storageDirectory: tmpDir)
        XCTAssertNil(migrated.lastError)
        XCTAssertEqual(migrated.progressByItem["vod:demo_bbb"]?.positionSeconds, 180.0)
        XCTAssertTrue(FileManager.default.fileExists(atPath: progURL.path))

        let scrubbedLib = String(decoding: try Data(contentsOf: libURL), as: UTF8.self)
        XCTAssertFalse(scrubbedLib.contains("\"position\":180"))

        try Data("{corrupt-library".utf8).write(to: libURL)
        try Data("{corrupt-progress".utf8).write(to: progURL)

        let recovered = LibraryStore(storageDirectory: tmpDir)
        XCTAssertNotNil(recovered.lastError)
        let files = try FileManager.default.contentsOfDirectory(atPath: tmpDir.path)
        XCTAssertTrue(files.contains { $0.hasPrefix("library_state.corrupt.") && $0.hasSuffix(".json") })
        XCTAssertTrue(files.contains { $0.hasPrefix("progress_state.corrupt.") && $0.hasSuffix(".json") })
    }

    @MainActor
    func testLibraryStoreSurfacesSaveWriteErrors() throws {
        guard geteuid() != 0 else { return }
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_ro_test_\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: tmpDir.path)
            try? FileManager.default.removeItem(at: tmpDir)
        }

        let store = LibraryStore(storageDirectory: tmpDir)
        try FileManager.default.setAttributes([.posixPermissions: 0o555], ofItemAtPath: tmpDir.path)

        store.toggleFavorite(DemoCatalog.items[0])
        XCTAssertNotNil(store.lastError)
    }

    func testHTTPClientRedactsCredentialsAndEnforcesMaxBytes() async throws {
        let raw = "Failed connecting to https://ali:superSecret99@panel.example.test:8080/live/ali/superSecret99/42.m3u8?token=tokABC"
        let redacted = MavieHTTPClient.redactSensitiveURLs(in: raw)
        XCTAssertFalse(redacted.contains("superSecret99"))
        XCTAssertFalse(redacted.contains("tokABC"))
        XCTAssertTrue(redacted.contains("***"))

        let urlErr = URLError(
            .unknown,
            userInfo: [NSURLErrorFailingURLStringErrorKey: "https://panel.example.test/player_api.php?username=demo_user&password=hiddenPassword42"]
        )
        let classified = MavieHTTPClient.classifyURLError(urlErr, context: "Xtream sunucusu")
        XCTAssertFalse(classified.contains("hiddenPassword42"))

        let session = MavieHTTPClient.makeSession(
            bypassProxy: true,
            requestTimeout: 5,
            resourceTimeout: 10,
            protocolClasses: [MavieTestURLProtocol.self]
        )
        defer { MavieTestURLProtocol.handler = nil }

        // 1. Content-Length exceeds maxBytes
        MavieTestURLProtocol.handler = { req in
            let resp = HTTPURLResponse(
                url: req.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Length": "1024"]
            )!
            return (resp, Data(repeating: 0x41, count: 16))
        }
        do {
            _ = try await MavieHTTPClient.fetchData(
                for: URLRequest(url: URL(string: "http://mock.local/large-header")!),
                session: session,
                retryDelays: [],
                retryOnTransportFailure: false,
                maxBytes: 64
            )
            XCTFail("Expected size error for Content-Length")
        } catch let err as MavieError {
            if case .validation = err { } else { XCTFail("Unexpected MavieError: \(err)") }
        }

        // 2. Chunked / unknown Content-Length exceeds maxBytes
        MavieTestURLProtocol.handler = { req in
            let resp = HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (resp, Data(repeating: 0x42, count: 128))
        }
        do {
            _ = try await MavieHTTPClient.fetchData(
                for: URLRequest(url: URL(string: "http://mock.local/large-body")!),
                session: session,
                retryDelays: [],
                retryOnTransportFailure: false,
                maxBytes: 64
            )
            XCTFail("Expected size error for body")
        } catch let err as MavieError {
            if case .validation = err { } else { XCTFail("Unexpected MavieError: \(err)") }
        }

        // 3. Within maxBytes succeeds
        MavieTestURLProtocol.handler = { req in
            let resp = HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (resp, Data("small-ok".utf8))
        }
        let (okData, _) = try await MavieHTTPClient.fetchData(
            for: URLRequest(url: URL(string: "http://mock.local/small")!),
            session: session,
            retryDelays: [],
            retryOnTransportFailure: false,
            maxBytes: 64
        )
        XCTAssertEqual(String(data: okData, encoding: .utf8), "small-ok")
    }

    func testLanSyncDnsTimeoutAndCancellation() async throws {
        let cancelTask = Task {
            try await Task.sleep(nanoseconds: 50_000_000)
            return try await LanSyncClient.resolveAndValidateLanAddress("slow.example.invalid:8844", dnsTimeout: 1.0)
        }
        cancelTask.cancel()
        do {
            _ = try await cancelTask.value
            XCTFail("Expected CancellationError")
        } catch is CancellationError {
            // Expected
        }

        do {
            _ = try await LanSyncClient.resolveAndValidateLanAddress("192.0.2.1:8844", dnsTimeout: 0.2)
            XCTFail("Expected public IP rejection")
        } catch let err as MavieError {
            if case .validation = err { } else { XCTFail("Expected validation error, got \(err)") }
        }

        let start = Date()
        do {
            _ = try await LanSyncClient.resolveAndValidateLanAddress("nonexistent.invalid:8844", dnsTimeout: 0.05)
            XCTFail("Expected DNS failure or timeout")
        } catch {
            XCTAssertLessThan(Date().timeIntervalSince(start), 2.0)
        }
    }

    @MainActor
    func testCredentialVaultAndSaltedPBKDF2PinsAndLockout() async throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_vault_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let store = LibraryStore(storageDirectory: tmpDir)
        let m3uSecretUrl = "https://panel.example.test/get.php?username=demo_user&password=secretM3uPass99"
        store.importM3uText("#EXTM3U\n#EXTINF:-1,Kanal\nhttps://cdn.example.test/live/1.m3u8", m3uUrl: m3uSecretUrl)

        let session = MavieHTTPClient.makeSession(
            bypassProxy: true,
            requestTimeout: 5,
            resourceTimeout: 10,
            protocolClasses: [MavieTestURLProtocol.self]
        )
        MavieTestURLProtocol.handler = { req in
            let q = req.url?.query ?? ""
            if !q.contains("action=") {
                return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data(#"{"user_info":{"auth":1,"status":"Active","max_connections":"1"}}"#.utf8))
            }
            if q.contains("categories") {
                return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data("[]".utf8))
            }
            if q.contains("get_live_streams") {
                return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data(#"[{"stream_id":10,"name":"Haber 1","category_id":"1"}]"#.utf8))
            }
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data("[]".utf8))
        }
        defer { MavieTestURLProtocol.handler = nil }

        await store.connectXtream(host: "http://panel.example.test", username: "ali", password: "secretXtreamPass88", session: session)
        XCTAssertNil(store.lastError)
        XCTAssertTrue(store.hasSavedXtreamPassword)

        let libJSON = String(decoding: try Data(contentsOf: tmpDir.appendingPathComponent("library_state.json")), as: UTF8.self)
        XCTAssertFalse(libJSON.contains("secretM3uPass99"))
        XCTAssertFalse(libJSON.contains("secretXtreamPass88"))

        let vaultURL = tmpDir.appendingPathComponent(".credentials_vault.json")
        XCTAssertTrue(FileManager.default.fileExists(atPath: vaultURL.path))
        let vaultAttrs = try FileManager.default.attributesOfItem(atPath: vaultURL.path)
        XCTAssertEqual((vaultAttrs[.posixPermissions] as? NSNumber)?.intValue, 0o600)

        let reloaded = LibraryStore(storageDirectory: tmpDir)
        XCTAssertEqual(reloaded.connection.password, "secretXtreamPass88")
        XCTAssertEqual(reloaded.connection.m3uUrl, m3uSecretUrl)
        XCTAssertTrue(reloaded.hasSavedXtreamPassword)

        // Salted PBKDF2 PINs + lockout
        let p1 = try reloaded.addProfile(name: "Profil A", pin: "4321")
        let p2 = try reloaded.addProfile(name: "Profil B", pin: "4321")
        XCTAssertTrue(p1.pinHash.hasPrefix("pbkdf2_sha256$10000$"))
        XCTAssertNotEqual(p1.pinHash, p2.pinHash)

        for _ in 1...5 {
            XCTAssertThrowsError(try reloaded.switchProfile(id: p1.id, pinAttempt: "0000"))
        }
        // Even correct PIN must be locked out immediately after 5 failures
        XCTAssertThrowsError(try reloaded.switchProfile(id: p1.id, pinAttempt: "4321"))

        // Correct PIN works on non-locked profile
        try reloaded.switchProfile(id: p2.id, pinAttempt: "4321")
        XCTAssertTrue(reloaded.profiles.first(where: { $0.id == p2.id })?.active ?? false)

        reloaded.clearSavedCredentials()
        XCTAssertFalse(reloaded.hasSavedXtreamPassword)
        XCTAssertFalse(FileManager.default.fileExists(atPath: vaultURL.path))
    }

    @MainActor
    func testLegacySha256PinUpgradesToPBKDF2OnLogin() throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_pin_upgrade_\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let legacyHash = SHA256.hash(data: Data("1357".utf8)).map { String(format: "%02x", $0) }.joined()
        let stateJSON = """
        {
          "sourceMode": "demo",
          "items": [],
          "categories": [],
          "favoriteIds": [],
          "favoriteCreatedAt": {},
          "progress": {},
          "playlists": [],
          "trackPreferences": [],
          "profiles": [
            {"id":"default","name":"Ana Profil","avatarColor":"#7C3AED","isKids":false,"hasPin":false,"pinHash":"","active":true},
            {"id":"prof_legacy","name":"Eski","avatarColor":"#3B82F6","isKids":false,"hasPin":true,"pinHash":"\(legacyHash)","active":false}
          ],
          "connection": {"sourceType":"demo","host":"","username":"","password":"legacyPlaintextPass","m3uUrl":"","epgUrl":"","lanAddress":""},
          "account": {"id":"demo","username":"AcikSinema","host":"https://user:pass@legacy.test/list?password=abc","name":"Demo","status":"Active","expiresAt":"","maxConnections":1,"sourceType":"demo","epgUrl":""}
        }
        """
        let libURL = tmpDir.appendingPathComponent("library_state.json")
        try Data(stateJSON.utf8).write(to: libURL)

        let store = LibraryStore(storageDirectory: tmpDir)
        XCTAssertEqual(store.connection.password, "legacyPlaintextPass")
        let scrubbedLib = String(decoding: try Data(contentsOf: libURL), as: UTF8.self)
        XCTAssertFalse(scrubbedLib.contains("legacyPlaintextPass"))
        XCTAssertFalse(scrubbedLib.contains("password=abc"))

        try store.switchProfile(id: "prof_legacy", pinAttempt: "1357")
        let upgraded = try XCTUnwrap(store.profiles.first(where: { $0.id == "prof_legacy" }))
        XCTAssertTrue(upgraded.pinHash.hasPrefix("pbkdf2_sha256$10000$"))
    }

    @MainActor
    func testURLSchemeValidationXtreamCancellationAndSportsErrorPreservation() async throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_sec_test_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }
        let store = LibraryStore(storageDirectory: tmpDir)

        for bad in ["file:///etc/passwd", "javascript:alert(1)", "ftp://example.com/v.mp4"] {
            let item = MediaItem(id: "vod:bad", providerId: "bad", name: "Bad", kind: .vod, sourceUrl: bad)
            XCTAssertThrowsError(try store.resolvePlayableURL(for: item))
        }

        let decodedUnsafeJSON = #"{"id":"vod:x","providerId":"x","name":"X","kind":"vod","poster":"javascript:alert(1)","backdrop":"ftp://a/b.png","sourceUrl":"javascript:alert(2)"}"#.data(using: .utf8)!
        let decodedItem = try JSONDecoder().decode(MediaItem.self, from: decodedUnsafeJSON)
        XCTAssertEqual(decodedItem.poster, "")
        XCTAssertEqual(decodedItem.backdrop, "")
        XCTAssertEqual(decodedItem.sourceUrl, "")

        let srcFile = tmpDir.appendingPathComponent("clip.mp4")
        try Data("video".utf8).write(to: srcFile)
        try await store.importLocalMediaFileAsync(from: srcFile)
        let localItem = try XCTUnwrap(store.items.first { $0.name == "clip" })
        let localPlayURL = try store.resolvePlayableURL(for: localItem)
        XCTAssertEqual(localPlayURL.scheme, "file")

        // Xtream cancellation propagation
        let session = MavieHTTPClient.makeSession(
            bypassProxy: true,
            requestTimeout: 5,
            resourceTimeout: 10,
            protocolClasses: [MavieTestURLProtocol.self]
        )
        MavieTestURLProtocol.handler = { _ in
            throw URLError(.cancelled)
        }
        defer { MavieTestURLProtocol.handler = nil }

        await store.connectXtream(host: "http://panel.example.test", username: "ali", password: "123", session: session)
        XCTAssertNil(store.lastError)

        // SportsGuideService error code preservation (DTD code 13 & HTTP 429)
        let sports = SportsGuideService()
        MavieTestURLProtocol.handler = { req in
            let dtd = "<!DOCTYPE tv [<!ENTITY xxe \"bad\">]><tv></tv>"
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data(dtd.utf8))
        }
        do {
            _ = try await sports.load(dayIso: "2026-11-21", epgUrl: "https://epg.example.test/bad.xml", sourceMode: "xmltv", force: true, session: session)
            XCTFail("Expected DTD error")
        } catch {
            let nsErr = error as NSError
            XCTAssertEqual(nsErr.domain, "MavieSports")
            XCTAssertEqual(nsErr.code, 13)
        }

        MavieTestURLProtocol.handler = { req in
            return (HTTPURLResponse(url: req.url!, statusCode: 429, httpVersion: nil, headerFields: nil)!, Data())
        }
        do {
            _ = try await sports.load(dayIso: "2026-11-21", epgUrl: "https://epg.example.test/rate.xml", sourceMode: "xmltv", force: true, session: session)
            XCTFail("Expected HTTP 429 MavieError")
        } catch let mavieErr as MavieError {
            XCTAssertTrue(mavieErr.localizedDescription.contains("429"))
        }
    }

    @MainActor
    func testPlaybackRecoveryStateMachineAndTrackPreferences() throws {
        let hlsURL = URL(string: "https://panel.example.test/live/ali/secretPass99/42.m3u8")!
        let tsURL = URL(string: "https://panel.example.test/live/ali/secretPass99/42.ts")!
        var state = PlaybackRecoveryState(
            isLive: true,
            currentURL: hlsURL,
            liveTSFallbackURL: tsURL,
            pendingResumeSeconds: 120
        )

        XCTAssertFalse(PlaybackRecoveryState.shouldPersistProgress(duration: 600, isLive: false, hasCompletedInitialSeek: state.hasCompletedInitialSeek, isScrubbing: false))
        XCTAssertEqual(state.markReadyToPlay(), 120)
        XCTAssertNil(state.markReadyToPlay())
        XCTAssertTrue(PlaybackRecoveryState.shouldPersistProgress(duration: 600, isLive: false, hasCompletedInitialSeek: state.hasCompletedInitialSeek, isScrubbing: false))
        XCTAssertFalse(PlaybackRecoveryState.shouldPersistProgress(duration: 600, isLive: false, hasCompletedInitialSeek: state.hasCompletedInitialSeek, isScrubbing: true))
        XCTAssertFalse(PlaybackRecoveryState.shouldPersistProgress(duration: 600, isLive: true, hasCompletedInitialSeek: state.hasCompletedInitialSeek, isScrubbing: false))

        let step1 = state.nextAction(for: PlaybackFailureSignal(httpStatusCode: 403))
        XCTAssertEqual(step1, .retry(url: hlsURL, userAgent: MavieHTTPClient.browserUserAgent, delaySeconds: 0.1, reason: .userAgentFallback))

        let step2 = state.nextAction(for: PlaybackFailureSignal(errorDomain: "AVFoundationErrorDomain", errorCode: -11828))
        XCTAssertEqual(step2, .retry(url: tsURL, userAgent: MavieHTTPClient.browserUserAgent, delaySeconds: 0.1, reason: .liveFormatFallback))

        let step3 = state.nextAction(for: PlaybackFailureSignal(isStallTimeout: true))
        XCTAssertEqual(step3, .retry(url: tsURL, userAgent: MavieHTTPClient.browserUserAgent, delaySeconds: 1.5, reason: .transientReconnect(attempt: 1)))

        let step4 = state.nextAction(for: PlaybackFailureSignal(isStallTimeout: true))
        XCTAssertEqual(step4, .retry(url: tsURL, userAgent: MavieHTTPClient.browserUserAgent, delaySeconds: 3.0, reason: .transientReconnect(attempt: 2)))

        let step5 = state.nextAction(for: PlaybackFailureSignal(rawMessage: "Error opening \(tsURL.absoluteString)"))
        if case .fail(let message) = step5 {
            XCTAssertFalse(message.contains("secretPass99"))
        } else {
            XCTFail("Expected terminal .fail action")
        }

        let queryAlt = PlaybackRecoveryState.alternateLiveTSURL(for: URL(string: "https://p.test/get.php?output=hls")!)
        XCTAssertTrue(queryAlt?.absoluteString.contains("output=mpegts") ?? false)

        let audioTracks = [
            PlaybackTrackCandidate(id: "0", displayName: "English (AAC)", languageTag: "en-US"),
            PlaybackTrackCandidate(id: "1", displayName: "Türkçe", languageTag: "tr-TR"),
        ]
        XCTAssertEqual(
            PlaybackRecoveryState.matchAudioOption(preferred: SyncTrackPreferenceData(audio: "tr", subtitle: "off"), options: audioTracks),
            1
        )
        XCTAssertEqual(
            PlaybackRecoveryState.matchSubtitleOption(preferred: SyncTrackPreferenceData(audio: "tr", subtitle: "off"), options: audioTracks),
            .off
        )
        XCTAssertEqual(
            PlaybackRecoveryState.matchSubtitleOption(preferred: SyncTrackPreferenceData(audio: "auto", subtitle: "en", clientSubtitle: "English (AAC)"), options: audioTracks),
            .select(index: 0)
        )

        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_track_pref_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }
        let store = LibraryStore(storageDirectory: tmpDir)
        store.saveTrackPreference(itemId: "vod:demo_bbb", audio: "tr", subtitle: "en", clientAudio: "Türkçe", clientSubtitle: "English")
        let reloaded = LibraryStore(storageDirectory: tmpDir)
        XCTAssertEqual(reloaded.trackPreference(for: "vod:demo_bbb")?.clientAudio, "Türkçe")

        let oversized = Data(repeating: 0x20, count: LanSyncClient.maxBackupBytes + 1)
        XCTAssertThrowsError(try reloaded.importBackupJSON(oversized))
    }

    @MainActor
    func testBackupImportPersistsProgressAcrossReloadAndLegacyMerge() throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("mavie_backup_prog_\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let backupJSON = """
        {
          "version": 1,
          "exportedAt": "2026-11-25T10:00:00Z",
          "favorites": [],
          "progress": [
            {"item_id": "vod:demo_bbb", "position": 245.0, "duration": 596.0, "completed": 0, "updated_at": "2026-11-25T10:00:00Z"}
          ],
          "playlists": [],
          "playlistItems": [],
          "trackPreferences": [],
          "appleTrackPreferences": [
            {"item_id": "vod:demo_sintel", "data": "{\\"audio\\": \\"en\\", \\"subtitle\\": \\"tr\\", \\"clientAudio\\": \\"English\\", \\"clientSubtitle\\": \\"Türkçe\\"}", "updated_at": "2026-11-25T10:00:00Z"}
          ],
          "items": []
        }
        """.data(using: .utf8)!

        let store = LibraryStore(storageDirectory: tmpDir)
        try store.importBackupJSON(backupJSON)
        XCTAssertEqual(store.progressByItem["vod:demo_bbb"]?.positionSeconds, 245.0)
        XCTAssertEqual(store.trackPreference(for: "vod:demo_sintel")?.clientSubtitle, "Türkçe")

        // Verify imported progress survived reload via progress_state.json
        let reloaded = LibraryStore(storageDirectory: tmpDir)
        XCTAssertEqual(reloaded.progressByItem["vod:demo_bbb"]?.positionSeconds, 245.0)
        XCTAssertEqual(reloaded.trackPreference(for: "vod:demo_sintel")?.clientSubtitle, "Türkçe")

        // Verify legacy progress embedded in library_state.json merges into existing progress_state.json
        let libURL = tmpDir.appendingPathComponent("library_state.json")
        let legacyMergeJSON = """
        {
          "sourceMode": "demo",
          "items": [],
          "categories": [],
          "favoriteIds": [],
          "favoriteCreatedAt": {},
          "progress": {
            "vod:demo_tears": {
              "item_id": "vod:demo_tears",
              "position": 310.0,
              "duration": 734.0,
              "completed": 0,
              "updated_at": "2026-11-25T11:00:00Z"
            }
          },
          "playlists": [],
          "trackPreferences": [],
          "profiles": [],
          "connection": {"sourceType":"demo","host":"","username":"","password":"","m3uUrl":"","epgUrl":"","lanAddress":""},
          "account": {"id":"demo","username":"AcikSinema","host":"demo.mavie.app","name":"Demo","status":"Active","expiresAt":"","maxConnections":1,"sourceType":"demo","epgUrl":""}
        }
        """
        try Data(legacyMergeJSON.utf8).write(to: libURL)

        let merged = LibraryStore(storageDirectory: tmpDir)
        XCTAssertEqual(merged.progressByItem["vod:demo_bbb"]?.positionSeconds, 245.0)
        XCTAssertEqual(merged.progressByItem["vod:demo_tears"]?.positionSeconds, 310.0)

        let reloadedAfterMerge = LibraryStore(storageDirectory: tmpDir)
        XCTAssertEqual(reloadedAfterMerge.progressByItem["vod:demo_bbb"]?.positionSeconds, 245.0)
        XCTAssertEqual(reloadedAfterMerge.progressByItem["vod:demo_tears"]?.positionSeconds, 310.0)
    }
}

private final class MavieTestURLProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        do {
            let (resp, data) = try handler(request)
            client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
