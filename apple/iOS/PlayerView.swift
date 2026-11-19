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

    let player = AVPlayer()
    var pipController: AVPictureInPictureController?
    private var timeObserver: Any?
    private var statusObservation: NSKeyValueObservation?
    private var rateObservation: NSKeyValueObservation?
    private var sleepTimerTask: Task<Void, Never>?

    func load(url: URL, resumeAt: Double) {
        teardownObserversOnly()
        errorMessage = nil
        isLoading = true
        currentTime = max(0, resumeAt)
        duration = 0

        let asset = AVURLAsset(url: url)
        let item = AVPlayerItem(asset: asset)

        statusObservation = item.observe(\.status, options: [.new, .initial]) { [weak self] observedItem, _ in
            Task { @MainActor [weak self] in
                guard let self else { return }
                switch observedItem.status {
                case .readyToPlay:
                    self.isLoading = false
                    let dur = observedItem.duration.seconds
                    if dur.isFinite && dur > 0 {
                        self.duration = dur
                    }
                    await self.loadMediaTracks(for: observedItem)
                case .failed:
                    self.isLoading = false
                    let rawMsg = observedItem.error?.localizedDescription ?? "Bilinmeyen oynatma hatası"
                    self.errorMessage = "Video oynatılamadı (\(rawMsg)). Ham .ts veya uyumsuz akışlarda yerel Vrelio masaüstü sunucusu üzerinden HLS olarak açmayı deneyin."
                case .unknown:
                    break
                @unknown default:
                    break
                }
            }
        }

        rateObservation = player.observe(\.rate, options: [.new, .initial]) { [weak self] p, _ in
            Task { @MainActor [weak self] in
                self?.isPlaying = p.rate > 0.05
            }
        }

        let interval = CMTime(seconds: 0.5, preferredTimescale: 600)
        timeObserver = player.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] cmTime in
            Task { @MainActor [weak self] in
                guard let self else { return }
                let sec = cmTime.seconds
                if sec.isFinite && sec >= 0 {
                    self.currentTime = sec
                }
                if let dur = self.player.currentItem?.duration.seconds, dur.isFinite && dur > 0 {
                    self.duration = dur
                }
            }
        }

        player.replaceCurrentItem(with: item)
        if resumeAt > 3 {
            let target = CMTime(seconds: resumeAt, preferredTimescale: 600)
            player.seek(to: target)
        }
        player.play()
        player.rate = playbackRate
    }

    func togglePlayPause() {
        if player.rate > 0.05 {
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

    func seek(to seconds: Double) {
        let clamped = max(0, seconds)
        currentTime = clamped
        player.seek(to: CMTime(seconds: clamped, preferredTimescale: 600))
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
                }
            }
        }
    }

    func selectAudio(_ option: AVMediaSelectionOption?) {
        guard let item = player.currentItem,
              let group = item.asset.mediaSelectionGroup(forMediaCharacteristic: .audible) else { return }
        item.select(option, in: group)
        selectedAudioOption = option
    }

    func selectSubtitle(_ option: AVMediaSelectionOption?) {
        guard let item = player.currentItem,
              let group = item.asset.mediaSelectionGroup(forMediaCharacteristic: .legible) else { return }
        item.select(option, in: group)
        selectedSubtitleOption = option
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
        sleepTimerTask?.cancel()
        sleepTimerTask = nil
        player.pause()
        teardownObserversOnly()
        player.replaceCurrentItem(with: nil)
    }

    private func teardownObserversOnly() {
        if let observer = timeObserver {
            player.removeTimeObserver(observer)
            timeObserver = nil
        }
        statusObservation?.invalidate()
        statusObservation = nil
        rateObservation?.invalidate()
        rateObservation = nil
    }

    private func loadMediaTracks(for item: AVPlayerItem) async {
        let asset = item.asset
        if let audible = try? await asset.loadMediaSelectionGroup(for: .audible) {
            audioOptions = audible.options
            selectedAudioOption = item.currentMediaSelection.selectedMediaOption(in: audible)
        }
        if let legible = try? await asset.loadMediaSelectionGroup(for: .legible) {
            subtitleOptions = legible.options
            selectedSubtitleOption = item.currentMediaSelection.selectedMediaOption(in: legible)
        }
    }
}

private final class PlayerLayerHostView: UIView {
    override class var layerClass: AnyClass { AVPlayerLayer.self }
    var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
}

private struct VrelioVideoSurfaceView: UIViewRepresentable {
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

private struct VrelioAirPlayRoutePicker: UIViewRepresentable {
    func makeUIView(context: Context) -> AVRoutePickerView {
        let picker = AVRoutePickerView()
        picker.tintColor = .white
        picker.activeTintColor = UIColor(red: 1.0, green: 75.0 / 255.0, blue: 69.0 / 255.0, alpha: 1.0)
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

            VrelioVideoSurfaceView(controller: controller)
                .ignoresSafeArea()
                .onTapGesture {
                    if reduceMotion {
                        showControls.toggle()
                    } else {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showControls.toggle()
                        }
                    }
                }

