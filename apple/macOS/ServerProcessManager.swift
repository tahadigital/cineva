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
    private var terminatingProcess: Process?
    private var logHandle: FileHandle?
    private var pollTask: Task<Void, Never>?
    private var startTask: Task<Void, Never>?
    private var terminationTask: Task<Void, Never>?
    private var generation: UInt64 = 0
    private var shuttingDown = false
    private var startupRetryCount = 0
    private var triedPorts: Set<Int> = []

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
        startTask?.cancel()
        pollTask?.cancel()
        pollTask = nil
        generation &+= 1
        let expectedGeneration = generation
        shuttingDown = false
        startupRetryCount = 0
        triedPorts = []
        status = .starting
        healthDetails = "Yerel medya motoru başlatılıyor..."
        startTask = Task { [weak self] in
            await self?.startInternal(excluding: [], expectedGeneration: expectedGeneration)
        }
    }

    private func startInternal(excluding: Set<Int>, expectedGeneration: UInt64) async {
        await terminationTask?.value
        guard !Task.isCancelled, !shuttingDown, generation == expectedGeneration else { return }

        let oldChild = process
        let oldHandle = logHandle
        process = nil
        logHandle = nil
        if oldChild != nil || oldHandle != nil {
            await terminateDetachedProcess(oldChild, logHandle: oldHandle)
        }
        guard !Task.isCancelled, !shuttingDown, generation == expectedGeneration else { return }

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

            let selectedPort = Self.choosePort(excluding: excluding)
            triedPorts.insert(selectedPort)
            port = selectedPort
            lanURLs = Self.discoverLanURLs(port: selectedPort)

            let launch = try resolveLaunchCommand(port: selectedPort)
            executableDescription = launch.description

            guard !Task.isCancelled, !shuttingDown, generation == expectedGeneration else {
                try? handle.close()
                return
            }

            logHandle = handle

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

            let launchGen = expectedGeneration
            child.terminationHandler = { [weak self] proc in
                let exitCode = proc.terminationStatus
                Task { @MainActor [weak self] in
                    guard let self, self.generation == launchGen, !self.shuttingDown else { return }
                    if case .ready = self.status {
                        self.status = .failed("Yerel medya sunucusu beklenmedik şekilde durdu (kod \(exitCode)).")
                        self.healthDetails = "Durdu (kod \(exitCode))"
                    }
                }
            }

            try child.run()
            process = child
            beginHealthPolling(port: selectedPort, generation: expectedGeneration)
        } catch {
            if process == nil {
                try? logHandle?.close()
                logHandle = nil
            }
            guard !Task.isCancelled, !shuttingDown, generation == expectedGeneration else { return }
            let msg = "Yerel medya sunucusu başlatılamadı: \(error.localizedDescription)"
            status = .failed(msg)
            healthDetails = msg
        }
    }

    public func restart() {
        start()
    }

    public func stopAsync() async {
        shuttingDown = true
        generation &+= 1
        startTask?.cancel()
        startTask = nil
        pollTask?.cancel()
        pollTask = nil

        if let existingTask = terminationTask {
            await existingTask.value
        }

        let child = process
        let handle = logHandle
        process = nil
        logHandle = nil

        let task: Task<Void, Never> = Task { @MainActor [weak self] in
            guard let self else {
                try? handle?.close()
                return
            }
            await self.terminateDetachedProcess(child, logHandle: handle)
        }
        terminationTask = task
        await task.value
        terminationTask = nil
    }

    public func stopSynchronouslyForTermination() {
        shuttingDown = true
        generation &+= 1
        startTask?.cancel()
        startTask = nil
        pollTask?.cancel()
        pollTask = nil
        terminationTask?.cancel()
        terminationTask = nil

        var children: [Process] = []
        if let child = process {
            children.append(child)
        }
        if let terminating = terminatingProcess, !children.contains(where: { $0 === terminating }) {
            children.append(terminating)
        }
        process = nil
        terminatingProcess = nil

        for child in children where child.isRunning {
            child.terminate()
            let deadline = Date().addingTimeInterval(2.5)
            while child.isRunning && Date() < deadline {
                Thread.sleep(forTimeInterval: 0.05)
            }
            if child.isRunning {
                kill(child.processIdentifier, SIGKILL)
            }
        }

        try? logHandle?.close()
        logHandle = nil
    }

    private func terminateDetachedProcess(_ child: Process?, logHandle: FileHandle?) async {
        if let child {
            terminatingProcess = child
            defer {
                if terminatingProcess === child {
                    terminatingProcess = nil
                }
            }
            if child.isRunning {
                child.terminate()
                for _ in 0..<70 {
                    if !child.isRunning { break }
                    try? await Task.sleep(nanoseconds: 50_000_000)
                }
                if child.isRunning {
                    kill(child.processIdentifier, SIGKILL)
                    for _ in 0..<6 {
                        if !child.isRunning { break }
                        try? await Task.sleep(nanoseconds: 50_000_000)
                    }
                }
            }
        }
        try? logHandle?.close()
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
                    req.cachePolicy = .reloadIgnoringLocalCacheData
                    req.timeoutInterval = 3
                    let (_, resp) = try await MavieHTTPClient.loopbackSession.data(for: req)
                    let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                    await stopAsync()
                    if code == 200 {
                        print("Mavie macOS smoke test OK on port \(port)")
                        return 0
                    } else {
                        fputs("Smoke test failed: GET / returned HTTP \(code)\n", stderr)
                        return 1
                    }
                } catch {
                    fputs("Smoke test failed requesting /: \(error.localizedDescription)\n", stderr)
                    await stopAsync()
                    return 1
                }
            }
            if case .failed(let msg) = status {
                fputs("Smoke test failed: \(msg)\n", stderr)
                await stopAsync()
                return 1
            }
            try? await Task.sleep(nanoseconds: 150_000_000)
        }
        fputs("Smoke test timed out waiting for /api/health\n", stderr)
        await stopAsync()
        return 1
    }

    // MARK: - Private

    private func beginHealthPolling(port: Int, generation expectedGeneration: UInt64) {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            guard let self else { return }
            let healthURL = URL(string: "http://127.0.0.1:\(port)/api/health")!
            for attempt in 1...120 {
                if Task.isCancelled || self.shuttingDown || self.generation != expectedGeneration { return }
                if let child = self.process, !child.isRunning {
                    let forcedPort = ProcessInfo.processInfo.environment["MAVIE_PORT"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                    if forcedPort.isEmpty && self.startupRetryCount < 2 {
                        self.startupRetryCount += 1
                        self.generation &+= 1
                        let nextGen = self.generation
                        await self.startInternal(excluding: self.triedPorts, expectedGeneration: nextGen)
                        return
                    }
                    let tail = self.readLastLogError()
                    let detail = tail.isEmpty ? "Günlüğü kontrol edin." : tail
                    self.status = .failed("Mavie sunucusu başlatılırken kapandı (çıkış kodu \(child.terminationStatus)). \(detail)")
                    self.healthDetails = "Çıkış kodu \(child.terminationStatus)"
                    return
                }
                if await Self.probeHealth(url: healthURL) {
                    guard !Task.isCancelled, !self.shuttingDown, self.generation == expectedGeneration else { return }
                    self.status = .ready
                    self.healthDetails = "Çalışıyor · 127.0.0.1:\(port)"
                    return
                }
                guard !Task.isCancelled, !self.shuttingDown, self.generation == expectedGeneration else { return }
                if attempt % 8 == 0 {
                    self.healthDetails = "Hazırlanıyor (\(attempt / 4) sn)..."
                }
                try? await Task.sleep(nanoseconds: 250_000_000)
            }
            guard !Task.isCancelled, !self.shuttingDown, self.generation == expectedGeneration else { return }
            self.status = .failed("Mavie sunucusu zamanında yanıt vermedi. Başka bir örneğin portu kullanmadığından emin olun.")
            self.healthDetails = "Zaman aşımı"
        }
    }

    private static func probeHealth(url: URL) async -> Bool {
        var req = URLRequest(url: url)
        req.cachePolicy = .reloadIgnoringLocalCacheData
        req.timeoutInterval = 1.2
        do {
            let (data, resp) = try await MavieHTTPClient.loopbackSession.data(for: req)
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

    private func readLastLogError() -> String {
        guard let text = try? String(contentsOf: logFile, encoding: .utf8) else { return "" }
        let lines = text.split(whereSeparator: \.isNewline).map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        if let errLine = lines.last(where: { $0.contains("Error:") || $0.contains("OSError:") || $0.contains("Exception") }) {
            return String(errLine.prefix(160))
        }
        return ""
    }

    private static func choosePort(excluding: Set<Int> = []) -> Int {
        if excluding.isEmpty,
           let raw = ProcessInfo.processInfo.environment["MAVIE_PORT"],
           let parsed = Int(raw.trimmingCharacters(in: .whitespaces)),
           (1024...65535).contains(parsed) {
            return parsed
        }
        for candidate in 8844...8864 where !excluding.contains(candidate) {
            if canBindPort(candidate) {
                return candidate
            }
        }
        return allocateEphemeralPort() ?? 8845
    }

    private static func isLoopbackPortListening(_ port: Int) -> Bool {
        let fd = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { Darwin.close(fd) }
        let flags = fcntl(fd, F_GETFL, 0)
        if flags >= 0 {
            _ = fcntl(fd, F_SETFL, flags | O_NONBLOCK)
        }
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = UInt16(port).bigEndian
        addr.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))
        let res = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        if res == 0 { return true }
        if errno != EINPROGRESS { return false }
        var pfd = pollfd(fd: fd, events: Int16(POLLOUT), revents: 0)
        let pr = Darwin.poll(&pfd, 1, 60)
        guard pr > 0 else { return false }
        var soErr: Int32 = 0
        var len = socklen_t(MemoryLayout<Int32>.size)
        if getsockopt(fd, SOL_SOCKET, SO_ERROR, &soErr, &len) == 0 {
            return soErr == 0
        }
        return false
    }

    private static func canBindPort(_ port: Int) -> Bool {
        // 1. Reject immediately if anything is already listening on loopback or wildcard.
        if isLoopbackPortListening(port) {
            return false
        }
        // 2. Test exact wildcard bind (0.0.0.0) + listen WITHOUT SO_REUSEADDR,
        // matching how mavie-server binds --host 0.0.0.0.
        let fd = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { Darwin.close(fd) }
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = UInt16(port).bigEndian
        addr.sin_addr = in_addr(s_addr: INADDR_ANY.bigEndian)
        let bindRes = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bindRes == 0 else { return false }
        return Darwin.listen(fd, 1) == 0
    }

    private static func allocateEphemeralPort() -> Int? {
        let fd = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return nil }
        defer { Darwin.close(fd) }
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = 0
        addr.sin_addr = in_addr(s_addr: INADDR_ANY.bigEndian)
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
