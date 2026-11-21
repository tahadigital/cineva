import Foundation

public struct SportBroadcastEvent: Identifiable, Hashable, Sendable {
    public var id: String
    public var title: String
    public var sport: String
    public var league: String
    public var time: String
    public var featured: Bool
    public var channels: [String]

    public init(
        id: String,
        title: String,
        sport: String,
        league: String,
        time: String,
        featured: Bool,
        channels: [String]
    ) {
        self.id = id
        self.title = title
        self.sport = sport
        self.league = league
        self.time = time
        self.featured = featured
        self.channels = channels
    }
}

public struct SportsGuideResponse: Hashable, Sendable {
    public var date: String
    public var events: [SportBroadcastEvent]
    public var stale: Bool
    public var sourceType: String

    public init(date: String, events: [SportBroadcastEvent], stale: Bool = false, sourceType: String = "sporekrani") {
        self.date = date
        self.events = events
        self.stale = stale
        self.sourceType = sourceType
    }
}

public enum SportsChannels {
    private static let regionRegex = try! NSRegularExpression(pattern: "^\\s*(?:(?:vip\\s+)?(?:tr|en|us|uk|de|fr|es)|turkey|intl)\\s*[:|➤\\-]\\s*")
    private static let qualityRegex = try! NSRegularExpression(pattern: "(?:[\\s|\\[\\]()\\-]+(?:fhd|hd|uhd|sd|raw|hevc|h265|4k|1080p|720p)\\b[\\s|\\[\\]()\\-]*)+$")
    private static let punctuationRegex = try! NSRegularExpression(pattern: "[^a-z0-9+]")
    private static let aliases: [String: String] = [
        "ssport1": "ssport",
        "smartsporhd": "sporsmart",
        "smartspor": "sporsmart",
        "smartspor2": "sporsmart2",
        "trtsporstar": "trtsporyildiz",
    ]

    public static func fold(_ text: String) -> String {
        text
            .replacingOccurrences(of: "ı", with: "i")
            .replacingOccurrences(of: "İ", with: "i")
            .folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .lowercased()
    }

    public static func key(_ name: String) -> String {
        var text = fold(name)
        text = regionRegex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: "")
        text = qualityRegex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: "")
        text = punctuationRegex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: "")
        return aliases[text] ?? text
    }

    public static func matchChannels(events: [SportBroadcastEvent], liveItems: [MediaItem]) -> [String: MediaItem] {
        let wanted = Set(events.flatMap { $0.channels }.map { key($0) })
        let fhdRegex = try! NSRegularExpression(pattern: "\\bfhd\\b")
        let hdRegex = try! NSRegularExpression(pattern: "\\bhd\\b")
        var bestByKey: [String: (score: Int, item: MediaItem)] = [:]

        for item in liveItems where item.kind == .live {
            let k = key(item.name)
            guard !k.isEmpty, wanted.contains(k) else { continue }
            let folded = fold(item.name)
            let range = NSRange(folded.startIndex..., in: folded)
            let quality = fhdRegex.firstMatch(in: folded, range: range) != nil ? 3
                : (hdRegex.firstMatch(in: folded, range: range) != nil ? 2 : 1)
            let isTr = folded.hasPrefix("tr:") || folded.hasPrefix("en:") ? 1 : 0
            let score = quality * 10 + isTr
            if let existing = bestByKey[k] {
                if score > existing.score {
                    bestByKey[k] = (score, item)
                }
            } else {
                bestByKey[k] = (score, item)
            }
        }

        var result: [String: MediaItem] = [:]
        for event in events {
            for label in event.channels {
                if let matched = bestByKey[key(label)]?.item {
                    result[label] = matched
                }
            }
        }
        return result
    }
}

