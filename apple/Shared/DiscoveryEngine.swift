import Foundation

public struct DiscoveryShelf: Identifiable, Hashable, Sendable {
    public var id: String
    public var title: String
    public var subtitle: String
    public var items: [MediaItem]

    public init(id: String, title: String, subtitle: String = "", items: [MediaItem]) {
        self.id = id
        self.title = title
        self.subtitle = subtitle
        self.items = items
    }
}

public struct DiscoveryFeedEntry: Codable, Hashable, Sendable {
    public var id: String
    public var kind: String
    public var name: String
    public var aliases: [String]
    public var genres: [String]
    public var year: String
    public var released: String
    public var globalRank: Int
    public var rank: Int
    public var week: String
    public var poster: String
    public var background: String
    public var netflixId: Int64
    public var source: String

    public init(
        id: String = "",
        kind: String = "vod",
        name: String = "",
        aliases: [String] = [],
        genres: [String] = [],
        year: String = "",
        released: String = "",
        globalRank: Int = 999,
        rank: Int = 99,
        week: String = "",
        poster: String = "",
        background: String = "",
        netflixId: Int64 = 0,
        source: String = "cinemeta"
    ) {
        self.id = id
        self.kind = kind
        self.name = name
        self.aliases = aliases
        self.genres = genres
        self.year = year
        self.released = released
        self.globalRank = globalRank
        self.rank = rank
        self.week = week
        self.poster = poster
        self.background = background
        self.netflixId = netflixId
        self.source = source
    }
}

public struct DiscoveryFeedPayload: Codable, Hashable, Sendable {
    public var version: Int
    public var updatedAt: TimeInterval
    public var metas: [DiscoveryFeedEntry]
    public var charts: [DiscoveryFeedEntry]
    public var chartSource: String

    public init(
        version: Int = 3,
        updatedAt: TimeInterval = 0,
        metas: [DiscoveryFeedEntry] = [],
        charts: [DiscoveryFeedEntry] = [],
        chartSource: String = "netflix"
    ) {
        self.version = version
        self.updatedAt = updatedAt
        self.metas = metas
        self.charts = charts
        self.chartSource = chartSource
    }
}

public struct DiscoveryResult: Hashable, Sendable {
    public var shelves: [DiscoveryShelf]
    public var showcase: [MediaItem]
    public var updatedAt: TimeInterval
    public var personalized: Bool
    public var topGenres: [String]

    public init(
        shelves: [DiscoveryShelf] = [],
        showcase: [MediaItem] = [],
        updatedAt: TimeInterval = 0,
        personalized: Bool = false,
        topGenres: [String] = []
    ) {
        self.shelves = shelves
        self.showcase = showcase
        self.updatedAt = updatedAt
        self.personalized = personalized
        self.topGenres = topGenres
    }
}

/// Public catalog discovery (Cinemeta + Netflix Türkiye Top 10) with 100% local personalized ranking.
public enum DiscoveryEngine {
    public static let istanbulTimeZone = TimeZone(identifier: "Europe/Istanbul") ?? TimeZone(secondsFromGMT: 10800)!
    public static let cinemetaBase = "https://v3-cinemeta.strem.io"
    public static let netflixTurkeyURL = "https://www.netflix.com/tudum/top10/turkey"

    public static let orderedGenres: [(key: String, label: String)] = [
        ("Action", "Aksiyon"),
        ("Adventure", "Macera"),
        ("Animation", "Animasyon"),
        ("Comedy", "Komedi"),
        ("Crime", "Suç"),
        ("Documentary", "Belgesel"),
        ("Drama", "Dram"),
        ("Family", "Aile"),
        ("Fantasy", "Fantastik"),
        ("Horror", "Korku"),
        ("Mystery", "Gizem"),
        ("Romance", "Romantik"),
        ("Sci-Fi", "Bilim Kurgu"),
        ("Thriller", "Gerilim"),
    ]

    private static let genreLabels: [String: String] = Dictionary(uniqueKeysWithValues: orderedGenres)

