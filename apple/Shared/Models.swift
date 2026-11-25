import Foundation

public enum SourceMode: String, Codable, CaseIterable, Sendable {
    case demo
    case m3u
    case xtream
    case local

    public var displayTitle: String {
        switch self {
        case .demo: return "Açık Sinema (Demo)"
        case .m3u: return "M3U / M3U8"
        case .xtream: return "Xtream Codes"
        case .local: return "Yerel Dosya"
        }
    }
}

public enum MediaKind: String, Codable, CaseIterable, Sendable {
    case live
    case vod
    case series
    case episode

    public var displayTitle: String {
        switch self {
        case .live: return "Canlı Yayın"
        case .vod: return "Film"
        case .series: return "Dizi"
        case .episode: return "Bölüm"
        }
    }
}

public struct WatchProgress: Codable, Hashable, Sendable {
    public var itemId: String
    public var positionSeconds: Double
    public var durationSeconds: Double
    public var completed: Bool
    public var updatedAt: TimeInterval

    private enum CodingKeys: String, CodingKey {
        case itemId = "item_id"
        case position
        case duration
        case completed
        case updatedAt = "updated_at"
    }

    private enum LegacyCodingKeys: String, CodingKey {
        case itemId
        case positionSeconds
        case durationSeconds
        case completed
        case updatedAt
    }

    public init(
        itemId: String,
        positionSeconds: Double,
        durationSeconds: Double,
        completed: Bool,
        updatedAt: TimeInterval = Date().timeIntervalSince1970
    ) {
        self.itemId = itemId
        self.positionSeconds = max(0, positionSeconds)
        self.durationSeconds = max(0, durationSeconds)
        self.completed = completed
        self.updatedAt = updatedAt
    }

    public init(from decoder: Decoder) throws {
        let canonical = try decoder.container(keyedBy: CodingKeys.self)
        let legacy = try decoder.container(keyedBy: LegacyCodingKeys.self)

        if let id = try canonical.decodeIfPresent(String.self, forKey: .itemId) {
            self.itemId = id
        } else {
            self.itemId = try legacy.decode(String.self, forKey: .itemId)
        }

        let rawPos = try canonical.decodeIfPresent(Double.self, forKey: .position)
            ?? legacy.decodeIfPresent(Double.self, forKey: .positionSeconds)
            ?? 0
        self.positionSeconds = max(0, rawPos.isFinite ? rawPos : 0)

        let rawDur = try canonical.decodeIfPresent(Double.self, forKey: .duration)
            ?? legacy.decodeIfPresent(Double.self, forKey: .durationSeconds)
            ?? 0
        self.durationSeconds = max(0, rawDur.isFinite ? rawDur : 0)

        if let b = try? canonical.decodeIfPresent(Bool.self, forKey: .completed) {
            self.completed = b
        } else if let n = try? canonical.decodeIfPresent(Int.self, forKey: .completed) {
            self.completed = (n != 0)
        } else if let b = try? legacy.decodeIfPresent(Bool.self, forKey: .completed) {
            self.completed = b
        } else {
            self.completed = false
        }

        if let iso = try? canonical.decodeIfPresent(String.self, forKey: .updatedAt),
           let parsed = MavieDateParser.parseISO8601(iso) {
            self.updatedAt = parsed.timeIntervalSince1970
        } else if let ts = try? canonical.decodeIfPresent(Double.self, forKey: .updatedAt) {
            self.updatedAt = ts
        } else if let ts = try? legacy.decodeIfPresent(Double.self, forKey: .updatedAt) {
            self.updatedAt = ts
        } else if let iso = try? legacy.decodeIfPresent(String.self, forKey: .updatedAt),
                  let parsed = MavieDateParser.parseISO8601(iso) {
            self.updatedAt = parsed.timeIntervalSince1970
        } else {
            self.updatedAt = Date().timeIntervalSince1970
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(itemId, forKey: .itemId)
        try container.encode(max(0, positionSeconds), forKey: .position)
        try container.encode(max(0, durationSeconds), forKey: .duration)
        try container.encode(completed ? 1 : 0, forKey: .completed)
        try container.encode(MavieDateParser.formatISO8601(Date(timeIntervalSince1970: updatedAt)), forKey: .updatedAt)
    }

    public var progressFraction: Double {
        guard durationSeconds > 0 else { return 0 }
        return min(1.0, max(0.0, positionSeconds / durationSeconds))
    }
}

public struct MediaItem: Identifiable, Codable, Hashable, Sendable {
    public var id: String
    public var providerId: String
    public var name: String
    public var kind: MediaKind
    public var categoryId: String
    public var categoryName: String
    public var poster: String
    public var backdrop: String
    public var year: String
    public var rating: Double
    public var extensionName: String
    public var durationSeconds: Double
    public var plot: String
    public var season: Int
    public var episode: Int
    public var parentId: String?
    public var addedAt: TimeInterval
    public var videoCodec: String
    public var audioCodec: String
    public var genres: String
    public var sourceUrl: String
    public var tvgId: String
    public var cast: String
    public var director: String

