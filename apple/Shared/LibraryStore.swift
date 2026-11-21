import CryptoKit
import Foundation
import SwiftUI

private struct PersistedLibraryState: Codable {
    var sourceMode: SourceMode = .demo
    var items: [MediaItem] = []
    var categories: [MediaCategory] = []
    var favoriteIds: [String] = []
    var favoriteCreatedAt: [String: String] = [:]
    var progress: [String: WatchProgress] = [:]
    var playlists: [Playlist] = []
    var trackPreferences: [SyncTrackPreferenceRecord] = []
    var profiles: [UserProfile] = []
    var connection: ConnectionSettings = ConnectionSettings()
    var account: AccountInfo = AccountInfo()

    init() {}

    init(
        sourceMode: SourceMode,
        items: [MediaItem],
        categories: [MediaCategory],
        favoriteIds: [String],
        favoriteCreatedAt: [String: String],
        progress: [String: WatchProgress],
        playlists: [Playlist],
        trackPreferences: [SyncTrackPreferenceRecord],
        profiles: [UserProfile],
        connection: ConnectionSettings,
        account: AccountInfo
    ) {
        self.sourceMode = sourceMode
        self.items = items
        self.categories = categories
        self.favoriteIds = favoriteIds
        self.favoriteCreatedAt = favoriteCreatedAt
        self.progress = progress
        self.playlists = playlists
        self.trackPreferences = trackPreferences
        self.profiles = profiles
        self.connection = connection
        self.account = account
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.sourceMode = (try? c.decodeIfPresent(SourceMode.self, forKey: .sourceMode)) ?? .demo
        self.items = (try? c.decodeIfPresent([MediaItem].self, forKey: .items)) ?? []
        self.categories = (try? c.decodeIfPresent([MediaCategory].self, forKey: .categories)) ?? []
        self.favoriteIds = (try? c.decodeIfPresent([String].self, forKey: .favoriteIds)) ?? []
        self.favoriteCreatedAt = (try? c.decodeIfPresent([String: String].self, forKey: .favoriteCreatedAt)) ?? [:]
        self.progress = (try? c.decodeIfPresent([String: WatchProgress].self, forKey: .progress)) ?? [:]
        self.playlists = (try? c.decodeIfPresent([Playlist].self, forKey: .playlists)) ?? []
        self.trackPreferences = (try? c.decodeIfPresent([SyncTrackPreferenceRecord].self, forKey: .trackPreferences)) ?? []
        self.profiles = (try? c.decodeIfPresent([UserProfile].self, forKey: .profiles)) ?? []
        self.connection = (try? c.decodeIfPresent(ConnectionSettings.self, forKey: .connection)) ?? ConnectionSettings()
        self.account = (try? c.decodeIfPresent(AccountInfo.self, forKey: .account)) ?? AccountInfo()
    }
}

@MainActor
public final class LibraryStore: ObservableObject {
    @Published public private(set) var sourceMode: SourceMode = .demo
    @Published public private(set) var items: [MediaItem] = []
    @Published public private(set) var categories: [MediaCategory] = []
    @Published public private(set) var favoriteIds: Set<String> = []
    @Published public private(set) var progressByItem: [String: WatchProgress] = [:]
    @Published public private(set) var playlists: [Playlist] = []
    @Published public private(set) var profiles: [UserProfile] = []
    @Published public var connection: ConnectionSettings = ConnectionSettings()
    @Published public private(set) var account: AccountInfo = AccountInfo()

    @Published public var isBusy: Bool = false
    @Published public var statusBanner: String?
    @Published public var lastError: String?

    private let baseDirectory: URL
    private let storageURL: URL
    private var favoriteCreatedAt: [String: String] = [:]
    private var trackPreferencesByItem: [String: SyncTrackPreferenceRecord] = [:]

