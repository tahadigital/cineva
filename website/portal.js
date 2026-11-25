'use strict';
(() => {
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const GITHUB_REPO_BASE = 'https://github.com/tahadigital/cineva/';
  const GITHUB_DL_BASE = GITHUB_REPO_BASE + 'releases/latest/download/';
  const GITHUB_RELEASES_URL = GITHUB_REPO_BASE + 'releases/latest';

  const RELEASE_ASSETS = {
    'windows-installer': 'Mavie-Setup.exe',
    'windows-portable': 'Mavie.exe',
    'android-apk': 'Mavie-Android.apk',
    'android-tv': 'Mavie-Android.apk',
    'macos': 'Mavie-macOS.dmg',
    'ios': 'Mavie-iOS.ipa',
    'tizen-wgt': 'Mavie-Tizen.wgt',
    'webos-ipk': 'Mavie-webOS.ipk',
  };

  const DOWNLOAD_URLS = Object.fromEntries(
    Object.entries(RELEASE_ASSETS).map(([key, file]) => [key, GITHUB_DL_BASE + file])
  );

  const DOWNLOAD_LABELS = {
    'windows-installer': 'Windows Kurulum Sihirbazı (Mavie-Setup.exe)',
    'windows-portable': 'Windows Taşınabilir Sürüm (Mavie.exe)',
    'android-apk': 'Android APK (Mavie-Android.apk)',
    'android-tv': 'Android TV / Google TV / Fire TV APK (Mavie-Android.apk)',
    'macos': 'macOS Uygulama Paketi (Mavie-macOS.dmg)',
    'ios': 'iOS Sideload Paketi (Mavie-iOS.ipa)',
    'tizen-wgt': 'Samsung Smart TV Tizen Paketi (Mavie-Tizen.wgt)',
    'webos-ipk': 'LG Smart TV webOS Paketi (Mavie-webOS.ipk)',
  };

  const DOWNLOAD_GUIDES = {
    'windows-installer': {
      tab: 'windows',
      hint: ' Uygulama kendi yerel Windows penceresinde açılır; SmartScreen çıkarsa Ek bilgi → Yine de çalıştır seçin.',
    },
    'windows-portable': {
      tab: 'windows',
      hint: ' Taşınabilir Mavie.exe kendi yerel penceresinde çalışır; tarayıcı/LAN için Mavie.exe --web kullanabilirsiniz.',
    },
    'macos': {
      tab: 'macos',
      hint: ' İlk açılışta Gatekeeper uyarısı çıkarsa aşağıdaki macOS kılavuzundaki tek adımlı onayı izleyin.',
    },
    'ios': {
      tab: 'ios',
      hint: ' İndirilen imzasız IPA dosyasını AltStore, SideStore veya Sideloadly ile iPhone/iPad cihazınıza yükleyebilirsiniz.',
    },
    'android-apk': {
      tab: 'android',
      hint: ' İndirme tamamlanınca APK dosyasına dokunun; gerekirse "Bu kaynaktan izin ver" seçeneğini açın.',
    },
    'android-tv': {
      tab: 'android',
      hint: ' Android TV / Google TV / Fire TV için Downloader, Send Files to TV veya USB bellek ile kurabilirsiniz (Leanback banner + tam D-Pad dahil).',
    },
    'tizen-wgt': {
      tab: 'samsung-tv',
      hint: ' Samsung TV Apps ekranında 12345 ile Geliştirici Modu açıp ./tv/tizen/install-tizen.sh, Tizen Studio CLI veya TizenBrew ile TV\'ye yükleyin.',
    },
    'webos-ipk': {
      tab: 'lg-tv',
      hint: ' LG Content Store\'dan Developer Mode kurup webOS Dev Manager veya ares-install -d tv Mavie-webOS.ipk ile TV\'ye yükleyin.',
    },
  };

  const GUIDE_LABELS = {
    'windows': 'Windows kurulum kılavuzu',
    'macos': 'macOS Gatekeeper & kurulum kılavuzu',
    'ios': 'iPhone / iPad sideload kılavuzu',
    'android': 'Android & Android TV kurulum kılavuzu',
    'samsung-tv': 'Samsung TV (Tizen) kurulum kılavuzu',
    'lg-tv': 'LG TV (webOS) & TV tarayıcı kılavuzu',
    'distribution': 'Yayın yerleri & dağıtım kanalları',
  };

  const GUIDE_ALIASES = {
    'web-tv': 'lg-tv',
    'tv': 'samsung-tv',
    'tizen': 'samsung-tv',
    'webos': 'lg-tv',
    'android-tv': 'android',
  };

  const VALID_GUIDES = Object.keys(GUIDE_LABELS);
  let detectedGuideKey = 'windows';

  function isSafeDownloadUrl(url) {
    return typeof url === 'string' && (/^https?:\/\//i.test(url) || /^\/(?!\/)/.test(url));
  }

  function resolveGuideKey(raw) {
    const normalized = String(raw || '').toLowerCase();
    if (VALID_GUIDES.includes(normalized)) return normalized;
    if (GUIDE_ALIASES[normalized]) return GUIDE_ALIASES[normalized];
    return detectedGuideKey;
  }

  function queryAll(sel) {
    return typeof document.querySelectorAll === 'function'
      ? Array.from(document.querySelectorAll(sel))
      : [];
  }

  function setClass(el, name, enabled) {
    if (!el) return;
    if (el.classList && typeof el.classList.toggle === 'function') {
      el.classList.toggle(name, Boolean(enabled));
      return;
    }
    const parts = String(el.className || '').split(/\s+/).filter(Boolean);
    const has = parts.includes(name);
    if (enabled && !has) parts.push(name);
    if (!enabled && has) parts.splice(parts.indexOf(name), 1);
    el.className = parts.join(' ');
  }

  function setAttr(el, attr, value) {
    if (!el) return;
    if (typeof el.setAttribute === 'function') {
      el.setAttribute(attr, String(value));
    }
    if (attr === 'tabindex') {
      el.tabIndex = Number(value);
    }
  }

  function activateGuideTab(guideKey, options = {}) {
    const key = resolveGuideKey(guideKey);
    const tabs = queryAll('[role="tab"][data-guide]');
    const panels = queryAll('[role="tabpanel"][data-guide-panel]');
    if (!tabs.length && !panels.length) return key;

    let activeTab = null;
    for (const tab of tabs) {
      const isMatch = tab.dataset && tab.dataset.guide === key;
      setAttr(tab, 'aria-selected', isMatch ? 'true' : 'false');
      setAttr(tab, 'tabindex', isMatch ? '0' : '-1');
      setClass(tab, 'is-active', isMatch);
      if (isMatch) activeTab = tab;
    }

    for (const panel of panels) {
      const isMatch = panel.dataset && panel.dataset.guidePanel === key;
      panel.hidden = !isMatch;
      setClass(panel, 'is-active', isMatch);
    }

    if (options.focusTab && activeTab && typeof activeTab.focus === 'function') {
      activeTab.focus();
    }

    if (options.scroll) {
      const section = document.getElementById('guides');
      if (section && typeof section.scrollIntoView === 'function') {
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }

    if (options.updateHash && typeof window !== 'undefined' && window.history && typeof window.history.replaceState === 'function') {
      try {
        window.history.replaceState(null, '', '#guide-' + key);
      } catch {}
    }

    return key;
  }

  function bindGuideJumpLinks(root) {
    const links = root && typeof root.querySelectorAll === 'function'
      ? Array.from(root.querySelectorAll('[data-guide-tab]'))
      : queryAll('[data-guide-tab]');

    for (const link of links) {
      if (link._mavieGuideBound) continue;
      link._mavieGuideBound = true;
      link.addEventListener('click', e => {
        if (e && typeof e.preventDefault === 'function') e.preventDefault();
        const raw = link.dataset ? link.dataset.guideTab : '';
        const targetKey = raw === 'auto' ? detectedGuideKey : raw;
        activateGuideTab(targetKey, { scroll: true, updateHash: true });
      });
    }
  }

  function startDownload(target) {
    const url = DOWNLOAD_URLS[target];
    if (!isSafeDownloadUrl(url)) return;
    const guideInfo = DOWNLOAD_GUIDES[target];
    const guideKey = guideInfo ? guideInfo.tab : null;
    if (guideKey) {
      activateGuideTab(guideKey, { scroll: false, updateHash: false });
    }
    const notice = document.getElementById('downloadNotice');
    if (notice) {
      const label = DOWNLOAD_LABELS[target] || target;
      const extraHint = (guideInfo && guideInfo.hint)
        ? guideInfo.hint
        : ' İndirme otomatik başlamazsa aşağıdaki doğrudan bağlantıyı kullanın.';
      const guideLink = guideKey
        ? ` <a href="#guides" data-guide-tab="${esc(guideKey)}" class="download-notice-link">${esc(GUIDE_LABELS[guideKey])} ›</a>`
        : '';
      notice.hidden = false;
      notice.innerHTML = `<strong>İndirme başlatıldı:</strong> ${esc(label)}.${esc(extraHint)} <a href="${esc(url)}" class="download-notice-link">Doğrudan indir</a>${guideLink}`;
      bindGuideJumpLinks(notice);
    }
    window.location.href = url;
  }

  function detectPlatform() {
    const ua = (typeof navigator !== 'undefined' && navigator.userAgent) ? navigator.userAgent : '';
    const isTizen = /Tizen/i.test(ua);
    const isWebOS = /Web0S|webOS/i.test(ua);
    const isAndroid = /Android/i.test(ua);
    const isIos = /iPhone|iPad|iPod/i.test(ua);
    const isMac = !isIos && /Macintosh|Mac OS X/i.test(ua);
    const isWin = /Windows/i.test(ua);

    if (isTizen) detectedGuideKey = 'samsung-tv';
    else if (isWebOS) detectedGuideKey = 'lg-tv';
    else if (isAndroid) detectedGuideKey = 'android';
    else if (isIos) detectedGuideKey = 'ios';
    else if (isMac) detectedGuideKey = 'macos';
    else detectedGuideKey = 'windows';

    const primary = document.getElementById('primaryDownloadBtn');
    const secondary = document.getElementById('secondaryDownloadBtn');
    const hint = document.getElementById('platformHint');
    if (!primary || !secondary || !hint) return detectedGuideKey;

    if (isTizen) {
      primary.textContent = 'Samsung TV için İndir (.wgt)';
      primary.onclick = e => { e.preventDefault(); startDownload('tizen-wgt'); };
      secondary.textContent = 'Windows (.exe)';
      secondary.onclick = e => { e.preventDefault(); startDownload('windows-installer'); };
      hint.textContent = 'Samsung Tizen TV algılandı — Mavie-Tizen.wgt paketi önerildi.';
    } else if (isWebOS) {
      primary.textContent = 'LG TV için İndir (.ipk)';
      primary.onclick = e => { e.preventDefault(); startDownload('webos-ipk'); };
      secondary.textContent = 'Windows (.exe)';
      secondary.onclick = e => { e.preventDefault(); startDownload('windows-installer'); };
      hint.textContent = 'LG webOS TV algılandı — Mavie-webOS.ipk paketi önerildi.';
    } else if (isAndroid) {
      primary.textContent = 'Android için İndir (.apk)';
      primary.onclick = e => { e.preventDefault(); startDownload('android-apk'); };
      secondary.textContent = 'Windows (.exe)';
      secondary.onclick = e => { e.preventDefault(); startDownload('windows-installer'); };
      hint.textContent = 'Android cihaz algılandı — önerilen Mavie-Android.apk (Mobil & Android TV) seçildi.';
    } else if (isIos) {
      primary.textContent = 'iOS için İndir (.ipa)';
      primary.onclick = e => { e.preventDefault(); startDownload('ios'); };
      secondary.textContent = 'macOS (.dmg)';
      secondary.onclick = e => { e.preventDefault(); startDownload('macos'); };
      hint.textContent = 'iOS cihaz algılandı — imzasız sideload IPA (AltStore / SideStore / Sideloadly) önerildi.';
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
        ? 'Windows algılandı — yerel masaüstü penceresinde çalışır; Web Sürümü ve Smart TV /tv sunucusu dahildir.'
        : 'Windows, macOS, Android, iOS ve Akıllı TV sürümlerinden cihazınıza uygun olanı ücretsiz indirin.';
    }
    return detectedGuideKey;
  }

  function setupGuideTabs() {
    const tabs = queryAll('[role="tab"][data-guide]');
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => {
        activateGuideTab(tab.dataset.guide, { focusTab: false, scroll: false, updateHash: true });
      });

      tab.addEventListener('keydown', e => {
        const key = e && e.key;
        if (!key) return;
        let nextIndex = null;
        if (key === 'ArrowRight' || key === 'ArrowDown') {
          nextIndex = (index + 1) % tabs.length;
        } else if (key === 'ArrowLeft' || key === 'ArrowUp') {
          nextIndex = (index - 1 + tabs.length) % tabs.length;
        } else if (key === 'Home') {
          nextIndex = 0;
        } else if (key === 'End') {
          nextIndex = tabs.length - 1;
        }
        if (nextIndex !== null) {
          if (typeof e.preventDefault === 'function') e.preventDefault();
          const nextTab = tabs[nextIndex];
          if (nextTab && nextTab.dataset) {
            activateGuideTab(nextTab.dataset.guide, { focusTab: true, scroll: false, updateHash: true });
          }
        }
      });
    });

    const readHashGuide = () => {
      const hash = (window.location && window.location.hash) ? String(window.location.hash) : '';
      const match = hash.match(/^#guide-([a-z-]+)$/i);
      if (!match) return null;
      const slug = match[1].toLowerCase();
      if (VALID_GUIDES.includes(slug)) return slug;
      if (GUIDE_ALIASES[slug]) return GUIDE_ALIASES[slug];
      return null;
    };

    const initialHashGuide = readHashGuide();
    activateGuideTab(initialHashGuide || detectedGuideKey, { scroll: false, updateHash: false });

    if (typeof window.addEventListener === 'function') {
      window.addEventListener('hashchange', () => {
        const next = readHashGuide();
        if (next) activateGuideTab(next, { scroll: false, updateHash: false });
      });
    }
  }

  async function copyText(text) {
    if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(text);
      return true;
    }
    if (typeof document.createElement === 'function' && document.body && typeof document.execCommand === 'function') {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return Boolean(ok);
    }
    return false;
  }

  function setupCopyButtons() {
    const live = document.getElementById('copyLiveStatus');
    for (const btn of queryAll('[data-copy]')) {
      const originalLabel = btn.textContent || 'Kopyala';
      let resetTimer = null;
      btn.addEventListener('click', async () => {
        const text = btn.dataset ? btn.dataset.copy : '';
        if (!text) return;
        let ok = false;
        try {
          ok = await copyText(text);
        } catch {
          ok = false;
        }
        if (ok) {
          btn.textContent = '✓ Kopyalandı';
          setClass(btn, 'is-copied', true);
          if (live) live.textContent = `${text} panoya kopyalandı.`;
          if (resetTimer && typeof clearTimeout === 'function') clearTimeout(resetTimer);
          if (typeof setTimeout === 'function') {
            resetTimer = setTimeout(() => {
              btn.textContent = originalLabel;
              setClass(btn, 'is-copied', false);
            }, 2000);
          }
        }
      });
    }
  }

  queryAll('[data-dl]').forEach(btn => {
    btn.addEventListener('click', () => startDownload(btn.dataset.dl));
  });
  queryAll('[data-releases]').forEach(link => {
    link.href = GITHUB_RELEASES_URL;
  });

  detectPlatform();
  setupGuideTabs();
  bindGuideJumpLinks();
  setupCopyButtons();
})();
