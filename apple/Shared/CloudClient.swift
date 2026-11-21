import Foundation
import Security

public struct CloudRegisterResponse: Codable, Sendable {
    public var ok: Bool
    public var verificationRequired: Bool
    public var emailVerified: Bool
    public var deliveryMode: String?
    public var user: CloudUser
}

public struct CloudVerifyEmailResponse: Codable, Sendable {
    public var ok: Bool
    public var token: String
    public var trialActivated: Bool
    public var user: CloudUser
}

public struct CloudAuthResponse: Codable, Sendable {
    public var ok: Bool
    public var token: String
    public var user: CloudUser
}

public struct CloudDeliveryResponse: Codable, Sendable {
    public var ok: Bool
    public var deliveryMode: String?
    public var message: String?
}

public struct CloudVerifyResetResponse: Codable, Sendable {
    public var ok: Bool
    public var valid: Bool
}

public struct CloudOkResponse: Codable, Sendable {
    public var ok: Bool
}

public struct CloudDevicesResponse: Codable, Sendable {
    public var ok: Bool?
    public var devices: [CloudDevice]
}

public struct CloudMeResponse: Codable, Sendable {
    public var user: CloudUser
}

public struct CloudRedeemResponse: Codable, Sendable {
    public var ok: Bool
    public var user: CloudUser
}

public struct CloudSyncResponse: Codable, Sendable {
    public var ok: Bool?
    public var state: CloudSyncPayload?
    public var updatedAt: String?
}

public enum CloudSessionKeychain {
    private static let service = "app.mavie.cloud"
    private static let tokenAccount = "session_token"

    public static func saveToken(_ token: String) {
        let data = Data(token.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
        ]
        SecItemDelete(query as CFDictionary)
        var addQuery = query
        addQuery[kSecValueData as String] = data
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(addQuery as CFDictionary, nil)
    }

    public static func loadToken() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    public static func deleteToken() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
        ]
        SecItemDelete(query as CFDictionary)
    }
}

public final class CloudClient: @unchecked Sendable {
    public static let defaultPortalURL = "https://cineva-app.netlify.app"

    private let session: URLSession
    private let decoder: JSONDecoder

    public init(session: URLSession = .shared) {
        self.session = session
        self.decoder = JSONDecoder()
    }

    public static func validateBaseURL(_ raw: String) throws -> URL {
        var trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        while trimmed.hasSuffix("/") {
            trimmed.removeLast()
        }
        guard !trimmed.isEmpty else {
            throw MavieError.invalidURL("Bulut portalı adresi boş olamaz.")
        }
        if !trimmed.contains("://") {
            trimmed = "https://" + trimmed
        }
        guard var components = URLComponents(string: trimmed),
              let scheme = components.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = components.host,
              !host.isEmpty else {
            throw MavieError.invalidURL("Geçerli bir bulut portalı adresi girin.")
        }
        if components.user != nil || components.password != nil {
            throw MavieError.validation("Bulut portalı adresinde gömülü kimlik bilgisi kullanılamaz.")
        }
        if components.query != nil || components.fragment != nil {
            throw MavieError.validation("Bulut portalı adresi sorgu parametresi veya # içeremez.")
        }
        if scheme == "http" && !isLocalOrPrivateHost(host) {
            throw MavieError.insecureTransport("Uzak bulut sunucuları için HTTPS zorunludur.")
        }
        components.path = components.path == "/" ? "" : components.path
        guard let url = components.url else {
            throw MavieError.invalidURL("Bulut portalı adresi geçersiz.")
        }
        return url
    }

    public static func isLocalOrPrivateHost(_ host: String) -> Bool {
        let lower = host.lowercased()
        if lower == "localhost" || lower == "127.0.0.1" || lower == "::1" || lower.hasSuffix(".local") {
            return true
        }
        let parts = lower.split(separator: ".").compactMap { Int($0) }
        guard parts.count == 4 else { return false }
        if parts[0] == 10 || parts[0] == 127 { return true }
        if parts[0] == 192 && parts[1] == 168 { return true }
        if parts[0] == 172 && (16...31).contains(parts[1]) { return true }
        if parts[0] == 169 && parts[1] == 254 { return true }
        return false
    }

