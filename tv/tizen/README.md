# Mavie — Samsung Tizen TV (TU8500 / Tizen 5.5+) Hızlı Kurulum

Bu klasör, **Samsung Smart TV (2020 TU8500 / Tizen 5.5 ve üzeri)** için donanımsal **AVPlay** destekli ve **Chromium M69** uyumlu `.wgt` uygulama paketini üretir ve TV'nize yükler.

## 1. Paketi Üretme (Sıfır Harici Bağımlılık)

Proje kök dizininden:

```bash
python3 tv/build_tv_packages.py
```

Çıktılar:
- `dist/Mavie-Tizen.wgt` (Samsung Tizen 5.5+)
- `dist/Mavie-webOS.ipk` (LG webOS 4.0+)

## 2. Samsung TU8500'de Geliştirici Modunu Açma

1. TV'de **Apps (Uygulamalar)** ekranına girin.
2. Kumandadan hızlıca **`12345`** tuşlayın.
3. **Developer Mode → Açık (On)** yapıp **Host PC IP** alanına bilgisayarınızın yerel IP adresini yazın.
4. Kumandanın Güç tuşuna ~5 saniye basılı tutarak TV'yi tamamen yeniden başlatın.

## 3. TV'ye Yükleme

Tizen Studio CLI (`sdb` + `tizen` + Samsung Certificate Extension) kuruluysa tek komutla yükleyebilirsiniz:

```bash
chmod +x tv/tizen/install-tizen.sh
./tv/tizen/install-tizen.sh 192.168.1.42 MavieProfile
```

Ayrıntılı sertifika, DUID, TizenBrew ve Samsung Seller Office yönergeleri için bkz. [`docs/TV_PLATFORM_GUIDE.md`](../../docs/TV_PLATFORM_GUIDE.md).
