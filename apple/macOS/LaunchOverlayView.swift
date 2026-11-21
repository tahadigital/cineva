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
            MavieTheme.cinemaBackdrop
                .ignoresSafeArea()

            VStack(spacing: 24) {
                ZStack {
                    if !reduceMotion {
                        Circle()
                            .fill(MavieTheme.coral.opacity(0.16))
                            .frame(width: 128, height: 128)
                            .scaleEffect(pulse ? 1.12 : 0.94)
                            .animation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true), value: pulse)
                    }
                    MavieLogoMark(size: 88, animateSweep: true)
                }

                VStack(spacing: 8) {
                    Text("Mavie")
                        .font(.system(size: 32, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)

                    switch manager.status {
                    case .idle, .starting:
                        Text(manager.healthDetails)
                            .font(.subheadline)
                            .foregroundStyle(MavieTheme.muted)
                        ProgressView()
                            .controlSize(.regular)
                            .tint(MavieTheme.amber)
                            .padding(.top, 4)

                    case .ready:
                        Label("Arayüz yükleniyor…", systemImage: "checkmark.circle.fill")
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(MavieTheme.success)

                    case .failed(let message):
                        VStack(spacing: 14) {
                            Label("Sunucu Başlatılamadı", systemImage: "exclamationmark.triangle.fill")
                                .font(.headline)
                                .foregroundStyle(MavieTheme.danger)

                            Text(message)
                                .font(.callout)
                                .foregroundStyle(MavieTheme.muted)
                                .multilineTextAlignment(.center)
                                .frame(maxWidth: 420)

                            HStack(spacing: 12) {
                                Button(action: onRetry) {
                                    Label("Tekrar Dene", systemImage: "arrow.clockwise")
                                }
                                .buttonStyle(MaviePrimaryButtonStyle(compact: true))
                                .accessibilityLabel("Sunucuyu Tekrar Başlat")

                                Button {
                                    manager.openLogFile()
                                } label: {
                                    Label("Günlüğü Aç", systemImage: "doc.text.magnifyingglass")
                                }
                                .buttonStyle(MavieGhostButtonStyle(compact: true))
                                .accessibilityLabel("Sunucu Günlüğünü Aç")

                                Button(action: onQuit) {
                                    Label("Çık", systemImage: "xmark.circle")
                                }
                                .buttonStyle(MavieGhostButtonStyle(compact: true))
                                .accessibilityLabel("Mavie Uygulamasından Çık")
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
}
