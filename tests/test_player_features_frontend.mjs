import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
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