    enum CodingKeys: String, CodingKey {
        case id
        case providerId
        case name
        case kind
        case categoryId
        case categoryName
        case poster
        case backdrop
        case year
        case rating
        case extensionName = "extension"
        case durationSeconds
        case plot
        case season
        case episode
        case parentId
        case addedAt
        case videoCodec
        case audioCodec
        case genres
        case sourceUrl
        case tvgId
        case cast
        case director
    }

    private enum LegacyCodingKeys: String, CodingKey {
        case providerId = "provider_id"
        case categoryId = "category_id"
        case categoryName = "category_name"
        case durationSeconds = "duration_seconds"
        case parentId = "parent_id"
        case addedAt = "added_at"
        case videoCodec = "video_codec"
        case audioCodec = "audio_codec"
        case sourceUrl = "source_url"
        case tvgId = "tvg_id"
    }

    public init(
        id: String,
        providerId: String,
        name: String,
        kind: MediaKind,
        categoryId: String = "",
        categoryName: String = "",
        poster: String = "",
        backdrop: String = "",
        year: String = "",
        rating: Double = 0,
        extensionName: String = "mp4",
        durationSeconds: Double = 0,
        plot: String = "",
        season: Int = 0,
        episode: Int = 0,
        parentId: String? = nil,
        addedAt: TimeInterval = 0,
        videoCodec: String = "",
        audioCodec: String = "",
        genres: String = "",
        sourceUrl: String = "",
        tvgId: String = "",
        cast: String = "",
        director: String = ""
    ) {
        self.id = id
        self.providerId = providerId
        self.name = name
        self.kind = kind
        self.categoryId = categoryId
        self.categoryName = categoryName
        self.poster = poster
        self.backdrop = backdrop
        self.year = year
        self.rating = rating
        self.extensionName = extensionName
        self.durationSeconds = durationSeconds
        self.plot = plot
        self.season = season
        self.episode = episode
        self.parentId = parentId
        self.addedAt = addedAt
        self.videoCodec = videoCodec
        self.audioCodec = audioCodec
        self.genres = genres
        self.sourceUrl = sourceUrl
        self.tvgId = tvgId
        self.cast = cast
        self.director = director
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let l = try decoder.container(keyedBy: LegacyCodingKeys.self)

        let decodedId = try c.decode(String.self, forKey: .id)
        self.id = decodedId
        self.kind = try c.decode(MediaKind.self, forKey: .kind)

        let rawProviderId = try c.decodeIfPresent(String.self, forKey: .providerId)
            ?? l.decodeIfPresent(String.self, forKey: .providerId)
        if let rawProviderId, !rawProviderId.isEmpty {
            self.providerId = rawProviderId
        } else if let colonIdx = decodedId.firstIndex(of: ":") {
            self.providerId = String(decodedId[decodedId.index(after: colonIdx)...])
        } else {
            self.providerId = decodedId
        }

        self.name = try c.decode(String.self, forKey: .name)
        self.categoryId = try c.decodeIfPresent(String.self, forKey: .categoryId)
            ?? l.decodeIfPresent(String.self, forKey: .categoryId)
            ?? ""
        self.categoryName = try c.decodeIfPresent(String.self, forKey: .categoryName)
            ?? l.decodeIfPresent(String.self, forKey: .categoryName)
            ?? ""
        self.poster = Self.sanitizedRemoteImageURL((try c.decodeIfPresent(String.self, forKey: .poster)) ?? "")
        self.backdrop = Self.sanitizedRemoteImageURL((try c.decodeIfPresent(String.self, forKey: .backdrop)) ?? "")

        if let y = try? c.decodeIfPresent(String.self, forKey: .year) {
            self.year = y
        } else if let yInt = try? c.decodeIfPresent(Int.self, forKey: .year) {
            self.year = String(yInt)
        } else {
            self.year = ""
        }

        self.rating = Self.decodeFlexibleDouble(c: c, key: .rating) ?? 0
        let rawExt = (try c.decodeIfPresent(String.self, forKey: .extensionName)) ?? "mp4"
        self.extensionName = rawExt.isEmpty ? "mp4" : rawExt
        self.durationSeconds = Self.decodeFlexibleDouble(c: c, key: .durationSeconds)
            ?? Self.decodeFlexibleDouble(c: l, key: .durationSeconds)
            ?? 0
        self.plot = (try c.decodeIfPresent(String.self, forKey: .plot)) ?? ""
        self.season = (try? c.decodeIfPresent(Int.self, forKey: .season)) ?? 0
        self.episode = (try? c.decodeIfPresent(Int.self, forKey: .episode)) ?? 0

        let rawParent = try c.decodeIfPresent(String.self, forKey: .parentId)
            ?? l.decodeIfPresent(String.self, forKey: .parentId)
        self.parentId = (rawParent?.isEmpty == true) ? nil : rawParent

        self.addedAt = Self.decodeFlexibleDouble(c: c, key: .addedAt)
            ?? Self.decodeFlexibleDouble(c: l, key: .addedAt)
            ?? 0
        self.videoCodec = try c.decodeIfPresent(String.self, forKey: .videoCodec)
            ?? l.decodeIfPresent(String.self, forKey: .videoCodec)
            ?? ""
        self.audioCodec = try c.decodeIfPresent(String.self, forKey: .audioCodec)
            ?? l.decodeIfPresent(String.self, forKey: .audioCodec)
            ?? ""
        self.genres = (try c.decodeIfPresent(String.self, forKey: .genres)) ?? ""
        let rawSourceUrl = try c.decodeIfPresent(String.self, forKey: .sourceUrl)
            ?? l.decodeIfPresent(String.self, forKey: .sourceUrl)
            ?? ""
        self.sourceUrl = Self.sanitizedImportedSourceURL(rawSourceUrl)
        self.tvgId = try c.decodeIfPresent(String.self, forKey: .tvgId)
            ?? l.decodeIfPresent(String.self, forKey: .tvgId)
            ?? ""
        self.cast = (try c.decodeIfPresent(String.self, forKey: .cast)) ?? ""
        self.director = (try c.decodeIfPresent(String.self, forKey: .director)) ?? ""
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(providerId, forKey: .providerId)
        try c.encode(name, forKey: .name)
        try c.encode(kind, forKey: .kind)
        try c.encode(categoryId, forKey: .categoryId)
        try c.encode(categoryName, forKey: .categoryName)
        try c.encode(poster, forKey: .poster)
        try c.encode(backdrop, forKey: .backdrop)
        try c.encode(String(year.prefix(4)), forKey: .year)
        try c.encode(rating, forKey: .rating)
        try c.encode(Self.sanitizedExtension(extensionName), forKey: .extensionName)
        try c.encode(max(0, durationSeconds), forKey: .durationSeconds)
        try c.encode(plot, forKey: .plot)
        try c.encode(season, forKey: .season)
        try c.encode(episode, forKey: .episode)
        if let parentId, !parentId.isEmpty {
            try c.encode(parentId, forKey: .parentId)
        } else {
            try c.encodeNil(forKey: .parentId)
        }
        try c.encode(addedAt, forKey: .addedAt)
        try c.encode(videoCodec, forKey: .videoCodec)
        try c.encode(audioCodec, forKey: .audioCodec)
        if !genres.isEmpty { try c.encode(genres, forKey: .genres) }
        if !sourceUrl.isEmpty { try c.encode(sourceUrl, forKey: .sourceUrl) }
        if !tvgId.isEmpty { try c.encode(tvgId, forKey: .tvgId) }
        if !cast.isEmpty { try c.encode(cast, forKey: .cast) }
        if !director.isEmpty { try c.encode(director, forKey: .director) }
    }

