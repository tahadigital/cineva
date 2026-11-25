import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { harness } from './playback_harness.mjs';

test('Mavie web player markup exposes speed, fit, sleep timer, episode drawer, profile, multiview, and local picker', () => {
  const html = fs.readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../public/player.css', import.meta.url), 'utf8');
  for (const id of [
    'id="surpriseButton"', 'id="localFilePicker"', 'id="profileAvatarBtn"',
    'id="speedSelect"', 'id="fitButton"', 'id="pipButton"',
    'id="toggleSleep"', 'id="sleepPanel"', 'id="toggleEpisodesDrawer"',
    'id="episodeDrawerPanel"', 'id="subtitleScaleSelect"', 'href="#multiview"',
  ]) {
    assert.ok(html.includes(id), `Expected ${id} in index.html`);
  }
  assert.doesNotMatch(css, /#e50914|#ff4b45|#ff9933/i);
  assert.match(css, /#7c3aed/i);
});

test('speed shortcuts, mute shortcut, fit toggle, volume keys, and subtitle scaling operate cleanly', async () => {
  const h = harness();
  const video = h.element('#video');
  video.playbackRate = 1;
  video.volume = 0.8;
  const dialog = h.element('#playerDialog');
  dialog.open = true;
  const surface = h.element('#playerSurface');
  const props = {};
  surface.style.setProperty = (k, v) => { props[k] = v; };

  h.state.player = {
    id: 'vod:99', item: { id: 'vod:99', name: 'Test Film', kind: 'vod' },
    mode: 'direct', ready: true, mediaBound: true, start: 0, offset: 0, duration: 1200,
  };

  // Speed select + [ / ] shortcuts
  h.element('#speedSelect').value = '1.5';
  h.element('#speedSelect').emit('change');
  assert.equal(h.state.playbackRate, 1.5);
  assert.equal(video.playbackRate, 1.5);

  h.element('document').emit('keydown', { key: ']', code: 'BracketRight', preventDefault() {} });
  assert.equal(h.state.playbackRate, 2);
  h.element('document').emit('keydown', { key: '[', code: 'BracketLeft', preventDefault() {} });
  assert.equal(h.state.playbackRate, 1.5);

  // Volume & mute keyboard shortcuts
  h.element('document').emit('keydown', { key: 'ArrowUp', preventDefault() {} });
  assert.equal(video.volume, 0.9);
  h.element('document').emit('keydown', { key: 'm', preventDefault() {} });
  assert.equal(video.muted, true);
  h.element('document').emit('keydown', { key: 'm', preventDefault() {} });
  assert.equal(video.muted, false);

  // Screen fit toggle + subtitle scale CSS var
  h.element('#fitButton').emit('click');
  assert.equal(video.classList.contains('video-cover'), true);
  h.element('#fitButton').emit('click');
  assert.equal(video.classList.contains('video-cover'), false);

  h.element('#subtitleScaleSelect').value = '1.25';
  h.element('#subtitleScaleSelect').emit('change');
  assert.equal(props['--cue-scale'], '1.25');
});

test('C3: index.html #video allows PiP, updateTransport respects disablePictureInPicture, and #pipButton toggles PiP', async () => {
  const html = fs.readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  const videoTag = html.match(/<video[^>]*id="video"[^>]*>/i)?.[0] || '';
  assert.ok(videoTag, 'Expected #video tag');
  assert.equal(/disablepictureinpicture/i.test(videoTag), false, '#video must not set disablepictureinpicture');

  const h = harness();
  const video = h.element('#video');
  let requested = 0;
  let exited = 0;
  video.requestPictureInPicture = async () => { requested++; };
  h.context.document.exitPictureInPicture = async () => { exited++; };

  video.disablePictureInPicture = true;
  h.updateTransport();
  assert.equal(h.element('#pipButton').hidden, true);

  video.disablePictureInPicture = false;
  h.updateTransport();
  assert.equal(h.element('#pipButton').hidden, false);

  h.element('#pipButton').emit('click');
  await h.settle();
  assert.equal(requested, 1);

  h.context.document.pictureInPictureElement = video;
  h.element('#pipButton').emit('click');
  await h.settle();
  assert.equal(exited, 1);
});

test('M6: #playerVolume drops deprecated orient attribute, dialogs restore focus, and sw.js uses network-first for app shell', async () => {
  const html = fs.readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
  const playerCss = fs.readFileSync(new URL('../public/player.css', import.meta.url), 'utf8');
  const volTag = html.match(/<input[^>]*id="playerVolume"[^>]*>/i)?.[0] || '';
  assert.ok(volTag);
  assert.equal(/orient=/i.test(volTag), false);
  assert.match(playerCss, /writing-mode:\s*vertical-lr/i);

  const h = harness();
  const trigger = h.element('#triggerBtn');
  h.context.document.activeElement = trigger;
  h.openDialog('detailDialog');
  assert.equal(h.element('#detailDialog').open, true);
  h.context.document.activeElement = h.element('#insideDialog');
  h.closeDialog('detailDialog');
  assert.equal(h.context.document.activeElement, trigger);

  // Disconnected trigger falls back to #main
  h.context.document.activeElement = trigger;
  h.openDialog('listDialog');
  trigger.isConnected = false;
  h.closeDialog('listDialog');
  assert.equal(h.context.document.activeElement, h.element('#main'));

  // Verify sw.js network-first HTML/JS/CSS & cache fallback
  const swSrc = fs.readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8');
  const listeners = new Map();
  const cachedEntries = new Map();
  let networkOnline = true;
  const swCtx = vm.createContext({
    URL,
    location: { origin: 'http://127.0.0.1:8844' },
    self: {
      addEventListener: (ev, fn) => listeners.set(ev, fn),
      skipWaiting: () => Promise.resolve(),
      clients: { claim: () => Promise.resolve() },
    },
    caches: {
      open: async () => ({
        put: async (req, res) => cachedEntries.set(typeof req === 'string' ? req : req.url, res),
        addAll: async () => {},
      }),
      match: async (req) => cachedEntries.get(typeof req === 'string' ? req : req.url),
      keys: async () => [],
      delete: async () => true,
    },
    fetch: async (req) => {
      if (!networkOnline) throw new Error('offline');
      return { ok: true, body: 'fresh-' + req.url, clone() { return { ok: true, body: this.body }; } };
    },
  });
  vm.runInContext(swSrc, swCtx);
  const fetchFn = listeners.get('fetch');
  let responded = null;
  fetchFn({
    request: { method: 'GET', url: 'http://127.0.0.1:8844/app.js', mode: 'cors' },
    respondWith: (p) => { responded = p; },
  });
  const freshRes = await responded;
  assert.equal(freshRes.body, 'fresh-http://127.0.0.1:8844/app.js');
  await new Promise((r) => setImmediate(r));

  networkOnline = false;
  fetchFn({
    request: { method: 'GET', url: 'http://127.0.0.1:8844/app.js', mode: 'cors' },
    respondWith: (p) => { responded = p; },
  });
  const fallbackRes = await responded;
  assert.equal(fallbackRes.body, 'fresh-http://127.0.0.1:8844/app.js');

  // /api/ requests bypass SW
  let apiResponded = false;
  fetchFn({
    request: { method: 'GET', url: 'http://127.0.0.1:8844/api/status', mode: 'cors' },
    respondWith: () => { apiResponded = true; },
  });
  assert.equal(apiResponded, false);
});

test('M5: renderMultiView creates 20s ping timer, shows #mvStatus on fatal HLS error & 410 ping, and clearMultiView cleans up', async () => {
  const h = harness({
    fetchHandler: async (url) => {
      if (url.startsWith('/api/catalog')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: [
              { id: 'live:1', kind: 'live', name: 'Kanal 1' },
              { id: 'live:2', kind: 'live', name: 'Kanal 2' },
              { id: 'live:3', kind: 'live', name: 'Kanal 3' },
              { id: 'live:4', kind: 'live', name: 'Kanal 4' },
            ],
          }),
        };
      }
      if (url.endsWith('/ping')) {
        return { ok: false, status: 410, json: async () => ({ error: 'Oturum sona erdi.', error_code: 'session_expired' }) };
      }
      return null;
    },
  });
  h.state.renderId = 1;
  await h.renderMultiView(1);
  await h.settle();
  assert.equal(h.instances.length, 4);
  assert.equal(h.intervals.size, 1);

  // Fatal network error shows #mvStatus0
  h.instances[0].emit('error', { fatal: true, type: 'networkError' });
  assert.equal(h.element('#mvStatus0').hidden, false);
  assert.match(h.element('#mvStatus0').textContent, /Yayın yüklenemedi/);

  // 20s ping hitting 410 marks tile expired
  const pingEntry = [...h.intervals.values()][0];
  await pingEntry.callback();
  await h.settle();
  assert.equal(h.element('#mvStatus1').hidden, false);
  assert.match(h.element('#mvStatus1').textContent, /oturumu sona erdi/i);

  h.clearMultiView();
  assert.equal(h.intervals.size, 0);
});
