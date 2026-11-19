'use strict';
(() => {
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const apiBase = () => (localStorage.getItem('vrelio_cloud_api') || '').replace(/\/$/, '');
  const tokenKey = 'vrelio_user_token';
  const GITHUB_DL_BASE = 'https://github.com/tahadigital/cineva/releases/latest/download/';

  let configData = null;
  let authMode = 'login';
  let authView = 'login';
  let pendingVerifyEmail = '';
  let trialCountdownTimer = null;
  let resendCooldownTimer = null;

  async function req(path, opts = {}) {
    const token = localStorage.getItem(tokenKey);
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const res = await fetch(apiBase() + path, {
      ...opts,
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.error || `Hata (${res.status})`);
      err.code = data.code || '';
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function resolveDownloadUrls() {
    const v = configData?.versions || {};
    return {
      'windows-installer': v.windowsInstallerUrl || GITHUB_DL_BASE + 'Vrelio-Setup.exe',
      'windows-portable': v.windowsPortableUrl || GITHUB_DL_BASE + 'Vrelio.exe',
      'android-apk': v.androidApkUrl || GITHUB_DL_BASE + 'Vrelio-Android.apk',
      'macos': v.macosUrl || GITHUB_DL_BASE + 'Vrelio-macOS.dmg',
      'ios': v.iosUrl || GITHUB_DL_BASE + 'Vrelio-iOS.ipa',
    };
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
      primary.onclick = e => { e.preventDefault(); return startDownload('android-apk'); };
      secondary.textContent = 'Windows (.exe)';
      secondary.onclick = e => { e.preventDefault(); return startDownload('windows-installer'); };
      hint.textContent = 'Android cihaz algılandı — önerilen Vrelio-Android.apk sürümü seçildi.';
    } else if (isIos) {
      primary.textContent = 'iOS için İndir (.ipa)';
      primary.onclick = e => { e.preventDefault(); return startDownload('ios'); };
      secondary.textContent = 'macOS (.dmg)';
      secondary.onclick = e => { e.preventDefault(); return startDownload('macos'); };
      hint.textContent = 'iOS cihaz algılandı — imzasız sideload IPA (AltStore / Sideloadly) önerildi.';
    } else if (isMac) {
      primary.textContent = 'macOS için İndir (.dmg)';
      primary.onclick = e => { e.preventDefault(); return startDownload('macos'); };
      secondary.textContent = 'Windows (.exe)';
      secondary.onclick = e => { e.preventDefault(); return startDownload('windows-installer'); };
      hint.textContent = 'macOS algılandı — Apple Silicon & Intel uyumlu Vrelio-macOS.dmg seçildi.';
    } else {
      primary.textContent = 'Windows için İndir (Vrelio-Setup.exe)';
      primary.onclick = e => { e.preventDefault(); return startDownload('windows-installer'); };
      secondary.textContent = 'Android APK İndir';
      secondary.onclick = e => { e.preventDefault(); return startDownload('android-apk'); };
      hint.textContent = isWin
        ? 'Windows algılandı — kurulum sihirbazı tek tıkla kurulur.'
        : 'Windows, Android, macOS ve iOS sürümlerinden cihazınıza uygun olanı seçin.';
    }
  }

  async function loadConfig() {
    try {
      configData = await req('/api/v1/app-config');
      const ann = configData.announcement || {};
      const bar = document.getElementById('announceBanner');
      if (bar) {
        if (ann.enabled && (ann.title || ann.message)) {
          bar.hidden = false;
          bar.className = 'announce-bar' + (ann.severity === 'critical' ? ' critical' : '');
          bar.innerHTML = `<strong>${esc(ann.title)}</strong> ${esc(ann.message)}`;
        } else {
          bar.hidden = true;
        }
      }

      const v = configData.versions || {};
      const d = configData.downloads || {};
      const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

      setTxt('winVerBadge', `Windows 10/11 · v${v.windowsLatest || v.latestVersion || '2.1.0'}`);
      setTxt('androidVerBadge', `Android 8+ · v${v.androidLatest || v.latestVersion || '2.1.0'}`);
      setTxt('macosVerBadge', `macOS 13+ · v${v.macosLatest || v.latestVersion || '2.1.0'}`);
      setTxt('iosVerBadge', `iOS 16+ · v${v.iosLatest || v.latestVersion || '2.1.0'}`);

      setTxt('dlWinCount', `${(d['windows-installer'] || 0) + (d['windows-portable'] || 0)} kez indirildi`);
      setTxt('dlAndroidCount', `${d['android-apk'] || 0} kez indirildi`);
      setTxt('dlMacCount', `${d.macos || 0} kez indirildi`);
      setTxt('dlIosCount', `${d.ios || 0} kez indirildi`);

      if (v.releaseNotes) setTxt('releaseNotesText', v.releaseNotes);

      const plans = configData.plans || {};
      if (plans.normal?.maxDevices) setTxt('planNormalDevices', String(plans.normal.maxDevices));
      if (plans.pro?.maxDevices) setTxt('planProDevices', String(plans.pro.maxDevices));
      if (plans.pro?.trialDays) setTxt('planProTrialDays', String(plans.pro.trialDays));
    } catch {
      /* Static preview mode without control server running */
    }
  }

  async function startDownload(target) {
    const urls = resolveDownloadUrls();
    const url = urls[target];
    if (!url || !/^(?:https?:\/\/|\/(?!\/))/i.test(url)) return;
    try {
      await req('/api/v1/downloads/track', { method: 'POST', body: { target } });
      await loadConfig();
    } catch {
      /* Tracking is best-effort */
    }
    const box = document.getElementById('downloadNotice');
    if (box) {
      box.hidden = false;
      box.innerHTML = `İndirme başlatılıyor: <a href="${esc(url)}" style="color:var(--amber);text-decoration:underline">${esc(url)}</a>`;
    }
    if (typeof window !== 'undefined' && window.location) {
      window.location.href = url;
    }
  }

  function clearCountdown() {
    if (trialCountdownTimer) {
      clearInterval(trialCountdownTimer);
      trialCountdownTimer = null;
    }
  }

  function formatRemaining(ms) {
    const totalSec = Math.max(0, Math.floor(ms / 1000));
    const days = Math.floor(totalSec / 86400);
    const hours = Math.floor((totalSec % 86400) / 3600);
    const mins = Math.floor((totalSec % 3600) / 60);
    const secs = totalSec % 60;
    return `${days} gün ${hours} sa ${mins} dk ${secs} sn kaldı`;
  }

  function startTrialCountdown(user) {
    clearCountdown();
    const box = document.getElementById('uTrialCountdownBox');
    if (!box) return;

    if (user.trialActive && user.trialEndsAt) {
      box.hidden = false;
      box.className = 'trial-box';
      const endMs = Date.parse(user.trialEndsAt);
      const startMs = user.trialStartedAt ? Date.parse(user.trialStartedAt) : endMs - 72 * 3600 * 1000;
      const totalSpan = Math.max(1, endMs - startMs);

      const renderTick = () => {
        const rem = Math.max(0, endMs - Date.now());
        const pct = Math.max(4, Math.min(100, Math.round((rem / totalSpan) * 100)));
        box.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
            <strong style="font-size:13px">3 Günlük Ücretsiz Vrelio Pro Denemesi Aktif</strong>
            <span class="badge trial">Deneme</span>
          </div>
          <div class="countdown-pill">${rem > 0 ? esc(formatRemaining(rem)) : 'Deneme süresi doldu'}</div>
          <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
        `;
        if (rem <= 0) clearCountdown();
      };
      renderTick();
      trialCountdownTimer = setInterval(renderTick, 1000);
      return;
    }

    if (user.trialUsed && !user.isPro) {
      box.hidden = false;
      box.className = 'trial-box expired';
      box.innerHTML = `
        <strong style="font-size:13px">3 Günlük Pro Denemeniz Sona Erdi</strong>
        <p style="margin:4px 0 0;font-size:12.5px;color:var(--muted)">Hesabınız Normal plana geçti. Bulut eşitleme, 5 cihaz sınırı ve 2×2 Çoklu Ekran için aşağıdan bir VRELIO lisans anahtarı etkinleştirin.</p>
      `;
      return;
    }

    box.hidden = true;
    box.innerHTML = '';
  }

  function startResendCooldown(seconds = 30) {
    const btn = document.getElementById('resendVerifyBtn');
    if (!btn) return;
    if (resendCooldownTimer) clearInterval(resendCooldownTimer);
    let left = seconds;
    btn.disabled = true;
    btn.textContent = `Kodu Tekrar Gönder (${left}s)`;
    resendCooldownTimer = setInterval(() => {
      left -= 1;
      if (left <= 0) {
        clearInterval(resendCooldownTimer);
        resendCooldownTimer = null;
        btn.disabled = false;
        btn.textContent = 'Kodu Tekrar Gönder';
      } else {
        btn.textContent = `Kodu Tekrar Gönder (${left}s)`;
      }
    }, 1000);
  }

  function switchAuthView(view, emailPrefill = '') {
    authView = view;
    const outBox = document.getElementById('accountLoggedOut');
    if (outBox) outBox.dataset.authView = view;

    const tabs = document.getElementById('authViewTabs');
    const authForm = document.getElementById('userAuthForm');
    const verifyPanel = document.getElementById('verifyEmailPanel');
    const forgotPanel = document.getElementById('forgotPassPanel');
    const resetPanel = document.getElementById('resetPassPanel');

    const isBase = view === 'login' || view === 'register';
    if (tabs) tabs.hidden = !isBase;
    if (authForm) authForm.hidden = !isBase;
    if (verifyPanel) verifyPanel.hidden = view !== 'verify';
    if (forgotPanel) forgotPanel.hidden = view !== 'forgot';
    if (resetPanel) resetPanel.hidden = view !== 'reset';

    if (isBase) {
      authMode = view;
      document.querySelectorAll('[data-auth-tab]').forEach(t => {
        t.classList.toggle('active', t.dataset.authTab === view);
      });
      const regWrap = document.getElementById('regNameWrap');
      const submitBtn = document.getElementById('uAuthSubmit');
      const forgotBtn = document.getElementById('openForgotBtn');
      const passInput = document.getElementById('uPass');
      if (regWrap) regWrap.hidden = view !== 'register';
      if (submitBtn) submitBtn.textContent = view === 'register' ? 'Hesap Oluştur ve Kod Gönder' : 'Giriş Yap';
      if (forgotBtn) forgotBtn.hidden = view !== 'login';
      if (passInput) passInput.autocomplete = view === 'register' ? 'new-password' : 'current-password';
      if (emailPrefill) {
        const uEmail = document.getElementById('uEmail');
        if (uEmail) uEmail.value = emailPrefill;
      }
    }

    if (view === 'verify') {
      if (emailPrefill) pendingVerifyEmail = emailPrefill;
      const target = document.getElementById('verifyEmailTarget');
      if (target) target.textContent = pendingVerifyEmail || 'kayıtlı e-posta';
      const codeInput = document.getElementById('verifyCodeInput');
      if (codeInput) codeInput.value = '';
    }

    if (view === 'forgot') {
      const fEmail = document.getElementById('forgotEmailInput');
      if (fEmail && emailPrefill) fEmail.value = emailPrefill;
    }

    if (view === 'reset') {
      const rEmail = document.getElementById('resetEmailInput');
      if (rEmail && emailPrefill) rEmail.value = emailPrefill;
    }
  }

  async function refreshUserPanel() {
    const outBox = document.getElementById('accountLoggedOut');
    const inBox = document.getElementById('accountLoggedIn');
    const openBtn = document.getElementById('openAccountBtn');
    const token = localStorage.getItem(tokenKey);

    if (!token || token === 'undefined' || token === 'null') {
      localStorage.removeItem(tokenKey);
      clearCountdown();
      if (outBox) outBox.hidden = false;
      if (inBox) inBox.hidden = true;
      if (openBtn) openBtn.textContent = 'Hesabım / Pro';
      return;
    }

    try {
      const { user } = await req('/api/v1/me');
      if (outBox) outBox.hidden = true;
      if (inBox) inBox.hidden = false;

      const planLabels = { normal: 'Normal (Ücretsiz)', pro: 'Vrelio Pro' };
      const planBadgeClass = user.trialActive ? 'trial' : (user.effectivePlan || 'normal');
      const planBadgeLabel = user.trialActive ? 'Pro Deneme (3 Gün)' : (planLabels[user.effectivePlan] || user.effectivePlan);
      const verifiedBadge = user.emailVerified
        ? '<span class="badge verified">E-posta Doğrulandı</span>'
        : '<span class="badge unverified">Doğrulama Bekliyor</span>';

      if (openBtn) openBtn.textContent = `${user.displayName || 'Hesabım'} (${user.isPro ? 'Pro' : 'Normal'})`;

      document.getElementById('uProfileSummary').innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
          <div>
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <strong>${esc(user.displayName)}</strong>
              ${verifiedBadge}
            </div>
            <div style="font-size:12px;color:var(--muted);margin-top:3px">${esc(user.email)}</div>
          </div>
          <span class="badge ${esc(planBadgeClass)}">${esc(planBadgeLabel)}</span>
        </div>
        <div style="margin-top:10px;font-size:12px;color:var(--muted)">
          Cihaz Limiti: <strong>${(user.devices || []).length} / ${esc(user.maxDevices)}</strong>
          ${user.expiresAt ? ` · Bitiş: ${new Date(user.expiresAt).toLocaleDateString('tr-TR')}` : (user.isPro ? ' · Süresiz Pro' : '')}
        </div>`;

      startTrialCountdown(user);

      const f = user.features || {};
      const entEl = document.getElementById('uPlanGateSummary');
      if (entEl) {
        const items = [
          ['Bulut Eşitleme', !!f.cloudSync],
          ['2×2 Çoklu Ekran', !!f.multiView],
          ['Sınırsız Profil & PIN', !!f.unlimitedProfiles],
          ['EPG Spor Eşleme', !!f.epgMatch],
          ['Gelişmiş Ses/Altyazı', !!f.advancedTracks],
        ];
        entEl.innerHTML = items.map(([label, on]) =>
          `<span class="ent-chip ${on ? 'on' : ''}">${on ? '✓' : '🔒'} ${esc(label)}</span>`
        ).join('');
      }

      const devs = user.devices || [];
      const devList = document.getElementById('uDevicesList');
      devList.innerHTML = devs.length
        ? `<div style="font-size:12px;color:var(--muted);margin-bottom:6px">Kayıtlı Cihazlar (${devs.length}/${esc(user.maxDevices)})</div>` +
          devs.map(d => `
            <div class="device-row">
              <div style="font-size:13px">
                <strong>${esc(d.name)}</strong>
                <span class="badge" style="margin-left:6px">${esc(d.platform)}</span>
              </div>
              <button class="btn danger small" type="button" data-rm-user-dev="${esc(d.id)}">Cihazı Kaldır</button>
            </div>`).join('')
        : '<p style="font-size:12px;color:var(--muted)">Henüz bağlı cihaz yok.</p>';

      devList.querySelectorAll('[data-rm-user-dev]').forEach(btn => {
        btn.addEventListener('click', async () => {
          btn.disabled = true;
          try {
            await req(`/api/v1/devices/${encodeURIComponent(btn.dataset.rmUserDev)}`, { method: 'DELETE' });
            await refreshUserPanel();
          } catch (ex) {
            btn.disabled = false;
            const msg = document.getElementById('redeemMsg');
            if (msg) { msg.className = 'error-msg'; msg.textContent = ex.message; }
          }
        });
      });
    } catch {
      localStorage.removeItem(tokenKey);
      clearCountdown();
      if (outBox) outBox.hidden = false;
      if (inBox) inBox.hidden = true;
      if (openBtn) openBtn.textContent = 'Hesabım / Pro';
    }
  }

  function openAccountModal(initialView = 'login') {
    const modal = document.getElementById('accountModal');
    if (!modal) return;
    modal.hidden = false;
    const cel = document.getElementById('uVerifyCelebration');
    if (cel) { cel.hidden = true; cel.textContent = ''; }
    const authErr = document.getElementById('uAuthErr');
    if (authErr) authErr.textContent = '';
    const authOk = document.getElementById('uAuthOk');
    if (authOk) { authOk.hidden = true; authOk.textContent = ''; }
    switchAuthView(initialView);
    refreshUserPanel();
  }

  function bindUi() {
    detectPlatform();
    loadConfig();
    refreshUserPanel();

    document.querySelectorAll('[data-dl]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.preventDefault();
        return startDownload(btn.dataset.dl);
      });
    });

    const modal = document.getElementById('accountModal');
    document.getElementById('openAccountBtn')?.addEventListener('click', () => openAccountModal('login'));
    document.getElementById('heroTrialBtn')?.addEventListener('click', () => openAccountModal('register'));
    document.getElementById('bannerTrialBtn')?.addEventListener('click', () => openAccountModal('register'));
    document.getElementById('startTrialFromPlansBtn')?.addEventListener('click', () => openAccountModal('register'));
    document.querySelectorAll('[data-open-auth]').forEach(btn => {
      btn.addEventListener('click', () => openAccountModal(btn.dataset.openAuth || 'login'));
    });

    document.getElementById('closeAccountModal')?.addEventListener('click', () => {
      if (modal) modal.hidden = true;
    });
    modal?.addEventListener('click', e => {
      if (e.target === modal) modal.hidden = true;
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && modal && !modal.hidden) modal.hidden = true;
    });

    document.querySelectorAll('[data-auth-tab]').forEach(tab => {
      tab.addEventListener('click', () => {
        document.getElementById('uAuthErr').textContent = '';
        const ok = document.getElementById('uAuthOk');
        if (ok) { ok.hidden = true; ok.textContent = ''; }
        switchAuthView(tab.dataset.authTab);
      });
    });

    document.getElementById('openForgotBtn')?.addEventListener('click', () => {
      document.getElementById('forgotErr').textContent = '';
      document.getElementById('forgotMsg').textContent = '';
      const email = document.getElementById('uEmail').value.trim();
      switchAuthView('forgot', email);
    });

    document.getElementById('verifyBackLoginBtn')?.addEventListener('click', () => switchAuthView('login', pendingVerifyEmail));
    document.getElementById('forgotBackLoginBtn')?.addEventListener('click', () => switchAuthView('login'));
    document.getElementById('resetBackLoginBtn')?.addEventListener('click', () => switchAuthView('login'));
    document.getElementById('forgotHaveCodeBtn')?.addEventListener('click', () => {
      const email = document.getElementById('forgotEmailInput').value.trim();
      switchAuthView('reset', email);
    });

    // 1. Login / Register form
    document.getElementById('userAuthForm')?.addEventListener('submit', async e => {
      e.preventDefault();
      const err = document.getElementById('uAuthErr');
      const ok = document.getElementById('uAuthOk');
      err.textContent = '';
      if (ok) { ok.hidden = true; ok.textContent = ''; }

      const email = document.getElementById('uEmail').value.trim();
      const password = document.getElementById('uPass').value;
      const displayName = document.getElementById('uName').value.trim();

      try {
        const endpoint = authMode === 'register' ? '/api/v1/auth/register' : '/api/v1/auth/login';
        const res = await req(endpoint, {
          method: 'POST',
          body: { email, password, displayName },
        });

        if (authMode === 'register' && (res.verificationRequired || !res.token)) {
          pendingVerifyEmail = res.user?.email || email;
          document.getElementById('verifyErr').textContent = '';
          document.getElementById('verifyMsg').textContent = '6 haneli doğrulama kodu e-postanıza gönderildi.';
          switchAuthView('verify', pendingVerifyEmail);
          return;
        }

        if (res.token) {
          localStorage.setItem(tokenKey, res.token);
          await refreshUserPanel();
        }
      } catch (ex) {
        if (ex.code === 'EMAIL_NOT_VERIFIED') {
          pendingVerifyEmail = ex.data?.email || email;
          document.getElementById('verifyMsg').textContent = '';
          document.getElementById('verifyErr').textContent = ex.message || 'E-posta doğrulaması gerekli. Kodunuzu girin veya yeni kod isteyin.';
          switchAuthView('verify', pendingVerifyEmail);
          return;
        }
        err.textContent = ex.message;
      }
    });

    // 2. Verify Email form
    document.getElementById('verifyEmailForm')?.addEventListener('submit', async e => {
      e.preventDefault();
      const err = document.getElementById('verifyErr');
      const msg = document.getElementById('verifyMsg');
      err.textContent = '';
      msg.textContent = '';
      try {
        const code = document.getElementById('verifyCodeInput').value.trim();
        const res = await req('/api/v1/auth/verify-email', {
          method: 'POST',
          body: { email: pendingVerifyEmail, code },
        });
        if (res.token) {
          localStorage.setItem(tokenKey, res.token);
        }
        const cel = document.getElementById('uVerifyCelebration');
        if (cel) {
          cel.hidden = false;
          cel.textContent = res.trialActivated
            ? 'E-posta doğrulandı! 3 günlük ücretsiz Vrelio Pro denemeniz otomatik başlatıldı.'
            : 'E-posta adresiniz başarıyla doğrulandı.';
        }
        await refreshUserPanel();
      } catch (ex) {
        err.textContent = ex.message;
      }
    });

    // 3. Resend Verification button
    document.getElementById('resendVerifyBtn')?.addEventListener('click', async () => {
      const err = document.getElementById('verifyErr');
      const msg = document.getElementById('verifyMsg');
      err.textContent = '';
      msg.textContent = '';
      try {
        await req('/api/v1/auth/resend-verification', {
          method: 'POST',
          body: { email: pendingVerifyEmail },
        });
        msg.textContent = 'Yeni doğrulama kodu gönderildi.';
        startResendCooldown(30);
      } catch (ex) {
        err.textContent = ex.message;
      }
    });

    // 4. Forgot Password form
    document.getElementById('forgotPassForm')?.addEventListener('submit', async e => {
      e.preventDefault();
      const err = document.getElementById('forgotErr');
      const msg = document.getElementById('forgotMsg');
      err.textContent = '';
      msg.textContent = '';
      const email = document.getElementById('forgotEmailInput').value.trim();
      try {
        const res = await req('/api/v1/auth/forgot-password', {
          method: 'POST',
          body: { email },
        });
        document.getElementById('resetErr').textContent = '';
        document.getElementById('resetMsg').textContent = res.message || 'Sıfırlama kodu gönderildi.';
        switchAuthView('reset', email);
      } catch (ex) {
        err.textContent = ex.message;
      }
    });

    // 5a. Inline Verify Reset Code button
    document.getElementById('verifyResetCodeBtn')?.addEventListener('click', async () => {
      const err = document.getElementById('resetErr');
      const msg = document.getElementById('resetMsg');
      err.textContent = '';
      msg.textContent = '';
      const email = document.getElementById('resetEmailInput').value.trim();
      const code = document.getElementById('resetCodeInput').value.trim();
      try {
        await req('/api/v1/auth/verify-reset-code', {
          method: 'POST',
          body: { email, code },
        });
        msg.textContent = 'Kod doğrulandı — yeni parolanızı belirleyebilirsiniz.';
      } catch (ex) {
        err.textContent = ex.message;
      }
    });

    // 5b. Complete Password Reset form
    document.getElementById('resetPassForm')?.addEventListener('submit', async e => {
      e.preventDefault();
      const err = document.getElementById('resetErr');
      const msg = document.getElementById('resetMsg');
      err.textContent = '';
      msg.textContent = '';
      const email = document.getElementById('resetEmailInput').value.trim();
      const code = document.getElementById('resetCodeInput').value.trim();
      const newPassword = document.getElementById('resetNewPassInput').value;
      try {
        await req('/api/v1/auth/reset-password', {
          method: 'POST',
          body: { email, code, newPassword },
        });
        document.getElementById('resetCodeInput').value = '';
        document.getElementById('resetNewPassInput').value = '';
        document.getElementById('uAuthErr').textContent = '';
        const ok = document.getElementById('uAuthOk');
        if (ok) {
          ok.hidden = false;
          ok.textContent = 'Parolanız güncellendi, yeni parolanızla giriş yapabilirsiniz.';
        }
        switchAuthView('login', email);
      } catch (ex) {
        err.textContent = ex.message;
      }
    });

    // License Redeem
    document.getElementById('redeemForm')?.addEventListener('submit', async e => {
      e.preventDefault();
      const msg = document.getElementById('redeemMsg');
      msg.className = 'ok-msg';
      msg.textContent = '';
      try {
        const res = await req('/api/v1/licenses/redeem', {
          method: 'POST',
          body: { code: document.getElementById('licenseCodeInput').value.trim() },
        });
        msg.textContent = `Tebrikler! Planınız "${res.user.effectivePlan === 'pro' ? 'Vrelio Pro' : res.user.plan}" olarak güncellendi.`;
        document.getElementById('licenseCodeInput').value = '';
        await refreshUserPanel();
      } catch (ex) {
        msg.className = 'error-msg';
        msg.textContent = ex.message;
      }
    });

    // Logout
    document.getElementById('uLogoutBtn')?.addEventListener('click', () => {
      localStorage.removeItem(tokenKey);
      const cel = document.getElementById('uVerifyCelebration');
      if (cel) { cel.hidden = true; cel.textContent = ''; }
      const redeemMsg = document.getElementById('redeemMsg');
      if (redeemMsg) { redeemMsg.className = 'ok-msg'; redeemMsg.textContent = ''; }
      switchAuthView('login');
      refreshUserPanel();
    });
  }

  bindUi();
})();
