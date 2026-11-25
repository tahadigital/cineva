import Foundation

public struct PlaybackSourcePlan: Equatable, Sendable {
    public var primaryURL: URL
    public var liveTSFallbackURL: URL?
    public var isLive: Bool

    public init(primaryURL: URL, liveTSFallbackURL: URL? = nil, isLive: Bool = false) {
        self.primaryURL = primaryURL
        self.liveTSFallbackURL = liveTSFallbackURL
        self.isLive = isLive
    }
}

public struct PlaybackFailureSignal: Equatable, Sendable {
    public var httpStatusCode: Int?
    public var errorDomain: String?
    public var errorCode: Int?
    public var isStallTimeout: Bool
    public var rawMessage: String

    public init(
        httpStatusCode: Int? = nil,
        errorDomain: String? = nil,
        errorCode: Int? = nil,
        isStallTimeout: Bool = false,
        rawMessage: String = ""
    ) {
        self.httpStatusCode = httpStatusCode
        self.errorDomain = errorDomain
        self.errorCode = errorCode
        self.isStallTimeout = isStallTimeout
        self.rawMessage = rawMessage
    }
}

public enum PlaybackRetryReason: Equatable, Sendable {
    case userAgentFallback
    case liveFormatFallback
    case transientReconnect(attempt: Int)
}

public enum PlaybackRecoveryAction: Equatable, Sendable {
    case retry(url: URL, userAgent: String, delaySeconds: TimeInterval, reason: PlaybackRetryReason)
    case fail(message: String)
}

public struct PlaybackTrackCandidate: Equatable, Sendable {
    public var id: String
    public var displayName: String
    public var languageTag: String?

    public init(id: String, displayName: String, languageTag: String? = nil) {
        self.id = id
        self.displayName = displayName
        self.languageTag = languageTag
    }
}

public enum SubtitleMatchResult: Equatable, Sendable {
    case off
    case select(index: Int)
    case keepDefault
}

public struct PlaybackRecoveryState: Equatable, Sendable {
    public var isLive: Bool
    public var currentURL: URL
    public var liveTSFallbackURL: URL?
    public var usedBrowserUserAgent: Bool
    public var usedFormatFallback: Bool
    public var reconnectAttempts: Int
    public var maxReconnectAttempts: Int
    public var currentUserAgent: String
    public var pendingResumeSeconds: Double
    public var hasCompletedInitialSeek: Bool
    public var isScrubbing: Bool

    public init(
        isLive: Bool,
        currentURL: URL,
        liveTSFallbackURL: URL? = nil,
        usedBrowserUserAgent: Bool = false,
        usedFormatFallback: Bool = false,
        reconnectAttempts: Int = 0,
        maxReconnectAttempts: Int = 2,
        currentUserAgent: String = MavieHTTPClient.primaryUserAgent,
        pendingResumeSeconds: Double = 0,
        hasCompletedInitialSeek: Bool = false,
        isScrubbing: Bool = false
    ) {
        self.isLive = isLive
        self.currentURL = currentURL
        self.liveTSFallbackURL = liveTSFallbackURL
        self.usedBrowserUserAgent = usedBrowserUserAgent
        self.usedFormatFallback = usedFormatFallback
        self.reconnectAttempts = reconnectAttempts
        self.maxReconnectAttempts = maxReconnectAttempts
        self.currentUserAgent = currentUserAgent
        self.pendingResumeSeconds = max(0, pendingResumeSeconds)
        self.hasCompletedInitialSeek = hasCompletedInitialSeek
        self.isScrubbing = isScrubbing
    }

    public var canPersistProgress: Bool {
        hasCompletedInitialSeek && !isScrubbing
    }

    public mutating func markReadyToPlay() -> Double? {
        guard !hasCompletedInitialSeek else { return nil }
        hasCompletedInitialSeek = true
        let target = pendingResumeSeconds
        pendingResumeSeconds = 0
        return target > 3 ? target : nil
    }

    public static func shouldPersistProgress(
        duration: Double,
        isLive: Bool,
        hasCompletedInitialSeek: Bool,
        isScrubbing: Bool
    ) -> Bool {
        !isLive && duration.isFinite && duration > 0 && hasCompletedInitialSeek && !isScrubbing
    }