    private static func decodeFlexibleDouble<K: CodingKey>(c: KeyedDecodingContainer<K>, key: K) -> Double? {
        if let d = try? c.decodeIfPresent(Double.self, forKey: key) {
            return d.isFinite ? d : 0
        }
        if let s = try? c.decodeIfPresent(String.self, forKey: key), let d = Double(s) {
            return d.isFinite ? d : 0
        }
        return nil
    }

    private static func sanitizedExtension(_ raw: String) -> String {
        let filtered = String(raw.lowercased().filter { $0.isASCII && ($0.isLetter || $0.isNumber) }.prefix(10))
        return filtered.isEmpty ? "mp4" : filtered
    }

    public static func sanitizedRemoteImageURL(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
              let url = URL(string: trimmed),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = url.host,
              !host.isEmpty else {
            return ""
        }
        return String(trimmed.prefix(4000))
    }

    public static func sanitizedImportedSourceURL(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
              let url = URL(string: trimmed),
              let scheme = url.scheme?.lowercased() else {
            return ""
        }
        if scheme == "http" || scheme == "https" {
            guard let host = url.host, !host.isEmpty else { return "" }
            return trimmed
        }
        if scheme == "file" {
            return trimmed
        }
        return ""
    }
}

public struct MediaCategory: Identifiable, Codable, Hashable, Sendable {
    public var id: String
    public var name: String
    public var kind: MediaKind

