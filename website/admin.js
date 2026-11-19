'use strict';
(() => {
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const TOKEN_KEY = 'vrelio_admin_token';
  const API_KEY = 'vrelio_cloud_api';
  const apiBase = () => (localStorage.getItem(API_KEY) || '').replace(/\/$/, '');

  async function api(path, opts = {}) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const res = await fetch(apiBase() + path, {
      ...opts,
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 || res.status === 403) {
      if (path !== '/api/v1/auth/login') {
        localStorage.removeItem(TOKEN_KEY);
        showLogin(data.error || 'Oturum sona erdi.');
      }
    }
    if (!res.ok) throw new Error(data.error || `İşlem başarısız (${res.status})`);
    return data;
  }

  function showLogin(msg = '') {
    document.getElementById('adminLoginCard').hidden = false;
    document.getElementById('adminDashboard').hidden = true;
    document.getElementById('adminLogoutBtn').hidden = true;
    const editModal = document.getElementById('editUserModal');
    if (editModal) editModal.hidden = true;
    document.getElementById('adminLoginErr').textContent = msg;
  }

  async function showDashboard() {
    document.getElementById('adminLoginCard').hidden = true;
    document.getElementById('adminDashboard').hidden = false;
    document.getElementById('adminLogoutBtn').hidden = false;
    await Promise.all([loadOverview(), loadUsers(), loadLicenses(), loadConfig(), loadAudit()]);
  }

  async function loadOverview() {
    const o = await api('/api/v1/admin/overview');
    const dlTotal = Object.values(o.downloads || {}).reduce((a, b) => a + Number(b || 0), 0);
    document.getElementById('kpiGrid').innerHTML = [
      ['Toplam Hesap', o.totalUsers ?? 0],
      ['Aktif Pro', o.paidUsers ?? 0],
      ['3 Günlük Deneme', o.trialUsers ?? 0],
      ['Doğrulanmış E-posta', o.verifiedUsers ?? 0],
      ['Askıdaki Hesap', o.suspendedUsers ?? 0],
      ['Kayıtlı Cihaz', o.activeDevices ?? 0],
      ['Aktif Lisans Kodu', `${o.licensesRedeemed ?? 0} / ${o.licensesCreated ?? 0}`],
      ['Toplam İndirme', dlTotal],
    ].map(([l, v]) => `<div class="kpi-card"><div class="kpi-label">${esc(l)}</div><div class="kpi-val">${esc(v)}</div></div>`).join('');
  }

  async function loadUsers() {
    const qs = new URLSearchParams({
      q: document.getElementById('searchUser').value.trim(),
      plan: document.getElementById('filterPlan').value,
      status: document.getElementById('filterStatus').value,
    });
    const { users } = await api('/api/v1/admin/users?' + qs.toString());
    document.getElementById('usersTbody').innerHTML = (users || []).map(u => {
      const planText = u.trialActive ? 'Pro Deneme' : (u.effectivePlan === 'pro' ? 'Vrelio Pro' : 'Normal');
      const planClass = u.trialActive ? 'trial' : (u.effectivePlan || 'normal');
      const verBadge = u.emailVerified
        ? '<span class="badge verified">Doğrulandı</span>'
        : '<span class="badge unverified">Bekliyor</span>';
      return `
      <tr>
        <td><strong>${esc(u.email)}</strong> ${u.role === 'admin' ? '<span class="badge">ADMIN</span>' : ''}</td>
        <td>${esc(u.displayName)}</td>
        <td>${verBadge}</td>
        <td><span class="badge ${esc(planClass)}">${esc(planText)}</span></td>
        <td><span class="badge ${esc(u.status)}">${u.status === 'active' ? 'Aktif' : 'Askıda'}</span></td>
        <td>${esc(u.deviceCount ?? 0)} / ${esc(u.maxDevices)}</td>
        <td>${u.expiresAt ? new Date(u.expiresAt).toLocaleDateString('tr-TR') : (u.effectivePlan === 'pro' ? 'Süresiz' : '—')}</td>
        <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${esc(u.adminNote || '—')}</td>
        <td><button class="btn secondary small" data-edit-user="${esc(u.id)}" type="button">Düzenle</button></td>
      </tr>`;
    }).join('') || '<tr><td colspan="9" style="color:var(--muted)">Eşleşen hesap bulunamadı.</td></tr>';
    document.querySelectorAll('[data-edit-user]').forEach(btn => btn.addEventListener('click', async () => {
      try {
        await openEditUser(btn.dataset.editUser);
      } catch (err) {
        const msg = document.getElementById('euMsg');
        if (msg) { msg.className = 'error-msg'; msg.textContent = err.message; }
      }
    }));
  }

  async function openEditUser(id) {
    const { user } = await api(`/api/v1/admin/users/${encodeURIComponent(id)}`);
    document.getElementById('euId').value = user.id;
    document.getElementById('euEmailLabel').textContent = `${user.email} (${user.id})`;
    document.getElementById('euName').value = user.displayName;
    document.getElementById('euPlan').value = user.plan === 'pro' ? 'pro' : 'normal';
    document.getElementById('euStatus').value = user.status;
    document.getElementById('euRole').value = user.role || 'user';
    document.getElementById('euMaxDev').value = user.maxDevices;
    document.getElementById('euAddDays').value = '';
    document.getElementById('euNote').value = user.adminNote || '';
    document.getElementById('euVerified').checked = !!user.emailVerified;
    document.getElementById('euMsg').textContent = '';

    const devs = user.devices || [];
    document.getElementById('euDevicesSection').innerHTML = `<strong style="font-size:13px">Kayıtlı Cihazlar (${esc(devs.length)}/${esc(user.maxDevices)})</strong>` + (devs.length ? devs.map(d => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)">
        <span style="font-size:13px">${esc(d.name)} <span class="badge">${esc(d.platform)}</span></span>
        <button class="btn danger small" data-rm-dev="${esc(d.id)}" data-uid="${esc(user.id)}" type="button">Bağlantıyı Kes</button>
      </div>`).join('') : '<p style="font-size:12px;color:var(--muted)">Kayıtlı cihaz yok.</p>');
    document.querySelectorAll('[data-rm-dev]').forEach(b => b.addEventListener('click', async () => {
      const msg = document.getElementById('euMsg');
      if (msg) { msg.className = 'ok-msg'; msg.textContent = ''; }
      try {
        await api(`/api/v1/admin/users/${encodeURIComponent(b.dataset.uid)}/devices/${encodeURIComponent(b.dataset.rmDev)}`, { method: 'DELETE' });
        await openEditUser(b.dataset.uid);
        await Promise.all([loadOverview(), loadUsers(), loadAudit()]);
      } catch (err) {
        if (msg) { msg.className = 'error-msg'; msg.textContent = err.message; }
      }
    }));
    document.getElementById('editUserModal').hidden = false;
  }

  async function loadLicenses() {
    const { licenses } = await api('/api/v1/admin/licenses');
    document.getElementById('licensesTbody').innerHTML = (licenses || []).map(l => `
      <tr>
        <td><code>${esc(l.code)}</code></td>
        <td><span class="badge ${esc(l.plan)}">${esc(l.plan === 'pro' ? 'Vrelio Pro' : l.plan)}</span></td>
        <td>${l.durationDays ? esc(l.durationDays) + ' gün' : 'Süresiz'}</td>
        <td>${esc(l.maxDevices)}</td>
        <td>${esc(l.usesCount)} / ${esc(l.maxUses)}</td>
        <td>${esc(l.note || '—')}</td>
        <td><button class="btn danger small" data-del-lic="${esc(l.code)}" type="button">Sil</button></td>
      </tr>`).join('') || '<tr><td colspan="7" style="color:var(--muted)">Henüz lisans kodu üretilmedi.</td></tr>';
    document.querySelectorAll('[data-del-lic]').forEach(btn => btn.addEventListener('click', async () => {
      const msg = document.getElementById('licCreatedMsg');
      if (msg) { msg.className = 'ok-msg'; msg.textContent = ''; }
      try {
        await api(`/api/v1/admin/licenses/${encodeURIComponent(btn.dataset.delLic)}`, { method: 'DELETE' });
        await Promise.all([loadLicenses(), loadOverview(), loadAudit()]);
      } catch (err) {
        if (msg) { msg.className = 'error-msg'; msg.textContent = err.message; }
      }
    }));
  }

  async function loadConfig() {
    const cfg = await api('/api/v1/admin/config');
    const v = cfg.versions || {}, a = cfg.announcement || {};
    document.getElementById('cfgWinInstaller').value = v.windowsInstallerUrl || '';
    document.getElementById('cfgWinPortable').value = v.windowsPortableUrl || '';
    document.getElementById('cfgAndroidApk').value = v.androidApkUrl || '';
    document.getElementById('cfgMacosUrl').value = v.macosUrl || '';
    document.getElementById('cfgIosUrl').value = v.iosUrl || '';
    document.getElementById('cfgWinVer').value = v.windowsLatest || '2.1.0';
    document.getElementById('cfgAndroidVer').value = v.androidLatest || '2.1.0';
    document.getElementById('cfgMacosVer').value = v.macosLatest || '2.1.0';
    document.getElementById('cfgIosVer').value = v.iosLatest || '2.1.0';
    document.getElementById('cfgReleaseNotes').value = v.releaseNotes || '';
    document.getElementById('cfgAnnTitle').value = a.title || '';
    document.getElementById('cfgAnnMsg').value = a.message || '';
    document.getElementById('cfgAnnSeverity').value = a.severity || 'info';
    document.getElementById('cfgAnnEnabled').checked = !!a.enabled;
  }

  async function loadAudit() {
    const { logs } = await api('/api/v1/admin/audit');
    document.getElementById('auditTbody').innerHTML = (logs || []).map(log => `
      <tr>
        <td>${new Date(log.createdAt).toLocaleString('tr-TR')}</td>
        <td>${esc(log.actorEmail)}</td>
        <td><code>${esc(log.action)}</code></td>
        <td>${esc(log.targetId)}</td>
        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis">${esc(JSON.stringify(log.details))}</td>
      </tr>`).join('') || '<tr><td colspan="5" style="color:var(--muted)">Henüz kayıt yok.</td></tr>';
  }

  function bind() {
    document.getElementById('adminApiUrl').value = localStorage.getItem(API_KEY) || '';
    document.getElementById('adminLoginForm').addEventListener('submit', async e => {
      e.preventDefault();
      const customApi = document.getElementById('adminApiUrl').value.trim();
      if (customApi) localStorage.setItem(API_KEY, customApi); else localStorage.removeItem(API_KEY);
      document.getElementById('adminLoginErr').textContent = '';
      try {
        const res = await api('/api/v1/auth/login', {
          method: 'POST',
          body: { email: document.getElementById('adminEmail').value.trim(), password: document.getElementById('adminPassword').value },
        });
        if (res.user?.role !== 'admin') throw new Error('Bu hesabın yönetici yetkisi yok.');
        localStorage.setItem(TOKEN_KEY, res.token);
        await showDashboard();
      } catch (err) {
        document.getElementById('adminLoginErr').textContent = err.message;
      }
    });
    document.getElementById('adminLogoutBtn').addEventListener('click', () => { localStorage.removeItem(TOKEN_KEY); showLogin(); });
    document.querySelectorAll('[data-tab]').forEach(btn => btn.addEventListener('click', () => {
      document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b === btn));
      ['users', 'licenses', 'config', 'audit', 'guide'].forEach(name => {
        const el = document.getElementById('tab-' + name);
        if (el) el.hidden = name !== btn.dataset.tab;
      });
    }));
    ['searchUser', 'filterPlan', 'filterStatus'].forEach(id => document.getElementById(id).addEventListener('input', () => loadUsers().catch(() => {})));
    document.getElementById('refreshUsersBtn').addEventListener('click', async () => {
      try {
        await Promise.all([loadOverview(), loadUsers()]);
      } catch (err) {
        const msg = document.getElementById('euMsg');
        if (msg) { msg.className = 'error-msg'; msg.textContent = err.message; }
      }
    });
    document.getElementById('closeEditUser').addEventListener('click', () => { document.getElementById('editUserModal').hidden = true; });
    document.getElementById('editUserForm').addEventListener('submit', async e => {
      e.preventDefault();
      const uid = document.getElementById('euId').value;
      const patch = {
        displayName: document.getElementById('euName').value.trim(),
        plan: document.getElementById('euPlan').value,
        status: document.getElementById('euStatus').value,
        role: document.getElementById('euRole').value,
        maxDevices: Number(document.getElementById('euMaxDev').value) || 1,
        adminNote: document.getElementById('euNote').value,
        emailVerified: document.getElementById('euVerified').checked,
      };
      const addDays = Number(document.getElementById('euAddDays').value);
      if (addDays > 0) patch.addDays = addDays;
      const msg = document.getElementById('euMsg'); msg.className = 'ok-msg'; msg.textContent = '';
      try {
        await api(`/api/v1/admin/users/${encodeURIComponent(uid)}`, { method: 'PATCH', body: patch });
        msg.textContent = 'Hesap güncellendi.';
        await Promise.all([loadOverview(), loadUsers(), loadAudit()]);
      } catch (err) { msg.className = 'error-msg'; msg.textContent = err.message; }
    });
    document.getElementById('euResetBtn').addEventListener('click', async () => {
      const uid = document.getElementById('euId').value;
      const msg = document.getElementById('euMsg');
      msg.className = 'ok-msg';
      msg.textContent = '';
      try {
        const res = await api(`/api/v1/admin/users/${encodeURIComponent(uid)}/reset-password-token`, { method: 'POST', body: {} });
        msg.textContent = `Tek kullanımlık sıfırlama kodu (1 saat geçerli): ${res.resetToken}`;
        await loadAudit();
      } catch (err) {
        msg.className = 'error-msg';
        msg.textContent = err.message;
      }
    });
    document.getElementById('createLicenseForm').addEventListener('submit', async e => {
      e.preventDefault();
      const msg = document.getElementById('licCreatedMsg'); msg.className = 'ok-msg'; msg.textContent = '';
      try {
        const res = await api('/api/v1/admin/licenses', {
          method: 'POST',
          body: {
            plan: document.getElementById('licPlan').value,
            durationDays: Number(document.getElementById('licDays').value) || 365,
            maxDevices: Number(document.getElementById('licDevs').value) || 5,
            maxUses: Number(document.getElementById('licUses').value) || 1,
            note: document.getElementById('licNote').value.trim(),
          },
        });
        msg.textContent = `Üretilen Anahtar: ${res.license.code}`;
        await Promise.all([loadLicenses(), loadOverview(), loadAudit()]);
      } catch (err) { msg.className = 'error-msg'; msg.textContent = err.message; }
    });
    document.getElementById('adminConfigForm').addEventListener('submit', async e => {
      e.preventDefault();
      const msg = document.getElementById('cfgMsg'); msg.className = 'ok-msg'; msg.textContent = '';
      try {
        await api('/api/v1/admin/config', {
          method: 'PUT',
          body: {
            versions: {
              windowsInstallerUrl: document.getElementById('cfgWinInstaller').value.trim(),
              windowsPortableUrl: document.getElementById('cfgWinPortable').value.trim(),
              androidApkUrl: document.getElementById('cfgAndroidApk').value.trim(),
              macosUrl: document.getElementById('cfgMacosUrl').value.trim(),
              iosUrl: document.getElementById('cfgIosUrl').value.trim(),
              windowsLatest: document.getElementById('cfgWinVer').value.trim(),
              androidLatest: document.getElementById('cfgAndroidVer').value.trim(),
              macosLatest: document.getElementById('cfgMacosVer').value.trim(),
              iosLatest: document.getElementById('cfgIosVer').value.trim(),
              releaseNotes: document.getElementById('cfgReleaseNotes').value.trim(),
            },
            announcement: {
              enabled: document.getElementById('cfgAnnEnabled').checked,
              title: document.getElementById('cfgAnnTitle').value.trim(),
              message: document.getElementById('cfgAnnMsg').value.trim(),
              severity: document.getElementById('cfgAnnSeverity').value,
            },
          },
        });
        msg.textContent = 'Ayarlar kaydedildi ve yayınlandı.';
        await loadAudit();
      } catch (err) { msg.className = 'error-msg'; msg.textContent = err.message; }
    });

    if (localStorage.getItem(TOKEN_KEY)) showDashboard().catch(() => showLogin());
    else showLogin();
  }

  bind();
})();