    public mutating func nextAction(
        for failure: PlaybackFailureSignal,
        fallbackURL: (() -> URL?)? = nil
    ) -> PlaybackRecoveryAction {
        let scheme = currentURL.scheme?.lowercased() ?? ""
        let isHTTP = scheme == "http" || scheme == "https"

        if (failure.httpStatusCode == 403 || failure.httpStatusCode == 406),
           !usedBrowserUserAgent,
           isHTTP {
            usedBrowserUserAgent = true
            currentUserAgent = MavieHTTPClient.browserUserAgent
            return .retry(
                url: currentURL,
                userAgent: currentUserAgent,
                delaySeconds: 0.1,
                reason: .userAgentFallback
            )
        }

        if isLive,
           !usedFormatFallback,
           let alt = fallbackURL?() ?? liveTSFallbackURL ?? Self.alternateLiveTSURL(for: currentURL),
           alt != currentURL {
            usedFormatFallback = true
            currentURL = alt
            return .retry(
                url: alt,
                userAgent: currentUserAgent,
                delaySeconds: 0.1,
                reason: .liveFormatFallback
            )
        }

        let permanentHTTP = [401, 403, 404, 410].contains(failure.httpStatusCode ?? -1)
        if !permanentHTTP,
           (isLive || failure.isStallTimeout || Self.isTransientTransportFailure(failure)),
           reconnectAttempts < maxReconnectAttempts {
            reconnectAttempts += 1
            return .retry(
                url: currentURL,
                userAgent: currentUserAgent,
                delaySeconds: Double(reconnectAttempts) * 1.5,
                reason: .transientReconnect(attempt: reconnectAttempts)
            )
        }

        return .fail(message: Self.classifyError(failure, isLive: isLive))
    }

    public static func alternateLiveTSURL(for url: URL) -> URL? {
        if url.pathExtension.lowercased() == "m3u8" {
            return url.deletingPathExtension().appendingPathExtension("ts")
        }
        guard var comps = URLComponents(url: url, resolvingAgainstBaseURL: false),
              var items = comps.queryItems,
              !items.isEmpty else {
            return nil
        }
        var changed = false
        for idx in items.indices {
            let name = items[idx].name.lowercased()
            let val = (items[idx].value ?? "").lowercased()
            if (name == "output" || name == "format") && (val == "hls" || val == "m3u8") {
                items[idx].value = "mpegts"
                changed = true
            }
        }
        guard changed else { return nil }
        comps.queryItems = items
        return comps.url
    }

    public static func liveFallbackURL(
        for item: MediaItem,
        failedURL: URL,
        sourceMode: SourceMode,
        host: String,
        username: String,
        password: String
    ) -> URL? {
        guard item.kind == .live else { return nil }
        if sourceMode == .xtream,
           item.sourceUrl.isEmpty,
           failedURL.pathExtension.lowercased() == "m3u8" {
            return try? XtreamClient.buildStreamURL(
                host: host,
                username: username,
                password: password,
                item: item,
                preferHLSForLive: false
            )
        }
        return alternateLiveTSURL(for: failedURL)
    }

    public static func isTransientTransportFailure(_ failure: PlaybackFailureSignal) -> Bool {
        if let status = failure.httpStatusCode, [429, 500, 502, 503, 504].contains(status) {
            return true
        }
        if failure.errorDomain == NSURLErrorDomain, let code = failure.errorCode {
            switch code {
            case NSURLErrorTimedOut,
                 NSURLErrorNetworkConnectionLost,
                 NSURLErrorCannotConnectToHost,
                 NSURLErrorNotConnectedToInternet,
                 NSURLErrorDNSLookupFailed,
                 NSURLErrorCannotFindHost:
                return true
            default:
                return false
            }
        }
        return false
    }