    public init(id: String, name: String, kind: MediaKind) {
        self.id = id
        self.name = name
        self.kind = kind
    }
}

public struct Season: Identifiable, Codable, Hashable, Sendable {
    public var id: Int { number }
    public var number: Int
    public var name: String
    public var episodes: [MediaItem]

    public init(number: Int, name: String, episodes: [MediaItem]) {
        self.number = number
        self.name = name
        self.episodes = episodes
    }
}

public struct MediaDetail: Codable, Hashable, Sendable {
    public var item: MediaItem
    public var seasons: [Season]
    public var genres: String
    public var cast: String
    public var director: String

    public init(
        item: MediaItem,
        seasons: [Season] = [],
        genres: String = "",
        cast: String = "",
        director: String = ""
    ) {
        self.item = item
        self.seasons = seasons
        self.genres = genres.isEmpty ? item.genres : genres
        self.cast = cast.isEmpty ? item.cast : cast
        self.director = director.isEmpty ? item.director : director
    }

    public func followingEpisode(after current: MediaItem) -> MediaItem? {
        guard current.kind == .episode, current.parentId == item.id else { return nil }
        let ordered = seasons
            .sorted { $0.number < $1.number }
            .flatMap { season in
                season.episodes.sorted { lhs, rhs in
                    if lhs.episode != rhs.episode { return lhs.episode < rhs.episode }
                    if lhs.name != rhs.name { return lhs.name < rhs.name }
                    return lhs.id < rhs.id
                }
            }
        guard let idx = ordered.firstIndex(where: { $0.id == current.id }) else { return nil }
        let playing = ordered[idx]
        return ordered.dropFirst(idx + 1).first { next in
            next.season != playing.season || playing.episode <= 0 || next.episode > playing.episode
        }
    }
}

public struct Playlist: Identifiable, Codable, Hashable, Sendable {
    public var id: String
    public var name: String
    public var createdAt: String
    public var itemIds: [String]

    private enum CodingKeys: String, CodingKey {
        case id
        case name
        case createdAt = "created_at"
        case itemIds
    }

    private enum LegacyCodingKeys: String, CodingKey {
        case createdAt
    }

    public init(id: String, name: String, createdAt: String = MavieDateParser.formatISO8601(), itemIds: [String] = []) {
        self.id = id
        self.name = name
        self.createdAt = createdAt
        self.itemIds = itemIds
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let l = try decoder.container(keyedBy: LegacyCodingKeys.self)
        self.id = try c.decode(String.self, forKey: .id)
        self.name = try c.decode(String.self, forKey: .name)
        self.createdAt = try c.decodeIfPresent(String.self, forKey: .createdAt)
            ?? l.decodeIfPresent(String.self, forKey: .createdAt)
            ?? MavieDateParser.formatISO8601()
        self.itemIds = (try c.decodeIfPresent([String].self, forKey: .itemIds)) ?? []
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(name, forKey: .name)
        try c.encode(createdAt, forKey: .createdAt)
        try c.encode(itemIds, forKey: .itemIds)
    }
}

public struct UserProfile: Identifiable, Codable, Hashable, Sendable {
    public var id: String
    public var name: String
    public var avatarColor: String
    public var isKids: Bool
    public var hasPin: Bool
    public var pinHash: String
    public var active: Bool