    public init(storageDirectory: URL? = nil) {
        let baseDir: URL
        if let storageDirectory {
            baseDir = storageDirectory
        } else {
            let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
                ?? FileManager.default.temporaryDirectory
            baseDir = appSupport.appendingPathComponent("Mavie", isDirectory: true)
        }
        try? FileManager.default.createDirectory(at: baseDir, withIntermediateDirectories: true)
        self.baseDirectory = baseDir
        self.storageURL = baseDir.appendingPathComponent("library_state.json")

        loadState()
        if profiles.isEmpty {
            profiles = [UserProfile(id: "default", name: "Ana Profil", avatarColor: "#7C3AED", active: true)]
        }
        if items.isEmpty && sourceMode == .demo {
            loadDemoCatalog(persist: false)
        }
    }

    // MARK: - Catalog Sources

    public func loadDemoCatalog(persist: Bool = true) {
        sourceMode = .demo
        connection.sourceType = .demo
        items = DemoCatalog.items
        categories = DemoCatalog.categories
        account = AccountInfo(
            id: "demo",
            username: "AcikSinema",
            host: "demo.mavie.app",
            name: "Açık Sinema / Demo",
            status: "Active",
            maxConnections: 1,
            sourceType: .demo
        )
        statusBanner = "4 açık lisanslı demo filmi yüklendi."
        if persist { saveState() }
    }

    public func importM3uText(_ text: String, m3uUrl: String = "") {
        let parsed = M3uParser.parse(text)
        guard !parsed.items.isEmpty else {
            lastError = "M3U listesinde geçerli yayın veya video adresi bulunamadı."
            return
        }
        sourceMode = .m3u
        connection.sourceType = .m3u
        if !m3uUrl.isEmpty { connection.m3uUrl = m3uUrl }
        if !parsed.epgUrl.isEmpty { connection.epgUrl = parsed.epgUrl }
        items = parsed.items
        categories = parsed.categories
        account = AccountInfo(
            id: "m3u",
            username: "M3U",
            host: m3uUrl.isEmpty ? "Yerel Liste" : m3uUrl,
            name: "M3U Kütüphanesi",
            status: "Active",
            sourceType: .m3u,
            epgUrl: parsed.epgUrl
        )
        statusBanner = "\(parsed.items.count) içerik M3U listesinden yüklendi."
        lastError = nil
        saveState()
    }

