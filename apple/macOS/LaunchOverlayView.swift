import SwiftUI

public struct LaunchOverlayView: View {
    @ObservedObject public var manager: ServerProcessManager
    public var onRetry: () -> Void
    public var onQuit: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulse = false

    public init(manager: ServerProcessManager, onRetry: @escaping () -> Void, onQuit: @escaping () -> Void) {
        self.manager = manager
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
                            .scaleEffect(pulse ? 1.12 : 0.94)
                            .animation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true), value: pulse)
                    }
                    MavieLogoMark(size: 88, animateSweep: true)
                }

                VStack(spacing: 12) {
                    Text("Mavie")
                        .font(.system(size: 32, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)

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
            .padding(32)
        }
        .onAppear { pulse = true }
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
