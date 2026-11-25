import assert from 'node:assert/strict';
import test from 'node:test';
import {harness} from './playback_harness.mjs';

test('fatal remux error switches once to transcode and retains absolute progress', async () => {
  const h = harness();
  await h.playItem('episode:test');
  const first = h.state.player, oldHls = h.instances[0];
  oldHls.emit('manifest');
  h.element('#video').currentTime = 9;
  oldHls.emit('error', {fatal: true, type: 'mediaError'});
  oldHls.emit('error', {fatal: true, type: 'mediaError'});
  await h.settle();
  assert.deepEqual(h.plays().map(request => request.body.mode), ['remux', 'transcode']);
  assert.equal(h.plays()[1].body.start, 129);
  assert.equal(h.state.player.mode, 'transcode');
  assert.equal(h.state.player.fallbackUsed, true);
  assert.equal(h.modes[2].classList.contains('active'), true);
  assert.ok(h.requests.some(request => request.url === `/api/play/${first.sessionId}` && request.method === 'DELETE'));
  const replacement = h.state.player;
  oldHls.emit('manifest');
  oldHls.emit('error', {fatal: true, type: 'networkError'});
  assert.equal(h.state.player, replacement);
  assert.equal(replacement.ready, false);
  const replacementHls = h.instances[1];
  replacementHls.emit('error', {fatal: true, type: 'networkError'});
  await h.settle();
  assert.equal(h.plays().length, 2);
  assert.equal(h.element('#playerOverlay').classList.contains('error'), true);
});

test('native video errors use the same bounded fallback', async () => {
  const h = harness({hls: false});
  await h.playItem('episode:test');
  const video = h.element('#video');
  video.emit('loadedmetadata');
  video.currentTime = 7;
  video.error = {code: 4};
  video.emit('error');
  await h.settle();
  assert.deepEqual(h.plays().map(request => request.body.mode), ['remux', 'transcode']);
  assert.equal(h.plays()[1].body.start, 127);
  video.error = {code: 4};
  video.emit('error');
  await h.settle();
  assert.equal(h.plays().length, 2);
});

test('remux startup failure retries once at the requested resume point', async () => {
  const h = harness({responses: [{status: 500, body: {error: 'Uyumlu yayın başlatılamadı.'}}]});
  await h.playItem('episode:test');
  await h.settle();
  assert.deepEqual(h.plays().map(request => request.body.mode), ['remux', 'transcode']);
  assert.equal(h.plays()[1].body.start, 120);
});

test('server-selected transcode is authoritative for the UI and metadata events', async () => {
  const h = harness({responses: [{body: {mode: 'transcode'}}]});
  await h.playItem('episode:test', 'direct', 120);
  assert.equal(h.state.player.mode, 'transcode');
  assert.equal(h.modes[2].classList.contains('active'), true);
  assert.equal(h.element('#absoluteSeek').hidden, false);
  const video = h.element('#video');
  video.currentTime = 0;
  video.emit('loadedmetadata');
  assert.equal(video.currentTime, 0, 'transcoded media must not seek twice');
  h.instances[0].emit('manifest');
  assert.equal(video.currentTime, 0, 'manifest callback must use the server-selected mode');
  h.instances[0].emit('error', {fatal: true, type: 'networkError'});
  await h.settle();
  assert.equal(h.plays().length, 1);
});

for (const response of [
  {status: 410, body: {error: 'Oturum sona erdi.'}},
  {status: 400, body: {error: 'Geçersiz istek.'}},
  {status: 500, body: {error: 'Dönüştürme başarısız.', mode: 'transcode'}},
  {status: 502, body: {error: 'Sağlayıcı bölüm için video göndermedi.', code: 'upstream_empty'}},
  {status: 502, body: {error: 'Sağlayıcı yanıt vermedi.', code: 'upstream_unavailable'}},
]) {
  test(`startup error ${response.body.code || response.body.mode || response.status} does not retry`, async () => {
    const h = harness({responses: [response]});
    await h.playItem('episode:test');
    await h.settle();
    assert.equal(h.plays().length, 1);
    assert.equal(h.element('#playerMessage').textContent, response.body.error);
    if (response.body.mode) assert.equal(h.state.player.mode, response.body.mode);
    if (response.body.code) assert.match(h.element('#playerHint').textContent, /sağlayıcıdan gelmedi/);
  });
}

