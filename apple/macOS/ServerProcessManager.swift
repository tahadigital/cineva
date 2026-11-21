import AppKit
import Darwin
import Foundation

public enum ServerStatus: Equatable {
    case idle
    case starting
    case ready
    case failed(String)

    public var isReady: Bool {
        if case .ready = self { return true }
        return false
    }
}

@MainActor
public final class ServerProcessManager: ObservableObject {
    @Published public private(set) var status: ServerStatus = .idle
    @Published public private(set) var port: Int = 8844
    @Published public private(set) var dataDir: URL
    @Published public private(set) var logFile: URL
    @Published public private(set) var executableDescription: String = ""
    @Published public private(set) var healthDetails: String = "Başlatılmadı"
    @Published public private(set) var lanURLs: [String] = []

    private var process: Process?
    private var logHandle: FileHandle?
    private var pollTask: Task<Void, Never>?
    private var shuttingDown = false

    public var baseURL: URL {
        URL(string: "http://127.0.0.1:\(port)/")!
    }

    public init() {
        let dir = Self.resolveDataDirectory()
        self.dataDir = dir
        self.logFile = dir.appendingPathComponent("server.log")
        self.lanURLs = Self.discoverLanURLs(port: 8844)
    }

    public static func resolveDataDirectory() -> URL {
        let env = ProcessInfo.processInfo.environment
        if let custom = env["MAVIE_DATA_DIR"] ?? env["CINEVA_DATA_DIR"],
           !custom.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return URL(fileURLWithPath: custom, isDirectory: true)
        }
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return appSupport
            .appendingPathComponent("Mavie", isDirectory: true)
            .appendingPathComponent("data", isDirectory: true)
    }

    public func start() {
        stop()
        shuttingDown = false
        status = .starting
        healthDetails = "Yerel medya motoru başlatılıyor..."

        do {
            try FileManager.default.createDirectory(
                at: dataDir,
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700]
            )
            rotateLogIfNeeded()
            if !FileManager.default.fileExists(atPath: logFile.path) {
                FileManager.default.createFile(
                    atPath: logFile.path,
                    contents: nil,
                    attributes: [.posixPermissions: 0o600]
                )
            }
            let handle = try FileHandle(forWritingTo: logFile)
            try handle.seekToEnd()
            logHandle = handle

            let selectedPort = Self.choosePort()
            port = selectedPort
            lanURLs = Self.discoverLanURLs(port: selectedPort)

            let launch = try resolveLaunchCommand(port: selectedPort)
            executableDescription = launch.description

            let child = Process()
            child.executableURL = launch.executableURL
            child.arguments = launch.arguments
            child.currentDirectoryURL = launch.workingDirectory
            child.standardInput = FileHandle.nullDevice
            child.standardOutput = handle
            child.standardError = handle

            var env = ProcessInfo.processInfo.environment
            env["MAVIE_DATA_DIR"] = dataDir.path
            env["PYTHONUNBUFFERED"] = "1"
            child.environment = env

            child.terminationHandler = { [weak self] proc in
                Task { @MainActor [weak self] in
                    guard let self, !self.shuttingDown else { return }
                    if case .ready = self.status {
                        self.status = .failed("Yerel medya sunucusu beklenmedik şekilde durdu (kod \(proc.terminationStatus)).")
                        self.healthDetails = "Durdu (kod \(proc.terminationStatus))"
                    }
                }
            }

            process = child
            try child.run()
            beginHealthPolling(port: selectedPort)
        } catch {
            let msg = "Yerel medya sunucusu başlatılamadı: \(error.localizedDescription)"
            status = .failed(msg)
            healthDetails = msg
        }
    }

    public func restart() {
        start()
    }

    public func stop() {
        shuttingDown = true
        pollTask?.cancel()
        pollTask = nil

        if let child = process {
            if child.isRunning {
                child.terminate()
                let deadline = Date().addingTimeInterval(3.5)
                while child.isRunning && Date() < deadline {
                    Thread.sleep(forTimeInterval: 0.05)
                }
                if child.isRunning {
                    kill(child.processIdentifier, SIGKILL)
                }
            }
            process = nil
        }

        try? logHandle?.close()
        logHandle = nil
    }

    public func openDataDirectory() {
        try? FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true)
        NSWorkspace.shared.open(dataDir)
    }

    public func openLogFile() {
        if FileManager.default.fileExists(atPath: logFile.path) {
            NSWorkspace.shared.open(logFile)
        } else {
            openDataDirectory()
        }
    }

    public func runHeadlessSmokeTest() async -> Int32 {
        start()
        let deadline = Date().addingTimeInterval(25)
        while Date() < deadline {
            if case .ready = status {
                do {
                    var req = URLRequest(url: baseURL)
                    req.timeoutInterval = 3
                    let (_, resp) = try await URLSession.shared.data(for: req)
                    let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                    stop()
                    if code == 200 {
                        print("Mavie macOS smoke test OK on port \(port)")
                        return 0
                    } else {
                        fputs("Smoke test failed: GET / returned HTTP \(code)\n", stderr)
                        return 1
                    }
                } catch {
                    fputs("Smoke test failed requesting /: \(error.localizedDescription)\n", stderr)
                    stop()
                    return 1
                }
            }
            if case .failed(let msg) = status {
                fputs("Smoke test failed: \(msg)\n", stderr)
                stop()
                return 1
            }
            try? await Task.sleep(nanoseconds: 150_000_000)
        }
        fputs("Smoke test timed out waiting for /api/health\n", stderr)
        stop()
        return 1
    }

    // MARK: - Private

    private func beginHealthPolling(port: Int) {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            guard let self else { return }
            let healthURL = URL(string: "http://127.0.0.1:\(port)/api/health")!
            for attempt in 1...120 {
                if Task.isCancelled || self.shuttingDown { return }
                if let child = self.process, !child.isRunning {
                    self.status = .failed("Mavie sunucusu başlatılırken kapandı (çıkış kodu \(child.terminationStatus)). Günlüğü kontrol edin.")
                    self.healthDetails = "Çıkış kodu \(child.terminationStatus)"
                    return
                }
                if await Self.probeHealth(url: healthURL) {
                    self.status = .ready
                    self.healthDetails = "Çalışıyor · 127.0.0.1:\(port)"
                    return
                }
                if attempt % 8 == 0 {
                    self.healthDetails = "Hazırlanıyor (\(attempt / 4) sn)..."
                }
                try? await Task.sleep(nanoseconds: 250_000_000)
            }
            self.status = .failed("Mavie sunucusu zamanında yanıt vermedi. Başka bir örneğin portu kullanmadığından emin olun.")
            self.healthDetails = "Zaman aşımı"
        }
    }

    private static func probeHealth(url: URL) async -> Bool {
        var req = URLRequest(url: url)
        req.timeoutInterval = 1.2
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse, http.statusCode == 200 else { return false }
            guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
            let app = obj["app"] as? String
            let ok = obj["ok"] as? Bool
            return app == "mavie" && ok == true
        } catch {
            return false
        }
    }

    private struct LaunchCommand {
        var executableURL: URL
        var arguments: [String]
        var workingDirectory: URL
        var description: String
    }

    private func resolveLaunchCommand(port: Int) throws -> LaunchCommand {
        let fm = FileManager.default
        let pidArg = String(ProcessInfo.processInfo.processIdentifier)
        let serverArgs = ["--host", "0.0.0.0", "--port", String(port), "--parent-pid", pidArg]

        // 1. Embedded PyInstaller --onedir binary inside Mavie.app/Contents/Resources/mavie-server/mavie-server
        if let resourceURL = Bundle.main.resourceURL {
            let embeddedDir = resourceURL.appendingPathComponent("mavie-server", isDirectory: true)
            let embeddedExe = embeddedDir.appendingPathComponent("mavie-server")
            if fm.isExecutableFile(atPath: embeddedExe.path) {
                return LaunchCommand(
                    executableURL: embeddedExe,
                    arguments: serverArgs,
                    workingDirectory: embeddedDir,
                    description: "Gömülü Motor (mavie-server)"
                )
            }

            let bundledScript = resourceURL.appendingPathComponent("server.py")
            if fm.fileExists(atPath: bundledScript.path),
               let py = Self.findPython(near: resourceURL) {
                return LaunchCommand(
                    executableURL: py,
                    arguments: [bundledScript.path] + serverArgs,
                    workingDirectory: resourceURL,
                    description: "Python (\(py.lastPathComponent))"
                )
            }
        }

        // 2. Development checkout fallback
        var searchRoots: [URL] = []
        var cursor = Bundle.main.bundleURL
        for _ in 0..<6 {
            searchRoots.append(cursor)
            cursor = cursor.deletingLastPathComponent()
        }
        searchRoots.append(URL(fileURLWithPath: fm.currentDirectoryPath, isDirectory: true))

        for root in searchRoots {
            let script = root.appendingPathComponent("server.py")
            if fm.fileExists(atPath: script.path), let py = Self.findPython(near: root) {
                return LaunchCommand(
                    executableURL: py,
                    arguments: [script.path] + serverArgs,
                    workingDirectory: root,
                    description: "Geliştirme (\(py.lastPathComponent))"
                )
            }
        }

        throw MavieError.validation("Gömülü mavie-server veya server.py bulunamadı. Uygulama paketini yeniden oluşturun.")
    }

    private static func findPython(near root: URL) -> URL? {
        let fm = FileManager.default
        let candidates = [
            root.appendingPathComponent(".venv/bin/python"),
            root.appendingPathComponent(".venv/bin/python3"),
            URL(fileURLWithPath: "/opt/homebrew/bin/python3"),
            URL(fileURLWithPath: "/usr/local/bin/python3"),
            URL(fileURLWithPath: "/usr/bin/python3"),
        ]
        return candidates.first { fm.isExecutableFile(atPath: $0.path) }
    }

    private func rotateLogIfNeeded() {
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: logFile.path),
              let size = attrs[.size] as? UInt64,
              size > 2 * 1024 * 1024 else {
            return
        }
        try? Data().write(to: logFile)
    }

    private static func choosePort() -> Int {
        if let raw = ProcessInfo.processInfo.environment["MAVIE_PORT"],
           let parsed = Int(raw.trimmingCharacters(in: .whitespaces)),
           (1024...65535).contains(parsed) {
            return parsed
        }
        if canBindPort(8844) {
            return 8844
        }
        return allocateEphemeralPort() ?? 8844
    }

    private static func canBindPort(_ port: Int) -> Bool {
        let fd = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { Darwin.close(fd) }
        var yes: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = UInt16(port).bigEndian
        addr.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))
        let res = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        return res == 0
    }

    private static func allocateEphemeralPort() -> Int? {
        let fd = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return nil }
        defer { Darwin.close(fd) }
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = 0
        addr.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))
        let bindRes = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bindRes == 0 else { return nil }
        var assigned = sockaddr_in()
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        let nameRes = withUnsafeMutablePointer(to: &assigned) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.getsockname(fd, $0, &len)
            }
        }
        guard nameRes == 0 else { return nil }
        return Int(UInt16(bigEndian: assigned.sin_port))
    }

    public static func discoverLanURLs(port: Int) -> [String] {
        var urls: [String] = []
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0, let first = ifaddr else {
            return ["http://127.0.0.1:\(port)"]
        }
        defer { freeifaddrs(ifaddr) }
        var ptr: UnsafeMutablePointer<ifaddrs>? = first
        while let current = ptr {
            let flags = Int32(current.pointee.ifa_flags)
            let isUp = (flags & IFF_UP) != 0 && (flags & IFF_LOOPBACK) == 0
            if isUp, let sa = current.pointee.ifa_addr, sa.pointee.sa_family == UInt8(AF_INET) {
                var hostBuf = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                if getnameinfo(sa, socklen_t(sa.pointee.sa_len), &hostBuf, socklen_t(hostBuf.count), nil, 0, NI_NUMERICHOST) == 0 {
                    let ip = String(cString: hostBuf)
                    if !ip.hasPrefix("169.254.") {
                        urls.append("http://\(ip):\(port)")
                    }
                }
            }
            ptr = current.pointee.ifa_next
        }
        if urls.isEmpty {
            urls.append("http://127.0.0.1:\(port)")
        }
        return urls
    }
}
