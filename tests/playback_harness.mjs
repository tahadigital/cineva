import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync(new URL('../public/app.js', import.meta.url), 'utf8')
  .replace(/init\(\);\s*$/, 'globalThis.playbackTest={state,empty,confirmDialog,section,renderFavorites,renderPlaylists,resumeCard,playItem,stopPlayer,bindPlayer,seekTo,requestSeek,skipPlayback,pingPlayback};');

export function harness({hls = true, responses = [], ffmpeg = true, tracks = false, documentSetup} = {}) {
  const elements = new Map(), requests = [], instances = [], timers = new Map();
  function element(selector) {
    if (elements.has(selector)) return elements.get(selector);
    const events = new Map(), classes = new Set();
    const el = {
      hidden: false, open: false, currentTime: 0, duration: NaN, error: null, paused: false, readyState: 0,
      volume: 1, muted: false, dataset: {}, style: {}, textContent: '', src: '', attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; },
      classList: {
        add: value => classes.add(value), remove: value => classes.delete(value),
        contains: value => classes.has(value),
        toggle(value, force) { if (force ?? !classes.has(value)) classes.add(value); else classes.delete(value); },
      },
      addEventListener(name, callback) { if (!events.has(name)) events.set(name, []); events.get(name).push(callback); },
      emit(name, detail = {}) { for (const callback of events.get(name) || []) callback({target: el, ...detail}); },
      play: () => Promise.resolve(), pause() {}, load() {},
      removeAttribute(name) { if (name === 'src') { this.src = ''; this.currentTime = 0; this.error = null; } },
      canPlayType: () => hls ? '' : 'probably',
      showModal() { this.open = true; }, close() { this.open = false; },
    };
    elements.set(selector, el);
    return el;
  }
  const modes = ['direct', 'remux', 'transcode'].map(mode => {
    const el = element(`[data-mode=${mode}]`); el.dataset.mode = mode; return el;
  });
  class FakeHls {
    static Events = {MANIFEST_PARSED: 'manifest', ERROR: 'error', AUDIO_TRACKS_UPDATED:'audio-updated', SUBTITLE_TRACKS_UPDATED:'subtitle-updated'};
    static ErrorTypes = {MEDIA_ERROR: 'mediaError'};
    static isSupported = () => hls;
    constructor(config) { this.config=config;this.audioTracks=[];this.subtitleTracks=[];this.audioTrack=0;this.subtitleTrack=-1;this.subtitleDisplay=false;this.events = new Map(); this.recoveries = 0; instances.push(this); }
    loadSource(url) { this.url = url; }
    attachMedia(video) { this.video = video; }
    on(name, callback) { if(!this.events.has(name))this.events.set(name,[]);this.events.get(name).push(callback); }
    emit(name, data) { for(const fn of this.events.get(name)||[])fn(name,data); }
    recoverMediaError() { this.recoveries++; }
    destroy() { this.destroyed = true; }
  }
  let sequence = 0, now = Date.now();
  class FakeDate extends Date { static now() { return now; } }
  const context = vm.createContext({
    URLSearchParams, Intl, Date: FakeDate, Math, Map, Number, String, Array, Object,
    Hls: FakeHls, HTMLImageElement: class {},
    window: {Hls: FakeHls, addEventListener() {}},
    document: {
      activeElement: null, documentElement: element('html'),
      addEventListener: (name, callback) => element('document').addEventListener(name, callback),
      querySelector: element, getElementById:id=>element('#'+id),
      querySelectorAll: selector => selector === '[data-mode]' ? modes : [],
    },
    location: {hash: '#vod'}, navigator: {},
    setInterval: () => ++sequence, clearInterval() {},
    setTimeout(callback, delay) {const id=++sequence;timers.set(id,{callback,delay});return id;},
    clearTimeout(id) {timers.delete(id);},
    async fetch(url, options = {}) {
      const body = options.body ? JSON.parse(options.body) : undefined;
      requests.push({url, method: options.method || 'GET', body});
      let response = {sessionId: `session-${++sequence}`, type: 'hls', url: '/media/current/index.m3u8', startOffset: body?.start || 0, duration: 3000};
      let status = 200;
      if (url === '/api/play') {
        const next = responses.shift();
        if (next instanceof Error) throw next;
        if (next) { const value=typeof next==='function'?await next():next;response = {...response, ...value.body}; status = value.status || 200; }
      }
      return {ok: status < 400, status, json: async () => response};
    },
  });
  if(tracks)vm.runInContext(fs.readFileSync(new URL('../public/tracks.js', import.meta.url),'utf8'),context);
  vm.runInContext(source, context);
  const api = context.playbackTest;
  api.state.status = {ffmpeg, authorized: true};
  api.state.route = 'vod';
  api.state.items.set('episode:test', {id: 'episode:test', kind: 'episode', name: 'Test bölümü', extension: 'mkv', progress: {position: 120}});
  documentSetup?.(context.document);
  api.bindPlayer();
  if(tracks)context.window.VrelioTracks.bind();
  const plays = () => requests.filter(request => request.url === '/api/play');
  const settle = () => new Promise(resolve => setImmediate(resolve));
  const runTimers=async(maxDelay=Infinity)=>{for(const [id,timer] of [...timers]){if(timer.delay>maxDelay||!timers.has(id))continue;timers.delete(id);await timer.callback();}await settle();};
  const advance=async(milliseconds)=>{now+=milliseconds;await runTimers(milliseconds);};
  return {...api, tracks:context.window.VrelioTracks, element, modes, requests, instances, plays, settle,runTimers,timers,advance};
}