test('cancelled startup and missing FFmpeg do not trigger fallback', async () => {
  const error = new Error('İstek iptal edildi.'); error.name = 'AbortError';
  const cancelled = harness({responses: [error]});
  await cancelled.playItem('episode:test');
  await cancelled.settle();
  assert.equal(cancelled.plays().length, 1);
  const unavailable = harness({ffmpeg: false});
  await unavailable.playItem('episode:test', 'remux');
  unavailable.instances[0].emit('error', {fatal: true, type: 'networkError'});
  await unavailable.settle();
  assert.equal(unavailable.plays().length, 1);
});

test('M5: playLocalFile error shows local_unsupported hint, disables mode buttons, and never calls /api/play', async () => {
  const h = harness();
  h.context.URL.createObjectURL = () => 'blob:local-test-1';
  h.context.URL.revokeObjectURL = () => {};
  await h.playLocalFile({ name: 'sample.mkv' });
  assert.equal(h.plays().length, 0);
  assert.equal(h.modes[1].disabled, true);
  assert.equal(h.modes[2].disabled, true);

  const video = h.element('#video');
  h.state.player.duration = 120;
  await h.seekTo(42);
  assert.equal(video.currentTime, 42);
  assert.equal(h.plays().length, 0);

  video.error = { code: 4 };
  video.emit('error');
  await h.settle();
  await h.seekTo(60);
  assert.equal(h.plays().length, 0);
  assert.equal(h.element('#playerOverlay').classList.contains('error'), true);
  assert.match(h.element('#playerHint').textContent, /Yerel Klasör/i);
});

test('M5: epgTime handles numeric and string epochs, api() handles timeout & error_code, and pingPlayback 410 interrupts playback', async () => {
  const h = harness({
    fetchHandler: async (url, options = {}) => {
      if (url === '/api/slow') {
        return new Promise((_resolve, reject) => {
          options.signal?.addEventListener('abort', () => {
            const err = new Error('Aborted');
            err.name = 'AbortError';
            reject(err);
          });
        });
      }
      if (url === '/api/errcode') {
        return { ok: false, status: 410, json: async () => ({ error: 'Bitti', error_code: 'session_expired' }) };
      }
      if (url.endsWith('/ping')) {
        return { ok: false, status: 410, json: async () => ({ error: 'Oturum bitti', error_code: 'session_expired' }) };
      }
      return null;
    },
  });

  // epgTime numeric + string epoch + invalid
  assert.match(h.epgTime(1732250000), /^\d{2}:\d{2}$/);
  assert.match(h.epgTime('1732250000'), /^\d{2}:\d{2}$/);
  assert.match(h.epgTime('1732250000000'), /^\d{2}:\d{2}$/);
  assert.equal(h.epgTime(''), '');
  assert.equal(h.epgTime('not-a-date'), '');

  // api() error_code fallback
  await assert.rejects(() => h.api('/api/errcode'), (err) => err.status === 410 && err.code === 'session_expired');

  // api() AbortController timeout
  const pending = h.api('/api/slow', { timeoutMs: 5000 });
  await h.runTimers(5000);
  await assert.rejects(() => pending, (err) => err.name === 'TimeoutError' && err.code === 'timeout');

  // pingPlayback 410 calls interruptPlayback -> clears sessionId, sets ready=false, shows error overlay
  await h.playItem('episode:test');
  assert.ok(h.state.player.sessionId);
  h.state.player.ready = true;
  await h.pingPlayback();
  await h.settle();
  assert.equal(h.state.player.sessionId, null);
  assert.equal(h.state.player.ready, false);
  assert.equal(h.element('#playerOverlay').classList.contains('error'), true);
});
