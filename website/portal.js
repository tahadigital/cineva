'use strict';
(() => {
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const GITHUB_REPO_BASE = 'https://github.com/tahadigital/cineva/';
  const GITHUB_DL_BASE = GITHUB_REPO_BASE + 'releases/latest/download/';
  const GITHUB_RELEASES_URL = GITHUB_REPO_BASE + 'releases/latest';

  const DOWNLOAD_URLS = {
    'windows-installer': GITHUB_DL_BASE + 'Mavie-Setup.exe',
    'windows-portable': GITHUB_DL_BASE + 'Mavie.exe',
    'android-apk': GITHUB_DL_BASE + 'Mavie-Android.apk',
    'macos': GITHUB_DL_BASE + 'Mavie-macOS.dmg',
    'ios': GITHUB_DL_BASE + 'Mavie-iOS.ipa',
  };

  const DOWNLOAD_LABELS = {
    'windows-installer': 'Windows Kurulum Sihirbazı (Mavie-Setup.exe)',
    'windows-portable': 'Windows Taşınabilir Sürüm (Mavie.exe)',
    'android-apk': 'Android APK (Mavie-Android.apk)',
    'macos': 'macOS Uygulama Paketi (Mavie-macOS.dmg)',
    'ios': 'iOS Sideload Paketi (Mavie-iOS.ipa)',
  };

  function isSafeDownloadUrl(url) {
    return typeof url === 'string' && (/^https?:\/\//i.test(url) || /^\/(?!\/)/.test(url));
  }

  function startDownload(target) {
    const url = DOWNLOAD_URLS[target];
    if (!isSafeDownloadUrl(url)) return;
    const notice = document.getElementById('downloadNotice');
    if (notice) {
      const label = DOWNLOAD_LABELS[target] || target;
      const extraHint = target === 'ios'
        ? ' İndirilen imzasız IPA dosyasını AltStore veya Sideloadly ile iPhone/iPad cihazınıza yükleyebilirsiniz.'
        : ' İndirme otomatik başlamazsa aşağıdaki doğrudan bağlantıyı kullanın.';
      notice.hidden = false;
      notice.innerHTML = `<strong>İndirme başlatıldı:</strong> ${esc(label)}.${esc(extraHint)} <a href="${esc(url)}" style="color:var(--amber);font-weight:700;text-decoration:underline;margin-left:6px">Doğrudan indir</a>`;
    }
    window.location.href = url;
  }

  function detectPlatform() {
    const ua = navigator.userAgent || '';
    const isAndroid = /Android/i.test(ua);
    const isIos = /iPhone|iPad|iPod/i.test(ua);
    const isMac = !isIos && /Macintosh|Mac OS X/i.test(ua);
    const isWin = /Windows/i.test(ua);

    const primary = document.getElementById('primaryDownloadBtn');
    const secondary = document.getElementById('secondaryDownloadBtn');
    const hint = document.getElementById('platformHint');
    if (!primary || !secondary || !hint) return;

    if (isAndroid) {
      primary.textContent = 'Android için İndir (.apk)';
      primary.onclick = e => { e.preventDefault(); startDownload('android-apk'); };
      secondary.textContent = 'Windows (.exe)';
      secondary.onclick = e => { e.preventDefault(); startDownload('windows-installer'); };
      hint.textContent = 'Android cihaz algılandı — önerilen Mavie-Android.apk sürümü seçildi.';
    } else if (isIos) {
      primary.textContent = 'iOS için İndir (.ipa)';
      primary.onclick = e => { e.preventDefault(); startDownload('ios'); };
      secondary.textContent = 'macOS (.dmg)';
      secondary.onclick = e => { e.preventDefault(); startDownload('macos'); };
      hint.textContent = 'iOS cihaz algılandı — imzasız sideload IPA (AltStore / Sideloadly) önerildi.';
    } else if (isMac) {
      primary.textContent = 'macOS için İndir (.dmg)';
      primary.onclick = e => { e.preventDefault(); startDownload('macos'); };
      secondary.textContent = 'Windows (.exe)';
      secondary.onclick = e => { e.preventDefault(); startDownload('windows-installer'); };
      hint.textContent = 'macOS algılandı — Apple Silicon & Intel uyumlu Mavie-macOS.dmg seçildi.';
    } else {
      primary.textContent = 'Windows için İndir (Mavie-Setup.exe)';
      primary.onclick = e => { e.preventDefault(); startDownload('windows-installer'); };
      secondary.textContent = 'Android APK İndir';
      secondary.onclick = e => { e.preventDefault(); startDownload('android-apk'); };
      hint.textContent = isWin
        ? 'Windows algılandı — kurulum sihirbazı tek tıkla kurulur, hesap gerektirmez.'
        : 'Windows, Android, macOS ve iOS sürümlerinden cihazınıza uygun olanı ücretsiz indirin.';
    }
  }

  document.querySelectorAll('[data-dl]').forEach(btn => {
    btn.addEventListener('click', () => startDownload(btn.dataset.dl));
  });
  document.querySelectorAll('[data-releases]').forEach(link => {
    link.href = GITHUB_RELEASES_URL;
  });

  detectPlatform();
})();
