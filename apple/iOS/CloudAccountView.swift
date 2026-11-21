import SwiftUI
import UIKit

private enum AuthPanelMode: String, CaseIterable, Identifiable {
    case login = "Giriş"
    case register = "Kayıt Ol"
    case verifyEmail = "Doğrula"
    case forgotPassword = "Şifre Sıfırla"

    var id: String { rawValue }
}

public struct CloudAccountView: View {
    @ObservedObject public var store: LibraryStore

    @State private var mode: AuthPanelMode = .login
    @State private var portalURLInput: String = ""

    // Auth fields
    @State private var displayName = ""
    @State private var email = ""
    @State private var password = ""
    @State private var verificationCode = ""

    // Password reset fields
    @State private var resetCode = ""
    @State private var newPassword = ""
    @State private var resetCodeSent = false
    @State private var resetCodeVerified = false

    // Signed-in actions
    @State private var licenseCode = ""
    @State private var feedbackMessage: String?
    @State private var errorMessage: String?
    @State private var showUpgradeAlert = false

    public init(store: LibraryStore) {
        self.store = store
    }

    private var currentDeviceName: String {
        UIDevice.current.name
    }

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    portalConfigCard

                    if let feedbackMessage {
                        bannerCard(text: feedbackMessage, isError: false)
                    }
                    if let err = errorMessage ?? store.lastError {
                        bannerCard(text: err, isError: true)
                    }

                    if let user = store.cloudUser, store.isCloudSignedIn {
                        signedInDashboard(user: user)
                    } else {
                        signedOutPanel
                    }

