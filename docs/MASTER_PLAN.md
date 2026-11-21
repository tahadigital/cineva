# Mavie — Çoklu Platform Mimari ve Ürün Planı

Mavie, yerel medya arşivlerini, kullanıcıların kendi sağladığı M3U/M3U8 oynatma listelerini, XMLTV EPG rehberlerini ve açık lisanslı yayınları Windows, Android, macOS ve iOS üzerinde oynatmak için tasarlanmış **tamamen ücretsiz, hesap gerektirmeyen ve yerel öncelikli (local-first)** bir medya merkezidir.

## 1. Platform Mimarisi

- **Yerel Medya Motoru (`server.py`, `playback.py`, `discovery.py`, `local_media.py`, `m3u.py`, `sports.py`):**
  - Python HTTP sunucusu ve SQLite yerel durum yönetimi
  - FFmpeg ile HLS remux/transcode ve çoklu ses/altyazı seçimi
  - Demo/Creative Commons içerik, yerel klasör tarama, M3U/Xtream ve XMLTV EPG & Spor rehberi
  - Sınırsız PBKDF2 PIN korumalı profiller, Çocuk Modu, 2×2 Çoklu Ekran, yerel ağ (LAN) eşleştirme ve JSON yedekleme
- **Web Arayüzü (`public/`):**
  - Masaüstü ve yerel ağ istemcileri için mor–mavi–turkuaz sinema arayüzü, 2×2 çoklu ekran, profil yönetimi ve LAN paylaşımı
- **Windows Uygulaması (`desktop/mavie_desktop.py`, `windows/`):**
  - PyInstaller tek dosya çalıştırılabilir paket (`Mavie.exe`) ve Inno Setup kurulum sihirbazı (`Mavie-Setup.exe`)
  - Uygulama içi sunucu iş parçacığı ve yerleşik tarayıcı yoksa yerel kontrol penceresi yedeği
- **Android Uygulaması (`android/` — `app.mavie.player`):**
  - Kotlin, Jetpack Compose, Material 3 ve LibVLC oynatıcı motoru
  - Telefon ve tablet adaptif düzen, erişilebilir etiketli kontroller, LAN eşitleme ve JSON yedekleme
- **macOS & iOS Uygulamaları (`apple/`):**
  - **macOS (`app.mavie.macos`):** Yerel sunucu ve web arayüzünü paketleyen `Mavie.app` / `Mavie-macOS.dmg` / `Mavie-macOS.zip`
  - **iOS / iPadOS (`app.mavie.ios`):** SwiftUI + `AVKit` (`AVPlayer`) tabanlı yerel oynatıcı ve `Mavie-iOS.ipa`

## 2. Tamamen Ücretsiz & Hesapsız Model

- Mavie'de kullanıcı hesabı, e-posta doğrulama, abonelik planı, lisans anahtarı veya yönetim paneli bulunmaz.
- Tüm özellikler (sınırsız profil + PIN + Çocuk Modu, 2×2 Çoklu Ekran, XMLTV EPG & Spor Rehberi, gelişmiş ses/altyazı kontrolü, LAN eşitleme ve JSON yedekleme) tüm 4 platformda kurulduğu andan itibaren herkese ücretsiz ve sınırsız olarak açıktır.
- Web sitesi (`website/`) statik olarak Netlify üzerinde yayınlanır ve 4 platformun güncel GitHub Releases paketlerine doğrudan bağlantı sunar.

## 3. Yasal Konumlandırma & Gizlilik

- Mavie telifli yayın veya IPTV aboneliği barındırmaz; kullanıcılar yalnızca yasal erişim hakkına sahip oldukları içerikleri oynatır.
- Merkezi kullanıcı veritabanı veya bulut takibi yoktur; tüm medya kaynakları, favoriler ve izleme geçmişi yalnızca kullanıcının kendi cihazında saklanır.
- Gizlilik talepleri için `privacy@mavie.app`, yasal/DMCA bildirimleri için `legal@mavie.app` kullanılır.
