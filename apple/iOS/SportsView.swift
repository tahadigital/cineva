import SwiftUI

public struct SportsView: View {
    @ObservedObject public var store: LibraryStore
    public var onPlay: (MediaItem, MediaDetail?) -> Void

    @State private var selectedDayIso: String = SportsView.todayIso()
    @State private var events: [SportBroadcastEvent] = []
    @State private var matchedChannels: [String: MediaItem] = [:]
    @State private var isLoading = false
    @State private var isStale = false
    @State private var errorMessage: String?
    @State private var searchQuery = ""
    @State private var selectedSport = ""
    @State private var guideSource = "auto"
    @State private var activeSourceType = "sporekrani"
    @State private var isGuideConfigured = true

    public init(store: LibraryStore, onPlay: @escaping (MediaItem, MediaDetail?) -> Void) {
        self.store = store
        self.onPlay = onPlay
    }

    private static var istanbulCalendar: Calendar {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = DiscoveryEngine.istanbulTimeZone
        return cal
    }

    private static func isoFormatter() -> DateFormatter {
        let f = DateFormatter()
        f.calendar = istanbulCalendar
        f.timeZone = DiscoveryEngine.istanbulTimeZone
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }

    private static func labelFormatter() -> DateFormatter {
        let f = DateFormatter()
        f.calendar = istanbulCalendar
        f.timeZone = DiscoveryEngine.istanbulTimeZone
        f.locale = Locale(identifier: "tr_TR")
        f.dateFormat = "d MMM EEE"
        return f
    }

    private static func todayIso() -> String {
        isoFormatter().string(from: Date())
    }

    private struct DayChoice: Identifiable {
        let id: String
        let label: String
    }

    private var dayChoices: [DayChoice] {
        let cal = Self.istanbulCalendar
        let today = cal.startOfDay(for: Date())
        let isoFmt = Self.isoFormatter()
        let lblFmt = Self.labelFormatter()
        return (-1...8).compactMap { offset in
            guard let date = cal.date(byAdding: .day, value: offset, to: today) else { return nil }
            let iso = isoFmt.string(from: date)
            let label: String
            switch offset {
            case -1: label = "Dün"
            case 0: label = "Bugün"
            case 1: label = "Yarın"
            default: label = lblFmt.string(from: date)
            }
            return DayChoice(id: iso, label: label)
        }
    }

    private var sportsCategories: [String] {
        Array(Set(events.map(\.sport))).sorted { $0.localizedCompare($1) == .orderedAscending }
    }

    private var filteredEvents: [SportBroadcastEvent] {
        let term = SportsChannels.fold(searchQuery.trimmingCharacters(in: .whitespacesAndNewlines))
        return events.filter { ev in
            let matchesSport = selectedSport.isEmpty || ev.sport == selectedSport
            let haystack = SportsChannels.fold(([ev.title, ev.league, ev.sport] + ev.channels).joined(separator: " "))
            return matchesSport && (term.isEmpty || haystack.contains(term))
        }
    }

