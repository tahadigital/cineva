'use strict';
(() => {
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const apiBase = () => (localStorage.getItem('cineva_cloud_api') || '').replace(/\/$/, '');
  const tokenKey = 'cineva_user_token';
  let configData = null;
  let authMode = 'login';

  async function req(path, opts = {}) {
    const token = localStorage.getItem(tokenKey);
    const headers = {'Content-Type': 'application/json', ...(opts.headers || {})};
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const res = await fetch(apiBase() + path, { ...opts, headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Hata (${res.status})`);
    return data;
  }

  function detectPlatform() {
    const ua = navigator.userAgent || '';
    const isAndroid = /Android/i.test(ua);
    const isWin = /Windows/i.test(ua);
    const primary = document.getElementById('primaryDownloadBtn');
    const secondary = document.getElementById('secondaryDownloadBtn');
    const hint = document.getElementById('platformHint');
    if (isAndroid) {
      primary.textContent = 'Android için İndir (.apk)';
      primary.onclick = e => { e.preventDefault(); startDownload('android-apk'); };
      secondary.textContent = 'Windows (.exe)';
      secondary.onclick = e => { e.preventDefault(); startDownload('windows-installer'); };
      hint.textContent = 'Android cihaz algılandı — önerilen sürüm doğrudan seçildi.';
    } else {
      primary.textContent = 'Windows için İndir (Cineva-Setup.exe)';
      primary.onclick = e => { e.preventDefault(); startDownload('windows-installer'); };
      secondary.textContent = 'Android APK İndir';
      secondary.onclick = e => { e.preventDefault(); startDownload('android-apk'); };
      hint.textContent = isWin ? 'Windows algılandı — kurulum sihirbazı tek tıkla kurulur.' : 'Windows, Android Telefon/Tablet ve yerel Web/Mac desteği hazır.';
    }
  }

  async function loadConfig() {
    try {
      configData = await req('/api/v1/app-config');
      const ann = configData.announcement || {};
      const bar = document.getElementById('announceBanner');
      if (ann.enabled && (ann.title || ann.message)) {
        bar.hidden = false;
        bar.className = 'announce-bar' + (ann.severity === 'critical' ? ' critical' : '');
        bar.innerHTML = `<strong>${esc(ann.title)}</strong> ${esc(ann.message)}`;
      }
      const v = configData.versions || {};
      const d = configData.downloads || {};
      document.getElementById('winVerBadge').textContent = `Windows 10/11 · v${v.windowsLatest || '2.0.0'}`;
      document.getElementById('androidVerBadge').textContent = `Android 8+ · v${v.androidLatest || '2.0.0'}`;
      document.getElementById('dlWinCount').textContent = `${(d['windows-installer'] || 0) + (d['windows-portable'] || 0)} kez indirildi`;
      document.getElementById('dlAndroidCount').textContent = `${d['android-apk'] || 0} kez indirildi`;
    } catch {
      /* Static preview mode without control server running */
    }
  }

  async function startDownload(target) {
    const v = configData?.versions || {};
    const urls = {
      'windows-installer': v.windowsInstallerUrl || 'https://github.com/tahadigital/cineva/releases/latest/download/Cineva-Setup.exe',
      'windows-portable': v.windowsPortableUrl || 'https://github.com/tahadigital/cineva/releases/latest/download/Cineva.exe',
      'android-apk': v.androidApkUrl || 'https://github.com/tahadigital/cineva/releases/latest/download/Cineva-Android.apk',
    };
    const url = urls[target];
    try { await req('/api/v1/downloads/track', { method: 'POST', body: { target } }); loadConfig(); } catch {}
    const box = document.getElementById('downloadNotice');
    box.hidden = false;
    box.innerHTML = `İndirme başlatılıyor: <a href="${esc(url)}" style="color:var(--amber);text-decoration:underline">${esc(url)}</a>`;
    window.location.href = url;
  }

  async function refreshUserPanel() {
    const outBox = document.getElementById('accountLoggedOut');
    const inBox = document.getElementById('accountLoggedIn');
    const token = localStorage.getItem(tokenKey);
    if (!token) { outBox.hidden = false; inBox.hidden = true; return; }
    try {
      const { user } = await req('/api/v1/me');
      outBox.hidden = true; inBox.hidden = false;
      const planLabels = { free: 'Ücretsiz', pro: 'Cineva Pro', family: 'Aile Planı', lifetime: 'Ömür Boyu Pro' };
      document.getElementById('uProfileSummary').innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px">
          <div>
            <strong>${esc(user.displayName)}</strong>
            <div style="font-size:12px;color:var(--muted)">${esc(user.email)}</div>
          </div>
          <span class="badge ${esc(user.effectivePlan)}">${esc(planLabels[user.effectivePlan] || user.effectivePlan)}</span>
        </div>
        <div style="margin-top:10px;font-size:12px;color:var(--muted)">
          Cihaz Limiti: <strong>${(user.devices || []).length} / ${user.maxDevices}</strong>
          ${user.expiresAt ? ` · Bitiş: ${new Date(user.expiresAt).toLocaleDateString('tr-TR')}` : ''}
        </div>`;
      const devs = user.devices || [];
      document.getElementById('uDevicesList').innerHTML = devs.length
        ? `<div style="font-size:12px;color:var(--muted);margin-bottom:6px">Kayıtlı Cihazlar</div>` + devs.map(d => `<div style="font-size:13px;padding:6px 0;border-bottom:1px solid var(--border)">${esc(d.name)} <span class="badge">${esc(d.platform)}</span></div>`).join('')
        : '<p style="font-size:12px;color:var(--muted)">Henüz bağlı cihaz yok.</p>';
    } catch {
      localStorage.removeItem(tokenKey);
      outBox.hidden = false; inBox.hidden = true;
    }
  }

  function bindUi() {
    detectPlatform();
    loadConfig();
    document.querySelectorAll('[data-dl]').forEach(btn => btn.addEventListener('click', () => startDownload(btn.dataset.dl)));
    document.getElementById('howLocalBtn').addEventListener('click', () => {
      const box = document.getElementById('downloadNotice');
      box.hidden = false;
      box.innerHTML = `<strong>Yerel Web & Mac/Windows Hızlı Başlatma:</strong><br>Bilgisayarınızda proje klasöründe <code>python desktop/cineva_desktop.py</code> komutunu çalıştırın veya Windows'ta <code>windows\\Cineva.bat</code> dosyasına çift tıklayın. Aynı Wi-Fi'daki telefon veya TV tarayıcısından bağlanabilirsiniz.`;
    });
    const modal = document.getElementById('accountModal');
    document.getElementById('openAccountBtn').addEventListener('click', () => { modal.hidden = false; refreshUserPanel(); });
    document.getElementById('closeAccountModal').addEventListener('click', () => { modal.hidden = true; });
    document.querySelectorAll('[data-auth-tab]').forEach(tab => tab.addEventListener('click', () => {
      authMode = tab.dataset.authTab;
      document.querySelectorAll('[data-auth-tab]').forEach(t => t.classList.toggle('active', t === tab));
      document.getElementById('regNameWrap').hidden = authMode !== 'register';
      document.getElementById('uAuthSubmit').textContent = authMode === 'register' ? 'Hesap Oluştur' : 'Giriş Yap';
    }));
    document.getElementById('userAuthForm').addEventListener('submit', async e => {
      e.preventDefault();
      const err = document.getElementById('uAuthErr'); err.textContent = '';
      try {
        const res = await req(authMode === 'register' ? '/api/v1/auth/register' : '/api/v1/auth/login', {
          method: 'POST',
          body: {
            email: document.getElementById('uEmail').value.trim(),
            password: document.getElementById('uPass').value,
            displayName: document.getElementById('uName').value.trim(),
          },
        });
        localStorage.setItem(tokenKey, res.token);
        await refreshUserPanel();
      } catch (ex) { err.textContent = ex.message; }
    });
    document.getElementById('redeemForm').addEventListener('submit', async e => {
      e.preventDefault();
      const msg = document.getElementById('redeemMsg'); msg.className = 'ok-msg'; msg.textContent = '';
      try {
        const res = await req('/api/v1/licenses/redeem', { method: 'POST', body: { code: document.getElementById('licenseCodeInput').value.trim() } });
        msg.textContent = `Tebrikler! Planınız "${res.user.plan}" olarak güncellendi.`;
        document.getElementById('licenseCodeInput').value = '';
        await refreshUserPanel();
      } catch (ex) { msg.className = 'error-msg'; msg.textContent = ex.message; }
    });
    document.getElementById('uLogoutBtn').addEventListener('click', () => {
      localStorage.removeItem(tokenKey);
      refreshUserPanel();
    });
  }

  bindUi();
})();
