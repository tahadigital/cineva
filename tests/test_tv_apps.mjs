import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import zlib from 'node:zlib';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const TV_SRC = path.join(ROOT, 'tv', 'src');
const TIZEN_DIR = path.join(ROOT, 'tv', 'tizen');
const WEBOS_DIR = path.join(ROOT, 'tv', 'webos');

const ALL_TV_JS = [
  path.join(TV_SRC, 'qr.js'),
  path.join(TV_SRC, 'm3u-tv.js'),
  path.join(TV_SRC, 'spatial.js'),
  path.join(TV_SRC, 'player.js'),
  path.join(TV_SRC, 'app.js'),
  path.join(TIZEN_DIR, 'tizen-bridge.js'),
  path.join(WEBOS_DIR, 'webos-bridge.js'),
];

function stripCommentsAndStrings(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/[^\n]*/g, '')
    .replace(/'(?:\\.|[^'\\])*'/g, "''")
    .replace(/"(?:\\.|[^"\\])*"/g, '""');
}

function listZipEntries(buf) {
  // Parse ZIP End of Central Directory & Central Directory entries in pure Node
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65558); i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  assert.ok(eocd >= 0, 'ZIP End of Central Directory signature not found');
  const totalEntries = buf.readUInt16LE(eocd + 10);
  const cdOffset = buf.readUInt32LE(eocd + 16);
  const entries = new Map();

  let off = cdOffset;
  for (let i = 0; i < totalEntries; i++) {
    assert.equal(buf.readUInt32LE(off), 0x02014b50, 'Invalid ZIP central directory header');
    const method = buf.readUInt16LE(off + 10);
    const compSize = buf.readUInt32LE(off + 20);
    const nameLen = buf.readUInt16LE(off + 28);
    const extraLen = buf.readUInt16LE(off + 30);
    const commentLen = buf.readUInt16LE(off + 32);
    const localOffset = buf.readUInt32LE(off + 42);
    const name = buf.subarray(off + 46, off + 46 + nameLen).toString('utf8');

    assert.equal(buf.readUInt32LE(localOffset), 0x04034b50, `Invalid local header for ${name}`);
    const localNameLen = buf.readUInt16LE(localOffset + 26);
    const localExtraLen = buf.readUInt16LE(localOffset + 28);
    const dataStart = localOffset + 30 + localNameLen + localExtraLen;
    const compressed = buf.subarray(dataStart, dataStart + compSize);
    const content = method === 0 ? compressed : zlib.inflateRawSync(compressed);
    entries.set(name, content);

    off += 46 + nameLen + extraLen + commentLen;
  }
  return entries;
}

function parseArArchive(buf) {
  assert.equal(buf.subarray(0, 8).toString('ascii'), '!<arch>\n', 'Missing Debian/OPKG ar magic');
  const members = new Map();
  let off = 8;
  while (off + 60 <= buf.length) {
    const hdr = buf.subarray(off, off + 60).toString('ascii');
    assert.equal(hdr.slice(58, 60), '`\n', `Invalid ar member trailer at offset ${off}`);
    const name = hdr.slice(0, 16).trim().replace(/\/$/, '');
    const size = parseInt(hdr.slice(48, 58).trim(), 10);
    assert.ok(Number.isFinite(size) && size >= 0, `Invalid ar size for ${name}`);
    off += 60;
    members.set(name, buf.subarray(off, off + size));
    off += size + (size % 2);
  }
  return members;
}

