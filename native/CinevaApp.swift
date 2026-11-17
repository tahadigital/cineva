import Cocoa
import WebKit
import UniformTypeIdentifiers

// The window owns the local service. Closing the last window quits the app,
// terminates the service, and disconnects all paired devices.
final class CinevaDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var service: Process?
    var log: FileHandle?
    var poll: Timer?
    var checks = 0
    var shuttingDown = false
    let root = Bundle.main.bundleURL.deletingLastPathComponent()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.appearance = NSAppearance(named: .darkAqua)
        buildMenu()
        let configuration = WKWebViewConfiguration()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        configuration.preferences.isElementFullscreenEnabled = true
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.underPageBackgroundColor = .black
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1200, height: 820), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Cineva"
        window.backgroundColor = .black
        window.titlebarAppearsTransparent = true
        window.minSize = NSSize(width: 420, height: 600)
        window.delegate = self
        window.isReleasedWhenClosed = false
        window.contentView = webView
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        webView.loadHTMLString("<html lang='tr' style='background:#0e1015;color-scheme:dark'><title>Cineva</title></html>", baseURL: nil)
        launchService()
    }

    func buildMenu() {
        let menu = NSMenu()
        let app = NSMenuItem(); menu.addItem(app)
        let appMenu = NSMenu(); app.submenu = appMenu
        appMenu.addItem(withTitle: "Cineva’dan Çık", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let file = NSMenuItem(); menu.addItem(file); file.submenu = NSMenu(title: "Dosya")
        file.submenu?.addItem(withTitle: "Pencereyi Kapat", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        let edit = NSMenuItem(); menu.addItem(edit); edit.submenu = NSMenu(title: "Düzen")
        edit.submenu?.addItem(withTitle: "Geri Al", action: Selector(("undo:")), keyEquivalent: "z")
        edit.submenu?.addItem(withTitle: "Kes", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.submenu?.addItem(withTitle: "Kopyala", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.submenu?.addItem(withTitle: "Yapıştır", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.submenu?.addItem(withTitle: "Tümünü Seç", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        let view = NSMenuItem(); menu.addItem(view); view.submenu = NSMenu(title: "Görünüm")
        let reload = NSMenuItem(title: "Yenile", action: #selector(reloadPage), keyEquivalent: "r"); reload.target = self
        view.submenu?.addItem(reload)
        NSApp.mainMenu = menu
    }
    @objc func reloadPage() { webView.reload() }

    func launchService() {
        let data = root.appendingPathComponent("data")
        do {
            try FileManager.default.createDirectory(at: data, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            let logfile = data.appendingPathComponent("server.log")
            if !FileManager.default.fileExists(atPath: logfile.path) {
                FileManager.default.createFile(atPath: logfile.path, contents: nil, attributes: [.posixPermissions: 0o600])
            } else if let size = (try? FileManager.default.attributesOfItem(atPath: logfile.path))?[.size] as? UInt64, size > 2 * 1024 * 1024 {
                try? Data().write(to: logfile)
            }
            log = try FileHandle(forWritingTo: logfile); try log?.seekToEnd()
            let child = Process()
            let candidates = [
                root.appendingPathComponent(".venv/bin/python"),
                URL(fileURLWithPath: "/opt/homebrew/bin/python3"),
                URL(fileURLWithPath: "/usr/local/bin/python3"),
                URL(fileURLWithPath: "/usr/bin/python3")
            ]
            child.executableURL = candidates.first { FileManager.default.isExecutableFile(atPath: $0.path) } ?? candidates[0]
            child.arguments = [root.appendingPathComponent("server.py").path, "--host", "0.0.0.0", "--port", "8844", "--parent-pid", String(ProcessInfo.processInfo.processIdentifier)]
            child.currentDirectoryURL = root
            child.standardInput = FileHandle.nullDevice
            child.standardOutput = log; child.standardError = log
            child.environment = ProcessInfo.processInfo.environment.merging(["CINEVA_DATA_DIR": data.path, "PYTHONUNBUFFERED": "1"]) { _, new in new }
            child.terminationHandler = { [weak self] _ in
                DispatchQueue.main.async {
                    guard let self = self, !self.shuttingDown, self.poll == nil else { return }
                    NSApp.terminate(nil)
                }
            }
            service = child
            try child.run()
            poll = Timer.scheduledTimer(withTimeInterval: 0.35, repeats: true) { [weak self] _ in self?.checkReady() }
        } catch { fail("Yerel medya sunucusu başlatılamadı. Kurulumu kontrol edin.") }
    }

    func checkReady() {
        guard !shuttingDown, let child = service else { return }
        checks += 1
        if !child.isRunning || checks > 45 { fail("Cineva sunucusu açılamadı. Başka bir örneğin çalışmadığından emin olun."); return }
        let pidFile = root.appendingPathComponent("data/server.pid")
        guard let pid = try? String(contentsOf: pidFile, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines), pid == String(child.processIdentifier) else { return }
        var request = URLRequest(url: URL(string: "http://localhost:8844/api/health")!)
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard error == nil, let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any], json["app"] as? String == "cineva", json["ok"] as? Bool == true else { return }
            DispatchQueue.main.async {
                guard let self = self, self.poll != nil, !self.shuttingDown else { return }
                self.poll?.invalidate(); self.poll = nil
                self.webView.load(URLRequest(url: URL(string: "http://localhost:8844/")!))
            }
        }.resume()
    }
    func fail(_ text: String) {
        poll?.invalidate(); poll = nil
        let alert = NSAlert(); alert.messageText = "Cineva açılamadı"; alert.informativeText = text
        alert.runModal(); NSApp.terminate(nil)
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil); return true
    }
    func applicationWillTerminate(_ notification: Notification) {
        shuttingDown = true; poll?.invalidate(); poll = nil
        webView?.stopLoading()
        if let child = service, child.isRunning {
            child.terminate()
            let deadline = Date().addingTimeInterval(4)
            while child.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
            if child.isRunning { kill(child.processIdentifier, SIGKILL) }
        }
        try? log?.close()
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if navigationAction.shouldPerformDownload { decisionHandler(.download); return }
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if url.scheme == "about" || url.scheme == "blob" || ((url.host == "localhost" || url.host == "127.0.0.1") && url.port == 8844) { decisionHandler(.allow) }
        else { decisionHandler(.cancel) }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(navigationResponse.canShowMIMEType ? .allow : .download)
    }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel(); panel.nameFieldStringValue = (suggestedFilename as NSString).lastPathComponent
        panel.beginSheetModal(for: window) { result in completionHandler(result == .OK ? panel.url : nil) }
    }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel(); panel.canChooseDirectories = false; panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.allowedContentTypes = [.json]
        panel.beginSheetModal(for: window) { result in completionHandler(result == .OK ? panel.urls : nil) }
    }
}

let app = NSApplication.shared
let delegate = CinevaDelegate()
app.delegate = delegate
app.run()
