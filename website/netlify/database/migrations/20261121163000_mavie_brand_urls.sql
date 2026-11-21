-- Migration: 20261121163000_mavie_brand_urls
-- Corrective migration: update app_config release metadata and 4-platform download URLs to Mavie v2.1.0.

INSERT INTO app_config (key, value) VALUES
  ('versions', '{"latestVersion":"2.1.0","windowsLatest":"2.1.0","windowsMin":"2.0.0","androidLatest":"2.1.0","androidMin":"2.0.0","macosLatest":"2.1.0","macosMin":"2.0.0","iosLatest":"2.1.0","iosMin":"2.0.0","windowsInstallerUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Mavie-Setup.exe","windowsPortableUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Mavie.exe","androidApkUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Mavie-Android.apk","macosUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Mavie-macOS.dmg","iosUrl":"https://github.com/tahadigital/cineva/releases/latest/download/Mavie-iOS.ipa","releaseNotes":"Mavie 2.1.0: 4 platform desteği, mor-mavi-turkuaz yeni tasarım, e-posta doğrulama ve 3 günlük Pro deneme."}')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
