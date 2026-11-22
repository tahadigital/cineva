import SwiftUI

public struct DetailView: View {
    @ObservedObject public var store: LibraryStore
    public var item: MediaItem
    public var onPlay: (MediaItem, MediaDetail?) -> Void

    @State private var detail: MediaDetail?
    @State private var selectedSeasonNumber: Int = 1
    @State private var showPlaylistSheet = false
    @State private var newPlaylistName = ""
    @State private var isLoadingDetail = false

    public init(
        store: LibraryStore,
        item: MediaItem,
        onPlay: @escaping (MediaItem, MediaDetail?) -> Void
    ) {
        self.store = store
        self.item = item
        self.onPlay = onPlay
    }

    private var activeItem: MediaItem {
        detail?.item ?? item
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                headerArtwork

                VStack(alignment: .leading, spacing: 12) {
                    Text(activeItem.name)
                        .font(.title2.weight(.bold))
                        .foregroundStyle(.white)

                    HStack(spacing: 10) {
                        if !activeItem.year.isEmpty {
                            badge(activeItem.year)
                        }
                        if activeItem.rating > 0 {
                            Label(String(format: "%.1f", activeItem.rating), systemImage: "star.fill")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(MavieTheme.amber)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .mavieGlassPill()
                        }
                        if activeItem.durationSeconds > 0 {
                            badge("\(Int(activeItem.durationSeconds / 60)) dk")
                        }
                        if !activeItem.extensionName.isEmpty {
                            badge(activeItem.extensionName.uppercased())
                        }
                    }

                    actionButtons

                    if let genres = detail?.genres, !genres.isEmpty {
                        metadataRow(label: "Tür", value: genres)
                    } else if !activeItem.genres.isEmpty {
                        metadataRow(label: "Tür", value: activeItem.genres)
                    }

                    if let director = detail?.director, !director.isEmpty {
                        metadataRow(label: "Yönetmen", value: director)
                    }
                    if let cast = detail?.cast, !cast.isEmpty {
                        metadataRow(label: "Oyuncular", value: cast)
                    }

                    if !activeItem.plot.isEmpty {
                        Text(activeItem.plot)
                            .font(.body)
                            .foregroundStyle(MavieTheme.muted)
                            .padding(.top, 4)
                    }

                    if activeItem.kind == .series {
                        seasonsSection
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
            }
        }
        .background(MavieTheme.cinemaBackdrop.ignoresSafeArea())
        .navigationTitle(activeItem.kind.displayTitle)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            isLoadingDetail = true
            let loaded = await store.loadDetail(for: item)
            detail = loaded
            if let firstSeason = loaded.seasons.first?.number {
                selectedSeasonNumber = firstSeason
            }
            isLoadingDetail = false
        }
        .sheet(isPresented: $showPlaylistSheet) {
            playlistPickerSheet
        }
    }

    private var headerArtwork: some View {
        ZStack(alignment: .bottomLeading) {
            let imageUrl = activeItem.backdrop.isEmpty ? activeItem.poster : activeItem.backdrop
            if let url = URL(string: imageUrl), !imageUrl.isEmpty {
                AsyncImage(url: url) { phase in
                    if case .success(let img) = phase {
                        img.resizable().scaledToFill()
                    } else {
                        MavieTheme.panelElevated
                    }
                }
            } else {
                MavieTheme.panelElevated
            }
            LinearGradient(
                colors: [.clear, MavieTheme.bgDeep],
                startPoint: .center,
                endPoint: .bottom
            )
        }
        .frame(height: 240)
        .frame(maxWidth: .infinity)
        .clipped()
    }

    private var actionButtons: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Button {
                    if activeItem.kind == .series {
                        if let firstEp = detail?.seasons.first(where: { $0.number == selectedSeasonNumber })?.episodes.first
                            ?? detail?.seasons.first?.episodes.first {
                            onPlay(firstEp, detail)
                        }
                    } else {
                        onPlay(activeItem, detail)
                    }
                } label: {
                    let hasProgress = store.progress(for: activeItem) != nil
                    Label(
                        activeItem.kind == .series ? "İlk Bölümü Oynat" : (hasProgress ? "İzlemeye Devam Et" : "Oynat"),
                        systemImage: "play.fill"
                    )
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(MaviePrimaryButtonStyle())
                .disabled(activeItem.kind == .series && (detail?.seasons.isEmpty ?? true))
                .accessibilityLabel("\(activeItem.name) oynat")
            }

            HStack(spacing: 10) {
                Button {
                    store.toggleFavorite(activeItem)
                } label: {
                    let fav = store.isFavorite(activeItem)
                    Label(fav ? "Favoriden Çıkar" : "Favoriye Ekle", systemImage: fav ? "heart.fill" : "heart")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .accessibilityLabel(store.isFavorite(activeItem) ? "Favorilerden çıkar" : "Favorilere ekle")

                Button {
                    showPlaylistSheet = true
                } label: {
                    Label("Listeye Ekle", systemImage: "text.badge.plus")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .accessibilityLabel("Çalma listesine ekle")
            }
        }
    }

    @ViewBuilder
    private var seasonsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Sezonlar ve Bölümler")
                .font(.headline)
                .foregroundStyle(.white)
                .padding(.top, 8)

            if isLoadingDetail {
                ProgressView("Bölümler yükleniyor…")
                    .tint(MavieTheme.amber)
            } else if let seasons = detail?.seasons, !seasons.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(seasons) { season in
                            Button {
                                selectedSeasonNumber = season.number
                            } label: {
                                Text(season.name)
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 14)
                                    .frame(minHeight: 44)
                                    .mavieGlassPill(selected: selectedSeasonNumber == season.number)
                            }
                            .buttonStyle(MavieInteractiveCardButtonStyle())
                            .accessibilityLabel(season.name)
                        }
                    }
                }

                if let activeSeason = seasons.first(where: { $0.number == selectedSeasonNumber }) ?? seasons.first {
                    ForEach(activeSeason.episodes) { ep in
                        Button {
                            onPlay(ep, detail)
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "play.circle.fill")
                                    .font(.title2)
                                    .foregroundStyle(MavieTheme.coral)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Bölüm \(ep.episode): \(ep.name)")
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(.white)
                                    if let p = store.progress(for: ep), p.durationSeconds > 0 {
                                        ProgressView(value: p.progressFraction)
                                            .tint(MavieTheme.amber)
                                    }
                                }
                                Spacer()
                            }
                            .padding(12)
                            .frame(minHeight: 54)
                            .mavieCard(cornerRadius: 12)
                        }
                        .buttonStyle(MavieInteractiveCardButtonStyle())
                        .accessibilityLabel("Bölüm \(ep.episode) \(ep.name) oynat")
                    }
                }
            } else {
                Text("Bu dizi için bölüm bilgisi bulunamadı.")
                    .font(.subheadline)
                    .foregroundStyle(MavieTheme.muted)
            }
        }
    }

    private var playlistPickerSheet: some View {
        NavigationStack {
            List {
                Section("Yeni Liste Oluştur") {
                    HStack {
                        TextField("Liste adı", text: $newPlaylistName)
                        Button("Ekle") {
                            store.createPlaylist(name: newPlaylistName)
                            newPlaylistName = ""
                        }
                        .frame(minHeight: 44)
                    }
                }
                Section("Mevcut Listeler") {
                    if store.playlists.isEmpty {
                        Text("Henüz liste yok.")
                            .foregroundStyle(MavieTheme.muted)
                    } else {
                        ForEach(store.playlists) { list in
                            Button {
                                store.addItem(activeItem, toPlaylist: list.id)
                                showPlaylistSheet = false
                            } label: {
                                HStack {
                                    Text(list.name)
                                    Spacer()
                                    if list.itemIds.contains(activeItem.id) {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundStyle(MavieTheme.success)
                                    }
                                }
                                .frame(minHeight: 44)
                            }
                        }
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(MavieTheme.cinemaBackdrop.ignoresSafeArea())
            .navigationTitle("Listeye Ekle")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Kapat") { showPlaylistSheet = false }
                }
            }
        }
        .preferredColorScheme(.dark)
    }

    private func badge(_ text: String) -> some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .mavieGlassPill()
    }

    private func metadataRow(label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption.weight(.bold))
                .foregroundStyle(MavieTheme.amber)
            Text(value)
                .font(.subheadline)
                .foregroundStyle(.white)
        }
    }
}
