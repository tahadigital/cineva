# Mavie Android

Mac'ten bağımsız, Kotlin/Jetpack Compose ile yazılmış Android IPTV istemcisi.

## Kurulum

`dist/Mavie-Android.apk` güncel ARM64 sürümüdür. Android cihazlarda Mavie simgesiyle açılır. Başka bir cihaza kurarken APK'yı telefona aktarın ve Android'in kurulum ekranından açın. APK kullanıcı adı/parola içermez. İlk kullanımda kendi IPTV bilgileri girilir. Normal kullanımda Mac ve yerel sunucu gerekmez.

Filmler, diziler, canlı TV, yerel ses/altyazı seçimi, kaldığın yer, favoriler, kişisel listeler, arama, kategoriler, özgün açılış animasyonu ve ekran geçişleri bulunur. Sağlayıcının sunduğu içerikler ve dil seçenekleri kullanılır. Gelişmiş kodekler LibVLC ile telefonda çözülür; mümkün olduğunda donanım kullanılır.

Film ve dizi oynatıcısında tek çubuk içeriğin başından sonuna kadar sarar. Bir bölüm bitince **Sonraki Bölüm** kartı ve iptal edilebilir otomatik geçiş açılır.

**1.2.1:** Bazı dizilerde son saniyelerin saat bilgisi sabit kaldığı için bölüm geçişinin açılmaması düzeltildi. Bitiş kontrolü gerçek ses ve görüntü ilerlemesini de kullanır. Büyük kütüphanelerde öneri hazırlığındaki tekrarlar azaltıldı; ekran kapanınca bekleyen katalog istekleri ve hesaplamalar iptal edilir.

**Spor** sekmesi, Türkiye saatine göre maç ve yarış yayınlarını Spor Ekranı'ndan alır. Tarih, spor dalı ve arama filtreleri bulunur. IPTV listenizdeki eşleşen kanal doğrudan açılır. Rehber ve Android oynatma Mac bağlantısından bağımsızdır.

## Veriler

Bağlantı AES/GCM ile Android Keystore anahtarı kullanılarak şifrelenir. Katalog ve kişisel kütüphane uygulamaya özel SQLite veritabanındadır. Otomatik bulut yedeği ve cihaz transferi kapalıdır. Ayarlardan kişisel izleme/listeler yedeği alınabilir; bu JSON hesabın parolasını içermez.

Mac ile eşitleme isteğe bağlı ve aynı yerel ağda yapılan bir birleştirmedir; otomatik bulut eşitlemesi değildir. Silmeler diğer cihaza yayılmaz. Telefon Mac kapalıyken bağımsız çalışır. Oynatıcı parça kimlikleri farklı olduğu için Android ve Mac ses/altyazı tercihleri ayrı tutulur.

## Derleme

JDK 17, Android SDK platform 36 ve Build Tools 35 gerekir. Gradle Wrapper 8.13 / AGP 8.13.2 kullanılır. SDK yolu `local.properties` içindeki `sdk.dir` ile veya Android SDK ortam değişkeniyle seçilir.

```sh
./gradlew :app:assembleRelease :app:lintRelease :app:testDebugUnitTest
```

`JAVA_HOME` JDK 17'yi göstermelidir. Yerel `signing/` klasörü kişisel güncelleme anahtarını içerir ve sürüm kontrolünden dışlanır. Bu anahtar korunmalıdır; mevcut uygulamanın verileri silinmeden güncellenebilmesi için aynı imza gerekir. Anahtar olmadan yeni bir kurulum için kendi imzanızı oluşturun.

## Doğrulama

JVM testleri sahte veriler kullanır. `LocalStateTest` ayrı geçici SQLite dosyalarında çalışır. Gerçek sağlayıcı testleri açıkça seçilir ve uygulamanın özel alanında geçici opt-in dosyası bulunmadığında atlanır. Hesaplar kaynak koduna/test APK'sına yazılmaz. `dist/proofs/` yalnızca redakte edilmiş sayısal sonuçlar ve uygulama ekran görüntülerini içerir.

NativePlaybackProofTest: gerçek video kareleri, ses/altyazı seçimi, altyazı kapalı, ileri/geri sarma, duraklatma ve uygulamaya dönüş.
AppFlowProofTest: ana ekran → arama → ayrıntı → yerel oynatıcı akışı.
ContentKindsProofTest: canlı TV ve dizi bölümü oynatımı.
EpisodeTransitionTest: tek zaman çubuğu, geri sarma, sonraki bölümü iptal etme ve otomatik geçiş.
ProviderEpisodeFlowProofTest: açıkça seçilerek gerçek sağlayıcıda uzun film sarma ve Dexter bölüm geçişi; test sonunda etkilenen izleme ve ses/altyazı kayıtları geri yüklenir.

## Üçüncü taraflar

LibVLC Android 3.7.7: LGPL 2.1 veya sonrası. Kaynak: https://code.videolan.org/videolan/libvlcjni
Compose/AndroidX, OkHttp, Coil ve Kotlin: Apache 2.0. Uygulamanın `assets/NOTICE.txt` dosyası atıfları içerir. LibVLC kitaplığında değişiklik yapılmamıştır.

## Güncel keşif ve öneriler (1.2)

Ana sayfadaki büyük **Yeni Çıkanlar** vitrini film ve diziler arasında gezilebilir. **Türkiye’de Popüler Filmler/Diziler**, Netflix Türkiye'nin tarihli haftalık Top 10 listesiyle eşleşen kütüphane içeriklerini gösterir; tüm platformların Türkiye sıralaması değildir. Cinemeta'nın genel ve yıl/tür katalogları da keşif bilgisi sağlar. Kaynaklardaki Türkçe ve özgün adlar yerel sağlayıcı kayıtlarıyla eşleştirilir; öneri kartlarında yalnızca gerçek yerel içerik kimlikleri bulunur.

**Sana Özel** sıralaması izleme süresi, tamamlanma, favoriler ve yakın zamandaki izlemelerden tür ağırlıkları çıkarır. Bölüm geçmişi bağlı olduğu dizi üzerinden değerlendirilir. İzlenen başlıklar kişisel önerilerden elenir; geçmiş yokken **Keşfet** gösterilir. Türler sağlayıcının kategori adlarından alınmaz. İzleme geçmişi ve IPTV bilgileri dışarıya gönderilmez. Her cihaz kendi yerel geçmişini kullanır.

Keşif verisi altı saatte bir ihtiyaç olduğunda arka planda yenilenir. Ağ kesilirse kayıtlı metadata korunur; 21 günden eski Türkiye sıralaması gösterilmez. Yeni çıkanlar yayın tarihine göre son bir yıl / tarih yoksa mevcut yayın yılı üzerinden seçilir; gelecekteki yayınlar yeni çıkan vitrinine alınmaz. Sağlayıcının kütüphaneye ekleme tarihi ayrı sıralarda gösterilir.