function parseTarBuffer(tarBuf) {
  const files = new Map();
  let off = 0;
  while (off + 512 <= tarBuf.length) {
    const header = tarBuf.subarray(off, off + 512);
    if (header.every((b) => b === 0)) break;
    const rawName = header.subarray(0, 100).toString('utf8').replace(/\0.*$/, '');
    const prefix = header.subarray(345, 500).toString('utf8').replace(/\0.*$/, '');
    const fullName = (prefix ? `${prefix}/${rawName}` : rawName).replace(/^\.\//, '');
    const sizeOctal = header.subarray(124, 136).toString('ascii').replace(/\0.*$/, '').trim();
    const size = parseInt(sizeOctal || '0', 8);
    off += 512;
    files.set(fullName, tarBuf.subarray(off, off + size));
    off += Math.ceil(size / 512) * 512;
  }
  return files;
}

test('TV JavaScript files strictly comply with Chromium M69 (Tizen 5.5) & webOS 4.0 syntax', () => {
  const forbidden = [
    ['optional chaining (?.)', /\?\.(?!\d)/],
    ['nullish coalescing (??)', /\?\?(?!=)/],
    ['Object.fromEntries', /\bObject\.fromEntries\s*\(/],
    ['Array.prototype.flat/flatMap', /\.(?:flat|flatMap)\s*\(/],
    ['unguarded globalThis', /\bglobalThis\b/],
    ['ES module import/export', /^\s*(?:import|export)\s+/m],
    ['async/await (webOS 4.0 M53 safety)', /\b(?:async\s+function|await\s+)/],
  ];

  for (const file of ALL_TV_JS) {
    const raw = fs.readFileSync(file, 'utf8');
    // Must parse cleanly in V8
    assert.doesNotThrow(() => new vm.Script(raw, { filename: file }), `Syntax error in ${file}`);
    const code = stripCommentsAndStrings(raw);
    for (const [label, regex] of forbidden) {
      assert.equal(regex.test(code), false, `${path.relative(ROOT, file)} contains forbidden M69/webOS syntax: ${label}`);
    }
  }
});

test('tv/src/tv.css strictly complies with Chromium M69 CSS rules', () => {
  const css = fs.readFileSync(path.join(TV_SRC, 'tv.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
  const forbiddenCss = [
    ['flexbox/grid gap', /\b(?:row-|column-)?gap\s*:/],
    ['aspect-ratio', /\baspect-ratio\s*:/],
    ['inset shorthand', /\binset(?:-block|-inline)?\s*:/],
    ['clamp() math', /\bclamp\s*\(/],
    [':has() selector', /:has\s*\(/],
    ['dvh/svh/lvh units', /\d+(?:dvh|svh|lvh)\b/],
  ];
  for (const [label, regex] of forbiddenCss) {
    assert.equal(regex.test(css), false, `tv/src/tv.css contains forbidden M69 CSS feature: ${label}`);
  }
  assert.ok(css.includes('.tv-focused'), 'Missing high-contrast .tv-focused rule');
  assert.ok(css.includes('padding: 48px'), 'Missing 1920x1080 overscan-safe 48px padding');
});

test('tv/src/index.html & app.js have zero inline JS handlers (strict CSP)', () => {
  const html = fs.readFileSync(path.join(TV_SRC, 'index.html'), 'utf8');
  const appJs = fs.readFileSync(path.join(TV_SRC, 'app.js'), 'utf8');
  assert.equal(/\bon(?:click|error|load|change|input)\s*=/i.test(html), false, 'index.html has inline event handler');
  assert.equal(/\bon(?:click|error|load|change|input)\s*=/i.test(appJs), false, 'app.js renders inline event handler');
  assert.equal(/type=["']module["']/i.test(html), false, 'index.html must use classic defer scripts for file://');
});

test('Tizen config.xml & tizen-bridge.js meet Samsung TU8500 & Seller Office QA rules', () => {
  const cfg = fs.readFileSync(path.join(TIZEN_DIR, 'config.xml'), 'utf8');
  assert.ok(cfg.includes('required_version="5.5"'), 'config.xml must target Tizen 5.5');
  assert.ok(cfg.includes('<tizen:profile name="tv-samsung"/>'), 'config.xml must specify tv-samsung profile');
  assert.ok(cfg.includes('<access origin="*" subdomains="true"/>'), 'config.xml must permit standalone network access');
  assert.ok(cfg.includes('http://tizen.org/privilege/internet'));
  assert.ok(cfg.includes('http://tizen.org/privilege/tv.inputdevice'));

  const bridge = fs.readFileSync(path.join(TIZEN_DIR, 'tizen-bridge.js'), 'utf8');
  assert.ok(bridge.includes("'MediaPlayPause'"), 'tizen-bridge.js must register MediaPlayPause');
  assert.equal(/['"]Exit['"]/.test(stripCommentsAndStrings(bridge)), false, "tizen-bridge.js must NOT register 'Exit' (10182)");
});

test('MavieQR generates valid scannable SVG QR codes for LAN & TV URLs', () => {
  const qr = require(path.join(TV_SRC, 'qr.js'));
  const matrix = qr.encodeMatrix('http://192.168.1.35:8844/tv');
  assert.ok(matrix.length >= 25 && matrix.length % 4 === 1, 'QR matrix size must match 4*V + 17');
  const svg = qr.toSvg('http://192.168.1.35:8844/tv');
  assert.ok(svg.startsWith('<svg ') && svg.endsWith('</svg>'));
  assert.ok(svg.includes('<rect') && svg.includes('<path'));
});

test('MavieM3U parses M3U playlists and ships open-license Demo Catalog', () => {
  const m3u = require(path.join(TV_SRC, 'm3u-tv.js'));
  const demo = m3u.getDemoCatalog();
  assert.ok(demo.length >= 4, 'Demo catalog must contain at least 4 open films');

  const sample = [
    '#EXTM3U url-tvg="https://example.org/epg.xml"',
    '#EXTINF:-1 tvg-id="trt1" tvg-logo="https://img/trt.png" group-title="Ulusal",TRT 1 HD',
    'https://stream.example.org/trt1/index.m3u8',
    '#EXTINF:-1 group-title="Filmler",Ornek Film, 2024',
    'https://stream.example.org/movie/101.mp4',
    '#EXTINF:-1 group-title="Diziler",Ornek Dizi S01E01',
    'https://stream.example.org/series/202.mp4',
  ].join('\n');
  const parsed = m3u.parseM3U(sample);
  assert.equal(parsed.epgUrl, 'https://example.org/epg.xml');
  assert.equal(parsed.items.length, 3);
  assert.equal(parsed.items[0].kind, 'live');
  assert.equal(parsed.items[1].kind, 'vod');
  assert.equal(parsed.items[1].name, 'Ornek Film, 2024');
  assert.equal(parsed.items[2].kind, 'series');
});

test('MavieSpatial handles 2D D-Pad scoring and Tizen/webOS Back stack + Exit flow', () => {
  const spatial = require(path.join(TV_SRC, 'spatial.js'));
  const origin = { left: 100, top: 100, width: 200, height: 120, right: 300, bottom: 220 };
  const rightCard = { el: 'rightCard', rect: { left: 340, top: 100, width: 200, height: 120, right: 540, bottom: 220 } };
  const downCard = { el: 'downCard', rect: { left: 100, top: 260, width: 200, height: 120, right: 300, bottom: 380 } };
  const farDiag = { el: 'farDiag', rect: { left: 600, top: 450, width: 200, height: 120, right: 800, bottom: 570 } };

  assert.equal(spatial.findBestCandidate(origin, [rightCard, downCard, farDiag], 'right'), 'rightCard');
  assert.equal(spatial.findBestCandidate(origin, [rightCard, downCard, farDiag], 'down'), 'downCard');
  assert.equal(spatial.isBackKey(10009, ''), true, 'Tizen Back 10009');
  assert.equal(spatial.isBackKey(461, ''), true, 'LG webOS Back 461');
  assert.equal(spatial.isBackKey(27, 'Escape'), true, 'Escape 27');

  let modalClosed = false;
  let rootExitPrompted = false;
  const stack = spatial.createBackStack(() => { rootExitPrompted = true; });
  stack.push(() => { modalClosed = true; return true; });
  assert.equal(stack.triggerBack(), 'popped');
  assert.equal(modalClosed, true);
  assert.equal(rootExitPrompted, false);
  assert.equal(stack.triggerBack(), 'root');
  assert.equal(rootExitPrompted, true);
});

test('build_tv_packages.py builds valid Mavie-Tizen.wgt (ZIP) and Mavie-webOS.ipk (ar+tar.gz)', () => {
  const tmpOut = fs.mkdtempSync(path.join(os.tmpdir(), 'mavie-tv-pkg-'));
  try {
    execFileSync('python3', [path.join(ROOT, 'tv', 'build_tv_packages.py'), '--out-dir', tmpOut], {
      cwd: ROOT,
      stdio: 'pipe',
    });

    const wgtPath = path.join(tmpOut, 'Mavie-Tizen.wgt');
    const ipkPath = path.join(tmpOut, 'Mavie-webOS.ipk');
    assert.ok(fs.existsSync(wgtPath) && fs.statSync(wgtPath).size > 50_000);
    assert.ok(fs.existsSync(ipkPath) && fs.statSync(ipkPath).size > 50_000);

    // 1) Validate Samsung Tizen .wgt ZIP contents
    const wgtEntries = listZipEntries(fs.readFileSync(wgtPath));
    for (const required of [
      'config.xml', 'icon.png', 'index.html', 'tizen-bridge.js',
      'tv.css', 'qr.js', 'm3u-tv.js', 'spatial.js', 'player.js', 'app.js', 'vendor/hls.min.js',
    ]) {
      assert.ok(wgtEntries.has(required), `Mavie-Tizen.wgt missing ${required}`);
    }
    const tizenHtml = wgtEntries.get('index.html').toString('utf8');
    assert.ok(tizenHtml.includes('$WEBAPIS/webapis/webapis.js'), 'Tizen index.html missing $WEBAPIS script');
    assert.ok(tizenHtml.includes('tizen-bridge.js'), 'Tizen index.html missing tizen-bridge.js');
    assert.equal(wgtEntries.get('icon.png').subarray(0, 8).toString('hex'), '89504e470d0a1a0a', 'icon.png must be valid PNG');

    // 2) Validate LG webOS .ipk Debian/OPKG ar + tar.gz contents
    const arMembers = parseArArchive(fs.readFileSync(ipkPath));
    assert.equal(arMembers.get('debian-binary').toString('ascii'), '2.0\n');
    const controlFiles = parseTarBuffer(zlib.gunzipSync(arMembers.get('control.tar.gz')));
    assert.ok(controlFiles.has('control'), 'control.tar.gz missing control');
    assert.ok(controlFiles.get('control').toString('utf8').includes('Package: app.mavie.tv'));

    const dataFiles = parseTarBuffer(zlib.gunzipSync(arMembers.get('data.tar.gz')));
    const prefix = 'usr/palm/applications/app.mavie.tv';
    for (const required of [
      'appinfo.json', 'icon-80.png', 'icon-130.png', 'splash-1920x1080.png',
      'index.html', 'webos-bridge.js', 'tv.css', 'qr.js', 'm3u-tv.js', 'spatial.js', 'player.js', 'app.js', 'vendor/hls.min.js',
    ]) {
      assert.ok(dataFiles.has(`${prefix}/${required}`), `Mavie-webOS.ipk missing ${prefix}/${required}`);
    }
    const appinfo = JSON.parse(dataFiles.get(`${prefix}/appinfo.json`).toString('utf8'));
    assert.equal(appinfo.id, 'app.mavie.tv');
    assert.equal(appinfo.main, 'index.html');
    assert.equal(appinfo.icon, 'icon-80.png');
    assert.equal(appinfo.largeIcon, 'icon-130.png');
    assert.ok(dataFiles.get(`${prefix}/index.html`).toString('utf8').includes('webos-bridge.js'));
  } finally {
    fs.rmSync(tmpOut, { recursive: true, force: true });
  }
});
