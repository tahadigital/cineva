# Vrelio

**Vrelio**, kişisel medya arşivlerinizi, M3U/M3U8 oynatma listelerinizi, XMLTV EPG program rehberlerinizi ve açık lisanslı akışları tek bir modern arayüzde yönetip oynatmanızı sağlayan çoklu platform medya merkezidir.

> **Gizlilik ve Yasal Konumlandırma:** Vrelio kişisel bir medya oynatıcıdır; herhangi bir televizyon kanalı, telifli içerik veya yayın akışı barındırmaz ve sağlamaz. Medya kaynaklarınız ve izleme geçmişiniz yalnızca kendi cihazınızda saklanır.

## İndirme

Hazır kurulum dosyalarını her zaman en güncel haliyle GitHub Releases üzerinden indirebilirsiniz:

- **Windows Kurulum Sihirbazı (`Vrelio-Setup.exe`) & Taşınabilir (`Vrelio.exe`):** [GitHub Releases](https://github.com/tahadigital/cineva/releases/latest)
- **Android APK (`Vrelio-Android.apk` / `Vrelio-Android.aab`):** [GitHub Releases](https://github.com/tahadigital/cineva/releases/latest)
- **macOS (`Vrelio-macOS.dmg` / `Vrelio-macOS.zip`):** [GitHub Releases](https://github.com/tahadigital/cineva/releases/latest)
- **iOS (`Vrelio-iOS.ipa`):** [GitHub Releases](https://github.com/tahadigital/cineva/releases/latest)

## Özellikler

- **4 Platform Desteği:** Windows Masaüstü, Android (Telefon & Tablet 2-panelli arayüz), macOS (Native `.app`/`.dmg`) ve iOS / iPadOS (Native SwiftUI + AVKit)
- **İki Katmanlı Plan Sistemi (Normal & Pro):** E-posta doğrulamasını tamamlayan her yeni hesap otomatik olarak **3 günlük Pro deneme** ile başlar; Pro plan bulut eşitleme, 2×2 çoklu ekran, sınırsız/PIN korumalı profil, XMLTV EPG eşleştirme ve 5 cihaza kadar kayıt desteği sunar
- **E-posta Doğrulamalı Hesap & Parola Sıfırlama:** Kötüye kullanımı önlemek için doğrulama kodlu kayıt ve self-servis parola sıfırlama (SMTP, Resend/Webhook veya yerel test `email_outbox` modu)
- **Gelişmiş Oynatıcı:** LibVLC / AVKit / hls.js motoru, PiP (resim içinde resim), oynatma hızı, ekran oranı, uyku zamanlayıcısı, çoklu ses/altyazı seçimi ve zaman kaydırma
- **Yerel Medya & Profiller:** Bilgisayardaki yerel video klasörlerini tarama, sürükle-bırak oynatma, PIN korumalı profiller ve Çocuk Modu
- **2×2 Çoklu Ekran:** Web/Masaüstü arayüzünde aynı anda 4 adede kadar yayını bölünmüş ekranda izleme

## Kaynaktan Çalıştırma

### Masaüstü / Web Uygulaması (Windows / Mac / Linux)
```bash
python3 desktop/vrelio_desktop.py
```

### Bulut Kontrol Sunucusu & E-posta Yapılandırması
```bash
python3 cloud_admin.py --host 127.0.0.1 --port 8899
```
İsteğe bağlı e-posta ortam değişkenleri:
- `VRELIO_EMAIL_MODE`: `auto` (varsayılan), `smtp` veya `outbox`
- `VRELIO_SMTP_HOST`, `VRELIO_SMTP_PORT` (varsayılan `587`), `VRELIO_SMTP_USER`, `VRELIO_SMTP_PASS`, `VRELIO_SMTP_FROM`
- `VRELIO_EMAIL_OUTBOX_FILE`: SMTP kimlik bilgileri yokken doğrulama/sıfırlama e-postalarının yazıldığı dosya yolu (varsayılan `cloud_data/email_outbox.json`)

### Android
`android/` dizinindeki Gradle projesini Android Studio ile açabilir veya komut satırından derleyebilirsiniz:
```bash
cd android && ./gradlew :app:assembleDebug
```

## Doğrulama Testleri

- Backend (Python): `python3 -m unittest discover -s tests -v`
- Web & Bulut (Node.js): `node --test tests/test_*.mjs`
- Android (Gradle): `./gradlew :app:testDebugUnitTest :app:lintDebug`