    public func importM3uFromURL(_ urlString: String) async {
        isBusy = true
        lastError = nil
        defer { isBusy = false }
        do {
            var normalized = urlString.trimmingCharacters(in: .whitespacesAndNewlines)
            if !normalized.contains("://") { normalized = "https://" + normalized }
            guard let url = URL(string: normalized),
                  let scheme = url.scheme?.lowercased(),
                  scheme == "http" || scheme == "https" else {
                throw MavieError.invalidURL("Geçerli bir M3U adresi girin.")
            }
            var req = URLRequest(url: url)
            req.timeoutInterval = 25
            let (data, response) = try await URLSession.shared.data(for: req)
            if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
                throw MavieError.network("M3U listesi indirilemedi (HTTP \(http.statusCode)).")
            }
            guard let text = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) else {
                throw MavieError.parsing("M3U dosyası okunamadı.")
            }
            importM3uText(text, m3uUrl: normalized)
        } catch {
            lastError = error.localizedDescription
        }
    }

    public func connectXtream(host: String, username: String, password: String) async {
        isBusy = true
        lastError = nil
        defer { isBusy = false }
        do {
            let auth = try await XtreamClient.authenticate(host: host, username: username, password: password)
            async let liveCatsTask = XtreamClient.fetchCategories(host: host, username: username, password: password, kind: .live)
            async let vodCatsTask = XtreamClient.fetchCategories(host: host, username: username, password: password, kind: .vod)
            async let seriesCatsTask = XtreamClient.fetchCategories(host: host, username: username, password: password, kind: .series)

            let liveCats = (try? await liveCatsTask) ?? []
            let vodCats = (try? await vodCatsTask) ?? []
            let seriesCats = (try? await seriesCatsTask) ?? []

            let liveMap = Dictionary(uniqueKeysWithValues: liveCats.map { ($0.id, $0.name) })
            let vodMap = Dictionary(uniqueKeysWithValues: vodCats.map { ($0.id, $0.name) })
            let seriesMap = Dictionary(uniqueKeysWithValues: seriesCats.map { ($0.id, $0.name) })

            async let liveTask = XtreamClient.fetchStreams(host: host, username: username, password: password, kind: .live, categories: liveMap)
            async let vodTask = XtreamClient.fetchStreams(host: host, username: username, password: password, kind: .vod, categories: vodMap)
            async let seriesTask = XtreamClient.fetchStreams(host: host, username: username, password: password, kind: .series, categories: seriesMap)

            let liveItems = (try? await liveTask) ?? []
            let vodItems = (try? await vodTask) ?? []
            let seriesItems = (try? await seriesTask) ?? []

            sourceMode = .xtream
            connection.sourceType = .xtream
            connection.host = host
            connection.username = username
            connection.password = password
            categories = liveCats + vodCats + seriesCats
            items = liveItems + vodItems + seriesItems
            account = AccountInfo(
                id: "xtream_\(username)",
                username: username,
                host: host,
                name: "Xtream · \(username)",
                status: auth.status,
                expiresAt: auth.expiresAt,
                maxConnections: auth.maxConnections,
                sourceType: .xtream
            )
            statusBanner = "Xtream bağlandı: \(items.count) içerik."
            saveState()
        } catch {
            lastError = error.localizedDescription
        }
    }

    public func importLocalMediaFile(from sourceURL: URL) throws {
        let localDir = baseDirectory.appendingPathComponent("LocalMedia", isDirectory: true)
        try FileManager.default.createDirectory(at: localDir, withIntermediateDirectories: true)

        let rawName = sourceURL.lastPathComponent
        let sanitized = rawName
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "..", with: "_")
        let safeFileName = sanitized.isEmpty ? "video.mp4" : sanitized
        let digest = Insecure.SHA1.hash(data: Data(sourceURL.absoluteString.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        let destURL = localDir.appendingPathComponent("\(digest.prefix(10))_\(safeFileName)")

        if sourceURL.standardizedFileURL != destURL.standardizedFileURL {
            if FileManager.default.fileExists(atPath: destURL.path) {
                try FileManager.default.removeItem(at: destURL)
            }
            try FileManager.default.copyItem(at: sourceURL, to: destURL)
        }
        let originalName = sourceURL.deletingPathExtension().lastPathComponent
        addLocalMediaFile(url: destURL, displayName: originalName)
    }

    public func addLocalMediaFile(url: URL, displayName: String? = nil) {
        let fallbackName = url.deletingPathExtension().lastPathComponent
        let name = (displayName?.isEmpty == false) ? displayName! : fallbackName
        let ext = url.pathExtension.lowercased()
        let digest = Insecure.SHA1.hash(data: Data(url.absoluteString.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        let pid = "local_\(String(digest.prefix(12)))"
        let item = MediaItem(
            id: "vod:\(pid)",
            providerId: pid,
            name: name.isEmpty ? "Yerel Video" : name,
            kind: .vod,
            categoryId: "local_files",
            categoryName: "Yerel Dosyalar",
            extensionName: ext.isEmpty ? "mp4" : ext,
            addedAt: Date().timeIntervalSince1970,
            sourceUrl: url.absoluteString
        )
        if !categories.contains(where: { $0.id == "local_files" }) {
            categories.append(MediaCategory(id: "local_files", name: "Yerel Dosyalar", kind: .vod))
        }
        items.removeAll { $0.id == item.id }
        items.insert(item, at: 0)
        sourceMode = .local
        statusBanner = "\(item.name) kütüphaneye eklendi."
        saveState()
    }

    public func loadDetail(for item: MediaItem) async -> MediaDetail {
        if item.kind == .series && sourceMode == .xtream && !connection.host.isEmpty {
            if let detail = try? await XtreamClient.fetchSeriesDetail(
                host: connection.host,
                username: connection.username,
                password: connection.password,
                series: item
            ) {
                return detail
            }
        }
        if item.kind == .vod && sourceMode == .xtream && !connection.host.isEmpty {
            if let detail = try? await XtreamClient.fetchVodDetail(
                host: connection.host,
                username: connection.username,
                password: connection.password,
                item: item
            ) {
                return detail
            }
        }
        return MediaDetail(item: item)
    }

    public func resolvePlayableURL(for item: MediaItem) throws -> URL {
        if !item.sourceUrl.isEmpty, let url = URL(string: item.sourceUrl) {
            return url
        }
        if sourceMode == .xtream {
            return try XtreamClient.buildStreamURL(
                host: connection.host,
                username: connection.username,
                password: connection.password,
                item: item
            )
        }
        throw MavieError.invalidURL("Bu içerik için oynatılabilir yayın adresi bulunamadı.")
    }

    // MARK: - Favorites, Progress & Playlists

    public func isFavorite(_ item: MediaItem) -> Bool {
        favoriteIds.contains(item.id)
    }

    public func toggleFavorite(_ item: MediaItem) {
        if favoriteIds.contains(item.id) {
            favoriteIds.remove(item.id)
            favoriteCreatedAt.removeValue(forKey: item.id)
        } else {
            favoriteIds.insert(item.id)
            favoriteCreatedAt[item.id] = MavieDateParser.formatISO8601()
        }
        saveState()
    }

    public func progress(for item: MediaItem) -> WatchProgress? {
        progressByItem[item.id]
    }

    public func saveProgress(itemId: String, positionSeconds: Double, durationSeconds: Double) {
        guard durationSeconds > 0 else { return }
        let ratio = positionSeconds / durationSeconds
        let completed = ratio >= 0.92
        progressByItem[itemId] = WatchProgress(
            itemId: itemId,
            positionSeconds: completed ? durationSeconds : max(0, positionSeconds),
            durationSeconds: durationSeconds,
            completed: completed
        )
        saveState()
    }

    public func createPlaylist(name: String) {
        let clean = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        let list = Playlist(id: "pl_\(UUID().uuidString.prefix(8))", name: clean)
        playlists.append(list)
        saveState()
    }

    public func addItem(_ item: MediaItem, toPlaylist playlistId: String) {
        guard let idx = playlists.firstIndex(where: { $0.id == playlistId }) else { return }
        if !playlists[idx].itemIds.contains(item.id) {
            playlists[idx].itemIds.append(item.id)
            saveState()
        }
    }

    public func removePlaylist(id: String) {
        playlists.removeAll { $0.id == id }
        saveState()
    }

    // MARK: - Profiles (Unlimited & Free)

    @discardableResult
    public func addProfile(name: String, avatarColor: String = "#7C3AED", isKids: Bool = false, pin: String = "") throws -> UserProfile {
        let clean = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else {
            throw MavieError.validation("Profil adı boş olamaz.")
        }
        let hashedPin = pin.isEmpty ? "" : SHA256.hash(data: Data(pin.utf8)).map { String(format: "%02x", $0) }.joined()
        let profile = UserProfile(
            id: "prof_\(UUID().uuidString.prefix(8))",
            name: clean,
            avatarColor: avatarColor,
            isKids: isKids,
            hasPin: !hashedPin.isEmpty,
            pinHash: hashedPin,
            active: false
        )
        profiles.append(profile)
        saveState()
        return profile
    }

    public func switchProfile(id: String, pinAttempt: String = "") throws {
        guard let target = profiles.first(where: { $0.id == id }) else { return }
        if target.hasPin {
            let attemptHash = SHA256.hash(data: Data(pinAttempt.utf8)).map { String(format: "%02x", $0) }.joined()
            if attemptHash != target.pinHash {
                throw MavieError.validation("Profil PIN kodu hatalı.")
            }
        }
        for i in profiles.indices {
            profiles[i].active = (profiles[i].id == id)
        }
        saveState()
    }

    // MARK: - Home Sections & Search

    public var continueWatchingItems: [MediaItem] {
        items.filter { item in
            guard let p = progressByItem[item.id] else { return false }
            return !p.completed && p.positionSeconds > 5
        }
        .sorted { (progressByItem[$0.id]?.updatedAt ?? 0) > (progressByItem[$1.id]?.updatedAt ?? 0) }
    }

    public var favoriteItems: [MediaItem] {
        items.filter { favoriteIds.contains($0.id) }
    }

    public var recentMovies: [MediaItem] {
        items.filter { $0.kind == .vod }.sorted { $0.addedAt > $1.addedAt }
    }

    public var recentSeries: [MediaItem] {
        items.filter { $0.kind == .series }.sorted { $0.addedAt > $1.addedAt }
    }

    public func searchItems(query: String, kind: MediaKind? = nil) -> [MediaItem] {
        let needle = foldTurkish(query)
        return items.filter { item in
            if let kind, item.kind != kind { return false }
            if needle.isEmpty { return true }
            return foldTurkish(item.name).contains(needle)
                || foldTurkish(item.categoryName).contains(needle)
                || foldTurkish(item.genres).contains(needle)
        }
    }

    public func surpriseItem() -> MediaItem? {
        let playableVod = items.filter { $0.kind == .vod || $0.kind == .episode }
        if !playableVod.isEmpty {
            return playableVod.randomElement()
        }
        let playableAny = items.filter { $0.kind != .series }
        if !playableAny.isEmpty {
            return playableAny.randomElement()
        }
        return items.randomElement()
    }

    // MARK: - LAN Sync & Local Backup

    public func syncWithLanServer(address: String, pairingCode: String) async throws {
        isBusy = true
        lastError = nil
        defer { isBusy = false }
        connection.lanAddress = address
        let localPayload = buildSyncPayload(limitItems: 500)
        let data = try JSONEncoder().encode(localPayload)
        guard let dict = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw MavieError.parsing("Yerel yedek verisi JSON nesnesine dönüştürülemedi.")
        }
        let remoteObj = try await LanSyncClient.merge(address: address, code: pairingCode, localExportDictionary: dict)
        let rawData = try JSONSerialization.data(withJSONObject: remoteObj)
        let remotePayload: LibrarySyncPayload
        do {
            remotePayload = try JSONDecoder().decode(LibrarySyncPayload.self, from: rawData)
        } catch {
            throw MavieError.parsing("Masaüstü eşitleme verisi ayrıştırılamadı: \(error.localizedDescription)")
        }
        mergeSyncPayload(remotePayload)
        statusBanner = "Yerel ağ sunucusu ile eşitleme tamamlandı."
        saveState()
    }

    public func buildSyncPayload(limitItems: Int? = nil) -> LibrarySyncPayload {
        var referencedIds = Set(favoriteIds)
        referencedIds.formUnion(progressByItem.keys)
        for pl in playlists {
            referencedIds.formUnion(pl.itemIds)
        }

        var selectedItems: [MediaItem] = []
        var seenIds = Set<String>()
        for item in items where referencedIds.contains(item.id) && item.id == "\(item.kind.rawValue):\(item.providerId)" {
            if seenIds.insert(item.id).inserted {
                selectedItems.append(item)
            }
        }
        let cap = limitItems ?? items.count
        for item in items where selectedItems.count < cap && item.id == "\(item.kind.rawValue):\(item.providerId)" {
            if seenIds.insert(item.id).inserted {
                selectedItems.append(item)
            }
        }

        let nowIso = MavieDateParser.formatISO8601()
        let favRecords = favoriteIds.sorted().map { id in
            SyncFavoriteRecord(itemId: id, createdAt: favoriteCreatedAt[id] ?? nowIso)
        }

        return LibrarySyncPayload(
            version: 1,
            exportedAt: nowIso,
            items: selectedItems,
            favorites: favRecords,
            progress: Array(progressByItem.values),
            playlists: playlists,
            trackPreferences: Array(trackPreferencesByItem.values)
        )
    }

    public func exportBackupJSON() throws -> Data {
        let payload = buildSyncPayload()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try encoder.encode(payload)
    }

    public func importBackupJSON(_ data: Data) throws {
        let payload = try JSONDecoder().decode(LibrarySyncPayload.self, from: data)
        mergeSyncPayload(payload)
        statusBanner = "Yedek içe aktarıldı."
        saveState()
    }

    // MARK: - Persistence & Helpers

    private func mergeSyncPayload(_ payload: LibrarySyncPayload) {
        if !payload.items.isEmpty {
            var existingById = Dictionary(uniqueKeysWithValues: items.map { ($0.id, $0) })
            for remote in payload.items where existingById[remote.id] == nil {
                existingById[remote.id] = remote
            }
            items = Array(existingById.values)
        }
        for fav in payload.favorites {
            favoriteIds.insert(fav.itemId)
            if favoriteCreatedAt[fav.itemId] == nil {
                favoriteCreatedAt[fav.itemId] = fav.createdAt
            }
        }
        for p in payload.progress {
            if let existing = progressByItem[p.itemId] {
                if p.updatedAt > existing.updatedAt {
                    progressByItem[p.itemId] = p
                }
            } else {
                progressByItem[p.itemId] = p
            }
        }
        for pl in payload.playlists {
            if let idx = playlists.firstIndex(where: { $0.id == pl.id }) {
                for iid in pl.itemIds where !playlists[idx].itemIds.contains(iid) {
                    playlists[idx].itemIds.append(iid)
                }
            } else {
                playlists.append(pl)
            }
        }
        if !payload.playlistItems.isEmpty {
            let grouped = Dictionary(grouping: payload.playlistItems, by: \.playlistId)
            for idx in playlists.indices {
                if let entries = grouped[playlists[idx].id] {
                    for rec in entries.sorted(by: { $0.position < $1.position }) where !playlists[idx].itemIds.contains(rec.itemId) {
                        playlists[idx].itemIds.append(rec.itemId)
                    }
                }
            }
        }
        for pref in payload.trackPreferences {
            if let existing = trackPreferencesByItem[pref.itemId],
               let existingDate = MavieDateParser.parseISO8601(existing.updatedAt),
               let incomingDate = MavieDateParser.parseISO8601(pref.updatedAt),
               incomingDate <= existingDate {
                continue
            }
            trackPreferencesByItem[pref.itemId] = pref
        }
    }

    private func loadState() {
        guard let data = try? Data(contentsOf: storageURL),
              let state = try? JSONDecoder().decode(PersistedLibraryState.self, from: data) else {
            return
        }
        sourceMode = state.sourceMode
        items = state.items
        categories = state.categories
        favoriteIds = Set(state.favoriteIds)
        favoriteCreatedAt = state.favoriteCreatedAt
        progressByItem = state.progress
        playlists = state.playlists
        trackPreferencesByItem = Dictionary(uniqueKeysWithValues: state.trackPreferences.map { ($0.itemId, $0) })
        profiles = state.profiles
        connection = state.connection
        account = state.account
    }

    private func saveState() {
        let snapshot = PersistedLibraryState(
            sourceMode: sourceMode,
            items: Array(items.prefix(4000)),
            categories: categories,
            favoriteIds: Array(favoriteIds),
            favoriteCreatedAt: favoriteCreatedAt,
            progress: progressByItem,
            playlists: playlists,
            trackPreferences: Array(trackPreferencesByItem.values),
            profiles: profiles,
            connection: connection,
            account: account
        )
        if let data = try? JSONEncoder().encode(snapshot) {
            try? data.write(to: storageURL, options: [.atomic])
        }
    }

    private func foldTurkish(_ value: String) -> String {
        value
            .replacingOccurrences(of: "ı", with: "i")
            .replacingOccurrences(of: "İ", with: "i")
            .folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "tr_TR"))
            .lowercased()
    }
}
