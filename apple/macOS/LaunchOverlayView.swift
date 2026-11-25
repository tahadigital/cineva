import SwiftUI

@MainActor
public final class LaunchOverlayState: ObservableObject {
    @Published public var isVisible: Bool = true
    @Published public var webError: String? = nil

    public init(isVisible: Bool = true, webError: String? = nil) {
        self.isVisible = isVisible
        self.webError = webError
    }
}

public struct LaunchOverlayView: View {
    @ObservedObject public var manager: ServerProcessManager
    @ObservedObject public var overlayState: LaunchOverlayState
    public var onRetry: () -> Void
    public var onQuit: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulse = false

    private var shouldAnimate: Bool {
        overlayState.isVisible && !reduceMotion
    }

    public init(
        manager: ServerProcessManager,
        overlayState: LaunchOverlayState,
        onRetry: @escaping () -> Void,
        onQuit: @escaping () -> Void
    ) {
        self.manager = manager
        self.overlayState = overlayState
        self.onRetry = onRetry
        self.onQuit = onQuit
    }

    public var body: some View {
        ZStack {
            Rectangle()
                .fill(.ultraThinMaterial)
                .overlay(MavieTheme.cinemaBackdrop.opacity(0.86))
                .ignoresSafeArea()

            VStack(spacing: 24) {
                ZStack {
                    if !reduceMotion {
                        Circle()
                            .fill(MavieTheme.purple.opacity(0.18))
                            .frame(width: 132, height: 132)
                            .scaleEffect(shouldAnimate && pulse ? 1.12 : 0.94)
                            .animation(
                                shouldAnimate
                                    ? .easeInOut(duration: 1.6).repeatForever(autoreverses: true)
                                    : .linear(duration: 0.1),
                                value: pulse
                            )
                    }
                    MavieLogoMark(size: 88, animateSweep: overlayState.isVisible)
                }

                VStack(spacing: 12) {
                    Text("Mavie")
                        .font(.system(size: 32, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)

                    if let webError = overlayState.webError {
                        VStack(spacing: 14) {
                            Label("Arayüz Yüklenemedi", systemImage: "exclamationmark.triangle.fill")
                                .font(.headline)
                                .foregroundStyle(MavieTheme.danger)

                            Text(webError)
                                .font(.callout)
                                .foregroundStyle(MavieTheme.muted)
                                .multilineTextAlignment(.center)
                                .frame(maxWidth: 460)

                            ViewThatFits(in: .horizontal) {
                                HStack(spacing: 12) {
                                    failedButtons
                                }
                                VStack(spacing: 10) {
                                    failedButtons
                                }
                            }
                        }
                        .padding(20)
                        .mavieCard(cornerRadius: 18)
                    } else {
                        switch manager.status {
                        case .idle, .starting:
                            HStack(spacing: 10) {
                                ProgressView()
                                    .controlSize(.small)
                                    .tint(MavieTheme.cyanDot)
                                Text(manager.healthDetails)
                                    .font(.subheadline)
                                    .foregroundStyle(MavieTheme.muted)
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 10)
                            .mavieGlassPill()

                        case .ready:
                            Label("Arayüz yükleniyor…", systemImage: "checkmark.circle.fill")
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(MavieTheme.success)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                                .mavieGlassPill()

                        case .failed(let message):
                            VStack(spacing: 14) {
                                Label("Sunucu Başlatılamadı", systemImage: "exclamationmark.triangle.fill")
                                    .font(.headline)
                                    .foregroundStyle(MavieTheme.danger)

                                Text(message)
                                    .font(.callout)
                                    .foregroundStyle(MavieTheme.muted)
                                    .multilineTextAlignment(.center)
                                    .frame(maxWidth: 460)

                                ViewThatFits(in: .horizontal) {
                                    HStack(spacing: 12) {
                                        failedButtons
                                    }
                                    VStack(spacing: 10) {
                                        failedButtons
                                    }
                                }
                            }
                            .padding(20)
                            .mavieCard(cornerRadius: 18)
                        }
                    }
                }
            }
            .padding(32)
        }
        .onAppear {
            pulse = shouldAnimate
        }
        .onDisappear {
            pulse = false
        }
        .onChange(of: shouldAnimate) { newValue in
            pulse = newValue
        }
    }

    @ViewBuilder
    private var failedButtons: some View {
        Button(action: onRetry) {
            Label("Tekrar Dene", systemImage: "arrow.clockwise")
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
        .buttonStyle(MaviePrimaryButtonStyle(compact: true))
        .accessibilityLabel("Sunucuyu Tekrar Başlat")

        Button {
            manager.openLogFile()
        } label: {
            Label("Günlüğü Aç", systemImage: "doc.text.magnifyingglass")
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
        .buttonStyle(MavieGhostButtonStyle(compact: true))
        .accessibilityLabel("Sunucu Günlüğünü Aç")

        Button(action: onQuit) {
            Label("Çık", systemImage: "xmark.circle")
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
        .buttonStyle(MavieGhostButtonStyle(compact: true))
        .accessibilityLabel("Mavie Uygulamasından Çık")
    }
}
