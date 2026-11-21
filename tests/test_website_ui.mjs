import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const WEBSITE_DIR = path.resolve("website");

function readWeb(rel) {
  return fs.readFileSync(path.join(WEBSITE_DIR, rel), "utf8");
}

function makeMockElement(id = "", tagName = "DIV") {
  const listeners = new Map();
  const classes = new Set();
  const dataset = {};
  const el = {
    id,
    tagName,
    hidden: false,
    disabled: false,
    checked: false,
    value: "",
    textContent: "",
    innerHTML: "",
    className: "",
    href: "",
    autocomplete: "",
    dataset,
    style: {},
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      toggle: (c, force) => {
        if (force === undefined) {
          if (classes.has(c)) classes.delete(c);
          else classes.add(c);
        } else if (force) classes.add(c);
        else classes.delete(c);
      },
      contains: (c) => classes.has(c),
    },
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    async trigger(type, extra = {}) {
      const evt = {
        type,
        target: el,
        preventDefault() {},
        ...extra,
      };
      if (typeof el["on" + type] === "function") {
        await el["on" + type](evt);
      }
      for (const fn of listeners.get(type) || []) {
        await fn(evt);
      }
    },
    querySelectorAll() {
      return [];
    },
  };
  return el;
}

function runPortalHarness({ userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", fetchHandler }) {
  const elements = new Map();
  const ensureEl = (id, tag = "DIV") => {
    if (!elements.has(id)) elements.set(id, makeMockElement(id, tag));
    return elements.get(id);
  };

  const ids = [
    "announceBanner", "openAccountBtn", "primaryDownloadBtn", "secondaryDownloadBtn",
    "heroTrialBtn", "bannerTrialBtn", "startTrialFromPlansBtn", "platformHint",
    "winVerBadge", "androidVerBadge", "macosVerBadge", "iosVerBadge",
    "dlWinCount", "dlAndroidCount", "dlMacCount", "dlIosCount",
    "releaseNotesText", "planNormalDevices", "planProDevices", "planProTrialDays",
    "downloadNotice", "accountModal", "closeAccountModal", "accountLoggedOut",
    "authViewTabs", "userAuthForm", "regNameWrap", "uName", "uEmail", "uPass",
    "uAuthOk", "uAuthErr", "uAuthSubmit", "openForgotBtn",
    "verifyEmailPanel", "verifyEmailTarget", "verifyEmailForm", "verifyCodeInput",
    "verifyMsg", "verifyErr", "resendVerifyBtn", "verifyBackLoginBtn",
    "forgotPassPanel", "forgotPassForm", "forgotEmailInput", "forgotMsg", "forgotErr",
    "forgotHaveCodeBtn", "forgotBackLoginBtn",
    "resetPassPanel", "resetPassForm", "resetEmailInput", "resetCodeInput",
    "verifyResetCodeBtn", "resetNewPassInput", "resetMsg", "resetErr", "resetBackLoginBtn",
    "accountLoggedIn", "uVerifyCelebration", "uProfileSummary", "uTrialCountdownBox",
    "uPlanGateSummary", "redeemForm", "licenseCodeInput", "redeemMsg", "uDevicesList",
    "uLogoutBtn",
  ];
  for (const id of ids) ensureEl(id);

  const tabLogin = makeMockElement("", "BUTTON");
  tabLogin.dataset.authTab = "login";
  tabLogin.classList.add("active");
  const tabRegister = makeMockElement("", "BUTTON");
  tabRegister.dataset.authTab = "register";

  const dlButtons = ["windows-installer", "windows-portable", "android-apk", "macos", "ios"].map((t) => {
    const b = makeMockElement("", "BUTTON");
    b.dataset.dl = t;
    return b;
  });

  const devButtons = [];
  const uDevicesList = ensureEl("uDevicesList");
  let devicesHtml = "";
  Object.defineProperty(uDevicesList, "innerHTML", {
    get: () => devicesHtml,
    set: (html) => {
      devicesHtml = String(html);
      devButtons.length = 0;
      const re = /data-rm-user-dev="([^"]+)"/g;
      let m;
      while ((m = re.exec(devicesHtml)) !== null) {
        const btn = makeMockElement("", "BUTTON");
        btn.dataset.rmUserDev = m[1];
        devButtons.push(btn);
      }
    },
  });
  uDevicesList.querySelectorAll = (sel) => (sel === "[data-rm-user-dev]" ? devButtons : []);

  const storage = new Map();
  const localStorage = {
    getItem: (k) => (storage.has(k) ? storage.get(k) : null),
    setItem: (k, v) => storage.set(k, String(v)),
    removeItem: (k) => storage.delete(k),
  };

  const docListeners = new Map();
  const document = {
    getElementById: (id) => elements.get(id) || null,
    querySelectorAll: (sel) => {
      if (sel === "[data-dl]") return dlButtons;
      if (sel === "[data-auth-tab]") return [tabLogin, tabRegister];
      if (sel === "[data-open-auth]") return [];
      return [];
    },
    addEventListener: (type, fn) => {
      if (!docListeners.has(type)) docListeners.set(type, []);
      docListeners.get(type).push(fn);
    },
  };

  const windowObj = {
    location: { href: "http://127.0.0.1/" },
  };

  const timers = [];
  const ctx = vm.createContext({
    window: windowObj,
    document,
    localStorage,
    navigator: { userAgent },
    fetch: fetchHandler,
    setInterval: (fn, ms) => {
      const handle = { fn, ms, cleared: false };
      timers.push(handle);
      return handle;
    },
    clearInterval: (h) => {
      if (h) h.cleared = true;
    },
    Date,
    Math,
    JSON,
    String,
    Number,
    Object,
    Array,
    Error,
    encodeURIComponent,
    console,
  });

  vm.runInContext(readWeb("portal.js"), ctx, { filename: "website/portal.js" });

  return {
    elements,
    storage,
    windowObj,
    tabLogin,
    tabRegister,
    dlButtons,
    devButtons,
    cleanupTimers: () => timers.forEach((t) => (t.cleared = true)),
  };
}

