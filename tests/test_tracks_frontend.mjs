import assert from 'node:assert/strict';
import test from 'node:test';
import {harness} from './playback_harness.mjs';
const sourceTracks={scanned:true,audio:[{id:'stream:1',index:1,language:'tur',title:'Türkçe Dublaj',codec:'aac',default:true},{id:'stream:2',index:2,language:'eng',title:'English',codec:'aac'}],subtitles:[{id:'stream:3',index:3,language:'tur',codec:'subrip'},{id:'stream:4',index:4,language:'eng',codec:'ass'}]};
const response=(extra={})=>({body:{tracks:sourceTracks,selection:{audio:'auto',subtitle:'off'},mode:'remux',...extra}});

test('native HLS restores generated subtitle visibility after playback resumes',async()=>{
 const h=harness({hls:false,tracks:true,responses:[response({selection:{audio:'auto',subtitle:'stream:4'}})]});
 const video=h.element('#video');
 video.textTracks=[{kind:'subtitles',language:'eng',mode:'disabled'},{kind:'metadata',mode:'hidden'}];
 await h.playItem('episode:test');
 video.emit('playing');
 assert.equal(video.textTracks[0].mode,'showing');
 assert.equal(video.textTracks[1].mode,'hidden');
 video.textTracks[0].mode='disabled';
 video.emit('playing');
 assert.equal(video.textTracks[0].mode,'showing');
 h.state.player.selection.subtitle='off';
 video.emit('playing');
 assert.equal(video.textTracks[0].mode,'disabled');
 assert.equal(video.textTracks[1].mode,'hidden');
});

test('every provider track is displayed with Turkish language labels and subtitle off',async()=>{
 const h=harness({tracks:true,responses:[response()]});await h.playItem('episode:test');
 assert.match(h.element('#audioTrackSelect').innerHTML,/stream:1/);assert.match(h.element('#audioTrackSelect').innerHTML,/stream:2/);
 assert.match(h.element('#audioTrackSelect').innerHTML,/Türkçe/);assert.match(h.element('#audioTrackSelect').innerHTML,/İngilizce/);
 assert.match(h.element('#subtitleTrackSelect').innerHTML,/stream:3/);assert.match(h.element('#subtitleTrackSelect').innerHTML,/stream:4/);
 assert.equal(h.element('#subtitleTrackSelect').value,'off');
});
test('source audio switch restarts at absolute position and preserves subtitle selection',async()=>{
 const selection={audio:'auto',subtitle:'stream:4'};
 const h=harness({tracks:true,responses:[response({startOffset:120,selection}),response({selection:{audio:'stream:2',subtitle:'stream:4'}})]});
 await h.playItem('episode:test');h.instances[0].emit('manifest');h.element('#video').currentTime=9;
 await h.tracks.change('audio','stream:2');
 const request=h.plays()[1];assert.equal(request.body.audioTrack,'stream:2');assert.equal(request.body.subtitleTrack,'stream:4');assert.equal(request.body.start,129);
});
test('subtitle switch and off are both sent to the server',async()=>{
 const h=harness({tracks:true,responses:[response(),response({selection:{audio:'auto',subtitle:'stream:3'}}),response()]});
 await h.playItem('episode:test');await h.tracks.change('subtitle','stream:3');await h.tracks.change('subtitle','off');
 assert.equal(h.plays()[1].body.subtitleTrack,'stream:3');assert.equal(h.plays()[2].body.subtitleTrack,'off');
});
test('HLS rendition controls switch without opening a second provider stream and persist',async()=>{
 const h=harness({tracks:true,responses:[response({mode:'direct'})]});await h.playItem('episode:test','direct');
 const stream=h.instances[0];stream.audioTracks=[{lang:'tur',name:'Dublaj'},{lang:'eng',name:'Original'}];stream.subtitleTracks=[{lang:'tur',name:'Türkçe'}];
 stream.emit('audio-updated');stream.emit('subtitle-updated');
 await h.tracks.change('audio','hls:1');await h.tracks.change('subtitle','hls:0');
 assert.equal(stream.audioTrack,1);assert.equal(stream.subtitleTrack,0);assert.equal(h.plays().length,1);
 assert.ok(h.requests.some(r=>r.url==='/api/track-preferences'&&r.body.clientAudio==='hls:1'));
 await h.tracks.change('subtitle','off');assert.equal(stream.subtitleTrack,-1);
});
test('selected generated subtitles activate HLS WebVTT while all source options remain visible',async()=>{
 const h=harness({tracks:true,responses:[response({selection:{audio:'auto',subtitle:'stream:4'}})]});await h.playItem('episode:test');
 const stream=h.instances[0];stream.subtitleTracks=[{lang:'eng',name:'English'}];stream.emit('subtitle-updated');
 assert.equal(stream.subtitleTrack,0);assert.match(h.element('#subtitleTrackSelect').innerHTML,/stream:3/);assert.match(h.element('#subtitleTrackSelect').innerHTML,/stream:4/);
});
test('stale manifests cannot apply track preferences to replacement playback',async()=>{
 const h=harness({tracks:true,responses:[response(),response()]});await h.playItem('episode:test');const old=h.instances[0];
 await h.playItem('episode:test','transcode',150);old.subtitleTracks=[{name:'stale'}];old.emit('subtitle-updated');
 assert.equal(h.state.hls,h.instances[1]);assert.equal(h.state.hls.subtitleTrack,-1);
});
