import Foundation

public enum MavieHTTPClient {
    public static let primaryUserAgent = "VLC/3.0.21 LibVLC/3.0.21"
    public static let browserUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"

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
        throwOnHTTPError: Bool = true
    ) async throws -> (Data, HTTPURLResponse) {
        var req = request
        req.cachePolicy = .reloadIgnoringLocalCacheData
        if req.value(forHTTPHeaderField: "User-Agent")?.isEmpty ?? true {
            req.setValue(primaryUserAgent, forHTTPHeaderField: "User-Agent")
        }

        var attempt = 0
        var usedFallbackUA = false

        while true {
            try Task.checkCancellation()
            do {
                let (data, response) = try await session.data(for: req)
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

    public static func classifyURLError(_ error: Error, context: String = "Sunucu") -> String {
        if let mavie = error as? MavieError, let desc = mavie.errorDescription {
            return desc
        }
        guard let urlErr = error as? URLError else {
            return "\(context) ile bağlantı kurulamadı: \(error.localizedDescription)"
        }
        switch urlErr.code {
        case .notConnectedToInternet, .dataNotAllowed, .internationalRoamingOff:
            return "İnternet bağlantısı bulunamadı. Ağınızı kontrol edip tekrar deneyin."
        case .timedOut:
            return "\(context) zamanında yanıt vermedi (zaman aşımı). Tekrar deneyin."
        case .cannotFindHost, .dnsLookupFailed:
            return "\(context) adresi çözümlenemedi (DNS). Adresi kontrol edin."
        case .cannotConnectToHost, .networkConnectionLost:
            return "\(context) ile bağlantı kurulamadı veya bağlantı kesildi."
        case .secureConnectionFailed, .serverCertificateHasBadDate, .serverCertificateUntrusted,
             .serverCertificateHasUnknownRoot, .serverCertificateNotYetValid, .clientCertificateRejected:
            return "\(context) için güvenli TLS/SSL bağlantısı doğrulanamadı. HTTP adresini veya sunucu sertifikasını kontrol edin."
        case .badServerResponse, .cannotParseResponse, .zeroByteResource:
            return "\(context) geçersiz veya boş bir yanıt döndürdü."
        case .badURL, .unsupportedURL:
            return "Geçersiz sunucu adresi."
        default:
            return "\(context) bağlantısı başarısız: \(urlErr.localizedDescription)"
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
