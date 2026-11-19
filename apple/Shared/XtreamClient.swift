import Foundation

public struct XtreamAuthResult: Codable, Sendable, Equatable {
    public var status: String
    public var expiresAt: String
    public var maxConnections: Int
}

public enum XtreamClient {
    private static let providerIdAllowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")

    public static func validateBaseURL(_ raw: String) throws -> URL {
        var trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw VrelioError.invalidURL("Sunucu adresi boş olamaz.")
        }
        if !trimmed.contains("://") {
            trimmed = "http://" + trimmed
        }
        guard let url = URL(string: trimmed),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = url.host,
              !host.isEmpty else {
            throw VrelioError.invalidURL("Geçerli bir Xtream sunucu adresi girin.")
        }
        if url.user != nil || url.password != nil {
            throw VrelioError.validation("Kullanıcı adı ve parolayı ayrı alanlara girin.")
        }
        return url
    }

    public static func buildPlayerApiURL(host: String, username: String, password: String, action: String? = nil, extraParams: [String: String] = [:]) throws -> URL {
        let base = try validateBaseURL(host)
        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw VrelioError.invalidURL("Sunucu adresi ayrıştırılamadı.")
        }
        var path = components.path
        while path.hasSuffix("/") { path.removeLast() }
        components.path = path + "/player_api.php"
        var queryItems = [
            URLQueryItem(name: "username", value: username),
            URLQueryItem(name: "password", value: password),
        ]
        if let action, !action.isEmpty {
            queryItems.append(URLQueryItem(name: "action", value: action))
        }
        for (key, value) in extraParams.sorted(by: { $0.key < $1.key }) {
            queryItems.append(URLQueryItem(name: key, value: value))
        }
        components.queryItems = queryItems
        guard let finalURL = components.url else {
            throw VrelioError.invalidURL("API adresi oluşturulamadı.")
        }
        return finalURL
    }

    public static func buildStreamURL(
        host: String,
        username: String,
        password: String,
        item: MediaItem,
        preferHLSForLive: Bool = true
    ) throws -> URL {
        if !item.sourceUrl.isEmpty, let direct = URL(string: item.sourceUrl) {
            return direct
        }
        let base = try validateBaseURL(host)
        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw VrelioError.invalidURL("Yayın adresi oluşturulamadı.")
        }
        var path = components.path
        while path.hasSuffix("/") { path.removeLast() }

        let safeExt = item.extensionName.isEmpty ? "mp4" : item.extensionName
        switch item.kind {
        case .live:
            let liveExt = preferHLSForLive ? "m3u8" : (safeExt.isEmpty ? "ts" : safeExt)
            components.path = "\(path)/live/\(username)/\(password)/\(item.providerId).\(liveExt)"
        case .vod:
            components.path = "\(path)/movie/\(username)/\(password)/\(item.providerId).\(safeExt)"
        case .episode:
            components.path = "\(path)/series/\(username)/\(password)/\(item.providerId).\(safeExt)"
        case .series:
            throw VrelioError.validation("Dizi öğesi doğrudan oynatılamaz; lütfen bir bölüm seçin.")
        }
        guard let url = components.url else {
            throw VrelioError.invalidURL("Yayın URL’si geçersiz.")
        }
        return url
    }

    // MARK: - Pure Parsers (Offline Testable)

    public static func parseAuth(data: Data) throws -> XtreamAuthResult {
        guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw VrelioError.parsing("Xtream oturum yanıtı JSON nesnesi değil.")
        }
        let userInfo = (obj["user_info"] as? [String: Any]) ?? obj
        let authFlag = intValue(userInfo["auth"])
        let status = stringValue(userInfo["status"], default: authFlag == 1 ? "Active" : "")
        if authFlag == 0 && status.lowercased() != "active" {
            throw VrelioError.validation("Xtream kullanıcı adı veya parola doğrulanamadı.")
        }
        let exp = stringValue(userInfo["exp_date"])
        let maxConn = max(1, intValue(userInfo["max_connections"], default: 1))
        return XtreamAuthResult(status: status.isEmpty ? "Active" : status, expiresAt: exp, maxConnections: maxConn)
    }

    public static func parseCategories(data: Data, kind: MediaKind) throws -> [MediaCategory] {
        guard let rows = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            throw VrelioError.parsing("Kategori listesi beklenilen formatta değil.")
        }
        return rows.compactMap { row in
            let id = stringValue(row["category_id"]).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty else { return nil }
            let name = String(stringValue(row["category_name"], default: "Diğer").prefix(500))
            return MediaCategory(id: id, name: name.isEmpty ? "Diğer" : name, kind: kind)
        }
    }

    public static func parseStreams(
        data: Data,
        kind: MediaKind,
        categories: [String: String] = [:],
        parent: MediaItem? = nil,
        seasonNumber: Int = 0
    ) throws -> [MediaItem] {
        guard let rows = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            throw VrelioError.parsing("İçerik listesi beklenilen formatta değil.")
        }
        return rows.compactMap { row in
            itemFromDictionary(row, kind: kind, categories: categories, parent: parent, seasonNumber: seasonNumber)
        }
    }

    public static func parseSeriesDetail(data: Data, series: MediaItem) throws -> MediaDetail {
        guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw VrelioError.parsing("Dizi detayı okunamadı.")
        }
        let info = (obj["info"] as? [String: Any]) ?? [:]
        var updatedSeries = series
        let plot = stringValue(info["plot"], default: series.plot)
        let genres = stringValue(info["genre"], default: series.genres)
        let cast = stringValue(info["cast"], default: series.cast)
        let director = stringValue(info["director"], default: series.director)
        let cover = safeImage(stringValue(info["cover"], default: series.poster))
        let backdrop = safeImage(extractBackdrop(from: info) ?? series.backdrop)
        updatedSeries.plot = String(plot.prefix(24000))
        updatedSeries.genres = genres
        updatedSeries.cast = cast
        updatedSeries.director = director
        if !cover.isEmpty { updatedSeries.poster = cover }
        if !backdrop.isEmpty { updatedSeries.backdrop = backdrop }

        var allEpisodes: [MediaItem] = []
        if let episodesDict = obj["episodes"] as? [String: Any] {
            for (seasonKey, rawList) in episodesDict {
                guard let list = rawList as? [[String: Any]] else { continue }
                let sNum = Int(seasonKey) ?? 1
                for row in list {
                    if let ep = itemFromDictionary(row, kind: .episode, parent: updatedSeries, seasonNumber: sNum) {
                        allEpisodes.append(ep)
                    }
                }
            }
        } else if let episodesArray = obj["episodes"] as? [Any] {
            for (index, entry) in episodesArray.enumerated() {
                if let subList = entry as? [[String: Any]] {
                    for row in subList {
                        if let ep = itemFromDictionary(row, kind: .episode, parent: updatedSeries, seasonNumber: index + 1) {
                            allEpisodes.append(ep)
                        }
                    }
                } else if let row = entry as? [String: Any] {
                    if let ep = itemFromDictionary(row, kind: .episode, parent: updatedSeries, seasonNumber: 1) {
                        allEpisodes.append(ep)
                    }
                }
            }
        }

        var deduped: [MediaItem] = []
        var seen = Set<String>()
        for ep in allEpisodes where seen.insert(ep.id).inserted {
            deduped.append(ep)
        }

        let grouped = Dictionary(grouping: deduped) { max(1, $0.season) }
        let seasons = grouped.keys.sorted().map { num in
            let eps = (grouped[num] ?? []).sorted { lhs, rhs in
                if lhs.episode != rhs.episode { return lhs.episode < rhs.episode }
                return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
            return Season(number: num, name: "\(num). Sezon", episodes: eps)
        }

        return MediaDetail(item: updatedSeries, seasons: seasons, genres: genres, cast: cast, director: director)
    }

    public static func parseVodDetail(data: Data, item: MediaItem) throws -> MediaDetail {
        guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return MediaDetail(item: item)
        }
        let info = (obj["info"] as? [String: Any]) ?? [:]
        var updated = item
        let plot = stringValue(info["plot"], default: item.plot)
        let genres = stringValue(info["genre"], default: item.genres)
        let cast = stringValue(info["cast"], default: item.cast)
        let director = stringValue(info["director"], default: item.director)
        let duration = parseDuration(info["duration_secs"]) ?? parseDuration(info["duration"]) ?? item.durationSeconds
        let poster = safeImage(stringValue(info["movie_image"], default: stringValue(info["cover"], default: item.poster)))
        let backdrop = safeImage(extractBackdrop(from: info) ?? item.backdrop)
        let releaseYear = extractYear(from: stringValue(info["releasedate"], default: stringValue(info["releaseDate"], default: item.year)), fallbackTitle: item.name)
        updated.plot = String(plot.prefix(24000))
        updated.genres = genres
        updated.cast = cast
        updated.director = director
        if duration > 0 { updated.durationSeconds = duration }
        if !poster.isEmpty { updated.poster = poster }
        if !backdrop.isEmpty { updated.backdrop = backdrop }
        if !releaseYear.isEmpty { updated.year = releaseYear }
        return MediaDetail(item: updated, genres: genres, cast: cast, director: director)
    }

    public static func itemFromDictionary(
        _ row: [String: Any],
        kind: MediaKind,
        categories: [String: String] = [:],
        parent: MediaItem? = nil,
        seasonNumber: Int = 0
    ) -> MediaItem? {
        let rawId: String
        switch kind {
        case .series: rawId = stringValue(row["series_id"])
        case .episode: rawId = stringValue(row["id"])
        case .live, .vod: rawId = stringValue(row["stream_id"])
        }
        let providerId = rawId.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !providerId.isEmpty,
              providerId.count <= 100,
              providerId.unicodeScalars.allSatisfy({ providerIdAllowed.contains($0) }) else {
            return nil
        }

        let info = (row["info"] as? [String: Any]) ?? [:]
        let video = (info["video"] as? [String: Any]) ?? [:]
        let audio = (info["audio"] as? [String: Any]) ?? [:]
        let categoryId = stringValue(row["category_id"], default: parent?.categoryId ?? "")
        let poster = [
            stringValue(row["stream_icon"]),
            stringValue(row["cover"]),
            stringValue(row["movie_image"]),
            stringValue(info["movie_image"]),
            parent?.poster ?? "",
        ].first { !$0.isEmpty } ?? ""

        let backdrop = extractBackdrop(from: row) ?? extractBackdrop(from: info) ?? parent?.backdrop ?? ""
        let rawName = stringValue(row["name"], default: stringValue(row["title"], default: "İsimsiz içerik"))
        let name = String((rawName.isEmpty ? "İsimsiz içerik" : rawName).prefix(1000))
        let rawYear = [
            stringValue(row["year"]),
            stringValue(row["releaseDate"]),
            stringValue(row["releasedate"]),
            stringValue(info["releasedate"]),
        ].first { !$0.isEmpty } ?? ""
        let year = extractYear(from: rawYear, fallbackTitle: name)
        let defaultExt = kind == .live ? "ts" : "mp4"
        let ext = stringValue(row["container_extension"], default: defaultExt).lowercased()
        let validExt = (1...10).contains(ext.count) && ext.allSatisfy { $0.isLetter || $0.isNumber } ? ext : defaultExt

        let ratingRaw = doubleValue(row["rating"]) ?? ((doubleValue(row["rating_5based"]) ?? 0) * 2.0)
        let rating = min(10.0, max(0.0, ratingRaw.isFinite ? ratingRaw : 0.0))
        let duration = parseDuration(info["duration_secs"]) ?? parseDuration(info["duration"]) ?? 0.0
        let seasonVal = max(0, intValue(row["season"], default: seasonNumber))
        let episodeVal = max(0, intValue(row["episode_num"], default: intValue(row["episode"], default: 0)))
        let addedVal = Double(stringValue(row["added"], default: stringValue(row["last_modified"]))) ?? 0

        return MediaItem(
            id: "\(kind.rawValue):\(providerId)",
            providerId: providerId,
            name: name,
            kind: kind,
            categoryId: categoryId,
            categoryName: categories[categoryId] ?? parent?.categoryName ?? "",
            poster: safeImage(poster),
            backdrop: safeImage(backdrop),
            year: year,
            rating: rating,
            extensionName: validExt,
            durationSeconds: duration,
            plot: String(stringValue(info["plot"], default: stringValue(row["plot"])).prefix(24000)),
            season: seasonVal,
            episode: episodeVal,
            parentId: parent?.id,
            addedAt: addedVal,
            videoCodec: stringValue(video["codec_name"]),
            audioCodec: stringValue(audio["codec_name"]),
            genres: stringValue(info["genre"], default: stringValue(row["genre"])),
            cast: stringValue(info["cast"], default: stringValue(row["cast"])),
            director: stringValue(info["director"], default: stringValue(row["director"]))
        )
    }

    // MARK: - Live Async Requests

    public static func authenticate(host: String, username: String, password: String, session: URLSession = .shared) async throws -> XtreamAuthResult {
        let url = try buildPlayerApiURL(host: host, username: username, password: password)
        let data = try await fetchData(url: url, session: session)
        return try parseAuth(data: data)
    }

    public static func fetchCategories(host: String, username: String, password: String, kind: MediaKind, session: URLSession = .shared) async throws -> [MediaCategory] {
        let action: String
        switch kind {
        case .live: action = "get_live_categories"
        case .vod: action = "get_vod_categories"
        case .series, .episode: action = "get_series_categories"
        }
        let url = try buildPlayerApiURL(host: host, username: username, password: password, action: action)
        let data = try await fetchData(url: url, session: session)
        return try parseCategories(data: data, kind: kind)
    }

    public static func fetchStreams(host: String, username: String, password: String, kind: MediaKind, categories: [String: String], session: URLSession = .shared) async throws -> [MediaItem] {
        let action: String
        switch kind {
        case .live: action = "get_live_streams"
        case .vod: action = "get_vod_streams"
        case .series, .episode: action = "get_series"
        }
        let url = try buildPlayerApiURL(host: host, username: username, password: password, action: action)
        let data = try await fetchData(url: url, session: session)
        return try parseStreams(data: data, kind: kind, categories: categories)
    }

    public static func fetchSeriesDetail(host: String, username: String, password: String, series: MediaItem, session: URLSession = .shared) async throws -> MediaDetail {
        let url = try buildPlayerApiURL(host: host, username: username, password: password, action: "get_series_info", extraParams: ["series_id": series.providerId])
        let data = try await fetchData(url: url, session: session)
        return try parseSeriesDetail(data: data, series: series)
    }

    public static func fetchVodDetail(host: String, username: String, password: String, item: MediaItem, session: URLSession = .shared) async throws -> MediaDetail {
        let url = try buildPlayerApiURL(host: host, username: username, password: password, action: "get_vod_info", extraParams: ["vod_id": item.providerId])
        let data = try await fetchData(url: url, session: session)
        return try parseVodDetail(data: data, item: item)
    }

    private static func fetchData(url: URL, session: URLSession) async throws -> Data {
        var req = URLRequest(url: url)
        req.timeoutInterval = 25
        req.setValue("Vrelio/2.1", forHTTPHeaderField: "User-Agent")
        do {
            let (data, response) = try await session.data(for: req)
            if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
                throw VrelioError.network("Xtream sunucusu HTTP \(http.statusCode) döndürdü.")
            }
            return data
        } catch let err as VrelioError {
            throw err
        } catch {
            throw VrelioError.network("Xtream sunucusuna bağlanılamadı: \(error.localizedDescription)")
        }
    }

    // MARK: - Helpers

    private static func stringValue(_ raw: Any?, default fallback: String = "") -> String {
        guard let raw, !(raw is NSNull) else { return fallback }
        if let str = raw as? String {
            return str == "null" ? fallback : str
        }
        if let num = raw as? NSNumber {
            return num.stringValue
        }
        return fallback
    }

    private static func intValue(_ raw: Any?, default fallback: Int = 0) -> Int {
        if let i = raw as? Int { return i }
        if let n = raw as? NSNumber { return n.intValue }
        if let s = raw as? String, let parsed = Int(s.trimmingCharacters(in: .whitespaces)) { return parsed }
        return fallback
    }

    private static func doubleValue(_ raw: Any?) -> Double? {
        if let d = raw as? Double { return d }
        if let n = raw as? NSNumber { return n.doubleValue }
        if let s = raw as? String { return Double(s.trimmingCharacters(in: .whitespaces)) }
        return nil
    }

    private static func parseDuration(_ raw: Any?) -> Double? {
        guard let raw, !(raw is NSNull) else { return nil }
        if let str = raw as? String, str.contains(":") {
            let parts = str.split(separator: ":").compactMap { Double($0) }
            guard !parts.isEmpty else { return nil }
            let total = parts.reduce(0.0) { $0 * 60.0 + $1 }
            return total > 0 ? total : nil
        }
        if let val = doubleValue(raw), val.isFinite, val > 0 {
            return val
        }
        return nil
    }

    private static func extractBackdrop(from dict: [String: Any]) -> String? {
        if let list = dict["backdrop_path"] as? [Any], let first = list.first as? String, !first.isEmpty {
            return first
        }
        let raw = stringValue(dict["backdrop_path"])
        if !raw.isEmpty && !raw.hasPrefix("[") {
            return raw
        }
        return nil
    }

    private static func safeImage(_ value: String) -> String {
        let lower = value.lowercased()
        if lower.hasPrefix("https://") || lower.hasPrefix("http://") {
            return String(value.prefix(4000))
        }
        return ""
    }

    private static func extractYear(from raw: String, fallbackTitle: String) -> String {
        let prefix = String(raw.prefix(4))
        if prefix.count == 4, prefix.allSatisfy(\.isNumber) {
            return prefix
        }
        if let range = fallbackTitle.range(of: #"\b(19|20)\d{2}\b"#, options: .regularExpression) {
            return String(fallbackTitle[range])
        }
        return ""
    }
}
