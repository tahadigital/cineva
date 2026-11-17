# Cineva

**Cineva**, kişisel medya arşivlerinizi, M3U/M3U8 oynatma listelerinizi, XMLTV EPG program rehberlerinizi ve açık lisanslı akışları tek bir modern arayüzde yönetip oynatmanızı sağlayan çoklu platform medya merkezidir.

> **Yasal Konumlandırma:** Cineva herhangi bir televizyon kanalı, telifli içerik veya yayın akışı barındırmaz ve satmaz. Uygulama içi ilk açılış demosu yalnızca açık kaynaklı Blender Vakfı Creative Commons filmlerinden oluşur.

## Klasör Yapısı

- `server.py`, `local_media.py`, `playback.py`, `m3u.py`, `discovery.py`, `sports.py`: Yerel medya sunucusu, yerel klasör tarayıcı & Range streaming, M3U & XMLTV EPG ayrıştırıcıları, profil/PIN yöneticisi ve FFmpeg remux/transcode motoru
- `public/`: Web & PWA arayüzü (Profiller, 2×2 Çoklu Ekran, Sürükle-Bırak dosya oynatma, oynatma hızı/uyku zamanlayıcısı/PiP/bölüm seçici)
- `desktop/` & `windows/`: Windows ve macOS/Linux için bağımsız çerçevesiz masaüstü başlatıcı (`desktop/cineva_desktop.py`, `windows/Cineva.bat`, PyInstaller `windows/cineva.spec`)
- `android/`: Jetpack Compose & LibVLC Android Telefon & Tablet adaptif uygulama projesi (`app.cineva.player`: PiP, çift dokunuş sarma, parlaklık/ses kaydırma, ekran kilidi, hız/oran, altyazı senkronu, profiller ve tablet 2-panelli görünüm)
- `native/CinevaApp.swift`: macOS yerel pencere sarmalayıcısı
- `.github/workflows/ci.yml`: Otomatik Python/Node/Android ve Windows standalone `.exe` derleme hattı
- `legal/`: KVKK/GDPR uyumlu Gizlilik Politikası, Kullanım Koşulları ve Açık Kaynak Lisans bildirimleri
- `docs/MASTER_PLAN.md`: Küresel yayın, çoklu platform genişleme (Android Telefon/Tablet -> Windows & Web -> Apple) ve gelir mimarisi yol haritası

## Hızlı Başlatma (Web / Masaüstü / Windows)

```bash
python desktop/cineva_desktop.py
```
Windows üzerinde tek tıkla başlatmak için `windows\Cineva.bat` dosyasını çalıştırabilir veya `pyinstaller windows\cineva.spec` ile taşınabilir `Cineva.exe` üretebilirsiniz.

## Doğrulama Testleri

- Backend (Python): `python -m unittest discover -s tests`
- Web Frontend (Node.js): `node --test tests/test_*.mjs`
- Android (Gradle): `./gradlew :app:testDebugUnitTest :app:compileDebugAndroidTestKotlin :app:lintDebug :app:assembleRelease`
