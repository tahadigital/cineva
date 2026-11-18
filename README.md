# Cineva

**Cineva**, kişisel medya arşivlerinizi, M3U/M3U8 oynatma listelerinizi, XMLTV EPG program rehberlerinizi ve açık lisanslı akışları tek bir modern arayüzde yönetip oynatmanızı sağlayan çoklu platform medya merkezidir.

> **Gizlilik ve Yasal Konumlandırma:** Cineva kişisel bir medya oynatıcıdır; herhangi bir televizyon kanalı, telifli içerik veya yayın akışı barındırmaz ve sağlamaz. Medya kaynaklarınız ve izleme geçmişiniz yalnızca kendi cihazınızda saklanır.

## İndirme

Hazır kurulum dosyalarını her zaman en güncel haliyle GitHub Releases üzerinden indirebilirsiniz:

- **Windows Kurulum Sihirbazı (`Cineva-Setup.exe`) & Taşınabilir (`Cineva.exe`):** [GitHub Releases](https://github.com/tahadigital/cineva/releases/latest)
- **Android APK (`Cineva-Android.apk`):** [GitHub Releases](https://github.com/tahadigital/cineva/releases/latest)

## Özellikler

- **Çoklu Platform:** Android (Telefon & Tablet 2-panelli arayüz), Windows Masaüstü ve Web/macOS
- **Gelişmiş Oynatıcı:** LibVLC / hls.js motoru, PiP (resim içinde resim), oynatma hızı, ekran oranı, uyku zamanlayıcısı, çoklu ses/altyazı seçimi ve zaman kaydırma
- **Yerel Medya & Profiller:** Bilgisayardaki yerel video klasörlerini tarama, sürükle-bırak oynatma, PIN korumalı profiller ve Çocuk Modu
- **2×2 Çoklu Ekran:** Web arayüzünde aynı anda 4 adede kadar yayını bölünmüş ekranda izleme

## Kaynaktan Çalıştırma

### Masaüstü / Web Uygulaması (Windows / Mac / Linux)
```bash
python desktop/cineva_desktop.py
```

### Android
`android/` dizinindeki Gradle projesini Android Studio ile açabilir veya komut satırından derleyebilirsiniz:
```bash
cd android && ./gradlew :app:assembleDebug
```

## Doğrulama Testleri

- Backend (Python): `python -m unittest discover -s tests -v`
- Web Frontend (Node.js): `node --test tests/test_*.mjs`
- Android (Gradle): `./gradlew :app:testDebugUnitTest :app:lintDebug`
