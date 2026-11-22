import AppKit
import Combine
import SwiftUI
import UniformTypeIdentifiers
import WebKit

@MainActor
final class MavieMacDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var overlayHostingView: NSHostingView<LaunchOverlayView>!
    private var preferencesWindow: NSWindow?
    private let serverManager = ServerProcessManager()
    private var statusCancellable: AnyCancellable?
    private var hasLoadedWebApp = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.appearance = NSAppearance(named: .darkAqua)
        if let iconURL = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
           let iconImage = NSImage(contentsOf: iconURL) {
            NSApp.applicationIconImage = iconImage
        }
        buildMenu()

        let configuration = WKWebViewConfiguration()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        configuration.preferences.isElementFullscreenEnabled = true

        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.underPageBackgroundColor = NSColor(red: 14.0 / 255.0, green: 16.0 / 255.0, blue: 21.0 / 255.0, alpha: 1.0)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.translatesAutoresizingMaskIntoConstraints = false

        let overlay = LaunchOverlayView(
            manager: serverManager,
            onRetry: { [weak self] in
                self?.hasLoadedWebApp = false
                self?.showOverlay()
                self?.serverManager.restart()
            },
            onQuit: {
                NSApp.terminate(nil)
            }
        )
        overlayHostingView = NSHostingView(rootView: overlay)
        overlayHostingView.translatesAutoresizingMaskIntoConstraints = false

        let visualEffect = NSVisualEffectView()
        visualEffect.material = .underWindowBackground
        visualEffect.blendingMode = .behindWindow
        visualEffect.state = .active
        visualEffect.translatesAutoresizingMaskIntoConstraints = false

        let container = NSView(frame: NSRect(x: 0, y: 0, width: 1220, height: 840))
        container.addSubview(visualEffect)
        container.addSubview(webView)
        container.addSubview(overlayHostingView)

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1220, height: 840),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "Mavie"
        window.isOpaque = false
        window.backgroundColor = .clear
        window.titlebarAppearsTransparent = true
        window.minSize = NSSize(width: 480, height: 620)
        window.delegate = self
        window.isReleasedWhenClosed = false
        window.contentView = container

        let webTopAnchor = (window.contentLayoutGuide as? NSLayoutGuide)?.topAnchor ?? container.topAnchor
        NSLayoutConstraint.activate([
            visualEffect.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            visualEffect.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            visualEffect.topAnchor.constraint(equalTo: container.topAnchor),
            visualEffect.bottomAnchor.constraint(equalTo: container.bottomAnchor),

            webView.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            webView.topAnchor.constraint(equalTo: webTopAnchor),
            webView.bottomAnchor.constraint(equalTo: container.bottomAnchor),

            overlayHostingView.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            overlayHostingView.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            overlayHostingView.topAnchor.constraint(equalTo: container.topAnchor),
            overlayHostingView.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])

        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        observeServerStatus()
        serverManager.start()
    }

    private func observeServerStatus() {
        statusCancellable = serverManager.$status
            .receive(on: RunLoop.main)
            .sink { [weak self] status in
                guard let self else { return }
                switch status {
                case .ready:
                    if !self.hasLoadedWebApp {
                        self.hasLoadedWebApp = true
                        self.webView.load(URLRequest(url: self.serverManager.baseURL))
                    }
                case .failed:
                    self.showOverlay()
                case .idle, .starting:
                    self.showOverlay()
                }
            }
    }

    private func showOverlay() {
        overlayHostingView.isHidden = false
        overlayHostingView.alphaValue = 1.0
    }

    private func hideOverlay() {
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.25
            overlayHostingView.animator().alphaValue = 0.0
        }, completionHandler: { [weak self] in
            Task { @MainActor in
                self?.overlayHostingView.isHidden = true
            }
        })
    }

    // MARK: - Native Menu Bar

    private func buildMenu() {
        let menu = NSMenu()

        let appMenuItem = NSMenuItem()
        menu.addItem(appMenuItem)
        let appMenu = NSMenu()
        appMenuItem.submenu = appMenu

        let aboutItem = NSMenuItem(title: "Mavie Hakkında", action: #selector(showAbout), keyEquivalent: "")
        aboutItem.target = self
        appMenu.addItem(aboutItem)

        appMenu.addItem(.separator())

        let prefsItem = NSMenuItem(title: "Tercihler / Sunucu Durumu…", action: #selector(openPreferences), keyEquivalent: ",")
        prefsItem.target = self
        appMenu.addItem(prefsItem)

        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Mavie’den Çık", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        let fileMenuItem = NSMenuItem()
        menu.addItem(fileMenuItem)
        let fileMenu = NSMenu(title: "Dosya")
        fileMenuItem.submenu = fileMenu

        let openDataItem = NSMenuItem(title: "Veri Klasörünü Aç", action: #selector(openDataFolder), keyEquivalent: "")
        openDataItem.target = self
        fileMenu.addItem(openDataItem)

        let openLogItem = NSMenuItem(title: "Sunucu Günlüğünü Aç", action: #selector(openLogFile), keyEquivalent: "")
        openLogItem.target = self
        fileMenu.addItem(openLogItem)

        let restartItem = NSMenuItem(title: "Sunucuyu Yeniden Başlat", action: #selector(restartServer), keyEquivalent: "")
        restartItem.target = self
        fileMenu.addItem(restartItem)

        fileMenu.addItem(.separator())
        fileMenu.addItem(withTitle: "Pencereyi Kapat", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")

        let editMenuItem = NSMenuItem()
        menu.addItem(editMenuItem)
        let editMenu = NSMenu(title: "Düzen")
        editMenuItem.submenu = editMenu
        editMenu.addItem(withTitle: "Geri Al", action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: "Kes", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Kopyala", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Yapıştır", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Tümünü Seç", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        let viewMenuItem = NSMenuItem()
        menu.addItem(viewMenuItem)
        let viewMenu = NSMenu(title: "Görünüm")
        viewMenuItem.submenu = viewMenu

        let reloadItem = NSMenuItem(title: "Yenile", action: #selector(reloadPage), keyEquivalent: "r")
        reloadItem.target = self
        viewMenu.addItem(reloadItem)

        let fullScreenItem = NSMenuItem(title: "Tam Ekran", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        fullScreenItem.keyEquivalentModifierMask = [.command, .control]
        viewMenu.addItem(fullScreenItem)

        let windowMenuItem = NSMenuItem()
        menu.addItem(windowMenuItem)
        let windowMenu = NSMenu(title: "Pencere")
        windowMenuItem.submenu = windowMenu
        windowMenu.addItem(withTitle: "Simge Durumuna Küçült", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Öne Getir", action: #selector(NSApplication.arrangeInFront(_:)), keyEquivalent: "")

        let helpMenuItem = NSMenuItem()
        menu.addItem(helpMenuItem)
        let helpMenu = NSMenu(title: "Yardım")
        helpMenuItem.submenu = helpMenu
        let websiteItem = NSMenuItem(title: "Mavie Web Sitesini Aç", action: #selector(openWebsite), keyEquivalent: "")
        websiteItem.target = self
        helpMenu.addItem(websiteItem)

        NSApp.mainMenu = menu
    }

    @objc private func showAbout() {
        let alert = NSAlert()
        alert.messageText = "Mavie Medya Merkezi"
        alert.informativeText = "Sürüm 2.2.0\nTamamen ücretsiz ve hesap gerektirmeyen yerel medya sunucusu, HLS oynatıcı ve yerel ağ (LAN) eşitlemesi ile macOS masaüstü uygulaması."
        alert.addButton(withTitle: "Tamam")
        alert.runModal()
    }

    @objc private func openPreferences() {
        if let existing = preferencesWindow {
            existing.makeKeyAndOrderFront(nil)
            return
        }
        let view = PreferencesView(manager: serverManager) { [weak self] in
            self?.preferencesWindow?.close()
        }
        let hosting = NSHostingController(rootView: view)
        let fx = NSVisualEffectView()
        fx.material = .underWindowBackground
        fx.blendingMode = .behindWindow
        fx.state = .active
        fx.translatesAutoresizingMaskIntoConstraints = false

        let wrapper = NSView()
        wrapper.addSubview(fx)
        hosting.view.translatesAutoresizingMaskIntoConstraints = false
        wrapper.addSubview(hosting.view)
        NSLayoutConstraint.activate([
            fx.leadingAnchor.constraint(equalTo: wrapper.leadingAnchor),
            fx.trailingAnchor.constraint(equalTo: wrapper.trailingAnchor),
            fx.topAnchor.constraint(equalTo: wrapper.topAnchor),
            fx.bottomAnchor.constraint(equalTo: wrapper.bottomAnchor),
            hosting.view.leadingAnchor.constraint(equalTo: wrapper.leadingAnchor),
            hosting.view.trailingAnchor.constraint(equalTo: wrapper.trailingAnchor),
            hosting.view.topAnchor.constraint(equalTo: wrapper.topAnchor),
            hosting.view.bottomAnchor.constraint(equalTo: wrapper.bottomAnchor),
        ])

        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 620, height: 520),
            styleMask: [.titled, .closable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        win.title = "Mavie Tercihleri"
        win.titlebarAppearsTransparent = true
        win.isOpaque = false
        win.backgroundColor = .clear
        win.isMovableByWindowBackground = true
        win.appearance = NSAppearance(named: .darkAqua)
        win.contentView = wrapper
        win.isReleasedWhenClosed = false
        win.center()
        preferencesWindow = win
        win.makeKeyAndOrderFront(nil)
    }

    @objc private func openDataFolder() {
        serverManager.openDataDirectory()
    }

    @objc private func openLogFile() {
        serverManager.openLogFile()
    }

    @objc private func restartServer() {
        hasLoadedWebApp = false
        showOverlay()
        serverManager.restart()
    }

    @objc private func reloadPage() {
        if serverManager.status.isReady {
            webView.reload()
        } else {
            restartServer()
        }
    }

    @objc private func openWebsite() {
        if let url = URL(string: "https://maviemovie.netlify.app") {
            NSWorkspace.shared.open(url)
        }
    }

    // MARK: - NSApplicationDelegate

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil)
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        statusCancellable?.cancel()
        webView?.stopLoading()
        serverManager.stop()
    }

    // MARK: - WKWebView Delegates

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if serverManager.status.isReady {
            hideOverlay()
        }
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        if navigationAction.shouldPerformDownload {
            decisionHandler(.download)
            return
        }
        guard let url = navigationAction.request.url else {
            decisionHandler(.cancel)
            return
        }
        if url.scheme == "about" || url.scheme == "blob" {
            decisionHandler(.allow)
            return
        }
        if (url.host == "localhost" || url.host == "127.0.0.1") && url.port == serverManager.port {
            decisionHandler(.allow)
            return
        }
        if url.scheme == "https" || url.scheme == "http" {
            NSWorkspace.shared.open(url)
        }
        decisionHandler(.cancel)
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationResponse: WKNavigationResponse,
        decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void
    ) {
        decisionHandler(navigationResponse.canShowMIMEType ? .allow : .download)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(
        _ download: WKDownload,
        decideDestinationUsing response: URLResponse,
        suggestedFilename: String,
        completionHandler: @escaping (URL?) -> Void
    ) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = (suggestedFilename as NSString).lastPathComponent
        panel.beginSheetModal(for: window) { result in
            completionHandler(result == .OK ? panel.url : nil)
        }
    }

    func webView(
        _ webView: WKWebView,
        runOpenPanelWith parameters: WKOpenPanelParameters,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping ([URL]?) -> Void
    ) {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.allowedContentTypes = [.json, .movie, .mpeg4Movie, .item]
        panel.beginSheetModal(for: window) { result in
            completionHandler(result == .OK ? panel.urls : nil)
        }
    }
}

@main
struct MavieMacEntry {
    @MainActor
    static func main() {
        let args = CommandLine.arguments
        let env = ProcessInfo.processInfo.environment
        if args.contains("--smoke-test") || env["MAVIE_MACOS_SMOKE"] == "1" {
            let manager = ServerProcessManager()
            Task { @MainActor in
                let code = await manager.runHeadlessSmokeTest()
                exit(code)
            }
            RunLoop.main.run()
            return
        }

        let app = NSApplication.shared
        let delegate = MavieMacDelegate()
        app.delegate = delegate
        app.run()
    }
}
