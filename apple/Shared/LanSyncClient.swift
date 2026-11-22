import Darwin
import Foundation

public struct LanExportPayload: Codable, Sendable {
    public var version: Int?
    public var exportedAt: String?
    public var items: [MediaItem]?
    public var favorites: [SyncFavoriteRecord]?
    public var progress: [WatchProgress]?
    public var playlists: [Playlist]?
    public var playlistItems: [SyncPlaylistItemRecord]?
    public var trackPreferences: [SyncTrackPreferenceRecord]?
}

public enum LanSyncClient {
    public static let maxBackupBytes = 25 * 1024 * 1024

    private static func parseLanComponents(_ raw: String) throws -> (components: URLComponents, host: String) {
        var trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        while trimmed.hasSuffix("/") {
            trimmed.removeLast()
        }
        guard !trimmed.isEmpty else {
            throw MavieError.invalidURL("Masaüstü sunucusunun yerel ağ adresini girin (ör. 192.168.1.25:8844).")
        }
        if !trimmed.contains("://") {
            trimmed = "http://" + trimmed
        }
        guard var components = URLComponents(string: trimmed),
              let scheme = components.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = components.host,
              !host.isEmpty else {
            throw MavieError.invalidURL("Geçerli bir yerel ağ adresi girin.")
        }
        if components.user != nil || components.password != nil || components.query != nil || components.fragment != nil {
            throw MavieError.validation("Yalnızca sunucunun yerel ağ adresini ve portunu girin.")
        }
        if components.port == nil {
            components.port = 8844
        }
        components.path = ""
        return (components, host)
    }

    public static func validateLanAddress(_ raw: String) throws -> URL {
        let (components, host) = try parseLanComponents(raw)
        guard isAllowedLanHost(host) else {
            throw MavieError.validation("Eşitleme için aynı Wi-Fi ağındaki yerel (RFC1918/loopback) adresi kullanın.")
        }
        guard let url = components.url else {
            throw MavieError.invalidURL("Yerel ağ adresi oluşturulamadı.")
        }
        return url
    }

    public static func resolveAndValidateLanAddress(_ raw: String) async throws -> URL {
        let (components, host) = try parseLanComponents(raw)
        let lower = host.lowercased()
        let allowed: Bool
        if lower == "localhost" || lower == "::1" || lower.hasSuffix(".local") || isNumericIPLiteral(lower) {
            allowed = isAllowedLanHost(host)
        } else {
            allowed = await withCheckedContinuation { continuation in
                DispatchQueue.global(qos: .userInitiated).async {
                    continuation.resume(returning: isAllowedLanHost(host))
                }
            }
        }
        guard allowed else {
            throw MavieError.validation("Eşitleme için aynı Wi-Fi ağındaki yerel (RFC1918/loopback) adresi kullanın.")
        }
        guard let url = components.url else {
            throw MavieError.invalidURL("Yerel ağ adresi oluşturulamadı.")
        }
        return url
    }

    public static func validatePairingCode(_ code: String) throws -> String {
        let clean = code.trimmingCharacters(in: .whitespacesAndNewlines)
        guard clean.count == 6, clean.allSatisfy(\.isNumber) else {
            throw MavieError.validation("Masaüstü uygulamasındaki 6 haneli eşleştirme kodunu girin.")
        }
        return clean
    }

    private static func unbracketHost(_ host: String) -> String {
        if host.hasPrefix("[") && host.hasSuffix("]") && host.count >= 2 {
            return String(host.dropFirst().dropLast())
        }
        return host
    }

    public static func isNumericIPLiteral(_ host: String) -> Bool {
        let clean = unbracketHost(host)
        var addr4 = in_addr()
        if inet_pton(AF_INET, clean, &addr4) == 1 {
            return true
        }
        let stripped = clean.split(separator: "%").first.map(String.init) ?? clean
        var addr6 = in6_addr()
        return inet_pton(AF_INET6, stripped, &addr6) == 1
    }

    public static func isAllowedLanHost(_ host: String) -> Bool {
        let lower = unbracketHost(host).lowercased()
        if lower == "localhost" || lower == "::1" || lower.hasSuffix(".local") {
            return true
        }
        if isNumericIPLiteral(lower) {
            return isPrivateOrLoopbackIPv4(lower) || isPrivateOrLoopbackIPv6(lower)
        }
        // If hostname is not a raw IP, resolve and verify every resolved IP is local/private.
        var hints = addrinfo()
        hints.ai_family = AF_UNSPEC
        hints.ai_socktype = SOCK_STREAM
        var res: UnsafeMutablePointer<addrinfo>?
        guard getaddrinfo(lower, nil, &hints, &res) == 0, let first = res else {
            return false
        }
        defer { freeaddrinfo(res) }
        var resolvedAny = false
        var cursor: UnsafeMutablePointer<addrinfo>? = first
        while let current = cursor {
            if let sa = current.pointee.ai_addr {
                var hostBuffer = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                let rc = getnameinfo(sa, current.pointee.ai_addrlen, &hostBuffer, socklen_t(hostBuffer.count), nil, 0, NI_NUMERICHOST)
                if rc == 0 {
                    resolvedAny = true
                    let ip = String(cString: hostBuffer)
                    if !isPrivateOrLoopbackIPv4(ip) && !isPrivateOrLoopbackIPv6(ip) {
                        return false
                    }
                }
            }
            cursor = current.pointee.ai_next
        }
        return resolvedAny
    }