test("website static files are completely rebranded to Mavie with zero Cineva strings", () => {
  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "cineva-mark.svg")), false);
  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "mavie-mark.svg")), true);
  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "icon.svg")), true);

  const mavieMark = readWeb("mavie-mark.svg");
  const iconSvg = readWeb("icon.svg");
  assert.match(mavieMark, /mavieGrad/);
  assert.doesNotMatch(mavieMark, /cineva/i);
  assert.match(iconSvg, /mavieBg/);
  assert.match(iconSvg, /mavieRing/);
  assert.doesNotMatch(iconSvg, /cineva/i);

  for (const file of ["index.html", "admin.html", "privacy.html", "terms.html", "styles.css", "admin.js", "robots.txt", "netlify.toml"]) {
    const content = readWeb(file);
    assert.equal(/cineva/i.test(content), false, `${file} must not contain residual Cineva strings`);
  }

  const portalSrc = readWeb("portal.js").replaceAll("https://github.com/tahadigital/cineva/", "");
  assert.equal(/cineva/i.test(portalSrc), false, "portal.js must not contain Cineva outside GitHub repo URL");

  const indexHtml = readWeb("index.html");
  assert.equal(indexHtml.includes('href="/admin"'), false);
  assert.match(readWeb("robots.txt"), /Disallow:\s*\/admin/);
  assert.match(readWeb("privacy.html"), /privacy@mavie\.app/);
  assert.match(readWeb("terms.html"), /legal@mavie\.app/);
});

