# Cineva

**Cineva**, kişisel medya arşivlerinizi, M3U/M3U8 oynatma listelerinizi, XMLTV EPG program rehberlerinizi ve açık lisanslı akışları tek bir modern arayüzde yönetip oynatmanızı sağlayan çoklu platform medya merkezidir.

> **Yasal Konumlandırma:** Cineva herhangi bir televizyon kanalı, telifli içerik veya yayın akışı barındırmaz ve satmaz. Uygulama içi ilk açılış demosu yalnızca açık kaynaklı Blender Vakfı Creative Commons filmlerinden oluşur.

## Klasör Yapısı

- `server.py`, `local_media.py`, `cloud_admin.py`, `playback.py`, `m3u.py`, `discovery.py`, `sports.py`: Yerel medya sunucusu, yerel klasör tarayıcı, bulut hesap/lisans kontrol sunucusu (`cloud_admin.py`), M3U & XMLTV EPG ayrıştırıcıları, profil/PIN yöneticisi ve FFmpeg motoru
- `website/`: Herkese açık **İndirme & Tanıtım Portalı** (`index.html`), **Yönetim Paneli** (`admin.html`), yasal sayfalar (`privacy.html`, `terms.html`) ve Netlify ayarları (`netlify.toml`)
- `public/`: Web & PWA medya oynatıcı arayüzü (Profiller, 2×2 Çoklu Ekran, Sürükle-Bırak dosya oynatma, oynatma hızı/uyku zamanlayıcısı/PiP/bölüm seçici, isteğe bağlı bulut hesap bağlantısı)
- `desktop/` & `windows/`: Windows ve macOS/Linux başlatıcıları (`desktop/cineva_desktop.py`, `windows/Cineva.bat`, PyInstaller `windows/cineva.spec`, Inno Setup `windows/CinevaSetup.iss`)
- `android/`: Jetpack Compose & LibVLC Android Telefon & Tablet adaptif uygulama projesi (`app.cineva.player`: PiP, çift dokunuş sarma, parlaklık/ses kaydırma, ekran kilidi, hız/oran, altyazı senkronu, profiller, isteğe bağlı lisans senkronu ve tablet 2-panelli görünüm)
- `native/CinevaApp.swift`: macOS yerel pencere sarmalayıcısı
- `.github/workflows/ci.yml`: Otomatik testler, Android APK, Windows `Cineva.exe` + `Cineva-Setup.exe` derlemesi ve `v*` tag ile GitHub Release yayını

## Hızlı Başlatma

### 1. İndirme Web Sitesi & Yönetim Paneli (Admin)
```bash
python cloud_admin.py --port 8899
```
- **İndirme Sitesi:** `http://127.0.0.1:8899/`
- **Admin Paneli:** `http://127.0.0.1:8899/admin` *(İlk açılışta geçici yönetici parolası terminalde üretilir veya `CINEVA_ADMIN_PASSWORD` ile belirlenir)*

### 2. Masaüstü / Web Medya Uygulaması (Windows / Mac / Linux)
```bash
python desktop/cineva_desktop.py
```
Windows kurulum dosyaları (`Cineva.exe` ve `Cineva-Setup.exe`) GitHub'a `v2.0.0` etiketi gönderildiğinde [ci.yml](.github/workflows/ci.yml) tarafından otomatik derlenip GitHub Releases sayfasına yüklenir.

## Doğrulama Testleri

- Backend (Python): `python -m unittest discover -s tests`
- Web Frontend (Node.js): `node --test tests/test_*.mjs`
- Android (Gradle): `./gradlew :app:testDebugUnitTest :app:compileDebugAndroidTestKotlin :app:lintDebug :app:assembleRelease`
