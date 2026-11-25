import AVFoundation
import AVKit
import SwiftUI
import UIKit

@MainActor
private final class PlayerController: ObservableObject {
    @Published var isPlaying = false
    @Published var isLoading = true
    @Published var currentTime: Double = 0
    @Published var duration: Double = 0
    @Published var playbackRate: Float = 1.0
    @Published var errorMessage: String?
    @Published var audioOptions: [AVMediaSelectionOption] = []
    @Published var subtitleOptions: [AVMediaSelectionOption] = []
    @Published var selectedAudioOption: AVMediaSelectionOption?
    @Published var selectedSubtitleOption: AVMediaSelectionOption?
    @Published var isPiPSupported = false
    @Published var isPiPActive = false
    @Published var sleepRemainingMinutes: Int?

    var hasCompletedInitialSeek: Bool {
        recoveryState?.hasCompletedInitialSeek ?? false
    }

    var onPlaybackCompleted: (() -> Void)?

    let player = AVPlayer()
    var pipController: AVPictureInPictureController?

    private var timeObserver: Any?
    private var statusObservation: NSKeyValueObservation?
    private var rateObservation: NSKeyValueObservation?
    private var timeControlObservation: NSKeyValueObservation?
    private var itemNotificationObservers: [NSObjectProtocol] = []
    private var audioSessionObservers: [NSObjectProtocol] = []
    private var sleepTimerTask: Task<Void, Never>?
    private var stallWatchdogTask: Task<Void, Never>?
    private var recoveryTask: Task<Void, Never>?
    private var recoveryState: PlaybackRecoveryState?
    private var savedTrackPreference: SyncTrackPreferenceData?
    private var wasPlayingBeforeInterruption = false
    private var loadGeneration: UInt64 = 0

    func load(
        plan: PlaybackSourcePlan,
        resumeAt: Double,
        trackPreference: SyncTrackPreferenceData?
    ) {
        loadGeneration &+= 1
        let activeGeneration = loadGeneration
        recoveryTask?.cancel()
        recoveryTask = nil
        stallWatchdogTask?.cancel()
        stallWatchdogTask = nil
        teardownItemObserversOnly()

        errorMessage = nil
        isLoading = true
        currentTime = max(0, resumeAt)
        duration = 0
        savedTrackPreference = trackPreference
        recoveryState = PlaybackRecoveryState(
            isLive: plan.isLive,
            currentURL: plan.primaryURL,
            liveTSFallbackURL: plan.liveTSFallbackURL,
            pendingResumeSeconds: resumeAt
        )

        ensureAudioSessionObservers()
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .moviePlayback, options: [.allowAirPlay])
        try? session.setActive(true)

