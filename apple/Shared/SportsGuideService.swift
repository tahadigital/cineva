import Foundation
import zlib

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
    public var configured: Bool

    public init(
        date: String,
        events: [SportBroadcastEvent],
        stale: Bool = false,
        sourceType: String = "sporekrani",
        configured: Bool = true
    ) {
        self.date = date
        self.events = events
        self.stale = stale
        self.sourceType = sourceType
        self.configured = configured
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
    private static let xmltvTsRegex = try! NSRegularExpression(pattern: #"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\s*([+-]\d{4}))?"#)
    private static let sportCategoryRegex = try! NSRegularExpression(
        pattern: #"\b(sport|sports|spor|futbol|football|soccer|basketbol|basketball|tennis|tenis|motorsport|formula|racing|boxing|ufc|golf)\b"#,
        options: [.caseInsensitive]
    )
    public static let maxXmltvDecompressedBytes = 16 * 1024 * 1024

    private struct CacheEntry {
        var fetchedAt: TimeInterval
        var events: [SportBroadcastEvent]
    }
    private var cache: [String: CacheEntry] = [:]

    public init() {}

    public static func decompressGzipIfNeeded(_ data: Data, maxBytes: Int = maxXmltvDecompressedBytes) throws -> Data {
        guard data.count >= 2,
              data[data.startIndex] == 0x1F,
              data[data.index(after: data.startIndex)] == 0x8B else {
            return data
        }
        var stream = z_stream()
        let initStatus = inflateInit2_(&stream, 16 + MAX_WBITS, ZLIB_VERSION, Int32(MemoryLayout<z_stream>.size))
        guard initStatus == Z_OK else {
            throw NSError(domain: "MavieSports", code: 10, userInfo: [NSLocalizedDescriptionKey: "XMLTV arşivi açılamadı."])
        }
        defer { inflateEnd(&stream) }

        var output = Data()
        let chunkSize = 65_536
        var chunk = [UInt8](repeating: 0, count: chunkSize)

        let inflateResult: Int32 = data.withUnsafeBytes { rawBuffer in
            guard let basePtr = rawBuffer.bindMemory(to: Bytef.self).baseAddress else {
                return Z_DATA_ERROR
            }
            stream.next_in = UnsafeMutablePointer<Bytef>(mutating: basePtr)
            stream.avail_in = uInt(data.count)

            while true {
                let produced = chunk.withUnsafeMutableBytes { outRaw -> Int32 in
                    guard let outPtr = outRaw.bindMemory(to: Bytef.self).baseAddress else {
                        return Z_DATA_ERROR
                    }
                    stream.next_out = outPtr
                    stream.avail_out = uInt(chunkSize)
                    return inflate(&stream, Z_NO_FLUSH)
                }
                let have = chunkSize - Int(stream.avail_out)
                if have > 0 {
                    if output.count + have > maxBytes {
                        return Z_MEM_ERROR
                    }
                    output.append(contentsOf: chunk[0..<have])
                }
                if produced == Z_STREAM_END {
                    return Z_OK
                }
                if produced != Z_OK {
                    return produced
                }
                if stream.avail_in == 0 && stream.avail_out > 0 {
                    return Z_DATA_ERROR
                }
            }
        }

        if inflateResult == Z_MEM_ERROR {
            throw NSError(domain: "MavieSports", code: 11, userInfo: [NSLocalizedDescriptionKey: "EPG rehberi çok büyük."])
        }
        guard inflateResult == Z_OK else {
            throw NSError(domain: "MavieSports", code: 12, userInfo: [NSLocalizedDescriptionKey: "XMLTV arşiv verisi bozuk."])
        }
        return output
    }

    private static func parseXMLTVTimestamp(_ raw: String, targetTimeZone: TimeZone = DiscoveryEngine.istanbulTimeZone) -> Date? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let nsRange = NSRange(trimmed.startIndex..<trimmed.endIndex, in: trimmed)
        guard let match = xmltvTsRegex.firstMatch(in: trimmed, range: nsRange),
              match.numberOfRanges >= 7 else {
            return nil
        }
        func intGroup(_ idx: Int) -> Int? {
            guard let r = Range(match.range(at: idx), in: trimmed) else { return nil }
            return Int(trimmed[r])
        }
        guard let year = intGroup(1),
              let month = intGroup(2),
              let day = intGroup(3),
              let hour = intGroup(4),
              let minute = intGroup(5),
              let second = intGroup(6) else {
            return nil
        }
        let tz: TimeZone
        if match.numberOfRanges > 7,
           match.range(at: 7).location != NSNotFound,
           let offsetRange = Range(match.range(at: 7), in: trimmed) {
            let offStr = String(trimmed[offsetRange])
            if offStr.count == 5,
               let sign = offStr.first == "+" ? 1 : (offStr.first == "-" ? -1 : nil),
               let oh = Int(offStr.dropFirst(1).prefix(2)),
               let om = Int(offStr.dropFirst(3).prefix(2)) {
                let secondsFromGMT = sign * (oh * 3600 + om * 60)
                tz = TimeZone(secondsFromGMT: secondsFromGMT) ?? targetTimeZone
            } else {
                tz = targetTimeZone
            }
        } else {
            tz = targetTimeZone
        }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = tz
        var comps = DateComponents()
        comps.calendar = cal
        comps.timeZone = tz
        comps.year = year
        comps.month = month
        comps.day = day
        comps.hour = hour
        comps.minute = minute
        comps.second = second
        return cal.date(from: comps)
    }

    public static func parseXMLTV(data rawData: Data, dayIso: String, timeZone: TimeZone = DiscoveryEngine.istanbulTimeZone) throws -> [SportBroadcastEvent] {
        let payload = try decompressGzipIfNeeded(rawData)
        let text = MavieHTTPClient.decodeText(payload)
        let upperPrefix = text.prefix(4096).uppercased()
        if upperPrefix.contains("<!ENTITY") || upperPrefix.contains("<!DOCTYPE") {
            throw NSError(
                domain: "MavieSports",
                code: 13,
                userInfo: [NSLocalizedDescriptionKey: "Güvenlik nedeniyle XMLTV DTD bildirimlerine izin verilmiyor."]
            )
        }

        let utf8Data = Data(text.utf8)
        let parser = XMLParser(data: utf8Data)
        parser.shouldResolveExternalEntities = false
        parser.shouldProcessNamespaces = false
        parser.shouldReportNamespacePrefixes = false

        let delegate = XMLTVParserDelegate(dayIso: dayIso, timeZone: timeZone)
        parser.delegate = delegate
        guard parser.parse(), !delegate.rejectedDTD else {
            if delegate.rejectedDTD {
                throw NSError(
                    domain: "MavieSports",
                    code: 13,
                    userInfo: [NSLocalizedDescriptionKey: "Güvenlik nedeniyle XMLTV DTD bildirimlerine izin verilmiyor."]
                )
            }
            throw NSError(
                domain: "MavieSports",
                code: 14,
                userInfo: [NSLocalizedDescriptionKey: "XMLTV yayın rehberi okunamadı."]
            )
        }
        guard delegate.rootTag == "tv" else {
            throw NSError(
                domain: "MavieSports",
                code: 15,
                userInfo: [NSLocalizedDescriptionKey: "Geçerli bir XMLTV dosyası değil."]
            )
        }
        return delegate.events.sorted { lhs, rhs in
            if lhs.time != rhs.time { return lhs.time < rhs.time }
            return lhs.id < rhs.id
        }
    }

    private final class XMLTVParserDelegate: NSObject, XMLParserDelegate {
        let dayIso: String
        let timeZone: TimeZone
        let isoFormatter: DateFormatter
        let hhmmFormatter: DateFormatter

        var rootTag: String?
        var rejectedDTD = false
        var channelsMap: [String: [String]] = [:]
        var events: [SportBroadcastEvent] = []
        private var seenIds = Set<String>()
        private var programmeIndex = 0

        private var currentChannelId: String?
        private var currentDisplayNames: [String] = []
        private var currentProgChannel: String?
        private var currentProgStart: Date?
        private var currentProgTitle = ""
        private var currentProgCategories: [String] = []
        private var currentProgDesc = ""

        private var elementStack: [String] = []
        private var textBuffer = ""

        init(dayIso: String, timeZone: TimeZone) {
            self.dayIso = dayIso
            self.timeZone = timeZone
            var cal = Calendar(identifier: .gregorian)
            cal.timeZone = timeZone

            let iso = DateFormatter()
            iso.calendar = cal
            iso.timeZone = timeZone
            iso.locale = Locale(identifier: "en_US_POSIX")
            iso.dateFormat = "yyyy-MM-dd"
            self.isoFormatter = iso

            let hhmm = DateFormatter()
            hhmm.calendar = cal
            hhmm.timeZone = timeZone
            hhmm.locale = Locale(identifier: "en_US_POSIX")
            hhmm.dateFormat = "HH:mm"
            self.hhmmFormatter = hhmm
        }

        private func cleanLabel(_ value: String, maxLen: Int) -> String {
            let collapsed = value.split(whereSeparator: \.isWhitespace).joined(separator: " ")
            return String(collapsed.prefix(maxLen))
        }

        func parser(_ parser: XMLParser, foundExternalEntityDeclarationWithName name: String, publicID: String?, systemID: String?) {
            rejectedDTD = true
            parser.abortParsing()
        }

        func parser(_ parser: XMLParser, foundInternalEntityDeclarationWithName name: String, value: String?) {
            rejectedDTD = true
            parser.abortParsing()
        }

        func parser(_ parser: XMLParser, resolveExternalEntityName name: String, systemID: String?) -> Data? {
            rejectedDTD = true
            parser.abortParsing()
            return nil
        }

        func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String: String] = [:]) {
            if rootTag == nil {
                rootTag = elementName
            }
            elementStack.append(elementName)
            textBuffer = ""

            if elementName == "channel", elementStack.count == 2 {
                currentChannelId = cleanLabel(attributeDict["id"] ?? "", maxLen: 120)
                currentDisplayNames = []
            } else if elementName == "programme", elementStack.count == 2 {
                currentProgChannel = cleanLabel(attributeDict["channel"] ?? "", maxLen: 120)
                currentProgStart = SportsGuideService.parseXMLTVTimestamp(attributeDict["start"] ?? "", targetTimeZone: timeZone)
                currentProgTitle = ""
                currentProgCategories = []
                currentProgDesc = ""
            }
        }

        func parser(_ parser: XMLParser, foundCharacters string: String) {
            textBuffer.append(string)
        }

        func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) {
            defer {
                if !elementStack.isEmpty { elementStack.removeLast() }
                textBuffer = ""
            }
            let parent = elementStack.count >= 2 ? elementStack[elementStack.count - 2] : ""
            if elementName == "display-name" && parent == "channel" {
                let name = cleanLabel(textBuffer, maxLen: 100)
                if !name.isEmpty { currentDisplayNames.append(name) }
            } else if elementName == "channel" && elementStack.count == 2 {
                if let cid = currentChannelId, !cid.isEmpty {
                    channelsMap[cid] = currentDisplayNames.isEmpty ? [cid] : currentDisplayNames
                }
                currentChannelId = nil
                currentDisplayNames = []
            } else if elementName == "title" && parent == "programme" {
                if currentProgTitle.isEmpty {
                    currentProgTitle = cleanLabel(textBuffer, maxLen: 180)
                }
            } else if elementName == "category" && parent == "programme" {
                let cat = cleanLabel(textBuffer, maxLen: 60)
                if !cat.isEmpty { currentProgCategories.append(cat) }
            } else if elementName == "desc" && parent == "programme" {
                if currentProgDesc.isEmpty {
                    currentProgDesc = cleanLabel(textBuffer, maxLen: 240)
                }
            } else if elementName == "programme" && elementStack.count == 2 {
                let idx = programmeIndex
                programmeIndex += 1
                defer {
                    currentProgChannel = nil
                    currentProgStart = nil
                }
                guard let startDt = currentProgStart,
                      isoFormatter.string(from: startDt) == dayIso,
                      let channelId = currentProgChannel,
                      !channelId.isEmpty,
                      !currentProgTitle.isEmpty else {
                    return
                }
                let chNames = channelsMap[channelId] ?? [channelId]
                let isSport = currentProgCategories.contains { cat in
                    let r = NSRange(cat.startIndex..<cat.endIndex, in: cat)
                    return SportsGuideService.sportCategoryRegex.firstMatch(in: cat, range: r) != nil
                } || {
                    let r = NSRange(currentProgTitle.startIndex..<currentProgTitle.endIndex, in: currentProgTitle)
                    return SportsGuideService.sportCategoryRegex.firstMatch(in: currentProgTitle, range: r) != nil
                }()
                let sportLabel = currentProgCategories.first ?? (isSport ? "Spor" : "Canlı Yayın")
                let leagueLabel = currentProgCategories.count > 1 ? currentProgCategories[1] : String(currentProgDesc.prefix(90))
                let hhmm = hhmmFormatter.string(from: startDt)
                let compactHm = hhmm.replacingOccurrences(of: ":", with: "")
                let eid = "\(channelId):\(compactHm):\(idx)"
                guard seenIds.insert(eid).inserted else { return }

                events.append(
                    SportBroadcastEvent(
                        id: eid,
                        title: currentProgTitle,
                        sport: sportLabel,
                        league: leagueLabel,
                        time: hhmm,
                        featured: isSport,
                        channels: chNames
                    )
                )
            }
        }
    }

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

    public func load(
        dayIso: String,
        epgUrl: String = "",
        sourceMode: String = "auto",
        force: Bool = false,
        session: URLSession = MavieHTTPClient.sharedSession
    ) async throws -> SportsGuideResponse {
        let mode = sourceMode.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let epg = epgUrl.trimmingCharacters(in: .whitespacesAndNewlines)

        if mode == "xmltv" && epg.isEmpty {
            return SportsGuideResponse(date: dayIso, events: [], stale: false, sourceType: "xmltv", configured: false)
        }

        let useXmltv = !epg.isEmpty && mode != "sporekrani"
        let sourceType = useXmltv ? "xmltv" : "sporekrani"
        let sourceURLString = useXmltv ? epg : (Self.sourceBase + dayIso)
        let freshTTL: TimeInterval = useXmltv ? 900 : 300
        let cacheKey = "\(useXmltv ? epg : "sporekrani")|\(dayIso)"

        let now = Date().timeIntervalSince1970
        let cached = cache[cacheKey]
        if !force, let cached, now - cached.fetchedAt < freshTTL {
            return SportsGuideResponse(date: dayIso, events: cached.events, stale: false, sourceType: sourceType, configured: true)
        }

        guard let url = URL(string: sourceURLString),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https" else {
            throw NSError(
                domain: "MavieSports",
                code: 5,
                userInfo: [NSLocalizedDescriptionKey: useXmltv ? "Geçersiz XMLTV EPG adresi." : "Geçersiz spor rehberi adresi."]
            )
        }

        var req = URLRequest(url: url)
        req.timeoutInterval = useXmltv ? 20 : 12
        req.setValue(useXmltv ? "Mavie/2.2 (XMLTV EPG)" : "Mavie/2.2 (sports schedule)", forHTTPHeaderField: "User-Agent")

        do {
            let (data, resp) = try await MavieHTTPClient.fetchData(
                for: req,
                session: session,
                context: useXmltv ? "XMLTV yayın rehberi" : "Spor yayın rehberi",
                fallbackUserAgent: MavieHTTPClient.browserUserAgent,
                retryDelays: [0.3, 0.9]
            )
            let events: [SportBroadcastEvent]
            if useXmltv {
                events = try Self.parseXMLTV(data: data, dayIso: dayIso)
            } else {
                let html = MavieHTTPClient.decodeText(data, response: resp)
                events = try Self.parseSporekrani(page: html, dayIso: dayIso)
            }
            cache[cacheKey] = CacheEntry(fetchedAt: now, events: events)
            return SportsGuideResponse(date: dayIso, events: events, stale: false, sourceType: sourceType, configured: true)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            if let cached, now - cached.fetchedAt <= 12 * 3600 {
                return SportsGuideResponse(date: dayIso, events: cached.events, stale: true, sourceType: sourceType, configured: true)
            }
            let fallbackMsg = useXmltv
                ? "XMLTV yayın rehberine ulaşılamadı. Bağlantıyı kontrol edin."
                : "Spor yayın rehberine ulaşılamadı. Biraz sonra tekrar dene."
            throw NSError(
                domain: "MavieSports",
                code: 7,
                userInfo: [NSLocalizedDescriptionKey: fallbackMsg]
            )
        }
    }
}
