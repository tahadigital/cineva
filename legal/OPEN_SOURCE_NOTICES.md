# Vrelio — Açık Kaynak Lisansları

Vrelio aşağıdaki açık kaynak yazılımlarından ve platform çerçevelerinden yararlanır:

- **LibVLC for Android / Desktop (`org.videolan.android:libvlc-all`)**
  - Lisans: GNU Lesser General Public License v2.1 or later (LGPL-2.1+)
  - Telif Hakkı: VideoLAN ve katkıda bulunanlar
  - Kaynak Kod: https://code.videolan.org/videolan/libvlcjni
  - Vrelio, LibVLC kütüphanesi üzerinde değişiklik yapmadan standart dinamik bağlama ile kullanır.

- **hls.js**
  - Lisans: Apache License 2.0 (Copyright Dailymotion / Video-Dev)

- **AndroidX, Jetpack Compose, OkHttp, Coil, Kotlin & Coroutines**
  - Lisans: Apache License 2.0

- **FFmpeg (İsteğe bağlı masaüstü uyumlu oynatma bileşeni)**
  - Ticari dağıtımda yalnızca LGPL v2.1+ uyumlu derleme veya işletim sistemi donanım kod çözücüleri kullanılmalıdır (`--enable-gpl` ikili paketleri kapalı kaynaklı mağaza derlemelerine gömülmez).

- **Apple Sistem Çerçeveleri (macOS & iOS)**
  - Native Apple istemcilerinde işletim sistemiyle birlikte gelen `SwiftUI`, `AVFoundation` ve `AVKit` sistem çerçeveleri kullanılır.