                    planComparisonCard
                }
                .padding(16)
            }
            .background(MavieTheme.bg.ignoresSafeArea())
            .navigationTitle("Bulut & Plan")
            .onAppear {
                if portalURLInput.isEmpty {
                    portalURLInput = store.portalURL
                }
            }
            .alert("Mavie Pro Plan Gerekli", isPresented: $showUpgradeAlert) {
                Button("Tamam", role: .cancel) {}
            } message: {
                Text("Bulut eşitleme, 5 cihaza kadar kullanım ve çoklu/PIN korumalı profiller için Mavie Pro planına geçin veya lisans anahtarı girin.")
            }
        }
    }

    private var portalConfigCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Bulut Portalı Bağlantısı")
                .font(.headline)
                .foregroundStyle(.white)
            HStack(spacing: 8) {
                TextField("https://cineva-app.netlify.app", text: $portalURLInput)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .padding(10)
                    .background(MavieTheme.panelElevated, in: RoundedRectangle(cornerRadius: 10))
                    .foregroundStyle(.white)

                Button("Kaydet") {
                    do {
                        let valid = try CloudClient.validateBaseURL(portalURLInput)
                        store.portalURL = valid.absoluteString
                        portalURLInput = valid.absoluteString
                        feedbackMessage = "Bulut adresi kaydedildi."
                        errorMessage = nil
                    } catch {
                        errorMessage = error.localizedDescription
                    }
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .accessibilityLabel("Bulut Portalı Adresini Kaydet")
            }
        }
        .padding(14)
        .mavieCard()
    }

    private var signedOutPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            Picker("Hesap İşlemi", selection: $mode) {
                ForEach(AuthPanelMode.allCases) { m in
                    Text(m.rawValue).tag(m)
                }
            }
            .pickerStyle(.segmented)

            switch mode {
            case .login:
                loginForm
            case .register:
                registerForm
            case .verifyEmail:
                verifyEmailForm
            case .forgotPassword:
                forgotResetForm
            }
        }
        .padding(16)
        .mavieCard()
    }

    private var loginForm: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Mavie Hesabına Giriş Yap")
                .font(.headline)
                .foregroundStyle(.white)

            inputField(title: "E-posta adresi", text: $email, keyboard: .emailAddress)
            secureInputField(title: "Parola", text: $password)

            Button {
                Task { await performLogin() }
            } label: {
                if store.isBusy {
                    ProgressView().tint(.white).frame(maxWidth: .infinity)
                } else {
                    Label("Giriş Yap", systemImage: "arrow.right.circle.fill")
                        .frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(MaviePrimaryButtonStyle())
            .disabled(store.isBusy)
            .accessibilityLabel("Bulut Hesabına Giriş Yap")

            HStack {
                Button("Şifremi Unuttum") {
                    mode = .forgotPassword
                    errorMessage = nil
                }
                .frame(minHeight: 44)
                .foregroundStyle(MavieTheme.amber)
                .accessibilityLabel("Şifremi Unuttum Akışını Aç")

                Spacer()

                Button("Doğrulama Kodu Gir") {
                    mode = .verifyEmail
                    errorMessage = nil
                }
                .frame(minHeight: 44)
                .foregroundStyle(MavieTheme.muted)
                .accessibilityLabel("E-posta Doğrulama Ekranını Aç")
            }
            .font(.subheadline.weight(.medium))
        }
    }

    private var registerForm: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Yeni Hesap Oluştur")
                .font(.headline)
                .foregroundStyle(.white)
            Text("E-posta doğrulamasından sonra 3 günlük Mavie Pro denemeniz otomatik başlatılır.")
                .font(.caption)
                .foregroundStyle(MavieTheme.muted)

            inputField(title: "Adınız", text: $displayName, keyboard: .default)
            inputField(title: "E-posta adresi", text: $email, keyboard: .emailAddress)
            secureInputField(title: "Parola (en az 8 karakter)", text: $password)

            Button {
                Task { await performRegister() }
            } label: {
                if store.isBusy {
                    ProgressView().tint(.white).frame(maxWidth: .infinity)
                } else {
                    Label("Kayıt Ol ve Doğrulama Kodu Gönder", systemImage: "person.badge.plus")
                        .frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(MaviePrimaryButtonStyle())
            .disabled(store.isBusy)
            .accessibilityLabel("Yeni Mavie Hesabı Oluştur")
        }
    }

    private var verifyEmailForm: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("E-posta Doğrulama")
                .font(.headline)
                .foregroundStyle(.white)
            Text("E-postanıza gelen 6 haneli kodu girin.")
                .font(.caption)
                .foregroundStyle(MavieTheme.muted)

            inputField(title: "E-posta adresi", text: $email, keyboard: .emailAddress)
            inputField(title: "6 Haneli Doğrulama Kodu", text: $verificationCode, keyboard: .numberPad)

            Button {
                Task { await performVerifyEmail() }
            } label: {
                Label("E-postayı Doğrula", systemImage: "checkmark.shield.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(MaviePrimaryButtonStyle())
            .disabled(store.isBusy)
            .accessibilityLabel("6 Haneli Kodu Doğrula")

            Button {
                Task { await performResendCode() }
            } label: {
                Label("Kodu Yeniden Gönder", systemImage: "envelope.arrow.triangle.branch")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(MavieGhostButtonStyle(compact: true))
            .disabled(store.isBusy)
            .accessibilityLabel("Doğrulama Kodunu Yeniden Gönder")
        }
    }

    private var forgotResetForm: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Parola Sıfırlama")
                .font(.headline)
                .foregroundStyle(.white)

            inputField(title: "Kayıtlı e-posta adresi", text: $email, keyboard: .emailAddress)

            Button {
                Task { await performForgotPassword() }
            } label: {
                Label("Sıfırlama Kodu Gönder", systemImage: "paperplane.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(MavieGhostButtonStyle(compact: true))
            .disabled(store.isBusy)
            .accessibilityLabel("Şifre Sıfırlama Kodu Gönder")

            if resetCodeSent {
                Divider().overlay(MavieTheme.border)
                inputField(title: "6 Haneli Sıfırlama Kodu", text: $resetCode, keyboard: .numberPad)

                Button {
                    Task { await performVerifyResetCode() }
                } label: {
                    Label(resetCodeVerified ? "Kod Doğrulandı" : "Kodu Kontrol Et", systemImage: "checkmark.circle")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .disabled(store.isBusy)
                .accessibilityLabel("Sıfırlama Kodunu Doğrula")

                secureInputField(title: "Yeni Parola (en az 8 karakter)", text: $newPassword)

                Button {
                    Task { await performResetPassword() }
                } label: {
                    Label("Parolayı Güncelle", systemImage: "key.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(MaviePrimaryButtonStyle())
                .disabled(store.isBusy)
                .accessibilityLabel("Yeni Parolayı Kaydet")
            }
        }
    }

    private func signedInDashboard(user: CloudUser) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(user.displayName)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.white)
                    Text(user.email)
                        .font(.caption)
                        .foregroundStyle(MavieTheme.muted)
                    HStack(spacing: 8) {
                        Label(user.emailVerified ? "E-posta Doğrulandı" : "Doğrulanmadı", systemImage: user.emailVerified ? "checkmark.seal.fill" : "exclamationmark.triangle")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(user.emailVerified ? MavieTheme.success : MavieTheme.warning)
                    }
                }
                Spacer()
                Text(user.isPro ? "PRO" : "NORMAL")
                    .font(.caption.weight(.heavy))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(
                        user.isPro ? AnyShapeStyle(MavieTheme.brandGradient) : AnyShapeStyle(MavieTheme.panelElevated),
                        in: Capsule()
                    )
            }

            if user.trialActive, let remaining = user.trialRemainingSummary() {
                HStack(spacing: 10) {
                    Image(systemName: "crown.fill")
                        .foregroundStyle(MavieTheme.amber)
                    Text("3 Günlük Pro Deneme Aktif · \(remaining)")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(MavieTheme.amber.opacity(0.14), in: RoundedRectangle(cornerRadius: 12))
            }

            HStack(spacing: 10) {
                Button {
                    Task { await performCloudSync() }
                } label: {
                    Label("Bulutla Eşitle", systemImage: "icloud.and.arrow.up.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(MaviePrimaryButtonStyle(compact: true))
                .accessibilityLabel("Kütüphane ve İzleme İlerlemesini Bulutla Eşitle")

                Button {
                    Task { await store.refreshCloudProfile() }
                } label: {
                    Label("Yenile", systemImage: "arrow.clockwise")
                }
                .buttonStyle(MavieGhostButtonStyle(compact: true))
                .accessibilityLabel("Hesap Bilgilerini Yenile")
            }

            // Redeem license
            VStack(alignment: .leading, spacing: 8) {
                Text("Lisans Anahtarı Kullan")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                HStack(spacing: 8) {
                    inputField(title: "MAVIE-XXXX-XXXX-XXXX", text: $licenseCode, keyboard: .asciiCapable)
                    Button("Uygula") {
                        Task { await performRedeemLicense() }
                    }
                    .buttonStyle(MavieGhostButtonStyle(compact: true))
                    .accessibilityLabel("Lisans Anahtarını Uygula")
                }
            }

            // Registered devices
            VStack(alignment: .leading, spacing: 10) {
                Text("Kayıtlı Cihazlar (\(user.devices?.count ?? 0) / \(user.maxDevices))")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)

                if let devices = user.devices, !devices.isEmpty {
                    ForEach(devices) { dev in
                        HStack {
                            Image(systemName: platformIcon(dev.platform))
                                .foregroundStyle(MavieTheme.amber)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(dev.name)
                                    .font(.subheadline.weight(.medium))
                                    .foregroundStyle(.white)
                                Text(dev.platform.uppercased())
                                    .font(.caption2)
                                    .foregroundStyle(MavieTheme.muted)
                            }
                            Spacer()
                            Button(role: .destructive) {
                                Task { await performRemoveDevice(dev.id) }
                            } label: {
                                Label("Kaldır", systemImage: "trash")
                            }
                            .buttonStyle(MavieGhostButtonStyle(compact: true))
                            .accessibilityLabel("\(dev.name) cihazını hesaptan kaldır")
                        }
                        .padding(10)
                        .background(MavieTheme.panelElevated, in: RoundedRectangle(cornerRadius: 12))
                    }
                } else {
                    Text("Henüz kayıtlı cihaz listelenmedi.")
                        .font(.caption)
                        .foregroundStyle(MavieTheme.muted)
                }
            }

            Button(role: .destructive) {
                store.logoutCloud()
                feedbackMessage = "Oturum kapatıldı."
            } label: {
                Label("Çıkış Yap", systemImage: "rectangle.portrait.and.arrow.right")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(MavieGhostButtonStyle(compact: true))
            .accessibilityLabel("Bulut Hesabından Çıkış Yap")
        }
        .padding(16)
        .mavieCard()
    }

    private var planComparisonCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Plan Karşılaştırması")
                .font(.headline)
                .foregroundStyle(.white)

            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Normal")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.white)
                    Text("• 1 Cihaz")
                    Text("• Demo, M3U ve Yerel Oynatma")
                    Text("• 1 Profil")
                }
                .font(.caption)
                .foregroundStyle(MavieTheme.muted)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
                .background(MavieTheme.panelElevated, in: RoundedRectangle(cornerRadius: 12))

                VStack(alignment: .leading, spacing: 6) {
                    Label("Pro (3 Gün Deneme)", systemImage: "crown.fill")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(MavieTheme.amber)
                    Text("• 5 Cihaza Kadar")
                    Text("• Bulut Eşitleme (/sync)")
                    Text("• Çoklu Profil & PIN Koruma")
                    Text("• Gelişmiş İz & Spor EPG")
                }
                .font(.caption)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
                .background(
                    RoundedRectangle(cornerRadius: 12)
                        .fill(MavieTheme.coral.opacity(0.15))
                        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(MavieTheme.coral.opacity(0.45)))
                )
            }
        }
        .padding(14)
        .mavieCard()
    }

    // MARK: - Actions

    private func performLogin() async {
        errorMessage = nil
        feedbackMessage = nil
        do {
            try await store.loginCloud(email: email, password: password, deviceName: currentDeviceName, platform: "ios")
            if let deviceNotice = store.lastError {
                errorMessage = deviceNotice
            } else {
                feedbackMessage = "Giriş başarılı."
            }
        } catch MavieError.api(let apiErr) where apiErr.verificationRequired || apiErr.code == "EMAIL_NOT_VERIFIED" {
            if let returnedEmail = apiErr.email, !returnedEmail.isEmpty {
                email = returnedEmail
            }
            mode = .verifyEmail
            errorMessage = "E-posta doğrulaması gerekli. Lütfen kodunuzu girin veya yeniden gönderin."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func performRegister() async {
        errorMessage = nil
        feedbackMessage = nil
        do {
            _ = try await store.registerCloud(email: email, password: password, displayName: displayName)
            mode = .verifyEmail
            feedbackMessage = "Kayıt alındı! Doğrulama kodunu girerek 3 günlük Pro denemenizi başlatın."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func performVerifyEmail() async {
        errorMessage = nil
        feedbackMessage = nil
        do {
            let res = try await store.verifyCloudEmail(email: email, code: verificationCode, deviceName: currentDeviceName, platform: "ios")
            feedbackMessage = res.trialActivated
                ? "E-posta doğrulandı ve 3 günlük Pro denemeniz başladı!"
                : "E-posta doğrulandı."
            if let deviceNotice = store.lastError {
                errorMessage = deviceNotice
            }
            verificationCode = ""
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func performResendCode() async {
        errorMessage = nil
        feedbackMessage = nil
        do {
            try await store.resendVerification(email: email)
            feedbackMessage = "Doğrulama kodu tekrar gönderildi."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func performForgotPassword() async {
        errorMessage = nil
        feedbackMessage = nil
        do {
            try await store.forgotPassword(email: email)
            resetCodeSent = true
            resetCodeVerified = false
            feedbackMessage = "Eğer hesap kayıtlıysa şifre sıfırlama kodu gönderildi."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func performVerifyResetCode() async {
        errorMessage = nil
        feedbackMessage = nil
        do {
            let valid = try await store.verifyResetCode(email: email, code: resetCode)
            resetCodeVerified = valid
            if valid {
                feedbackMessage = "Kod doğrulandı. Şimdi yeni parolanızı belirleyin."
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func performResetPassword() async {
        errorMessage = nil
        feedbackMessage = nil
        do {
            try await store.resetPassword(email: email, code: resetCode, newPassword: newPassword)
            resetCode = ""
            newPassword = ""
            resetCodeSent = false
            resetCodeVerified = false
            mode = .login
            feedbackMessage = "Parolanız güncellendi! Yeni parolanızla giriş yapabilirsiniz."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func performCloudSync() async {
        errorMessage = nil
        feedbackMessage = nil
        do {
            try await store.syncWithCloud()
            feedbackMessage = "Bulut eşitleme tamamlandı."
        } catch MavieError.proRequired {
            showUpgradeAlert = true
        } catch MavieError.api(let apiErr) where apiErr.upgradeRequired || apiErr.code == "PRO_REQUIRED" {
            showUpgradeAlert = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func performRedeemLicense() async {
        errorMessage = nil
        feedbackMessage = nil
        do {
            try await store.redeemLicense(code: licenseCode)
            licenseCode = ""
            feedbackMessage = "Lisans anahtarı uygulandı!"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func performRemoveDevice(_ id: String) async {
        errorMessage = nil
        feedbackMessage = nil
        do {
            try await store.removeCloudDevice(deviceId: id)
            feedbackMessage = "Cihaz kaldırıldı."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Helpers

    private func inputField(title: String, text: Binding<String>, keyboard: UIKeyboardType) -> some View {
        TextField(title, text: text)
            .keyboardType(keyboard)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .padding(12)
            .frame(minHeight: 46)
            .background(MavieTheme.panelElevated, in: RoundedRectangle(cornerRadius: 10))
            .foregroundStyle(.white)
    }

    private func secureInputField(title: String, text: Binding<String>) -> some View {
        SecureField(title, text: text)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .padding(12)
            .frame(minHeight: 46)
            .background(MavieTheme.panelElevated, in: RoundedRectangle(cornerRadius: 10))
            .foregroundStyle(.white)
    }

    private func bannerCard(text: String, isError: Bool) -> some View {
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
            RoundedRectangle(cornerRadius: 12)
                .fill((isError ? MavieTheme.danger : MavieTheme.success).opacity(0.14))
        )
    }

    private func platformIcon(_ platform: String) -> String {
        switch platform.lowercased() {
        case "ios": return "iphone"
        case "macos": return "laptopcomputer"
        case "android": return "smartphone"
        case "windows": return "desktopcomputer"
        default: return "display"
        }
    }
}