    public init(
        id: String,
        name: String,
        avatarColor: String = "#7C3AED",
        isKids: Bool = false,
        hasPin: Bool = false,
        pinHash: String = "",
        active: Bool = false
    ) {
        self.id = id
        self.name = name
        self.avatarColor = avatarColor
        self.isKids = isKids
        self.hasPin = hasPin
        self.pinHash = pinHash
        self.active = active
    }
}

public struct ConnectionSettings: Codable, Hashable, Sendable, CustomStringConvertible {
    public var sourceType: SourceMode
    public var host: String
    public var username: String
    public var password: String
    public var m3uUrl: String
    public var epgUrl: String
    public var lanAddress: String

    public init(
        sourceType: SourceMode = .demo,
        host: String = "",
        username: String = "",
        password: String = "",
        m3uUrl: String = "",
        epgUrl: String = "",
        lanAddress: String = ""
    ) {
        self.sourceType = sourceType
        self.host = host
        self.username = username
        self.password = password
        self.m3uUrl = m3uUrl
        self.epgUrl = epgUrl
        self.lanAddress = lanAddress
    }

    public var description: String {
        "ConnectionSettings(sourceType: \(sourceType.rawValue), host: \(host))"
    }
}

public struct AccountInfo: Codable, Hashable, Sendable {
    public var id: String
    public var username: String
    public var host: String
    public var name: String
    public var status: String
    public var expiresAt: String
    public var maxConnections: Int
    public var sourceType: SourceMode
    public var epgUrl: String

    public init(
        id: String = "default",
        username: String = "",
        host: String = "",
        name: String = "Mavie Kütüphanesi",
        status: String = "Active",
        expiresAt: String = "",
        maxConnections: Int = 1,
        sourceType: SourceMode = .demo,
        epgUrl: String = ""
    ) {
        self.id = id
        self.username = username
        self.host = host
        self.name = name
        self.status = status
        self.expiresAt = expiresAt
        self.maxConnections = maxConnections
        self.sourceType = sourceType
        self.epgUrl = epgUrl
    }
}

public enum MavieError: LocalizedError, Equatable, Sendable {
    case invalidURL(String)
    case insecureTransport(String)
    case network(String)
    case parsing(String)
    case validation(String)

    public var errorDescription: String? {
        switch self {
        case .invalidURL(let msg),
             .insecureTransport(let msg),
             .network(let msg),
             .parsing(let msg),
             .validation(let msg):
            return msg
        }
    }
}

public struct SyncFavoriteRecord: Codable, Hashable, Sendable {
    public var itemId: String
    public var createdAt: String

    private enum CodingKeys: String, CodingKey {
        case itemId = "item_id"
        case createdAt = "created_at"
    }

    public init(itemId: String, createdAt: String = MavieDateParser.formatISO8601()) {
        self.itemId = itemId
        self.createdAt = createdAt
    }

    public init(from decoder: Decoder) throws {
        if let single = try? decoder.singleValueContainer(),
           let legacyId = try? single.decode(String.self) {
            self.itemId = legacyId
            self.createdAt = MavieDateParser.formatISO8601()
            return
        }
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.itemId = try c.decode(String.self, forKey: .itemId)
        self.createdAt = (try c.decodeIfPresent(String.self, forKey: .createdAt))
            ?? MavieDateParser.formatISO8601()
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(itemId, forKey: .itemId)
        try c.encode(createdAt, forKey: .createdAt)
    }
}

public struct SyncPlaylistRecord: Codable, Hashable, Sendable {
    public var id: String
    public var name: String
    public var createdAt: String

    private enum CodingKeys: String, CodingKey {
        case id
        case name
        case createdAt = "created_at"
    }

    public init(id: String, name: String, createdAt: String) {
        self.id = id
        self.name = name
        self.createdAt = createdAt
    }
}

public struct SyncPlaylistItemRecord: Codable, Hashable, Sendable {
    public var playlistId: String
    public var itemId: String
    public var position: Int

