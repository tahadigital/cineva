# Mavie — Akıllı TV & Samsung Tizen (TU8500) Mimari, Kurulum ve Yayın Rehberi

Bu rehber, **Mavie** medya merkezini televizyonlara — öncelikli olarak **Samsung Smart TV (özellikle 2020 model TU8500 serisi)** — hangi mimariyle çıkarmamız gerektiğini, evdeki televizyona **ücretsiz ve güvenli biçimde nasıl yüklenip kullanılacağını**, mağazada herkese açık nasıl yayınlanacağını ve diğer TV platformlarının (LG webOS, Android TV / Google TV, Apple TV) mevcut Mavie kod tabanına göre gerçek hazırlık durumunu adım adım açıklar.

> **Kısa Özet (Başlamadan Önce Bilmeniz Gereken 4 Şey)**
> 1. Evdeki **Samsung TU8500** serisi (2020 Crystal UHD), **Tizen 5.5** işletim sistemi çalıştırır. Android değildir; bu yüzden `Mavie-Android.apk` bu TV'ye yüklenemez.
> 2. Samsung TV uygulamaları **`.wgt`** (Tizen Web Uygulaması — HTML/CSS/JS + Samsung donanımsal **AVPlay** oynatıcı) biçiminde paketlenir.
> 3. **Tam model kodunu öğrenmek başlamak için zorunlu değildir**; tüm TU8500 boyutları (`43"`, `50"`, `55"`, `65"`) aynı Tizen 5.5 platformunu paylaşır. Sadece kurulum aşamasında TV'nin yerel IP adresini ve isteğe bağlı olarak yazılım sürümünü menüden kontrol etmek yeterlidir.
> 4. Evdeki TV'ye mağaza onayı beklemeden **ücretsiz kurulum (sideloading)** mümkündür: TV'de kumandadan `12345` ile **Geliştirici Modu (Developer Mode)** açılır ve bilgisayardan 1–2 dakikada `.wgt` paketi yüklenir.

---

## 1. Evdeki Samsung TU8500 Nasıl Çalışır?

### 1.1. Donanım ve İşletim Sistemi Özeti

| Özellik | Samsung TU8500 (2020 Crystal UHD — `20TV_STANDARD`) |
| --- | --- |
| **Model Ailesi Örnekleri** | `UE43TU8500`, `UE50TU8500`, `UE55TU8500`, `UE65TU8500` (TR bölge kodu genellikle `UXTK`) |
| **İşletim Sistemi** | **Tizen 5.5** (Linux tabanlı Samsung TV işletim sistemi) |
| **Yerleşik Web Motoru** | **Chromium M69** (`69.0.3497.xxx` eşdeğeri — sabit kalır, yeni Chrome sürümüne yükselmez) |
| **Uygulama Paketi Formatı** | **`.wgt`** (dijital imzalı W3C Web Widget / Tizen Web App) |
| **Önerilen Oynatıcı Motoru** | **Samsung AVPlay API** (`webapis.avplay`) — donanımsal 4K video/ses çözme |
| **Android APK Desteği** | **Yok** (Tizen, Android/Google Play ekosisteminden tamamen ayrıdır) |

### 1.2. Neden Android APK Çalışmaz ve `.wgt` Formatı Nedir?

- **Android APK neden çalışmaz?** Android TV / Google TV cihazları Android işletim sistemi ve Dalvik/ART çalışma zamanı kullanır. Samsung televizyonlar ise kendi **Tizen OS** işletim sistemini kullanır; bu yüzden Android uygulama paketleri (`.apk` / `.aab`) Samsung TV tarafından tanınmaz.
- **`.wgt` nedir?** Bir `.wgt` dosyası, temelinde `index.html`, JavaScript, CSS, uygulama simgeleri ve izinleri tanımlayan `config.xml` dosyasını içeren, Samsung geliştirici/dağıtım sertifikasıyla imzalanmış bir ZIP arşividir. Web teknolojileriyle yazılmasına rağmen standart bir web sitesinden çok daha yeteneklidir: Samsung'un donanımsal **AVPlay** medya motoruna, kumanda tuşlarına (`tvinputdevice`), ekran koruyucu yönetimine ve CORS kısıtı olmadan dış akışlara doğrudan erişebilir.

### 1.3. Kritik Teknik Kısıt: Chromium M69 ve Mevcut `public/` Kod Tabanı Denetimi

