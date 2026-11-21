import SwiftUI

public struct HomeView: View {
    @ObservedObject public var store: LibraryStore
    public var onPlay: (MediaItem, MediaDetail?) -> Void
    public var onOpenTab: (MavieTab) -> Void

    @State private var surpriseSeriesItem: MediaItem?
    @State private var showSurpriseSeriesDetail = false

    public init(
        store: LibraryStore,
        onPlay: @escaping (MediaItem, MediaDetail?) -> Void,
        onOpenTab: @escaping (MavieTab) -> Void
    ) {
        self.store = store
        self.onPlay = onPlay
        self.onOpenTab = onOpenTab
    }

    private var spotlightItem: MediaItem? {
        store.discoveryResult.showcase.first ?? store.continueWatchingItems.first ?? store.recentMovies.first ?? store.items.first
    }

    public var body: some View {
        let discovery = store.discoveryResult
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    headerBar

                    if let hero = spotlightItem {
                        heroSpotlight(item: hero)
                    } else {
                        MavieEmptyStateCard(
                            systemImage: "sparkles.tv",
                            title: "Kütüphaneniz Henüz Boş",
                            message: "Açık Sinema demo filmleriyle hemen başlayın veya M3U / Xtream kaynağınızı ekleyin.",
                            actionTitle: "Açık Sinema ile Hemen Dene (Demo)"
                        ) {
                            store.loadDemoCatalog()
                        }
                    }

                    if !store.continueWatchingItems.isEmpty {
                        carouselSection(title: "İzlemeye Devam Et", subtitle: "", items: Array(store.continueWatchingItems.prefix(12)))
                    }

                    ForEach(discovery.shelves) { shelf in
                        carouselSection(title: shelf.title, subtitle: shelf.subtitle, items: shelf.items)
                    }

                    if !store.favoriteItems.isEmpty {
                        carouselSection(title: "Favorilerim", subtitle: "", items: Array(store.favoriteItems.prefix(12)))
                    }

                    if !store.recentMovies.isEmpty {
                        carouselSection(title: "Filmler", subtitle: "", items: Array(store.recentMovies.prefix(12)))
                    }

                    if !store.recentSeries.isEmpty {
                        carouselSection(title: "Diziler", subtitle: "", items: Array(store.recentSeries.prefix(12)))
                    }

                    if !discovery.shelves.isEmpty {
                        Text("Keşif: Cinemeta ve Netflix Türkiye Top 10 listeleri yerel kütüphanen ve izleme geçmişinle eşleştirilir.")
                            .font(.caption2)
                            .foregroundStyle(MavieTheme.muted)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
            }
            .background(MavieTheme.cinemaBackdrop.ignoresSafeArea())
            .navigationTitle("Ana Sayfa")
            .navigationBarTitleDisplayMode(.inline)
            .task(id: store.sourceMode) {
                await store.refreshDiscoveryIfNeeded()
            }
            .navigationDestination(isPresented: $showSurpriseSeriesDetail) {
                if let seriesItem = surpriseSeriesItem {
                    DetailView(store: store, item: seriesItem, onPlay: onPlay)
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    MavieWordmark(markSize: 28)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        if let pick = store.surpriseItem() {
                            if pick.kind == .series {
                                surpriseSeriesItem = pick
                                showSurpriseSeriesDetail = true
                            } else {
                                onPlay(pick, nil)
                            }
                        }
                    } label: {
                        Label("Sürpriz Yap", systemImage: "shuffle")
                    }
                    .frame(minWidth: 44, minHeight: 44)
                    .accessibilityLabel("Rastgele Bir İçerik Oynat")
                }
            }
        }
    }

    private var headerBar: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(store.account.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                Text("\(store.items.count) içerik hazır · \(store.sourceMode.displayTitle)")
                    .font(.caption)
                    .foregroundStyle(MavieTheme.muted)
            }
            Spacer()
            if store.sourceMode != .demo {
                Button {
                    store.loadDemoCatalog()
                } label: {
                    Label("Demo Aç", systemImage: "film.fill")
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .accessibilityLabel("Açık Sinema Demo Kataloğunu Yükle")
            }
        }
        .padding(14)
        .mavieCard()
    }

    private func heroSpotlight(item: MediaItem) -> some View {
        ZStack(alignment: .bottomLeading) {
            Group {
                if let url = URL(string: item.backdrop.isEmpty ? item.poster : item.backdrop),
                   !(item.backdrop.isEmpty && item.poster.isEmpty) {
                    AsyncImage(url: url) { phase in
                        if case .success(let image) = phase {
                            image.resizable().scaledToFill()
                        } else {
                            LinearGradient(colors: [MavieTheme.panelElevated, MavieTheme.bgDeep], startPoint: .top, endPoint: .bottom)
                        }
                    }
                } else {
                    LinearGradient(colors: [MavieTheme.panelElevated, MavieTheme.bgDeep], startPoint: .top, endPoint: .bottom)
                }
            }
            .frame(height: 260)
            .frame(maxWidth: .infinity)
            .clipped()

            LinearGradient(
                colors: [.clear, MavieTheme.bgDeep.opacity(0.82), MavieTheme.bgDeep],
                startPoint: .top,
                endPoint: .bottom
            )

            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Text(item.categoryName.isEmpty ? item.kind.displayTitle : item.categoryName)
                        .font(.caption.weight(.bold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(MavieTheme.coral.opacity(0.85), in: Capsule())
                        .foregroundStyle(.white)
                    if !item.year.isEmpty {
                        Text(item.year)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(MavieTheme.muted)
                    }
                    if item.rating > 0 {
                        Label(String(format: "%.1f", item.rating), systemImage: "star.fill")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(MavieTheme.amber)
                    }
                }

                Text(item.name)
                    .font(.title2.weight(.bold))
                    .foregroundStyle(.white)
                    .lineLimit(2)

                if !item.plot.isEmpty {
                    Text(item.plot)
                        .font(.caption)
                        .foregroundStyle(MavieTheme.muted)
                        .lineLimit(2)
                }

                HStack(spacing: 12) {
                    if item.kind == .series {
                        NavigationLink {
                            DetailView(store: store, item: item, onPlay: onPlay)
                        } label: {
                            Label("Bölümleri Seç", systemImage: "play.fill")
                        }
                        .buttonStyle(MaviePrimaryButtonStyle(compact: true))
                        .accessibilityLabel("\(item.name) bölümlerini aç")
                    } else {
                        Button {
                            onPlay(item, nil)
                        } label: {
                            Label(store.progress(for: item) != nil ? "Devam Et" : "Hemen Oynat", systemImage: "play.fill")
                        }
                        .buttonStyle(MaviePrimaryButtonStyle(compact: true))
                        .accessibilityLabel("\(item.name) içeriğini oynat")
                    }

                    NavigationLink {
                        DetailView(store: store, item: item, onPlay: onPlay)
                    } label: {
                        Label("Detaylar", systemImage: "info.circle")
                    }
                    .buttonStyle(MavieGhostButtonStyle(compact: true))
                    .accessibilityLabel("\(item.name) detaylarını aç")
                }
            }
            .padding(18)
        }
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .strokeBorder(MavieTheme.border, lineWidth: 1)
        )
    }

    private func carouselSection(title: String, subtitle: String = "", items: [MediaItem]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.title3.weight(.bold))
                    .foregroundStyle(.white)
                if !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(MavieTheme.muted)
                }
            }

            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: 14) {
                    ForEach(items) { item in
                        NavigationLink {
                            DetailView(store: store, item: item, onPlay: onPlay)
                        } label: {
                            MediaPosterCard(
                                item: item,
                                progress: store.progress(for: item),
                                isFavorite: store.isFavorite(item),
                                onToggleFavorite: { store.toggleFavorite(item) }
                            )
                            .frame(width: 162)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}
