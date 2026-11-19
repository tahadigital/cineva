// Real browser integration; requires Playwright and an H.264-capable Chromium.
const {chromium,webkit}=require('playwright');
const {spawn}=require('child_process'); const readline=require('readline'); const path=require('path'); const fs=require('fs'); const assert=require('node:assert/strict');
(async()=>{
const server=spawn('.venv/bin/python',[path.join(__dirname,'subtitle_browser_server.py')],{cwd:process.cwd(),stdio:['ignore','pipe','pipe']});
let browser;
try {
const port=await new Promise((resolve,reject)=>{readline.createInterface({input:server.stdout}).once('line',resolve);server.once('exit',c=>reject(Error('fixture server exit '+c)));});
const useWebkit=process.env.AKIS_BROWSER_ENGINE==='webkit';
const native=useWebkit&&!process.env.AKIS_FORCE_MSE;
browser=await (useWebkit?webkit:chromium).launch({...(!useWebkit&&process.env.AKIS_TEST_BROWSER?{executablePath:process.env.AKIS_TEST_BROWSER}:{}),headless:true,...(!useWebkit?{args:['--autoplay-policy=no-user-gesture-required']}:{} )});
const page=await browser.newPage();await page.goto('http://127.0.0.1:'+port);await page.addScriptTag({url:'/hls.js'});
await page.evaluate(()=>{window.state={hls:null,player:null,status:{ffmpeg:true}};window.esc=x=>String(x);window.notify=()=>{};window.api=async(url,o={})=>{const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o.body||{})});return r.json();};});
await page.addScriptTag({url:'/tracks.js'});await page.evaluate(native=>window.nativeHls=native,native);
await page.evaluate(rate=>{
 window.testRate=rate;VrelioTracks.bind();window.errors=[];window.seen=[];
 const video=document.querySelector('#video');
 const collect=()=>{for(const t of video.textTracks)for(const cue of t.activeCues||[])if(!seen.some(x=>x.text===cue.text&&x.epoch===window.epoch))seen.push({epoch:window.epoch,text:cue.text,time:video.currentTime,start:cue.startTime,end:cue.endTime});};
 video.textTracks.addEventListener('addtrack',event=>event.track.addEventListener('cuechange',collect));
 setInterval(collect,25);
 setInterval(()=>{if(state.player)api('/ping',{body:{sid:state.player.sessionId,position:video.currentTime}}).catch(()=>{});},250);
 window.start=async(offset=0)=>{
  state.hls?.destroy();const r=await api('/start',{body:{offset}});
  const p=state.player={mode:'remux',id:'fixture',item:{kind:'episode'},sessionId:r.sessionId,selection:{audio:'auto',subtitle:'stream:2'},tracks:{audio:[],subtitles:[{id:'stream:2',language:'eng'}],scanned:true}};
  window.epoch=(window.epoch||0)+1;
  if(window.nativeHls){
   state.hls=null;await new Promise((resolve,reject)=>{video.onloadedmetadata=resolve;video.onerror=()=>reject(Error('Native HLS error '+video.error?.code));video.src=r.url;});
   // Production bindPlayer() positions generated VOD at session time zero
   // in loadedmetadata before playing, rather than following the live edge.
   video.currentTime=0;
  }else{
  const h=state.hls=new Hls({enableWorker:true,lowLatencyMode:false,backBufferLength:120,maxBufferLength:60,maxMaxBufferLength:90,maxBufferSize:64*1024*1024,startPosition:0,liveSyncDuration:86400,liveMaxLatencyDuration:Infinity,maxLiveSyncPlaybackRate:1});
  VrelioTracks.bindHls(p,h);h.on(Hls.Events.ERROR,(_,d)=>errors.push({fatal:d.fatal,details:d.details}));
  h.loadSource(r.url);h.attachMedia(video);await new Promise(res=>h.on(Hls.Events.MANIFEST_PARSED,res));}
  video.playbackRate=window.testRate;await video.play();
 };
},Number(process.env.AKIS_SUBTITLE_RATE||1));
const reporter=setInterval(async()=>{try{console.error('progress',JSON.stringify(await page.evaluate(()=>({time:document.querySelector('#video').currentTime,ready:document.querySelector('#video').readyState,rate:document.querySelector('#video').playbackRate,cues:seen.length,epoch:window.epoch,tracks:[...document.querySelector('#video').textTracks].map(t=>({mode:t.mode,cues:t.cues?.length}))}))));}catch{}},10000);reporter.unref();
await page.evaluate(()=>Promise.race([start(),new Promise((_,reject)=>setTimeout(()=>reject(Error('Initial playback timed out')),30000))]));
if(process.env.AKIS_SUBTITLE_SHORT_NATIVE){
 await page.waitForFunction(()=>document.querySelector('#video').currentTime>=12&&document.querySelector('#video').currentTime<15,{},{timeout:30000});
 await page.screenshot({path:process.env.AKIS_SUBTITLE_SHORT_NATIVE});console.log(JSON.stringify(await page.evaluate(()=>({time:document.querySelector('#video').currentTime,seen,tracks:[...document.querySelector('#video').textTracks].map(t=>({mode:t.mode,language:t.language,cues:[...(t.cues||[])].map(c=>({start:c.startTime,end:c.endTime,text:c.text}))}))})),null,2));return;
}
await page.waitForFunction(()=>document.querySelector('#video').currentTime>319.5,{},{timeout:360000});

