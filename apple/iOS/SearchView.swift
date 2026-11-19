import SwiftUI

public struct SearchView: View {
    @ObservedObject public var store: LibraryStore
    public var onPlay: (MediaItem, MediaDetail?) -> Void

    @State private var query = ""
    @State private var selectedKind: MediaKind?

    public init(store: LibraryStore, onPlay: @escaping (MediaItem, MediaDetail?) -> Void) {
        self.store = store
        self.onPlay = onPlay
    }

    private var results: [MediaItem] {
        store.searchItems(query: query, kind: selectedKind)
    }

    public var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(VrelioTheme.muted)
                    TextField("Film, dizi, kanal veya kategori ara…", text: $query)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .foregroundStyle(.white)
                    if !query.isEmpty {
                        Button {
                            query = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(VrelioTheme.muted)
                                .frame(width: 44, height: 44)
                        }
                        .accessibilityLabel("Aramayı Temizle")
                    }
                }
                .padding(.horizontal, 12)
                .frame(minHeight: 48)
                .vrelioCard(cornerRadius: 14)
                .padding(.horizontal, 16)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        kindChip(title: "Tümü", kind: nil)
                        kindChip(title: "Canlı", kind: .live)
                        kindChip(title: "Filmler", kind: .vod)
                        kindChip(title: "Diziler", kind: .series)
                    }
                    .padding(.horizontal, 16)
                }

                ScrollView {
                    if results.isEmpty {
                        VrelioEmptyStateCard(
                            systemImage: "magnifyingglass",
                            title: "Sonuç Bulunamadı",
                            message: "Farklı bir anahtar kelime deneyin veya tür filtresini temizleyin."
                        )
                        .padding(16)
                    } else {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 155, maximum: 220), spacing: 14)], spacing: 14) {
                            ForEach(results) { item in
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
            .padding(.top, 10)
            .background(VrelioTheme.bg.ignoresSafeArea())
            .navigationTitle("Ara")
        }
    }

    private func kindChip(title: String, kind: MediaKind?) -> some View {
        let active = selectedKind == kind
        return Button {
            selectedKind = kind
        } label: {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 14)
                .frame(minHeight: 44)
                .background(
                    Capsule()
                        .fill(active ? AnyShapeStyle(VrelioTheme.brandGradient) : AnyShapeStyle(VrelioTheme.panel))
                        .overlay(Capsule().strokeBorder(VrelioTheme.border, lineWidth: 1))
                )
        }
        .accessibilityLabel("\(title) türünü filtrele")
    }
}
