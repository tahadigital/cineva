import assert from 'node:assert/strict';
import test from 'node:test';
import {harness} from './playback_harness.mjs';

for(const webkit of [false,true]){
  test(`${webkit?'WebKit':'standard'} fullscreen enters on the player surface, toggles and exits when playback closes`,async()=>{
    const calls=[];
    const property=webkit?'webkitFullscreenElement':'fullscreenElement';
    let document;
    const h=harness({documentSetup(doc){
      document=doc;
      doc.querySelector('#playerSurface')[webkit?'webkitRequestFullscreen':'requestFullscreen']=function(){
        assert.equal(this,doc.querySelector('#playerSurface'));
        calls.push('enter');doc[property]=this;
        return Promise.resolve();
      };
      doc[webkit?'webkitExitFullscreen':'exitFullscreen']=function(){
        assert.equal(this,doc);
        calls.push('exit');doc[property]=null;
        return Promise.resolve();
      };
    }});
    await h.playItem('episode:test');
    const button=h.element('#fullscreenButton');
    assert.equal(button.hidden,false);
    button.emit('click');await h.settle();
    assert.equal(document[property],document.querySelector('#playerSurface'));
    h.element('document').emit(webkit?'webkitfullscreenchange':'fullscreenchange');
    assert.equal(button.attributes['aria-label'],'Tam ekrandan çık');
    button.emit('click');await h.settle();
    h.element('document').emit(webkit?'webkitfullscreenchange':'fullscreenchange');
    assert.equal(button.attributes['aria-label'],'Tam ekran');
    button.emit('click');await h.settle();
    await h.stopPlayer();
    assert.deepEqual(calls,['enter','exit','enter','exit']);
    assert.equal(h.element('#playerDialog').open,false);
  });
}

test('fullscreen control is hidden when the browser cannot request fullscreen',()=>{
  const h=harness();
  assert.equal(h.element('#fullscreenButton').hidden,true);
});

test('desktop single click on video pauses even when controls are hidden, while double click toggles fullscreen without pausing',async()=>{
  const fsCalls=[];
  const h=harness({documentSetup(doc){
    doc.querySelector('#playerSurface').requestFullscreen=function(){
      fsCalls.push('enter');doc.fullscreenElement=this;
      return Promise.resolve();
    };
    doc.exitFullscreen=function(){
      fsCalls.push('exit');doc.fullscreenElement=null;
      return Promise.resolve();
    };
  }});
  await h.playItem('episode:test');
  const video=h.element('#video');
  const dialog=h.element('#playerDialog');
  let pauseCalls=0,playCalls=0;
  video.pause=()=>{pauseCalls++;video.paused=true;};
  video.play=()=>{playCalls++;video.paused=false;return Promise.resolve();};
  h.instances[0].emit('manifest');
  video.paused=false;
  pauseCalls=0;playCalls=0;

  // Single desktop click when controls are hidden still pauses cleanly on the first click.
  dialog.classList.add('controls-hidden');
  dialog.emit('click',{target:video,pointerType:'mouse',detail:1});
  assert.equal(dialog.classList.contains('controls-hidden'),false);
  await h.runTimers(220);
  assert.equal(pauseCalls,1);
  assert.equal(fsCalls.length,0);

  // Double click cancels the pending click timer and toggles fullscreen without extra play/pause.
  pauseCalls=0;playCalls=0;
  dialog.emit('click',{target:video,pointerType:'mouse',detail:1});
  dialog.emit('click',{target:video,pointerType:'mouse',detail:2});
  video.emit('dblclick');
  await h.runTimers(250);
  assert.equal(playCalls,0);
  assert.equal(pauseCalls,0);
  assert.deepEqual(fsCalls,['enter']);
});