        loadAsset(url: plan.primaryURL, userAgent: MavieHTTPClient.primaryUserAgent, generation: activeGeneration)
    }

    private func loadAsset(url: URL, userAgent: String, generation: UInt64) {
        guard generation == loadGeneration else { return }
        stallWatchdogTask?.cancel()
        stallWatchdogTask = nil
        teardownItemObserversOnly()

        isLoading = true
        errorMessage = nil

        let asset: AVURLAsset
        if let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https" {
            asset = AVURLAsset(
                url: url,
                options: [
                    "AVURLAssetHTTPHeaderFieldsKey": [
                        "User-Agent": userAgent
                    ]
                ]
            )
        } else {
            asset = AVURLAsset(url: url)
        }
        let item = AVPlayerItem(asset: asset)

        statusObservation = item.observe(\.status, options: [.new, .initial]) { [weak self] observedItem, _ in
            Task { @MainActor [weak self] in
                guard let self, self.loadGeneration == generation else { return }
                switch observedItem.status {
                case .readyToPlay:
                    let dur = observedItem.duration.seconds
                    if dur.isFinite && dur > 0 {
                        self.duration = dur
                    }
                    await self.loadMediaTracks(for: observedItem)
                    guard self.loadGeneration == generation else { return }
                    if let resumeTarget = self.recoveryState?.markReadyToPlay() {
                        await self.seekItem(observedItem, toSeconds: resumeTarget)
                        guard self.loadGeneration == generation else { return }
                    }
                    self.isLoading = false
                    self.player.play()
                    self.player.rate = self.playbackRate
                case .failed:
                    let httpStatus = observedItem.errorLog()?.events.last?.errorStatusCode
                    let nsErr = observedItem.error as NSError?
                    let signal = PlaybackFailureSignal(
                        httpStatusCode: (httpStatus ?? 0) > 0 ? httpStatus : nil,
                        errorDomain: nsErr?.domain,
                        errorCode: nsErr?.code,
                        isStallTimeout: false,
                        rawMessage: observedItem.error?.localizedDescription ?? ""
                    )
                    self.handlePlaybackFailure(signal, generation: generation)
                case .unknown:
                    break
                @unknown default:
                    break
                }
            }
        }

        rateObservation = player.observe(\.rate, options: [.new, .initial]) { [weak self] p, _ in
            let activeRate = p.rate
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.isPlaying = activeRate > 0.05 || self.player.timeControlStatus == .playing
            }
        }

        timeControlObservation = player.observe(\.timeControlStatus, options: [.new, .initial]) { [weak self] p, _ in
            let controlStatus = p.timeControlStatus
            let waitReason = p.reasonForWaitingToPlay
            let ready = p.currentItem?.status == .readyToPlay
            Task { @MainActor [weak self] in
                guard let self, self.loadGeneration == generation else { return }
                switch controlStatus {
                case .playing:
                    self.isPlaying = true
                    self.isLoading = false
                    self.cancelStallWatchdog()
                    self.setIdleTimerDisabled(true)
                case .waitingToPlayAtSpecifiedRate:
                    self.isPlaying = false
                    self.setIdleTimerDisabled(false)
                    if waitReason == .toMinimizeStalls || waitReason == .evaluatingBufferingRate {
                        self.isLoading = true
                        self.startStallWatchdog(generation: generation)
                    }
                case .paused:
                    self.isPlaying = false
                    self.setIdleTimerDisabled(false)
                    if ready {
                        self.isLoading = false
                        self.cancelStallWatchdog()
                    }
                @unknown default:
                    break
                }
            }
        }

        let interval = CMTime(seconds: 0.5, preferredTimescale: 600)
        timeObserver = player.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] cmTime in
            let sec = cmTime.seconds
            Task { @MainActor [weak self] in
                guard let self, self.loadGeneration == generation else { return }
                if !(self.recoveryState?.isScrubbing ?? false), sec.isFinite && sec >= 0 {
                    self.currentTime = sec
                }
                if let dur = self.player.currentItem?.duration.seconds, dur.isFinite && dur > 0 {
                    self.duration = dur
                }
            }
        }

        let nc = NotificationCenter.default
        let failedObs = nc.addObserver(forName: .AVPlayerItemFailedToPlayToEndTime, object: item, queue: .main) { [weak self] note in
            let nsErr = note.userInfo?[AVPlayerItemFailedToPlayToEndTimeErrorKey] as? NSError
            let domain = nsErr?.domain
            let code = nsErr?.code
            let rawMsg = nsErr?.localizedDescription ?? ""
            let statusCode = (note.object as? AVPlayerItem)?.errorLog()?.events.last?.errorStatusCode
            Task { @MainActor [weak self] in
                guard let self, self.loadGeneration == generation else { return }
                let signal = PlaybackFailureSignal(
                    httpStatusCode: (statusCode ?? 0) > 0 ? statusCode : nil,
                    errorDomain: domain,
                    errorCode: code,
                    isStallTimeout: false,
                    rawMessage: rawMsg
                )
                self.handlePlaybackFailure(signal, generation: generation)
            }
        }
        let stalledObs = nc.addObserver(forName: .AVPlayerItemPlaybackStalled, object: item, queue: .main) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self, self.loadGeneration == generation else { return }
                self.isLoading = true
                self.startStallWatchdog(generation: generation)
            }
        }
        let endedObs = nc.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self, self.loadGeneration == generation else { return }
                self.cancelStallWatchdog()
                self.setIdleTimerDisabled(false)
                self.isPlaying = false
                self.onPlaybackCompleted?()
            }
        }
        itemNotificationObservers = [failedObs, stalledObs, endedObs]

        player.replaceCurrentItem(with: item)
    }

    private func ensureAudioSessionObservers() {
        guard audioSessionObservers.isEmpty else { return }
        let nc = NotificationCenter.default
        let interruptionObs = nc.addObserver(
            forName: AVAudioSession.interruptionNotification,
            object: AVAudioSession.sharedInstance(),
            queue: .main
        ) { [weak self] note in
            let rawType = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt
            let rawOptions = note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt
            Task { @MainActor [weak self] in
                guard let self, let rawType, let type = AVAudioSession.InterruptionType(rawValue: rawType) else { return }
                switch type {
                case .began:
                    self.wasPlayingBeforeInterruption = self.player.rate > 0.05 || self.player.timeControlStatus == .playing
                    self.player.pause()
                    self.setIdleTimerDisabled(false)
                case .ended:
                    let options = AVAudioSession.InterruptionOptions(rawValue: rawOptions ?? 0)
                    if options.contains(.shouldResume) && self.wasPlayingBeforeInterruption {
                        self.wasPlayingBeforeInterruption = false
                        try? AVAudioSession.sharedInstance().setActive(true)
                        self.player.play()
                        self.player.rate = self.playbackRate
                    } else {
                        self.wasPlayingBeforeInterruption = false
                    }
                @unknown default:
                    break
                }
            }
        }

        let routeObs = nc.addObserver(
            forName: AVAudioSession.routeChangeNotification,
            object: AVAudioSession.sharedInstance(),
            queue: .main
        ) { [weak self] note in
            let rawReason = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
            Task { @MainActor [weak self] in
                guard let self, let rawReason,
                      let reason = AVAudioSession.RouteChangeReason(rawValue: rawReason),
                      reason == .oldDeviceUnavailable else { return }
                self.player.pause()
                self.setIdleTimerDisabled(false)
            }
        }
        audioSessionObservers = [interruptionObs, routeObs]
    }

    private func startStallWatchdog(generation: UInt64) {
        stallWatchdogTask?.cancel()
        stallWatchdogTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 15_000_000_000)
            guard let self, !Task.isCancelled, self.loadGeneration == generation else { return }
            if self.player.timeControlStatus != .playing && self.errorMessage == nil {
                self.handlePlaybackFailure(PlaybackFailureSignal(isStallTimeout: true), generation: generation)
            }
        }
    }

    private func cancelStallWatchdog() {
        stallWatchdogTask?.cancel()
        stallWatchdogTask = nil
    }

    private func handlePlaybackFailure(_ signal: PlaybackFailureSignal, generation: UInt64) {
        guard generation == loadGeneration else { return }
        cancelStallWatchdog()
        setIdleTimerDisabled(false)

        guard var state = recoveryState else {
            isLoading = false
            errorMessage = PlaybackRecoveryState.classifyError(signal)
            return
        }

        switch state.nextAction(for: signal) {
        case .retry(let nextURL, let ua, let delaySeconds, let reason):
            if case .transientReconnect = reason, !state.isLive && currentTime > 3 {
                state.pendingResumeSeconds = currentTime
                state.hasCompletedInitialSeek = false
            }
            recoveryState = state
            isLoading = true
            recoveryTask?.cancel()
            recoveryTask = Task { @MainActor [weak self] in
                if delaySeconds > 0 {
                    try? await Task.sleep(nanoseconds: UInt64(delaySeconds * 1_000_000_000))
                }
                guard let self, !Task.isCancelled, self.loadGeneration == generation else { return }
                self.loadAsset(url: nextURL, userAgent: ua, generation: generation)
            }
        case .fail(let message):
            recoveryState = state
            isLoading = false
            errorMessage = message
        }
    }

    private func seekItem(_ item: AVPlayerItem, toSeconds seconds: Double) async {
        guard item.status == .readyToPlay else { return }
        let target = CMTime(seconds: max(0, seconds), preferredTimescale: 600)
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            item.seek(to: target, toleranceBefore: .zero, toleranceAfter: .zero) { _ in
                continuation.resume()
            }
        }
    }

    private func setIdleTimerDisabled(_ disabled: Bool) {
        UIApplication.shared.isIdleTimerDisabled = disabled
    }

    func setScrubbing(_ scrubbing: Bool) {
        recoveryState?.isScrubbing = scrubbing
    }

    func togglePlayPause() {
        if player.rate > 0.05 || player.timeControlStatus == .playing {
            player.pause()
        } else {
            player.play()
            player.rate = playbackRate
        }
    }

    func seek(by delta: Double) {
        let target = max(0, min(duration > 0 ? duration : currentTime + delta, currentTime + delta))
        seek(to: target)
    }

    func seek(to seconds: Double, toleranceSeconds: Double = 0) {
        let clamped = max(0, seconds)
        currentTime = clamped
        let target = CMTime(seconds: clamped, preferredTimescale: 600)
        let tolerance = toleranceSeconds > 0 ? CMTime(seconds: toleranceSeconds, preferredTimescale: 600) : .zero
        player.seek(to: target, toleranceBefore: tolerance, toleranceAfter: tolerance)
    }

    func setRate(_ rate: Float) {
        playbackRate = rate
        if player.rate > 0.05 {
            player.rate = rate
        }
    }

    func setSleepTimer(minutes: Int?) {
        sleepTimerTask?.cancel()
        sleepRemainingMinutes = minutes
        guard let minutes, minutes > 0 else { return }
        sleepTimerTask = Task { [weak self] in
            var left = minutes
            while left > 0 && !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 60_000_000_000)
                if Task.isCancelled { return }
                left -= 1
                await MainActor.run {
                    self?.sleepRemainingMinutes = left > 0 ? left : nil
                }
            }
            if !Task.isCancelled {
                await MainActor.run {
                    self?.player.pause()
                    self?.setIdleTimerDisabled(false)
                }
            }
        }
    }

    func selectAudio(_ option: AVMediaSelectionOption?) {
        guard let item = player.currentItem else { return }
        selectedAudioOption = option
        Task { @MainActor in
            guard let group = try? await item.asset.loadMediaSelectionGroup(for: .audible) else { return }
            item.select(option, in: group)
        }
    }

    func selectSubtitle(_ option: AVMediaSelectionOption?) {
        guard let item = player.currentItem else { return }
        selectedSubtitleOption = option
        Task { @MainActor in
            guard let group = try? await item.asset.loadMediaSelectionGroup(for: .legible) else { return }
            item.select(option, in: group)
        }
    }

    func togglePiP() {
        guard let pipController else { return }
        if pipController.isPictureInPictureActive {
            pipController.stopPictureInPicture()
        } else {
            pipController.startPictureInPicture()
        }
    }

    func teardown() {
        loadGeneration &+= 1
        sleepTimerTask?.cancel()
        sleepTimerTask = nil
        stallWatchdogTask?.cancel()
        stallWatchdogTask = nil
        recoveryTask?.cancel()
        recoveryTask = nil
        onPlaybackCompleted = nil

        if pipController?.isPictureInPictureActive == true {
            pipController?.stopPictureInPicture()
        }
        pipController?.delegate = nil
        pipController = nil
        isPiPActive = false
        isPiPSupported = false

        player.pause()
        setIdleTimerDisabled(false)
        teardownItemObserversOnly()
        for obs in audioSessionObservers {
            NotificationCenter.default.removeObserver(obs)
        }
        audioSessionObservers.removeAll()
        player.replaceCurrentItem(with: nil)
    }

    private func teardownItemObserversOnly() {
        if let observer = timeObserver {
            player.removeTimeObserver(observer)
            timeObserver = nil
        }
        statusObservation?.invalidate()
        statusObservation = nil
        rateObservation?.invalidate()
        rateObservation = nil
        timeControlObservation?.invalidate()
        timeControlObservation = nil
        for obs in itemNotificationObservers {
            NotificationCenter.default.removeObserver(obs)
        }
        itemNotificationObservers.removeAll()
    }

    private func loadMediaTracks(for item: AVPlayerItem) async {
        let asset = item.asset
        if let audible = try? await asset.loadMediaSelectionGroup(for: .audible) {
            audioOptions = audible.options
            let candidates = audible.options.enumerated().map { idx, opt in
                PlaybackTrackCandidate(
                    id: String(idx),
                    displayName: opt.displayName,
                    languageTag: opt.locale?.identifier ?? opt.extendedLanguageTag
                )
            }
            if let matchIdx = PlaybackRecoveryState.matchAudioOption(preferred: savedTrackPreference, options: candidates),
               matchIdx < audible.options.count {
                let matched = audible.options[matchIdx]
                item.select(matched, in: audible)
                selectedAudioOption = matched
            } else {
                selectedAudioOption = item.currentMediaSelection.selectedMediaOption(in: audible)
            }
        }
        if let legible = try? await asset.loadMediaSelectionGroup(for: .legible) {
            subtitleOptions = legible.options
            let candidates = legible.options.enumerated().map { idx, opt in
                PlaybackTrackCandidate(
                    id: String(idx),
                    displayName: opt.displayName,
                    languageTag: opt.locale?.identifier ?? opt.extendedLanguageTag
                )
            }
            switch PlaybackRecoveryState.matchSubtitleOption(preferred: savedTrackPreference, options: candidates) {
            case .off:
                item.select(nil, in: legible)
                selectedSubtitleOption = nil
            case .select(let matchIdx) where matchIdx < legible.options.count:
                let matched = legible.options[matchIdx]
                item.select(matched, in: legible)
                selectedSubtitleOption = matched
            default:
                selectedSubtitleOption = item.currentMediaSelection.selectedMediaOption(in: legible)
            }
        }
    }
}