    private enum CodingKeys: String, CodingKey {
        case playlistId = "playlist_id"
        case itemId = "item_id"
        case position
    }

    public init(playlistId: String, itemId: String, position: Int) {
        self.playlistId = playlistId
        self.itemId = itemId
        self.position = max(0, position)
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.playlistId = try c.decode(String.self, forKey: .playlistId)
        self.itemId = try c.decode(String.self, forKey: .itemId)
        self.position = max(0, (try c.decodeIfPresent(Int.self, forKey: .position)) ?? 0)
    }
}

public struct SyncTrackPreferenceData: Codable, Hashable, Sendable {
    public var audio: String?
    public var subtitle: String?
    public var clientAudio: String?
    public var clientSubtitle: String?

    public init(
        audio: String? = "auto",
        subtitle: String? = "off",
        clientAudio: String? = nil,
        clientSubtitle: String? = nil
    ) {
        self.audio = audio
        self.subtitle = subtitle
        self.clientAudio = clientAudio
        self.clientSubtitle = clientSubtitle
    }
}

public typealias SyncTrackPreference = SyncTrackPreferenceRecord

public struct SyncTrackPreferenceRecord: Codable, Hashable, Sendable {
    public var itemId: String
    public var data: SyncTrackPreferenceData
    public var updatedAt: String

    private enum CodingKeys: String, CodingKey {
        case itemId = "item_id"
        case data
        case updatedAt = "updated_at"
    }

    public init(
        itemId: String,
        data: SyncTrackPreferenceData,
        updatedAt: String = MavieDateParser.formatISO8601()
    ) {
        self.itemId = itemId
        self.data = data
        self.updatedAt = updatedAt
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.itemId = try c.decode(String.self, forKey: .itemId)
        self.updatedAt = (try c.decodeIfPresent(String.self, forKey: .updatedAt))
            ?? MavieDateParser.formatISO8601()

        if let obj = try? c.decode(SyncTrackPreferenceData.self, forKey: .data) {
            self.data = obj
        } else if let jsonString = try? c.decode(String.self, forKey: .data),
                  let rawData = jsonString.data(using: .utf8),
                  let parsed = try? JSONDecoder().decode(SyncTrackPreferenceData.self, from: rawData) {
            self.data = parsed
        } else {
            self.data = SyncTrackPreferenceData()
        }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(itemId, forKey: .itemId)
        try c.encode(data, forKey: .data)
        try c.encode(updatedAt, forKey: .updatedAt)
    }
}

public struct LibrarySyncPayload: Codable, Hashable, Sendable {
    public var version: Int
    public var exportedAt: String
    public var items: [MediaItem]
    public var favorites: [SyncFavoriteRecord]
    public var progress: [WatchProgress]
    public var playlists: [Playlist]
    public var playlistItems: [SyncPlaylistItemRecord]
    public var trackPreferences: [SyncTrackPreferenceRecord]
    public var appleTrackPreferences: [SyncTrackPreferenceRecord]?

    private enum CodingKeys: String, CodingKey {
        case version
        case exportedAt
        case items
        case favorites
        case progress
        case playlists
        case playlistItems
        case trackPreferences
        case appleTrackPreferences
    }

