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
  const attrs = new Map();
  const dataset = {};
  const classSet = new Set();
  let focused = false;
  let scrolled = false;
  const el = {
    id,
    tagName,
    hidden: false,
    disabled: false,
    tabIndex: 0,
    textContent: "",
    innerHTML: "",
    href: "",
    dataset,
    style: {},
    classList: {
      toggle(name, force) {
        if (force === undefined) {
          if (classSet.has(name)) {
            classSet.delete(name);
            return false;
          }
          classSet.add(name);
          return true;
        }
        if (force) classSet.add(name);
        else classSet.delete(name);
        return Boolean(force);
      },
      contains(name) {
        return classSet.has(name);
      },
    },
    get className() {
      return Array.from(classSet).join(" ");
    },
    set className(val) {
      classSet.clear();
      for (const c of String(val || "").split(/\s+/).filter(Boolean)) classSet.add(c);
    },
    setAttribute(k, v) {
      attrs.set(k, String(v));
    },
    getAttribute(k) {
      return attrs.has(k) ? attrs.get(k) : null;
    },
    focus() {
      focused = true;
    },
    get _focused() {
      return focused;
    },
    scrollIntoView() {
      scrolled = true;
    },
    get _scrolled() {
      return scrolled;
    },
    querySelectorAll() {
      return [];
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
  };
  return el;
}

const GUIDE_KEYS = ["windows", "macos", "ios", "android", "samsung-tv", "lg-tv", "distribution"];
const ALL_DL_TARGETS = [
  ["windows-installer", "Mavie-Setup.exe"],
  ["windows-portable", "Mavie.exe"],
  ["android-apk", "Mavie-Android.apk"],
  ["android-tv", "Mavie-Android.apk"],
  ["macos", "Mavie-macOS.dmg"],
  ["ios", "Mavie-iOS.ipa"],
  ["tizen-wgt", "Mavie-Tizen.wgt"],
  ["webos-ipk", "Mavie-webOS.ipk"],
];

function runPortalHarness({
  userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
  hash = "",
} = {}) {
  const elements = new Map();
  const ensureEl = (id, tag = "DIV") => {
    if (!elements.has(id)) elements.set(id, makeMockElement(id, tag));
    return elements.get(id);
  };

  for (const id of [
    "primaryDownloadBtn",
    "secondaryDownloadBtn",
    "platformHint",
    "downloadNotice",
    "winVerBadge",
    "androidVerBadge",
    "macosVerBadge",
    "iosVerBadge",
    "releaseNotesText",
    "guides",
    "copyLiveStatus",
  ]) {
    ensureEl(id);
  }

  const dlButtons = ALL_DL_TARGETS.map(([target]) => {
    const b = makeMockElement("", "BUTTON");
    b.dataset.dl = target;
    return b;
  });

  const releaseLinks = [makeMockElement("", "A")];

  const guideTabs = GUIDE_KEYS.map((key, idx) => {
    const tab = makeMockElement(`tab-${key}`, "BUTTON");
    tab.dataset.guide = key;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", idx === 0 ? "true" : "false");
    return tab;
  });

  const guidePanels = GUIDE_KEYS.map((key, idx) => {
    const panel = makeMockElement(`panel-${key}`, "DIV");
    panel.dataset.guidePanel = key;
    panel.hidden = idx !== 0;
    return panel;
  });

  const guideJumpLinks = ["auto", "windows", "macos", "ios", "android", "samsung-tv", "lg-tv"].map((key) => {
    const a = makeMockElement("", "A");
    a.dataset.guideTab = key;
    return a;
  });

  const copyButtons = [
    { text: "Mavie.exe --web", label: "Kopyala" },
    { text: "xattr -cr /Applications/Mavie.app", label: "Kopyala" },
    { text: "./tv/tizen/install-tizen.sh <TV-IP>", label: "Betik" },
    { text: "ares-install -d tv Mavie-webOS.ipk", label: "ares-install" },
    { text: "http://<bilgisayar-IP>:8844/tv", label: "TV Modu" },
  ].map(({ text, label }) => {
    const b = makeMockElement("", "BUTTON");
    b.dataset.copy = text;
    b.textContent = label;
    return b;
  });

  const document = {
    getElementById: (id) => elements.get(id) || null,
    querySelectorAll: (sel) => {
      if (sel === "[data-dl]") return dlButtons;
      if (sel === "[data-releases]") return releaseLinks;
      if (sel === '[role="tab"][data-guide]') return guideTabs;
      if (sel === '[role="tabpanel"][data-guide-panel]') return guidePanels;
      if (sel === "[data-guide-tab]") return guideJumpLinks;
      if (sel === "[data-copy]") return copyButtons;
      return [];
    },
  };

  const copied = [];
  const hashUpdates = [];
  const windowObj = {
    location: { href: "http://127.0.0.1/", hash },
    history: {
      replaceState(_state, _title, url) {
        hashUpdates.push(url);
        windowObj.location.hash = url;
      },
    },
    addEventListener() {},
  };

  const ctx = vm.createContext({
    window: windowObj,
    document,
    navigator: {
      userAgent,
      clipboard: {
        async writeText(val) {
          copied.push(val);
        },
      },
    },
    setTimeout: (fn) => {
      void fn;
      return 1;
    },
    clearTimeout: () => {},
    String,
    Object,
    Array,
    Number,
    Boolean,
    console,
  });

  vm.runInContext(readWeb("portal.js"), ctx, { filename: "website/portal.js" });

  return {
    elements,
    windowObj,
    dlButtons,
    releaseLinks,
    guideTabs,
    guidePanels,
    guideJumpLinks,
    copyButtons,
    copied,
    hashUpdates,
  };
}

