# Mavie

**Mavie**, kişisel medya arşivlerinizi, M3U/M3U8 oynatma listelerinizi, XMLTV EPG program rehberlerinizi ve açık lisanslı akışları tek bir modern arayüzde yönetip oynatmanızı sağlayan **tamamen ücretsiz ve hesap gerektirmeyen** çoklu platform medya merkezidir.

> **Gizlilik ve Yasal Konumlandırma:** Mavie kişisel bir medya oynatıcıdır; herhangi bir televizyon kanalı, telifli içerik veya yayın akışı barındırmaz ve sağlamaz. Hesap, abonelik veya merkezi sunucu gerektirmez — medya kaynaklarınız ve izleme geçmişiniz yalnızca kendi cihazınızda saklanır.

## İndirme

Hazır kurulum dosyalarını her zaman en güncel haliyle ücretsiz olarak GitHub Releases üzerinden indirebilirsiniz:

- **Windows Kurulum Sihirbazı (`Mavie-Setup.exe`) & Taşınabilir (`Mavie.exe`):** [GitHub Releases](https://github.com/tahadigital/cineva/releases/latest)
- **Android APK (`Mavie-Android.apk` / `Mavie-Android.aab`):** [GitHub Releases](https://github.com/tahadigital/cineva/releases/latest)
- **macOS (`Mavie-macOS.dmg` / `Mavie-macOS.zip`):** [GitHub Releases](https://github.com/tahadigital/cineva/releases/latest)
- **iOS (`Mavie-iOS.ipa`):** [GitHub Releases](https://github.com/tahadigital/cineva/releases/latest)

## Özellikler

- **%100 Ücretsiz & Hesapsız:** Kayıt, giriş, abonelik veya lisans anahtarı yok — tüm özellikler kurulduğu anda herkese açık.
- **4 Platform Desteği:** Windows Masaüstü, Android (Telefon & Tablet 2-panelli arayüz), macOS (Native `.app`/`.dmg`) ve iOS / iPadOS (Native SwiftUI + AVKit).
- **Gelişmiş Oynatıcı:** LibVLC / AVKit / hls.js / FFmpeg motoru, PiP (resim içinde resim), oynatma hızı, ekran oranı, uyku zamanlayıcısı, çoklu ses/altyazı seçimi ve zaman kaydırma.
- **Yerel Medya & Sınırsız Profiller:** Bilgisayardaki yerel video klasörlerini tarama, sürükle-bırak oynatma, PBKDF2 PIN korumalı sınırsız profiller ve Çocuk Modu.
- **Keşif, Netflix Türkiye Top 10 & Kişisel Öneri Algoritması:** Cinemeta + Netflix Türkiye Top 10 listelerini yerel kütüphanenle otomatik eşleştirir; izleme sürene, tamamlama oranına ve favorilerine göre *Sana Özel* rafları üretir ve sevdiğin tür kategorilerini otomatik öne çıkarır (izleme geçmişi cihaz dışına çıkmaz).
- **2×2 Çoklu Ekran & Canlı Spor Ekranı / XMLTV EPG:** Web/Masaüstü arayüzünde aynı anda 4 canlı yayını tek ızgarada izleme; tüm 4 platformda sıfır ayar ile çalışan **Spor Ekranı** maç rehberi, kanal eşleştirme ve isteğe bağlı XMLTV EPG desteği.
- **Yerel Ağ (LAN) Eşitleme & JSON Yedek:** Aynı Wi-Fi ağındaki cihazlar arasında 6 haneli kodla veya JSON dosyasıyla çevrimdışı kütüphane aktarımı.

## Kaynaktan Çalıştırma

### Masaüstü / Web Uygulaması (Windows / Mac / Linux)
```bash
python3 desktop/mavie_desktop.py
```

### Android
`android/` dizinindeki Gradle projesini Android Studio ile açabilir veya komut satırından derleyebilirsiniz:
```bash
cd android && ./gradlew :app:assembleDebug
```

## Doğrulama Testleri

- Backend (Python): `python3 -m unittest discover -s tests -v`
- Web & Site (Node.js): `node --test tests/test_*.mjs`
- Android (Gradle): `./gradlew :app:testDebugUnitTest :app:lintDebug`
