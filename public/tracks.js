'use strict';
// Source tracks are selected on this device; HLS rendition/native tracks switch in
// the browser. Both paths use the same controls and per-content preferences.
window.VrelioTracks = (() => {
  let current = null, busy = false;
  const el = id => document.getElementById(id);
  const languageNames = {tur:'Türkçe',tr:'Türkçe',eng:'İngilizce',en:'İngilizce',deu:'Almanca',ger:'Almanca',de:'Almanca',fra:'Fransızca',fre:'Fransızca',fr:'Fransızca',ara:'Arapça',ar:'Arapça',spa:'İspanyolca',es:'İspanyolca',ita:'İtalyanca',it:'İtalyanca',rus:'Rusça',ru:'Rusça',jpn:'Japonca',ja:'Japonca',kor:'Korece',ko:'Korece',por:'Portekizce',pt:'Portekizce',nld:'Felemenkçe',dut:'Felemenkçe',nl:'Felemenkçe',pol:'Lehçe',pl:'Lehçe',zho:'Çince',chi:'Çince',zh:'Çince',aze:'Azerice',az:'Azerice',kur:'Kürtçe',ku:'Kürtçe',ell:'Yunanca',gre:'Yunanca',el:'Yunanca',fas:'Farsça',per:'Farsça',fa:'Farsça',hin:'Hintçe',hi:'Hintçe',ukr:'Ukraynaca',uk:'Ukraynaca',und:'Dil belirtilmemiş'};
  const titleLangHints = [
    [/\b(t[uü]rk[cç]e|turkish|\btr\b|dublaj)\b/i,'tur'],
    [/\b(ingilizce|english|\beng?\b|original|orijinal)\b/i,'eng'],
    [/\b(almanca|german|deutsch|\bdeu\b|\bger\b)\b/i,'deu'],
    [/\b(frans[ıi]zca|french|fran[cç]ais|\bfra\b|\bfre\b)\b/i,'fra'],
    [/\b(rus[cç]a|russian|\brus\b)\b/i,'rus'],
    [/\b(arap[cç]a|arabic|\bara\b)\b/i,'ara'],
    [/\b(ispanyolca|spanish|espa[nñ]ol|\bspa\b)\b/i,'spa'],
    [/\b(italyanca|italian|italiano|\bita\b)\b/i,'ita'],
    [/\b(japonca|japanese|\bjpn\b)\b/i,'jpn'],
    [/\b(korece|korean|\bkor\b)\b/i,'kor'],
    [/\b(portekizce|portuguese|\bpor\b)\b/i,'por'],
    [/\b(azerice|azerbaijani|\baze\b)\b/i,'aze'],
    [/\b(k[uü]rt[cç]e|kurdish|\bkur\b)\b/i,'kur'],
  ];
  function inferLangCode(rawCode, title) {
    const clean = String(rawCode || 'und').trim().toLowerCase();
    if (clean && !['und','unk','unknown','mul','zxx'].includes(clean)) return clean;
    const text = String(title || '');
    for (const [pattern, iso] of titleLangHints) {
      if (pattern.test(text)) return iso;
    }
    return clean || 'und';
  }
  function label(track,index,kind) {
    const title=track.title||track.name||track.label||'';
    const code=inferLangCode(track.language||track.lang||'und', title);
    let language=languageNames[code];
    if(!language){try{language=new Intl.DisplayNames(['tr'],{type:'language'}).of(code);}catch{} }
    const parts=[language||code];
    if(title&&String(title).toLowerCase()!==String(parts[0]).toLowerCase())parts.push(title);
    if(track.channels)parts.push(track.channels);
    if(track.codec)parts.push(String(track.codec).toUpperCase());
    if(track.forced)parts.push('Zorunlu');
    if(track.hearingImpaired)parts.push('İşitme engelliler için');
    if(track.default)parts.push('Varsayılan');
    if(track.bitmap)parts.push('Görüntü altyazısı');
    return `${index+1}. ${parts.join(' · ')}`;
  }
  function clientTracks(player,kind) {
    const video=document.querySelector('#video');
    const hls=state.hls;
    if(player.mode==='direct') {
      const list=kind==='audio'?hls?.audioTracks:hls?.subtitleTracks;
      if(list?.length)return Array.from(list,(track,i)=>({...track,id:`hls:${i}`,index:i}));
      const native=kind==='audio'?video?.audioTracks:video?.textTracks;
      if(native?.length)return Array.from(native,(track,i)=>({id:`native:${i}`,index:i,language:track.language||'und',title:track.label||'',kind:track.kind})).filter(track=>kind==='audio'||['subtitles','captions',''].includes(track.kind));
    }
    return Array.from(player.tracks?.[kind==='audio'?'audio':'subtitles']||[]);
  }
  function selected(player,kind,list) {
    const pref=player.selection||{};
    const native=list[0]?.id?.startsWith('hls:')||list[0]?.id?.startsWith('native:');
    const saved=native?pref[kind==='audio'?'clientAudio':'clientSubtitle']:pref[kind==='audio'?'audio':'subtitle'];
    const fallback=kind==='audio'?'auto':'off';
    return list.some(track=>track.id===saved)?saved:fallback;
  }
  function render(player=current) {
    if(!player||state.player!==player||!el('audioTrackSelect'))return;
    for(const kind of ['audio','subtitle']){
      const select=el(kind==='audio'?'audioTrackSelect':'subtitleTrackSelect');
      const list=clientTracks(player,kind);
      const initial=kind==='audio'?'auto':'off';
      const title=kind==='audio'?'Varsayılan ses':'Kapalı';
      select.innerHTML=`<option value="${initial}">${title}</option>`+list.map((track,i)=>`<option value="${esc(track.id)}">${esc(label(track,i,kind))}</option>`).join('');
      select.value=selected(player,kind,list);
      select.disabled=busy||!player.sessionId||!list.length;
    }
    const a=clientTracks(player,'audio').length,s=clientTracks(player,'subtitle').length;
    const status=el('trackStatus');
    if(status)status.textContent=busy?'Seçtiğin parçalar hazırlanıyor…':!player.sessionId?'Ses ve altyazı seçenekleri okunuyor…':!player.tracks?.scanned&&!a&&!s?'Kaynak parça listesi okunamadı. Yeniden taramayı deneyebilirsin.':`${a} ses · ${s} altyazı seçeneği${s?'':' · Bu kaynakta ek altyazı yok.'}`;
    const refresh=el('refreshTracks');if(refresh)refresh.disabled=busy||!player.sessionId||!state.status?.ffmpeg;
  }
  function applyNative(player) {
    if(state.player!==player)return;
    const video=document.querySelector('#video'),hls=state.hls;
    for(const kind of ['audio','subtitle']){
      const list=clientTracks(player,kind),value=selected(player,kind,list);
      if(player.mode!=='direct'){
        if(kind==='subtitle'&&player.selection?.subtitle!=='off'&&hls?.subtitleTracks?.length){hls.subtitleTrack=0;hls.subtitleDisplay=true;}
        if(kind==='subtitle'&&!hls){
          // Safari/WebKit uses native HLS rather than hls.js. The generated
          // rendition contains only the selected source subtitle, and its
          // native TextTrack can be disabled when the media is reloaded.
          let shown=false;
          for(const track of Array.from(video.textTracks||[])){
            if(!['subtitles','captions'].includes(track.kind))continue;
            const show=player.selection?.subtitle&&player.selection.subtitle!=='off'&&!shown;
            track.mode=show?'showing':'disabled';
            shown=shown||show;
          }
        }
        continue;
      }
      if(list[0]?.id?.startsWith('hls:')){
        if(kind==='audio'){if(value.startsWith('hls:'))hls.audioTrack=Number(value.split(':')[1]);else if(hls.audioTracks?.length)hls.audioTrack=0;}
        else{hls.subtitleTrack=value.startsWith('hls:')?Number(value.split(':')[1]):-1;hls.subtitleDisplay=value!=='off';}
      }else if(list[0]?.id?.startsWith('native:')){
        const tracks=kind==='audio'?video.audioTracks:video.textTracks;
        for(let i=0;i<tracks.length;i++){
          if(kind==='audio')tracks[i].enabled=value==='auto'?i===0:value===`native:${i}`;
          else if(['subtitles','captions',''].includes(tracks[i].kind))tracks[i].mode=value===`native:${i}`?'showing':'disabled';
        }
      }
    }
    render(player);
  }
  function options(player) {
    const result={audioTrack:player.selection?.audio||'auto',subtitleTrack:player.selection?.subtitle||'off'};
    for(const kind of ['audio','subtitle']){
      const list=clientTracks(player,kind),value=selected(player,kind,list);
      if(value.startsWith('hls:')||value.startsWith('native:')){
        const chosen=list.find(track=>track.id===value);
        const backend=player.tracks?.[kind==='audio'?'audio':'subtitles']||[];
        const match=backend.find(track=>chosen&&(track.language||'und')===(chosen.language||chosen.lang||'und'));
        if(match)result[kind==='audio'?'audioTrack':'subtitleTrack']=match.id;
      }
    }
    return result;
  }
  async function restart(player,changes={}) {
    if(state.player!==player||busy)return;
    const video=document.querySelector('#video');
    const position=player.item.kind==='live'?0:player.ready?(Number(video.currentTime)||0)+player.offset:player.start;
    const paused=video.paused===true;
    busy=true;render(player);
    try{await playItem(player.id,player.mode,position,false,{...options(player),...changes,paused});}
    finally{busy=false;if(state.player)render(state.player);}
  }
  async function change(kind,value) {
    const player=current;if(!player||state.player!==player||busy)return;
    const list=clientTracks(player,kind),client=list[0]?.id?.startsWith('hls:')||list[0]?.id?.startsWith('native:');
    if(client){
      const key=kind==='audio'?'clientAudio':'clientSubtitle';
      const old=player.selection[key];player.selection[key]=value;applyNative(player);
      try{await api('/api/track-preferences',{method:'POST',body:{id:player.id,[key]:value}});}
      catch(error){player.selection[key]=old;applyNative(player);notify(error.message,true);}
    }else{await restart(player,{[kind==='audio'?'audioTrack':'subtitleTrack']:value});}
  }
  function syncExternalSubtitles(externalList) {
    const video=document.querySelector('#video');
    if(!video?.querySelectorAll)return;
    video.querySelectorAll('track[data-sidecar="1"]').forEach(el=>el.remove());
    for(const sub of externalList||[]){
      if(!sub?.url||!document.createElement)continue;
      const tr=document.createElement('track');
      tr.kind='subtitles';
      tr.label=sub.title||'Harici Altyazı';
      tr.srclang=sub.language||'tr';
      tr.src=sub.url;
      tr.dataset.sidecar='1';
      video.appendChild(tr);
    }
  }
  function reset(player){current=player;player.tracks={audio:[],subtitles:[],scanned:false};player.selection={audio:'auto',subtitle:'off'};syncExternalSubtitles([]);render(player);}
  function ready(player,result){if(state.player!==player)return;current=player;player.tracks=result.tracks||{audio:[],subtitles:[],scanned:false};player.selection=result.selection||{audio:'auto',subtitle:'off'};syncExternalSubtitles(result.externalSubtitles||[]);render(player);}
  function bindHls(player,hls){
    for(const key of ['AUDIO_TRACKS_UPDATED','SUBTITLE_TRACKS_UPDATED','MANIFEST_PARSED']){
      const name=Hls.Events[key];if(name)hls.on(name,()=>{if(state.player===player)applyNative(player);});
    }
  }
  function bind(){
    el('audioTrackSelect')?.addEventListener('change',event=>change('audio',event.target.value).catch(error=>notify(error.message,true)));
    el('subtitleTrackSelect')?.addEventListener('change',event=>change('subtitle',event.target.value).catch(error=>notify(error.message,true)));
    el('refreshTracks')?.addEventListener('click',()=>current&&restart(current,{refreshTracks:true}).catch(error=>notify(error.message,true)));
    const video=document.querySelector('#video');
    for(const name of ['loadedmetadata','playing'])video?.addEventListener(name,()=>current&&applyNative(current));
    for(const list of [video?.audioTracks,video?.textTracks]){
      list?.addEventListener?.('addtrack',()=>current&&applyNative(current));
      list?.addEventListener?.('removetrack',()=>current&&render(current));
    }
  }
  return {bind,reset,ready,bindHls,options,render,label,change};
})();