test("website index.html and styles.css showcase all 4 platforms, Normal vs Pro, and responsive safeguards", () => {
  const html = readWeb("index.html");
  const css = readWeb("styles.css");

  for (const label of ["Windows", "Android", "macOS", "iOS"]) {
    assert.ok(html.includes(label), `Missing platform label ${label}`);
  }
  for (const artifact of ["Mavie-Setup.exe", "Mavie.exe", "Mavie-Android.apk", "Mavie-macOS.dmg", "Mavie-iOS.ipa"]) {
    assert.ok(html.includes(artifact), `Missing artifact ${artifact}`);
  }
  for (const target of ["windows-installer", "windows-portable", "android-apk", "macos", "ios"]) {
    assert.ok(html.includes(`data-dl="${target}"`), `Missing data-dl="${target}"`);
  }

  assert.match(html, /Normal/i);
  assert.match(html, /Mavie Pro/);
  assert.match(html, /MAVIE-XXXX-XXXX-XXXX/);
  assert.match(html, /verifyEmailPanel/);
  assert.match(html, /forgotPassPanel/);
  assert.match(html, /resetPassPanel/);
  assert.match(html, /uTrialCountdownBox/);

  assert.match(css, /overflow-x:\s*clip/);
  assert.match(css, /\.grid-4/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
});

test("portal.js detectPlatform selects Windows, Android, macOS, and iOS primary targets dynamically", async () => {
  const cases = [
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64)", /Windows/i, "Mavie-Setup.exe"],
    ["Mozilla/5.0 (Linux; Android 14; Pixel 8)", /Android/i, "Mavie-Android.apk"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5)", /macOS/i, "Mavie-macOS.dmg"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)", /iOS/i, "Mavie-iOS.ipa"],
  ];

  for (const [ua, btnPattern, expectedUrlFile] of cases) {
    const tracked = [];
    const h = runPortalHarness({
      userAgent: ua,
      fetchHandler: async (url, opts) => {
        if (url === "/api/v1/app-config") {
          return { ok: true, status: 200, json: async () => ({ versions: {}, downloads: {}, plans: {} }) };
        }
        if (url === "/api/v1/downloads/track") {
          tracked.push(JSON.parse(opts.body));
          return { ok: true, status: 200, json: async () => ({ ok: true }) };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      },
    });
    await new Promise((r) => setTimeout(r, 10));
    const primary = h.elements.get("primaryDownloadBtn");
    assert.match(primary.textContent, btnPattern);
    await primary.trigger("click");
    await new Promise((r) => setTimeout(r, 10));
    assert.ok(tracked.length === 1);
    assert.ok(h.windowObj.location.href.endsWith(expectedUrlFile), `Expected ${expectedUrlFile}, got ${h.windowObj.location.href}`);
    h.cleanupTimers();
  }
});

