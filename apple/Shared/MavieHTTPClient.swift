import Foundation

public enum MavieHTTPClient {
    public static let primaryUserAgent = "VLC/3.0.21 LibVLC/3.0.21"
    public static let browserUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
    public static let defaultMaxResponseBytes = 64 * 1024 * 1024

    private static let urlMatchRegex = try! NSRegularExpression(pattern: #"https?://[^\s"'<>()]+"#, options: [.caseInsensitive])
    private static let xtreamStreamPathRegex = try! NSRegularExpression(pattern: #"^(.*/)?(live|movie|series)/([^/]+)/([^/]+)/([^/]+)/?$"#, options: [.caseInsensitive])
    private static let bareSecretParamRegex = try! NSRegularExpression(pattern: #"(?i)\b(username|user|password|pass|token|auth|key|secret|api_key|apikey|access_token|sig|signature)=([^&\s"']+)"#)
    private static let sensitiveQueryNames: Set<String> = [
        "username", "user", "password", "pass", "token", "auth",
        "key", "secret", "api_key", "apikey", "access_token", "sig", "signature",
    ]

    public static let sharedSession: URLSession = makeSession(bypassProxy: false, requestTimeout: 30, resourceTimeout: 180)
    public static let loopbackSession: URLSession = makeSession(bypassProxy: true, requestTimeout: 3, resourceTimeout: 10)
    public static let lanSession: URLSession = makeSession(bypassProxy: true, requestTimeout: 15, resourceTimeout: 60)

    public static func makeSession(
        bypassProxy: Bool,
        requestTimeout: TimeInterval = 30,
        resourceTimeout: TimeInterval = 180,
        protocolClasses: [AnyClass]? = nil
    ) -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.urlCache = nil
        config.timeoutIntervalForRequest = requestTimeout
        config.timeoutIntervalForResource = resourceTimeout
        config.waitsForConnectivity = false
        config.httpAdditionalHeaders = [
            "User-Agent": primaryUserAgent,
            "Accept": "*/*",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        ]
        if bypassProxy {
            config.connectionProxyDictionary = [:]
        }
        if let protocolClasses {
            config.protocolClasses = protocolClasses
        }
        return URLSession(configuration: config)
    }

    public static func fetchData(
        for request: URLRequest,
        session: URLSession = sharedSession,
        context: String = "Sunucu",
        fallbackUserAgent: String? = browserUserAgent,
        retryDelays: [TimeInterval] = [0.4, 1.2],
        retryOnTransportFailure: Bool = true,
        throwOnHTTPError: Bool = true,
        maxBytes: Int = defaultMaxResponseBytes
    ) async throws -> (Data, HTTPURLResponse) {
        var req = request
        req.cachePolicy = .reloadIgnoringLocalCacheData
        if req.value(forHTTPHeaderField: "User-Agent")?.isEmpty ?? true {
            req.setValue(primaryUserAgent, forHTTPHeaderField: "User-Agent")
        }

        var attempt = 0
        var usedFallbackUA = false
        let effectiveMaxBytes = max(1, maxBytes)

        while true {
            try Task.checkCancellation()
            do {
                let (data, response) = try await performBoundedDataTask(
                    for: req,
                    session: session,
                    maxBytes: effectiveMaxBytes
                )
                guard let http = response as? HTTPURLResponse else {
                    throw MavieError.network("\(context) geçerli bir HTTP yanıtı döndürmedi.")
                }
                if (200...299).contains(http.statusCode) {
                    return (data, http)
                }

                if (http.statusCode == 403 || http.statusCode == 406),
                   !usedFallbackUA,
                   let fallback = fallbackUserAgent,
                   !fallback.isEmpty,
                   req.value(forHTTPHeaderField: "User-Agent") != fallback {
                    usedFallbackUA = true
                    req.setValue(fallback, forHTTPHeaderField: "User-Agent")
                    continue
                }

                if [429, 500, 502, 503, 504].contains(http.statusCode), attempt < retryDelays.count {
                    let delay = retryAfterDelay(from: http) ?? retryDelays[attempt]
                    attempt += 1
                    try await Task.sleep(nanoseconds: UInt64(max(0.05, delay) * 1_000_000_000))
                    continue
                }

                if !throwOnHTTPError {
                    return (data, http)
                }
                throw MavieError.network(classifyHTTPStatus(http.statusCode, context: context))
            } catch is CancellationError {
                throw CancellationError()
            } catch let urlErr as URLError where urlErr.code == .cancelled {
                throw urlErr
            } catch let mavieErr as MavieError {
                throw mavieErr
            } catch {
                if retryOnTransportFailure,
                   let urlErr = error as? URLError,
                   isTransientURLError(urlErr.code),
                   attempt < retryDelays.count {
                    let delay = retryDelays[attempt]
                    attempt += 1
                    try await Task.sleep(nanoseconds: UInt64(max(0.05, delay) * 1_000_000_000))
                    continue
                }
                throw MavieError.network(classifyURLError(error, context: context))
            }
        }
    }

    public static func redactSensitiveURLs(in text: String) -> String {
        guard !text.isEmpty else { return text }
        var output = text
        let matches = urlMatchRegex.matches(in: output, range: NSRange(output.startIndex..., in: output))
        for match in matches.reversed() {
            guard let range = Range(match.range, in: output) else { continue }
            let rawURL = String(output[range])
            let redacted = redactURLString(rawURL)
            output.replaceSubrange(range, with: redacted)
        }
        let paramMatches = bareSecretParamRegex.matches(in: output, range: NSRange(output.startIndex..., in: output))
        for match in paramMatches.reversed() {
            guard match.numberOfRanges >= 3,
                  let fullRange = Range(match.range, in: output),
                  let keyRange = Range(match.range(at: 1), in: output) else { continue }
            let keyName = String(output[keyRange])
            output.replaceSubrange(fullRange, with: "\(keyName)=***")
        }
        return output
    }

    private static func redactURLString(_ raw: String) -> String {
        guard var comps = URLComponents(string: raw) else {
            return raw
        }
        if comps.user != nil { comps.user = "***" }
        if comps.password != nil { comps.password = "***" }
        if var items = comps.queryItems, !items.isEmpty {
            var modified = false
            for idx in items.indices {
                if sensitiveQueryNames.contains(items[idx].name.lowercased()) {
                    items[idx].value = "***"
                    modified = true
                }
            }
            if modified { comps.queryItems = items }
        }
        let path = comps.path
        let nsPath = NSRange(path.startIndex..., in: path)
        if let m = xtreamStreamPathRegex.firstMatch(in: path, range: nsPath),
           m.numberOfRanges >= 6,
           let kindRange = Range(m.range(at: 2), in: path),
           let tailRange = Range(m.range(at: 5), in: path) {
            let prefix = m.range(at: 1).location != NSNotFound ? (Range(m.range(at: 1), in: path).map { String(path[$0]) } ?? "") : ""
            let leading = prefix.isEmpty ? "/" : prefix
            comps.path = "\(leading)\(path[kindRange])/***/***/\(path[tailRange])"
        }
        return comps.string ?? raw
    }

    public static func classifyURLError(_ error: Error, context: String = "Sunucu") -> String {
        if let mavie = error as? MavieError, let desc = mavie.errorDescription {
            return redactSensitiveURLs(in: desc)
        }
        guard let urlErr = error as? URLError else {
            return "\(context) ile bağlantı kurulamadı: \(redactSensitiveURLs(in: error.localizedDescription))"
        }
        switch urlErr.code {
        case .cancelled:
            return "\(context) isteği iptal edildi."
        case .notConnectedToInternet, .dataNotAllowed, .internationalRoamingOff:
            return "İnternet bağlantısı bulunamadı. Ağınızı kontrol edip tekrar deneyin."
        case .timedOut:
            return "\(context) zamanında yanıt vermedi (zaman aşımı). Tekrar deneyin."
        case .cannotFindHost, .dnsLookupFailed:
            return "\(context) adresi çözümlenemedi (DNS). Adresi kontrol edin."
        case .cannotConnectToHost, .networkConnectionLost:
            return "\(context) ile bağlantı kurulamadı veya bağlantı kesildi."
        case .appTransportSecurityRequiresSecureConnection:
            return "\(context) için güvenli HTTPS bağlantısı gerekiyor (ATS)."
        case .secureConnectionFailed, .serverCertificateHasBadDate, .serverCertificateUntrusted,
             .serverCertificateHasUnknownRoot, .serverCertificateNotYetValid, .clientCertificateRejected:
            return "\(context) için güvenli TLS/SSL bağlantısı doğrulanamadı. HTTP adresini veya sunucu sertifikasını kontrol edin."
        case .httpTooManyRedirects, .redirectToNonExistentLocation:
            return "\(context) çok fazla yönlendirme döndürdü."
        case .userAuthenticationRequired:
            return "\(context) kimlik doğrulaması gerektiriyor."
        case .badServerResponse, .cannotParseResponse, .zeroByteResource, .resourceUnavailable, .fileDoesNotExist:
            return "\(context) geçersiz veya boş bir yanıt döndürdü."
        case .badURL, .unsupportedURL:
            return "Geçersiz sunucu adresi."
        default:
            return "\(context) bağlantısı başarısız (hata kodu: \(urlErr.errorCode))."
        }
    }

    private final class BoundedTaskDelegate: NSObject, URLSessionDataDelegate, @unchecked Sendable {
        private let maxBytes: Int
        private let lock = NSLock()
        private var continuation: CheckedContinuation<(Data, URLResponse), Error>?
        private var task: URLSessionDataTask?
        private var response: URLResponse?
        private var buffer = Data()
        private var finished = false
        private var cancelledExternally = false

        init(maxBytes: Int, continuation: CheckedContinuation<(Data, URLResponse), Error>) {
            self.maxBytes = maxBytes
            self.continuation = continuation
        }

        func attach(task: URLSessionDataTask) {
            lock.lock()
            self.task = task
            let shouldCancel = cancelledExternally
            lock.unlock()
            if shouldCancel {
                task.cancel()
            } else {
                task.resume()
            }
        }

        func cancel() {
            lock.lock()
            cancelledExternally = true
            let t = task
            let cont = takeContinuationLocked()
            lock.unlock()
            t?.cancel()
            cont?.resume(throwing: CancellationError())
        }

        private func takeContinuationLocked() -> CheckedContinuation<(Data, URLResponse), Error>? {
            guard !finished else { return nil }
            finished = true
            task = nil
            let cont = continuation
            continuation = nil
            return cont
        }

        func urlSession(
            _ session: URLSession,
            dataTask: URLSessionDataTask,
            didReceive response: URLResponse,
            completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
        ) {
            if response.expectedContentLength > Int64(maxBytes) {
                lock.lock()
                let cont = takeContinuationLocked()
                lock.unlock()
                completionHandler(.cancel)
                cont?.resume(throwing: MavieError.validation("Sunucu yanıtı izin verilen boyut sınırını aşıyor."))
                return
            }
            lock.lock()
            self.response = response
            let alreadyFinished = finished
            lock.unlock()
            completionHandler(alreadyFinished ? .cancel : .allow)
        }

        func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
            lock.lock()
            guard !finished else {
                lock.unlock()
                return
            }
            if buffer.count + data.count > maxBytes {
                let cont = takeContinuationLocked()
                lock.unlock()
                dataTask.cancel()
                cont?.resume(throwing: MavieError.validation("Sunucu yanıtı izin verilen boyut sınırını aşıyor."))
                return
            }
            buffer.append(data)
            lock.unlock()
        }

        func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
            lock.lock()
            let cont = takeContinuationLocked()
            let capturedResponse = response
            let capturedData = buffer
            let wasCancelled = cancelledExternally
            lock.unlock()

            guard let cont else { return }
            if wasCancelled {
                cont.resume(throwing: CancellationError())
                return
            }
            if let error {
                cont.resume(throwing: error)
                return
            }
            guard let capturedResponse else {
                cont.resume(throwing: MavieError.network("Sunucu yanıtı alınamadı."))
                return
            }
            cont.resume(returning: (capturedData, capturedResponse))
        }
    }