const linear=await page.evaluate(()=>({time:document.querySelector('#video').currentTime,seen:[...seen],errors:[...errors]}));
if(process.env.AKIS_SUBTITLE_DIAGNOSTIC)fs.writeFileSync(process.env.AKIS_SUBTITLE_DIAGNOSTIC,JSON.stringify(linear,null,2));
const expected=[0,4,8,12,16,...Array.from({length:40},(_,i)=>160+i*4)];
for(const t of expected){const cue=linear.seen.find(x=>x.text==='CUE_'+t);assert.ok(cue,'Missing rendered cue '+t);assert.ok(Math.abs(cue.start-t)<.15,'Subtitle clock drift at '+t);if(Number(process.env.AKIS_SUBTITLE_RATE||1)===1)assert.ok(cue.time-cue.start<.5,'Late rendered subtitle '+t); }
assert.ok(!linear.errors.some(x=>x.fatal),'Fatal HLS error');
await page.evaluate(async()=>{const v=document.querySelector('#video');v.pause();await api('/pause',{body:{sid:state.player.sessionId,paused:true}});});
const paused=await page.evaluate(()=>document.querySelector('#video').currentTime);
await new Promise(resolve=>setTimeout(resolve,500));
assert.ok(Math.abs(await page.evaluate(()=>document.querySelector('#video').currentTime)-paused)<.1);
await page.evaluate(async()=>{await api('/pause',{body:{sid:state.player.sessionId,paused:false}});await document.querySelector('#video').play();});
await page.evaluate(()=>start(280));
await page.waitForFunction(()=>seen.some(x=>x.epoch===2&&x.text==='CUE_300'),{},{timeout:30000});
await page.evaluate(()=>start(0));
await page.waitForFunction(()=>seen.some(x=>x.epoch===3&&x.text==='CUE_8'),{},{timeout:30000});
const proof={success:true,engine:native?'native-webkit':useWebkit?'webkit-hlsjs':'chromium-hlsjs',playbackRate:Number(process.env.AKIS_SUBTITLE_RATE||1),linearTimelineSeconds:linear.time,renderedCues:expected.length,maxCueClockErrorSeconds:Math.max(...linear.seen.map(x=>Math.abs(Number(x.text.slice(4))-x.start))),longSilentGap:true,rollingCache:true,pause:true,forwardRestart:true,backwardRestart:true,fatalErrors:linear.errors.filter(x=>x.fatal)};
if(process.env.AKIS_SUBTITLE_PROOF)fs.writeFileSync(process.env.AKIS_SUBTITLE_PROOF,JSON.stringify(proof,null,2)+'\n');
console.log(JSON.stringify(proof,null,2));

} finally {await browser?.close();if(server.exitCode===null&&server.signalCode===null){server.kill('SIGTERM');await new Promise(resolve=>server.once('close',resolve));}}
})().catch(e=>{console.error(e);process.exitCode=1});