    private static let extraAliases: [String: String] = [
        "dramalar": "Drama",
        "drama": "Drama",
        "komediler": "Comedy",
        "gerilimler": "Thriller",
        "korkular": "Horror",
        "korkufilmleri": "Horror",
        "belgeseller": "Documentary",
        "aksiyonvemacera": "Action",
        "bilimkurguvefantastik": "Sci-Fi",
        "bilimkurgu": "Sci-Fi",
        "scifi": "Sci-Fi",
        "sciencefiction": "Sci-Fi",
        "sucdizileri": "Crime",
        "sucfilmleri": "Crime",
        "romantikfilmler": "Romance",
        "romantikdiziler": "Romance",
        "ailevecocuk": "Family",
        "cocukveaile": "Family",
        "animasyonlar": "Animation",
        "anime": "Animation",
        "fantastikfilmler": "Fantasy",
        "gizemli": "Mystery",
    ]

    private static let genreAliases: [String: String] = {
        var map: [String: String] = [:]
        for (en, tr) in orderedGenres {
            map[discoveryKey(en)] = en
            map[discoveryKey(tr)] = en
        }
        for (alias, en) in extraAliases where map[alias] == nil {
            map[alias] = en
        }
        return map
    }()

    private static let prefixRegex = try! NSRegularExpression(pattern: "^\\s*(?:tr|en|us|uk|de|fr|es|vip)\\s*[:|]\\s*")
    private static let techRegex = try! NSRegularExpression(pattern: "\\b(?:19|20)\\d{2}\\b|\\b(?:tr|en|trsub|eng|turkce|altyazili|dublaj|uhd|fhd|hd|4k|1080p|720p)\\b")
    private static let nonAlnumRegex = try! NSRegularExpression(pattern: "[^a-z0-9]")
    private static let splitTitleRegex = try! NSRegularExpression(pattern: "\\s+[|/]\\s+|\\s+\\([^)]*\\)\\s*")
    private static let splitGenreRegex = try! NSRegularExpression(pattern: "[,/|&]")
    private static let netflixGraphqlRegex = try! NSRegularExpression(
        pattern: "netflix\\.reactContext\\.models\\.graphql\\s*=\\s*JSON\\.parse\\('(.*?)'\\);",
        options: [.dotMatchesLineSeparators]
    )
    private static let ldJsonRegex = try! NSRegularExpression(
        pattern: "<script[^>]*type=\"application/ld\\+json\"[^>]*>(.*?)</script>",
        options: [.dotMatchesLineSeparators]
    )