            if controller.isLoading && controller.errorMessage == nil {
                VStack(spacing: 12) {
                    ProgressView()
                        .controlSize(.large)
                        .tint(VrelioTheme.amber)
                    Text("Akış hazırlanıyor…")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.white)
                }
                .padding(20)
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16))
            }

            if let errorMessage = controller.errorMessage {
                VStack(spacing: 14) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.largeTitle)
                        .foregroundStyle(VrelioTheme.danger)
                    Text("Oynatma Hatası")
                        .font(.headline)
                        .foregroundStyle(.white)
                    Text(errorMessage)
                        .font(.subheadline)
                        .foregroundStyle(VrelioTheme.muted)
                        .multilineTextAlignment(.center)
                    HStack(spacing: 12) {
                        Button {
                            startPlayback(for: currentItem)
                        } label: {
                            Label("Tekrar Dene", systemImage: "arrow.clockwise")
                        }
                        .buttonStyle(VrelioPrimaryButtonStyle(compact: true))
                        .accessibilityLabel("Videoyu Tekrar Dene")

                        Button {
                            persistProgress()
                            controller.teardown()
                            onClose()
                        } label: {
                            Label("Kapat", systemImage: "xmark")
                        }
                        .buttonStyle(VrelioGhostButtonStyle(compact: true))
                        .accessibilityLabel("Oynatıcıyı Kapat")
                    }
                }
                .padding(24)
                .frame(maxWidth: 420)
                .vrelioCard()
                .padding(20)
            }

            if showControls && controller.errorMessage == nil {
                controlsOverlay
                    .transition(.opacity)
            }
        }
        .statusBarHidden(true)
        .onAppear {
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
                    persistProgress()
                    controller.teardown()
                    onClose()
                } label: {
                    Label("Kapat", systemImage: "xmark")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12)
                        .frame(minWidth: 44, minHeight: 44)
                        .background(.black.opacity(0.65), in: Capsule())
                }
                .accessibilityLabel("Oynatıcıyı Kapat")

                VStack(alignment: .leading, spacing: 2) {
                    Text(currentItem.name)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.white)
                        .lineLimit(1)
                    if let sleep = controller.sleepRemainingMinutes {
                        Text("Uyku zamanlayıcı: \(sleep) dk")
                            .font(.caption2)
                            .foregroundStyle(VrelioTheme.amber)
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
                            .background(.black.opacity(0.65), in: Capsule())
                    }
                    .accessibilityLabel("Resim İçinde Resim Modunu Aç veya Kapat")
                }

                VrelioAirPlayRoutePicker()
                    .frame(width: 44, height: 44)
                    .background(.black.opacity(0.65), in: Circle())
                    .accessibilityLabel("AirPlay Cihazı Seç")

                Button {
                    showTrackSheet = true
                } label: {
                    Label("Ses/Altyazı", systemImage: "captions.bubble")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 10)
                        .frame(minWidth: 44, minHeight: 44)
                        .background(.black.opacity(0.65), in: Capsule())
                }
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
                    .background(.black.opacity(0.55), in: Circle())
                }
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
                    .background(VrelioTheme.brandGradient, in: Circle())
                }
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
                    .background(.black.opacity(0.55), in: Circle())
                }
                .accessibilityLabel("10 Saniye İleri Sar")
            }

            Spacer()

            // Bottom scrubber & utility bar
            VStack(spacing: 10) {
                if controller.duration > 0 {
                    HStack(spacing: 10) {
                        Text(formatClock(controller.currentTime))
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.white)
                        Slider(
                            value: Binding(
                                get: { controller.currentTime },
                                set: { controller.seek(to: $0) }
                            ),
                            in: 0...max(1, controller.duration)
                        )
                        .tint(VrelioTheme.coral)
                        .accessibilityLabel("Oynatma İlerleme Çubuğu")
                        Text(formatClock(controller.duration))
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(VrelioTheme.muted)
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
                            .background(.black.opacity(0.65), in: Capsule())
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
                            .background(.black.opacity(0.65), in: Capsule())
                    }
                    .accessibilityLabel("Uyku Zamanlayıcısı")

                    Spacer()

                    if let nextEp = nextEpisode {
                        Button {
                            persistProgress()
                            currentItem = nextEp
                            startPlayback(for: nextEp)
                        } label: {
                            Label("Sonraki Bölüm", systemImage: "forward.end.fill")
                        }
                        .buttonStyle(VrelioPrimaryButtonStyle(compact: true))
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
                            .foregroundStyle(VrelioTheme.muted)
                    } else {
                        ForEach(controller.audioOptions, id: \.self) { option in
                            Button {
                                controller.selectAudio(option)
                            } label: {
                                HStack {
                                    Text(option.displayName)
                                    Spacer()
                                    if controller.selectedAudioOption == option {
                                        Image(systemName: "checkmark").foregroundStyle(VrelioTheme.coral)
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
                    } label: {
                        HStack {
                            Text("Altyazı Kapalı")
                            Spacer()
                            if controller.selectedSubtitleOption == nil {
                                Image(systemName: "checkmark").foregroundStyle(VrelioTheme.coral)
                            }
                        }
                        .frame(minHeight: 44)
                    }
                    ForEach(controller.subtitleOptions, id: \.self) { option in
                        Button {
                            controller.selectSubtitle(option)
                        } label: {
                            HStack {
                                Text(option.displayName)
                                Spacer()
                                if controller.selectedSubtitleOption == option {
                                    Image(systemName: "checkmark").foregroundStyle(VrelioTheme.coral)
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

    private func startPlayback(for item: MediaItem) {
        do {
            let url = try store.resolvePlayableURL(for: item)
            let savedPos = store.progress(for: item)?.positionSeconds ?? 0
            let resumeAt = (store.progress(for: item)?.completed == true) ? 0 : savedPos
            controller.load(url: url, resumeAt: resumeAt)
        } catch {
            controller.errorMessage = error.localizedDescription
        }
    }

    private func persistProgress() {
        guard controller.duration > 0 else { return }
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
}
