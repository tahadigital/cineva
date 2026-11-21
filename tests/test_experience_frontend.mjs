import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../public/experience.js', import.meta.url), 'utf8');

function experience({reduced = false, storage = new Map(), blockedStorage = false, loading = false} = {}) {
  let now = 0, sequence = 0, mutationCallback, busy = loading;
  const timers = new Map(), events = new Map(), windowEvents = new Map(), classes = new Set(), animations = [];
  const createCard = () => ({isConnected: true, animate() {
    const animation = {finished: new Promise(() => {}), cancelled: false, cancel() { this.cancelled = true; }};
    animations.push(animation);
    return animation;
  }});
  let cards = [createCard()];
  const intro = {hidden: true, removed: false, classList: {add: value => classes.add(value)}, remove() { this.removed = true; }};
  const main = {querySelector: () => busy ? {} : null, querySelectorAll: () => cards};
  const motion = {matches: reduced, addEventListener(_name, callback) { this.callback = callback; }};
  const document = {
    readyState: 'interactive', hidden: false,
    getElementById: id => id === 'mavieLaunch' ? (intro.removed ? null : intro) : id === 'main' ? main : null,
    addEventListener: (name, callback) => events.set(name, callback),
  };
  class IntersectionObserver {
    constructor(callback) { this.callback = callback; }
    observe(target) { this.callback([{target, isIntersecting: true}]); }
    unobserve() {}
  }
  class MutationObserver {
    constructor(callback) { mutationCallback = callback; }
    observe() {}
  }
  const setTimeout = (callback, delay) => {
    const id = ++sequence; timers.set(id, {at: now + delay, callback}); return id;
  };
  const context = {
    document, Set, WeakSet, IntersectionObserver, MutationObserver,
    sessionStorage: {
      getItem(key) { if (blockedStorage) throw new Error('Storage unavailable'); return storage.get(key); },
      setItem(key, value) { if (blockedStorage) throw new Error('Storage unavailable'); storage.set(key, value); },
    },
    window: {matchMedia: () => motion, IntersectionObserver, addEventListener: (name, callback) => windowEvents.set(name, callback)},
    setTimeout, clearTimeout: id => timers.delete(id), requestAnimationFrame: callback => setTimeout(callback, 1),
  };
  vm.runInNewContext(source, context);
  function advance(milliseconds) {
    const end = now + milliseconds;
    while (true) {
      const next = [...timers].filter(([, value]) => value.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      timers.delete(next[0]); now = next[1].at; next[1].callback();
    }
    now = end;
  }
  return {
    intro, classes, events, windowEvents, motion, storage, document, animations, advance,
    mutate: () => mutationCallback(),
    setLoading(value) { busy = value; },
    replaceCards() { cards.forEach(card => { card.isConnected = false; }); cards = [createCard()]; },
  };
}

test('cold launch dismisses cleanly and lets loaded cards enter afterward', () => {
  const h = experience();
  assert.equal(h.intro.hidden, false);
  h.advance(719);
  assert.equal(h.intro.removed, false);
  assert.equal(h.animations.length, 0, 'card entrance should wait for the cover, not data fetching');
  h.advance(190);
  assert.equal(h.intro.removed, true);
  assert.equal(h.animations.length, 1);
});

test('a reload within the same tab session skips the launch cover', () => {
  const storage = new Map();
  const first = experience({storage}); first.advance(2510);
  const reload = experience({storage});
  assert.equal(reload.intro.removed, true);
  reload.advance(10);
  assert.equal(reload.animations.length, 1);
});

test('reduced motion bypasses intro and card animations completely', () => {
  const h = experience({reduced: true});
  h.advance(1500);
  assert.equal(h.intro.removed, true);
  assert.equal(h.animations.length, 0);
});

test('changing reduced-motion preference immediately dismisses an active intro', () => {
  const h = experience();
  h.motion.matches = true; h.motion.callback();
  assert.equal(h.intro.removed, true);
  h.advance(1500);
  assert.equal(h.animations.length, 0);
});

test('idle home refresh does not replay animations, while a real navigation does', () => {
  const h = experience({storage: new Map([['mavie:launch:v1', '1']])});
  h.advance(10);
  assert.equal(h.animations.length, 1);
  h.replaceCards(); h.mutate(); h.advance(10);
  assert.equal(h.animations.length, 1);
  h.setLoading(true); h.windowEvents.get('hashchange')(); h.advance(10);
  assert.equal(h.animations.length, 1, 'a loading placeholder must not consume the navigation animation');
  h.setLoading(false); h.mutate(); h.advance(10);
  assert.equal(h.animations.length, 2);
});

test('blocked session storage cannot strand the launch cover', () => {
  const h = experience({blockedStorage: true});
  h.advance(1000);
  assert.equal(h.intro.removed, true);
});

test('hiding the page dismisses the cover and cancels any remaining timer', () => {
  const h = experience();
  h.document.hidden = true; h.events.get('visibilitychange')();
  assert.equal(h.intro.removed, true);
  h.advance(1500);
  assert.equal(h.animations.length, 0);
});

test('a runtime reduced-motion change cancels active entrance animations', () => {
  const h = experience({storage: new Map([['mavie:launch:v1', '1']])});
  h.advance(10);
  h.motion.matches = true; h.motion.callback();
  assert.ok(h.animations.length > 0);
  assert.ok(h.animations.every(animation => animation.cancelled));
});