    private static func performBoundedDataTask(
        for request: URLRequest,
        session: URLSession,
        maxBytes: Int
    ) async throws -> (Data, URLResponse) {
        try Task.checkCancellation()
        let box = DelegateBox()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                let delegate = BoundedTaskDelegate(maxBytes: maxBytes, continuation: continuation)
                box.set(delegate)
                let task = session.dataTask(with: request)
                task.delegate = delegate
                delegate.attach(task: task)
            }
        } onCancel: {
            box.cancel()
        }
    }

    private final class DelegateBox: @unchecked Sendable {
        private let lock = NSLock()
        private var delegate: BoundedTaskDelegate?
        private var pendingCancel = false

        func set(_ delegate: BoundedTaskDelegate) {
            lock.lock()
            self.delegate = delegate
            let shouldCancel = pendingCancel
            lock.unlock()
            if shouldCancel {
                delegate.cancel()
            }
        }

        func cancel() {
            lock.lock()
            pendingCancel = true
            let d = delegate
            lock.unlock()
            d?.cancel()
        }
    }

    public static func classifyHTTPStatus(_ statusCode: Int, context: String = "Sunucu") -> String {
        switch statusCode {
        case 401, 403:
            return "\(context) erişimi reddetti (HTTP \(statusCode)). Kullanıcı bilgilerini veya erişim iznini kontrol edin."
        case 404:
            return "\(context) üzerinde istenen kaynak bulunamadı (HTTP 404)."
        case 429:
            return "\(context) çok fazla istek nedeniyle geçici olarak sınırladı (HTTP 429). Biraz sonra tekrar deneyin."
        case 500...599:
            return "\(context) geçici bir sunucu hatası verdi (HTTP \(statusCode))."
        default:
            return "\(context) beklenmeyen bir yanıt döndürdü (HTTP \(statusCode))."
        }
    }

    public static func decodeText(_ data: Data, response: URLResponse? = nil) -> String {
        if let charset = response?.textEncodingName?.trimmingCharacters(in: .whitespacesAndNewlines),
           !charset.isEmpty {
            let cfEncoding = CFStringConvertIANACharSetNameToEncoding(charset as CFString)
            if cfEncoding != kCFStringEncodingInvalidId {
                let nsEncoding = CFStringConvertEncodingToNSStringEncoding(cfEncoding)
                if let decoded = String(data: data, encoding: String.Encoding(rawValue: nsEncoding)) {
                    return decoded
                }
            }
        }
        if let utf8 = String(data: data, encoding: .utf8) {
            return utf8
        }
        if let latin1 = String(data: data, encoding: .isoLatin1) {
            return latin1
        }
        return String(decoding: data, as: UTF8.self)
    }

    private static func retryAfterDelay(from response: HTTPURLResponse) -> TimeInterval? {
        guard response.statusCode == 429 || response.statusCode == 503,
              let raw = response.value(forHTTPHeaderField: "Retry-After")?.trimmingCharacters(in: .whitespacesAndNewlines),
              let seconds = Double(raw),
              seconds.isFinite else {
            return nil
        }
        return min(5.0, max(0.2, seconds))
    }

    private static func isTransientURLError(_ code: URLError.Code) -> Bool {
        switch code {
        case .timedOut,
             .networkConnectionLost,
             .cannotConnectToHost,
             .cannotFindHost,
             .dnsLookupFailed,
             .notConnectedToInternet:
            return true
        default:
            return false
        }
    }
}
