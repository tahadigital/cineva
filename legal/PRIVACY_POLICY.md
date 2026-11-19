# Vrelio — Gizlilik Politikası (KVKK & GDPR Uyumlu)

**Son Güncelleme:** 19 Kasım 2026

**Vrelio**, kişisel medya dosyalarınızı ve kendi eklediğiniz açık yayın/oynatma listelerinizi düzenleyip oynatmanıza yardımcı olan bir medya oynatıcı yazılımıdır.

## 1. Topladığımız Veriler ve Yerel İlkeler
- **Yerel Öncelikli Mimari (Local-First):** Medya kaynak adresleriniz, oynatma listeleriniz (M3U/Xtream/WebDAV/SMB) ve izleme geçmişiniz cihazınızda yerel olarak saklanır.
- **Kimlik Bilgileri Güvenliği:** Android cihazlarda hesap bilgileri Android Keystore şifrelemesiyle; masaüstü ve Apple platformlarında işletim sisteminin güvenli kasasıyla korunur.
- **Hesap Doğrulama, Parola Sıfırlama ve Plan Yönetimi:** Bulut hesabı oluşturduğunuzda yalnızca e-posta adresiniz, görünen adınız, PBKDF2-SHA256 ile özetlenmiş parolanız, hesap plan/3 günlük Pro deneme durumunuz ve kayıtlı cihaz kimlikleriniz saklanır. E-posta doğrulama ve parola sıfırlama kodları tek yönlü SHA-256 özeti olarak tutulur ve süreleri dolduğunda veya kullanıldığında geçersiz kılınır.
- **Bulut Eşitleme (Pro Plan):** Yalnızca hesabınızı doğrulayıp Pro plan (veya 3 günlük Pro deneme) kapsamında bulut eşitlemeyi etkinleştirdiğinizde favorileriniz, listeleriniz ve kaldığınız süre konumu cihazlarınız arasında senkronize edilir. Medya sunucularınıza ait parolalar üçüncü taraflarla paylaşılmaz ve buluta aktarılmaz.
- **İçerik Taraması Yok:** Vrelio, kullanıcıların oynattığı özel medya içeriklerini veya URL'leri izlemez, analiz etmez ya da reklam profillemesi için satmaz.

## 2. Üçüncü Taraf Hizmetleri
- **Meta Veri Sağlayıcıları (TMDB vb.):** Film ve dizi kapakları/özetleri için resmi API'ler kullanıldığında yalnızca genel eser kimlikleri veya başlıkları sorgulanır; kişisel kimlik bilgisi iletilmez.
- **E-posta İletimi:** Hesap doğrulama ve parola sıfırlama iletileri yalnızca yapılandırılmış SMTP/e-posta servisi üzerinden gönderilir; pazarlama amaçlı kullanılmaz.
- **Ödeme Sağlayıcıları:** Uygulama içi satın alımlar Google Play Billing, Apple StoreKit, Paddle veya Lemon Squeezy üzerinden yürütülür. Vrelio kredi kartı bilgilerinizi saklamaz.

## 3. Veri Haklarınız ve Silme
Uygulama içi **Ayarlar → Verileri Temizle / Hesaptan Çıkış Yap** adımlarıyla cihazınızdaki tüm yerel verileri anında silebilir, kayıtlı cihazlarınızı hesap panelinden kaldırabilirsiniz. Bulut hesabı silme talepleri için `privacy@vrelio.app` adresinden istediğiniz zaman verilerinizin kalıcı olarak kaldırılmasını isteyebilirsiniz.
