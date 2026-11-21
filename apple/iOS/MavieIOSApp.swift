import AVFoundation
import SwiftUI

public enum MavieTab: String, CaseIterable, Identifiable {
    case home
    case library
    case search
    case settings

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .home: return "Ana Sayfa"
        case .library: return "Kütüphane"
        case .search: return "Ara"
        case .settings: return "Ayarlar"
        }
    }

    public var systemImage: String {
        switch self {
        case .home: return "house.fill"
        case .library: return "square.grid.2x2.fill"
        case .search: return "magnifyingglass"
        case .settings: return "gearshape.fill"
        }
    }
}

public struct PlayRequest: Identifiable, Hashable {
    public var id: String { item.id }
    public var item: MediaItem
    public var detail: MediaDetail?

    public init(item: MediaItem, detail: MediaDetail? = nil) {
        self.item = item
        self.detail = detail
    }
}

@main
struct MavieIOSApp: App {
    @StateObject private var store = LibraryStore()
    @State private var showLaunch = true
    @State private var selectedTab: MavieTab = .home
    @State private var activePlayRequest: PlayRequest?

    init() {
        configureAudioSession()
    }

    var body: some Scene {
        WindowGroup {
            ZStack {
                MavieRootShell(
                    store: store,
                    selectedTab: $selectedTab,
                    onPlay: { item, detail in
                        activePlayRequest = PlayRequest(item: item, detail: detail)
                    }
                )
                .preferredColorScheme(.dark)

                if showLaunch {
                    MavieLaunchView {
                        withAnimation(.easeOut(duration: 0.35)) {
                            showLaunch = false
                        }
                    }
                    .transition(.opacity)
                    .zIndex(10)
                }
            }
            .fullScreenCover(item: $activePlayRequest) { req in
                PlayerView(
                    store: store,
                    initialItem: req.item,
                    detail: req.detail,
                    onClose: { activePlayRequest = nil }
                )
            }
        }
    }

    private func configureAudioSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .moviePlayback, options: [.allowAirPlay])
        try? session.setActive(true)
    }
}

private struct MavieRootShell: View {
    @ObservedObject var store: LibraryStore
    @Binding var selectedTab: MavieTab
    var onPlay: (MediaItem, MediaDetail?) -> Void

    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    var body: some View {
        Group {
            if horizontalSizeClass == .regular {
                NavigationSplitView {
                    List(MavieTab.allCases, selection: Binding<MavieTab?>(
                        get: { selectedTab },
                        set: { if let val = $0 { selectedTab = val } }
                    )) { tab in
                        Label(tab.title, systemImage: tab.systemImage)
                            .font(.body.weight(.medium))
                            .frame(minHeight: 44)
                            .tag(tab)
                            .accessibilityLabel(tab.title)
                    }
                    .scrollContentBackground(.hidden)
                    .background(MavieTheme.bgDeep)
                    .navigationTitle("Mavie")
                } detail: {
                    tabContent(for: selectedTab)
                }
                .tint(MavieTheme.coral)
            } else {
                TabView(selection: $selectedTab) {
                    ForEach(MavieTab.allCases) { tab in
                        tabContent(for: tab)
                            .tabItem {
                                Label(tab.title, systemImage: tab.systemImage)
                            }
                            .tag(tab)
                    }
                }
                .tint(MavieTheme.coral)
            }
        }
        .background(MavieTheme.bg.ignoresSafeArea())
    }

    @ViewBuilder
    private func tabContent(for tab: MavieTab) -> some View {
        switch tab {
        case .home:
            HomeView(store: store, onPlay: onPlay, onOpenTab: { selectedTab = $0 })
        case .library:
            LibraryView(store: store, onPlay: onPlay)
        case .search:
            SearchView(store: store, onPlay: onPlay)
        case .settings:
            SettingsView(store: store)
        }
    }
}

private struct MavieLaunchView: View {
    var onFinished: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var scale: CGFloat = 0.88
    @State private var opacity: Double = 0.0