test("portal.js handles 201 verificationRequired, 403 EMAIL_NOT_VERIFIED, verify->trial countdown, device removal, and password reset", async () => {
  const calls = [];
  let devices = [
    { id: "dev-1", name: "MacBook Pro", platform: "macos" },
    { id: "dev-2", name: "Pixel 8", platform: "android" },
  ];
  let verified = false;

  const h = runPortalHarness({
    fetchHandler: async (url, opts = {}) => {
      calls.push({ url, method: opts.method || "GET", body: opts.body ? JSON.parse(opts.body) : null });
      if (url === "/api/v1/app-config") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            versions: {
              windowsLatest: "2.1.0",
              androidLatest: "2.1.0",
              macosLatest: "2.1.0",
              iosLatest: "2.1.0",
              releaseNotes: "Mavie 2.1.0 hazır.",
            },
            downloads: { "windows-installer": 4, "android-apk": 2, macos: 3, ios: 1 },
            plans: { normal: { maxDevices: 1 }, pro: { maxDevices: 5, trialDays: 3 } },
          }),
        };
      }
      if (url === "/api/v1/auth/register") {
        return {
          ok: true,
          status: 201,
          json: async () => ({
            ok: true,
            verificationRequired: true,
            emailVerified: false,
            user: { id: "u1", email: "ali@mavie.app", displayName: "Ali", emailVerified: false, plan: "normal" },
          }),
        };
      }
      if (url === "/api/v1/auth/login") {
        if (!verified) {
          return {
            ok: false,
            status: 403,
            json: async () => ({ error: "E-posta doğrulaması gerekli.", code: "EMAIL_NOT_VERIFIED", email: "ali@mavie.app" }),
          };
        }
        return { ok: true, status: 200, json: async () => ({ ok: true, token: "tok-verified-2", user: {} }) };
      }
      if (url === "/api/v1/auth/resend-verification") {
        return { ok: true, status: 200, json: async () => ({ ok: true, deliveryMode: "outbox" }) };
      }
      if (url === "/api/v1/auth/verify-email") {
        verified = true;
        return { ok: true, status: 200, json: async () => ({ ok: true, token: "tok-verified-1", trialActivated: true }) };
      }
      if (url === "/api/v1/me") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            user: {
              id: "u1",
              email: "ali@mavie.app",
              displayName: "Ali",
              emailVerified: true,
              plan: "pro",
              effectivePlan: "pro",
              isPro: true,
              trialActive: true,
              trialUsed: true,
              trialStartedAt: new Date(Date.now() - 3600_000).toISOString(),
              trialEndsAt: new Date(Date.now() + 70 * 3600_000).toISOString(),
              maxDevices: 5,
              features: { cloudSync: true, multiView: true, unlimitedProfiles: true, epgMatch: true, advancedTracks: true, maxDevices: 5 },
              devices,
            },
          }),
        };
      }
      if (url === "/api/v1/devices/dev-2" && opts.method === "DELETE") {
        devices = devices.filter((d) => d.id !== "dev-2");
        return { ok: true, status: 200, json: async () => ({ ok: true, devices }) };
      }
      if (url === "/api/v1/auth/forgot-password") {
        return { ok: true, status: 200, json: async () => ({ ok: true, message: "Sıfırlama kodu gönderildi." }) };
      }
      if (url === "/api/v1/auth/verify-reset-code") {
        return { ok: true, status: 200, json: async () => ({ ok: true, valid: true }) };
      }
      if (url === "/api/v1/auth/reset-password") {
        return { ok: true, status: 200, json: async () => ({ ok: true }) };
      }
      return { ok: false, status: 404, json: async () => ({ error: "Not found" }) };
    },
  });

  await new Promise((r) => setTimeout(r, 15));
  assert.equal(h.elements.get("dlMacCount").textContent, "3 kez indirildi");
  assert.equal(h.elements.get("dlIosCount").textContent, "1 kez indirildi");
  assert.equal(h.elements.get("planProDevices").textContent, "5");

  // Register -> 201 verificationRequired -> must NOT set token and must switch to verify view
  await h.tabRegister.trigger("click");
  h.elements.get("uName").value = "Ali";
  h.elements.get("uEmail").value = "ali@mavie.app";
  h.elements.get("uPass").value = "StrongPass123!";
  await h.elements.get("userAuthForm").trigger("submit");
  assert.equal(h.storage.get("mavie_user_token"), undefined);
  assert.equal(h.elements.get("accountLoggedOut").dataset.authView, "verify");

  // Unverified login -> 403 EMAIL_NOT_VERIFIED -> verify view
  await h.tabLogin.trigger("click");
  await h.elements.get("userAuthForm").trigger("submit");
  assert.equal(h.elements.get("accountLoggedOut").dataset.authView, "verify");

  // Resend verification & verify code -> logs in + shows 3-day Pro trial countdown
  await h.elements.get("resendVerifyBtn").trigger("click");
  assert.equal(h.elements.get("resendVerifyBtn").disabled, true);
  h.elements.get("verifyCodeInput").value = "123456";
  await h.elements.get("verifyEmailForm").trigger("submit");
  assert.equal(h.storage.get("mavie_user_token"), "tok-verified-1");
  assert.equal(h.elements.get("accountLoggedIn").hidden, false);
  assert.equal(h.elements.get("uTrialCountdownBox").hidden, false);
  assert.match(h.elements.get("uTrialCountdownBox").innerHTML, /3 Günlük Ücretsiz Mavie Pro Denemesi Aktif/);
  assert.equal(h.devButtons.length, 2);

  // Self-service device removal
  await h.devButtons[1].trigger("click");
  assert.equal(devices.length, 1);
  assert.equal(h.devButtons.length, 1);

  // Logout & Forgot -> Verify Reset Code -> Reset Password
  await h.elements.get("uLogoutBtn").trigger("click");
  assert.equal(h.storage.get("mavie_user_token"), undefined);
  await h.elements.get("openForgotBtn").trigger("click");
  assert.equal(h.elements.get("accountLoggedOut").dataset.authView, "forgot");
  h.elements.get("forgotEmailInput").value = "ali@mavie.app";
  await h.elements.get("forgotPassForm").trigger("submit");
  assert.equal(h.elements.get("accountLoggedOut").dataset.authView, "reset");

  h.elements.get("resetCodeInput").value = "654321";
  await h.elements.get("verifyResetCodeBtn").trigger("click");
  assert.match(h.elements.get("resetMsg").textContent, /Kod doğrulandı/);

  h.elements.get("resetNewPassInput").value = "NewStrongPass!99";
  await h.elements.get("resetPassForm").trigger("submit");
  assert.equal(h.elements.get("accountLoggedOut").dataset.authView, "login");
  assert.match(h.elements.get("uAuthOk").textContent, /Parolanız güncellendi/);

  h.cleanupTimers();
});