test("website static files are completely Mavie-branded, free, and contain zero admin/account artifacts", () => {
  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "cineva-mark.svg")), false);
  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "admin.html")), false);
  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "admin.js")), false);
  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "netlify", "functions", "api.mts")), false);
  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "netlify", "functions", "cloud-core.mjs")), false);
  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "netlify", "edge-functions", "admin-gate.ts")), false);

  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "mavie-mark.svg")), true);
  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "icon.svg")), true);
  assert.equal(fs.existsSync(path.join(WEBSITE_DIR, "404.html")), true);

  const mavieMark = readWeb("mavie-mark.svg");
  const iconSvg = readWeb("icon.svg");
  for (const svg of [mavieMark, iconSvg]) {
    assert.match(svg, /<svg\b/i);
    assert.match(svg, /#7c3aed/i);
    assert.match(svg, /#3b82f6/i);
    assert.match(svg, /#06b6d4/i);
    assert.doesNotMatch(svg, /cineva/i);
  }

  for (const file of ["index.html", "404.html", "privacy.html", "terms.html", "styles.css", "robots.txt", "netlify.toml"]) {
    const content = readWeb(file);
    assert.equal(/cineva/i.test(content), false, `${file} must not contain residual Cineva strings`);
  }

  const portalSrc = readWeb("portal.js").replaceAll("https://github.com/tahadigital/cineva/", "");
  assert.equal(/cineva/i.test(portalSrc), false, "portal.js must not contain Cineva outside GitHub repo URL");

  const indexHtml = readWeb("index.html");
  assert.equal(indexHtml.includes('href="/admin"'), false);
  assert.equal(indexHtml.includes("accountModal"), false);
  assert.equal(indexHtml.includes("Mavie Pro"), false);
  assert.equal(indexHtml.includes("MAVIE-XXXX-XXXX-XXXX"), false);
  assert.match(readWeb("robots.txt"), /Disallow:\s*\/admin/);
  assert.match(readWeb("privacy.html"), /privacy@mavie\.app/);
  assert.match(readWeb("terms.html"), /legal@mavie\.app/);
});

test("website index.html and styles.css showcase all 4 platforms plus Smart TV downloads, Windows native+web modes, and responsive safeguards", () => {
  const html = readWeb("index.html");
  const css = readWeb("styles.css");

  for (const label of ["Windows", "Android", "macOS", "iOS", "Samsung Smart TV", "LG Smart TV", "Android TV / Fire TV"]) {
    assert.ok(html.includes(label), `Missing platform label ${label}`);
  }
  for (const artifact of [
    "Mavie-Setup.exe",
    "Mavie.exe",
    "Mavie-Android.apk",
    "Mavie-macOS.dmg",
    "Mavie-iOS.ipa",
    "Mavie-Tizen.wgt",
    "Mavie-webOS.ipk",
  ]) {
    assert.ok(html.includes(artifact), `Missing artifact ${artifact}`);
  }
  for (const [target] of ALL_DL_TARGETS) {
    assert.ok(html.includes(`data-dl="${target}"`), `Missing data-dl="${target}"`);
  }

  // Windows native desktop app window + Web Surumu messaging
  assert.match(html, /yerel Windows uygulama penceresinde/i);
  assert.ok(html.includes("Mavie (Web Sürümü)"), "Missing Mavie (Web Sürümü) shortcut reference");
  assert.ok(html.includes("Mavie.exe --web"), "Missing Mavie.exe --web command");
  assert.ok(html.includes("Mavie.exe --serve"), "Missing Mavie.exe --serve command");

  // Smart TV downloads block
  assert.match(html, /id="tv-downloads"/);
  assert.ok(html.includes("http://&lt;bilgisayar-IP&gt;:8844/tv"), "Missing /tv URL in Smart TV section");

  assert.match(html, /%100 ÜCRETSİZ/i);
  assert.match(html, /Tamamen Ücretsiz/i);
  assert.match(html, /id="free-forever"/);
  assert.match(css, /overflow-x:\s*clip/);
  assert.match(css, /\.grid-4/);
  assert.match(css, /\.tv-downloads-block/);
  assert.match(css, /\.guide-shell/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
});

test("website Kurulum and Yayin Kilavuzu (#guides) covers all 7 tabs including Samsung Tizen, LG webOS, Android TV, and copyable snippets", () => {
  const html = readWeb("index.html");

  // Top nav + section + ARIA tablist
  assert.match(html, /<a href="#guides">Kurulum Kılavuzu<\/a>/);
  assert.match(html, /<section id="guides"/);
  assert.match(html, /role="tablist"/);

  for (const key of GUIDE_KEYS) {
    assert.ok(html.includes(`data-guide="${key}"`), `Missing guide tab for ${key}`);
    assert.ok(html.includes(`data-guide-panel="${key}"`), `Missing guide panel for ${key}`);
    assert.ok(html.includes(`aria-controls="panel-${key}"`), `Missing aria-controls for ${key}`);
    assert.ok(html.includes(`aria-labelledby="tab-${key}"`), `Missing aria-labelledby for ${key}`);
  }

  const requiredTokens = [
    // Windows
    "SmartScreen",
    "Ek bilgi",
    "Yine de çalıştır",
    "Mavie (Web Sürümü)",
    "Mavie.exe --web",
    "Mavie.exe --serve",
    // macOS
    "Uygulamalar (Applications)",
    "Gatekeeper",
    "Yine de Aç",
    "xattr -cr /Applications/Mavie.app",
    "Apple Silicon",
    // iOS
    "AltStore",
    "SideStore",
    "Sideloadly",
    "VPN ve Aygıt Yönetimi",
    "Geliştirici Modu",
    "7 gün",
    // Android & Android TV / Fire TV
    "Bilinmeyen",
    "Android TV",
    "Fire TV",
    "Leanback",
    "D-Pad",
    "Downloader",
    "Send Files to TV",
    // Samsung TV (Tizen / TU8500)
    "TU8500",
    "Tizen 5.5",
    "12345",
    "Host PC IP",
    "Mavie-Tizen.wgt",
    "./tv/tizen/install-tizen.sh",
    "tizen install -n Mavie-Tizen.wgt",
    "TizenBrew",
    "AVPlay",
    // LG TV (webOS) & Other Smart TVs
    "LG Content Store",
    "webOS Dev Manager",
    "ares-install -d tv Mavie-webOS.ipk",
    "./tv/webos/install-webos.sh",
    "1000 saat",
    "Hisense",
    "Vestel",
    ":8844/tv",
    "PWA",
    // Distribution channels
    "GitHub Releases",
    "Google Play Store",
    "Mavie-Android.aab",
    "TestFlight",
    "App Store",
    "Microsoft Store",
    "Winget",
    "Seller Office",
    "LG Seller Lounge",
  ];

  for (const tok of requiredTokens) {
    assert.ok(html.includes(tok), `Missing required guide instruction token: ${tok}`);
  }

  // Copyable command buttons
  for (const cmd of [
    "Mavie.exe --web",
    "Mavie.exe --serve",
    "xattr -cr /Applications/Mavie.app",
    "./tv/tizen/install-tizen.sh <TV-IP>",
    "tizen install -n Mavie-Tizen.wgt -t <TV-AD>",
    "ares-install -d tv Mavie-webOS.ipk",
    "./tv/webos/install-webos.sh <TV-IP>",
    "http://<bilgisayar-IP>:8844/tv",
  ]) {
    assert.ok(html.includes(`data-copy="${cmd}"`), `Missing copyable command button for ${cmd}`);
  }

  // CSP compliance: zero inline onclick handlers or inline script blocks
  assert.doesNotMatch(html, /\bonclick\s*=/i);
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>/i);
});

test("portal.js detectPlatform selects Windows, Android, macOS, iOS, Tizen, and webOS release downloads and defaults matching guide tab", async () => {
  const cases = [
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64)", /Windows/i, "Mavie-Setup.exe", "windows"],
    ["Mozilla/5.0 (Linux; Android 14; Pixel 8)", /Android/i, "Mavie-Android.apk", "android"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5)", /macOS/i, "Mavie-macOS.dmg", "macos"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)", /iOS/i, "Mavie-iOS.ipa", "ios"],
    ["Mozilla/5.0 (SMART-TV; LINUX; Tizen 5.5) AppleWebKit/537.36", /Samsung TV/i, "Mavie-Tizen.wgt", "samsung-tv"],
    ["Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36", /LG TV/i, "Mavie-webOS.ipk", "lg-tv"],
  ];

  for (const [ua, btnPattern, expectedUrlFile, expectedGuide] of cases) {
    const h = runPortalHarness({ userAgent: ua });
    const primary = h.elements.get("primaryDownloadBtn");
    assert.match(primary.textContent, btnPattern);

    const activeTab = h.guideTabs.find((t) => t.getAttribute("aria-selected") === "true");
    assert.equal(activeTab?.dataset.guide, expectedGuide, `Default active guide tab for ${ua} should be ${expectedGuide}`);
    const visiblePanels = h.guidePanels.filter((p) => !p.hidden);
    assert.equal(visiblePanels.length, 1);
    assert.equal(visiblePanels[0].dataset.guidePanel, expectedGuide);

    await primary.trigger("click");
    assert.ok(
      h.windowObj.location.href.endsWith(expectedUrlFile),
      `Expected ${expectedUrlFile}, got ${h.windowObj.location.href}`,
    );
    assert.equal(h.elements.get("downloadNotice").hidden, false);
    assert.ok(h.elements.get("downloadNotice").innerHTML.includes(expectedUrlFile));
  }
});

