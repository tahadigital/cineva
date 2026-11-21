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

    public static func validateLanAddress(_ raw: String) throws -> URL {
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
        guard isAllowedLanHost(host) else {
            throw MavieError.validation("Eşitleme için aynı Wi-Fi ağındaki yerel (RFC1918/loopback) adresi kullanın.")
        }
        if components.port == nil && !host.contains(":") {
            components.port = 8844
        }
        components.path = ""
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

    public static func isAllowedLanHost(_ host: String) -> Bool {
        let lower = host.lowercased()
        if lower == "localhost" || lower == "::1" || lower.hasSuffix(".local") {
            return true
        }
        if isPrivateOrLoopbackIPv4(lower) || isPrivateOrLoopbackIPv6(lower) {
            return true
        }
        // If hostname is not a raw IP, resolve and verify every resolved IP is local/private.
        var hints = addrinfo()
        hints.ai_family = AF_UNSPEC
        hints.ai_socktype = SOCK_STREAM
        var res: UnsafeMutablePointer<addrinfo>?
        guard getaddrinfo(host, nil, &hints, &res) == 0, let first = res else {
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
        let stripped = ip.split(separator: "%").first.map(String.init) ?? ip
        var addr = in6_addr()
        guard inet_pton(AF_INET6, stripped, &addr) == 1 else { return false }
        let bytes = withUnsafeBytes(of: addr) { Array($0) }
        guard bytes.count == 16 else { return false }
        let isLoopback = bytes[0..<15].allSatisfy { $0 == 0 } && bytes[15] == 1
        let isLinkLocal = bytes[0] == 0xFE && (bytes[1] & 0xC0) == 0x80
        let isUniqueLocal = (bytes[0] & 0xFE) == 0xFC
        return isLoopback || isLinkLocal || isUniqueLocal
    }

    public static func merge(
        address: String,
        code: String,
        localExportDictionary: [String: Any],
        session: URLSession = .shared
    ) async throws -> [String: Any] {
        let base = try validateLanAddress(address)
        let validCode = try validatePairingCode(code)

        // 1. Pair
        guard let pairURL = URL(string: base.absoluteString + "/api/pair") else {
            throw MavieError.invalidURL("Eşleştirme adresi geçersiz.")
        }
        var pairReq = URLRequest(url: pairURL)
        pairReq.httpMethod = "POST"
        pairReq.timeoutInterval = 10
        pairReq.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        pairReq.httpBody = try JSONSerialization.data(withJSONObject: ["code": validCode])

        let (_, pairResp) = try await session.data(for: pairReq)
        guard let pairHttp = pairResp as? HTTPURLResponse else {
            throw MavieError.network("Masaüstü sunucusundan yanıt alınamadı.")
        }
        guard (200...299).contains(pairHttp.statusCode) else {
            throw MavieError.validation(pairHttp.statusCode == 403 ? "Eşleştirme kodu hatalı." : "Masaüstü sunucusuyla eşleştirme başarısız.")
        }
        guard let setCookie = pairHttp.value(forHTTPHeaderField: "Set-Cookie"),
              let cookieHeader = setCookie.split(separator: ";").first.map(String.init),
              !cookieHeader.isEmpty else {
            throw MavieError.network("Masaüstü eşleştirme çerezi alınamadı.")
        }

        // 2. Pull remote export
        guard let exportURL = URL(string: base.absoluteString + "/api/export") else {
            throw MavieError.invalidURL("Dışa aktarım adresi geçersiz.")
        }
        var exportReq = URLRequest(url: exportURL)
        exportReq.timeoutInterval = 15
        exportReq.setValue(cookieHeader, forHTTPHeaderField: "Cookie")

        let (exportData, exportResp) = try await session.data(for: exportReq)
        guard let exportHttp = exportResp as? HTTPURLResponse, (200...299).contains(exportHttp.statusCode) else {
            throw MavieError.network("Masaüstü kütüphanesi okunamadı.")
        }
        guard exportData.count <= maxBackupBytes else {
            throw MavieError.validation("Masaüstü yedek boyutu çok büyük.")
        }
        guard let remoteObj = try JSONSerialization.jsonObject(with: exportData) as? [String: Any] else {
            throw MavieError.parsing("Masaüstü yedek verisi ayrıştırılamadı.")
        }

        // 3. Push local backup back to desktop
        guard let importURL = URL(string: base.absoluteString + "/api/import") else {
            throw MavieError.invalidURL("İçe aktarım adresi geçersiz.")
        }
        var importReq = URLRequest(url: importURL)
        importReq.httpMethod = "POST"
        importReq.timeoutInterval = 15
        importReq.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        importReq.setValue(cookieHeader, forHTTPHeaderField: "Cookie")
        importReq.httpBody = try JSONSerialization.data(withJSONObject: ["data": localExportDictionary])

        let (importData, importResp) = try await session.data(for: importReq)
        guard let importHttp = importResp as? HTTPURLResponse else {
            throw MavieError.network("Masaüstü sunucusundan içe aktarım yanıtı alınamadı.")
        }
        guard (200...299).contains(importHttp.statusCode) else {
            let serverErr = (try? JSONSerialization.jsonObject(with: importData) as? [String: Any])?["error"] as? String
            throw MavieError.validation(serverErr ?? "Masaüstü sunucusu yedek verisini kabul etmedi (HTTP \(importHttp.statusCode)).")
        }

        return remoteObj
    }
}
