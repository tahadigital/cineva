import CryptoKit
import Foundation
import SwiftUI

private struct PersistedProgressState: Codable, Sendable {
    var version: Int = 1
    var progress: [String: WatchProgress] = [:]
}

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
    @Published public private(set) var discoveryFeed: DiscoveryFeedPayload = DiscoveryFeedPayload()

    private let baseDirectory: URL
    private let storageURL: URL
    private let progressURL: URL
    private let discoveryCacheURL: URL
    private let credentialVault: CredentialVault
    private let progressIOQueue = DispatchQueue(label: "app.mavie.library.progress-io", qos: .utility)
    private var progressSaveWorkItem: DispatchWorkItem?
    private var favoriteCreatedAt: [String: String] = [:]
    private var trackPreferencesByItem: [String: SyncTrackPreferenceRecord] = [:]
    private var failedPinAttempts: [String: (count: Int, lockedUntil: Date?)] = [:]
    private var discoveryRefreshAttempt: TimeInterval = 0
    private var discoveryRefreshing = false

    private var localMediaDirectory: URL {
        baseDirectory.appendingPathComponent("LocalMedia", isDirectory: true)
    }

    public var hasSavedXtreamPassword: Bool {
        !connection.password.isEmpty
    }

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
        self.progressURL = baseDir.appendingPathComponent("progress_state.json")
        self.discoveryCacheURL = baseDir.appendingPathComponent("discovery-public.json")
        self.credentialVault = CredentialVault(
            fallbackFileURL: baseDir.appendingPathComponent(".credentials_vault.json"),
            useKeychain: storageDirectory == nil
        )

        loadState()
        if let data = try? Data(contentsOf: discoveryCacheURL),
           let cached = try? JSONDecoder().decode(DiscoveryFeedPayload.self, from: data) {
            discoveryFeed = cached
        }
        if profiles.isEmpty {
            profiles = [UserProfile(id: "default", name: "Ana Profil", avatarColor: "#7C3AED", active: true)]
        }
        if items.isEmpty && sourceMode == .demo {
            loadDemoCatalog(persist: false, clearError: false)
        }
    }

    public var discoveryResult: DiscoveryResult {
        DiscoveryEngine.build(
            catalog: items,
            progressByItem: progressByItem,
            favoriteIds: favoriteIds,
            feed: discoveryFeed
        )
    }

    public func refreshDiscoveryIfNeeded(force: Bool = false, session: URLSession = MavieHTTPClient.sharedSession) async {
        guard sourceMode != .demo else { return }
        let now = Date().timeIntervalSince1970
        if !force && now - discoveryFeed.updatedAt < 6 * 3600 { return }
        if discoveryRefreshing || (!force && now - discoveryRefreshAttempt < 900) { return }
        discoveryRefreshing = true
        discoveryRefreshAttempt = now
        defer { discoveryRefreshing = false }
        if let payload = await DiscoveryEngine.refreshPublicFeed(session: session) {
            discoveryFeed = payload
            if let data = try? JSONEncoder().encode(payload) {
                try? data.write(to: discoveryCacheURL, options: [.atomic])
            }
        }
    }

    // MARK: - Catalog Sources

    public func loadDemoCatalog(persist: Bool = true, clearError: Bool = true) {
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
        if clearError {
            lastError = nil
        }
        statusBanner = "4 açık lisanslı demo filmi yüklendi."
        if persist { saveState() }
    }

    public func importM3uText(_ text: String, m3uUrl: String = "") {
        let parsed = M3uParser.parse(text)
        guard !parsed.items.isEmpty else {
            statusBanner = nil
            lastError = "M3U listesinde geçerli yayın veya video adresi bulunamadı."
            return
        }
        sourceMode = .m3u
        connection.sourceType = .m3u
        if !m3uUrl.isEmpty { connection.m3uUrl = m3uUrl }
        if !parsed.epgUrl.isEmpty { connection.epgUrl = parsed.epgUrl }
        items = parsed.items
        categories = parsed.categories
        let safeHostLabel: String
        if m3uUrl.isEmpty {
            safeHostLabel = "Yerel Liste"
        } else if let host = URL(string: m3uUrl)?.host, !host.isEmpty {
            safeHostLabel = host
        } else {
            safeHostLabel = MavieHTTPClient.redactSensitiveURLs(in: m3uUrl)
        }
        account = AccountInfo(
            id: "m3u",
            username: "M3U",
            host: safeHostLabel,
            name: "M3U Kütüphanesi",
            status: "Active",
            sourceType: .m3u,
            epgUrl: parsed.epgUrl
        )
        statusBanner = "\(parsed.items.count) içerik M3U listesinden yüklendi."
        lastError = nil
        saveState()
    }

    public func clearSavedCredentials() {
        connection.host = ""
        connection.username = ""
        connection.password = ""
        connection.m3uUrl = ""
        connection.epgUrl = ""
        account.host = ""
        account.username = ""
        account.epgUrl = ""
        do {
            try credentialVault.clear()
        } catch {
            lastError = error.localizedDescription
            return
        }
        lastError = nil
        statusBanner = "Kayıtlı kaynak bilgileri temizlendi."
        saveState()
    }

    public func updateEpgUrl(_ raw: String) throws {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
            guard let url = URL(string: trimmed),
                  let scheme = url.scheme?.lowercased(),
                  scheme == "http" || scheme == "https",
                  let host = url.host,
                  !host.isEmpty else {
                throw MavieError.invalidURL("Geçerli bir XMLTV EPG adresi girin (http:// veya https://).")
            }
        }
        connection.epgUrl = trimmed
        account.epgUrl = trimmed
        lastError = nil
        statusBanner = trimmed.isEmpty ? "Özel EPG adresi temizlendi." : "XMLTV EPG adresi kaydedildi."
        saveState()
    }

    public func importM3uFromURL(_ urlString: String, session: URLSession = MavieHTTPClient.sharedSession) async {
        isBusy = true
        lastError = nil
        statusBanner = nil
        defer { isBusy = false }
        do {
            let trimmed = urlString.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else {
                throw MavieError.invalidURL("Geçerli bir M3U adresi girin.")
            }
            let hadScheme = trimmed.contains("://")
            let primaryString = hadScheme ? trimmed : "http://" + trimmed
            guard let primaryURL = URL(string: primaryString),
                  let scheme = primaryURL.scheme?.lowercased(),
                  scheme == "http" || scheme == "https",
                  let host = primaryURL.host,
                  !host.isEmpty else {
                throw MavieError.invalidURL("Geçerli bir M3U adresi girin.")
            }

            var resolvedURL = primaryURL
            let fetched: (Data, HTTPURLResponse)
            do {
                var req = URLRequest(url: primaryURL)
                req.timeoutInterval = 60
                fetched = try await MavieHTTPClient.fetchData(for: req, session: session, context: "M3U sunucusu")
            } catch is CancellationError {
                throw CancellationError()
            } catch let urlErr as URLError where urlErr.code == .cancelled {
                throw CancellationError()
            } catch let primaryErr {
                if !hadScheme, let fallbackURL = URL(string: "https://" + trimmed) {
                    var fallbackReq = URLRequest(url: fallbackURL)
                    fallbackReq.timeoutInterval = 60
                    do {
                        fetched = try await MavieHTTPClient.fetchData(for: fallbackReq, session: session, context: "M3U sunucusu")
                        resolvedURL = fallbackURL
                    } catch is CancellationError {
                        throw CancellationError()
                    } catch let urlErr as URLError where urlErr.code == .cancelled {
                        throw CancellationError()
                    } catch {
                        throw primaryErr
                    }
                } else {
                    throw primaryErr
                }
            }

            let (data, httpResp) = fetched
            guard !data.isEmpty else {
                throw MavieError.network("Sunucudan boş M3U yanıtı alındı.")
            }
            let text = MavieHTTPClient.decodeText(data, response: httpResp)
            importM3uText(text, m3uUrl: resolvedURL.absoluteString)
        } catch is CancellationError {
            lastError = nil
        } catch {
            lastError = MavieHTTPClient.classifyURLError(error, context: "M3U sunucusu")
        }
    }

    public func connectXtream(
        host: String,
        username: String,
        password: String,
        session: URLSession = MavieHTTPClient.sharedSession
    ) async {
        isBusy = true
        lastError = nil
        statusBanner = nil
        defer { isBusy = false }
        do {
            let trimmedHost = host.trimmingCharacters(in: .whitespacesAndNewlines)
            let hadScheme = trimmedHost.contains("://")
            var resolvedHost = trimmedHost
            let auth: XtreamAuthResult
            do {
                auth = try await XtreamClient.authenticate(host: resolvedHost, username: username, password: password, session: session)
            } catch is CancellationError {
                throw CancellationError()
            } catch let urlErr as URLError where urlErr.code == .cancelled {
                throw CancellationError()
            } catch let primaryErr {
                if !hadScheme, !trimmedHost.isEmpty {
                    let httpsHost = "https://" + trimmedHost
                    do {
                        auth = try await XtreamClient.authenticate(host: httpsHost, username: username, password: password, session: session)
                        resolvedHost = httpsHost
                    } catch is CancellationError {
                        throw CancellationError()
                    } catch let urlErr as URLError where urlErr.code == .cancelled {
                        throw CancellationError()
                    } catch {
                        throw primaryErr
                    }
                } else {
                    throw primaryErr
                }
            }

            let finalHost = resolvedHost

            @Sendable func fetchCatResult(_ kind: MediaKind) async -> Result<[MediaCategory], Error> {
                do {
                    return .success(try await XtreamClient.fetchCategories(host: finalHost, username: username, password: password, kind: kind, session: session))
                } catch {
                    return .failure(error)
                }
            }

            @Sendable func fetchStreamResult(_ kind: MediaKind, categories: [String: String]) async -> Result<[MediaItem], Error> {
                do {
                    return .success(try await XtreamClient.fetchStreams(host: finalHost, username: username, password: password, kind: kind, categories: categories, session: session))
                } catch {
                    return .failure(error)
                }
            }

            async let liveCatsTask = fetchCatResult(.live)
            async let vodCatsTask = fetchCatResult(.vod)
            async let seriesCatsTask = fetchCatResult(.series)

            let liveCatRes = await liveCatsTask
            let vodCatRes = await vodCatsTask
            let seriesCatRes = await seriesCatsTask

            func isCancelledError(_ err: Error) -> Bool {
                if err is CancellationError { return true }
                if let urlErr = err as? URLError, urlErr.code == .cancelled { return true }
                return false
            }

            var failedKinds: [String] = []
            func unwrapCategories(_ res: Result<[MediaCategory], Error>, label: String) throws -> [MediaCategory] {
                switch res {
                case .success(let list):
                    return list
                case .failure(let err):
                    if isCancelledError(err) { throw CancellationError() }
                    failedKinds.append(label)
                    return []
                }
            }

            let liveCats = try unwrapCategories(liveCatRes, label: "Canlı kategorileri")
            let vodCats = try unwrapCategories(vodCatRes, label: "Film kategorileri")
            let seriesCats = try unwrapCategories(seriesCatRes, label: "Dizi kategorileri")

            let liveMap = Dictionary(uniqueKeysWithValues: liveCats.map { ($0.id, $0.name) })
            let vodMap = Dictionary(uniqueKeysWithValues: vodCats.map { ($0.id, $0.name) })
            let seriesMap = Dictionary(uniqueKeysWithValues: seriesCats.map { ($0.id, $0.name) })

            async let liveTask = fetchStreamResult(.live, categories: liveMap)
            async let vodTask = fetchStreamResult(.vod, categories: vodMap)
            async let seriesTask = fetchStreamResult(.series, categories: seriesMap)

            let liveRes = await liveTask
            let vodRes = await vodTask
            let seriesRes = await seriesTask

            var failedStreams = 0
            var firstFailure: Error?
            var combinedItems: [MediaItem] = []

            for (label, res) in [("Canlı", liveRes), ("Film", vodRes), ("Dizi", seriesRes)] {
                switch res {
                case .success(let list):
                    combinedItems.append(contentsOf: list)
                case .failure(let err):
                    if isCancelledError(err) {
                        throw CancellationError()
                    }
                    failedStreams += 1
                    failedKinds.append(label)
                    if firstFailure == nil { firstFailure = err }
                }
            }

            if failedStreams == 3, let firstFailure {
                throw firstFailure
            }
            guard !combinedItems.isEmpty else {
                throw MavieError.network("Xtream sunucusunda oynatılabilir içerik bulunamadı.")
            }

            sourceMode = .xtream
            connection.sourceType = .xtream
            connection.host = resolvedHost
            connection.username = username
            connection.password = password
            categories = liveCats + vodCats + seriesCats
            items = combinedItems
            account = AccountInfo(
                id: "xtream_\(username)",
                username: username,
                host: resolvedHost,
                name: "Xtream · \(username)",
                status: auth.status,
                expiresAt: auth.expiresAt,
                maxConnections: auth.maxConnections,
                sourceType: .xtream
            )
            if failedKinds.isEmpty {
                statusBanner = "Xtream bağlandı: \(items.count) içerik."
            } else {
                statusBanner = "Xtream bağlandı: \(items.count) içerik (kısmi hata: \(failedKinds.joined(separator: ", ")))."
            }
            saveState()
        } catch is CancellationError {
            lastError = nil
        } catch {
            lastError = MavieHTTPClient.classifyURLError(error, context: "Xtream sunucusu")
        }
    }

    private static func localMediaDestination(for sourceURL: URL, localDir: URL) -> URL {
        let rawName = sourceURL.lastPathComponent
        let sanitized = rawName
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "..", with: "_")
        let safeFileName = sanitized.isEmpty ? "video.mp4" : sanitized
        let digest = Insecure.SHA1.hash(data: Data(sourceURL.absoluteString.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        return localDir.appendingPathComponent("\(digest.prefix(10))_\(safeFileName)")
    }

    public func importLocalMediaFile(from sourceURL: URL) throws {
        let localDir = localMediaDirectory
        try FileManager.default.createDirectory(at: localDir, withIntermediateDirectories: true)
        let destURL = Self.localMediaDestination(for: sourceURL, localDir: localDir)

        if sourceURL.standardizedFileURL != destURL.standardizedFileURL {
            if FileManager.default.fileExists(atPath: destURL.path) {
                try FileManager.default.removeItem(at: destURL)
            }
            try FileManager.default.copyItem(at: sourceURL, to: destURL)
        }
        let originalName = sourceURL.deletingPathExtension().lastPathComponent
        addLocalMediaFile(url: destURL, displayName: originalName)
    }

    public func importLocalMediaFileAsync(from sourceURL: URL) async throws {
        isBusy = true
        lastError = nil
        statusBanner = nil
        defer { isBusy = false }

        let localDir = localMediaDirectory
        let destURL = Self.localMediaDestination(for: sourceURL, localDir: localDir)
        let originalName = sourceURL.deletingPathExtension().lastPathComponent

        try await Task.detached(priority: .userInitiated) {
            try FileManager.default.createDirectory(at: localDir, withIntermediateDirectories: true)
            if sourceURL.standardizedFileURL.resolvingSymlinksInPath() != destURL.standardizedFileURL.resolvingSymlinksInPath() {
                let tmpURL = localDir.appendingPathComponent(".tmp_\(UUID().uuidString)_\(destURL.lastPathComponent)")
                defer { try? FileManager.default.removeItem(at: tmpURL) }
                try FileManager.default.copyItem(at: sourceURL, to: tmpURL)
                if FileManager.default.fileExists(atPath: destURL.path) {
                    try FileManager.default.removeItem(at: destURL)
                }
                try FileManager.default.moveItem(at: tmpURL, to: destURL)
            }
        }.value

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
        if !item.sourceUrl.isEmpty {
            guard let url = URL(string: item.sourceUrl),
                  let scheme = url.scheme?.lowercased() else {
                throw MavieError.invalidURL("Güvenli olmayan veya geçersiz yayın adresi.")
            }
            if scheme == "http" || scheme == "https" {
                guard let host = url.host, !host.isEmpty else {
                    throw MavieError.invalidURL("Güvenli olmayan veya geçersiz yayın adresi.")
                }
                return url
            }
            if scheme == "file" {
                let allowedRoot = localMediaDirectory.standardizedFileURL.resolvingSymlinksInPath().path
                let candidatePath = url.standardizedFileURL.resolvingSymlinksInPath().path
                guard candidatePath.hasPrefix(allowedRoot + "/") else {
                    throw MavieError.invalidURL("Güvenli olmayan veya geçersiz yayın adresi.")
                }
                return url
            }
            throw MavieError.invalidURL("Güvenli olmayan veya geçersiz yayın adresi.")
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

    public func resolvePlaybackPlan(for item: MediaItem) throws -> PlaybackSourcePlan {
        let primary = try resolvePlayableURL(for: item)
        let fallback = PlaybackRecoveryState.liveFallbackURL(
            for: item,
            failedURL: primary,
            sourceMode: sourceMode,
            host: connection.host,
            username: connection.username,
            password: connection.password
        )
        return PlaybackSourcePlan(
            primaryURL: primary,
            liveTSFallbackURL: fallback,
            isLive: item.kind == .live
        )
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

    public func saveProgress(itemId: String, positionSeconds: Double, durationSeconds: Double, flush: Bool = false) {
        guard durationSeconds > 0 else { return }
        let ratio = positionSeconds / durationSeconds
        let completed = ratio >= 0.92
        progressByItem[itemId] = WatchProgress(
            itemId: itemId,
            positionSeconds: completed ? durationSeconds : max(0, positionSeconds),
            durationSeconds: durationSeconds,
            completed: completed
        )
        scheduleProgressWrite(immediate: flush)
    }

    public func flushProgressPersistence() {
        scheduleProgressWrite(immediate: true)
    }

    private func scheduleProgressWrite(immediate: Bool) {
        progressSaveWorkItem?.cancel()
        progressSaveWorkItem = nil

        let snapshot = PersistedProgressState(progress: progressByItem)
        let targetURL = progressURL

        if immediate {
            progressIOQueue.sync {
                do {
                    let data = try JSONEncoder().encode(snapshot)
                    try Self.writeProtectedData(data, to: targetURL)
                } catch {
                    Task { @MainActor [weak self] in
                        self?.lastError = "İzleme ilerlemesi kaydedilemedi: \(error.localizedDescription)"
                    }
                }
            }
            return
        }

        let workItem = DispatchWorkItem { [weak self] in
            do {
                let data = try JSONEncoder().encode(snapshot)
                try Self.writeProtectedData(data, to: targetURL)
            } catch {
                Task { @MainActor [weak self] in
                    self?.lastError = "İzleme ilerlemesi kaydedilemedi: \(error.localizedDescription)"
                }
            }
        }
        progressSaveWorkItem = workItem
        progressIOQueue.asyncAfter(deadline: .now() + 1.5, execute: workItem)
    }

    public func trackPreference(for itemId: String) -> SyncTrackPreferenceData? {
        trackPreferencesByItem[itemId]?.data
    }

    public func saveTrackPreference(
        itemId: String,
        audio: String?,
        subtitle: String?,
        clientAudio: String? = nil,
        clientSubtitle: String? = nil
    ) {
        let data = SyncTrackPreferenceData(
            audio: audio,
            subtitle: subtitle,
            clientAudio: clientAudio,
            clientSubtitle: clientSubtitle
        )
        trackPreferencesByItem[itemId] = SyncTrackPreferenceRecord(itemId: itemId, data: data)
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
        let hashedPin = pin.isEmpty ? "" : Self.makeSaltedPBKDF2PinHash(pin)
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
        guard let targetIdx = profiles.firstIndex(where: { $0.id == id }) else { return }
        let target = profiles[targetIdx]
        if target.hasPin {
            let now = Date()
            if let entry = failedPinAttempts[id], let lockedUntil = entry.lockedUntil, now < lockedUntil {
                let remaining = max(1, Int(ceil(lockedUntil.timeIntervalSince(now))))
                throw MavieError.validation("Çok fazla hatalı PIN denemesi. \(remaining) saniye sonra tekrar deneyin.")
            }

            let verification = Self.verifyPin(pinAttempt, storedHash: target.pinHash)
            if !verification.matched {
                let prevCount = (failedPinAttempts[id]?.lockedUntil.map { $0 <= now } ?? false) ? 0 : (failedPinAttempts[id]?.count ?? 0)
                let newCount = prevCount + 1
                if newCount >= 5 {
                    failedPinAttempts[id] = (count: newCount, lockedUntil: now.addingTimeInterval(30))
                    throw MavieError.validation("Çok fazla hatalı PIN denemesi. 30 saniye sonra tekrar deneyin.")
                } else {
                    failedPinAttempts[id] = (count: newCount, lockedUntil: nil)
                    throw MavieError.validation("Profil PIN kodu hatalı.")
                }
            }
            failedPinAttempts.removeValue(forKey: id)
            if verification.needsUpgrade {
                profiles[targetIdx].pinHash = Self.makeSaltedPBKDF2PinHash(pinAttempt)
            }
        }
        for i in profiles.indices {
            profiles[i].active = (profiles[i].id == id)
        }
        saveState()
    }

    public func removeProfile(id: String) throws {
        guard id != "default", profiles.count > 1 else {
            throw MavieError.validation("Varsayılan veya tek profil silinemez.")
        }
        guard let idx = profiles.firstIndex(where: { $0.id == id }) else {
            return
        }
        let wasActive = profiles[idx].active
        profiles.remove(at: idx)
        if wasActive || !profiles.contains(where: \.active) {
            if let defIdx = profiles.firstIndex(where: { $0.id == "default" }) {
                profiles[defIdx].active = true
            } else if !profiles.isEmpty {
                profiles[0].active = true
            }
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

    public func syncWithLanServer(address: String, pairingCode: String, session: URLSession = MavieHTTPClient.lanSession) async throws {
        isBusy = true
        lastError = nil
        defer { isBusy = false }
        connection.lanAddress = address
        let localPayload = buildSyncPayload(limitItems: 500)
        let data = try JSONEncoder().encode(localPayload)
        guard let dict = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw MavieError.parsing("Yerel yedek verisi JSON nesnesine dönüştürülemedi.")
        }
        let remoteObj = try await LanSyncClient.merge(address: address, code: pairingCode, localExportDictionary: dict, session: session)
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
        if !remotePayload.progress.isEmpty {
            flushProgressPersistence()
        }
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
        guard data.count <= LanSyncClient.maxBackupBytes else {
            throw MavieError.validation("Yedek dosyası çok büyük (en fazla 25 MB).")
        }
        let payload = try JSONDecoder().decode(LibrarySyncPayload.self, from: data)
        mergeSyncPayload(payload)
        statusBanner = "Yedek içe aktarıldı."
        saveState()
        if !payload.progress.isEmpty {
            flushProgressPersistence()
        }
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
        for pref in payload.trackPreferences + (payload.appleTrackPreferences ?? []) {
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
        let fm = FileManager.default
        var legacyProgress: [String: WatchProgress] = [:]
        var needsResaveLibraryState = false

        if fm.fileExists(atPath: storageURL.path) {
            do {
                let data = try Data(contentsOf: storageURL)
                let state = try JSONDecoder().decode(PersistedLibraryState.self, from: data)
                sourceMode = state.sourceMode
                items = state.items
                categories = state.categories
                favoriteIds = Set(state.favoriteIds)
                favoriteCreatedAt = state.favoriteCreatedAt
                legacyProgress = state.progress
                playlists = state.playlists
                trackPreferencesByItem = Dictionary(uniqueKeysWithValues: state.trackPreferences.map { ($0.itemId, $0) })
                profiles = state.profiles
                connection = state.connection
                account = state.account
            } catch {
                let backupName = quarantineCorruptFile(at: storageURL, prefix: "library_state")
                lastError = "Kütüphane dosyası bozuk olduğu için yedeklendi (\(backupName))."
            }
        }

        let hadProgressFile = fm.fileExists(atPath: progressURL.path)
        var loadedProgress: [String: WatchProgress] = [:]
        if hadProgressFile {
            do {
                let progData = try Data(contentsOf: progressURL)
                let progState = try JSONDecoder().decode(PersistedProgressState.self, from: progData)
                loadedProgress = progState.progress
            } catch {
                let backupName = quarantineCorruptFile(at: progressURL, prefix: "progress_state")
                let msg = "İzleme ilerlemesi dosyası bozuk olduğu için yedeklendi (\(backupName))."
                lastError = lastError.map { "\($0) \(msg)" } ?? msg
            }
        }

        if !legacyProgress.isEmpty {
            for (itemId, legacyEntry) in legacyProgress {
                if let current = loadedProgress[itemId] {
                    if legacyEntry.updatedAt > current.updatedAt {
                        loadedProgress[itemId] = legacyEntry
                    }
                } else {
                    loadedProgress[itemId] = legacyEntry
                }
            }
        }
        progressByItem = loadedProgress

        if !legacyProgress.isEmpty {
            do {
                let encoded = try JSONEncoder().encode(PersistedProgressState(progress: loadedProgress))
                try Self.writeProtectedData(encoded, to: progressURL)
                needsResaveLibraryState = true
            } catch {
                let msg = "İzleme ilerlemesi taşınamadı: \(error.localizedDescription)"
                lastError = lastError.map { "\($0) \(msg)" } ?? msg
            }
        }

        let vaultCreds = credentialVault.load()
        let hadLegacyPlaintextSecrets = !connection.password.isEmpty || !connection.m3uUrl.isEmpty || !connection.epgUrl.isEmpty
        if connection.password.isEmpty && !vaultCreds.xtreamPassword.isEmpty {
            connection.password = vaultCreds.xtreamPassword
        }
        if connection.m3uUrl.isEmpty && !vaultCreds.m3uUrl.isEmpty {
            connection.m3uUrl = vaultCreds.m3uUrl
        }
        if connection.epgUrl.isEmpty && !vaultCreds.epgUrl.isEmpty {
            connection.epgUrl = vaultCreds.epgUrl
        }
        if account.epgUrl.isEmpty && !connection.epgUrl.isEmpty {
            account.epgUrl = connection.epgUrl
        }
        if !account.host.isEmpty && (account.host.contains("://") || account.host.contains("?")) {
            let redactedHost = URL(string: account.host)?.host ?? MavieHTTPClient.redactSensitiveURLs(in: account.host)
            if redactedHost != account.host {
                account.host = redactedHost
                needsResaveLibraryState = true
            }
        }

        if hadLegacyPlaintextSecrets {
            needsResaveLibraryState = true
        }
        if needsResaveLibraryState {
            saveState()
        }
    }

    private func quarantineCorruptFile(at url: URL, prefix: String) -> String {
        let ts = Int(Date().timeIntervalSince1970)
        var backupName = "\(prefix).corrupt.\(ts).json"
        var backupURL = url.deletingLastPathComponent().appendingPathComponent(backupName)
        if FileManager.default.fileExists(atPath: backupURL.path) {
            backupName = "\(prefix).corrupt.\(ts)_\(UUID().uuidString.prefix(6)).json"
            backupURL = url.deletingLastPathComponent().appendingPathComponent(backupName)
        }
        do {
            try FileManager.default.moveItem(at: url, to: backupURL)
        } catch {
            if (try? FileManager.default.copyItem(at: url, to: backupURL)) != nil {
                try? FileManager.default.removeItem(at: url)
            }
        }
        return backupName
    }

    private func saveState() {
        let creds = StoredCredentials(
            xtreamPassword: connection.password,
            m3uUrl: connection.m3uUrl,
            epgUrl: connection.epgUrl
        )
        do {
            try credentialVault.save(creds)
        } catch {
            lastError = "Kimlik bilgileri kaydedilemedi: \(error.localizedDescription)"
        }

        var scrubbedConnection = connection
        scrubbedConnection.password = ""
        scrubbedConnection.m3uUrl = ""
        scrubbedConnection.epgUrl = ""

        var scrubbedAccount = account
        scrubbedAccount.epgUrl = ""
        if !scrubbedAccount.host.isEmpty && (scrubbedAccount.host.contains("://") || scrubbedAccount.host.contains("?")) {
            scrubbedAccount.host = URL(string: scrubbedAccount.host)?.host ?? MavieHTTPClient.redactSensitiveURLs(in: scrubbedAccount.host)
        }

        let snapshot = PersistedLibraryState(
            sourceMode: sourceMode,
            items: items,
            categories: categories,
            favoriteIds: Array(favoriteIds),
            favoriteCreatedAt: favoriteCreatedAt,
            progress: [:],
            playlists: playlists,
            trackPreferences: Array(trackPreferencesByItem.values),
            profiles: profiles,
            connection: scrubbedConnection,
            account: scrubbedAccount
        )
        do {
            let data = try JSONEncoder().encode(snapshot)
            try Self.writeProtectedData(data, to: storageURL)
        } catch {
            lastError = "Kütüphane durumu kaydedilemedi: \(error.localizedDescription)"
        }
    }

    nonisolated private static func writeProtectedData(_ data: Data, to url: URL) throws {
        #if os(iOS)
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: url, options: [.atomic])
        #endif
    }

    private static let pinIterations = 10_000

    private static func makeSaltedPBKDF2PinHash(_ pin: String) -> String {
        let key = SymmetricKey(size: .bits128)
        let salt = key.withUnsafeBytes { Data($0) }
        let dk = pbkdf2HMACSHA256(password: Data(pin.utf8), salt: salt, iterations: pinIterations, keyByteCount: 32)
        return "pbkdf2_sha256$\(pinIterations)$\(hexString(salt))$\(hexString(dk))"
    }

    private static func verifyPin(_ attempt: String, storedHash: String) -> (matched: Bool, needsUpgrade: Bool) {
        if storedHash.hasPrefix("pbkdf2_sha256$") {
            let parts = storedHash.split(separator: "$", omittingEmptySubsequences: false)
            guard parts.count == 4,
                  let iterations = Int(parts[1]),
                  iterations > 0,
                  let salt = dataFromHex(String(parts[2])),
                  let expectedDK = dataFromHex(String(parts[3])) else {
                return (false, false)
            }
            let derived = pbkdf2HMACSHA256(
                password: Data(attempt.utf8),
                salt: salt,
                iterations: iterations,
                keyByteCount: expectedDK.count
            )
            return (constantTimeEquals(derived, expectedDK), false)
        }

        let legacyDigest = SHA256.hash(data: Data(attempt.utf8))
        let legacyBytes = Data(legacyDigest)
        guard let storedBytes = dataFromHex(storedHash) else {
            return (false, false)
        }
        let matched = constantTimeEquals(legacyBytes, storedBytes)
        return (matched, matched)
    }

    private static func pbkdf2HMACSHA256(password: Data, salt: Data, iterations: Int, keyByteCount: Int) -> Data {
        let hashLen = 32
        let blockCount = Int(ceil(Double(keyByteCount) / Double(hashLen)))
        let key = SymmetricKey(data: password)
        var derived = Data()
        derived.reserveCapacity(blockCount * hashLen)

        for blockIndex in 1...max(1, blockCount) {
            var blockInput = salt
            var beIndex = UInt32(blockIndex).bigEndian
            withUnsafeBytes(of: &beIndex) { blockInput.append(contentsOf: $0) }

            var u = Data(HMAC<SHA256>.authenticationCode(for: blockInput, using: key))
            var t = u
            if iterations > 1 {
                for _ in 2...iterations {
                    u = Data(HMAC<SHA256>.authenticationCode(for: u, using: key))
                    for i in 0..<hashLen {
                        t[i] ^= u[i]
                    }
                }
            }
            derived.append(t)
        }
        return derived.prefix(keyByteCount)
    }

    private static func constantTimeEquals(_ lhs: Data, _ rhs: Data) -> Bool {
        guard lhs.count == rhs.count else { return false }
        var diff: UInt8 = 0
        for (a, b) in zip(lhs, rhs) {
            diff |= (a ^ b)
        }
        return diff == 0
    }

    private static func hexString(_ data: Data) -> String {
        data.map { String(format: "%02x", $0) }.joined()
    }

    private static func dataFromHex(_ hex: String) -> Data? {
        let chars = Array(hex)
        guard chars.count % 2 == 0, !chars.isEmpty else { return nil }
        var data = Data(capacity: chars.count / 2)
        var i = 0
        while i < chars.count {
            let pair = String([chars[i], chars[i + 1]])
            guard let byte = UInt8(pair, radix: 16) else { return nil }
            data.append(byte)
            i += 2
        }
        return data
    }

    private func foldTurkish(_ value: String) -> String {
        value
            .replacingOccurrences(of: "ı", with: "i")
            .replacingOccurrences(of: "İ", with: "i")
            .folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "tr_TR"))
            .lowercased()
    }
}