private final class PlayerLayerHostView: UIView {
    override class var layerClass: AnyClass { AVPlayerLayer.self }
    var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
}

private struct MavieVideoSurfaceView: UIViewRepresentable {
    var controller: PlayerController

    func makeCoordinator() -> Coordinator {
        Coordinator(controller: controller)
    }

    func makeUIView(context: Context) -> PlayerLayerHostView {
        let view = PlayerLayerHostView()
        view.backgroundColor = .black
        view.playerLayer.player = controller.player
        view.playerLayer.videoGravity = .resizeAspect

        if AVPictureInPictureController.isPictureInPictureSupported(),
           let pip = AVPictureInPictureController(playerLayer: view.playerLayer) {
            pip.delegate = context.coordinator
            controller.pipController = pip
            Task { @MainActor in
                controller.isPiPSupported = true
            }
        }
        return view
    }

    func updateUIView(_ uiView: PlayerLayerHostView, context: Context) {
        if uiView.playerLayer.player !== controller.player {
            uiView.playerLayer.player = controller.player
        }
    }

    final class Coordinator: NSObject, AVPictureInPictureControllerDelegate {
        let controller: PlayerController
        init(controller: PlayerController) {
            self.controller = controller
        }

        func pictureInPictureControllerDidStartPictureInPicture(_ pictureInPictureController: AVPictureInPictureController) {
            Task { @MainActor in controller.isPiPActive = true }
        }