test("portal.js triggers direct download for every platform and Smart TV card button with contextual install notice", async () => {
  const h = runPortalHarness();
  for (let i = 0; i < ALL_DL_TARGETS.length; i++) {
    const [target, expectedFile] = ALL_DL_TARGETS[i];
    await h.dlButtons[i].trigger("click");
    assert.ok(
      h.windowObj.location.href.endsWith(expectedFile),
      `Button ${target} should download ${expectedFile}, got ${h.windowObj.location.href}`,
    );
    const noticeHtml = h.elements.get("downloadNotice").innerHTML;
    assert.ok(noticeHtml.includes(expectedFile), `Notice for ${target} should mention ${expectedFile}`);
    if (target === "tizen-wgt") {
      assert.ok(noticeHtml.includes("12345"), "Samsung Tizen download notice should mention 12345 Developer Mode");
      assert.equal(h.guideTabs.find((t) => t.dataset.guide === "samsung-tv").getAttribute("aria-selected"), "true");
    }
    if (target === "webos-ipk") {
      assert.ok(noticeHtml.includes("ares-install"), "LG webOS download notice should mention ares-install");
      assert.equal(h.guideTabs.find((t) => t.dataset.guide === "lg-tv").getAttribute("aria-selected"), "true");
    }
    if (target === "android-tv") {
      assert.ok(noticeHtml.includes("Leanback"), "Android TV download notice should mention Leanback");
      assert.equal(h.guideTabs.find((t) => t.dataset.guide === "android").getAttribute("aria-selected"), "true");
    }
  }
});

