import SwiftUI
import UniformTypeIdentifiers

private struct MavieBackupDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.json] }
    var data: Data

    init(data: Data) {
        self.data = data
    }

    init(configuration: ReadConfiguration) throws {
        self.data = configuration.file.regularFileContents ?? Data()
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: data)
    }
}

public struct SettingsView: View {
    @ObservedObject public var store: LibraryStore

    @State private var m3uURL = ""
    @State private var epgURL = ""
    @State private var xtreamHost = ""
    @State private var xtreamUser = ""
    @State private var xtreamPass = ""
    @State private var lanAddress = ""
    @State private var lanPairingCode = ""

    @State private var showVideoImporter = false
    @State private var showBackupImporter = false
    @State private var showBackupExporter = false
    @State private var exportDocument: MavieBackupDocument?

    @State private var showAddProfile = false
    @State private var newProfileName = ""
    @State private var newProfilePin = ""
    @State private var newProfileKids = false

    @State private var pinPromptProfile: UserProfile?
    @State private var pinAttempt = ""
    @State private var deleteConfirmProfile: UserProfile?

    @State private var feedbackMessage: String?
    @State private var errorMessage: String?

    public init(store: LibraryStore) {
        self.store = store
    }

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if let errorMessage = errorMessage ?? store.lastError {
                        statusCard(errorMessage, isError: true)
                    } else if let feedbackMessage {
                        statusCard(feedbackMessage, isError: false)
                    }