    private var spotlightEvent: SportBroadcastEvent? {
        events.first(where: \.featured) ?? events.first
    }

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("MAVIE SPOR EKRANI")
                            .font(.caption.weight(.bold))
                            .tracking(1.6)
                            .foregroundStyle(MavieTheme.turquoise)
                        Text("Spor Ekranı")
                            .font(.largeTitle.weight(.heavy))
                            .foregroundStyle(.white)
                        Text("Türkiye saatine göre günün maçları, yarışları ve eşleşen IPTV kanalları")
                            .font(.caption)
                            .foregroundStyle(MavieTheme.muted)
                    }

                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(dayChoices) { day in
                                Button {
                                    if selectedDayIso != day.id {
                                        selectedDayIso = day.id
                                        selectedSport = ""
                                        Task { await loadGuide(force: false) }
                                    }
                                } label: {
                                    Text(day.label)
                                        .font(.caption.weight(.semibold))
                                        .padding(.horizontal, 14)
                                        .frame(minHeight: 44)
                                        .mavieGlassPill(selected: selectedDayIso == day.id)
                                        .foregroundStyle(.white)
                                }
                                .buttonStyle(MavieInteractiveCardButtonStyle())
                            }
                        }
                    }

                    if !store.connection.epgUrl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                sourceModeChip(title: "Otomatik (XMLTV)", mode: "auto")
                                sourceModeChip(title: "XMLTV EPG", mode: "xmltv")
                                sourceModeChip(title: "Spor Ekranı", mode: "sporekrani")
                            }
                        }
                    }

                    if isLoading {
                        HStack(spacing: 10) {
                            ProgressView().tint(MavieTheme.turquoise)
                            Text("Spor yayın akışı yükleniyor…")
                                .font(.subheadline)
                                .foregroundStyle(MavieTheme.muted)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 32)
                    } else if let errorMessage {
                        VStack(spacing: 10) {
                            Text(errorMessage)
                                .font(.subheadline)
                                .foregroundStyle(MavieTheme.muted)
                                .multilineTextAlignment(.center)
                            Button("Tekrar Dene") {
                                Task { await loadGuide(force: true) }
                            }
                            .buttonStyle(MaviePrimaryButtonStyle(compact: true))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 24)
                    } else {
                        if isStale {
                            Text("Son alınan yayın akışı gösteriliyor.")
                                .font(.caption)
                                .foregroundStyle(MavieTheme.warning)
                        }

                        if let hero = spotlightEvent {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("ÖNE ÇIKAN KARŞILAŞMA")
                                    .font(.caption2.weight(.bold))
                                    .tracking(1.4)
                                    .foregroundStyle(MavieTheme.cyanDot)
                                Text(hero.title)
                                    .font(.title3.weight(.bold))
                                    .foregroundStyle(.white)
                                Text("\(hero.time) · \(hero.league.isEmpty ? hero.sport : hero.league)")
                                    .font(.caption)
                                    .foregroundStyle(MavieTheme.muted)
                                channelChips(for: hero)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(16)
                            .background(
                                RoundedRectangle(cornerRadius: 16, style: .continuous)
                                    .fill(.ultraThinMaterial)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                                            .fill(
                                                LinearGradient(
                                                    colors: [MavieTheme.purple.opacity(0.28), MavieTheme.turquoise.opacity(0.18)],
                                                    startPoint: .topLeading,
                                                    endPoint: .bottomTrailing
                                                )
                                            )
                                    )
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                                            .strokeBorder(MavieTheme.specularAccentBorder, lineWidth: 1)
                                    )
                            )
                            .shadow(color: MavieTheme.purple.opacity(0.22), radius: 14, y: 6)
                        }

                        if !events.isEmpty {
                            HStack(spacing: 8) {
                                Image(systemName: "magnifyingglass")
                                    .foregroundStyle(MavieTheme.muted)
                                TextField("Maç, takım veya kanal ara", text: $searchQuery)
                                    .textInputAutocapitalization(.never)
                                    .autocorrectionDisabled()
                                    .foregroundStyle(.white)
                            }
                            .padding(10)
                            .mavieCard(cornerRadius: 12)

                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 8) {
                                    sportChip(title: "Tümü", selected: selectedSport.isEmpty) { selectedSport = "" }
                                    ForEach(sportsCategories, id: \.self) { sport in
                                        sportChip(title: sport, selected: selectedSport == sport) { selectedSport = sport }
                                    }
                                }
                            }
                        }

                        if !isGuideConfigured {
                            Text("XMLTV EPG adresi ayarlanmamış. Ayarlar ekranından bir EPG URL'si ekleyin.")
                                .font(.subheadline)
                                .foregroundStyle(MavieTheme.muted)
                                .padding(.vertical, 16)
                        } else if filteredEvents.isEmpty {
                            Text(events.isEmpty ? "Bu gün için yayın bilgisi listelenmiyor." : "Bu filtreye uyan yayın yok.")
                                .font(.subheadline)
                                .foregroundStyle(MavieTheme.muted)
                                .padding(.vertical, 16)
                        } else {
                            LazyVStack(spacing: 10) {
                                ForEach(filteredEvents) { ev in
                                    VStack(alignment: .leading, spacing: 6) {
                                        HStack(alignment: .top, spacing: 12) {
                                            Text(ev.time)
                                                .font(.subheadline.weight(.bold).monospacedDigit())
                                                .foregroundStyle(MavieTheme.turquoise)
                                                .frame(width: 48, alignment: .leading)
                                            VStack(alignment: .leading, spacing: 4) {
                                                Text(ev.league.isEmpty ? ev.sport : "\(ev.sport) · \(ev.league)")
                                                    .font(.caption2)
                                                    .foregroundStyle(MavieTheme.muted)
                                                Text(ev.title)
                                                    .font(.subheadline.weight(.semibold))
                                                    .foregroundStyle(.white)
                                                channelChips(for: ev)
                                            }
                                        }
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(12)
                                    .mavieCard()
                                }
                            }
                        }

                        Text(activeSourceType == "xmltv" ? "Yayın bilgileri · XMLTV EPG (Türkiye saati)" : "Yayın bilgileri · Spor Ekranı (Türkiye saati)")
                            .font(.caption2)
                            .foregroundStyle(MavieTheme.muted)
                            .padding(.top, 4)
                    }
                }
                .padding(16)
            }
            .background(MavieTheme.cinemaBackdrop.ignoresSafeArea())
            .navigationTitle("Spor")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await loadGuide(force: true) }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .accessibilityLabel("Spor yayın akışını yenile")
                }
            }
            .task {
                if events.isEmpty {
                    await loadGuide(force: false)
                }
            }
            .onChange(of: store.items) { _ in
                matchedChannels = SportsChannels.matchChannels(events: events, liveItems: store.items)
            }
            .onChange(of: store.connection.epgUrl) { _ in
                Task { await loadGuide(force: false) }
            }
        }
    }

    private func sourceModeChip(title: String, mode: String) -> some View {
        let selected = guideSource == mode
        return Button {
            if guideSource != mode {
                guideSource = mode
                selectedSport = ""
                Task { await loadGuide(force: false) }
            }
        } label: {
            Text(title)
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 12)
                .frame(minHeight: 44)
                .mavieGlassPill(selected: selected)
                .foregroundStyle(.white)
        }
        .buttonStyle(MavieInteractiveCardButtonStyle())
    }

    private func sportChip(title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 14)
                .frame(minHeight: 44)
                .mavieGlassPill(selected: selected)
                .foregroundStyle(.white)
        }
        .buttonStyle(MavieInteractiveCardButtonStyle())
    }

    @ViewBuilder
    private func channelChips(for event: SportBroadcastEvent) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(event.channels, id: \.self) { label in
                    if let matched = matchedChannels[label] {
                        Button {
                            onPlay(matched, nil)
                        } label: {
                            Label(label, systemImage: "play.fill")
                                .font(.caption.weight(.semibold))
                                .padding(.horizontal, 12)
                                .frame(minHeight: 38)
                                .mavieGlassPill(selected: true, cornerRadius: 10)
                                .foregroundStyle(.white)
                        }
                        .buttonStyle(MavieInteractiveCardButtonStyle())
                        .accessibilityLabel("\(event.title) · \(label) kanalını aç")
                    } else {
                        Text("\(label) · Listende yok")
                            .font(.caption2)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .foregroundStyle(MavieTheme.muted)
                            .mavieGlassPill(selected: false, cornerRadius: 10)
                    }
                }
            }
        }
    }

    @MainActor
    private func loadGuide(force: Bool) async {
        isLoading = true
        errorMessage = nil
        do {
            let response = try await SportsGuideService.shared.load(
                dayIso: selectedDayIso,
                epgUrl: store.connection.epgUrl,
                sourceMode: guideSource,
                force: force
            )
            events = response.events
            isStale = response.stale
            activeSourceType = response.sourceType
            isGuideConfigured = response.configured
            matchedChannels = SportsChannels.matchChannels(events: response.events, liveItems: store.items)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