test("portal.js supports interactive ARIA guide tabs (click, keyboard, hash deep-link & alias, card jump) and clipboard copy", async () => {
  // Deep link hash overrides detected platform
  const hHash = runPortalHarness({
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    hash: "#guide-samsung-tv",
  });
  assert.equal(
    hHash.guideTabs.find((t) => t.getAttribute("aria-selected") === "true")?.dataset.guide,
    "samsung-tv",
  );

  // Legacy #guide-web-tv alias resolves cleanly to lg-tv
  const hAlias = runPortalHarness({
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    hash: "#guide-web-tv",
  });
  assert.equal(
    hAlias.guideTabs.find((t) => t.getAttribute("aria-selected") === "true")?.dataset.guide,
    "lg-tv",
  );

  // Click & keyboard navigation across all 7 tabs
  const h = runPortalHarness({ userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" });
  const winTab = h.guideTabs[0];
  const macTab = h.guideTabs[1];
  const distTab = h.guideTabs[6];

  await winTab.trigger("keydown", { key: "ArrowRight" });
  assert.equal(macTab.getAttribute("aria-selected"), "true");
  assert.equal(macTab._focused, true);
  assert.equal(h.guidePanels[1].hidden, false);
  assert.equal(h.guidePanels[0].hidden, true);

  await macTab.trigger("keydown", { key: "End" });
  assert.equal(distTab.getAttribute("aria-selected"), "true");
  assert.equal(h.guidePanels[6].hidden, false);

  await distTab.trigger("keydown", { key: "Home" });
  assert.equal(winTab.getAttribute("aria-selected"), "true");

  // Jump link from Samsung TV card activates samsung-tv tab and scrolls to #guides
  const tizenJump = h.guideJumpLinks.find((a) => a.dataset.guideTab === "samsung-tv");
  await tizenJump.trigger("click");
  assert.equal(h.guideTabs.find((t) => t.dataset.guide === "samsung-tv").getAttribute("aria-selected"), "true");
  assert.equal(h.elements.get("guides")._scrolled, true);

  // Copy-to-clipboard buttons copy TV & desktop commands cleanly
  const tizenCopy = h.copyButtons[2];
  await tizenCopy.trigger("click");
  assert.deepEqual(h.copied, ["./tv/tizen/install-tizen.sh <TV-IP>"]);
  assert.match(tizenCopy.textContent, /Kopyalandı/);
  assert.equal(tizenCopy.classList.contains("is-copied"), true);
  assert.match(h.elements.get("copyLiveStatus").textContent, /install-tizen\.sh/);
});

test("L1: website includes skip-link accessibility, main tabindex=-1, zero legacy colors, and no @netlify/database dependency", () => {
  const html = readWeb("index.html");
  const css = readWeb("styles.css");
  const pkg = JSON.parse(readWeb("package.json"));

  assert.match(html, /class="skip-link"\s+href="#top"/);
  assert.match(html, /<main\s+id="top"\s+tabindex="-1">/);
  assert.match(css, /\.skip-link\s*\{/);
  assert.match(css, /\.skip-link:focus\s*\{/);
  assert.doesNotMatch(css, /#e50914|#ff4b45|#ed1520/i);
  assert.equal(pkg.dependencies?.["@netlify/database"], undefined);
});