    public static func classifyError(_ failure: PlaybackFailureSignal, isLive: Bool = false) -> String {
        if let status = failure.httpStatusCode {
            switch status {
            case 401, 403:
                return "Yayın sunucusu erişimi reddetti (HTTP \(status)). Kullanıcı bilgilerini veya aboneliği kontrol edin."
            case 404, 410:
                return "İstenen yayın şu anda sunucuda bulunamıyor (HTTP \(status))."
            case 429:
                return "Sunucu çok fazla istek nedeniyle geçici olarak sınırlandırdı (HTTP 429)."
            case 500...599:
                return "Yayın sunucusu geçici bir hata verdi (HTTP \(status))."
            default:
                break
            }
        }

        if failure.errorDomain == NSURLErrorDomain, let code = failure.errorCode {
            switch code {
            case NSURLErrorNotConnectedToInternet, NSURLErrorDataNotAllowed, NSURLErrorInternationalRoamingOff:
                return "İnternet bağlantısı bulunamadı. Ağınızı kontrol edip tekrar deneyin."
            case NSURLErrorTimedOut:
                return "Yayın sunucusu zamanında yanıt vermedi (zaman aşımı)."
            case NSURLErrorCannotFindHost, NSURLErrorDNSLookupFailed:
                return "Yayın sunucusu adresi çözümlenemedi (DNS)."
            case NSURLErrorCannotConnectToHost, NSURLErrorNetworkConnectionLost:
                return "Yayın sunucusuyla bağlantı kurulamadı veya bağlantı kesildi."
            case NSURLErrorSecureConnectionFailed,
                 NSURLErrorServerCertificateHasBadDate,
                 NSURLErrorServerCertificateUntrusted,
                 NSURLErrorServerCertificateHasUnknownRoot,
                 NSURLErrorServerCertificateNotYetValid:
                return "Güvenli TLS/SSL bağlantısı doğrulanamadı."
            default:
                break
            }
        }

        if failure.errorDomain == "AVFoundationErrorDomain" || failure.errorDomain == "CoreMediaErrorDomain" {
            if failure.errorCode == -11828 || failure.errorCode == -11850 || isLive {
                return "Bu akış biçimi veya kodek iOS oynatıcısı tarafından doğrudan çözülemedi. Ham .ts veya uyumsuz akışlarda yerel Mavie masaüstü sunucusu üzerinden HLS olarak açmayı deneyin."
            }
            return "Video akışı çözümlenemedi. Farklı bir yayın veya yerel Mavie masaüstü sunucusu üzerinden HLS deneyin."
        }

        if failure.isStallTimeout {
            return "Yayın arabelleği zamanında dolmadı ve bağlantı zaman aşımına uğradı."
        }

        let sanitized = MavieHTTPClient.redactSensitiveURLs(in: failure.rawMessage)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if sanitized.isEmpty {
            return "Video oynatılamadı. Ham .ts veya uyumsuz akışlarda yerel Mavie masaüstü sunucusu üzerinden HLS olarak açmayı deneyin."
        }
        return "Video oynatılamadı (\(sanitized)). Ham .ts veya uyumsuz akışlarda yerel Mavie masaüstü sunucusu üzerinden HLS olarak açmayı deneyin."
    }

    public static func matchAudioOption(
        preferred: SyncTrackPreferenceData?,
        options: [PlaybackTrackCandidate]
    ) -> Int? {
        guard let preferred, !options.isEmpty else { return nil }
        if let clientAudio = preferred.clientAudio?.trimmingCharacters(in: .whitespacesAndNewlines),
           !clientAudio.isEmpty {
            if let exact = options.firstIndex(where: { $0.displayName.caseInsensitiveCompare(clientAudio) == .orderedSame }) {
                return exact
            }
            if let partial = options.firstIndex(where: { $0.displayName.localizedCaseInsensitiveContains(clientAudio) }) {
                return partial
            }
        }
        if let audioKey = preferred.audio?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
           !audioKey.isEmpty,
           audioKey != "auto" {
            if let langMatch = options.firstIndex(where: {
                guard let tag = $0.languageTag?.lowercased(), !tag.isEmpty else { return false }
                return tag == audioKey || tag.hasPrefix(audioKey + "-") || audioKey.hasPrefix(tag + "-")
            }) {
                return langMatch
            }
            if let nameMatch = options.firstIndex(where: { $0.displayName.lowercased().contains(audioKey) }) {
                return nameMatch
            }
        }
        return nil
    }

    public static func matchSubtitleOption(
        preferred: SyncTrackPreferenceData?,
        options: [PlaybackTrackCandidate]
    ) -> SubtitleMatchResult {
        guard let preferred else { return .keepDefault }
        let subKey = preferred.subtitle?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let clientSub = preferred.clientSubtitle?.trimmingCharacters(in: .whitespacesAndNewlines)
        if subKey == "off" && (clientSub == nil || clientSub?.isEmpty == true) {
            return .off
        }
        guard !options.isEmpty else { return .keepDefault }
        if let clientSub, !clientSub.isEmpty {
            if let exact = options.firstIndex(where: { $0.displayName.caseInsensitiveCompare(clientSub) == .orderedSame }) {
                return .select(index: exact)
            }
            if let partial = options.firstIndex(where: { $0.displayName.localizedCaseInsensitiveContains(clientSub) }) {
                return .select(index: partial)
            }
        }
        if let subKey, !subKey.isEmpty, subKey != "off", subKey != "auto" {
            if let langMatch = options.firstIndex(where: {
                guard let tag = $0.languageTag?.lowercased(), !tag.isEmpty else { return false }
                return tag == subKey || tag.hasPrefix(subKey + "-") || subKey.hasPrefix(tag + "-")
            }) {
                return .select(index: langMatch)
            }
            if let nameMatch = options.firstIndex(where: { $0.displayName.lowercased().contains(subKey) }) {
                return .select(index: nameMatch)
            }
        }
        return .keepDefault
    }
}
