import Foundation
import Security

public struct StoredCredentials: Codable, Equatable, Sendable {
    public var xtreamPassword: String
    public var m3uUrl: String
    public var epgUrl: String

    public init(xtreamPassword: String = "", m3uUrl: String = "", epgUrl: String = "") {
        self.xtreamPassword = xtreamPassword
        self.m3uUrl = m3uUrl
        self.epgUrl = epgUrl
    }

    public var isEmpty: Bool {
        xtreamPassword.isEmpty && m3uUrl.isEmpty && epgUrl.isEmpty
    }
}

public final class CredentialVault: @unchecked Sendable {
    private let service: String
    private let account: String
    private let fallbackFileURL: URL
    private let useKeychain: Bool
    private let lock = NSLock()

    public init(
        service: String = "app.mavie.credentials",
        account: String = "default",
        fallbackFileURL: URL,
        useKeychain: Bool
    ) {
        self.service = service
        self.account = account
        self.fallbackFileURL = fallbackFileURL
        self.useKeychain = useKeychain
    }

    public func load() -> StoredCredentials {
        lock.lock()
        defer { lock.unlock() }

        if useKeychain {
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: account,
                kSecReturnData as String: true,
                kSecMatchLimit as String: kSecMatchLimitOne,
            ]
            var result: AnyObject?
            let status = SecItemCopyMatching(query as CFDictionary, &result)
            if status == errSecSuccess,
               let data = result as? Data,
               let decoded = try? JSONDecoder().decode(StoredCredentials.self, from: data) {
                return decoded
            }
            if status != errSecItemNotFound && status != errSecSuccess {
                return loadRestrictedFile() ?? StoredCredentials()
            }
            return loadRestrictedFile() ?? StoredCredentials()
        }

        return loadRestrictedFile() ?? StoredCredentials()
    }

    public func save(_ credentials: StoredCredentials) throws {
        lock.lock()
        defer { lock.unlock() }

        if credentials.isEmpty {
            try clearLocked()
            return
        }

        let data = try JSONEncoder().encode(credentials)

        if useKeychain {
            let baseQuery: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: account,
            ]
            let updateAttrs: [String: Any] = [
                kSecValueData as String: data,
                kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
            ]
            let updateStatus = SecItemUpdate(baseQuery as CFDictionary, updateAttrs as CFDictionary)
            if updateStatus == errSecSuccess {
                removeRestrictedFileIfPresent()
                return
            }
            if updateStatus == errSecItemNotFound {
                var addQuery = baseQuery
                addQuery[kSecValueData as String] = data
                addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
                let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
                if addStatus == errSecSuccess {
                    removeRestrictedFileIfPresent()
                    return
                }
                if isKeychainFallbackStatus(addStatus) {
                    try saveRestrictedFile(data)
                    return
                }
                throw MavieError.validation("Kimlik bilgileri Keychain'e kaydedilemedi (kod: \(addStatus)).")
            }
            if isKeychainFallbackStatus(updateStatus) {
                try saveRestrictedFile(data)
                return
            }
            throw MavieError.validation("Kimlik bilgileri Keychain'de güncellenemedi (kod: \(updateStatus)).")
        }

        try saveRestrictedFile(data)
    }

    public func clear() throws {
        lock.lock()
        defer { lock.unlock() }
        try clearLocked()
    }

    private func clearLocked() throws {
        if useKeychain {
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: account,
            ]
            let status = SecItemDelete(query as CFDictionary)
            if status != errSecSuccess && status != errSecItemNotFound && !isKeychainFallbackStatus(status) {
                throw MavieError.validation("Kimlik bilgileri Keychain'den silinemedi (kod: \(status)).")
            }
        }
        removeRestrictedFileIfPresent()
    }

    private func isKeychainFallbackStatus(_ status: OSStatus) -> Bool {
        status == errSecMissingEntitlement || status == errSecInteractionNotAllowed || status == errSecNotAvailable
    }

    private func loadRestrictedFile() -> StoredCredentials? {
        guard FileManager.default.fileExists(atPath: fallbackFileURL.path),
              let data = try? Data(contentsOf: fallbackFileURL),
              let decoded = try? JSONDecoder().decode(StoredCredentials.self, from: data) else {
            return nil
        }
        return decoded
    }

    private func saveRestrictedFile(_ data: Data) throws {
        let dir = fallbackFileURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        #if os(iOS)
        try data.write(to: fallbackFileURL, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: fallbackFileURL, options: [.atomic])
        #endif
        try? FileManager.default.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: fallbackFileURL.path
        )
    }

    private func removeRestrictedFileIfPresent() {
        if FileManager.default.fileExists(atPath: fallbackFileURL.path) {
            try? FileManager.default.removeItem(at: fallbackFileURL)
        }
    }
}
