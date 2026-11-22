import AppKit
import SwiftUI

public struct PreferencesView: View {
    @ObservedObject public var manager: ServerProcessManager
    @State private var copiedAddress: String?
    public var onClose: () -> Void

    public init(manager: ServerProcessManager, onClose: @escaping () -> Void) {
        self.manager = manager
        self.onClose = onClose
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                MavieWordmark(subtitle: "macOS Sunucu & Tercihler", markSize: 34)
                Spacer()
                Button(action: onClose) {
                    Label("Kapat", systemImage: "xmark")
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .accessibilityLabel("Tercihler Penceresini Kapat")
            }

            Divider().overlay(MavieTheme.border)

            VStack(alignment: .leading, spacing: 10) {
                Text("Yerel Medya Sunucusu")
                    .font(.headline)
                    .foregroundStyle(.white)

                HStack {
                    Label(manager.healthDetails, systemImage: manager.status.isReady ? "checkmark.seal.fill" : "bolt.horizontal.circle")
                        .foregroundStyle(manager.status.isReady ? MavieTheme.success : MavieTheme.amber)
                    Spacer()
                    Text("Port \(manager.port)")
                        .font(.caption.monospaced())
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .mavieGlassPill()
                        .foregroundStyle(.white)
                }

                if !manager.executableDescription.isEmpty {
                    Text("Çalışma Modu: \(manager.executableDescription)")
                        .font(.caption)
                        .foregroundStyle(MavieTheme.muted)
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("Yerel Ağ (LAN) Eşleştirme Adresleri")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(MavieTheme.muted)

                    ForEach(manager.lanURLs, id: \.self) { url in
                        HStack {
                            Text(url)
                                .font(.callout.monospaced())
                                .foregroundStyle(.white)
                                .lineLimit(1)
                                .textSelection(.enabled)
                            Spacer()
                            Button {
                                NSPasteboard.general.clearContents()
                                NSPasteboard.general.setString(url, forType: .string)
                                copiedAddress = url
                            } label: {
                                Label(copiedAddress == url ? "Kopyalandı" : "Kopyala", systemImage: copiedAddress == url ? "checkmark" : "doc.on.doc")
                                    .lineLimit(1)
                                    .fixedSize(horizontal: true, vertical: false)
                            }
                            .buttonStyle(MavieGhostButtonStyle(compact: true))
                            .accessibilityLabel("\(url) adresini kopyala")
                        }
                    }
                }
            }
            .padding(14)
            .mavieCard()

            VStack(alignment: .leading, spacing: 10) {
                Text("Yerel Depolama & Günlük")
                    .font(.headline)
                    .foregroundStyle(.white)

                Text("Veri Klasörü: \(manager.dataDir.path)")
                    .font(.caption)
                    .foregroundStyle(MavieTheme.muted)
                    .lineLimit(2)

                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 10) {
                        storageActionButtons
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        storageActionButtons
                    }
                }

                Text("Mavie tamamen ücretsizdir ve hesap gerektirmez. Tüm kütüphane verileriniz yalnızca bu Mac üzerinde saklanır.")
                    .font(.caption)
                    .foregroundStyle(MavieTheme.muted)
            }
            .padding(14)
            .mavieCard()
        }
        .padding(.horizontal, 20)
        .padding(.bottom, 20)
        .padding(.top, 34)
        .frame(minWidth: 600, idealWidth: 620, maxWidth: 640)
        .background(
            ZStack {
                Rectangle().fill(.ultraThinMaterial)
                MavieTheme.cinemaBackdrop.opacity(0.68)
            }
        )
        .preferredColorScheme(.dark)
    }

    @ViewBuilder
    private var storageActionButtons: some View {
        Button {
            manager.openDataDirectory()
        } label: {
            Label("Veri Klasörünü Aç", systemImage: "folder")
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
        .buttonStyle(MavieGhostButtonStyle(compact: true))
        .accessibilityLabel("Veri Klasörünü Finder ile Aç")

        Button {
            manager.openLogFile()
        } label: {
            Label("Günlüğü Aç", systemImage: "doc.text")
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
        .buttonStyle(MavieGhostButtonStyle(compact: true))
        .accessibilityLabel("Sunucu Günlüğünü Aç")

        Button {
            manager.restart()
        } label: {
            Label("Sunucuyu Yeniden Başlat", systemImage: "arrow.clockwise")
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
        .buttonStyle(MaviePrimaryButtonStyle(compact: true))
        .accessibilityLabel("Yerel Sunucuyu Yeniden Başlat")
    }
}
