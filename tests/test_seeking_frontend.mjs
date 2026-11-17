import assert from 'node:assert/strict';
import test from 'node:test';
import {harness} from './playback_harness.mjs';

const ranges = (...entries) => ({length:entries.length,start:i=>entries[i][0],end:i=>entries[i][1]});

function prepared(h) {
  const video=h.element('#video');
  h.instances.at(-1)?.emit('manifest');
  video.currentTime=5;video.paused=false;
  video.buffered=ranges([0,35]);video.seekable=ranges([0,60]);
  video.emit('playing');
  return video;
}

test('buffered backward and forward seeks retain the player and provider session',async()=>{
  const h=harness();await h.playItem('episode:test');const video=prepared(h);
  const player=h.state.player,hls=h.instances[0];video.paused=true;
  await h.seekTo(123);
  assert.equal(video.currentTime,3);assert.equal(h.state.player,player);assert.equal(h.plays().length,1);
  await h.seekTo(145);
  assert.equal(video.currentTime,25);assert.equal(h.state.player,player);assert.equal(h.plays().length,1);
  assert.equal(hls.destroyed,undefined);assert.equal(video.paused,true);
});

test('retained seekable data can be fetched without restarting an unbuffered position',async()=>{
  const h=harness();await h.playItem('episode:test');const video=prepared(h);
  video.buffered=ranges([0,10]);video.seekable=ranges([0,90]);
  await h.seekTo(180);
  assert.equal(video.currentTime,60);assert.equal(h.plays().length,1);
});

test('direct file seeking uses the browser even outside its current buffered range',async()=>{
  const h=harness({responses:[{body:{mode:'direct',type:'file',startOffset:0}}]});
  await h.playItem('episode:test','direct',0);
  const video=h.element('#video');video.emit('loadedmetadata');video.buffered=ranges([0,10]);
  await h.seekTo(900);
  assert.equal(video.currentTime,900);assert.equal(h.plays().length,1);
});

test('out-of-cache seek keeps the chosen tracks and paused state',async()=>{
  const selection={audio:'stream:3',subtitle:'stream:1'};
  const h=harness({tracks:true,responses:[{body:{selection}}]});
  await h.playItem('episode:test');const video=prepared(h);video.paused=true;
  await h.seekTo(900);
  const request=h.plays()[1].body;
  assert.equal(request.start,900);assert.equal(request.audioTrack,'stream:3');assert.equal(request.subtitleTrack,'stream:1');
  assert.equal(request.paused,true);assert.equal(h.state.player.restorePaused,true);
});

test('rapid ten-second skips coalesce and accumulate before restarting once',async()=>{
  const h=harness();await h.playItem('episode:test');const video=prepared(h);
  video.buffered=ranges([0,10]);video.seekable=ranges([0,10]);
  h.skipPlayback(10);h.skipPlayback(10);h.skipPlayback(10);
  assert.equal(h.plays().length,1);
  await h.runTimers(219);assert.equal(h.plays().length,1);
  await h.runTimers(220);
  assert.equal(h.plays().length,2);assert.equal(h.plays()[1].body.start,155);
});

test('generated VOD starts at its requested beginning while live keeps normal HLS behavior',async()=>{
  const h=harness();await h.playItem('episode:test');
  assert.equal(h.instances[0].config.startPosition,0);
  assert.ok(h.instances[0].config.liveSyncDuration>3000);
  assert.equal(h.instances[0].config.maxLiveSyncPlaybackRate,1);
  h.state.items.set('live:test',{id:'live:test',kind:'live',name:'Live'});
  await h.playItem('live:test');
  assert.equal(h.instances[1].config.liveSyncDuration,undefined);
  assert.equal(h.instances[1].config.startPosition,undefined);
});

test('a stale startup cannot replace a newer player or attach its manifest',async()=>{
  let release;const pending=new Promise(resolve=>{release=resolve;});
  const h=harness({responses:[async()=>await pending,{body:{sessionId:'latest-session',startOffset:300}}]});
  const old=h.playItem('episode:test','remux',120);
  await h.playItem('episode:test','remux',300);
  const latest=h.state.player;
  release({body:{sessionId:'stale-session',startOffset:120}});await old;
  assert.equal(h.state.player,latest);assert.equal(latest.start,300);assert.equal(latest.sessionId,'latest-session');
  assert.equal(h.instances.length,1);
  assert.ok(h.requests.some(r=>r.url==='/api/play/stale-session'&&r.method==='DELETE'));
});

test('brief waiting gaps do not flash an overlay and persistent gaps show a delayed indicator',async()=>{
  const h=harness();await h.playItem('episode:test');const video=prepared(h);video.readyState=2;
  video.emit('waiting');await h.runTimers(449);
  assert.equal(h.element('#playerOverlay').hidden,true);
  video.emit('canplay');await h.runTimers(500);
  assert.equal(h.element('#playerOverlay').hidden,true);
  video.emit('waiting');await h.runTimers(450);
  assert.equal(h.element('#playerOverlay').hidden,false);
  assert.equal(h.element('#playerOverlay').classList.contains('buffering'),true);
  video.emit('playing');
  assert.equal(h.element('#playerOverlay').hidden,true);
});

test('a waiting timer belonging to an old source cannot cover the replacement player',async()=>{
  const h=harness();await h.playItem('episode:test');const video=prepared(h);video.readyState=2;
  video.emit('waiting');
  await h.playItem('episode:test','remux',800);
  await h.runTimers(500);
  assert.equal(h.element('#playerOverlay').classList.contains('buffering'),false);
});