        func pictureInPictureControllerDidStopPictureInPicture(_ pictureInPictureController: AVPictureInPictureController) {
            Task { @MainActor in controller.isPiPActive = false }
        }
    }
}

private struct MavieAirPlayRoutePicker: UIViewRepresentable {
    func makeUIView(context: Context) -> AVRoutePickerView {
        let picker = AVRoutePickerView()
        picker.tintColor = .white
        picker.activeTintColor = UIColor(red: 124.0 / 255.0, green: 58.0 / 255.0, blue: 237.0 / 255.0, alpha: 1.0)
        picker.prioritizesVideoDevices = true
        return picker
    }

    func updateUIView(_ uiView: AVRoutePickerView, context: Context) {}
}

public struct PlayerView: View {
    @ObservedObject public var store: LibraryStore
    public var initialItem: MediaItem
    public var detail: MediaDetail?
    public var onClose: () -> Void

    @StateObject private var controller = PlayerController()
    @State private var currentItem: MediaItem
    @State private var showControls = true
    @State private var showTrackSheet = false
    @State private var lastSavedAt: Date = .distantPast
    @State private var isScrubbing = false
    @State private var scrubPosition: Double = 0
    @State private var lastScrubSeekAt: Date = .distantPast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(
        store: LibraryStore,
        initialItem: MediaItem,
        detail: MediaDetail?,
        onClose: @escaping () -> Void
    ) {
        self.store = store
        self.initialItem = initialItem
        self.detail = detail
        self.onClose = onClose
        _currentItem = State(initialValue: initialItem)
    }