public actor SportsGuideService {
    public static let shared = SportsGuideService()
    public static let sourceBase = "https://www.sporekrani.com/home/day/"
    private static let marker = "window.__INITIAL_STATE__="
    private static let commentaryNoise = try! NSRegularExpression(pattern: "basin toplantisi|spor bulteni|mac (?:onu|sonu|ozel)|tekrar")
    private static let startTimeRegex = try! NSRegularExpression(pattern: "^(?:[01]\\d|2[0-3]):[0-5]\\d:[0-5]\\d$")

    private struct CacheEntry {
        var fetchedAt: TimeInterval
        var events: [SportBroadcastEvent]
    }
    private var cache: [String: CacheEntry] = [:]

    public init() {}

    public static func parseSporekrani(page: String, dayIso: String) throws -> [SportBroadcastEvent] {
        guard let markerRange = page.range(of: marker) else {
            throw NSError(domain: "MavieSports", code: 1, userInfo: [NSLocalizedDescriptionKey: "Spor yayın rehberi şu anda okunamadı."])
        }
        let tail = page[markerRange.upperBound...]
        let rawJson = tail.components(separatedBy: "</script>").first?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: ";")) ?? ""
        guard let data = rawJson.data(using: .utf8),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let common = root["common"] as? [String: Any] else {
            throw NSError(domain: "MavieSports", code: 2, userInfo: [NSLocalizedDescriptionKey: "Spor yayın rehberi şu anda okunamadı."])
        }

        let rows: [[String: Any]]
        let channelMap: [String: [String: Any]]
        if let eventRows = common["eventRows"] as? [[String: Any]] {
            rows = eventRows
            channelMap = (common["eventChannels"] as? [String: [String: Any]]) ?? [:]
        } else if let legacyEvents = common["events"] as? [[String: Any]] {
            rows = legacyEvents
            channelMap = [:]
        } else {
            throw NSError(domain: "MavieSports", code: 3, userInfo: [NSLocalizedDescriptionKey: "Spor yayın rehberi şu anda okunamadı."])
        }

        func clean(_ value: Any?, maxLen: Int = 180) -> String {
            guard let str = value as? String else { return "" }
            let collapsed = str.split(whereSeparator: \.isWhitespace).joined(separator: " ")
            return String(collapsed.prefix(maxLen))
        }

        let prefix = dayIso + " "
        var dateMatches = rows.isEmpty
        var seen = Set<String>()
        var events: [SportBroadcastEvent] = []

        for row in rows {
            let start = clean(row["date_time"])
            guard start.hasPrefix(prefix) else { continue }
            dateMatches = true
            let timePart = String(start.dropFirst(prefix.count))
            guard startTimeRegex.firstMatch(in: timePart, range: NSRange(timePart.startIndex..., in: timePart)) != nil else { continue }

            guard let idNum = row["id"] as? NSNumber else { continue }
            let id = idNum.stringValue
            let sport = clean(row["sport_name"], maxLen: 50)
            let rawTitle = clean(row["name"])
            let eventType = clean(row["event_type_name"])
            if rawTitle.isEmpty || sport.isEmpty || SportsChannels.fold(sport) == "programlar" { continue }
            let foldedTitle = SportsChannels.fold(rawTitle)
            if eventType != "match" {
                if eventType != "commentary" { continue }
                if commentaryNoise.firstMatch(in: foldedTitle, range: NSRange(foldedTitle.startIndex..., in: foldedTitle)) != nil { continue }
            }

            guard let rawChannels = row["channels"] as? [Any] else { continue }
            var channelNames: [String] = []
            for entry in rawChannels {
                let chObj: [String: Any]?
                if let dict = entry as? [String: Any] {
                    chObj = dict
                } else if let num = entry as? NSNumber {
                    chObj = channelMap[num.stringValue]
                } else if let str = entry as? String {
                    chObj = channelMap[str]
                } else {
                    chObj = nil
                }
                guard let ch = chObj else { continue }
                if let activeNum = ch["active"] as? NSNumber, activeNum.intValue == 0 { continue }
                if let activeStr = ch["active"] as? String, activeStr == "0" { continue }
                let chName = clean(ch["name"], maxLen: 100)
                if chName.isEmpty || SportsChannels.key(chName) == "yayinyok" { continue }
                if !channelNames.contains(chName) { channelNames.append(chName) }
            }
            if channelNames.isEmpty || !seen.insert(id).inserted { continue }

            let qualifier = clean(row["post_fix"], maxLen: 90)
            let displayTitle = (!qualifier.isEmpty && !rawTitle.contains(qualifier)) ? "\(rawTitle) · \(qualifier)" : rawTitle
            let featured = ((row["featured"] as? NSNumber)?.intValue == 1) || ((row["featured"] as? String) == "1")
            let hhmm = String(timePart.prefix(5))
            events.append(
                SportBroadcastEvent(
                    id: id,
                    title: displayTitle,
                    sport: sport,
                    league: clean(row["league_name"]),
                    time: hhmm,
                    featured: featured,
                    channels: channelNames
                )
            )
        }

        if !dateMatches {
            throw NSError(domain: "MavieSports", code: 4, userInfo: [NSLocalizedDescriptionKey: "Yayın akışı seçilen gün için doğrulanamadı."])
        }
        return events.sorted { lhs, rhs in
            if lhs.time != rhs.time { return lhs.time < rhs.time }
            return lhs.id < rhs.id
        }
    }

    public func load(dayIso: String, force: Bool = false, session: URLSession = .shared) async throws -> SportsGuideResponse {
        let now = Date().timeIntervalSince1970
        let cached = cache[dayIso]
        if !force, let cached, now - cached.fetchedAt < 300 {
            return SportsGuideResponse(date: dayIso, events: cached.events, stale: false, sourceType: "sporekrani")
        }
        guard let url = URL(string: Self.sourceBase + dayIso) else {
            throw NSError(domain: "MavieSports", code: 5, userInfo: [NSLocalizedDescriptionKey: "Geçersiz spor rehberi adresi."])
        }
        var req = URLRequest(url: url)
        req.timeoutInterval = 12
        req.setValue("Mavie/2.2 (sports schedule)", forHTTPHeaderField: "User-Agent")
        do {
            let (data, resp) = try await session.data(for: req)
            guard (resp as? HTTPURLResponse)?.statusCode == 200,
                  let html = String(data: data, encoding: .utf8) else {
                throw NSError(domain: "MavieSports", code: 6, userInfo: [NSLocalizedDescriptionKey: "Spor yayın rehberine ulaşılamadı."])
            }
            let events = try Self.parseSporekrani(page: html, dayIso: dayIso)
            cache[dayIso] = CacheEntry(fetchedAt: now, events: events)
            return SportsGuideResponse(date: dayIso, events: events, stale: false, sourceType: "sporekrani")
        } catch {
            if let cached, now - cached.fetchedAt <= 12 * 3600 {
                return SportsGuideResponse(date: dayIso, events: cached.events, stale: true, sourceType: "sporekrani")
            }
            throw NSError(
                domain: "MavieSports",
                code: 7,
                userInfo: [NSLocalizedDescriptionKey: "Spor yayın rehberine ulaşılamadı. Biraz sonra tekrar dene."]
            )
        }
    }
}
