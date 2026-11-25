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
  const dataset = {};
  const el = {
    id,
    tagName,
    hidden: false,
    disabled: false,
    textContent: "",
    innerHTML: "",
    className: "",
    href: "",
    dataset,
    style: {},
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

function runPortalHarness({ userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" } = {}) {
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
  ]) {
    ensureEl(id);
  }

  const dlButtons = ["windows-installer", "windows-portable", "android-apk", "macos", "ios"].map((t) => {
    const b = makeMockElement("", "BUTTON");
    b.dataset.dl = t;
    return b;
  });

  const document = {
    getElementById: (id) => elements.get(id) || null,
    querySelectorAll: (sel) => (sel === "[data-dl]" ? dlButtons : []),
  };

  const windowObj = {
    location: { href: "http://127.0.0.1/" },
  };

  const ctx = vm.createContext({
    window: windowObj,
    document,
    navigator: { userAgent },
    String,
    Object,
    Array,
    console,
  });

  vm.runInContext(readWeb("portal.js"), ctx, { filename: "website/portal.js" });

  return {
    elements,
    windowObj,
    dlButtons,
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
  assert.match(mavieMark, /mavieGrad/);
  assert.doesNotMatch(mavieMark, /cineva/i);
  assert.match(iconSvg, /mavieBg/);
  assert.match(iconSvg, /mavieRing/);
  assert.doesNotMatch(iconSvg, /cineva/i);

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

test("website index.html and styles.css showcase all 4 platforms, free unlimited access, and responsive safeguards", () => {
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

  assert.match(html, /%100 ÜCRETSİZ/i);
  assert.match(html, /Tamamen Ücretsiz/i);
  assert.match(html, /id="free-forever"/);
  assert.match(css, /overflow-x:\s*clip/);
  assert.match(css, /\.grid-4/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
});

test("portal.js detectPlatform selects Windows, Android, macOS, and iOS direct release downloads cleanly", async () => {
  const cases = [
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64)", /Windows/i, "Mavie-Setup.exe"],
    ["Mozilla/5.0 (Linux; Android 14; Pixel 8)", /Android/i, "Mavie-Android.apk"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5)", /macOS/i, "Mavie-macOS.dmg"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)", /iOS/i, "Mavie-iOS.ipa"],
  ];

  for (const [ua, btnPattern, expectedUrlFile] of cases) {
    const h = runPortalHarness({ userAgent: ua });
    const primary = h.elements.get("primaryDownloadBtn");
    assert.match(primary.textContent, btnPattern);
    await primary.trigger("click");
    assert.ok(
      h.windowObj.location.href.endsWith(expectedUrlFile),
      `Expected ${expectedUrlFile}, got ${h.windowObj.location.href}`,
    );
    assert.equal(h.elements.get("downloadNotice").hidden, false);
    assert.ok(h.elements.get("downloadNotice").innerHTML.includes(expectedUrlFile));
  }
});

test("portal.js triggers direct download for every platform card button without any cloud API", async () => {
  const h = runPortalHarness();
  const expectedFiles = [
    "Mavie-Setup.exe",
    "Mavie.exe",
    "Mavie-Android.apk",
    "Mavie-macOS.dmg",
    "Mavie-iOS.ipa",
  ];
  for (let i = 0; i < expectedFiles.length; i++) {
    await h.dlButtons[i].trigger("click");
    assert.ok(
      h.windowObj.location.href.endsWith(expectedFiles[i]),
      `Button ${i} should download ${expectedFiles[i]}, got ${h.windowObj.location.href}`,
    );
  }
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