    private var nextEpisode: MediaItem? {
        detail?.followingEpisode(after: currentItem)
    }

    public var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            MavieVideoSurfaceView(controller: controller)
                .ignoresSafeArea()
                .accessibilityHidden(true)

            Button {
                toggleControlsVisibility()
            } label: {
                Color.clear
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .ignoresSafeArea()
            .accessibilityLabel(showControls ? "Oynatıcı kontrollerini gizle" : "Oynatıcı kontrollerini göster")
            .accessibilitySortPriority(-1)
            .accessibilityAction(.escape) {
                closePlayer()
            }

            if controller.isLoading && controller.errorMessage == nil {
                VStack(spacing: 12) {
                    ProgressView()
                        .controlSize(.large)
                        .tint(MavieTheme.amber)
                    Text("Akış hazırlanıyor…")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.white)
                }
                .padding(20)
                .mavieCard(cornerRadius: 16)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Akış hazırlanıyor, lütfen bekleyin")

                if !showControls {
                    VStack {
                        HStack {
                            Button {
                                closePlayer()
                            } label: {
                                Label("Kapat", systemImage: "xmark")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 12)
                                    .frame(minWidth: 44, minHeight: 44)
                                    .mavieGlassPill()
                            }
                            .buttonStyle(MavieInteractiveCardButtonStyle())
                            .accessibilityLabel("Oynatıcıyı Kapat")
                            Spacer()
                        }
                        .padding(.horizontal, 16)
                        .padding(.top, 16)
                        Spacer()
                    }
                }
            }

            if let errorMessage = controller.errorMessage {
                VStack(spacing: 14) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.largeTitle)
                        .foregroundStyle(MavieTheme.danger)
                    Text("Oynatma Hatası")
                        .font(.headline)
                        .foregroundStyle(.white)
                    Text(errorMessage)
                        .font(.subheadline)
                        .foregroundStyle(MavieTheme.muted)
                        .multilineTextAlignment(.center)
                    HStack(spacing: 12) {
                        Button {
                            startPlayback(for: currentItem)
                        } label: {
                            Label("Tekrar Dene", systemImage: "arrow.clockwise")
                        }
                        .buttonStyle(MaviePrimaryButtonStyle(compact: true))
                        .accessibilityLabel("Videoyu Tekrar Dene")

                        Button {
                            closePlayer()
                        } label: {
                            Label("Kapat", systemImage: "xmark")
                        }
                        .buttonStyle(MavieGhostButtonStyle(compact: true))
                        .accessibilityLabel("Oynatıcıyı Kapat")
                    }
                }
                .padding(24)
                .frame(maxWidth: 420)
                .mavieCard()
                .padding(20)
            }

            if showControls && controller.errorMessage == nil {
                controlsOverlay
                    .transition(.opacity)
            }

            keyboardShortcutLayer
        }
        .statusBarHidden(true)
        .persistentSystemOverlays(.hidden)
        .onAppear {
            controller.onPlaybackCompleted = {
                persistProgress(forceCompleted: true)
                if let nextEp = nextEpisode {
                    currentItem = nextEp
                    startPlayback(for: nextEp)
                } else {
                    showControls = true
                }
            }
            startPlayback(for: currentItem)
        }
        .onChange(of: controller.currentTime) { _ in
            if Date().timeIntervalSince(lastSavedAt) >= 5 {
                persistProgress()
                lastSavedAt = Date()
            }
        }
        .onDisappear {
            persistProgress()
            store.flushProgressPersistence()
            controller.teardown()
        }
        .sheet(isPresented: $showTrackSheet) {
            trackSelectionSheet
        }
    }

    private var controlsOverlay: some View {
        VStack {
            // Top bar
            HStack(spacing: 10) {
                Button {
                    closePlayer()
                } label: {
                    Label("Kapat", systemImage: "xmark")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12)
                        .frame(minWidth: 44, minHeight: 44)
                        .mavieGlassPill()
                }
                .buttonStyle(MavieInteractiveCardButtonStyle())
                .accessibilityLabel("Oynatıcıyı Kapat")

                VStack(alignment: .leading, spacing: 2) {
                    Text(currentItem.name)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.white)
                        .lineLimit(1)
                    if let sleep = controller.sleepRemainingMinutes {
                        Text("Uyku zamanlayıcı: \(sleep) dk")
                            .font(.caption2)
                            .foregroundStyle(MavieTheme.amber)
                    }
                }

                Spacer()

                if controller.isPiPSupported {
                    Button {
                        controller.togglePiP()
                    } label: {
                        Label("PiP", systemImage: controller.isPiPActive ? "pip.exit" : "pip.enter")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 10)
                            .frame(minWidth: 44, minHeight: 44)
                            .mavieGlassPill()
                    }
                    .buttonStyle(MavieInteractiveCardButtonStyle())
                    .accessibilityLabel("Resim İçinde Resim Modunu Aç veya Kapat")
                }

                MavieAirPlayRoutePicker()
                    .frame(width: 44, height: 44)
                    .background(
                        Circle()
                            .fill(.ultraThinMaterial)
                            .overlay(Circle().fill(MavieTheme.glassTint))
                            .overlay(Circle().strokeBorder(MavieTheme.specularBorder, lineWidth: 1))
                    )
                    .accessibilityLabel("AirPlay Cihazı Seç")

                Button {
                    showTrackSheet = true
                } label: {
                    Label("Ses/Altyazı", systemImage: "captions.bubble")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 10)
                        .frame(minWidth: 44, minHeight: 44)
                        .mavieGlassPill()
                }
                .buttonStyle(MavieInteractiveCardButtonStyle())
                .accessibilityLabel("Ses ve Altyazı İzlerini Seç")
            }
            .padding(.horizontal, 16)
            .padding(.top, 16)

            Spacer()

            // Center transport
            HStack(spacing: 28) {
                Button {
                    controller.seek(by: -10)
                } label: {
                    VStack(spacing: 2) {
                        Image(systemName: "gobackward.10")
                            .font(.title2.weight(.bold))
                        Text("-10 sn")
                            .font(.caption2.weight(.semibold))
                    }
                    .foregroundStyle(.white)
                    .frame(minWidth: 56, minHeight: 56)
                    .background(
                        Circle()
                            .fill(.ultraThinMaterial)
                            .overlay(Circle().fill(MavieTheme.glassTint))
                            .overlay(Circle().strokeBorder(MavieTheme.specularBorder, lineWidth: 1))
                    )
                }
                .buttonStyle(MavieInteractiveCardButtonStyle())
                .accessibilityLabel("10 Saniye Geri Sar")

                Button {
                    controller.togglePlayPause()
                } label: {
                    VStack(spacing: 2) {
                        Image(systemName: controller.isPlaying ? "pause.fill" : "play.fill")
                            .font(.largeTitle.weight(.bold))
                        Text(controller.isPlaying ? "Duraklat" : "Oynat")
                            .font(.caption2.weight(.semibold))
                    }
                    .foregroundStyle(.white)
                    .frame(width: 76, height: 76)
                    .background(
                        Circle()
                            .fill(MavieTheme.brandGradient)
                            .overlay(Circle().strokeBorder(MavieTheme.specularAccentBorder, lineWidth: 1.2))
                    )
                    .shadow(color: MavieTheme.purple.opacity(0.42), radius: 16, y: 6)
                }
                .buttonStyle(MavieInteractiveCardButtonStyle())
                .accessibilityLabel(controller.isPlaying ? "Oynatmayı Duraklat" : "Oynat")

                Button {
                    controller.seek(by: 10)
                } label: {
                    VStack(spacing: 2) {
                        Image(systemName: "goforward.10")
                            .font(.title2.weight(.bold))
                        Text("+10 sn")
                            .font(.caption2.weight(.semibold))
                    }
                    .foregroundStyle(.white)
                    .frame(minWidth: 56, minHeight: 56)
                    .background(
                        Circle()
                            .fill(.ultraThinMaterial)
                            .overlay(Circle().fill(MavieTheme.glassTint))
                            .overlay(Circle().strokeBorder(MavieTheme.specularBorder, lineWidth: 1))
                    )
                }
                .buttonStyle(MavieInteractiveCardButtonStyle())
                .accessibilityLabel("10 Saniye İleri Sar")
            }

            Spacer()

            // Bottom scrubber & utility bar
            VStack(spacing: 10) {
                if controller.duration > 0 {
                    let displayTime = isScrubbing ? scrubPosition : controller.currentTime
                    HStack(spacing: 10) {
                        Text(formatClock(displayTime))
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.white)
                        Slider(
                            value: Binding(
                                get: { displayTime },
                                set: { newVal in
                                    scrubPosition = newVal
                                    if isScrubbing && Date().timeIntervalSince(lastScrubSeekAt) >= 0.25 {
                                        lastScrubSeekAt = Date()
                                        controller.seek(to: newVal, toleranceSeconds: 0.5)
                                    }
                                }
                            ),
                            in: 0...max(1, controller.duration),
                            onEditingChanged: { editing in
                                isScrubbing = editing
                                controller.setScrubbing(editing)
                                if editing {
                                    scrubPosition = controller.currentTime
                                } else {
                                    controller.seek(to: scrubPosition)
                                    persistProgress()
                                }
                            }
                        )
                        .tint(MavieTheme.coral)
                        .accessibilityLabel("Oynatma İlerleme Çubuğu")
                        .accessibilityValue("\(formatAccessibleTime(displayTime)) / \(formatAccessibleTime(controller.duration))")
                        Text(formatClock(controller.duration))
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(MavieTheme.muted)
                    }
                }

                HStack(spacing: 10) {
                    Menu {
                        ForEach([Float(0.5), 1.0, 1.25, 1.5, 2.0], id: \.self) { rate in
                            Button {
                                controller.setRate(rate)
                            } label: {
                                Text(String(format: "%.2gx", rate))
                            }
                        }
                    } label: {
                        Label(String(format: "Hız %.2gx", controller.playbackRate), systemImage: "speedometer")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 12)
                            .frame(minHeight: 44)
                            .mavieGlassPill()
                    }
                    .accessibilityLabel("Oynatma Hızını Değiştir")

                    Menu {
                        Button("Kapalı") { controller.setSleepTimer(minutes: nil) }
                        Button("15 Dakika") { controller.setSleepTimer(minutes: 15) }
                        Button("30 Dakika") { controller.setSleepTimer(minutes: 30) }
                        Button("60 Dakika") { controller.setSleepTimer(minutes: 60) }
                    } label: {
                        Label("Uyku", systemImage: "moon.zzz")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 12)
                            .frame(minHeight: 44)
                            .mavieGlassPill()
                    }
                    .accessibilityLabel("Uyku Zamanlayıcısı")

                    Spacer()

                    if let nextEp = nextEpisode {
                        Button {
                            persistProgress()
                            store.flushProgressPersistence()
                            currentItem = nextEp
                            startPlayback(for: nextEp)
                        } label: {
                            Label("Sonraki Bölüm", systemImage: "forward.end.fill")
                        }
                        .buttonStyle(MaviePrimaryButtonStyle(compact: true))
                        .accessibilityLabel("Sonraki Bölüm: \(nextEp.name)")
                    }
                }
            }
            .padding(16)
            .background(
                LinearGradient(
                    colors: [.clear, .black.opacity(0.78)],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
        }
    }

    private var trackSelectionSheet: some View {
        NavigationStack {
            List {
                Section("Ses İzleri") {
                    if controller.audioOptions.isEmpty {
                        Text("Bu akışta seçilebilir ek ses izi yok.")
                            .foregroundStyle(MavieTheme.muted)
                    } else {
                        ForEach(controller.audioOptions, id: \.self) { option in
                            Button {
                                controller.selectAudio(option)
                                saveCurrentTrackPreference()
                            } label: {
                                HStack {
                                    Text(option.displayName)
                                    Spacer()
                                    if controller.selectedAudioOption == option {
                                        Image(systemName: "checkmark").foregroundStyle(MavieTheme.coral)
                                    }
                                }
                                .frame(minHeight: 44)
                            }
                        }
                    }
                }

                Section("Altyazılar") {
                    Button {
                        controller.selectSubtitle(nil)
                        saveCurrentTrackPreference()
                    } label: {
                        HStack {
                            Text("Altyazı Kapalı")
                            Spacer()
                            if controller.selectedSubtitleOption == nil {
                                Image(systemName: "checkmark").foregroundStyle(MavieTheme.coral)
                            }
                        }
                        .frame(minHeight: 44)
                    }
                    ForEach(controller.subtitleOptions, id: \.self) { option in
                        Button {
                            controller.selectSubtitle(option)
                            saveCurrentTrackPreference()
                        } label: {
                            HStack {
                                Text(option.displayName)
                                Spacer()
                                if controller.selectedSubtitleOption == option {
                                    Image(systemName: "checkmark").foregroundStyle(MavieTheme.coral)
                                }
                            }
                            .frame(minHeight: 44)
                        }
                    }
                }
            }
            .navigationTitle("Ses ve Altyazı")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Tamam") { showTrackSheet = false }
                }
            }
        }
        .preferredColorScheme(.dark)
    }

    private var keyboardShortcutLayer: some View {
        Group {
            Button("") { controller.togglePlayPause() }
                .keyboardShortcut(.space, modifiers: [])
            Button("") { controller.seek(by: -10) }
                .keyboardShortcut(.leftArrow, modifiers: [])
            Button("") { controller.seek(by: 10) }
                .keyboardShortcut(.rightArrow, modifiers: [])
            Button("") { closePlayer() }
                .keyboardShortcut(.escape, modifiers: [])
        }
        .frame(width: 0, height: 0)
        .opacity(0.001)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func toggleControlsVisibility() {
        if reduceMotion {
            showControls.toggle()
        } else {
            withAnimation(.spring(response: 0.28, dampingFraction: 0.82)) {
                showControls.toggle()
            }
        }
    }

    private func closePlayer() {
        persistProgress()
        store.flushProgressPersistence()
        controller.teardown()
        onClose()
    }

    private func saveCurrentTrackPreference() {
        let audioKey = controller.selectedAudioOption?.locale?.identifier
            ?? controller.selectedAudioOption?.extendedLanguageTag
            ?? "auto"
        let clientAudio = controller.selectedAudioOption?.displayName
        let subtitleKey: String
        let clientSubtitle: String?
        if let sub = controller.selectedSubtitleOption {
            subtitleKey = sub.locale?.identifier ?? sub.extendedLanguageTag ?? "auto"
            clientSubtitle = sub.displayName
        } else {
            subtitleKey = "off"
            clientSubtitle = nil
        }
        store.saveTrackPreference(
            itemId: currentItem.id,
            audio: audioKey,
            subtitle: subtitleKey,
            clientAudio: clientAudio,
            clientSubtitle: clientSubtitle
        )
    }

    private func startPlayback(for item: MediaItem) {
        do {
            let plan = try store.resolvePlaybackPlan(for: item)
            let savedPos = store.progress(for: item)?.positionSeconds ?? 0
            let resumeAt = (store.progress(for: item)?.completed == true) ? 0 : savedPos
            let trackPref = store.trackPreference(for: item.id)
            controller.load(plan: plan, resumeAt: resumeAt, trackPreference: trackPref)
        } catch {
            controller.errorMessage = MavieHTTPClient.redactSensitiveURLs(in: error.localizedDescription)
        }
    }

    private func persistProgress(forceCompleted: Bool = false) {
        if forceCompleted && currentItem.kind != .live {
            let dur = controller.duration > 0 ? controller.duration : max(1, controller.currentTime)
            store.saveProgress(
                itemId: currentItem.id,
                positionSeconds: dur,
                durationSeconds: dur,
                flush: true
            )
            return
        }
        guard PlaybackRecoveryState.shouldPersistProgress(
            duration: controller.duration,
            isLive: currentItem.kind == .live,
            hasCompletedInitialSeek: controller.hasCompletedInitialSeek,
            isScrubbing: isScrubbing
        ) else {
            return
        }
        store.saveProgress(
            itemId: currentItem.id,
            positionSeconds: controller.currentTime,
            durationSeconds: controller.duration
        )
    }

    private func formatClock(_ totalSeconds: Double) -> String {
        let clamped = max(0, Int(totalSeconds))
        let h = clamped / 3600
        let m = (clamped % 3600) / 60
        let s = clamped % 60
        if h > 0 {
            return String(format: "%d:%02d:%02d", h, m, s)
        }
        return String(format: "%02d:%02d", m, s)
    }

    private func formatAccessibleTime(_ totalSeconds: Double) -> String {
        let clamped = max(0, Int(totalSeconds))
        let h = clamped / 3600
        let m = (clamped % 3600) / 60
        let s = clamped % 60
        if h > 0 {
            return "\(h) saat \(m) dakika \(s) saniye"
        }
        if m > 0 {
            return "\(m) dakika \(s) saniye"
        }
        return "\(s) saniye"
    }
}
