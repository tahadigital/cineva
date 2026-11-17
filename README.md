# Cineva

**Cineva**, kişisel medya arşivlerinizi, M3U/M3U8 oynatma listelerinizi, XMLTV EPG program rehberlerinizi ve açık lisanslı akışları tek bir modern arayüzde yönetip oynatmanızı sağlayan çoklu platform medya merkezidir.

> **Yasal Konumlandırma:** Cineva herhangi bir televizyon kanalı, telifli içerik veya yayın akışı barındırmaz ve satmaz. Uygulama içi ilk açılış demosu yalnızca açık kaynaklı Blender Vakfı Creative Commons filmlerinden oluşur.

## Klasör Yapısı

- `server.py`, `playback.py`, `m3u.py`, `discovery.py`, `sports.py`: Yerel medya sunucusu, M3U & XMLTV ayrıştırıcıları, FFmpeg remux/transcode motoru
- `public/`: Web & PWA arayüzü (`Cineva · Kişisel Medya Merkezi`)
- `android/`: Jetpack Compose & LibVLC Android (Telefon & Tablet adaptif arayüzlü) uygulama projesi (`app.cineva.player`)
- `native/CinevaApp.swift`: macOS yerel pencere sarmalayıcısı
- `legal/`: KVKK/GDPR uyumlu Gizlilik Politikası, Kullanım Koşulları ve Açık Kaynak Lisans bildirimleri
- `docs/MASTER_PLAN.md`: Küresel yayın, çoklu platform genişleme (Android Telefon/Tablet $\rightarrow$ Windows & Web $\rightarrow$ Apple) ve gelir mimarisi yol haritası

## Doğrulama Testleri

- Backend (Python): `python -m unittest discover -s tests`
- Web Frontend (Node.js): `node --test tests/test_*.mjs`
- Android (Gradle): `./gradlew :app:testDebugUnitTest :app:compileDebugAndroidTestKotlin`