    public init(
        version: Int = 1,
        exportedAt: String = MavieDateParser.formatISO8601(),
        items: [MediaItem] = [],
        favorites: [SyncFavoriteRecord] = [],
        progress: [WatchProgress] = [],
        playlists: [Playlist] = [],
        playlistItems: [SyncPlaylistItemRecord]? = nil,
        trackPreferences: [SyncTrackPreferenceRecord] = [],
        appleTrackPreferences: [SyncTrackPreferenceRecord]? = nil
    ) {
        self.version = version
        self.exportedAt = exportedAt
        self.items = items
        self.favorites = favorites
        self.progress = progress
        self.playlists = playlists
        if let playlistItems {
            self.playlistItems = playlistItems
        } else {
            self.playlistItems = Self.buildPlaylistItems(from: playlists)
        }
        self.trackPreferences = trackPreferences
        self.appleTrackPreferences = appleTrackPreferences
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.version = (try c.decodeIfPresent(Int.self, forKey: .version)) ?? 1
        self.exportedAt = (try c.decodeIfPresent(String.self, forKey: .exportedAt))
            ?? MavieDateParser.formatISO8601()
        self.items = (try c.decodeIfPresent([MediaItem].self, forKey: .items)) ?? []
        self.favorites = (try c.decodeIfPresent([SyncFavoriteRecord].self, forKey: .favorites)) ?? []
        self.progress = (try c.decodeIfPresent([WatchProgress].self, forKey: .progress)) ?? []
        let decodedPlaylistItems = (try c.decodeIfPresent([SyncPlaylistItemRecord].self, forKey: .playlistItems)) ?? []
        var decodedPlaylists = (try c.decodeIfPresent([Playlist].self, forKey: .playlists)) ?? []

        if !decodedPlaylistItems.isEmpty {
            let grouped = Dictionary(grouping: decodedPlaylistItems, by: \.playlistId)
            for idx in decodedPlaylists.indices {
                let plId = decodedPlaylists[idx].id
                if let entries = grouped[plId] {
                    let sortedIds = entries
                        .sorted { $0.position < $1.position }
                        .map(\.itemId)
                    for itemId in sortedIds where !decodedPlaylists[idx].itemIds.contains(itemId) {
                        decodedPlaylists[idx].itemIds.append(itemId)
                    }
                }
            }
        }

        self.playlists = decodedPlaylists
        self.playlistItems = decodedPlaylistItems.isEmpty
            ? Self.buildPlaylistItems(from: decodedPlaylists)
            : decodedPlaylistItems
        self.trackPreferences = (try c.decodeIfPresent([SyncTrackPreferenceRecord].self, forKey: .trackPreferences)) ?? []
        self.appleTrackPreferences = try c.decodeIfPresent([SyncTrackPreferenceRecord].self, forKey: .appleTrackPreferences)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(version, forKey: .version)
        try c.encode(exportedAt, forKey: .exportedAt)
        try c.encode(favorites, forKey: .favorites)
        try c.encode(progress, forKey: .progress)
        let plRecords = playlists.map { SyncPlaylistRecord(id: $0.id, name: $0.name, createdAt: $0.createdAt) }
        try c.encode(plRecords, forKey: .playlists)
        let derivedItems = Self.buildPlaylistItems(from: playlists, extra: playlistItems)
        try c.encode(derivedItems, forKey: .playlistItems)
        try c.encode(trackPreferences, forKey: .trackPreferences)
        if let appleTrackPreferences, !appleTrackPreferences.isEmpty {
            try c.encode(appleTrackPreferences, forKey: .appleTrackPreferences)
        }
        try c.encode(items, forKey: .items)
    }

    private static func buildPlaylistItems(
        from playlists: [Playlist],
        extra: [SyncPlaylistItemRecord] = []
    ) -> [SyncPlaylistItemRecord] {
        var result: [SyncPlaylistItemRecord] = []
        var seen = Set<String>()
        for pl in playlists {
            for (index, itemId) in pl.itemIds.enumerated() {
                let key = "\(pl.id)|\(itemId)"
                if seen.insert(key).inserted {
                    result.append(SyncPlaylistItemRecord(playlistId: pl.id, itemId: itemId, position: index))
                }
            }
        }
        for rec in extra {
            let key = "\(rec.playlistId)|\(rec.itemId)"
            if seen.insert(key).inserted {
                result.append(rec)
            }
        }
        return result
    }
}

public enum MavieDateParser {
    public static func formatISO8601(_ date: Date = Date()) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: date)
    }

    public static func parseISO8601(_ raw: String) -> Date? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = fractional.date(from: trimmed) { return d }
        let standard = ISO8601DateFormatter()
        standard.formatOptions = [.withInternetDateTime]
        if let d = standard.date(from: trimmed) { return d }
        let formats = [
            "yyyy-MM-dd'T'HH:mm:ss.SSSSSSXXXXX",
            "yyyy-MM-dd'T'HH:mm:ss.SSSXXXXX",
            "yyyy-MM-dd'T'HH:mm:ssXXXXX",
            "yyyy-MM-dd'T'HH:mm:ss",
        ]
        for fmt in formats {
            let fallback = DateFormatter()
            fallback.locale = Locale(identifier: "en_US_POSIX")
            fallback.timeZone = TimeZone(secondsFromGMT: 0)
            fallback.dateFormat = fmt
            if let d = fallback.date(from: trimmed) { return d }
        }
        return nil
    }
}
