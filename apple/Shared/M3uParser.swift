import CryptoKit
import Foundation

public struct M3uParseResult: Sendable, Equatable {
    public var epgUrl: String
    public var items: [MediaItem]
    public var categories: [MediaCategory]

    public init(epgUrl: String, items: [MediaItem], categories: [MediaCategory]) {
        self.epgUrl = epgUrl
        self.items = items
        self.categories = categories
    }
}

public enum M3uParser {
    private static let attrRegex = try! NSRegularExpression(pattern: #"([A-Za-z0-9_-]+)="([^"]*)""#)
    private static let extRegex = try! NSRegularExpression(pattern: #"\.([a-z0-9]{2,5})(?:[?#]|$)"#, options: [.caseInsensitive])
    private static let vodExtensions: Set<String> = ["mp4", "mkv", "avi", "mov", "webm", "m4v"]

    private struct PendingEntry {
        var name: String
        var tvgId: String
        var poster: String
        var group: String
        var type: String
    }

    public static func parse(_ text: String) -> M3uParseResult {
        var epgUrl = ""
        var items: [MediaItem] = []
        var categoryMap: [String: MediaCategory] = [:]
        var pending: PendingEntry?

        let lines = text.components(separatedBy: .newlines)
        for raw in lines {
            let line = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if line.isEmpty { continue }

            if line.hasPrefix("#EXTM3U") {
                let attrs = extractAttributes(from: line)
                epgUrl = attrs["url-tvg"] ?? attrs["x-tvg-url"] ?? ""
                continue
            }

            if line.hasPrefix("#EXTINF:") {
                let attrs = extractAttributes(from: line)
                let title: String
                if let commaIndex = line.firstIndex(of: ",") {
                    title = String(line[line.index(after: commaIndex)...]).trimmingCharacters(in: .whitespacesAndNewlines)
                } else {
                    title = attrs["tvg-name"] ?? ""
                }
                let finalName = String((title.isEmpty ? (attrs["tvg-name"] ?? "Adsız Yayın") : title).prefix(500))
                let group = String((attrs["group-title"] ?? "").prefix(200))
                pending = PendingEntry(
                    name: finalName.isEmpty ? "Adsız Yayın" : finalName,
                    tvgId: String((attrs["tvg-id"] ?? "").prefix(100)),
                    poster: safeImage(String((attrs["tvg-logo"] ?? "").prefix(3000))),
                    group: group.isEmpty ? "Genel" : group,
                    type: (attrs["type"] ?? "").lowercased()
                )
                continue
            }

            if line.hasPrefix("#") {
                continue
            }

            let lower = line.lowercased()
            if lower.hasPrefix("http://") || lower.hasPrefix("https://") {
                let fallbackTitle = line.split(separator: "/").last.map(String.init) ?? "Akış"
                let meta = pending ?? PendingEntry(
                    name: String(fallbackTitle.prefix(120)),
                    tvgId: "",
                    poster: "",
                    group: "Genel",
                    type: ""
                )
                pending = nil

                let ext = extractExtension(from: line) ?? "m3u8"
                let isVod = meta.type == "movie" || meta.type == "vod" || vodExtensions.contains(ext)
                let kind: MediaKind = isVod ? .vod : .live
                let digest = sha1Hex("\(kind.rawValue):\(line)", length: 16)
                let categoryId = sha1Hex(meta.group, length: 10)

                if categoryMap[categoryId] == nil {
                    categoryMap[categoryId] = MediaCategory(id: categoryId, name: meta.group, kind: kind)
                }

                let item = MediaItem(
                    id: "\(kind.rawValue):m3u_\(digest)",
                    providerId: "m3u_\(digest)",
                    name: meta.name,
                    kind: kind,
                    categoryId: categoryId,
                    categoryName: meta.group,
                    poster: meta.poster,
                    extensionName: String(ext.prefix(12)),
                    addedAt: TimeInterval(items.count + 1),
                    sourceUrl: line,
                    tvgId: meta.tvgId
                )
                items.append(item)
            }
        }

        let categories = categoryMap.values.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        return M3uParseResult(epgUrl: epgUrl, items: items, categories: categories)
    }

    private static func extractAttributes(from line: String) -> [String: String] {
        var result: [String: String] = [:]
        let nsRange = NSRange(line.startIndex..<line.endIndex, in: line)
        for match in attrRegex.matches(in: line, range: nsRange) {
            guard match.numberOfRanges >= 3,
                  let keyRange = Range(match.range(at: 1), in: line),
                  let valRange = Range(match.range(at: 2), in: line) else { continue }
            result[String(line[keyRange]).lowercased()] = String(line[valRange])
        }
        return result
    }

    private static func extractExtension(from url: String) -> String? {
        let nsRange = NSRange(url.startIndex..<url.endIndex, in: url)
        guard let match = extRegex.firstMatch(in: url, range: nsRange),
              match.numberOfRanges >= 2,
              let extRange = Range(match.range(at: 1), in: url) else {
            return nil
        }
        return String(url[extRange]).lowercased()
    }

    private static func safeImage(_ value: String) -> String {
        let lower = value.lowercased()
        if lower.hasPrefix("https://") || lower.hasPrefix("http://") {
            return value
        }
        return ""
    }

    private static func sha1Hex(_ input: String, length: Int) -> String {
        let digest = Insecure.SHA1.hash(data: Data(input.utf8))
        let hex = digest.map { String(format: "%02x", $0) }.joined()
        return String(hex.prefix(length))
    }
}
