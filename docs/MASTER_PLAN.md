# Vrelio — Çoklu Platform Mimari ve Ürün Planı

Vrelio, yerel medya arşivlerini, kullanıcıların kendi sağladığı M3U/M3U8 oynatma listelerini, XMLTV EPG rehberlerini ve açık lisanslı yayınları Windows, Android, macOS ve iOS üzerinde oynatmak için tasarlanmış yerel öncelikli (local-first) bir medya merkezidir.

## 1. Platform Mimarisi

- **Yerel Medya Motoru (`server.py`, `playback.py`, `discovery.py`, `local_media.py`, `m3u.py`, `sports.py`):**
  - Python HTTP sunucusu ve SQLite yerel durum yönetimi
  - FFmpeg ile HLS remux/transcode ve çoklu ses/altyazı seçimi
  - Demo/Creative Commons içerik, yerel klasör tarama, M3U/Xtream ve XMLTV EPG rehberi
  - PIN korumalı profiller, yerel ağ eşleştirme ve bulut köprüsü (`/api/cloud/*`)
- **Web Arayüzü (`public/`):**
  - Masaüstü ve yerel ağ istemcileri için koyu sinema arayüzü, 2×2 çoklu ekran (Pro), hesap doğrulama, parola sıfırlama ve plan yönetimi
- **Windows Uygulaması (`desktop/vrelio_desktop.py`, `windows/`):**
  - PyInstaller tek dosya çalıştırılabilir paket (`Vrelio.exe`) ve Inno Setup kurulum sihirbazı (`Vrelio-Setup.exe`)
  - Uygulama içi sunucu iş parçacığı ve yerleşik tarayıcı yoksa yerel kontrol penceresi yedeği
- **Android Uygulaması (`android/` — `app.vrelio.player`):**
  - Kotlin, Jetpack Compose, Material 3 ve LibVLC oynatıcı motoru
  - Telefon ve tablet adaptif düzen, erişilebilir etiketli kontroller ve bulut doğrulama/plan akışları
- **macOS & iOS Uygulamaları (`apple/`, `macos/`, `ios/`):**
  - **macOS:** Yerel sunucu ve web arayüzünü paketleyen `Vrelio.app` / `Vrelio-macOS.dmg`
  - **iOS / iPadOS:** SwiftUI + `AVKit` (`AVPlayer`) tabanlı yerel oynatıcı ve `Vrelio-iOS.ipa`

## 2. Bulut Kontrol Katmanı & İki Katmanlı Plan Modeli

Vrelio bulut altyapısı iki eşlenik uygulama olarak çalışır: yerel/self-host için Python + SQLite (`cloud_admin.py`) ve üretim portalı için Netlify Functions + Postgres (`website/netlify/functions/cloud-core.mjs`).

### E-posta Doğrulama ve Güvenlik (R5)
- **Kayıt (`POST /api/v1/auth/register`):** Hesap `email_verified = false` ve `plan = 'normal'` olarak oluşturulur; 6 haneli doğrulama kodu ve güvenli belirteç yalnızca domain-ayrımlı SHA-256 özeti olarak saklanır ve yapılandırılmış SMTP / HTTP e-posta API'si (veya test/yerel ortamda `email_outbox`) üzerinden iletilir.
- **Doğrulama (`POST /api/v1/auth/verify-email`):** 5 deneme kilitli zaman-sabit doğrulama sonrası hesabı aktifleştirir ve ilk doğrulamada otomatik olarak **3 günlük (72 saat) Pro deneme** başlatır.
- **Parola Sıfırlama (`forgot-password`, `verify-reset-code`, `reset-password`):** E-posta ile 30 dakikalık sıfırlama kodu gönderir, parola güncellendiğinde `token_version` değerini artırarak tüm eski oturum anahtarlarını anında geçersiz kılar.

### Normal vs Pro Planlar (R4)
| Özellik | Normal Plan | Pro Plan (ve 3 Günlük Deneme) |
| :--- | :--- | :--- |
| Kayıtlı Cihaz Limiti | 1 cihaz | 5 cihaz (lisansla genişletilebilir) |
| Bulut Eşitleme (`/api/v1/sync`) | Kapalı (`403 PRO_REQUIRED`) | Açık |
| 2×2 Çoklu Ekran | Kapalı | Açık |
| Profiller & PIN Kilidi | Tek profil | Sınırsız profil & PIN koruması |
| XMLTV EPG & Gelişmiş İzler | Temel | Tam destek |

## 3. Yasal Konumlandırma & Gizlilik

- Vrelio telifli yayın veya IPTV aboneliği barındırmaz; kullanıcılar yalnızca yasal erişim hakkına sahip oldukları içerikleri oynatır.
- Bulut katmanı sıfır-bilgi (zero-knowledge) ilkesiyle M3U adreslerini veya medya sunucu parolalarını asla saklamaz.
- Gizlilik talepleri için `privacy@vrelio.app`, yasal/DMCA bildirimleri için `legal@vrelio.app` kullanılır.
