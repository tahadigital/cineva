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