    var body: some View {
        ZStack {
            MavieTheme.cinemaBackdrop
                .ignoresSafeArea()

            VStack(spacing: 18) {
                MavieLogoMark(size: 96, animateSweep: true)
                    .scaleEffect(scale)
                    .opacity(opacity)

                VStack(spacing: 6) {
                    Text("Mavie")
                        .font(.system(size: 36, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                    Text("Kişisel Medya & IPTV Merkezi")
                        .font(.subheadline)
                        .foregroundStyle(MavieTheme.muted)
                }
                .opacity(opacity)
            }
        }
        .onAppear {
            if reduceMotion {
                scale = 1.0
                opacity = 1.0
            } else {
                withAnimation(.spring(response: 0.55, dampingFraction: 0.78)) {
                    scale = 1.0
                    opacity = 1.0
                }
            }
            Task { @MainActor in
                try? await Task.sleep(nanoseconds: reduceMotion ? 350_000_000 : 1_050_000_000)
                onFinished()
            }
        }
    }
}

public struct MavieEmptyStateCard: View {
    public var systemImage: String
    public var title: String
    public var message: String
    public var actionTitle: String?
    public var action: (() -> Void)?

    public init(
        systemImage: String,
        title: String,
        message: String,
        actionTitle: String? = nil,
        action: (() -> Void)? = nil
    ) {
        self.systemImage = systemImage
        self.title = title
        self.message = message
        self.actionTitle = actionTitle
        self.action = action
    }

    public var body: some View {
        VStack(spacing: 14) {
            Image(systemName: systemImage)
                .font(.system(size: 36, weight: .semibold))
                .foregroundStyle(MavieTheme.amber)
            Text(title)
                .font(.headline)
                .foregroundStyle(.white)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(MavieTheme.muted)
                .multilineTextAlignment(.center)
            if let actionTitle, let action {
                Button(action: action) {
                    Text(actionTitle)
                }
                .buttonStyle(MaviePrimaryButtonStyle(compact: true))
                .accessibilityLabel(actionTitle)
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .mavieCard()
    }
}

public struct MediaPosterCard: View {
    public var item: MediaItem
    public var progress: WatchProgress?
    public var isFavorite: Bool
    public var onToggleFavorite: () -> Void

    public init(
        item: MediaItem,
        progress: WatchProgress?,
        isFavorite: Bool,
        onToggleFavorite: @escaping () -> Void
    ) {
        self.item = item
        self.progress = progress
        self.isFavorite = isFavorite
        self.onToggleFavorite = onToggleFavorite
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ZStack(alignment: .topTrailing) {
                posterArtwork
                    .frame(height: 200)
                    .frame(maxWidth: .infinity)
                    .clipped()
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

                Button(action: onToggleFavorite) {
                    Image(systemName: isFavorite ? "heart.fill" : "heart")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(isFavorite ? MavieTheme.coral : .white)
                        .frame(width: 44, height: 44)
                        .background(.ultraThinMaterial, in: Circle())
                }
                .padding(6)
                .accessibilityLabel(isFavorite ? "\(item.name) favorilerden çıkar" : "\(item.name) favorilere ekle")
            }

            if let progress, progress.durationSeconds > 0 {
                ProgressView(value: progress.progressFraction)
                    .tint(MavieTheme.coral)
            }

            Text(item.name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .lineLimit(2)

            HStack(spacing: 6) {
                if !item.categoryName.isEmpty {
                    Text(item.categoryName)
                        .lineLimit(1)
                } else {
                    Text(item.kind.displayTitle)
                }
                if item.rating > 0 {
                    Spacer(minLength: 4)
                    Label(String(format: "%.1f", item.rating), systemImage: "star.fill")
                        .foregroundStyle(MavieTheme.amber)
                }
            }
            .font(.caption)
            .foregroundStyle(MavieTheme.muted)
        }
        .padding(10)
        .mavieCard(cornerRadius: 16)
    }

    @ViewBuilder
    private var posterArtwork: some View {
        if let url = URL(string: item.poster), !item.poster.isEmpty {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image.resizable().scaledToFill()
                default:
                    fallbackArtwork
                }
            }
        } else {
            fallbackArtwork
        }
    }

    private var fallbackArtwork: some View {
        ZStack {
            LinearGradient(
                colors: [MavieTheme.panelElevated, MavieTheme.bgDeep],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Image(systemName: item.kind == .live ? "dot.radiowaves.left.and.right" : "film.stack")
                .font(.system(size: 32))
                .foregroundStyle(MavieTheme.amber.opacity(0.85))
        }
    }
}