    public static func isPrivateOrLoopbackIPv4(_ ip: String) -> Bool {
        var addr = in_addr()
        guard inet_pton(AF_INET, ip, &addr) == 1 else { return false }
        let hostOrder = UInt32(bigEndian: addr.s_addr)
        let b0 = (hostOrder >> 24) & 0xFF
        let b1 = (hostOrder >> 16) & 0xFF
        if b0 == 10 || b0 == 127 { return true }
        if b0 == 192 && b1 == 168 { return true }
        if b0 == 172 && (16...31).contains(b1) { return true }
        if b0 == 169 && b1 == 254 { return true }
        return false
    }

    public static func isPrivateOrLoopbackIPv6(_ ip: String) -> Bool {
        let unbracketed = unbracketHost(ip)
        let stripped = unbracketed.split(separator: "%").first.map(String.init) ?? unbracketed
        var addr = in6_addr()
        guard inet_pton(AF_INET6, stripped, &addr) == 1 else { return false }
        let bytes = withUnsafeBytes(of: addr) { Array($0) }
        guard bytes.count == 16 else { return false }
        let isLoopback = bytes[0..<15].allSatisfy { $0 == 0 } && bytes[15] == 1
        let isLinkLocal = bytes[0] == 0xFE && (bytes[1] & 0xC0) == 0x80
        let isUniqueLocal = (bytes[0] & 0xFE) == 0xFC
        return isLoopback || isLinkLocal || isUniqueLocal
    }

    public static func extractCookieHeader(from response: HTTPURLResponse, url: URL) -> String? {
        var headerFields: [String: String] = [:]
        for (k, v) in response.allHeaderFields {
            if let ks = k as? String, let vs = v as? String {
                headerFields[ks] = vs
            }
        }
        let cookies = HTTPCookie.cookies(withResponseHeaderFields: headerFields, for: url)
        if !cookies.isEmpty {
            return cookies.map { "\($0.name)=\($0.value)" }.joined(separator: "; ")
        }
        if let setCookie = response.value(forHTTPHeaderField: "Set-Cookie"),
           let first = setCookie.split(separator: ";").first.map({ String($0).trimmingCharacters(in: .whitespacesAndNewlines) }),
           !first.isEmpty {
            return first
        }
        return nil
    }

    public static func merge(
        address: String,
        code: String,
        localExportDictionary: [String: Any],
        session: URLSession = MavieHTTPClient.lanSession
    ) async throws -> [String: Any] {
        let base = try await resolveAndValidateLanAddress(address)
        let validCode = try validatePairingCode(code)

        // 1. Pair
        let pairURL = base.appendingPathComponent("api").appendingPathComponent("pair")
        var pairReq = URLRequest(url: pairURL)
        pairReq.httpMethod = "POST"
        pairReq.timeoutInterval = 10
        pairReq.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        pairReq.httpBody = try JSONSerialization.data(withJSONObject: ["code": validCode])

        let (_, pairHttp) = try await MavieHTTPClient.fetchData(
            for: pairReq,
            session: session,
            context: "Masaüstü sunucusu",
            fallbackUserAgent: nil,
            retryDelays: [],
            retryOnTransportFailure: false,
            throwOnHTTPError: false
        )
        guard (200...299).contains(pairHttp.statusCode) else {
            throw MavieError.validation(pairHttp.statusCode == 403 ? "Eşleştirme kodu hatalı." : "Masaüstü sunucusuyla eşleştirme başarısız.")
        }
        guard let cookieHeader = extractCookieHeader(from: pairHttp, url: pairURL),
              !cookieHeader.isEmpty else {
            throw MavieError.network("Masaüstü eşleştirme çerezi alınamadı.")
        }

        // 2. Pull remote export
        let exportURL = base.appendingPathComponent("api").appendingPathComponent("export")
        var exportReq = URLRequest(url: exportURL)
        exportReq.timeoutInterval = 15
        exportReq.setValue(cookieHeader, forHTTPHeaderField: "Cookie")

        let (exportData, exportHttp) = try await MavieHTTPClient.fetchData(
            for: exportReq,
            session: session,
            context: "Masaüstü kütüphanesi",
            fallbackUserAgent: nil,
            retryDelays: [0.3, 0.8],
            retryOnTransportFailure: true,
            throwOnHTTPError: false
        )
        guard (200...299).contains(exportHttp.statusCode) else {
            throw MavieError.network("Masaüstü kütüphanesi okunamadı (HTTP \(exportHttp.statusCode)).")
        }
        guard exportData.count <= maxBackupBytes else {
            throw MavieError.validation("Masaüstü yedek boyutu çok büyük.")
        }
        guard let remoteObj = try JSONSerialization.jsonObject(with: exportData) as? [String: Any] else {
            throw MavieError.parsing("Masaüstü yedek verisi ayrıştırılamadı.")
        }

        // 3. Push local backup back to desktop
        let importURL = base.appendingPathComponent("api").appendingPathComponent("import")
        var importReq = URLRequest(url: importURL)
        importReq.httpMethod = "POST"
        importReq.timeoutInterval = 15
        importReq.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        importReq.setValue(cookieHeader, forHTTPHeaderField: "Cookie")
        importReq.httpBody = try JSONSerialization.data(withJSONObject: ["data": localExportDictionary])

        let (importData, importHttp) = try await MavieHTTPClient.fetchData(
            for: importReq,
            session: session,
            context: "Masaüstü sunucusu",
            fallbackUserAgent: nil,
            retryDelays: [],
            retryOnTransportFailure: false,
            throwOnHTTPError: false
        )
        guard (200...299).contains(importHttp.statusCode) else {
            let serverErr = (try? JSONSerialization.jsonObject(with: importData) as? [String: Any])?["error"] as? String
            throw MavieError.validation(serverErr ?? "Masaüstü sunucusu yedek verisini kabul etmedi (HTTP \(importHttp.statusCode)).")
        }

        return remoteObj
    }
}