    public static func discoveryKey(_ value: String) -> String {
        var text = value
            .replacingOccurrences(of: "ı", with: "i")
            .replacingOccurrences(of: "İ", with: "i")
            .folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .lowercased()
        text = prefixRegex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: "")
        text = techRegex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: " ")
        text = nonAlnumRegex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: "")
        return text
    }

    public static func discoveryTitles(_ name: String) -> Set<String> {
        let range = NSRange(name.startIndex..., in: name)
        var parts = [name]
        let matches = splitTitleRegex.matches(in: name, range: range)
        if !matches.isEmpty {
            var last = name.startIndex
            for m in matches {
                if let r = Range(m.range, in: name) {
                    parts.append(String(name[last..<r.lowerBound]))
                    last = r.upperBound
                }
            }
            parts.append(String(name[last...]))
        }
        return Set(parts.map(discoveryKey).filter { $0.count >= 2 })
    }

    public static func genreSet(_ raw: String) -> [String] {
        guard !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return [] }
        let range = NSRange(raw.startIndex..., in: raw)
        let matches = splitGenreRegex.matches(in: raw, range: range)
        var parts: [String] = []
        var last = raw.startIndex
        for m in matches {
            if let r = Range(m.range, in: raw) {
                parts.append(String(raw[last..<r.lowerBound]))
                last = r.upperBound
            }
        }
        parts.append(String(raw[last...]))
        var seen = Set<String>()
        var result: [String] = []
        for p in parts {
            let trimmed = p.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty, let canonical = genreAliases[discoveryKey(trimmed)] else { continue }
            if seen.insert(canonical).inserted {
                result.append(canonical)
            }
        }
        return result
    }

    public static func parseNetflix(html: String) -> [DiscoveryFeedEntry] {
        let fullRange = NSRange(html.startIndex..., in: html)
        guard let match = netflixGraphqlRegex.firstMatch(in: html, range: fullRange),
              let captureRange = Range(match.range(at: 1), in: html) else {
            return []
        }
        let escaped = String(html[captureRange])
        var unescaped = ""
        unescaped.reserveCapacity(escaped.count)
        var i = escaped.startIndex
        while i < escaped.endIndex {
            let ch = escaped[i]
            let next = escaped.index(after: i)
            if ch == "\\" && next < escaped.endIndex && (escaped[next] == "\\" || escaped[next] == "'") {
                unescaped.append(escaped[next])
                i = escaped.index(after: next)
            } else {
                unescaped.append(ch)
                i = next
            }
        }
        guard let jsonData = unescaped.data(using: .utf8),
              let root = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any],
              let data = root["data"] as? [String: Any] else {
            return []
        }
        var seen = Set<String>()
        var entries: [DiscoveryFeedEntry] = []
        for value in data.values {
            guard let dict = value as? [String: Any],
                  let info = dict["top10Video"] as? [String: Any],
                  let chart = dict["top10"] as? [String: Any] else { continue }
            let parent = info["parentShow"] as? [String: Any]
            let title = (parent?["title"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? (info["title"] as? String ?? "")
            guard !title.isEmpty else { continue }
            let category = chart["category"] as? String ?? ""
            let kind = category == "MOVIES" ? "vod" : "series"
            let week = chart["weekEndDate"] as? String ?? ""
            let dedupKey = "\(kind)|\(title)|\(week)"
            guard seen.insert(dedupKey).inserted else { continue }
            let yearInt = info["releaseYear"] as? Int ?? 0
            let rank = chart["weeklyRank"] as? Int ?? 99
            let netflixId = (parent?["videoId"] as? NSNumber)?.int64Value ?? (info["videoId"] as? NSNumber)?.int64Value ?? 0
            entries.append(
                DiscoveryFeedEntry(
                    id: "netflix:\(kind):\(netflixId)",
                    kind: kind,
                    name: title,
                    year: yearInt > 0 ? String(yearInt) : "",
                    rank: rank,
                    week: week,
                    netflixId: netflixId,
                    source: "netflix"
                )
            )
        }
        return entries.sorted { $0.rank < $1.rank }
    }

    public static func refreshPublicFeed(session: URLSession = MavieHTTPClient.sharedSession) async -> DiscoveryFeedPayload? {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = istanbulTimeZone
        let currentYear = cal.component(.year, from: Date())

        var specs: [(kind: String, catalog: String, extra: String)] = []
        for kind in ["movie", "series"] {
            specs.append((kind, "top", ""))
            specs.append((kind, "year", "/genre=\(currentYear)"))
            specs.append((kind, "year", "/genre=\(currentYear - 1)"))
            for g in ["Comedy", "Drama", "Action", "Crime", "Sci-Fi", "Horror", "Romance", "Animation"] {
                specs.append((kind, "top", "/genre=\(g)"))
            }
        }

        var metasById: [String: DiscoveryFeedEntry] = [:]
        var successCount = 0
        let maxConcurrent = 4

        await withTaskGroup(of: [(String, DiscoveryFeedEntry)].self) { group in
            func enqueue(_ spec: (kind: String, catalog: String, extra: String)) {
                group.addTask {
                    guard let url = URL(string: "\(cinemetaBase)/catalog/\(spec.kind)/\(spec.catalog)\(spec.extra).json") else { return [] }
                    var req = URLRequest(url: url)
                    req.timeoutInterval = 15
                    req.setValue("Mozilla/5.0 Mavie/2.2", forHTTPHeaderField: "User-Agent")
                    guard let (data, _) = try? await MavieHTTPClient.fetchData(
                        for: req,
                        session: session,
                        context: "Keşif servisi",
                        retryDelays: [0.3, 0.9]
                    ),
                          let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                          let rows = obj["metas"] as? [[String: Any]] else { return [] }
                    let isTop = spec.catalog == "top" && spec.extra.isEmpty
                    var out: [(String, DiscoveryFeedEntry)] = []
                    for (idx, row) in rows.enumerated() {
                        guard let id = row["id"] as? String, !id.isEmpty,
                              let name = row["name"] as? String, !name.isEmpty else { continue }
                        let genresArr = (row["genres"] as? [String]) ?? (row["genre"] as? [String]) ?? []
                        let rawYear = (row["year"] as? String) ?? (row["releaseInfo"] as? String) ?? ""
                        let released = (row["released"] as? String) ?? ""
                        let entry = DiscoveryFeedEntry(
                            id: id,
                            kind: spec.kind == "movie" ? "vod" : "series",
                            name: name,
                            genres: genresArr,
                            year: String(rawYear.prefix(4)),
                            released: String(released.prefix(10)),
                            globalRank: isTop ? (idx + 1) : 999,
                            poster: (row["poster"] as? String) ?? "",
                            background: (row["background"] as? String) ?? "",
                            source: "cinemeta"
                        )
                        out.append((id, entry))
                    }
                    return out
                }
            }

            var nextIdx = 0
            while nextIdx < min(maxConcurrent, specs.count) {
                enqueue(specs[nextIdx])
                nextIdx += 1
            }

            for await batch in group {
                if nextIdx < specs.count {
                    enqueue(specs[nextIdx])
                    nextIdx += 1
                }
                if !batch.isEmpty { successCount += 1 }
                for (id, entry) in batch {
                    if let existing = metasById[id], entry.globalRank >= existing.globalRank {
                        var merged = entry
                        merged.globalRank = existing.globalRank
                        metasById[id] = merged
                    } else {
                        metasById[id] = entry
                    }
                }
            }
        }

        var charts: [DiscoveryFeedEntry] = []
        for urlString in [netflixTurkeyURL, netflixTurkeyURL + "/tv"] {
            if let url = URL(string: urlString) {
                var req = URLRequest(url: url)
                req.timeoutInterval = 15
                req.setValue("curl/8.7.1", forHTTPHeaderField: "User-Agent")
                if let (data, resp) = try? await MavieHTTPClient.fetchData(
                    for: req,
                    session: session,
                    context: "Netflix Türkiye",
                    fallbackUserAgent: MavieHTTPClient.browserUserAgent,
                    retryDelays: [0.3, 0.9]
                ) {
                    let html = MavieHTTPClient.decodeText(data, response: resp)
                    charts.append(contentsOf: parseNetflix(html: html))
                }
            }
        }

        if !charts.isEmpty {
            let localized: [DiscoveryFeedEntry] = await withTaskGroup(of: DiscoveryFeedEntry.self) { group in
                func enqueueEntry(_ entry: DiscoveryFeedEntry) {
                    group.addTask {
                        guard entry.netflixId > 0,
                              let url = URL(string: "https://www.netflix.com/tr/title/\(entry.netflixId)") else { return entry }
                        var updated = entry
                        var req = URLRequest(url: url)
                        req.timeoutInterval = 12
                        req.setValue("curl/8.7.1", forHTTPHeaderField: "User-Agent")
                        if let (data, resp) = try? await MavieHTTPClient.fetchData(
                            for: req,
                            session: session,
                            context: "Netflix başlık",
                            fallbackUserAgent: MavieHTTPClient.browserUserAgent,
                            retryDelays: [0.3, 0.9]
                        ) {
                            let html = MavieHTTPClient.decodeText(data, response: resp)
                            let full = NSRange(html.startIndex..., in: html)
                            for m in ldJsonRegex.matches(in: html, range: full) {
                                guard let r = Range(m.range(at: 1), in: html),
                                      let blockData = String(html[r]).data(using: .utf8),
                                      let info = try? JSONSerialization.jsonObject(with: blockData) as? [String: Any] else { continue }
                                if updated.aliases.isEmpty, let trName = info["name"] as? String, !trName.isEmpty {
                                    updated.aliases = [trName]
                                }
                                if updated.genres.isEmpty {
                                    if let trGenre = info["genre"] as? String, !trGenre.isEmpty {
                                        updated.genres = genreSet(trGenre)
                                    } else if let trGenres = info["genre"] as? [String], !trGenres.isEmpty {
                                        updated.genres = genreSet(trGenres.joined(separator: ","))
                                    }
                                }
                            }
                        }
                        return updated
                    }
                }

                var nextIdx = 0
                while nextIdx < min(maxConcurrent, charts.count) {
                    enqueueEntry(charts[nextIdx])
                    nextIdx += 1
                }

                var collected: [DiscoveryFeedEntry] = []
                for await e in group {
                    if nextIdx < charts.count {
                        enqueueEntry(charts[nextIdx])
                        nextIdx += 1
                    }
                    collected.append(e)
                }
                return collected
            }
            charts = localized
        }

        guard successCount > 0 || !charts.isEmpty else { return nil }
        return DiscoveryFeedPayload(
            version: 3,
            updatedAt: Date().timeIntervalSince1970,
            metas: Array(metasById.values),
            charts: charts,
            chartSource: "netflix"
        )
    }

    public static func build(
        catalog: [MediaItem],
        progressByItem: [String: WatchProgress],
        favoriteIds: Set<String>,
        feed: DiscoveryFeedPayload,
        today: Date = Date()
    ) -> DiscoveryResult {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = istanbulTimeZone
        let todayStart = cal.startOfDay(for: today)
        let currentYear = cal.component(.year, from: todayStart)
        let isoFormatter = DateFormatter()
        isoFormatter.calendar = cal
        isoFormatter.timeZone = istanbulTimeZone
        isoFormatter.locale = Locale(identifier: "en_US_POSIX")
        isoFormatter.dateFormat = "yyyy-MM-dd"
        let todayIso = isoFormatter.string(from: todayStart)
        let cutoffDate = cal.date(byAdding: .day, value: -365, to: todayStart) ?? todayStart
        let cutoffIso = isoFormatter.string(from: cutoffDate)

        var candidates = catalog.filter { $0.kind == .vod || $0.kind == .series }
        var index: [String: [Int]] = [:]
        for (i, item) in candidates.enumerated() {
            for title in discoveryTitles(item.name) {
                let k = "\(item.kind.rawValue)|\(title)"
                index[k, default: []].append(i)
            }
        }

        func match(_ meta: DiscoveryFeedEntry) -> Int? {
            let kind: MediaKind = meta.kind == "series" ? .series : .vod
            var optionIndices = Set<Int>()
            for name in ([meta.name] + meta.aliases) where !name.isEmpty {
                for title in discoveryTitles(name) {
                    if let hits = index["\(kind.rawValue)|\(title)"] {
                        optionIndices.formUnion(hits)
                    }
                }
            }
            let year = String(meta.year.prefix(4))
            let yearNum = Int(year)
            let valid = optionIndices.filter { idx in
                let item = candidates[idx]
                let itemYear = Int(item.year.prefix(4))
                return kind == .series || yearNum == nil || itemYear == nil || itemYear == yearNum
            }
            return valid.max { a, b in
                let ia = candidates[a]
                let ib = candidates[b]
                let pa = ia.poster.isEmpty ? 0 : 1
                let pb = ib.poster.isEmpty ? 0 : 1
                if pa != pb { return pa < pb }
                return ia.rating < ib.rating
            }
        }

        var releaseDates: [String: String] = [:]
        var globalRanks: [String: Int] = [:]
        for meta in (feed.metas + feed.charts) {
            guard let idx = match(meta) else { continue }
            let metaGenres = genreSet(meta.genres.joined(separator: ","))
            if !metaGenres.isEmpty {
                candidates[idx].genres = metaGenres.joined(separator: ",")
            }
            if meta.released.count >= 10 {
                releaseDates[candidates[idx].id] = String(meta.released.prefix(10))
            }
            if meta.globalRank > 0 && meta.globalRank < 999 {
                globalRanks[candidates[idx].id] = meta.globalRank
            }
            if candidates[idx].backdrop.isEmpty && !meta.background.isEmpty {
                candidates[idx].backdrop = meta.background
            }
            if candidates[idx].poster.isEmpty && !meta.poster.isEmpty {
                candidates[idx].poster = meta.poster
            }
            if candidates[idx].year.isEmpty && !meta.year.isEmpty {
                candidates[idx].year = String(meta.year.prefix(4))
            }
        }

        // Deduplicate provider duplicates without merging remakes
        var uniqueMap: [String: MediaItem] = [:]
        var uniqueOrder: [String] = []
        for item in candidates {
            let token = "\(item.kind.rawValue)|\(discoveryKey(item.name))|\(item.year)"
            if let existing = uniqueMap[token] {
                if genreSet(item.genres).count > genreSet(existing.genres).count {
                    uniqueMap[token] = item
                }
            } else {
                uniqueMap[token] = item
                uniqueOrder.append(token)
            }
        }
        let pool = uniqueOrder.compactMap { uniqueMap[$0] }
        var byId: [String: MediaItem] = Dictionary(uniqueKeysWithValues: catalog.map { ($0.id, $0) })
        for item in pool { byId[item.id] = item }

        // Compute personalized genre affinity from viewing history & favorites
        var watched = Set<String>()
        var weights: [String: Double] = [:]
        var seeds: [MediaItem] = []

        var historyIds = Set(progressByItem.keys)
        historyIds.formUnion(favoriteIds)
        for rawId in historyIds {
            let sourceItem = byId[rawId]
            let targetId = sourceItem?.parentId ?? rawId
            guard let item = byId[targetId] else { continue }
            let p = progressByItem[rawId]
            let isFav = favoriteIds.contains(rawId) || favoriteIds.contains(targetId)
            if (p?.positionSeconds ?? 0) > 0 || p?.completed == true {
                watched.insert(targetId)
            }
            if (p?.positionSeconds ?? 0) < 60 && p?.completed != true && !isFav {
                continue
            }
            let ratio = min(1.0, (p?.positionSeconds ?? 0) / max(1.0, p?.durationSeconds ?? 1.0))
            var affinity = 1.0 + ratio + (isFav ? 2.0 : 0.0)
            let days: Double
            if let updated = p?.updatedAt, updated > 0 {
                let d = cal.startOfDay(for: Date(timeIntervalSince1970: updated))
                days = Double(max(0, cal.dateComponents([.day], from: d, to: todayStart).day ?? 0))
            } else {
                days = 30.0
            }
            affinity *= pow(0.5, days / 90.0)
            let gs = genreSet(item.genres)
            for g in gs {
                weights[g, default: 0] += affinity
            }
            if !gs.isEmpty {
                seeds.append(item)
            }
        }

        let genreCache: [String: [String]] = Dictionary(uniqueKeysWithValues: pool.map { ($0.id, genreSet($0.genres)) })
        func score(_ item: MediaItem) -> Double {
            let gs = genreCache[item.id] ?? []
            let w = gs.reduce(0.0) { $0 + (weights[$1] ?? 0.0) }
            let r = min(10.0, max(0.0, item.rating)) * 0.08
            let g = 1.0 / (1.0 + Double(globalRanks[item.id] ?? 999))
            return w + r + g
        }

        let fresh = pool.filter { item in
            guard let y = Int(item.year.prefix(4)), (currentYear - 1)...currentYear ~= y else { return false }
            if let rel = releaseDates[item.id], rel.count >= 10 {
                return rel >= cutoffIso && rel <= todayIso
            }
            return y == currentYear
        }.sorted { a, b in
            let ra = releaseDates[a.id] ?? a.year
            let rb = releaseDates[b.id] ?? b.year
            if ra != rb { return ra > rb }
            return (globalRanks[a.id] ?? 999) < (globalRanks[b.id] ?? 999)
        }

        let latestWeek = feed.charts.map(\.week).filter { $0.count >= 10 }.max() ?? ""
        let chartFresh: Bool = {
            guard !latestWeek.isEmpty, let weekDate = isoFormatter.date(from: String(latestWeek.prefix(10))) else { return false }
            let delta = cal.dateComponents([.day], from: weekDate, to: todayStart).day ?? 99
            return (0...21).contains(delta)
        }()

        let ranked = pool.sorted { score($0) > score($1) }
        var personalVod: [MediaItem] = []
        var personalSeries: [MediaItem] = []
        var byGenre: [String: [MediaItem]] = [:]

        for item in ranked {
            let gs = genreCache[item.id] ?? []
            guard !gs.isEmpty else { continue }
            if !watched.contains(item.id) {
                if item.kind == .vod && personalVod.count < 20 { personalVod.append(item) }
                if item.kind == .series && personalSeries.count < 20 { personalSeries.append(item) }
            }
            for g in gs {
                let bucketKey = "\(item.kind.rawValue)|\(g)"
                if (byGenre[bucketKey]?.count ?? 0) < 20 {
                    byGenre[bucketKey, default: []].append(item)
                }
            }
        }

        let topGenreKeys = weights.sorted { $0.value > $1.value }.map(\.key)
        let topGenreLabels = topGenreKeys.compactMap { genreLabels[$0] }.prefix(3).map { $0 }

        var shelves: [DiscoveryShelf] = []
        func appendShelf(_ id: String, _ title: String, _ subtitle: String, _ rows: [MediaItem]) {
            guard !rows.isEmpty else { return }
            shelves.append(DiscoveryShelf(id: id, title: title, subtitle: subtitle, items: Array(rows.prefix(20))))
        }

        for (kind, label) in [(MediaKind.vod, "Filmler"), (MediaKind.series, "Diziler")] {
            if chartFresh {
                var used = Set<String>()
                let chartRows: [MediaItem] = feed.charts
                    .filter { $0.week == latestWeek && ($0.kind == "series") == (kind == .series) }
                    .sorted { $0.rank < $1.rank }
                    .compactMap { meta in
                        guard let idx = match(meta) else { return nil }
                        let item = candidates[idx]
                        return used.insert(item.id).inserted ? item : nil
                    }
                appendShelf(
                    "turkey-\(kind.rawValue)",
                    "Türkiye’de Popüler \(label)",
                    "Netflix Türkiye Top 10 · \(latestWeek) haftası",
                    chartRows
                )
            }
            appendShelf(
                "new-\(kind.rawValue)",
                "Yeni Çıkan \(label)",
                "Yayın yılı ve çıkış tarihine göre",
                fresh.filter { $0.kind == kind }
            )
            let personalRows = kind == .vod ? personalVod : personalSeries
            let hint = topGenreLabels.isEmpty ? "" : " · \(topGenreLabels.prefix(2).joined(separator: ", "))"
            let personalSub = seeds.first.map { "\($0.name) ve izleme geçmişine göre\(hint)" } ?? "Türler ve güncel keşif listeleriyle"
            appendShelf(
                "for-you-\(kind.rawValue)",
                weights.isEmpty ? "Keşfet: \(label)" : "Sana Özel \(label)",
                personalSub,
                personalRows
            )
        }

        // Order genre shelves dynamically by watched genre affinity
        let sortedGenres = orderedGenres.enumerated().sorted { lhs, rhs in
            let wl = weights[lhs.element.key] ?? 0
            let wr = weights[rhs.element.key] ?? 0
            if wl != wr { return wl > wr }
            return lhs.offset < rhs.offset
        }.map(\.element)

        for (genreKey, genreLabel) in sortedGenres {
            let sub = (weights[genreKey] ?? 0) > 0 ? "İzleme geçmişine göre öne çıkarıldı" : ""
            for (kind, suffix) in [(MediaKind.vod, "Filmleri"), (MediaKind.series, "Dizileri")] {
                appendShelf("genre-\(kind.rawValue)-\(genreKey)", "\(genreLabel) \(suffix)", sub, byGenre["\(kind.rawValue)|\(genreKey)"] ?? [])
            }
        }

        let films = Array(fresh.filter { $0.kind == .vod && !watched.contains($0.id) && !$0.poster.isEmpty }.prefix(4))
        let shows = Array(fresh.filter { $0.kind == .series && !watched.contains($0.id) && !$0.poster.isEmpty }.prefix(4))
        var showcase: [MediaItem] = []
        for idx in 0..<max(films.count, shows.count) {
            if idx < films.count { showcase.append(films[idx]) }
            if idx < shows.count { showcase.append(shows[idx]) }
        }
        return DiscoveryResult(
            shelves: shelves,
            showcase: showcase,
            updatedAt: feed.updatedAt,
            personalized: !weights.isEmpty,
            topGenres: topGenreLabels
        )
    }
}
