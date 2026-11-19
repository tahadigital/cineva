import SwiftUI

public struct HomeView: View {
    @ObservedObject public var store: LibraryStore
    public var onPlay: (MediaItem, MediaDetail?) -> Void
    public var onOpenTab: (VrelioTab) -> Void

    @State private var surpriseSeriesItem: MediaItem?
    @State private var showSurpriseSeriesDetail = false

    public init(
        store: LibraryStore,
        onPlay: @escaping (MediaItem, MediaDetail?) -> Void,
        onOpenTab: @escaping (VrelioTab) -> Void
    ) {
        self.store = store
        self.onPlay = onPlay
        self.onOpenTab = onOpenTab
    }

    private var spotlightItem: MediaItem? {
        store.continueWatchingItems.first ?? store.recentMovies.first ?? store.items.first
    }

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    headerBar

                    if let user = store.cloudUser, user.trialActive, let remaining = user.trialRemainingSummary() {
                        trialBanner(remaining: remaining)
                    }

                    if let hero = spotlightItem {
                        heroSpotlight(item: hero)
                    } else {
                        VrelioEmptyStateCard(
                            systemImage: "sparkles.tv",
                            title: "Kütüphaneniz Henüz Boş",
                            message: "Açık Sinema demo filmleriyle hemen başlayın veya M3U / Xtream kaynağınızı ekleyin.",
                            actionTitle: "Açık Sinema ile Hemen Dene (Demo)"
                        ) {
                            store.loadDemoCatalog()
                        }
                    }

                    if !store.continueWatchingItems.isEmpty {
                        carouselSection(title: "İzlemeye Devam Et", items: Array(store.continueWatchingItems.prefix(12)))
                    }

                    if !store.favoriteItems.isEmpty {
                        carouselSection(title: "Favorilerim", items: Array(store.favoriteItems.prefix(12)))
                    }

                    if !store.recentMovies.isEmpty {
                        carouselSection(title: "Filmler", items: Array(store.recentMovies.prefix(12)))
                    }

                    if !store.recentSeries.isEmpty {
                        carouselSection(title: "Diziler", items: Array(store.recentSeries.prefix(12)))
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
            }
            .background(VrelioTheme.cinemaBackdrop.ignoresSafeArea())
            .navigationTitle("Ana Sayfa")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(isPresented: $showSurpriseSeriesDetail) {
                if let seriesItem = surpriseSeriesItem {
                    DetailView(store: store, item: seriesItem, onPlay: onPlay)
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    VrelioWordmark(markSize: 28)
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
                    .foregroundStyle(VrelioTheme.muted)
            }
            Spacer()
            if store.sourceMode != .demo {
                Button {
                    store.loadDemoCatalog()
                } label: {
                    Label("Demo Aç", systemImage: "film.fill")
                }
                .buttonStyle(VrelioGhostButtonStyle(compact: true))
                .accessibilityLabel("Açık Sinema Demo Kataloğunu Yükle")
            }
        }
        .padding(14)
        .vrelioCard()
    }

    private func trialBanner(remaining: String) -> some View {
        Button {
            onOpenTab(.cloud)
        } label: {
            HStack(spacing: 12) {
                Image(systemName: "crown.fill")
                    .font(.title3)
                    .foregroundStyle(VrelioTheme.amber)
                VStack(alignment: .leading, spacing: 2) {
                    Text("3 Günlük Vrelio Pro Deneme Aktif")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.white)
                    Text("Kalan süre: \(remaining) · Bulut Eşitleme ve 5 Cihaz açık")
                        .font(.caption)
                        .foregroundStyle(VrelioTheme.muted)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .foregroundStyle(VrelioTheme.muted)
            }
            .padding(14)
            .frame(minHeight: 54)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(VrelioTheme.coral.opacity(0.16))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .strokeBorder(VrelioTheme.amber.opacity(0.45), lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Pro deneme durumu: \(remaining)")
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
                            LinearGradient(colors: [VrelioTheme.panelElevated, VrelioTheme.bgDeep], startPoint: .top, endPoint: .bottom)
                        }
                    }
                } else {
                    LinearGradient(colors: [VrelioTheme.panelElevated, VrelioTheme.bgDeep], startPoint: .top, endPoint: .bottom)
                }
            }
            .frame(height: 260)
            .frame(maxWidth: .infinity)
            .clipped()

            LinearGradient(
                colors: [.clear, VrelioTheme.bgDeep.opacity(0.82), VrelioTheme.bgDeep],
                startPoint: .top,
                endPoint: .bottom
            )

            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Text(item.categoryName.isEmpty ? item.kind.displayTitle : item.categoryName)
                        .font(.caption.weight(.bold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(VrelioTheme.coral.opacity(0.85), in: Capsule())
                        .foregroundStyle(.white)
                    if !item.year.isEmpty {
                        Text(item.year)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(VrelioTheme.muted)
                    }
                    if item.rating > 0 {
                        Label(String(format: "%.1f", item.rating), systemImage: "star.fill")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(VrelioTheme.amber)
                    }
                }

                Text(item.name)
                    .font(.title2.weight(.bold))
                    .foregroundStyle(.white)
                    .lineLimit(2)

                if !item.plot.isEmpty {
                    Text(item.plot)
                        .font(.caption)
                        .foregroundStyle(VrelioTheme.muted)
                        .lineLimit(2)
                }

                HStack(spacing: 12) {
                    if item.kind == .series {
                        NavigationLink {
                            DetailView(store: store, item: item, onPlay: onPlay)
                        } label: {
                            Label("Bölümleri Seç", systemImage: "play.fill")
                        }
                        .buttonStyle(VrelioPrimaryButtonStyle(compact: true))
                        .accessibilityLabel("\(item.name) bölümlerini aç")
                    } else {
                        Button {
                            onPlay(item, nil)
                        } label: {
                            Label(store.progress(for: item) != nil ? "Devam Et" : "Hemen Oynat", systemImage: "play.fill")
                        }
                        .buttonStyle(VrelioPrimaryButtonStyle(compact: true))
                        .accessibilityLabel("\(item.name) içeriğini oynat")
                    }

                    NavigationLink {
                        DetailView(store: store, item: item, onPlay: onPlay)
                    } label: {
                        Label("Detaylar", systemImage: "info.circle")
                    }
                    .buttonStyle(VrelioGhostButtonStyle(compact: true))
                    .accessibilityLabel("\(item.name) detaylarını aç")
                }
            }
            .padding(18)
        }
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .strokeBorder(VrelioTheme.border, lineWidth: 1)
        )
    }

    private func carouselSection(title: String, items: [MediaItem]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.title3.weight(.bold))
                .foregroundStyle(.white)

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
