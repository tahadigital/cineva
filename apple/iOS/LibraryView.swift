import SwiftUI

public enum LibrarySectionTab: String, CaseIterable, Identifiable {
    case all = "Tümü"
    case live = "Canlı"
    case vod = "Filmler"
    case series = "Diziler"
    case playlists = "Listeler"

    public var id: String { rawValue }
}

public enum LibrarySortOrder: String, CaseIterable, Identifiable {
    case defaultOrder = "Varsayılan"
    case alphabetical = "Ada Göre (A-Z)"
    case ratingDesc = "Puana Göre"
    case yearDesc = "Yıla Göre"

    public var id: String { rawValue }
}

public struct LibraryView: View {
    @ObservedObject public var store: LibraryStore
    public var onPlay: (MediaItem, MediaDetail?) -> Void

    @State private var section: LibrarySectionTab = .all
    @State private var selectedCategoryId: String = "all"
    @State private var sortOrder: LibrarySortOrder = .defaultOrder
    @State private var showCreatePlaylist = false
    @State private var newPlaylistName = ""

    public init(store: LibraryStore, onPlay: @escaping (MediaItem, MediaDetail?) -> Void) {
        self.store = store
        self.onPlay = onPlay
    }

    private var relevantCategories: [MediaCategory] {
        let base: [MediaCategory]
        switch section {
        case .all: base = store.categories
        case .live: base = store.categories.filter { $0.kind == .live }
        case .vod: base = store.categories.filter { $0.kind == .vod }
        case .series: base = store.categories.filter { $0.kind == .series }
        case .playlists: base = []
        }
        return base
    }

    private var filteredItems: [MediaItem] {
        var list = store.items.filter { item in
            switch section {
            case .all: return true
            case .live: return item.kind == .live
            case .vod: return item.kind == .vod
            case .series: return item.kind == .series
            case .playlists: return false
            }
        }
        if selectedCategoryId != "all" {
            list = list.filter { $0.categoryId == selectedCategoryId }
        }
        switch sortOrder {
        case .defaultOrder:
            return list
        case .alphabetical:
            return list.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        case .ratingDesc:
            return list.sorted { $0.rating > $1.rating }
        case .yearDesc:
            return list.sorted { $0.year > $1.year }
        }
    }

    public var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                Picker("Kütüphane Sekmesi", selection: $section) {
                    ForEach(LibrarySectionTab.allCases) { tab in
                        Text(tab.rawValue).tag(tab)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 16)
                .onChange(of: section) { _ in
                    selectedCategoryId = "all"
                }

                if section == .playlists {
                    playlistsView
                } else {
                    if !relevantCategories.isEmpty {
                        categoryStrip
                    }
                    catalogGrid
                }
            }
            .padding(.top, 8)
            .background(VrelioTheme.bg.ignoresSafeArea())
            .navigationTitle("Kütüphane")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    if section == .playlists {
                        Button {
                            showCreatePlaylist = true
                        } label: {
                            Label("Yeni Liste", systemImage: "plus")
                        }
                        .frame(minWidth: 44, minHeight: 44)
                        .accessibilityLabel("Yeni Çalma Listesi Oluştur")
                    } else {
                        Menu {
                            ForEach(LibrarySortOrder.allCases) { order in
                                Button {
                                    sortOrder = order
                                } label: {
                                    if sortOrder == order {
                                        Label(order.rawValue, systemImage: "checkmark")
                                    } else {
                                        Text(order.rawValue)
                                    }
                                }
                            }
                        } label: {
                            Label("Sırala", systemImage: "arrow.up.arrow.down")
                        }
                        .frame(minWidth: 44, minHeight: 44)
                        .accessibilityLabel("Katalog Sıralama Seçenekleri")
                    }
                }
            }
            .alert("Yeni Liste Oluştur", isPresented: $showCreatePlaylist) {
                TextField("Liste adı", text: $newPlaylistName)
                Button("Oluştur") {
                    store.createPlaylist(name: newPlaylistName)
                    newPlaylistName = ""
                }
                Button("İptal", role: .cancel) { newPlaylistName = "" }
            }
        }
    }

    private var categoryStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                categoryChip(id: "all", name: "Tümü")
                ForEach(relevantCategories) { cat in
                    categoryChip(id: cat.id, name: cat.name)
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private func categoryChip(id: String, name: String) -> some View {
        let selected = selectedCategoryId == id
        return Button {
            selectedCategoryId = id
        } label: {
            Text(name)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 14)
                .frame(minHeight: 44)
                .background(
                    Capsule()
                        .fill(selected ? AnyShapeStyle(VrelioTheme.brandGradient) : AnyShapeStyle(VrelioTheme.panel))
                        .overlay(Capsule().strokeBorder(VrelioTheme.border, lineWidth: 1))
                )
        }
        .accessibilityLabel("\(name) kategorisini filtrele")
    }

    private var catalogGrid: some View {
        ScrollView {
            if filteredItems.isEmpty {
                VrelioEmptyStateCard(
                    systemImage: "film",
                    title: "İçerik Bulunamadı",
                    message: "Seçili filtreye uygun içerik yok veya henüz kaynak yüklenmedi.",
                    actionTitle: "Demo İçerikleri Yükle"
                ) {
                    store.loadDemoCatalog()
                }
                .padding(16)
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 155, maximum: 220), spacing: 14)], spacing: 14) {
                    ForEach(filteredItems) { item in
                        NavigationLink {
                            DetailView(store: store, item: item, onPlay: onPlay)
                        } label: {
                            MediaPosterCard(
                                item: item,
                                progress: store.progress(for: item),
                                isFavorite: store.isFavorite(item),
                                onToggleFavorite: { store.toggleFavorite(item) }
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(16)
            }
        }
    }

    private var playlistsView: some View {
        ScrollView {
            VStack(spacing: 12) {
                if store.playlists.isEmpty {
                    VrelioEmptyStateCard(
                        systemImage: "text.badge.plus",
                        title: "Henüz Listeniz Yok",
                        message: "Filmleri ve canlı kanalları düzenlemek için yeni bir liste oluşturun.",
                        actionTitle: "Liste Oluştur"
                    ) {
                        showCreatePlaylist = true
                    }
                } else {
                    ForEach(store.playlists) { playlist in
                        let resolved = store.items.filter { playlist.itemIds.contains($0.id) }
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(playlist.name)
                                        .font(.headline)
                                        .foregroundStyle(.white)
                                    Text("\(resolved.count) içerik")
                                        .font(.caption)
                                        .foregroundStyle(VrelioTheme.muted)
                                }
                                Spacer()
                                Button(role: .destructive) {
                                    store.removePlaylist(id: playlist.id)
                                } label: {
                                    Label("Sil", systemImage: "trash")
                                }
                                .buttonStyle(VrelioGhostButtonStyle(compact: true))
                                .accessibilityLabel("\(playlist.name) listesini sil")
                            }
                            ForEach(resolved) { item in
                                NavigationLink {
                                    DetailView(store: store, item: item, onPlay: onPlay)
                                } label: {
                                    HStack {
                                        Text(item.name)
                                            .font(.subheadline)
                                            .foregroundStyle(.white)
                                        Spacer()
                                        Image(systemName: "play.circle.fill")
                                            .foregroundStyle(VrelioTheme.coral)
                                    }
                                    .frame(minHeight: 44)
                                }
                            }
                        }
                        .padding(14)
                        .vrelioCard()
                    }
                }
            }
            .padding(16)
        }
    }
}