Tizen 5.5'teki web motoru **Chromium M69** sürümüne sabitlidir. Bu sürüm 2018 sonu web standartlarını destekler; daha yeni JavaScript sözdizimlerini (özellikle Chromium 80'de gelen **optional chaining `?.`** ve **nullish coalescing `??`**) çalıştıramaz ve dosya ayrıştırılırken doğrudan **`SyntaxError`** fırlatır. *(Not: Runtime polyfill kütüphaneleri `SyntaxError`'ı çözemez; kodun derleme aşamasında ES2018 / `chrome69` hedefine dönüştürülmesi — transpile edilmesi — zorunludur.)*

Mavie'nin mevcut web arayüzü (`public/`) üzerinde yapılan statik kod denetiminin gerçek sonuçları:

| Katman | Mevcut Kod Tabanı Bulgusu (`public/`) | Chromium M69 (TU8500) Etkisi | Çözüm |
| --- | --- | --- | --- |
| **JavaScript Sözdizimi** | `public/app.js` içinde **172** `?.`, **10** `??`, **2** `Object.fromEntries`, **3** `flat/flatMap`; `public/tracks.js` içinde **41** `?.`; `public/experience.js` içinde **19** `?.`; `public/sports.js` içinde **2** `?.`, **1** `Object.fromEntries` | **Kritik:** Dönüştürülmeden çalıştırılırsa `SyntaxError` verir ve uygulama hiç başlamaz | Derleme hattında (esbuild / Babel / TypeScript) `target: es2018` / `chrome69` transpile + `Object.fromEntries` / `flat` polyfill |
| **HLS Kütüphanesi** | `public/vendor/hls.min.js` (**hls.js 1.7.3**): `0` adet `?.`, `0` adet `??`, yalnızca güvenli geri dönüşlü `globalThis` kontrolü | **Uyumlu:** Sözdizimi M69'da ayrıştırılabilir; ancak canlı IPTV / 4K için AVPlay çok daha verimlidir | Tizen `.wgt` içinde birincil oynatıcı olarak **AVPlay**, yedek/tarayıcı testi için `hls.js` |
| **CSS Özellikleri** | 4 stil dosyasında (`styles.css`, `cinema.css`, `player.css`, `sports.css`) toplam **174** `gap` (Flexbox `gap` Chrome 84), **11** `aspect-ratio` (Chrome 88), **24** `inset` (Chrome 87), **35** `clamp()` (Chrome 79), **6** `:has()` (Chrome 105), **21** `dvh/svh` (Chrome 108) ve kısmen prefix'siz `backdrop-filter` (Chrome 76) | **Görsel Bozulma:** Kart aralıkları, en-boy oranları ve modal yerleşimleri bozulur | TV için M69 uyumlu ayrı bir **10-foot CSS katmanı** (`margin`, `top/left/right/bottom`, `-webkit-backdrop-filter` veya düşük maliyetli yarı saydam yüzeyler) |
| **Kumanda (D-Pad)** | `public/app.js` içinde yalnızca oynatıcı açıkken `ArrowLeft/Right` (10 sn sarma) ve `ArrowUp/Down` (ses) klavye dinleyicisi var; ana menü ve kart raflarında 2B D-Pad odak gezintisi (spatial navigation) yok | **Kullanım Zorluğu:** Kumanda ok tuşlarıyla kartlar ve sekmeler arasında gezinilemez | TV'ye özel 2B odak yöneticisi (spatial navigation) + Tizen `10009` (Geri) yığını |

### 1.4. Donanımsal Video/Ses Desteği ve Samsung AVPlay API

TU8500 üzerinde HTML5 `<video>` etiketi yerine **`$WEBAPIS/webapis/webapis.js`** üzerinden erişilen **Samsung AVPlay API (`webapis.avplay`)** kullanıldığında TV'nin donanımsal 4K çözücüleri devreye girer:

- **Desteklenen Video Kodekleri (2020 UHD Donanım Profili):**
  - **H.264 / AVC:** High Profile, 4K UHD @ 30fps / 1080p FHD @ 60fps
  - **HEVC / H.265:** Main & Main 10 Profile (HDR10 / HLG), **4K UHD @ 60fps**
  - **VP9:** Profile 0 & Profile 2, 4K UHD @ 60fps
  - **AV1:** 4K UHD @ 30/40fps (2020 donanım profil sınırları dahilinde)
  - **Diğer:** MPEG-2, MPEG-4, VC-1 (WMV9)
- **Desteklenen Ses Kodekleri:**
  - **Dolby Digital (AC3)**, **Dolby Digital Plus (EAC3 / DD+)**, **Dolby AC-4**, **AAC / HE-AAC**, **MP3**, **LPCM**, **Opus**, **FLAC**
  - **Önemli Not (DTS Kısıtı):** Samsung'un 2018 sonrası tüm modellerinde olduğu gibi TU8500 de **DTS** ses kodeğini donanımsal olarak çözmez. Bu tür MKV film dosyaları için Mavie'nin **Ev Sunucusu (Companion)** modundaki mevcut **FFmpeg** motoru, videoyu yeniden kodlamadan (copy) yalnızca DTS sesi anında AAC/AC3'e çevirerek (remux/audio transcode) kesintisiz oynatma sağlar.
- **Konteyner, Akış ve Altyazı Desteği (AVPlay):**
  - **HLS (`.m3u8`)** ve **MPEG-TS (`.ts`)** canlı IPTV yayınları donanımsal çözülür.
  - **MP4** ve **MKV** dosyaları desteklenir.
  - Gömülü çoklu ses ve altyazı parçaları `webapis.avplay.getTotalTrackInfo()` ve `webapis.avplay.setSelectTrack('AUDIO' | 'TEXT', index)` ile değiştirilebilir; harici `.srt`/`.vtt` altyazılar `webapis.avplay.setExternalSubtitlePath(url)` ile yüklenebilir.

### 1.5. Kumanda Tuş Kodları (`tvinputdevice`) ve Ekran Koruyucu

Tizen TV'de kumanda tuşları iki gruba ayrılır:

- **Otomatik Gelen Zorunlu Tuşlar:** `ArrowLeft` (37), `ArrowUp` (38), `ArrowRight` (39), `ArrowDown` (40), `Enter/OK` (13) ve **`Back/Return` (10009)** — kayıt gerekmeden doğrudan `keydown` olayına düşer.
- **Kayıt Gerektiren Ek Tuşlar:** `config.xml` içine `<tizen:privilege name="http://tizen.org/privilege/tv.inputdevice"/>` izni eklenir ve açılışta `tizen.tvinputdevice.registerKeyBatch(...)` ile kaydedilir:
  - **`MediaPlayPause` (`10252`)** — Samsung Smart Remote üzerindeki tekli Oynat/Duraklat tuşu
  - **`MediaPlay` (`415`)**, **`MediaPause` (`19`)**, **`MediaStop` (`413`)**, **`MediaRewind` (`412`)**, **`MediaFastForward` (`417`)**
  - **`ChannelUp` (`427`)**, **`ChannelDown` (`428`)** — Canlı TV'de kanal zapping için ideal
  - **`ColorF0Red` (`403`)**, **`ColorF1Green` (`404`)**, **`ColorF2Yellow` (`405`)**, **`ColorF3Blue` (`406`)** — Hızlı favori/ses/altyazı kısayolları
- **`Exit` (`10182`) Tuşu Kuralı:** `Exit` tuşunu `registerKeyBatch` ile kaydetmemeniz önerilir; böylece Tizen işletim sistemi kumandadaki fiziksel Exit tuşuna basıldığında uygulamayı doğal biçimde kapatır (kaydedip `keydown` içinde `exit()` çağırmamak tuşu yutar ve Samsung Seller Office QA reddine yol açar).
- **Ekran Koruyucu Kontrolü:** Uzun film/maç izlerken TV'nin ekran koruyucuya geçmesini engellemek için oynatma başladığında `webapis.appcommon.setScreenSaver(webapis.appcommon.AppCommonScreenSaverState.SCREEN_SAVER_OFF)`, duraklatıldığında/çıkıldığında `SCREEN_SAVER_ON` çağrılır.

### 1.6. Tam Model Kodunu Öğrenmek Gerekir mi? Nasıl Bakılır?

- **Gerekli mi?** Hayır — mimari tasarım ve geliştirme için **"TU8500"** bilgisi yeterlidir; 43" ile 65" arasındaki tüm TU8500 varyantları aynı **Tizen 5.5 / Chromium M69 / AVPlay** altyapısını kullanır.
- **Yine de teyit etmek ve kuruluma hazırlanmak için TV'den şu iki bilgiye bakmanız faydalıdır (30 saniye):**
  1. **Tam Model & Yazılım Sürümü:** Kumandadan **Ayarlar (Dişli) → Destek → Bu TV Hakkında** (*Settings → Support → About This TV*) menüsünü açın. **Model Kodu** (örn. `UE55TU8500UXTK`) ve **Yazılım Sürümü** satırlarını görün.
  2. **TV'nin Yerel IP Adresi:** **Ayarlar → Genel → Ağ → Ağ Durumu → IP Ayarları** menüsünden TV'nin `192.168.x.x` IP adresini not edin (Adım 3'teki kurulumda kullanacağız).

---

## 2. Mavie'yi Samsung TV'ye Nasıl Çıkarmalıyız? (3 Pratik Mimari Model)

Mavie için tek bir büyük adıma zorlamak yerine, birbirinin üzerine kurulan **3 aşamalı** en verimli ürün stratejisi şöyledir:

| Aşama | Yaklaşım | PC Gerekli mi? | Kumanda & Video Kalitesi | Önerilen Rol |
| --- | --- | --- | --- | --- |
| **Aşama 0 (Hazır)** | TV Yerleşik Tarayıcıdan `http://<PC-IP>:8844/tv` (M69-uyumlu 10-foot TV arayüzü) | Evet (PC/Mac açık olmalı) | Yüksek (ES2018 + M69 CSS + D-Pad odak + HTML5/hls.js) | Kurulumsuz anında kullanım (Hisense/Vestel/TU8500 tarayıcı) |
| **Aşama 1 (Hazır — Önerilen)** | **Samsung Tizen `Mavie-Tizen.wgt` + AVPlay** & **LG webOS `Mavie-webOS.ipk`** (Bağımsız + Ev Sunucusu çift mod) | **Hayır** (Bağımsız modda PC kapalıyken çalışır; yerel MKV/DTS için opsiyonel PC) | **Mükemmel** (Gerçek D-Pad 10-foot arayüz + donanımsal 4K AVPlay) | **Evdeki TU8500 & LG TV için ana paketler** |
| **Aşama 2** | **Samsung Apps Store (Seller Office)** & **LG Content Store** resmî yayın | Hayır | Mükemmel (mağazadan tek tık kurulum + otomatik güncelleme) | Herkese açık genel dağıtım |

### Hızlı Başlangıç: Hazır Paketleri Derleme ve Kurma

Mavie'nin çoklu TV paketi artık doğrudan depo içinden tek komutla üretilir (harici SDK veya pip paketi gerektirmez):

```bash
# 1) Samsung Tizen (.wgt) ve LG webOS (.ipk) paketlerini üret
python3 tv/build_tv_packages.py
# Çıktılar:
#   dist/Mavie-Tizen.wgt  (Samsung Tizen 5.5+ / TU8500)
#   dist/Mavie-webOS.ipk  (LG webOS 4.0+)

# 2) Samsung TU8500'e tek komutla yükle (Developer Mode 12345 açıkken)
./tv/tizen/install-tizen.sh <TV_IP_ADRESI> [SERTIFIKA_PROFILI]

# veya Docker ile:
docker build -f tv/tizen/Dockerfile -t mavie-tizen .
docker run --rm --network host -e TIZEN_PROFILE=MavieProfile mavie-tizen <TV_IP_ADRESI>

# 3) LG webOS TV'ye yükle (Developer Mode açıkken)
./tv/webos/install-webos.sh lgtv
```

Kurulumsuz anında denemek için bilgisayarınızda Mavie'yi açıp aynı Wi-Fi'deki herhangi bir TV tarayıcısından **`http://<BILGISAYAR-IP>:8844/tv`** adresine girmeniz yeterlidir.

---

### Aşama 0: Kurulumsuz Yerel Ağ Erişimi (`http://<PC-IP>:8844/tv`)

Mavie'nin yerel sunucusu (`server.py`) varsayılan olarak **`0.0.0.0:8844`** adresinde çalışır ve **Chromium M69 (TU8500) + LG webOS 4.0+** uyumlu özel 10-foot arayüzünü doğrudan **`/tv`** rotasında sunar (`tv/src/`).

- **Nasıl kullanılır?**
  1. Bilgisayarda Mavie'yi başlatın (Windows'ta `Mavie.exe`, `Mavie.exe --web` veya `Mavie.exe --serve`; macOS'ta `Mavie.app`).
  2. Aynı Wi-Fi/Ethernet ağındaki televizyonun yerleşik tarayıcısından (Samsung Internet, LG Tarayıcı, Hisense VIDAA, Vestel) adres çubuğuna **`http://<BILGISAYAR-IP>:8844/tv`** (ör. `http://192.168.1.35:8844/tv`) yazın.
- **Neden `/tv` rotası?** Ana masaüstü arayüzü (`public/`) modern ES2020 sözdizimi kullandığı için 2020 TU8500 (Chromium M69) tarayıcısında hata verir; buna karşılık **`/tv` rotası** sıfır `?.`/`??`, sıfır flexbox `gap` ve yerleşik 2B kumanda odak motoruyla TU8500 dahil eski/yeni tüm akıllı TV tarayıcılarında doğrudan açılır.
- **Artıları:** TV'ye paket kurmadan anında çalışma; bilgisayardaki FFmpeg motorunun DTS/MKV dosyalarını uyumlu akışa çevirmesi.
- **Eksileri:** PC/Mac açık kalmalıdır; tam donanımsal Samsung AVPlay ve PC kapalıyken bağımsız çalışma için `Mavie-Tizen.wgt` (Aşama 1) önerilir.

---

### Aşama 1 (Önerilen Gerçek Çözüm): Tizen `.wgt` Uygulaması + AVPlay (Çift Modlu Mimari)

Samsung Smart Hub ana ekranında kendi **Mavie** logosuyla duran, kumandayla Netflix/YouTube kalitesinde kontrol edilen **gerçek Tizen `.wgt` uygulaması**. Tek kod tabanı içinde kullanıcıya iki tamamlayıcı mod sunar:

#### Mod 1: Bağımsız (Standalone) Mod — Bilgisayar Kapalıyken Bile Çalışır
- **Neden mümkün?** Tizen `.wgt` uygulamalarında `config.xml` içine `<access origin="*" subdomains="true"/>` ve `<tizen:privilege name="http://tizen.org/privilege/internet"/>` eklendiğinde uygulama, normal web tarayıcılarındaki CORS engeline takılmadan doğrudan M3U/M3U8, Xtream Codes API, XMLTV EPG, Cinemeta keşif ve Spor Ekranı kaynaklarını TV içinden çekebilir.
- **Kumandayla URL Yazma Derdine Son (QR Kod + 6 Haneli Eşleştirme):** TV kumandasıyla 80 karakterlik M3U/Xtream linki yazmak pratik değildir. İlk kurulum ekranında Mavie TV bir **QR Kod ve kısa eşleştirme kodu** gösterir:
  - Kullanıcı telefonundan QR kodu okutarak (veya mevcut Mavie Android/iOS/Masaüstü uygulamasındaki **6 haneli LAN Eşitleme** akışıyla) M3U/Xtream kaynaklarını, profillerini ve favorilerini saniyeler içinde TV'ye aktarır.
- **Donanımsal AVPlay Oynatıcı:** Canlı TV (`.m3u8`, `.ts`), film/dizi (`.mp4`, `.mkv`, H.264/HEVC 4K, AC3/EAC3) ve çoklu ses/altyazı seçimi doğrudan TV çipinde donanımsal çözülür; bilgisayar kapalıyken bile akıcı izleme sağlanır.
- **Yerel Saklama:** Profiller, PIN koruması, Çocuk Modu, favoriler ve izleme geçmişi yalnızca TV'nin kendi `localStorage` / `IndexedDB` alanında (hesapsız ve ücretsiz) tutulur.

#### Mod 2: Ev Sunucusu (Companion) Modu — PC/Mac'teki Mavie ile Güç Birliği
- Kullanıcı isterse Ayarlar'dan (veya tek QR taramasıyla) ev ağındaki `http://<PC-IP>:8844` Mavie sunucusunu bağlar.
- **Kazandırdıkları:**
  - Bilgisayardaki yerel **MKV/MP4/AVI** klasörleri doğrudan TV'de görünür.
  - TU8500'ün donanımsal desteklemediği **DTS sesli** veya nadir kodekli arşiv dosyaları, PC'deki Mavie **FFmpeg** motoruyla anında uyumlu HLS'e dönüştürülerek oynatılır.
  - Bilgisayar, telefon ve TV arasında "İzlemeye Devam Et", favoriler ve kütüphane otomatik eşitlenir.

---

### Aşama 2: Herkese Açık Yayın — Samsung Apps Store (Samsung Seller Office)

Uygulamayı yalnızca evinizde değil, tüm Samsung TV sahiplerinin **Samsung Apps (Smart Hub)** mağazasından ücretsiz indirebilmesini istediğinizde izlenecek resmî süreçtir:

1. **Hesap ve Bölge Yetkisi (Partner Seller):**
   - [Samsung TV Seller Office](https://seller.samsungapps.com/tv) hesabı açılır (ücretsizdir).
   - Standart satıcı hesapları varsayılan olarak yalnızca **ABD** mağazasına yayın açar; **Türkiye, Avrupa ve küresel dağıtım** için Seller Office içinden **Partner Seller** yetkisi talep edilmelidir.
2. **IPTV / Medya Oynatıcı Politika Uyumu (Mavie'nin Güçlü Yönü):**
   - Samsung, içinde telifli/korsan kanal listesi gömülü uygulamaları kesin olarak reddeder. Mavie'nin **"hiçbir yayın veya kanal barındırmayan, tamamen kullanıcı kaynaklı ücretsiz kişisel oynatıcı"** modeli politika açısından en temiz konumlandırmadır; bu uyarı hem mağaza açıklamasında hem uygulamanın ilk açılışında açıkça yer almalıdır.
   - **Çalışan Demo / Test İçeriği Şartı:** Açılışta bomboş ekran veya giriş duvarı gösteren oynatıcılar Samsung QA ekibinden red yer. Mavie'de zaten bulunan **açık lisanslı Demo / Creative Commons kataloğu** (ve Seller Office *Test Environment* bölümüne eklenecek çalışan örnek akış URL'si) QA ekibinin oynatıcıyı anında doğrulamasını sağlar.
3. **Zorunlu Kumanda ve UX Sertifikasyon Kuralları (En Sık Red Sebepleri):**
   - **Geri (`Return` / `10009`) Tuşu:** Alt ekranlarda bir önceki ekrana dönmelidir. **Ana ekranda Geri tuşuna basıldığında uygulama hemen kapanmamalı**, HTML tabanlı *"Mavie'den çıkmak istiyor musunuz? (Evet / Hayır)"* onay kutusu açılmalı ve yalnızca **Evet** seçildiğinde `tizen.application.getCurrentApplication().exit()` çağrılmalıdır.
   - **Uzun Basma Kuralı:** `Return`/`Exit` tuşuna uzun basma davranışına özel kod yazılmamalıdır (Tizen sistemi bunu zorla kapatma için kendisi yönetir).
   - **10-Foot Odak ve Ağ Hatası Yönetimi:** Her etkileşimli eleman kumandayla ulaşılabilir ve belirgin odak halkasına sahip olmalıdır; internet koptuğunda uygulama kilitlenmemeli, anlaşılır hata + "Yeniden Dene" seçeneği göstermelidir.
4. **Başvuru Belgeleri & İnceleme:**
   - Resmî **Application UI Description** belgesi (ekran akış şeması, tuş eşlemeleri, test adımları) yüklenir.
   - İmzalı `.wgt` paketi önce otomatik **Pre-Test** kontrolünden, ardından Samsung insan QA testinden (2020+ Tizen modelleri dahil) geçerek mağazada yayınlanır.

---

## 3. Evdeki Samsung TU8500'e Uygulama Nasıl Yüklenir? (Adım Adım Ücretsiz Sideloading Rehberi)

Samsung mağazasına başvurmadan, tamamen ücretsiz olarak kendi evinizdeki TU8500 televizyona Mavie `.wgt` paketini yüklemek için izlenecek adımlar şöyledir. İlk kurulum ortalama **5–10 dakika**, sonraki güncellemeler **30 saniye** sürer.

### Ön Koşullar
- Bilgisayarınız (Mac, Windows veya Linux) ile Samsung TU8500 **aynı yerel ağa** (aynı modem/Wi-Fi veya Ethernet) bağlı olmalıdır.
- TV'de ücretsiz bir **Samsung Hesabı** ile oturum açılmış olmalıdır (**Ayarlar → Genel → Sistem Yöneticisi → Samsung Hesabı**).
- Bilgisayarınızın yerel IP adresini öğrenin (macOS: *Sistem Ayarları → Ağ*, Windows: `ipconfig` → `IPv4 Address`, örn. `192.168.1.35`).

---

### Adım 1: TV'de Geliştirici Modunu (Developer Mode) Açma (`12345`)

1. Kumandadan **Home (Ev)** tuşuna basıp **Apps (Uygulamalar)** ekranına girin.
2. Apps ekranındayken kumandadan rakam tuş takımını açın (`123` tuşu veya sayısal tuşlar) ve hızlıca **`1` `2` `3` `4` `5`** tuşlayın.
3. Ekranda gizli **Developer Mode** penceresi açılacaktır.
4. **Developer Mode** anahtarını **Açık (On)** konumuna getirin.
5. **Host PC IP** alanına bilgisayarınızın yerel IP adresini yazın (örn. `192.168.1.35`) ve **Tamam (OK)** deyin.
6. **TV'yi tamamen yeniden başlatın:** Kumandadaki Güç (Power) tuşuna Samsung logosu ekrana gelene kadar ~4–5 saniye basılı tutun (veya fişini çekip 10 saniye bekleyip takın; normal tek basış TV'yi sadece uykuya alır!).
7. TV açılıp tekrar **Apps** ekranına girdiğinizde üst bölümde kırmızı **"Developer Mode"** şeridi görünüyorsa TV yüklemeye hazırdır.

---

### Adım 2: `.wgt` Paketini TV'ye Yükleme (3 Yöntem)

#### Yöntem A — Resmî ve Tam Kontrollü Yöntem: Tizen Studio CLI + Samsung Certificate Extension
Geliştirme yaparken (kodu derleyip doğrudan TU8500'e atmak için) en güvenilir yoldur:

1. Bilgisayarınıza **Tizen Studio** (veya daha hafif olan **Tizen Studio CLI**) kurun.
2. **Package Manager**'ı açın:
   - *Main SDK* sekmesinden **TV Extensions** (ve CLI araçları / `sdb`),
   - *Extension SDK* sekmesinden **Samsung Certificate Extension** paketlerini kurun.
3. Bilgisayardan TV'ye SDB (*Smart Development Bridge*, varsayılan port `26101`) ile bağlanın:
   ```bash
   sdb connect <TV_IP_ADRESI>
   sdb devices
   ```
4. TV'nin **DUID (Cihaz Benzersiz Kimliği)** kodunu alın:
   - GUI: Tizen Studio → *Device Manager* → TV'nize sağ tık → **Permit to Install Applications** (DUID otomatik kopyalanır).
   - CLI: `sdb shell 0 getduid`
5. **Sertifika Profili Oluşturun (Ücretsiz, 1 kez):**
   - Tizen Studio → *Certificate Manager* → `+` → **Samsung** → **TV** seçin.
   - Ücretsiz Samsung Hesabınızla giriş yapın ve 4. adımda aldığınız TV **DUID** kodunu ekleyin. Bu işlem cihazınıza özel **Author** ve **Distributor** (`.p12`) sertifikalarını oluşturur.
6. Mavie `.wgt` paketini imzalayıp TV'ye yükleyin:
   ```bash
   tizen build-web -- ./tv/tizen
   tizen package -t wgt -s MavieProfile -- ./tv/tizen/.buildResult
   tizen install -n Mavie.wgt -t <TV_DEVICE_ID>
   ```
   Kurulum tamamlandığında **Mavie** ikonu TV'nin *Apps* ekranında görünür; isterseniz Ana Ekrana (Smart Hub şeridine) sabitleyebilirsiniz.

#### Yöntem B — En Zahmetsiz Yöntem: Tek Komutluk Docker Yükleyici (Jellyfin-Tizen Modeli)
Bilgisayara Tizen Studio ve Java/SDK kurmak istemeyen kullanıcılar için Jellyfin topluluğunun kanıtladığı (`ghcr.io/georift/install-jellyfin-tizen`) Docker modeli Mavie için de birebir uygulanabilir:
- TV'de Adım 1 (`12345` + Host PC IP) yapıldıktan sonra bilgisayarda yalnızca tek bir komut çalıştırılır:
  ```bash
  docker run --rm ghcr.io/<mavie-repo>/install-mavie-tizen <TV_IP_ADRESI>
  ```
- Konteyner gerekli Tizen CLI araçlarını, sertifika imzalamayı ve SDB aktarımını otomatik halledip Mavie'yi TV'nin ana ekranına kurar.

#### Yöntem C — Topluluk Alternatifi: TizenBrew (TU8500 / Tizen 5.5 Tam Uyumlu!)
- **Uyumluluk:** **TizenBrew**, **Tizen 3.0 ve üzeri (2017+)** tüm Samsung TV'leri — yani **2020 TU8500 (Tizen 5.5)** modelini tam olarak destekler.
- **Nasıl çalışır?**
  1. TV'de Adım 1 (`12345` Geliştirici Modu) açılır.
  2. PC'de **TizenBrew Installer** (veya Tizen 5.5 için **TizenBrew Device Manager**) çalıştırılarak TV'ye tek seferde **TizenBrew** ana uygulaması kurulur.
  3. Kurulumdan sonra yeni modül eklemek için PC'ye bile gerek kalmaz: TV'de TizenBrew açılıp kumandadan **Yeşil tuş** ile modül eklenebilir.
- **Mavie için rolü:** İleride Mavie TV'yi bir TizenBrew modülü olarak da paketlersek, TizenBrew kullanan Samsung TV sahipleri PC açmadan kumandayla kurup güncelleyebilir.

---

### Adım 3: Gerçekçi Dikkat Edilecek Noktalar ve Sık Karşılaşılan Durumlar

- **Sertifika Geçerlilik Süresi (1 Yıl):** Ücretsiz Samsung geliştirici sertifikaları (Author/Distributor `.p12`) **1 yıl** geçerlidir. Süre dolduğunda yeni kurulum/güncelleme sırasında `-12` (*Invalid signature*) hatası alınır. *Certificate Manager* üzerinden yeni profil oluşturup tekrar imzalamak 2 dakika sürer.
- **Uygulama Çakışması (`118019` Hatası):** Sertifika değiştiyse veya paket kimliği çakıştıysa yeni `.wgt` yüklenmeden önce TV'deki eski geliştirici uygulamasını kaldırıp temiz kurulum yapın.
- **TV Yazılım Güncellemeleri:** Nadiren Samsung firmware güncellemeleri sonrası Geliştirici Modu bağlantısı/Host IP sıfırlanabilir; `12345` ile yeniden etkinleştirip PC IP'sini girmek yeterlidir.
- **Ağ ve Güvenlik Duvarı:** Bilgisayar ve TV misafir Wi-Fi (AP Isolation) ağında olmamalıdır. Bilgisayar güvenlik duvarında SDB için **`26101`** (ve Ev Sunucusu modu için Mavie portu **`8844`**) yerel ağa açık olmalıdır.
- **Uygulama Slotu:** Samsung TV'ler Geliştirici Modu'nda sınırlı sayıda özel (sideloaded) uygulamaya izin verir; kişisel kullanım için fazlasıyla yeterlidir.

---

## 4. Diğer TV Platformları Karşılaştırması ve Mevcut Kod Tabanı Durumu

Mavie'nin mevcut deposu (`public/`, `android/`, `apple/Shared/`) doğrudan incelenerek her TV platformu için gerçek durum çıkarılmıştır:

| Platform | Paket Formatı | Evde Ücretsiz Kurulum | Süre / Yenileme Kısıtı | Mavie Kod Tabanı Hazırlığı | Önerilen Strateji |
| --- | --- | --- | --- | --- | --- |
| **Samsung Tizen (TU8500)** | `.wgt` (Web App + AVPlay) | Dev Mode (`12345`) + SDB / Docker / TizenBrew | Sertifika ~1 yıl | `public/` M69'da direkt çalışmaz (234 `?.` + 174 flex `gap`); yeni ince `tv/` çekirdeği gerekir | **Öncelik #1** — `tv/` + AVPlay adaptörü |
| **LG webOS** | `.ipk` (Web App) | LG Dev Mode uygulaması + `webOS Dev Manager` / `ares-install` | **1000 saat (~41 gün)** oturum sayacı (*EXTEND* ile sıfırlanır; dolarsa `.ipk` gizlenir) | Samsung için yazılacak **`tv/` çekirdeği %85–90 ortak kullanılır** | **Öncelik #2** — Aynı `tv/` çekirdeği + `appinfo.json` + geri tuşu (`461`) |
| **Android TV / Google TV** | `.apk` / `.aab` | USB / *Send Files to TV* / *Downloader* (en kolayı) | **Süre sınırı yok** | **~%70 Hazır!** (`LEANBACK_LAUNCHER`, LibVLC 3.7.7, oynatıcı D-Pad tuşları mevcut) | **Hızlı Kazanım** — `android:banner` + menü D-Pad odak eklemesi |
| **Apple TV (`tvOS`)** | `.ipa` (tvOS) / App Store | Xcode kablosuz kurulum | Ücretsiz Apple ID: **7 günde bir** yenileme ($99/yıl hesapta 1 yıl / TestFlight) | **`apple/Shared/` %95+ Hazır!** (12 Swift dosyasının tamamı UIKit'siz) | **Orta Vade** — `apple/project.yml` içine `MavieTVOS` hedefi + tvOS SwiftUI ekranları |

### Kod Tabanına Dayalı Platform Detayları

1. **Android TV / Google TV (`android/`) — Neredeyse Hazır!**
   - **Mevcut durumda çalışanlar:**
     - `android/app/src/main/AndroidManifest.xml` içinde `android.software.leanback` (`required="false"`), `android.hardware.touchscreen` (`required="false"`) ve `LEANBACK_LAUNCHER` intent filtresi **zaten tanımlı**.
     - `android/app/build.gradle.kts` içinde **`org.videolan.android:libvlc-all:3.7.7`** (HEVC, MKV, MPEG-TS, AC3, DTS dahil neredeyse her formatı oynatan motor) **zaten entegre**.
     - `player/PlayerScreen.kt` içinde `onPreviewKeyEvent`, `FocusRequester`, `focusable()` ve `Key.DirectionLeft/Right/Up/Down/Center/Enter` kumanda oynatma kısayolları **zaten yazılmış**.
   - **Tam Android TV deneyimi için kalan 2 eksik:**
     1. `AndroidManifest.xml` `<application>` etiketine TV ana ekran kutucuğu için zorunlu olan **`android:banner`** (`320×180px` yatay TV afişi) eklenmesi.
     2. `LibraryScreen.kt`, `DetailScreen.kt`, `MavieSportsScreen.kt` ve `SetupAndSettings.kt` ekranlarında kartlara ve gezinme çubuğuna belirgin D-Pad odak çerçevesi (`focusable` / odak takibi) eklenmesi.

2. **LG webOS — Samsung ile Ortak Yatırım Avantajı**
   - LG TV'ler de Tizen gibi HTML/CSS/JS tabanlı web uygulaması çalıştırır. Samsung TU8500 için kuracağımız **ES2018 uyumlu `tv/` 10-foot arayüzü, 2B D-Pad odak motoru, QR kodlu kurulum ve Çift Mod (Standalone + Companion)** mimarisi neredeyse hiç değişmeden LG webOS `.ipk` paketine de derlenebilir.
   - Fark eden tek katman ince platform adaptörüdür: `config.xml` yerine `appinfo.json`, Tizen `10009` yerine webOS Geri tuşu `461`, AVPlay yerine HTML5/webOS Luna medya bağlayıcısı.

3. **Apple TV (`apple/Shared/`) — Hazır İş Mantığı Çekirdeği**
   - `apple/Shared/` klasöründeki **12 Swift dosyasının tamamı** (`M3uParser.swift`, `XtreamClient.swift`, `SportsGuideService.swift`, `DiscoveryEngine.swift`, `LanSyncClient.swift`, `LibraryStore.swift`, `CredentialVault.swift`, `PlaybackRecovery.swift`, `Models.swift`, `DemoCatalog.swift`, `MavieHTTPClient.swift`, `BrandTheme.swift`) yalnızca `Foundation`, `SwiftUI`, `CryptoKit`, `Security` ve `zlib` kullanır; **hiçbirinde `UIKit` bağımlılığı yoktur**.
   - Sadece `CredentialVault.swift` ve `LibraryStore.swift` içindeki `#if os(iOS)` dosya koruma dalları vardır ve `#else` blokları tvOS'ta doğrudan çalışır.
   - Eksik olan kısım yalnızca `apple/project.yml` içine `MavieTVOS` hedefi eklenmesi ve `apple/iOS/` ekranlarındaki dokunmatik/iOS'a özgü görünümlerin (`navigationBarTitleDisplayMode`, `UIApplication` çağrıları) tvOS odak sistemine uyarlanmasıdır.

---

## 5. Mavie TV Geliştirme Yol Haritası

| Faz | Hedef & Çıktı | Kapsam ve Teknik İş Kalemleri | Durum / Efor |
| --- | --- | --- | --- |
| **Faz 0** | **Tizen 5.5 Uyumlu `/tv` Evrensel Rota** | • Chromium M69 & LG webOS 4.0 uyumlu saf ES2018 `tv/src/` 10-foot arayüzü (`0` `?.`/`??`, `0` `gap`/`aspect-ratio`)<br>• `server.py` üzerinden `http://<PC-IP>:8844/tv` ve `/api/tv-info` servisi | **Tamamlandı** |
| **Faz 1** | **Mavie Tizen `.wgt` (`dist/Mavie-Tizen.wgt`)** | • `tv/tizen/` (`config.xml`, `tizen-bridge.js`, `install-tizen.sh`, `Dockerfile`) ve stdlib `tv/build_tv_packages.py`<br>• `SamsungAVPlayAdapter` (`webapis.avplay`) + `HlsJsAdapter` çift motor<br>• 2B Spatial Navigation (`spatial.js`), `tvinputdevice` tuş kaydı, `setScreenSaver`, `Return (10009)` + HTML çıkış onay kutusu<br>• Çift Mod: Bağımsız (QR Kod `qr.js` + 6 haneli kod + M3U/Xtream + Demo Katalog) + Ev Sunucusu | **Tamamlandı** |
| **Faz 2** | **Android TV Cilası & LG webOS `.ipk` (`dist/Mavie-webOS.ipk`)** | • **Android TV:** `320×180px` `android:banner` (`drawable-xhdpi/tv_banner.png`) + Compose D-Pad odak iyileştirmesi<br>• **LG webOS:** `tv/webos/` (`appinfo.json`, `webos-bridge.js`, `install-webos.sh`) + `dist/Mavie-webOS.ipk` paketi | **Tamamlandı** |
| **Faz 3** | **Samsung Apps Store (Seller Office), LG Seller Lounge & Apple TV** | • Samsung Seller Office **Partner Seller** başvurusu (Türkiye/Avrupa/Küresel dağıtım) ve *UI Description* QA gönderimi<br>• LG Seller Lounge mağaza başvurusu<br>• İsteğe bağlı: `apple/project.yml` içine `MavieTVOS` hedefi eklenerek Apple TV sürümü | **Sıradaki Adım** *(1–2 hafta + mağaza inceleme)* |

---

## Ek: Faz 1 Başlangıç Teknik Referansı (Tizen `.wgt` İskeleti)

Faz 1 geliştirmesine geçildiğinde doğrudan baz alınacak **Tizen 5.5 (`TU8500`)** yapılandırma ve API iskeleti:

### A. `tv/tizen/config.xml` Temel Yapısı

```xml
<?xml version="1.0" encoding="UTF-8"?>
<widget xmlns="http://www.w3.org/ns/widgets"
        xmlns:tizen="http://tizen.org/ns/widgets"
        id="http://mavie.app/tv"
        version="1.0.0"
        viewmodes="fullscreen">
  <tizen:application id="MavieTV001.Mavie" package="MavieTV001" required_version="5.5"/>
  <content src="index.html"/>
  <feature name="http://tizen.org/feature/screen.size.normal.1080.1920"/>
  <icon src="icon.png"/>
  <name>Mavie</name>

  <!-- Bağımsız modda M3U/Xtream/Spor/Cinemeta erişimi için WARP/CORS izni -->
  <access origin="*" subdomains="true"/>

  <!-- Zorunlu izinler: İnternet + Kumanda tuş kaydı + Uygulama bilgisi -->
  <tizen:privilege name="http://tizen.org/privilege/internet"/>
  <tizen:privilege name="http://tizen.org/privilege/tv.inputdevice"/>
  <tizen:privilege name="http://tizen.org/privilege/application.launch"/>

  <tizen:profile name="tv-samsung"/>
  <tizen:setting screen-orientation="landscape"
                 context-menu="enable"
                 background-support="disable"
                 encryption="disable"
                 install-location="auto"
                 hwkey-event="enable"/>
</widget>
```

### B. `index.html`, Kumanda Kaydı, Çıkış Onayı ve Ekran Koruyucu (ES2018 / M69 Uyumlu)

```html
<!-- Samsung AVPlay ve AppCommon API'leri için zorunlu sistem betiği -->
<script type="text/javascript" src="$WEBAPIS/webapis/webapis.js"></script>
```

```javascript
// Chromium M69 (Tizen 5.5) uyumlu ES2018 örnek başlangıç katmanı
(function initMavieTizen() {
  // Not: 'Exit' (10182) bilinçli olarak kaydedilmez; Tizen sisteminin doğal
  // Exit davranışını koruması Samsung Seller Office QA kurallarına uygundur.
  var MEDIA_KEYS = [
    'MediaPlayPause', 'MediaPlay', 'MediaPause', 'MediaStop',
    'MediaRewind', 'MediaFastForward',
    'ChannelUp', 'ChannelDown',
    'ColorF0Red', 'ColorF1Green', 'ColorF2Yellow', 'ColorF3Blue'
  ];

  if (window.tizen && tizen.tvinputdevice && tizen.tvinputdevice.registerKeyBatch) {
    try {
      tizen.tvinputdevice.registerKeyBatch(MEDIA_KEYS);
    } catch (err) {
      console.warn('tvinputdevice batch register failed:', err && err.message);
    }
  }

  function setScreenSaverDisabled(disabled) {
    if (!window.webapis || !webapis.appcommon) return;
    var states = webapis.appcommon.AppCommonScreenSaverState;
    try {
      webapis.appcommon.setScreenSaver(
        disabled ? states.SCREEN_SAVER_OFF : states.SCREEN_SAVER_ON
      );
    } catch (err) {
      console.warn('setScreenSaver failed:', err && err.message);
    }
  }

  // Samsung Seller Office zorunlu Geri (10009) davranışı:
  // Alt sayfada geri dön; ana sayfada HTML çıkış onay penceresi aç.
  window.addEventListener('keydown', function (event) {
    if (event.keyCode === 10009) {
      event.preventDefault();
      if (window.MavieTV && typeof window.MavieTV.handleBack === 'function') {
        window.MavieTV.handleBack();
      }
    } else if (event.keyCode === 10252) {
      if (window.MavieTV && typeof window.MavieTV.togglePlayPause === 'function') {
        window.MavieTV.togglePlayPause();
      }
    }
  });

  window.MavieTizenBridge = {
    setScreenSaverDisabled: setScreenSaverDisabled,
    exitApp: function () {
      if (window.tizen && tizen.application) {
        tizen.application.getCurrentApplication().exit();
      }
    }
  };
})();
```