    public static func decodeApiError(status: Int, data: Data) -> CloudApiError {
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            let msg = (json["error"] as? String) ?? (json["message"] as? String) ?? "Bulut sunucusu hatası (HTTP \(status))."
            let code = (json["code"] as? String) ?? ""
            let verificationRequired = (json["verificationRequired"] as? Bool) ?? (code == "EMAIL_NOT_VERIFIED")
            let upgradeRequired = (json["upgradeRequired"] as? Bool) ?? (code == "PRO_REQUIRED")
            let email = json["email"] as? String
            let maxDevices = json["maxDevices"] as? Int
            return CloudApiError(
                status: status,
                message: msg,
                code: code,
                verificationRequired: verificationRequired,
                upgradeRequired: upgradeRequired,
                email: email,
                maxDevices: maxDevices
            )
        }
        return CloudApiError(status: status, message: "Bulut isteği başarısız oldu (HTTP \(status)).")
    }

    // MARK: - Public Endpoints

    public func fetchAppConfig(baseURL: String = CloudClient.defaultPortalURL) async throws -> CloudAppConfig {
        try await request(baseURL: baseURL, path: "/api/v1/app-config", method: "GET")
    }

    public func register(
        baseURL: String = CloudClient.defaultPortalURL,
        email: String,
        password: String,
        displayName: String
    ) async throws -> CloudRegisterResponse {
        try await request(
            baseURL: baseURL,
            path: "/api/v1/auth/register",
            method: "POST",
            body: [
                "email": email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
                "password": password,
                "displayName": displayName.trimmingCharacters(in: .whitespacesAndNewlines),
            ]
        )
    }

    public func verifyEmail(
        baseURL: String = CloudClient.defaultPortalURL,
        email: String,
        code: String = "",
        token: String = ""
    ) async throws -> CloudVerifyEmailResponse {
        var payload: [String: Any] = [
            "email": email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
        ]
        let cleanCode = code.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanToken = token.trimmingCharacters(in: .whitespacesAndNewlines)
        if !cleanCode.isEmpty { payload["code"] = cleanCode }
        if !cleanToken.isEmpty { payload["token"] = cleanToken }
        return try await request(baseURL: baseURL, path: "/api/v1/auth/verify-email", method: "POST", body: payload)
    }

    public func resendVerification(
        baseURL: String = CloudClient.defaultPortalURL,
        email: String
    ) async throws -> CloudDeliveryResponse {
        try await request(
            baseURL: baseURL,
            path: "/api/v1/auth/resend-verification",
            method: "POST",
            body: ["email": email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()]
        )
    }

    public func login(
        baseURL: String = CloudClient.defaultPortalURL,
        email: String,
        password: String
    ) async throws -> CloudAuthResponse {
        try await request(
            baseURL: baseURL,
            path: "/api/v1/auth/login",
            method: "POST",
            body: [
                "email": email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
                "password": password,
            ]
        )
    }

    public func forgotPassword(
        baseURL: String = CloudClient.defaultPortalURL,
        email: String
    ) async throws -> CloudDeliveryResponse {
        try await request(
            baseURL: baseURL,
            path: "/api/v1/auth/forgot-password",
            method: "POST",
            body: ["email": email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()]
        )
    }

    public func verifyResetCode(
        baseURL: String = CloudClient.defaultPortalURL,
        email: String,
        code: String = "",
        token: String = ""
    ) async throws -> CloudVerifyResetResponse {
        var payload: [String: Any] = [
            "email": email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
        ]
        if !code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload["code"] = code.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        if !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload["token"] = token.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return try await request(baseURL: baseURL, path: "/api/v1/auth/verify-reset-code", method: "POST", body: payload)
    }

    public func resetPassword(
        baseURL: String = CloudClient.defaultPortalURL,
        email: String,
        code: String = "",
        token: String = "",
        newPassword: String
    ) async throws -> CloudOkResponse {
        var payload: [String: Any] = [
            "email": email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            "newPassword": newPassword,
        ]
        if !code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload["code"] = code.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        if !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload["token"] = token.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return try await request(baseURL: baseURL, path: "/api/v1/auth/reset-password", method: "POST", body: payload)
    }

    // MARK: - Authenticated Endpoints

    public func fetchMe(baseURL: String = CloudClient.defaultPortalURL, token: String) async throws -> CloudUser {
        let resp: CloudMeResponse = try await request(baseURL: baseURL, path: "/api/v1/me", method: "GET", token: token)
        return resp.user
    }

    public func registerDevice(
        baseURL: String = CloudClient.defaultPortalURL,
        token: String,
        deviceId: String,
        deviceName: String,
        platform: String
    ) async throws -> [CloudDevice] {
        let resp: CloudDevicesResponse = try await request(
            baseURL: baseURL,
            path: "/api/v1/devices/register",
            method: "POST",
            token: token,
            body: [
                "deviceId": deviceId,
                "deviceName": deviceName,
                "platform": platform,
            ]
        )
        return resp.devices
    }

    public func removeDevice(
        baseURL: String = CloudClient.defaultPortalURL,
        token: String,
        deviceId: String
    ) async throws -> [CloudDevice] {
        let encoded = deviceId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? deviceId
        let resp: CloudDevicesResponse = try await request(
            baseURL: baseURL,
            path: "/api/v1/devices/\(encoded)",
            method: "DELETE",
            token: token
        )
        return resp.devices
    }

    public func redeemLicense(
        baseURL: String = CloudClient.defaultPortalURL,
        token: String,
        code: String
    ) async throws -> CloudUser {
        let resp: CloudRedeemResponse = try await request(
            baseURL: baseURL,
            path: "/api/v1/licenses/redeem",
            method: "POST",
            token: token,
            body: ["code": code.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()]
        )
        return resp.user
    }

    public func pullSync(baseURL: String = CloudClient.defaultPortalURL, token: String) async throws -> CloudSyncResponse {
        try await request(baseURL: baseURL, path: "/api/v1/sync", method: "GET", token: token)
    }

    public func pushSync(
        baseURL: String = CloudClient.defaultPortalURL,
        token: String,
        payload: CloudSyncPayload
    ) async throws -> CloudSyncResponse {
        let encoder = JSONEncoder()
        let raw = try encoder.encode(payload)
        let reqObj = (try JSONSerialization.jsonObject(with: raw) as? [String: Any]) ?? [:]
        return try await request(baseURL: baseURL, path: "/api/v1/sync", method: "PUT", token: token, body: ["state": reqObj])
    }

    // MARK: - HTTP Core

    private func request<T: Decodable>(
        baseURL: String,
        path: String,
        method: String,
        token: String? = nil,
        body: [String: Any]? = nil
    ) async throws -> T {
        let validated = try Self.validateBaseURL(baseURL)
        guard let url = URL(string: validated.absoluteString + path) else {
            throw MavieError.invalidURL("Bulut API adresi geçersiz.")
        }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.timeoutInterval = 20
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("Mavie/2.1", forHTTPHeaderField: "User-Agent")
        if let token, !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            req.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            throw MavieError.network("Bulut sunucusuna bağlanılamadı: \(error.localizedDescription)")
        }

        guard let http = response as? HTTPURLResponse else {
            throw MavieError.network("Geçersiz sunucu yanıtı.")
        }

        if !(200...299).contains(http.statusCode) {
            throw MavieError.api(Self.decodeApiError(status: http.statusCode, data: data))
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw MavieError.parsing("Bulut yanıtı ayrıştırılamadı: \(error.localizedDescription)")
        }
    }
}