test("portal.js resets to login view on immediate post-verify logout, handles redeemForm, and blocks non-http(s) download URLs", async () => {
  const redeemBodies = [];
  let currentPlan = "normal";
  const h = runPortalHarness({
    fetchHandler: async (url, opts = {}) => {
      if (url === "/api/v1/app-config") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            versions: {
              windowsInstallerUrl: "javascript:alert(1)",
              iosUrl: "//evil.example/payload.ipa",
              macosUrl: "https://github.com/tahadigital/cineva/releases/latest/download/Mavie-macOS.dmg",
            },
            downloads: {},
            plans: {},
          }),
        };
      }
      if (url === "/api/v1/auth/register") {
        return {
          ok: true,
          status: 201,
          json: async () => ({
            ok: true,
            verificationRequired: true,
            emailVerified: false,
            user: { id: "u2", email: "veli@mavie.app", displayName: "Veli", emailVerified: false, plan: "normal" },
          }),
        };
      }
      if (url === "/api/v1/auth/verify-email") {
        return { ok: true, status: 200, json: async () => ({ ok: true, token: "tok-veli-1", trialActivated: true }) };
      }
      if (url === "/api/v1/licenses/redeem") {
        const body = JSON.parse(opts.body);
        redeemBodies.push(body);
        currentPlan = "pro";
        return {
          ok: true,
          status: 200,
          json: async () => ({
            ok: true,
            user: { id: "u2", email: "veli@mavie.app", plan: "pro", effectivePlan: "pro", isPro: true },
          }),
        };
      }
      if (url === "/api/v1/me") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            user: {
              id: "u2",
              email: "veli@mavie.app",
              displayName: "Veli",
              emailVerified: true,
              plan: currentPlan,
              effectivePlan: currentPlan,
              isPro: true,
              trialActive: currentPlan === "normal",
              trialStartedAt: new Date(Date.now() - 1000).toISOString(),
              trialEndsAt: new Date(Date.now() + 71 * 3600_000).toISOString(),
              maxDevices: 5,
              features: { cloudSync: true, multiView: true, unlimitedProfiles: true, epgMatch: true, advancedTracks: true, maxDevices: 5 },
              devices: [],
            },
          }),
        };
      }
      return { ok: false, status: 404, json: async () => ({ error: "Not found" }) };
    },
  });

  await new Promise((r) => setTimeout(r, 15));

  // Unsafe javascript: and protocol-relative // URLs from config must be ignored by startDownload
  await h.dlButtons[0].trigger("click");
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(h.windowObj.location.href, "http://127.0.0.1/");
  assert.equal(h.elements.get("downloadNotice").innerHTML, "");

  await h.dlButtons[4].trigger("click");
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(h.windowObj.location.href, "http://127.0.0.1/");
  assert.equal(h.elements.get("downloadNotice").innerHTML, "");

  // Register -> Verify -> Redeem -> Immediate Logout
  await h.tabRegister.trigger("click");
  h.elements.get("uName").value = "Veli";
  h.elements.get("uEmail").value = "veli@mavie.app";
  h.elements.get("uPass").value = "VeliStrong123!";
  await h.elements.get("userAuthForm").trigger("submit");
  assert.equal(h.elements.get("accountLoggedOut").dataset.authView, "verify");

  h.elements.get("verifyCodeInput").value = "112233";
  await h.elements.get("verifyEmailForm").trigger("submit");
  assert.equal(h.elements.get("accountLoggedIn").hidden, false);
  assert.equal(h.elements.get("uVerifyCelebration").hidden, false);

  h.elements.get("licenseCodeInput").value = "MAVIE-1111-2222-3333";
  await h.elements.get("redeemForm").trigger("submit");
  assert.deepEqual(redeemBodies, [{ code: "MAVIE-1111-2222-3333" }]);
  assert.match(h.elements.get("redeemMsg").textContent, /Mavie Pro/);
  assert.equal(h.elements.get("licenseCodeInput").value, "");

  await h.elements.get("uLogoutBtn").trigger("click");
  assert.equal(h.storage.get("mavie_user_token"), undefined);
  assert.equal(h.elements.get("accountLoggedOut").hidden, false);
  assert.equal(h.elements.get("accountLoggedOut").dataset.authView, "login");
  assert.equal(h.elements.get("userAuthForm").hidden, false);
  assert.equal(h.elements.get("verifyEmailPanel").hidden, true);
  assert.equal(h.elements.get("regNameWrap").hidden, true);
  assert.equal(h.elements.get("uVerifyCelebration").hidden, true);
  assert.equal(h.elements.get("redeemMsg").textContent, "");

  h.cleanupTimers();
});
