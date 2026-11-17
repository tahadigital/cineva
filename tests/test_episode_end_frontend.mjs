import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import {harness} from './playback_harness.mjs';

const nextEpisode={id:'episode:next',kind:'episode',season:2,episode:1,name:'Yeni sezon',extension:'mkv'};

async function endEpisode({withNext=true,position=3000}={}) {
  const h=harness({responses:[{body:{startOffset:0,nextEpisode:withNext?nextEpisode:null}}]});
  await h.playItem('episode:test','remux',0);
  const video=h.element('#video');
  h.instances[0].emit('manifest');
  video.currentTime=position;video.paused=true;video.emit('ended');
  await h.settle();
  return h;
}

test('video exposes one full-title timeline in every playback mode',async()=>{
  const markup=fs.readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  const videoTag=markup.match(/<video\b[^>]+>/)?.[0];
  assert.ok(videoTag);
  assert.doesNotMatch(videoTag,/\bcontrols\b/);
  assert.equal([...markup.matchAll(/id="seekRange"/g)].length,1);
  const h=harness({responses:[{body:{duration:680000}}]});
  await h.playItem('episode:test','remux',0);
  const video=h.element('#video');
  video.duration=61;video.emit('loadedmetadata');
  assert.equal(h.element('#seekRange').max,'680000','the HLS window is never the timeline limit');
  await h.seekTo(640000);
  assert.equal(h.plays()[1].body.start,640000);
  assert.equal(h.element('#video'),video);
});

test('direct playback uses the complete media duration even when catalog metadata differs',async()=>{
  const h=harness({responses:[{body:{mode:'direct',type:'file',duration:60}}]});
  await h.playItem('episode:test','direct',0);
  const video=h.element('#video');
  video.duration=7202.5;video.emit('durationchange');video.emit('loadedmetadata');
  assert.equal(h.element('#seekRange').max,'7202.5');
  await h.seekTo(7100);
  assert.equal(h.plays().length,1);
  assert.equal(video.currentTime,7100);
});

test('an incompatible direct file switches mode in the same player at its absolute position',async()=>{
  const h=harness({responses:[{body:{mode:'direct',type:'file',startOffset:0}}]});
  await h.playItem('episode:test','direct',0);
  const video=h.element('#video');
  video.duration=3000;video.emit('loadedmetadata');
  video.currentTime=860;video.error={code:4};video.emit('error');
  await h.settle();
  assert.deepEqual(h.plays().map(r=>r.body.mode),['direct','remux']);
  assert.equal(h.plays()[1].body.start,860);
  assert.equal(h.element('#video'),video);
});

test('the actual end saves completion before automatically opening the next season',async()=>{
  const h=await endEpisode();
  assert.equal(h.element('#episodeEnding').hidden,false);
  assert.equal(h.element('#endingCaption').textContent,'SIRADAKİ BÖLÜM · S2 B1');
  assert.equal(h.element('#nextCountdown').textContent,'8');
  assert.equal(h.plays().length,1);
  await h.advance(4000);
  assert.equal(h.element('#nextCountdown').textContent,'4');
  await h.advance(4000);
  assert.equal(h.state.player.id,nextEpisode.id);
  assert.equal(h.plays()[1].body.start,0);
  assert.ok(h.requests.findIndex(r=>r.url==='/api/progress'&&r.body.completed===true&&r.body.position===3000)
    <h.requests.findIndex(r=>r.url==='/api/play'&&r.body.id===nextEpisode.id));
  assert.equal(h.element('#episodeEnding').hidden,true);
});

test('cancelling suppresses autoplay and gives both manual next and replay',async()=>{
  const manual=await endEpisode();
  manual.element('#cancelNextEpisode').emit('click');
  await manual.advance(10000);
  assert.equal(manual.plays().length,1);
  assert.equal(manual.element('#cancelNextEpisode').textContent,'Baştan oynat');
  manual.element('#playNextEpisode').emit('click');
  await manual.settle();
  assert.equal(manual.state.player.id,nextEpisode.id);
  const replay=await endEpisode();
  replay.element('#cancelNextEpisode').emit('click');
  replay.element('#cancelNextEpisode').emit('click');
  await replay.settle();
  assert.equal(replay.state.player.id,'episode:test');
  assert.equal(replay.plays()[1].body.start,0);
});

test('a prematurely ended transport window reconnects instead of skipping the episode',async()=>{
  const h=await endEpisode({position:115});
  assert.equal(h.plays()[1].body.id,'episode:test');
  assert.equal(h.plays()[1].body.start,115);
  assert.equal(h.element('#episodeEnding').hidden,true);
  assert.ok(h.requests.filter(r=>r.url==='/api/progress').every(r=>!r.body.completed));
});

test('the last episode ends cleanly and closing cancels a pending autoplay',async()=>{
  const last=await endEpisode({withNext:false});
  await last.advance(10000);
  assert.equal(last.plays().length,1);
  assert.equal(last.element('#episodeEnding').hidden,true);
  assert.equal(last.element('#togglePlay').attributes['aria-label'],'Baştan oynat');
  const pending=await endEpisode();
  await pending.stopPlayer();
  await pending.advance(10000);
  assert.equal(pending.plays().length,1);
});