                    sourcesSection
                    lanSyncSection
                    profilesSection
                    backupSection
                    aboutSection
                }
                .padding(16)
            }
            .background(MavieTheme.cinemaBackdrop.ignoresSafeArea())
            .navigationTitle("Ayarlar")
            .onAppear {
                if m3uURL.isEmpty { m3uURL = store.connection.m3uUrl }
                if epgURL.isEmpty { epgURL = store.connection.epgUrl }
                if xtreamHost.isEmpty { xtreamHost = store.connection.host }
                if xtreamUser.isEmpty { xtreamUser = store.connection.username }
                if lanAddress.isEmpty { lanAddress = store.connection.lanAddress }
            }
            .fileImporter(
                isPresented: $showVideoImporter,
                allowedContentTypes: [.movie, .mpeg4Movie, .audiovisualContent],
                allowsMultipleSelection: false
            ) { result in
                if case .success(let urls) = result, let url = urls.first {
                    let accessed = url.startAccessingSecurityScopedResource()
                    defer { if accessed { url.stopAccessingSecurityScopedResource() } }
                    do {
                        try store.importLocalMediaFile(from: url)
                        feedbackMessage = "Yerel video kütüphaneye kopyalandı."
                        errorMessage = nil
                    } catch {
                        errorMessage = error.localizedDescription
                    }
                }
            }
            .fileImporter(
                isPresented: $showBackupImporter,
                allowedContentTypes: [.json],
                allowsMultipleSelection: false
            ) { result in
                if case .success(let urls) = result, let url = urls.first {
                    let accessed = url.startAccessingSecurityScopedResource()
                    defer { if accessed { url.stopAccessingSecurityScopedResource() } }
                    do {
                        let data = try Data(contentsOf: url)
                        try store.importBackupJSON(data)
                        feedbackMessage = "Yedek dosyası içe aktarıldı."
                    } catch {
                        errorMessage = error.localizedDescription
                    }
                }
            }
            .fileExporter(
                isPresented: $showBackupExporter,
                document: exportDocument,
                contentType: .json,
                defaultFilename: "mavie-yedek"
            ) { result in
                if case .success = result {
                    feedbackMessage = "JSON yedek kaydedildi."
                }
            }
            .sheet(isPresented: $showAddProfile) {
                addProfileSheet
            }
            .alert(
                "Profil PIN Kodu",
                isPresented: Binding(
                    get: { pinPromptProfile != nil },
                    set: { if !$0 { pinPromptProfile = nil; pinAttempt = "" } }
                )
            ) {
                SecureField("PIN", text: $pinAttempt)
                    .keyboardType(.numberPad)
                Button("Giriş") {
                    guard let target = pinPromptProfile else { return }
                    let attempt = pinAttempt
                    pinPromptProfile = nil
                    pinAttempt = ""
                    do {
                        try store.switchProfile(id: target.id, pinAttempt: attempt)
                        feedbackMessage = "\(target.name) profiline geçildi."
                        errorMessage = nil
                    } catch {
                        feedbackMessage = nil
                        errorMessage = error.localizedDescription
                    }
                }
                Button("İptal", role: .cancel) {
                    pinPromptProfile = nil
                    pinAttempt = ""
                }
            } message: {
                Text("\(pinPromptProfile?.name ?? "Seçili profil") için PIN kodunu girin.")
            }
            .alert(
                "Profili Sil",
                isPresented: Binding(
                    get: { deleteConfirmProfile != nil },
                    set: { if !$0 { deleteConfirmProfile = nil } }
                )
            ) {
                Button("Sil", role: .destructive) {
                    guard let target = deleteConfirmProfile else { return }
                    deleteConfirmProfile = nil
                    do {
                        try store.removeProfile(id: target.id)
                        feedbackMessage = "\(target.name) profili silindi."
                        errorMessage = nil
                    } catch {
                        feedbackMessage = nil
                        errorMessage = error.localizedDescription
                    }
                }
                Button("İptal", role: .cancel) {
                    deleteConfirmProfile = nil
                }
            } message: {
                Text("\(deleteConfirmProfile?.name ?? "Bu profil") kalıcı olarak kaldırılsın mı?")
            }
        }
    }

    private var sourcesSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Medya Kaynakları")
                .font(.headline)
                .foregroundStyle(.white)

            Button {
                store.loadDemoCatalog()
                feedbackMessage = "Açık Sinema demo filmleri yüklendi."
                errorMessage = nil
            } label: {
                Label("Açık Sinema ile Hemen Dene (Demo)", systemImage: "sparkles.tv.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(MaviePrimaryButtonStyle(compact: true))
            .accessibilityLabel("Açık Sinema Demo Kataloğunu Yükle")

            Divider().overlay(MavieTheme.border)

            Text("M3U / M3U8 Oynatma Listesi")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
            HStack(spacing: 8) {
                TextField("http://.../get.php?... veya https://...", text: $m3uURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .padding(10)
                    .mavieGlassPill(selected: false, cornerRadius: 10)
                    .foregroundStyle(.white)
                Button("Yükle") {
                    Task {
                        feedbackMessage = nil
                        errorMessage = nil
                        await store.importM3uFromURL(m3uURL)
                        if store.lastError == nil {
                            feedbackMessage = store.statusBanner
                            if epgURL.isEmpty && !store.connection.epgUrl.isEmpty {
                                epgURL = store.connection.epgUrl
                            }
                        } else {
                            feedbackMessage = nil
                        }
                    }
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .accessibilityLabel("M3U Adresini Yükle")
            }

            Text("XMLTV EPG Adresi (İsteğe Bağlı)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(MavieTheme.muted)
            HStack(spacing: 8) {
                TextField("http://.../xmltv.php?... veya https://.../guide.xml.gz", text: $epgURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .padding(10)
                    .mavieGlassPill(selected: false, cornerRadius: 10)
                    .foregroundStyle(.white)
                Button("Kaydet") {
                    do {
                        try store.updateEpgUrl(epgURL)
                        feedbackMessage = store.statusBanner
                        errorMessage = nil
                    } catch {
                        feedbackMessage = nil
                        errorMessage = error.localizedDescription
                    }
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .accessibilityLabel("XMLTV EPG Adresini Kaydet")
            }

            Divider().overlay(MavieTheme.border)

            Text("Xtream Codes API")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
            TextField("Sunucu adresi (ör. http://panel.example.com:8080)", text: $xtreamHost)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(10)
                .mavieGlassPill(selected: false, cornerRadius: 10)
                .foregroundStyle(.white)
            TextField("Kullanıcı adı", text: $xtreamUser)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(10)
                .mavieGlassPill(selected: false, cornerRadius: 10)
                .foregroundStyle(.white)
            SecureField("Parola", text: $xtreamPass)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(10)
                .mavieGlassPill(selected: false, cornerRadius: 10)
                .foregroundStyle(.white)

            Button {
                Task {
                    feedbackMessage = nil
                    errorMessage = nil
                    await store.connectXtream(host: xtreamHost, username: xtreamUser, password: xtreamPass)
                    feedbackMessage = store.lastError == nil ? store.statusBanner : nil
                }
            } label: {
                Label("Xtream’e Bağlan", systemImage: "antenna.radiowaves.left.and.right")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(MavieGhostButtonStyle(compact: true))
            .accessibilityLabel("Xtream Sunucusuna Bağlan")

            Divider().overlay(MavieTheme.border)

            Button {
                showVideoImporter = true
            } label: {
                Label("Cihazdan Video Dosyası Ekle (.mp4/.mov/.m3u8)", systemImage: "folder.badge.plus")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(MavieGhostButtonStyle(compact: true))
            .accessibilityLabel("Cihazdan Yerel Video Dosyası Seç")
        }
        .padding(16)
        .mavieCard()
    }

    private var lanSyncSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Masaüstü Mavie Sunucusu ile Yerel Ağ Eşitleme")
                .font(.headline)
                .foregroundStyle(.white)
            Text("Aynı Wi-Fi ağındaki Mac veya Windows Mavie uygulamasının yerel IP adresini ve 6 haneli eşleştirme kodunu girin.")
                .font(.caption)
                .foregroundStyle(MavieTheme.muted)

            TextField("Yerel adres (ör. 192.168.1.25:8844)", text: $lanAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(10)
                .mavieGlassPill(selected: false, cornerRadius: 10)
                .foregroundStyle(.white)

            TextField("6 haneli eşleştirme kodu", text: $lanPairingCode)
                .keyboardType(.numberPad)
                .padding(10)
                .mavieGlassPill(selected: false, cornerRadius: 10)
                .foregroundStyle(.white)

            Button {
                Task {
                    do {
                        try await store.syncWithLanServer(address: lanAddress, pairingCode: lanPairingCode)
                        feedbackMessage = "Yerel sunucu ile eşitleme tamamlandı."
                        errorMessage = nil
                    } catch {
                        errorMessage = error.localizedDescription
                    }
                }
            } label: {
                Label("Yerel Sunucuyla Eşitle", systemImage: "wifi")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(MavieGhostButtonStyle(compact: true))
            .accessibilityLabel("Yerel Mavie Sunucusuyla Eşitle")
        }
        .padding(16)
        .mavieCard()
    }

    private var profilesSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Profiller")
                    .font(.headline)
                    .foregroundStyle(.white)
                Spacer()
                Button {
                    showAddProfile = true
                } label: {
                    Label("Profil Ekle", systemImage: "person.crop.circle.badge.plus")
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .accessibilityLabel("Yeni Profil Ekle")
            }

            ForEach(store.profiles) { profile in
                HStack(spacing: 8) {
                    Image(systemName: profile.isKids ? "figure.and.child.holdinghands" : "person.circle.fill")
                        .font(.title3)
                        .foregroundStyle(profile.active ? MavieTheme.cyanDot : MavieTheme.muted)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(profile.name)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.white)
                        if profile.hasPin {
                            Text("PIN Korumalı")
                                .font(.caption2)
                                .foregroundStyle(MavieTheme.amber)
                        }
                    }
                    Spacer()
                    if profile.active {
                        Text("Aktif")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(MavieTheme.success)
                    } else {
                        Button("Seç") {
                            if profile.hasPin {
                                pinAttempt = ""
                                pinPromptProfile = profile
                            } else {
                                do {
                                    try store.switchProfile(id: profile.id)
                                    feedbackMessage = "\(profile.name) profiline geçildi."
                                    errorMessage = nil
                                } catch {
                                    feedbackMessage = nil
                                    errorMessage = error.localizedDescription
                                }
                            }
                        }
                        .buttonStyle(MavieGhostButtonStyle(compact: true))
                        .accessibilityLabel("\(profile.name) profiline geç")
                    }

                    if profile.id != "default" && store.profiles.count > 1 {
                        Button(role: .destructive) {
                            deleteConfirmProfile = profile
                        } label: {
                            Image(systemName: "trash")
                                .foregroundStyle(MavieTheme.danger)
                                .frame(minWidth: 44, minHeight: 44)
                        }
                        .accessibilityLabel("\(profile.name) profilini sil")
                    }
                }
                .padding(10)
                .mavieGlassPill(selected: false, cornerRadius: 12)
            }
        }
        .padding(16)
        .mavieCard()
    }

    private var backupSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Yedekleme ve Geri Yükleme")
                .font(.headline)
                .foregroundStyle(.white)
            HStack(spacing: 10) {
                Button {
                    if let data = try? store.exportBackupJSON() {
                        exportDocument = MavieBackupDocument(data: data)
                        showBackupExporter = true
                    }
                } label: {
                    Label("Yedeği Dışa Aktar", systemImage: "square.and.arrow.up")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .accessibilityLabel("JSON Yedeğini Dışa Aktar")

                Button {
                    showBackupImporter = true
                } label: {
                    Label("Yedeği İçe Aktar", systemImage: "square.and.arrow.down")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .accessibilityLabel("JSON Yedeğini İçe Aktar")
            }
        }
        .padding(16)
        .mavieCard()
    }

    private var aboutSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            MavieWordmark(subtitle: "Sürüm 2.2.0 · iOS / iPadOS · Ücretsiz", markSize: 30)
            Text("Mavie tamamen ücretsiz ve hesap gerektirmeyen, kullanıcı tarafından sağlanan yasal medya kaynakları ve açık lisanslı demo katalogları için geliştirilmiş yerel bir medya oynatıcıdır.")
                .font(.caption)
                .foregroundStyle(MavieTheme.muted)
            Text("İletişim: privacy@mavie.app · legal@mavie.app")
                .font(.caption2)
                .foregroundStyle(MavieTheme.muted)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .mavieCard()
    }

    private var addProfileSheet: some View {
        NavigationStack {
            Form {
                Section("Profil Bilgileri") {
                    TextField("Profil adı", text: $newProfileName)
                    Toggle("Çocuk Profili", isOn: $newProfileKids)
                    SecureField("İsteğe bağlı PIN", text: $newProfilePin)
                        .keyboardType(.numberPad)
                }
            }
            .navigationTitle("Yeni Profil")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("İptal") { showAddProfile = false }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Ekle") {
                        do {
                            try store.addProfile(name: newProfileName, isKids: newProfileKids, pin: newProfilePin)
                            newProfileName = ""
                            newProfilePin = ""
                            newProfileKids = false
                            showAddProfile = false
                        } catch {
                            errorMessage = error.localizedDescription
                            showAddProfile = false
                        }
                    }
                }
            }
        }
        .preferredColorScheme(.dark)
    }

    private func statusCard(_ text: String, isError: Bool) -> some View {
        HStack(spacing: 10) {
            Image(systemName: isError ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                .foregroundStyle(isError ? MavieTheme.danger : MavieTheme.success)
            Text(text)
                .font(.subheadline)
                .foregroundStyle(.white)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill((isError ? MavieTheme.danger : MavieTheme.success).opacity(0.16))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .strokeBorder((isError ? MavieTheme.danger : MavieTheme.success).opacity(0.42), lineWidth: 1)
                )
        )
    }
}
