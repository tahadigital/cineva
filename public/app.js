'use strict';
const icons={sports:'<path d="M8 21h8m-4-4v4M7 4h10v7a5 5 0 0 1-10 0V4ZM7 6H3v2a4 4 0 0 0 4 4m10-6h4v2a4 4 0 0 1-4 4"/>',home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',live:'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m8 2 4 3 4-3M8 22h8"/><path d="m10 9 5 3-5 3z"/>',film:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4M7 12h10"/>',series:'<rect x="3" y="8" width="18" height="13" rx="2"/><path d="M6 4h12M9 1h6m-4 11 5 3-5 3z"/>',heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0l-1 1-1-1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',list:'<path d="M8 6h13M8 12h13M8 18h9M3 6h.01M3 12h.01M3 18h.01"/>',settings:'<path d="m9.5 3-.7 2-2 .9-2-.5-2 3.4 1.4 1.5v2.4L3 14.2l2 3.4 2-.5 2 .9.7 2h4.1l.7-2 2-.9 2 .5 2-3.4-1.4-1.5v-2.4L21 8.8l-2-3.4-2 .5-2-.9-.7-2z"/><circle cx="12" cy="11.5" r="3"/>',search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 6.1A8 8 0 0 1 20 12M4 12a8 8 0 0 0 13.9 5.9"/>',chevronRight:'<path d="m9 5 7 7-7 7"/>',chevronLeft:'<path d="m15 5-7 7 7 7"/>',close:'<path d="m6 6 12 12M6 18 18 6"/>',play:'<path d="m8 4 12 8-12 8z"/>',plus:'<path d="M12 5v14M5 12h14"/>',more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',star:'<path d="m12 2 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z"/>',arrowUp:'<path d="m6 12 6-6 6 6M12 6v14"/>',arrowDown:'<path d="m6 12 6 6 6-6M12 4v14"/>',trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',edit:'<path d="m15 4 5 5M3 21l5-1L21 7a3.5 3.5 0 0 0-5-5L3 15z"/>',download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',upload:'<path d="M12 16V4m-5 5 5-5 5 5M4 16v5h16v-5"/>',check:'<path d="m5 12 4 4L19 6"/>',alert:'<path d="m12 3 10 18H2zM12 9v5M12 17h.01"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',expand:'<path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5"/>',link:'<path d="m10 13 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0"/>',shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>',copy:'<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',logout:'<path d="M9 3H4v18h5M13 8l5 4-5 4M8 12h10"/>',volumeOn:'<path d="M3 9v6h4l5 4V5L7 9H3m13 0a4 4 0 0 1 0 6m3-9a8 8 0 0 1 0 12"/>',volumeOff:'<path d="M3 9v6h4l5 4V5L7 9H3m13 1 5 5m0-5-5 5"/>'};
const icon=name=>`<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name]||icons.film}</svg>`;
const $=selector=>document.querySelector(selector);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=new Intl.NumberFormat('tr-TR');
const kindNames={live:'Canlı TV',vod:'Film',series:'Dizi',episode:'Bölüm'};
const state={status:null,cloudStatus:null,route:'home',params:new URLSearchParams(),renderId:0,items:new Map(),detail:null,playlists:[],player:null,hls:null,progressTimer:null,pingTimer:null,syncTimer:null,searchTimer:null,playGeneration:0,playClient:Date.now().toString(36)+Math.random().toString(36).slice(2),seekTimer:null,waitingTimer:null,playbackRate:1,videoCover:false,sleepTimer:null,sleepUntil:0,osdTimer:null,multiHls:[],multiSids:[]};
function hydrateIcons(root=document){root.querySelectorAll('[data-icon]').forEach(el=>{el.innerHTML=icon(el.dataset.icon);});}
async function api(path,options={}){const init={...options,headers:{...(options.body?{'Content-Type':'application/json'}:{}),...(options.headers||{})}};if(init.body&&typeof init.body!=='string')init.body=JSON.stringify(init.body);const response=await fetch(path,init);let data;try{data=await response.json();}catch{throw new Error('Sunucudan geçerli bir yanıt alınamadı. Mavie uygulamasının açık olduğundan emin ol.');}if(!response.ok){if(response.status===401&&state.status?.authorized){state.status.authorized=false;render();}const error=new Error(data.error||`İşlem tamamlanamadı (${response.status}).`);error.status=response.status;error.mode=data.mode;error.code=data.code;error.verificationRequired=data.verificationRequired;error.upgradeRequired=data.upgradeRequired;error.email=data.email;throw error;}return data;}
function remember(items){for(const item of items||[])if(item?.id){if(state.items.has(item.id))state.items.delete(item.id);else if(state.items.size>=5000)state.items.delete(state.items.keys().next().value);state.items.set(item.id,item);}return items||[];}
function itemFor(id){return state.items.get(id);}
function notify(message,error=false){const toast=document.createElement('div');toast.className=`toast${error?' error':''}`;toast.innerHTML=icon(error?'alert':'check')+`<span>${esc(message)}</span>`;$('#toastRegion').append(toast);setTimeout(()=>toast.remove(),6000);}
function button(label,action,extra='',style='secondary'){return `<button class="button ${style}" data-action="${action}" ${extra}>${label}</button>`;}
function empty(title,description,iconName='film',action=''){return `<div class="empty-state"><div class="empty-icon">${icon(iconName)}</div><h2>${esc(title)}</h2><p>${esc(description)}</p>${action}</div>`;}
function loading(stageText='Kütüphanen, afişler ve yayın akışı hazırlanıyor…'){return `<section class="loading-panel-banner" role="status" aria-live="polite"><div class="cinema-eq" aria-hidden="true"><span></span><span></span><span></span><span></span></div><div class="loading-panel-copy"><strong>Sahne Hazırlanıyor</strong><p>${esc(stageText)}</p><div class="loading-progress-bar" aria-hidden="true"><span></span></div></div></section><div class="loading-grid">${Array.from({length:12},(_,i)=>`<div class="skeleton" style="--sk-delay:${i*55}ms"><span class="skeleton-bar-title"></span><span class="skeleton-bar-meta"></span></div>`).join('')}</div>`;}
function count(value){return fmt.format(Number(value)||0);}
function time(seconds){seconds=Math.max(0,Math.floor(Number(seconds)||0));const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),s=seconds%60;return h?`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${m}:${String(s).padStart(2,'0')}`;}
function minutes(seconds){return `${Math.max(1,Math.round((Number(seconds)||0)/60))} dk`;}
function date(value){if(!value)return 'Bilinmiyor';const d=new Date(/^\d+$/.test(String(value))?Number(value)*(Number(value)<1e12?1000:1):value);return Number.isNaN(d.getTime())?String(value):new Intl.DateTimeFormat('tr-TR',{day:'numeric',month:'long',year:'numeric'}).format(d);}
function imageUrl(url){if(!url||!/^https?:\/\//i.test(url))return '';return `/api/image?url=${encodeURIComponent(url)}`;}
function fallback(item){const hue=[...String(item.name||'')].reduce((n,c)=>n+c.charCodeAt(0),0)%360;return `<div class="poster-fallback" style="--hue:${hue}">${icon(item.kind==='live'?'live':item.kind==='series'?'series':'film')}<span>${esc(item.name||'İsimsiz içerik')}</span><small>${esc(kindNames[item.kind]||'MAVIE')}</small></div>`;}
function art(item,extra=''){const url=imageUrl(item.poster);return fallback(item)+(url?`<img src="${esc(url)}" alt="" loading="lazy" decoding="async" ${extra} data-poster>`:'');}
function progressPercent(item){const p=item.progress;return p?.duration?Math.max(0,Math.min(100,p.position/p.duration*100)):0;}
function card(item){remember([item]);if(item.kind==='live')return liveCard(item);const year=item.year?String(item.year):'';return `<article class="media-card"><button class="poster-button" data-action="detail" data-id="${esc(item.id)}" aria-label="${esc(item.name)} ayrıntıları">${art(item)}<span class="poster-shade"></span><span class="poster-play">${icon(item.kind==='series'?'series':'play')}</span><span class="card-badges">${Number(item.rating)>0?`<span class="badge rating">${icon('star')}${esc(Number(item.rating).toFixed(1))}</span>`:''}${item.progress?.completed?'<span class="badge">İZLENDİ</span>':''}</span>${item.progress?.position?`<span class="progress-track"><span style="width:${progressPercent(item)}%"></span></span>`:''}</button><button class="card-favorite ${item.favorite?'active':''}" data-action="favorite" data-id="${esc(item.id)}" title="${item.favorite?'Favorilerden kaldır':'Favorilere ekle'}" aria-label="${item.favorite?'Favorilerden kaldır':'Favorilere ekle'}">${icon('heart')}</button><div class="card-title-row"><button class="card-title" data-action="detail" data-id="${esc(item.id)}">${esc(item.name)}</button><button class="card-more" data-action="item-menu" data-id="${esc(item.id)}" aria-label="${esc(item.name)} seçenekleri">${icon('more')}</button></div><div class="card-meta">${year?`<span>${esc(year)}</span><span class="meta-dot"></span>`:''}<span class="meta-category">${esc(item.categoryName||kindNames[item.kind]||'Kütüphane')}</span></div></article>`;}
function liveCard(item){remember([item]);return `<article class="live-card"><span class="badge live">CANLI</span><button class="card-favorite ${item.favorite?'active':''}" data-action="favorite" data-id="${esc(item.id)}" title="Favori" aria-label="${item.favorite?'Favorilerden kaldır':'Favorilere ekle'}">${icon('heart')}</button><button class="live-logo" style="border:0;background:none;padding:0" data-action="detail" data-id="${esc(item.id)}" aria-label="${esc(item.name)} ayrıntıları">${art(item)}</button><h3 class="live-card-title">${esc(item.name)}</h3><div class="live-card-category">${esc(item.categoryName||'Canlı yayın')}</div><button class="button secondary" data-action="play" data-id="${esc(item.id)}">${icon('play')}Yayını aç</button></article>`;}
function grid(items,kind){return `<div class="${kind==='live'?'live-grid':'poster-grid'}">${items.map(card).join('')}</div>`;}
function resumeCard(item){
  remember([item]);
  const p=item.progress||{},next=item.continueReason==='nextEpisode';
  const episode=item.kind==='episode'?[item.season?`${item.season}. Sezon`:'',item.episode?`${item.episode}. Bölüm`:''].filter(Boolean).join(' · '):'';
  const action=next?'Sonraki bölümden devam et':episode?`${episode}e devam et`:'İzlemeye devam et';
  const status=next?[action,episode].filter(Boolean).join(' · '):[episode?action:'',`${time(p.position)} izlendi${p.duration?` · ${minutes(Math.max(0,p.duration-p.position))} kaldı`:''}`].filter(Boolean).join(' · ');
  return `<article class="resume-card"><div class="resume-art">${art(item)}<button class="resume-play" data-action="play" data-id="${esc(item.id)}" aria-label="${esc(item.name)} · ${esc(action)}"><span>${icon('play')}</span></button>${p.position&&!p.completed?`<span class="progress-track"><span style="width:${progressPercent(item)}%"></span></span>`:''}</div><div class="resume-info"><button class="card-more" data-action="item-menu" data-id="${esc(item.id)}" aria-label="İzleme seçenekleri">${icon('more')}</button><strong>${esc(item.seriesName||item.name)}</strong><small>${esc(status)}</small></div></article>`;
}
function pageHeading(title,subtitle,eyebrow='',actions=''){return `<div class="page-heading"><div>${eyebrow?`<span class="eyebrow">${esc(eyebrow)}</span>`:''}<h1>${esc(title)}</h1>${subtitle?`<p>${esc(subtitle)}</p>`:''}</div>${actions}</div>`;}
function section(title,items,kind,link,subtitle=''){return `<section class="section"><div class="section-heading"><div><h2>${esc(title)}</h2>${subtitle?`<p class="discovery-subtitle">${esc(subtitle)}</p>`:''}</div>${link?`<a class="text-button" href="#${link}">Tümünü gör ${icon('chevronRight')}</a>`:''}</div>${grid(items,kind)}</section>`;}
function syncBanner(){const catalog=state.status?.catalog;if(catalog?.syncing)return `<div class="sync-banner"><div class="cinema-eq small" aria-hidden="true"><span></span><span></span><span></span><span></span></div><span class="spinner"></span><span>Kütüphanen eşitleniyor · Kanal, film, dizi ve ses/altyazı bilgileri güncelleniyor…</span></div>`;if(catalog?.error)return `<div class="sync-banner error">${icon('alert')}<span>${esc(catalog.error)}</span><button class="text-button" data-action="sync">Tekrar dene</button></div>`;return '';}
function routeTo(route,params={}){const query=new URLSearchParams(Object.entries(params).filter(([,v])=>v!==''&&v!=null));location.hash=route+(query.size?'?'+query.toString():'');}
function updateShell(){const status=state.status;const route=state.route;if(route!=='multiview'&&typeof clearMultiView==='function')clearMultiView();document.querySelectorAll('[data-route]').forEach(el=>el.classList.toggle('active',el.dataset.route===route||(route.startsWith('playlists/')&&el.dataset.route==='playlists')));const names={home:'Mavie Kütüphanesi',live:'Kütüphane / Canlı TV',multiview:'Mavie / Çoklu Ekran',sports:'Canlı Yayın & EPG Rehberi',vod:'Kütüphane / Filmler',series:'Kütüphane / Diziler',favorites:'Kütüphanem / Favoriler',playlists:'Kütüphanem / Listelerim',settings:'Mavie / Ayarlar',search:'Kütüphane / Arama'};$('#breadcrumb').textContent=names[route]||'Kütüphanem / Listelerim';const prof=status?.profile;if(prof){const initEl=$('#profileInitial');if(initEl){initEl.textContent=(prof.name||'A').trim().charAt(0).toUpperCase();if(initEl.style)initEl.style.background=prof.avatarColor||'#7C3AED';}const av=$('#profileAvatarBtn');if(av){av.title=`Profil: ${prof.name}${prof.isKids?' (Çocuk)':''}`;}};$('#connectionName').textContent=status?.configured?(status.connection?.name||'Medya Kaynağı'):'Bağlantı bekleniyor';$('#connectionCaption').textContent=status?.catalog?.syncing?'Kütüphane eşitleniyor':status?.catalog?.error?'Bağlantıyı kontrol et':status?.configured?'Kişisel sunucun bağlı':'Ayarlarla başlayalım';$('#connectionLight').className=`connection-light ${status?.configured&&!status?.catalog?.error?'ready':status?.catalog?.error?'error':''}`;$('#footerStatus').textContent=status?.catalog?.updatedAt?`Son eşitleme · ${date(status.catalog.updatedAt)}`:'Bu cihazda çalışıyor';$('#syncButton').classList.toggle('syncing-icon',!!status?.catalog?.syncing);$('#syncButton').disabled=!status?.authorized||!status?.configured||!!status?.catalog?.syncing;const query=state.params.get('q')||'';if(document.activeElement!==$('#searchInput'))$('#searchInput').value=query;document.title=`${route==='home'?'Kütüphane':({live:'Canlı TV',multiview:'Çoklu Ekran',sports:'Yayın Rehberi',vod:'Filmler',series:'Diziler',favorites:'Favoriler',playlists:'Listelerim',settings:'Ayarlar',search:'Arama'}[route]||'Listem')} · Mavie`;}
async function render(){const token=++state.renderId;const hash=location.hash.slice(1)||'home';const split=hash.indexOf('?');state.route=split<0?hash:hash.slice(0,split);state.params=new URLSearchParams(split<0?'':hash.slice(split+1));updateShell();if(!state.status?.authorized){renderPairing();return;}if(!state.status.configured&&!['settings','sports'].includes(state.route)){renderSetup();return;}const main=$('#main');try{if(state.route==='sports'){await window.MavieSports.render(main,state.params,()=>token===state.renderId);return;}if(state.route==='multiview'){await renderMultiView(token);return;}if(state.route==='settings'){renderSettings();return;}if(state.route==='home'){main.innerHTML=loading();const data=await api('/api/home');if(token!==state.renderId)return;renderHome(data);return;}if(['live','vod','series'].includes(state.route)){main.innerHTML=pageHeading({live:'Canlı TV',vod:'Filmler',series:'Diziler'}[state.route],'Kütüphanen yükleniyor…','KENDİ EKRANIN')+loading();const data=await api(`/api/catalog?${new URLSearchParams({kind:state.route,q:state.params.get('q')||'',category:state.params.get('category')||'',sort:state.params.get('sort')||'recent',page:state.params.get('page')||'1',limit:'48'})}`);if(token!==state.renderId)return;renderCatalog(data);return;}if(state.route==='favorites'){main.innerHTML=loading();const data=await api('/api/favorites');if(token!==state.renderId)return;renderFavorites(data.items||[]);return;}if(state.route==='playlists'||state.route.startsWith('playlists/')){main.innerHTML=loading();const data=await api('/api/playlists');if(token!==state.renderId)return;state.playlists=data.playlists||[];renderPlaylists();return;}if(state.route==='search'){main.innerHTML=loading();const q=state.params.get('q')||'';const results=await Promise.all(['vod','series','live'].map(kind=>api(`/api/catalog?${new URLSearchParams({kind,q,limit:'18',page:'1'})}`).then(data=>({...data,kind}))));if(token!==state.renderId)return;renderSearch(q,results);return;}routeTo('home');}catch(error){if(token===state.renderId)main.innerHTML=empty('Bağlantı kurulamadı',error.message,'alert',button('Yeniden dene','reload'));}}
const featuredDetails = new Map();
function homeRail(title, items, renderer, link = '', subtitle = '') {
  if (!items.length) return '';
  return `<section class="section cinema-rail">
    <div class="section-heading"><h2>${esc(title)}</h2>${subtitle?`<p class="discovery-subtitle">${esc(subtitle)}</p>`:''}
      ${link ? `<a href="#${link}" class="text-button">Tümünü gör ${icon('chevronRight')}</a>` : ''}
    </div>
    <div class="rail-frame">
      <div class="rail-strip" tabindex="0" role="group" aria-label="${esc(title)}">${items.map(renderer).join('')}</div>
      ${items.length > 1 ? `
        <button type="button" class="rail-arrow rail-prev" data-rail-step="-1" aria-label="${esc(title)} önceki içerikler" hidden>${icon('chevronLeft')}</button>
        <button type="button" class="rail-arrow rail-next" data-rail-step="1" aria-label="${esc(title)} sonraki içerikler" hidden>${icon('chevronRight')}</button>` : ''}
    </div>
  </section>`;
}
function featuredDescription(item) {
  return String(item.plot || '').trim() || (item.kind === 'series'
    ? 'Sezonları ve bölümleri keşfet.'
    : item.progress?.position ? 'İzlemeye kaldığın yerden devam et.' : 'Kütüphanene yeni eklenen filmlerden.');
}
function featuredArt(item) {
  const backdrop = imageUrl(item.backdrop);
  const poster = imageUrl(item.poster);
  return backdrop
    ? `<img class="cinema-backdrop" src="${esc(backdrop)}" alt="" decoding="async" fetchpriority="high">`
    : poster
      ? `<img class="cinema-portrait" src="${esc(poster)}" alt="" decoding="async" fetchpriority="high">`
      : '';
}
function featuredTitle(item) {
  return String(item.name || '').replace(/\s*\|\s*(?:19|20)\d{2}\s*\|.*$/, '').trim() || item.name;
}
function featuredHero(item) {
  const label = item.kind === 'series' ? 'DİZİ' : 'FİLM';
  const action = `data-id="${esc(item.id)}"`;
  const details = button(`<span class="info-symbol" aria-hidden="true">i</span>Daha Fazla Bilgi`, 'detail', action, 'secondary');
  const start = item.kind === 'series'
    ? button(icon('series') + 'Bölümler', 'detail', action, '')
    : button(icon('play') + (item.progress?.position ? 'Devam Et' : 'Oynat'), 'play', action, '');
  return `<section class="hero cinema-hero" data-featured="${esc(item.id)}">
    <div class="cinema-art" aria-hidden="true">${featuredArt(item)}</div>
    <div class="hero-copy">
      <div class="cinema-kicker"><img src="/mavie-mark.svg" alt="" aria-hidden="true">${label}</div>
      <h1>${esc(featuredTitle(item))}</h1>
      <div class="cinema-meta">${[item.year, item.genre, item.duration > 0 ? minutes(item.duration) : ''].filter(Boolean).map(esc).join('  ·  ')}</div>
      <p>${esc(featuredDescription(item))}</p>
      <div class="hero-actions">${start}${item.kind === 'series' ? '' : details}</div>
    </div>
  </section>`;
}
function hydrateFeatured(item) {
  if (!item || item.backdrop && item.plot) return;
  const known = featuredDetails.get(item.id);
  if (known && Date.now() - known.time < 15 * 60 * 1000) return;
  featuredDetails.set(item.id, {time: Date.now(), info: null});
  api(`/api/items/${encodeURIComponent(item.id)}`).then(({item: details, info}) => {
    const enriched = {...item, ...details, ...info};
    featuredDetails.set(item.id, {time: Date.now(), info: enriched});
    const hero = [...document.querySelectorAll('#main .cinema-hero[data-featured]')].find(el => el.dataset.featured === item.id);
    if (!hero) return;
    const backdrop = imageUrl(enriched.backdrop);
    if (backdrop) {
      const img = new Image();
      img.className = 'cinema-backdrop';
      img.alt = '';
      img.onload = () => { if (hero.isConnected) hero.querySelector('.cinema-art').replaceChildren(img); };
      img.src = backdrop;
    }
    hero.querySelector('.hero-copy p').textContent = featuredDescription(enriched);
    hero.querySelector('.cinema-meta').textContent = [enriched.year, enriched.genre, enriched.duration > 0 ? minutes(enriched.duration) : ''].filter(Boolean).join('  ·  ');
  }).catch(() => { /* Existing poster and copy stay available if provider metadata is offline. */ });
}
function discoveryShowcase(items){
  remember(items);
  return `<section class="discovery-showcase" aria-label="Yeni çıkanlar vitrini"><div class="discovery-heading"><span>YENİ ÇIKANLAR</span><span>Film ve dizilerden güncel keşifler</span></div>${items.map((item,index)=>`<div class="showcase-slide" data-slide="${index}" ${index?'hidden':''}>${featuredHero({...item, ...featuredDetails.get(item.id)?.info})}</div>`).join('')}<div class="showcase-tabs" role="group" aria-label="Vitrin seçimi">${items.map((item,index)=>`<button data-showcase="${index}" aria-pressed="${!index}" aria-label="${esc(item.name)} kapağını göster">${index+1}<span>${esc(item.name)}</span></button>`).join('')}</div></section>`;
}
function renderHome(data) {
  const discovery=data.discovery||{};
  const showcase=remember(discovery.showcase||[]);
  const shelves=discovery.shelves||[];
  shelves.forEach(shelf=>remember(shelf.items||[]));
  const recent = remember(data.recent || []);
  const favorites = remember(data.favorites || []);
  const continuing = remember(data.continueWatching || []);
  const films = recent.filter(item => item.kind === 'vod');
  const series = recent.filter(item => item.kind === 'series');
  const heroItem = [...films, ...series].find(item => imageUrl(item.poster) && item.rating >= 5)
    || [...films, ...series].find(item => imageUrl(item.poster))
    || films[0] || series[0];
  const activeHero = showcase[0] || heroItem;
  const main = $('#main');
  const banner = syncBanner();
  const signature = JSON.stringify([banner, data]);
  if (main.dataset.cinemaSignature === signature && main.querySelector('.cinema-hero')) {
    hydrateFeatured(activeHero);
    return;
  }
  const railPositions = new Map([...main.querySelectorAll('.rail-strip')].map(rail => [rail.getAttribute('aria-label'), rail.scrollLeft]));
  main.dataset.cinemaSignature = signature;
  main.innerHTML = banner + (showcase.length?discoveryShowcase(showcase):heroItem ? featuredHero({...heroItem, ...featuredDetails.get(heroItem.id)?.info}) : `
    <section class="hero cinema-hero cinema-hero-empty">
      <div class="cinema-art" aria-hidden="true"></div>
      <div class="hero-copy"><div class="cinema-kicker"><img src="/mavie-mark.svg" alt="" aria-hidden="true">MAVIE</div>
        <h1>Ne izlemek istersin?</h1>
        <p>Kendi arşivlerin, filmler, diziler ve canlı yayınlar.</p>
        <div class="hero-actions">
          ${button(icon('refresh') + 'Kütüphaneyi Eşitle', 'sync', '', '')}
          <a class="button secondary" href="#sports">Yayın Rehberi</a>
        </div>
      </div>
    </section>`)
    + homeRail('İzlemeye Devam Et', continuing.slice(0, 12), resumeCard)
    + shelves.map(shelf=>homeRail(shelf.title,shelf.items,card,'',shelf.subtitle)).join('')
    + homeRail('Kütüphanene Yeni Eklenen Filmler', films, card, 'vod')
    + homeRail('Kütüphanene Yeni Eklenen Diziler', series, card, 'series')
    + homeRail('Favorilerim', favorites.slice(0, 12), card, 'favorites')
    + '<p class="discovery-credit">Keşif: Yalnızca kütüphanendeki kayıtlar ve yerel izleme geçmişin üzerinden hazırlanır. Mavie medya içeriği barındırmaz.</p>';
  main.querySelectorAll('[data-showcase]').forEach(button=>button.addEventListener('click',()=>{
    main.querySelectorAll('[data-slide]').forEach(slide=>{slide.hidden=slide.dataset.slide!==button.dataset.showcase;});
    main.querySelectorAll('[data-showcase]').forEach(tab=>tab.setAttribute('aria-pressed',String(tab===button)));
    hydrateFeatured(showcase[Number(button.dataset.showcase)]);
  }));
  main.querySelectorAll('.rail-strip').forEach(rail => { rail.scrollLeft = railPositions.get(rail.getAttribute('aria-label')) || 0; });
  hydrateFeatured(activeHero);
}
function renderCatalog(data){const kind=state.route;const items=remember(data.items);const selected=state.params.get('category')||'';const q=state.params.get('q')||'';const options=(data.categories||[]).filter(cat=>String(cat.id??'')!=='').map(cat=>`<option value="${esc(cat.id)}" ${String(cat.id)===selected?'selected':''}>${esc(cat.name)}${cat.count!=null?' ('+count(cat.count)+')':''}</option>`).join('');const title={live:'Şimdi, canlı.',vod:'Bir film seç.',series:'Hikâyeye kapıl.'}[kind];const subtitle={live:'Dünyanın ritmi, kendi ekranında.',vod:'Her ruh haline bir hikâye. Sıradaki favorini keşfet.',series:'Yeni dünyalar, tanıdık karakterler ve bir bölüm daha.'}[kind];$('#main').innerHTML=pageHeading(title,subtitle,{live:'CANLI TV',vod:'FİLM KÜTÜPHANEN',series:'DİZİ KÜTÜPHANEN'}[kind])+syncBanner()+`<div class="catalog-toolbar"><div class="category-tabs"><button class="category-tab ${!selected?'active':''}" data-action="category" data-category="">Tüm ${kind==='live'?'kanallar':kind==='vod'?'filmler':'diziler'}</button>${(data.categories||[]).filter(cat=>String(cat.id??'')!=='').slice(0,5).map(cat=>`<button class="category-tab ${String(cat.id)===selected?'active':''}" data-action="category" data-category="${esc(cat.id)}">${esc(cat.name)}</button>`).join('')}</div><select id="sortSelect" class="sort-select" aria-label="Sıralama"><option value="recent">Son eklenenler</option><option value="name">İsme göre A–Z</option><option value="rating">Puana göre</option></select></div><div class="filter-row"><select id="categorySelect" aria-label="Kategori"><option value="">Tüm kategoriler</option>${options}</select><span class="result-count">${count(data.total)} ${kind==='live'?'kanal':'içerik'}</span></div>${q?`<p class="search-summary"><strong>“${esc(q)}”</strong> için sonuçlar <button class="text-button" data-action="clear-search">${icon('close')} Aramayı temizle</button></p>`:''}${items.length?grid(items,kind):empty(q?'Bir eşleşme bulamadık':'Bu kategoride içerik yok',q?'Farklı bir isimle aramayı ya da kategoriyi değiştirmeyi dene.':'Kütüphaneyi eşitleyerek sağlayıcındaki içerikleri getirebilirsin.','search',button('Filtreleri temizle','reset-filters'))}${pagination(data)}`;$('#sortSelect').value=state.params.get('sort')||'recent';$('#sortSelect').addEventListener('change',e=>changeCatalog({sort:e.target.value,page:1}));$('#categorySelect').addEventListener('change',e=>changeCatalog({category:e.target.value,page:1}));}
function changeCatalog(changes){routeTo(state.route,{...Object.fromEntries(state.params),...changes});}
function pagination(data){if(Number(data.pages)<=1)return '';const p=Number(data.page)||1,pages=Number(data.pages);const values=[...new Set([1,...Array.from({length:5},(_,i)=>p-2+i).filter(n=>n>1&&n<pages),pages])];return `<nav class="pagination" aria-label="Sayfalar"><button data-action="page" data-page="${p-1}" ${p<=1?'disabled':''} aria-label="Önceki sayfa">‹</button>${values.map((n,i)=>(i&&n-values[i-1]>1?'<span>…</span>':'')+`<button data-action="page" data-page="${n}" class="${n===p?'active':''}" ${n===p?'aria-current="page"':''}>${n}</button>`).join('')}<button data-action="page" data-page="${p+1}" ${p>=pages?'disabled':''} aria-label="Sonraki sayfa">›</button></nav>`;}
function libraryTabs(active){return `<nav class="mobile-library-tabs" aria-label="Kütüphanem"><a href="#favorites" class="${active==='favorites'?'active':''}">${icon('heart')}Favoriler</a><a href="#playlists" class="${active==='playlists'?'active':''}">${icon('list')}Listelerim</a></nav>`;}
function renderFavorites(items){$('#main').dataset.favSignature=JSON.stringify(items);remember(items);const kind=state.params.get('kind')||'';const filtered=kind?items.filter(item=>item.kind===kind):items;$('#main').innerHTML=libraryTabs('favorites')+pageHeading('İyi şeyler biriktir.','Sevdiğin kanallar, tekrar izleyeceğin filmler ve aklındaki diziler.','FAVORİLERİN')+`<div class="catalog-toolbar"><div class="category-tabs">${[['','Tümü'],['vod','Filmler'],['series','Diziler'],['live','Canlı TV']].map(([k,label])=>`<button class="category-tab ${kind===k?'active':''}" data-action="favorite-filter" data-kind="${k}">${label}</button>`).join('')}</div><span class="result-count">${count(filtered.length)} favori</span></div>${filtered.length?grid(filtered,kind==='live'?'live':'vod'):empty('Kalbini kazananlar burada','İçeriklerin üzerindeki kalbe dokun. Favorilerin bu sunucuya bağlı tüm cihazlarında görünür.','heart','<a href="#vod" class="button">'+icon('film')+'Keşfetmeye başla</a>')}`;}
function renderSearch(q,results){$('#main').innerHTML=pageHeading('Aradığın hikâyeyi bul.',`“${q}” için kütüphanendeki sonuçlar.`,'ARAMA')+results.map(result=>result.items?.length?section(`${result.kind==='vod'?'Filmler':result.kind==='series'?'Diziler':'Canlı TV'} · ${count(result.total)}`,remember(result.items),result.kind,`${result.kind}?q=${encodeURIComponent(q)}`):'').join('')+(results.every(r=>!r.items?.length)?empty('Bir eşleşme bulamadık','Farklı bir kelimeyle aramayı dene. Sağlayıcının kullandığı başlıklar farklı olabilir.','search'):'');}
function renderPlaylists(){$('#main').dataset.listSignature=JSON.stringify(state.playlists);if(state.route.includes('/')){const id=decodeURIComponent(state.route.split('/').slice(1).join('/'));const list=state.playlists.find(l=>String(l.id)===id);if(!list){$('#main').innerHTML=empty('Bu liste bulunamadı','Liste silinmiş olabilir.','list','<a class="button secondary" href="#playlists">Listelerime dön</a>');return;}const items=remember(list.items||[]);$('#main').innerHTML=`<a class="text-button" href="#playlists" style="margin-bottom:20px">${icon('chevronLeft')}Tüm listelerim</a>`+pageHeading(list.name,`${count(items.length)} içerik · Sıralamayı oklarla değiştirebilirsin.`,'SENİN SEÇKİN',`<div class="playlist-tools">${button(icon('edit')+'Yeniden adlandır','rename-list',`data-list="${esc(id)}"`)}${button(icon('trash')+'Sil','delete-list',`data-list="${esc(id)}"`,'danger small')}</div>`)+(items.length?`<div class="playlist-rows">${items.map((item,index)=>`<div class="playlist-row"><span class="row-number">${index+1}</span>${imageUrl(item.poster)?`<img src="${esc(imageUrl(item.poster))}" alt="" class="row-art" data-poster>`:`<span class="row-art row-art-fallback">${icon(item.kind==='live'?'live':item.kind==='series'?'series':'film')}</span>`}<button class="row-info" style="text-align:left;background:none;border:0;padding:0" data-action="detail" data-id="${esc(item.id)}"><strong>${esc(item.name)}</strong><small>${esc(kindNames[item.kind])}${item.categoryName?' · '+esc(item.categoryName):''}</small></button><div class="row-actions"><button class="icon-button row-play" data-action="${item.kind==='series'?'detail':'play'}" data-id="${esc(item.id)}" aria-label="${esc(item.name)} aç">${icon('play')}</button><button class="icon-button" data-action="reorder" data-list="${esc(id)}" data-id="${esc(item.id)}" data-direction="-1" ${index===0?'disabled':''} aria-label="Yukarı taşı">${icon('arrowUp')}</button><button class="icon-button" data-action="reorder" data-list="${esc(id)}" data-id="${esc(item.id)}" data-direction="1" ${index===items.length-1?'disabled':''} aria-label="Aşağı taşı">${icon('arrowDown')}</button><button class="icon-button" data-action="remove-from-list" data-list="${esc(id)}" data-id="${esc(item.id)}" aria-label="Listeden kaldır">${icon('close')}</button></div></div>`).join('')}</div>`:empty('Bu liste sana bakıyor','Bir içerik seç, seçenekler menüsünden “Listeye ekle”ye dokun ve kendi seçkini oluştur.','list','<a href="#vod" class="button">'+icon('plus')+'İçerikleri keşfet</a>'));return;}$('#main').innerHTML=libraryTabs('playlists')+pageHeading('Kendi seçkini oluştur.','Hafta sonu filmleri, takip ettiğin diziler veya favori kanalların.','LİSTELERİM',button(icon('plus')+'Yeni liste','create-list','',''))+(state.playlists.length?`<div class="list-grid">${state.playlists.map(list=>`<button class="playlist-card" data-action="open-list" data-list="${esc(list.id)}"><div class="playlist-art">${(list.items||[]).filter(i=>imageUrl(i.poster)).slice(0,4).map(item=>`<img src="${esc(imageUrl(item.poster))}" alt="" loading="lazy">`).join('')}<span class="playlist-symbol">${icon('list')}</span></div><div class="playlist-info"><div><h3>${esc(list.name)}</h3><span>${count(list.count??list.items?.length)} içerik</span></div>${icon('chevronRight')}</div></button>`).join('')}</div>`:empty('İlk listenin bir adı olsun.','İçerikleri istediğin gibi gruplandır. Listelerin ve izleme konumun aynı sunucuya bağlanan cihazlarında senkronize olur.','list',button(icon('plus')+'Bir liste oluştur','create-list','','')));}
function renderPairing(){const main=$('#main');main.innerHTML=`<section class="pairing-screen"><div class="brand"><img src="/mavie-mark.svg" alt="" width="34" height="34"><span>mavie<span class="brand-dot">.</span></span></div><span class="eyebrow">AYNI KÜTÜPHANE. YENİ BİR EKRAN.</span><h1>Cihazını Mavie’ye bağla.</h1><p>Ana cihazındaki Mavie ayarlarında görünen eşleştirme kodunu gir. Favorilerin, listelerin ve kaldığın yer bu ekranda da yanında olsun.</p><form id="pairForm"><div class="field"><label for="pairCode" class="muted">Eşleştirme kodu</label><input id="pairCode" name="code" type="text" pattern="[0-9]{6}" inputmode="numeric" autocomplete="one-time-code" minlength="6" maxlength="6" placeholder="000000" required><span class="field-hint">Cihazlar aynı yerel ağa bağlı olmalı.</span></div><button class="button" type="submit">${icon('link')}Cihazı bağla</button><div id="pairError" class="inline-error" role="alert"></div></form></section>`;$('#pairForm').addEventListener('submit',async event=>{event.preventDefault();const submit=event.currentTarget.querySelector('button');submit.disabled=true;try{await api('/api/pair',{method:'POST',body:{code:$('#pairCode').value.trim()}});state.status=await api('/api/status');render();}catch(error){$('#pairError').textContent=error.message;}finally{submit.disabled=false;}});}
function connectionForm(setup=false){const c=state.status?.connection||{};const mode=['m3u','local','xtream'].includes(c.type)?c.type:'xtream';return `<form id="connectionForm"><div class="field"><label for="connectionType">Kaynak türü</label><select id="connectionType" name="type"><option value="m3u" ${mode==='m3u'?'selected':''}>M3U / M3U8 Oynatma Listesi</option><option value="local" ${mode==='local'?'selected':''}>Bilgisayardaki Yerel Klasör</option><option value="xtream" ${mode==='xtream'?'selected':''}>Xtream API Sunucusu</option></select></div><div class="field"><label for="connectionLabel">Bağlantı adı</label><input id="connectionLabel" name="name" value="${esc(c.name||'Kişisel Kütüphane')}" maxlength="80" required autocomplete="off"></div><div id="m3uFields" ${mode==='m3u'?'':'hidden'}><div class="field"><label for="connectionM3u">M3U / M3U8 liste adresi</label><input id="connectionM3u" name="m3uUrl" type="url" value="${esc(c.m3uUrl||'')}" placeholder="https://example.com/playlist.m3u8" spellcheck="false" autocomplete="url"></div></div><div id="localFields" ${mode==='local'?'':'hidden'}><div class="field"><label for="connectionLocalDir">Bilgisayardaki video klasörü yolu</label><input id="connectionLocalDir" name="localDir" value="${esc(c.localDir||'')}" placeholder="/Users/isim/Movies veya C:\\Users\\isim\\Videos" spellcheck="false" autocomplete="off"><span class="field-hint">Klasördeki MP4, MKV, AVI, MOV dosyalarını ve aynı isimli SRT/VTT altyazıları otomatik tarar.</span></div></div><div id="xtreamFields" ${mode==='xtream'?'':'hidden'}><div class="field"><label for="connectionHost">Sunucu adresi</label><input id="connectionHost" name="host" type="url" value="${esc(c.host||'')}" placeholder="https://sunucu-adresi:8080" spellcheck="false" autocomplete="url"><span class="field-hint">Sağlayıcının http:// veya https:// adresini port numarasıyla gir.</span></div><div class="field-row"><div class="field"><label for="connectionUsername">Kullanıcı adı</label><input id="connectionUsername" name="username" placeholder="${setup?'Kullanıcı adın':'Değiştirmek için gir'}" autocomplete="off" spellcheck="false"></div><div class="field"><label for="connectionPassword">Şifre</label><input id="connectionPassword" name="password" type="password" placeholder="${setup?'Parolan':'Kayıtlı şifre korunur'}" autocomplete="new-password"></div></div>${!setup?'<span class="field-hint">Kullanıcı adı ve şifreyi boş bırakırsan mevcut bilgiler korunur.</span>':''}</div><div class="field"><label for="connectionEpg">XMLTV EPG rehber adresi (İsteğe bağlı)</label><input id="connectionEpg" name="epgUrl" type="url" value="${esc(c.epgUrl||'')}" placeholder="https://example.com/guide.xml" spellcheck="false" autocomplete="url"></div><div class="settings-actions"><button class="button" type="submit">${icon('link')}${setup?'Bağlan ve kütüphaneyi getir':'Bağlantıyı kaydet'}</button></div><div id="settingsError" class="inline-error" role="alert"></div></form>`;}
function bindConnectionForm(){const form=$('#connectionForm');const toggle=()=>$('#connectionType')&&( $('#m3uFields').hidden=$('#connectionType').value!=='m3u', $('#localFields').hidden=$('#connectionType').value!=='local', $('#xtreamFields').hidden=$('#connectionType').value!=='xtream');$('#connectionType')?.addEventListener('change',toggle);toggle();form?.addEventListener('submit',async event=>{event.preventDefault();const submit=form.querySelector('[type=submit]');submit.disabled=true;$('#settingsError').textContent='';try{const body=Object.fromEntries(new FormData(form));await api('/api/settings',{method:'POST',body});state.status=await api('/api/status');notify('Bağlantı kaydedildi. Kütüphanen eşitleniyor.');await syncCatalog(false);routeTo('home');if(state.route==='home')render();}catch(error){$('#settingsError').textContent=error.message;}finally{submit.disabled=false;}});}
function renderSetup(){$('#main').innerHTML=`<div class="setup-intro"><span class="eyebrow">KENDİ EKRANINA HOŞ GELDİN</span><h1>Kütüphaneni bağla veya hemen dene.</h1><p>Mavie telifli içerik barındırmaz. Kendi M3U / medya kaynağını bağlayabilir ya da açık lisanslı örnek filmlerle uygulamayı anında test edebilirsin.</p><div style="margin-top:16px">${button(icon('play')+'Açık Sinema ile Hemen Dene (Demo)','demo','','')}</div></div><section class="panel setup-panel"><div class="panel-heading"><span>${icon('link')}</span><div><h2>Medya kaynağı bağla</h2><p>M3U listesi, XMLTV EPG veya Xtream API</p></div></div>${connectionForm(true)}</section>`;bindConnectionForm();}
function renderSettings(){const s=state.status;const a=s.account||{};const network=s.network||{};const lan=network.lanUrls||[];const active=['active','demo'].includes(String(a.status||'').toLowerCase());$('#main').innerHTML=pageHeading('Her şey yerli yerinde.','Bağlantını yönet, diğer ekranlarını bağla ve kütüphaneni koru.','AYARLAR')+syncBanner()+`<div class="settings-grid"><div><section class="panel"><div class="panel-heading"><span>${icon('link')}</span><div><h2>Medya bağlantısı</h2><p>Bilgilerin yalnızca bu cihazda saklanır</p></div></div>${connectionForm(!s.configured)}${s.configured?'<div class="notice">Farklı bir kaynağa geçersen eski kaynağın favorileri, izleme geçmişi ve listelerdeki içerikleri temizlenir.</div>':''}</section><section class="panel"><div class="panel-heading"><span>${icon('shield')}</span><div><h2>Mavie Hesabı & Lisans (İsteğe Bağlı)</h2><p>Özel M3U adresleriniz asla sunucuya gönderilmez</p></div></div><div id="cloudAccountBox"><p class="settings-note">Pro durumu ve lisans anahtarları yükleniyor…</p></div></section><section class="panel"><div class="panel-heading"><span>${icon('shield')}</span><div><h2>Kütüphane yedeği</h2><p>Listeler, favoriler ve izleme geçmişi</p></div></div><p class="settings-note">Başka bir kurulumda kaldığın yerden devam etmek için kişisel kütüphaneni dışa aktar. İçe aktarma, yedekteki listeleri ve favorileri mevcut kütüphanenle birleştirir; aynı içeriğin izleme konumunu günceller.</p><div class="backup-actions">${button(icon('download')+'Yedeği indir','export')}${button(icon('upload')+'Yedeği içe aktar','import')}${button(icon('play')+'Demo Modu','demo','','ghost')}<input type="file" id="importFile" accept="application/json,.json" hidden></div></section></div><div><section class="panel"><div class="panel-heading"><span>${icon('live')}</span><div><h2>Kaynak durumu</h2><p>Bağlantı ve oynatma motoru</p></div></div><dl class="account-list"><div><dt>Durum</dt><dd><span class="status-pill ${!active?'warning':''}">${esc(active?(a.status==='Demo'?'Açık Demo':'Aktif'):a.status||'Henüz sorgulanmadı')}</span></dd></div><div><dt>Bitiş tarihi</dt><dd>${esc(date(a.expires))}</dd></div><div><dt>Eşzamanlı bağlantı</dt><dd>${esc(a.activeConnections??'—')} / ${esc(a.maxConnections??'—')}</dd></div><div><dt>Son eşitleme</dt><dd>${esc(date(s.catalog?.updatedAt))}</dd></div><div><dt>Oynatma desteği</dt><dd>${s.ffmpeg?'Doğrudan + FFmpeg':'Doğrudan oynatma'}</dd></div></dl><div class="settings-section-spacer">${button(icon('refresh')+'Kütüphaneyi eşitle','sync','','secondary small')}</div></section><section class="panel"><div class="panel-heading"><span>${icon('link')}</span><div><h2>Diğer ekranların</h2><p>Android ve aynı ağdaki cihazların</p></div></div><p class="settings-note">Bu bilgisayar açıkken telefonunda veya tabletinde şu adresi aç. Tüm cihazlar aynı kütüphaneyi kullanır.</p>${lan.length?lan.map(url=>`<div class="network-address"><code>${esc(url)}</code><button class="text-button" data-action="copy" data-value="${esc(url)}" aria-label="Adresi kopyala">${icon('copy')}</button></div>`).join(''):'<div class="notice">Yerel ağ adresi bulunamadı. Wi-Fi bağlantını kontrol et.</div>'}${s.pairingCode?`<div class="pairing-code"><span>CİHAZ EŞLEŞTİRME KODU</span><strong>${esc(s.pairingCode)}</strong></div>`:'<div class="notice">Eşleştirme kodu yalnızca ana cihaz ekranında gösterilir.</div>'}<p class="install-note">Tarayıcı menüsünden “Ana ekrana ekle” ile uygulama gibi kurabilirsin.</p><a href="#favorites" class="text-button">${icon('heart')}Favorilerime git</a></section><section class="panel"><div class="panel-heading"><span>${icon('shield')}</span><div><h2>Yasal Bilgiler & Lisanslar</h2><p>Mavie medya oynatıcı politikası</p></div></div><p class="settings-note">Mavie hiçbir televizyon kanalı veya telifli video dağıtmaz; yalnızca kullanıcının eklediği açık veya yasal kaynakları oynatır. Açık kaynak bileşenler: <strong>hls.js (Apache-2.0)</strong>, <strong>LibVLC (LGPL-2.1+)</strong>.</p></section></div></div>`;bindConnectionForm();loadCloudBox();$('#importFile').addEventListener('change',importBackup);}
function trialCountdownText(endsAt){
  if(!endsAt)return '3 günlük Pro deneme etkin';
  const ms=new Date(endsAt).getTime()-Date.now();
  if(!Number.isFinite(ms)||ms<=0)return 'Deneme süresi sona eriyor';
  const totalHours=Math.max(1,Math.ceil(ms/3600000));
  const days=Math.floor(totalHours/24),hours=totalHours%24;
  return days>0?`${days} gün ${hours} saat kaldı (${date(endsAt)})`:`${totalHours} saat kaldı (${date(endsAt)})`;
}
async function loadCloudBox(tab='login',prefillEmail=''){
  const box=$('#cloudAccountBox');
  if(!box)return;
  try{
    const res=await api('/api/cloud/status');
    state.cloudStatus=res;
    const u=res.user;
    if(u){
      const isPro=Boolean(u.isPro||res.isPro||u.effectivePlan==='pro');
      const devices=Array.isArray(u.devices)?u.devices:[];
      box.innerHTML=`
        <dl class="account-list">
          <div><dt>Hesap</dt><dd>${esc(u.displayName||'Kullanıcı')} (${esc(u.email)})</dd></div>
          <div><dt>E-posta Durumu</dt><dd><span class="status-pill ${u.emailVerified?'':'warning'}">${u.emailVerified?'E-posta Doğrulandı':'Doğrulama Bekleniyor'}</span></dd></div>
          <div><dt>Aktif Plan</dt><dd><span class="status-pill ${isPro?'':'warning'}">${isPro?'Pro':'Normal'}</span></dd></div>
          <div><dt>Durum</dt><dd>${esc(u.status||'active')}</dd></div>
        </dl>
        ${u.trialActive?`<div class="cloud-trial-banner"><div><strong>3 Günlük Pro Deneme Aktif</strong><small>${esc(trialCountdownText(u.trialEndsAt))}</small></div><span class="status-pill">Pro Özellikler Açık</span></div>`:''}
        <div class="cloud-plan-grid">
          <div class="cloud-plan-card ${!isPro?'current':''}">
            <h3><span>Normal Plan</span><small>${!isPro?'Mevcut':''}</small></h3>
            <ul><li>1 cihaz sınırı</li><li>Temel yerel medya &amp; M3U oynatma</li><li>Tek profil</li></ul>
          </div>
          <div class="cloud-plan-card ${isPro?'current':''}">
            <h3><span>Pro Plan</span><small>${isPro?'Mevcut':'3 gün ücretsiz dene'}</small></h3>
            <ul><li>5 cihaza kadar kullanım</li><li>Bulut eşitleme &amp; yedek</li><li>Çoklu profil + PIN kilidi + Çoklu Ekran</li></ul>
          </div>
        </div>
        ${!isPro?`<div id="cloudUpgradeCallout" class="cloud-upgrade-callout"><span>Normal plandasınız. Bulut eşitleme, 5 cihaz ve PIN’li profiller için Pro lisans anahtarı girin.</span><button type="button" id="focusLicenseBtn" class="button small">Pro’ya Yükselt</button></div>`:''}
        <div id="cloudActionError" class="inline-error" role="alert" hidden></div>
        <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
          <button id="cloudSyncBtn" type="button" class="button small secondary">${icon('refresh')}Hesap Verilerini Şimdi Eşitle</button>
        </div>
        <form id="cloudRedeemForm" style="margin-top:12px;display:flex;gap:8px">
          <input id="cloudCode" placeholder="Lisans kodu: MAVIE-XXXX-XXXX-XXXX" required style="flex:1">
          <button class="button small" type="submit">Etkinleştir</button>
        </form>
        <div style="margin-top:14px">
          <strong style="font-size:12px">Kayıtlı Cihazlar (${devices.length} / ${esc(u.maxDevices||(isPro?5:1))})</strong>
          <div class="cloud-device-list">${devices.length?devices.map(d=>`<div class="cloud-device-row"><div><strong>${esc(d.name||'Cihaz')}</strong><small>${esc(d.platform||'desktop')} · ${esc(d.lastSeenAt?date(d.lastSeenAt):d.id)}</small></div><button type="button" class="button small danger" data-remove-device="${esc(d.id)}" aria-label="${esc(d.name||'Cihaz')} kaldır">${icon('trash')}Kaldır</button></div>`).join(''):'<p class="settings-note" style="margin:6px 0">Henüz kayıtlı cihaz yok.</p>'}</div>
        </div>
        <div style="margin-top:12px"><button id="cloudLogoutBtn" type="button" class="text-button">${icon('logout')}Hesaptan Çıkış Yap</button></div>`;
      $('#focusLicenseBtn')?.addEventListener('click',()=>$('#cloudCode')?.focus());
      $('#cloudSyncBtn')?.addEventListener('click',async e=>{
        const btn=e.currentTarget;btn.disabled=true;$('#cloudActionError').hidden=true;
        try{
          const s=await api('/api/cloud/sync',{method:'POST',body:{}});
          notify(`Bulut eşitlemesi tamamlandı (${s.counts?.favorites||0} favori, ${s.counts?.progress||0} izleme kaydı, ${s.counts?.playlists||0} liste).`);
        }catch(err){
          const errEl=$('#cloudActionError');
          errEl.textContent=err.message;errEl.hidden=false;
          notify(err.message,true);
          if(err.code==='PRO_REQUIRED')$('#cloudCode')?.focus();
        }finally{btn.disabled=false;}
      });
      $('#cloudRedeemForm')?.addEventListener('submit',async e=>{
        e.preventDefault();
        try{await api('/api/cloud/redeem',{method:'POST',body:{code:$('#cloudCode').value.trim()}});notify('Lisans anahtarı etkinleştirildi.');loadCloudBox();}
        catch(err){notify(err.message,true);}
      });
      box.querySelectorAll('[data-remove-device]').forEach(btn=>btn.addEventListener('click',async()=>{
        btn.disabled=true;
        try{
          await api(`/api/cloud/devices/${encodeURIComponent(btn.dataset.removeDevice)}`,{method:'DELETE'});
          notify('Cihaz hesaptan kaldırıldı.');
          loadCloudBox();
        }catch(err){notify(err.message,true);btn.disabled=false;}
      }));
      $('#cloudLogoutBtn')?.addEventListener('click',async()=>{try{await api('/api/cloud/logout',{method:'POST',body:{}});loadCloudBox();}catch(err){notify(err.message,true);}});
    }else{
      const portalUrl=res.cloudUrl||'https://cineva-app.netlify.app';
      const activeTab=['login','register','verify','forgot'].includes(tab)?tab:'login';
      box.innerHTML=`
        <div class="cloud-tabs" role="tablist" aria-label="Mavie Hesap İşlemleri">
          <button type="button" class="cloud-tab ${activeTab==='login'?'active':''}" data-cloud-tab="login">Giriş Yap</button>
          <button type="button" class="cloud-tab ${activeTab==='register'?'active':''}" data-cloud-tab="register">Kayıt Ol</button>
          <button type="button" class="cloud-tab ${activeTab==='verify'?'active':''}" data-cloud-tab="verify">E-posta Doğrula</button>
          <button type="button" class="cloud-tab ${activeTab==='forgot'?'active':''}" data-cloud-tab="forgot">Şifremi Unuttum</button>
        </div>
        <div class="field"><label for="clUrl">Mavie Portal Sunucusu</label><input id="clUrl" value="${esc(portalUrl)}" required></div>
        <div id="cloudMsgBox" class="inline-error" role="alert" hidden></div>
        <form id="cloudLoginForm" class="cloud-panel-pane" ${activeTab==='login'?'':'hidden'}>
          <div class="field-row">
            <div class="field"><label for="clLoginEmail">E-posta</label><input id="clLoginEmail" type="email" value="${esc(prefillEmail)}" required></div>
            <div class="field"><label for="clLoginPass">Parola</label><input id="clLoginPass" type="password" required minlength="8"></div>
          </div>
          <div class="settings-actions" style="margin-top:8px"><button class="button small" type="submit">Giriş Yap</button></div>
        </form>
        <form id="cloudRegForm" class="cloud-panel-pane" ${activeTab==='register'?'':'hidden'}>
          <div class="field"><label for="clRegName">Ad Soyad</label><input id="clRegName" placeholder="Örneğin: Ada Yılmaz" maxlength="60"></div>
          <div class="field-row">
            <div class="field"><label for="clRegEmail">E-posta</label><input id="clRegEmail" type="email" value="${esc(prefillEmail)}" required></div>
            <div class="field"><label for="clRegPass">Parola (en az 8 karakter)</label><input id="clRegPass" type="password" required minlength="8"></div>
          </div>
          <p class="field-hint">Doğrulama sonrası 3 günlük Pro deneme otomatik olarak başlar.</p>
          <div class="settings-actions" style="margin-top:8px"><button class="button small" type="submit">Hesap Oluştur</button></div>
        </form>
        <form id="cloudVerifyForm" class="cloud-panel-pane" ${activeTab==='verify'?'':'hidden'}>
          <div class="field-row">
            <div class="field"><label for="clVerEmail">E-posta</label><input id="clVerEmail" type="email" value="${esc(prefillEmail)}" required></div>
            <div class="field"><label for="clVerCode">6 Haneli Doğrulama Kodu</label><input id="clVerCode" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" placeholder="123456" required></div>
          </div>
          <div class="settings-actions" style="margin-top:8px;flex-wrap:wrap">
            <button class="button small" type="submit">Doğrula ve 3 Günlük Pro Denemeyi Başlat</button>
            <button class="button small secondary" type="button" id="clResendBtn">Kodu Tekrar Gönder</button>
          </div>
        </form>
        <form id="cloudForgotForm" class="cloud-panel-pane" ${activeTab==='forgot'?'':'hidden'}>
          <div class="field-row">
            <div class="field"><label for="clForgotEmail">E-posta</label><input id="clForgotEmail" type="email" value="${esc(prefillEmail)}" required></div>
            <div class="field" style="justify-content:flex-end"><button class="button small secondary" type="button" id="clSendResetBtn">Sıfırlama Kodu Gönder</button></div>
          </div>
          <div class="field-row">
            <div class="field"><label for="clResetCode">Sıfırlama Kodu</label><input id="clResetCode" inputmode="numeric" maxlength="12" placeholder="6 haneli kod"></div>
            <div class="field"><label for="clResetPass">Yeni Parola</label><input id="clResetPass" type="password" minlength="8" placeholder="En az 8 karakter"></div>
          </div>
          <div class="settings-actions" style="margin-top:8px"><button class="button small" type="submit">Parolayı Güncelle</button></div>
        </form>`;
      const showMsg=(msg)=>{const m=$('#cloudMsgBox');if(m){m.textContent=msg;m.hidden=!msg;}};
      box.querySelectorAll('[data-cloud-tab]').forEach(btn=>btn.addEventListener('click',()=>{
        const target=btn.dataset.cloudTab;
        const currentEmail=$('#clLoginEmail')?.value||$('#clRegEmail')?.value||$('#clVerEmail')?.value||$('#clForgotEmail')?.value||'';
        loadCloudBox(target,currentEmail.trim());
      }));
      $('#cloudLoginForm')?.addEventListener('submit',async e=>{
        e.preventDefault();showMsg('');
        const email=$('#clLoginEmail').value.trim();
        try{
          await api('/api/cloud/login',{method:'POST',body:{cloudUrl:$('#clUrl').value.trim(),email,password:$('#clLoginPass').value}});
          notify('Mavie hesabına bağlanıldı.');
          loadCloudBox();
        }catch(err){
          if(err.code==='EMAIL_NOT_VERIFIED'||err.verificationRequired){
            notify('E-posta doğrulaması gerekiyor. Doğrulama kodunu girin.',true);
            await loadCloudBox('verify',err.email||email);
            const m=$('#cloudMsgBox');if(m){m.textContent='E-posta adresiniz henüz doğrulanmamış. Lütfen kodunuzu girin veya yeni kod isteyin.';m.hidden=false;}
          }else{showMsg(err.message);notify(err.message,true);}
        }
      });
      $('#cloudRegForm')?.addEventListener('submit',async e=>{
        e.preventDefault();showMsg('');
        const email=$('#clRegEmail').value.trim();
        try{
          const reg=await api('/api/cloud/register',{method:'POST',body:{cloudUrl:$('#clUrl').value.trim(),displayName:$('#clRegName').value.trim(),email,password:$('#clRegPass').value}});
          if(reg.verificationRequired){
            notify('Hesap oluşturuldu! Doğrulama kodunuz gönderildi.');
            await loadCloudBox('verify',email);
            const m=$('#cloudMsgBox');if(m){m.textContent='E-posta adresinize gönderilen 6 haneli kodu girerek hesabınızı ve 3 günlük Pro denemenizi başlatın.';m.hidden=false;}
          }else{notify('Mavie hesabına bağlanıldı.');loadCloudBox();}
        }catch(err){showMsg(err.message);notify(err.message,true);}
      });
      $('#cloudVerifyForm')?.addEventListener('submit',async e=>{
        e.preventDefault();showMsg('');
        try{
          const v=await api('/api/cloud/verify-email',{method:'POST',body:{cloudUrl:$('#clUrl').value.trim(),email:$('#clVerEmail').value.trim(),code:$('#clVerCode').value.trim()}});
          notify(v.trialActivated?'E-posta doğrulandı ve 3 günlük Pro denemeniz başladı!':'E-posta doğrulandı.');
          loadCloudBox();
        }catch(err){showMsg(err.message);notify(err.message,true);}
      });
      $('#clResendBtn')?.addEventListener('click',async()=>{
        showMsg('');
        try{
          await api('/api/cloud/resend-verification',{method:'POST',body:{cloudUrl:$('#clUrl').value.trim(),email:$('#clVerEmail').value.trim()}});
          notify('Doğrulama kodu tekrar gönderildi.');
        }catch(err){showMsg(err.message);notify(err.message,true);}
      });
      $('#clSendResetBtn')?.addEventListener('click',async()=>{
        showMsg('');
        try{
          await api('/api/cloud/forgot-password',{method:'POST',body:{cloudUrl:$('#clUrl').value.trim(),email:$('#clForgotEmail').value.trim()}});
          notify('Eğer hesap varsa sıfırlama kodu gönderildi.');
        }catch(err){showMsg(err.message);notify(err.message,true);}
      });
      $('#cloudForgotForm')?.addEventListener('submit',async e=>{
        e.preventDefault();showMsg('');
        const email=$('#clForgotEmail').value.trim();
        const code=$('#clResetCode').value.trim();
        const newPassword=$('#clResetPass').value;
        try{
          await api('/api/cloud/verify-reset-code',{method:'POST',body:{cloudUrl:$('#clUrl').value.trim(),email,code}});
          await api('/api/cloud/reset-password',{method:'POST',body:{cloudUrl:$('#clUrl').value.trim(),email,code,newPassword}});
          notify('Parolanız güncellendi. Yeni parolanızla giriş yapabilirsiniz.');
          loadCloudBox('login',email);
        }catch(err){showMsg(err.message);notify(err.message,true);}
      });
    }
  }catch{box.innerHTML='<p class="settings-note">İsteğe bağlı bulut bağlantısı şu anda çevrimdışı.</p>';}
}
async function syncCatalog(showNotice=true){if(state.status?.catalog?.syncing){if(showNotice)notify('Kütüphane zaten eşitleniyor.');return;}await api('/api/catalog/sync',{method:'POST',body:{}});state.status=await api('/api/status');updateShell();if(showNotice){notify('Eşitleme başladı. Bu sırada kütüphaneni kullanabilirsin.');render();}}
async function toggleFavorite(id){const item=itemFor(id);if(!item)return;const favorite=!item.favorite;await api('/api/favorites',{method:'POST',body:{id,favorite}});item.favorite=favorite;document.querySelectorAll('[data-action="favorite"]').forEach(el=>{if(el.dataset.id===id){el.classList.toggle('active',favorite);el.setAttribute('aria-label',favorite?'Favorilerden kaldır':'Favorilere ekle');el.title=favorite?'Favorilerden kaldır':'Favorilere ekle';}});notify(favorite?'Favorilerine eklendi.':'Favorilerinden kaldırıldı.');if(state.route==='favorites')render();}
function openDialog(id){const dialog=$('#'+id);if(!dialog.open)dialog.showModal();}
function closeDialog(id){$('#'+id)?.close();}
async function openDetail(id){const dialog=$('#detailDialog');$('#detailContent').innerHTML='<div class="initial-loading" style="min-height:320px"><span class="spinner"></span><p>Ayrıntılar getiriliyor…</p></div>';openDialog('detailDialog');try{const data=await api(`/api/items/${encodeURIComponent(id)}`);if(!dialog.open)return;remember([data.item]);state.detail=data;renderDetail(data);if(data.item?.kind==='live')loadEpg(id);}catch(error){$('#detailContent').innerHTML=empty('Ayrıntılar getirilemedi',error.message,'alert');}}
function renderDetail(data){const item=data.item,info=data.info||{},seasons=data.seasons||[];remember(seasons.flatMap(s=>s.episodes||[]));const backdrop=imageUrl(info.backdrop);$('#detailContent').innerHTML=`<div class="detail-cover">${backdrop?`<img src="${esc(backdrop)}" alt="" loading="lazy">`:''}</div><div class="detail-main"><div class="detail-poster">${art(item)}</div><div class="detail-copy"><span class="eyebrow">${esc(kindNames[item.kind]||'KÜTÜPHANE')}</span><h2>${esc(item.name)}</h2><div class="detail-meta">${info.year||item.year?`<span>${esc(info.year||item.year)}</span>`:''}${info.rating||item.rating?`<span class="rating">★ ${esc(info.rating||item.rating)}</span>`:''}${info.duration?`<span>${esc(typeof info.duration==='number'?minutes(info.duration):info.duration)}</span>`:''}${info.genre?`<span>${esc(info.genre)}</span>`:''}</div><div class="detail-actions">${item.kind!=='series'?button(icon('play')+(item.progress?.position&&!item.progress?.completed&&item.kind!=='live'?'Devam et · '+time(item.progress.position):item.kind==='live'?'Yayını aç':'İzlemeye başla'),'play',`data-id="${esc(item.id)}"`,''):''}<button class="icon-button ${item.favorite?'active':''}" data-action="favorite" data-id="${esc(item.id)}" aria-label="Favori">${icon('heart')}</button><button class="icon-button" data-action="add-list" data-id="${esc(item.id)}" aria-label="Listeye ekle" title="Listeye ekle">${icon('plus')}</button>${item.progress?.position?`<button class="icon-button" data-action="clear-progress" data-id="${esc(item.id)}" title="İzleme kaydını sıfırla" aria-label="İzleme kaydını sıfırla">${icon('refresh')}</button>`:''}</div></div></div><div class="detail-body">${info.plot?`<p class="detail-plot">${esc(info.plot)}</p>`:'<p class="detail-plot">Bu içerik için sağlayıcından açıklama gelmedi.</p>'}<div class="detail-credits">${info.director?`<div><strong>Yönetmen</strong> ${esc(info.director)}</div>`:''}${info.cast?`<div><strong>Oyuncular</strong> ${esc(info.cast)}</div>`:''}${item.categoryName?`<div><strong>Kategori</strong> ${esc(item.categoryName)}</div>`:''}</div>${item.kind==='series'?`<section class="episode-section"><div class="section-heading"><h2>Bölümler</h2>${seasons.length?`<select class="season-select" id="seasonSelect" aria-label="Sezon seç">${seasons.map((season,index)=>`<option value="${index}">${esc(season.name||`${season.season}. Sezon`)} · ${(season.episodes||[]).length} bölüm</option>`).join('')}</select>`:''}</div><div id="episodeList">${seasons.length?episodesHtml(seasons[0]):empty('Henüz bölüm görünmüyor','Sağlayıcından bu diziye ait bölüm gelmedi.','series')}</div></section>`:''}${item.kind==='live'?'<section class="episode-section"><div class="section-heading"><h2>Yayın akışı</h2></div><div id="epgContent" class="muted" style="font-size:11px">Program bilgisi aranıyor…</div></section>':''}</div>`;$('#seasonSelect')?.addEventListener('change',e=>{$('#episodeList').innerHTML=episodesHtml(seasons[Number(e.target.value)]);});}
function episodesHtml(season){return `<div class="episode-list">${(season.episodes||[]).map((episode,index)=>`<div class="episode-row"><span class="episode-number">${esc(episode.episode||index+1)}</span><div class="episode-copy"><strong>${esc(episode.name)}</strong><small>${episode.progress?.completed?'İzlendi':episode.progress?.position?'Kaldığın yer · '+time(episode.progress.position):'İzlemeye hazır'}</small>${episode.progress?.position?`<div class="progress-inline"><span style="width:${progressPercent(episode)}%"></span></div>`:''}</div><button class="icon-button" data-action="add-list" data-id="${esc(episode.id)}" title="Listeye ekle" aria-label="Listeye ekle">${icon('plus')}</button><button class="icon-button episode-play" data-action="play" data-id="${esc(episode.id)}" aria-label="${esc(episode.name)} oynat">${icon('play')}</button></div>`).join('')}</div>`;}
async function loadEpg(id){try{const data=await api(`/api/epg/${encodeURIComponent(id)}`);if(state.detail?.item?.id!==id||!$('#epgContent'))return;const programs=(data.programs||[]).slice(0,10);$('#epgContent').innerHTML=programs.length?`<div class="epg-list">${programs.map(p=>`<div class="epg-item"><div class="epg-time">${esc(epgTime(p.start))}<br>${esc(epgTime(p.end))}</div><div><div class="epg-title">${esc(p.title)}</div>${p.description?`<div class="epg-description">${esc(p.description)}</div>`:''}</div></div>`).join('')}</div>`:'Bu kanal için program bilgisi bulunmuyor.';}catch{$('#epgContent')&&($('#epgContent').textContent='Yayın akışı bilgisi alınamadı.');}}
function epgTime(value){if(!value)return '';const d=new Date(typeof value==='number'?value*(value<1e12?1000:1):value);return Number.isNaN(d.getTime())?'':d.toLocaleTimeString('tr-TR',{hour:'2-digit',minute:'2-digit'});}
function itemMenu(id){const item=itemFor(id);if(!item)return;$('#listContent').innerHTML=`<h2>${esc(item.name)}</h2><p>Bu içerikle ne yapmak istersin?</p><button class="list-choice" data-action="favorite" data-id="${esc(id)}">${esc(item.favorite?'Favorilerden kaldır':'Favorilere ekle')}${icon('heart')}</button><button class="list-choice" data-action="add-list" data-id="${esc(id)}">Listeye ekle${icon('plus')}</button>${item.progress?.position?`<button class="list-choice" data-action="clear-progress" data-id="${esc(id)}">İzleme kaydını sıfırla${icon('refresh')}</button>`:''}<button class="list-choice" data-action="detail" data-id="${esc(id)}">İçerik ayrıntıları${icon('chevronRight')}</button>`;openDialog('listDialog');}
async function addToListDialog(id){const data=await api('/api/playlists');state.playlists=data.playlists||[];$('#listContent').innerHTML=`<h2>Listeye ekle</h2><p>${esc(itemFor(id)?.name||'Seçilen içerik')}</p>${state.playlists.map(list=>`<button class="list-choice" data-action="select-list" data-id="${esc(id)}" data-list="${esc(list.id)}">${esc(list.name)}<small>${count(list.count??list.items?.length)}</small>${icon((list.items||[]).some(i=>i.id===id)?'check':'plus')}</button>`).join('')}${!state.playlists.length?'<p>Henüz bir listen yok. İlk listeni aşağıdan oluşturabilirsin.</p>':''}<div class="small-dialog-actions">${button(icon('plus')+'Yeni liste','create-list',`data-item="${esc(id)}"`,'')}</div>`;openDialog('listDialog');}
function listNameDialog(listId='',itemId=''){const list=state.playlists.find(l=>String(l.id)===listId);$('#listContent').innerHTML=`<h2>${list?'Listeyi yeniden adlandır':'Yeni bir seçki'}</h2><p>${list?'Listene yeni bir ad ver.':'Güzel bir liste, güzel bir isimle başlar.'}</p><form id="listNameForm"><div class="field"><label for="listName">Liste adı</label><input id="listName" name="name" value="${esc(list?.name||'')}" placeholder="Örneğin: Hafta sonu filmleri" required maxlength="100" autocomplete="off"></div><div class="small-dialog-actions"><button type="button" class="button ghost" data-close="listDialog">Vazgeç</button><button class="button" type="submit">${list?'Kaydet':'Listeyi oluştur'}</button></div><div class="inline-error" id="listError" role="alert"></div></form>`;openDialog('listDialog');setTimeout(()=>$('#listName')?.focus(),50);$('#listNameForm').addEventListener('submit',async e=>{e.preventDefault();const name=$('#listName').value.trim();if(!name)return;const submit=e.currentTarget.querySelector('[type=submit]');submit.disabled=true;try{const data=await api(list?`/api/playlists/${encodeURIComponent(listId)}`:'/api/playlists',{method:list?'PATCH':'POST',body:{name}});if(itemId){const createdId=data.playlist?.id||data.id;if(!createdId)throw new Error('Liste oluşturuldu; içeriği listeye tekrar ekleyebilirsin.');await api(`/api/playlists/${encodeURIComponent(createdId)}`,{method:'PATCH',body:{itemId}});}closeDialog('listDialog');notify(list?'Liste adı güncellendi.':itemId?'Liste oluşturuldu ve içerik eklendi.':'Yeni listen hazır.');if(state.route.startsWith('playlists'))render();}catch(error){$('#listError').textContent=error.message;}finally{submit.disabled=false;}});}
function confirmDialog(title,description,onConfirm,label='Onayla'){const content=$('#listContent');content.innerHTML=`<h2>${esc(title)}</h2><p>${esc(description)}</p><div class="small-dialog-actions"><button class="button ghost" data-close="listDialog">Vazgeç</button><button class="button danger" id="confirmAction">${esc(label)}</button></div>`;openDialog('listDialog');$('#confirmAction').addEventListener('click',async e=>{e.target.disabled=true;try{await onConfirm();closeDialog('listDialog');}catch(error){notify(error.message,true);e.target.disabled=false;}});}
async function clearProgress(id){await api(`/api/progress/${encodeURIComponent(id)}`,{method:'DELETE'});const item=itemFor(id);if(item)item.progress=null;closeDialog('listDialog');notify('İzleme kaydı sıfırlandı.');if(state.detail?.item?.id===id&&$('#detailDialog').open)renderDetail(state.detail);render();}
async function importBackup(e){const file=e.target.files?.[0];if(!file)return;try{if(file.size>25*1024*1024)throw new Error('Yedek dosyası 25 MB’tan küçük olmalı.');const data=JSON.parse(await file.text());confirmDialog('Yedeği geri yükle?',`${file.name} dosyasındaki favoriler ve listeler kütüphanenle birleştirilecek. Aynı içeriklerin izleme konumu yedekteki konumla güncellenecek.`,async()=>{await api('/api/import',{method:'POST',body:{data}});notify('Kütüphanen geri yüklendi.');render();},'Geri yükle');}catch(error){notify('Yedek okunamadı: '+error.message,true);}finally{e.target.value='';}}
async function exportBackup(){const response=await fetch('/api/export');if(!response.ok)throw new Error('Yedek indirilemedi.');const blob=await response.blob();const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=`mavie-yedek-${new Date().toISOString().slice(0,10)}.json`;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),10000);notify('Kütüphane yedeğin indirildi.');}
function playbackHint(mode){return mode==='direct'?'Doğrudan oynatma · Görüntü veya ses gelmezse uyumlu oynatmayı dene.':mode==='remux'?'Uyumlu oynatma · Video değiştirilmeden paketlenir. Ses sorunu varsa dönüştürmeyi dene.':'Dönüştürülerek oynatılıyor · Bu cihazın işlemcisi kullanılıyor.';}
function updatePlaybackMode(player){document.querySelectorAll('[data-mode]').forEach(button=>{button.classList.toggle('active',button.dataset.mode===player.mode);button.disabled=button.dataset.mode!=='direct'&&!state.status?.ffmpeg;});$('#playerHint').textContent=playbackHint(player.mode);}
const playerPanels = [['#trackPanel', '#toggleTracks'], ['#modePanel', '#toggleModes'], ['#sleepPanel', '#toggleSleep'], ['#episodeDrawerPanel', '#toggleEpisodesDrawer']];
function setPlayerPanel(open = '') {
  for (const [panel, trigger] of playerPanels) {
    $(panel).hidden = panel !== open;
    $(trigger).setAttribute('aria-expanded', String(panel === open));
  }
}
function showPlayerOsd(text) {
  const el = $('#playerOsd');
  if (!el) return;
  el.textContent = text;
  el.hidden = false;
  clearTimeout(state.osdTimer);
  state.osdTimer = setTimeout(() => { if ($('#playerOsd')) $('#playerOsd').hidden = true; }, 1400);
}
function setSleepTimer(minutes) {
  clearTimeout(state.sleepTimer);
  state.sleepTimer = null;
  state.sleepUntil = 0;
  const m = Math.max(0, Number(minutes) || 0);
  const status = $('#sleepStatus');
  if (!m) {
    if (status) status.textContent = 'Zamanlayıcı kapalı';
    showPlayerOsd('Uyku zamanlayıcısı kapatıldı');
    return;
  }
  state.sleepUntil = Date.now() + m * 60000;
  if (status) status.textContent = `${m} dakika sonra durdurulacak`;
  showPlayerOsd(`Uyku zamanlayıcısı: ${m} dk`);
  state.sleepTimer = setTimeout(() => {
    state.sleepTimer = null;
    state.sleepUntil = 0;
    const vid = $('#video');
    if (vid?.pause) vid.pause();
    if ($('#sleepStatus')) $('#sleepStatus').textContent = 'Süre doldu, oynatma durduruldu';
    notify('Uyku zamanlayıcısı süresi doldu.');
  }, m * 60000);
}
async function populateEpisodeDrawer(player) {
  const listEl = $('#episodeDrawerList');
  if (!listEl || !player || player.item.kind !== 'episode') return;
  const parentId = player.item.parentId;
  if (!parentId) return;
  if (state.detail?.item?.id !== parentId) {
    listEl.innerHTML = '<p class="player-hint">Bölümler yükleniyor…</p>';
    try {
      const data = await api(`/api/items/${encodeURIComponent(parentId)}`);
      state.detail = data;
      remember((data.seasons || []).flatMap(s => s.episodes || []));
    } catch {
      listEl.innerHTML = '<p class="player-hint">Bölüm listesi alınamadı.</p>';
      return;
    }
  }
  const seasons = state.detail?.seasons || [];
  const allEps = seasons.flatMap(s => s.episodes || []);
  listEl.innerHTML = allEps.map(ep => `<button type="button" class="episode-drawer-item ${ep.id === player.id ? 'active' : ''}" data-drawer-ep="${esc(ep.id)}"><span>S${esc(ep.season || 1)}·B${esc(ep.episode || '')} — ${esc(ep.name)}</span><small>${ep.progress?.completed ? 'İzlendi' : ''}</small></button>`).join('') || '<p class="player-hint">Başka bölüm bulunamadı.</p>';
  listEl.querySelectorAll('[data-drawer-ep]').forEach(btn => btn.addEventListener('click', () => {
    setPlayerPanel();
    playItem(btn.dataset.drawerEp).catch(error => notify(error.message, true));
  }));
}
function showPlayerControls(player = state.player) {
  const dialog = $('#playerDialog');
  dialog.classList.remove('controls-hidden');
  if (!player) return;
  clearTimeout(player.controlsTimer);
  player.controlsTimer = setTimeout(() => {
    const focused = document.activeElement?.matches?.('.player-chrome :focus-visible');
    if (state.player === player && !$('#video').paused && !player.scrubbing && !player.ended && !focused &&
        $('#playerOverlay').hidden && playerPanels.every(([panel]) => $(panel).hidden)) {
      dialog.classList.add('controls-hidden');
    }
  }, 3200);
}
function playbackButton(button, label, svg) {
  button.setAttribute('aria-label', label);
  button.title = label;
  if (svg) button.innerHTML = svg;
}
function updateTransport(player = state.player) {
  const video = $('#video');
  const playing = player?.ready && !video.paused && !player.ended;
  playbackButton($('#togglePlay'), playing ? 'Duraklat' : player?.ended ? 'Baştan oynat' : 'Oynat',
    playing ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h3v14H7zm7 0h3v14h-3z"/></svg>' : icon('play'));
  const muted = video.muted || video.volume === 0;
  playbackButton($('#mutePlayer'), muted ? 'Sesi aç' : 'Sesi kapat',
    `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 9v6h4l5 4V5L7 9H3 ${muted ? 'm13 1 5 5m0-5-5 5' : 'm13 0a4 4 0 0 1 0 6m3-9a8 8 0 0 1 0 12'}"/></svg>`);
  $('#playerVolume').value = muted ? 0 : video.volume;
  $('#skipBack').hidden = $('#skipForward').hidden = player?.item.kind === 'live';
  $('#nextEpisodeShortcut').hidden = !player?.nextEpisode;
  if ($('#toggleEpisodesDrawer')) $('#toggleEpisodesDrawer').hidden = player?.item.kind !== 'episode';
  if ($('#speedSelect') && 'playbackRate' in video) $('#speedSelect').value = String(state.playbackRate || 1);
  if ($('#pipButton')) $('#pipButton').hidden = typeof document === 'undefined' || !document.pictureInPictureEnabled || typeof video.requestPictureInPicture !== 'function';
}
function clearEpisodeEnding(player) {
  clearTimeout(player?.endingTimer);
  $('#episodeEnding').hidden = true;
}
function replayPlayer(player) {
  if (state.player === player) return playItem(player.id, player.mode, 0, player.fallbackUsed);
}
async function openNextEpisode(player) {
  if (state.player !== player || !player.nextEpisode || player.advancing) return;
  player.advancing = true;
  clearEpisodeEnding(player);
  try {
    await (player.endProgress || saveProgress(true));
    if (state.player === player) await playItem(player.nextEpisode.id);
  } finally {
    player.advancing = false;
  }
}
function cancelEpisodeCountdown(player) {
  clearTimeout(player.endingTimer);
  player.endingTimer = null;
  $('#nextCountdown').textContent = '';
  $('#cancelNextEpisode').textContent = 'Baştan oynat';
  $('#cancelNextEpisode').setAttribute('aria-label', 'Bölümü baştan oynat');
}
function showEpisodeEnding(player) {
  const next = player.nextEpisode;
  if (!next) return;
  const poster = imageUrl(next.poster);
  $('#endingArt').innerHTML = poster ? `<img src="${esc(poster)}" alt="" decoding="async">` : '';
  $('#endingCaption').textContent = next.season > 0 && next.episode > 0
    ? `SIRADAKİ BÖLÜM · S${next.season} B${next.episode}` : 'SIRADAKİ BÖLÜM';
  $('#endingTitle').textContent = next.name;
  $('#cancelNextEpisode').textContent = 'İptal';
  $('#cancelNextEpisode').setAttribute('aria-label', 'Otomatik geçişi iptal et');
  $('#episodeEnding').hidden = false;
  const deadline = Date.now() + 8000;
  const tick = () => {
    if (state.player !== player || !player.ended || player.advancing) return;
    const remaining = Math.ceil((deadline - Date.now()) / 1000);
    if (remaining <= 0) {
      player.endingTimer = null;
      openNextEpisode(player).catch(error => notify(error.message, true));
    } else {
      $('#nextCountdown').textContent = String(remaining);
      player.endingTimer = setTimeout(tick, 1000);
    }
  };
  tick();
}
function actualPlaybackPosition(player, video = $('#video')) {
  return player.ready ? Math.max(0, Number(video.currentTime) || 0) + player.offset : player.start;
}
function playerEnded(player) {
  if (!player.ready || player.ended || player.item.kind === 'live') return;
  hideBuffering();
  const position = actualPlaybackPosition(player);
  // A provider can truncate an input without an HLS network error. Only offer
  // the next episode once playback reaches the title's actual end.
  if (player.mode !== 'direct' && player.duration - position > 8) {
    if (player.endRetries < 2) {
      const options = window.MavieTracks?.options(player) || player.trackOptions;
      playItem(player.id, player.mode, position, player.fallbackUsed, options, player.endRetries + 1)
        .catch(error => playerError(error.message));
    } else {
      playerError('Yayın sona ermeden kesildi. Kaldığın yerden yeniden açmayı deneyebilirsin.');
    }
    return;
  }
  player.ended = true;
  player.endProgress = saveProgress(true);
  updateTransport(player);
  showPlayerControls(player);
  showEpisodeEnding(player);
}
function playbackFailed(player,message,error=null){
  if(state.player!==player||player.retrying||!player.mediaBound)return;
  const cancelled=error?.name==='AbortError'||[400,401,403,404,409,410].includes(error?.status)||String(error?.code||'').startsWith('upstream_');
  const nextMode=player.mode==='direct'?'remux':player.mode==='remux'&&!player.fallbackUsed?'transcode':null;
  if(nextMode&&error?.mode!=='transcode'&&state.status?.ffmpeg&&!cancelled){
    player.retrying=true;
    player.fallbackUsed=nextMode==='transcode';
    const position=player.item.kind==='live'?0:actualPlaybackPosition(player);
    playItem(player.id,nextMode,position,player.fallbackUsed,player.trackOptions,player.endRetries).catch(failure=>{if(state.player===player){player.retrying=false;playerError(failure.message);}});
    return;
  }
  playerError(message,error?.code);
}
function playVideo(player){if(player.restorePaused){$('#video').pause();if(player.sessionId&&player.mode!=='direct')api(`/api/play/${encodeURIComponent(player.sessionId)}/pause`,{method:'POST',body:{paused:true}}).catch(()=>{});return;}$('#video').play().catch(error=>{if(state.player!==player||player.retrying||!player.mediaBound)return;if(error.name==='NotSupportedError')playbackFailed(player,'Video biçimi bu cihazda oynatılamadı.',error);else playerPausedMessage(player);});}
async function playItem(id,mode,startOverride,fallbackUsed=false,trackOptions=null,endRetries=0){
  const generation=++state.playGeneration;
  clearTimeout(state.seekTimer);state.seekTimer=null;
  const item=itemFor(id);
  if(!item)throw new Error('İçerik bulunamadı. Kütüphaneyi yenileyip tekrar dene.');
  if(item.kind==='series'){openDetail(id);return;}
  if(!mode)mode=state.status?.ffmpeg&&item.kind!=='live'&&!['mp4','m4v','webm'].includes(String(item.extension||'').toLowerCase())?'remux':'direct';
  if(state.player){
    if(state.player.id===id&&!trackOptions)trackOptions=window.MavieTracks?.options(state.player)||state.player.trackOptions;
    await stopPlayer(false);
  }
  if(generation!==state.playGeneration)return;
  closeDialog('detailDialog');closeDialog('listDialog');
  const start=item.kind==='live'?0:startOverride!=null?Math.max(0,Number(startOverride)||0):item.progress?.completed?0:Number(item.progress?.position)||0;
  const player={id,item,mode,start,offset:0,duration:0,sessionId:null,ready:false,recoveries:0,fallbackUsed,retrying:false,mediaBound:true,endRetries};
  state.player=player;
  player.trackOptions=trackOptions;player.restorePaused=trackOptions?.paused===true;
  window.MavieTracks?.reset(player);
  $('#playerTitle').textContent=item.name;
  $('#playerEyebrow').textContent=item.kind==='live'?'CANLI YAYIN':item.seriesName||'ŞİMDİ OYNATILIYOR';
  $('#playerOverlay').hidden=false;$('#playerOverlay').classList.remove('error');
  $('#playerMessage').textContent=mode==='transcode'?'Video dönüştürülüyor. İlk açılış biraz zaman alabilir…':mode==='remux'?'Uyumlu yayın hazırlanıyor…':'Yayın açılıyor…';
  updatePlaybackMode(player);$('#playerHint').textContent='Bağlantı kuruluyor';$('#absoluteSeek').hidden=true;
  clearEpisodeEnding(player);
  setPlayerPanel();
  updateTransport(player);
  showPlayerControls(player);
  openDialog('playerDialog');
  try{
    const result=await api('/api/play',{method:'POST',body:{id,mode,start,...(trackOptions||{}),clientId:state.playClient,generation}});
    if(state.player!==player){if(result.sessionId)fetch(`/api/play/${encodeURIComponent(result.sessionId)}`,{method:'DELETE',keepalive:true}).catch(()=>{});return;}
    player.sessionId=result.sessionId;
    window.MavieTracks?.ready(player,result);
    if(['direct','remux','transcode'].includes(result.mode))player.mode=result.mode;
    window.MavieTracks?.render(player);
    player.offset=Number(result.startOffset)||0;
    if(player.mode!=='direct')player.start=player.offset;
    player.duration=Number(result.duration)||Number(item.duration)||Number(item.progress?.duration)||0;
    if(result.nextEpisode?.kind==='episode'){
      player.nextEpisode=result.nextEpisode;
      remember([result.nextEpisode]);
    }
    updateTransport(player);
    updatePlaybackMode(player);
    const video=$('#video');
    if(result.type==='hls'&&window.Hls?.isSupported()){
      const generatedVod=player.item.kind!=='live'&&player.mode!=='direct';
      // A file is produced progressively, but it must never follow the HLS live
      // edge. Keep the requested beginning and retain useful seek history.
      const hls=new Hls({enableWorker:true,lowLatencyMode:false,backBufferLength:120,maxBufferLength:60,maxMaxBufferLength:90,maxBufferSize:64*1024*1024,...(generatedVod?{startPosition:0,liveSyncDuration:Math.max(86400,player.duration+120),liveMaxLatencyDuration:Infinity,maxLiveSyncPlaybackRate:1}: {})});
      state.hls=hls;
      window.MavieTracks?.bindHls(player,hls);
      hls.loadSource(result.url);hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED,()=>{if(state.player!==player||state.hls!==hls||player.retrying)return;player.ready=true;if(player.mode==='direct'&&start>0&&player.offset===0)video.currentTime=start;playVideo(player);});
      hls.on(Hls.Events.ERROR,(_event,data)=>{
        if(state.player!==player||state.hls!==hls||player.retrying||!data.fatal)return;
        if(player.mode!=='remux'&&data.type===Hls.ErrorTypes.MEDIA_ERROR&&player.recoveries<2){player.recoveries++;hls.recoverMediaError();return;}
        playbackFailed(player,'Yayın oynatılamadı. Aşağıdaki alternatif oynatma seçeneklerinden birini deneyebilirsin.');
      });
    }else if(result.type==='hls'&&video.canPlayType('application/vnd.apple.mpegurl'))video.src=result.url;
    else if(result.type==='hls')throw new Error('Bu tarayıcı HLS yayınını desteklemiyor. Tarayıcını güncelleyip tekrar dene.');
    else video.src=result.url;
    updateSeekDisplay(player);
    state.progressTimer=setInterval(()=>saveProgress(),10000);
    state.pingTimer=setInterval(()=>pingPlayback(),5000);
  }catch(error){if(state.player===player&&['direct','remux','transcode'].includes(error.mode)){player.mode=error.mode;updatePlaybackMode(player);}playbackFailed(player,error.message,error);}
}
async function interruptPlayback(message){
  const p=state.player;if(!p)return;
  const position=actualPlaybackPosition(p),generation=state.playGeneration;
  await stopPlayer(false,false);
  if(state.player||state.playGeneration!==generation)return;
  p.sessionId=null;p.ready=false;p.start=position;p.offset=position;p.ended=false;
  state.player=p;updateTransport(p);playerError(message);
}
function playerPausedMessage(player=state.player){if(!player||state.player!==player||player.retrying||!player.mediaBound)return;$('#playerOverlay').hidden=true;$('#playerHint').textContent='Video hazır. İzlemeye başlamak için oynat düğmesine dokun.';updateTransport(player);showPlayerControls(player);}
function playerError(message,code=''){$('#playerOverlay').hidden=false;$('#playerOverlay').classList.add('error');$('#playerMessage').textContent=message;$('#playerHint').textContent=String(code).startsWith('upstream_')?'Bu bölümün video kaynağı sağlayıcıdan gelmedi. Başka bir bölüm deneyebilir veya daha sonra yeniden açabilirsin.':state.status?.ffmpeg?'Alternatif oynatma seçenekleriyle tekrar deneyebilirsin.':'FFmpeg kurulumu tamamlandığında alternatif oynatma seçenekleri kullanılabilir.';showPlayerControls();}
function saveProgress(keepalive=false){
  const player=state.player;
  if(!player||player.localFile||player.item.kind==='live'||!player.ready)return;
  const duration=player.duration||0, current=actualPlaybackPosition(player);
  if(!Number.isFinite(current)||(!player.ended&&current<1))return;
  const position=duration?Math.min(player.ended?duration:current,duration):current;
  const completed=player.ended||(duration>0&&position/duration>=.95);
  player.item.progress={position,duration,completed,updatedAt:new Date().toISOString()};
  const send=()=>fetch('/api/progress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:player.id,position,duration,completed,sessionId:player.sessionId}),keepalive}).catch(()=>{});
  const previous=player.progressWrite;
  const write=previous?previous.then(send):send();
  player.progressWrite=write;
  write.finally(()=>{if(player.progressWrite===write)player.progressWrite=null;});
  return write;
}
function hideBuffering(){clearTimeout(state.waitingTimer);state.waitingTimer=null;if(!$('#playerOverlay').classList.contains('error'))$('#playerOverlay').hidden=true;$('#playerOverlay').classList.remove('buffering');}
function mediaRanges(ranges){const result=[];for(let i=0;i<(ranges?.length||0);i++){try{result.push([ranges.start(i),ranges.end(i)]);}catch{}}return result;}
function updateSeekDisplay(player=state.player){
  if(!player||state.player!==player)return;
  const video=$('#video'),visible=player.item.kind!=='live'&&player.duration>0;
  $('#absoluteSeek').hidden=!visible;if(!visible)return;
  const pos=Math.min(player.duration,player.seekTarget??actualPlaybackPosition(player,video));
  const ranges=mediaRanges(video.buffered),range=ranges.find(([a,b])=>video.currentTime>=a-.25&&video.currentTime<=b+.25);
  const ahead=range?Math.max(0,range[1]-video.currentTime):0;
  $('#seekBufferStatus').textContent=ahead>=1?`${Math.floor(ahead)} sn hazır`:'';
  const slider=$('#seekRange');
  slider.max=String(player.duration);
  if(!player.scrubbing)slider.value=String(pos);
  const shown=player.scrubbing?Number(slider.value):pos;
  const label=`${time(shown)} / ${time(player.duration)}`;
  $('#seekTime').textContent=label;
  slider.setAttribute('aria-valuetext',label);
  const p=Math.min(100,shown/player.duration*100),end=Math.min(100,Math.max(shown,pos+ahead)/player.duration*100);
  slider.style.background=`linear-gradient(to right,#7c3aed 0%,#7c3aed ${p}%,#ffffff86 ${p}%,#ffffff86 ${end}%,#ffffff59 ${end}%,#ffffff59 100%)`;
}
async function pingPlayback(player=state.player){
  if(!player?.sessionId||player.localFile||state.player!==player)return;
  try{await api(`/api/play/${encodeURIComponent(player.sessionId)}/ping`,{method:'POST',body:{position:Math.max(0,Number($('#video').currentTime)||0)}});}
  catch(error){if(error.status===410&&state.player===player)interruptPlayback('Başka bir cihazda oynatma başlatılmış veya oturum sona ermiş olabilir. Yeniden başlatmak için bir oynatma seçeneğine dokun.');}
}
async function seekTo(position){
  const player=state.player;if(!player||player.item.kind==='live')return;
  const video=$('#video'),target=Math.max(0,Math.min(Number(position)||0,player.duration?Math.max(0,player.duration-.1):Infinity));
  const relative=target-player.offset;
  player.scrubbing=false;player.seekTarget=null;
  player.ended=false;player.endProgress=null;clearEpisodeEnding(player);
  const available=[...mediaRanges(video.buffered),...mediaRanges(video.seekable)];
  if(player.ready&&!$('#playerOverlay').classList.contains('error')&&(player.mode==='direct'||relative>=0&&available.some(([a,b])=>relative>=a&&relative<b-.15))){
    try {
      video.currentTime=relative;hideBuffering();updateSeekDisplay(player);updateTransport(player);pingPlayback(player);saveProgress();return;
    } catch {
      if(player.mode==='direct'&&!state.status?.ffmpeg)throw new Error('Bu yayın istenen konuma sarılamadı.');
    }
  }
  const options={...(window.MavieTracks?.options(player)||player.trackOptions||{}),paused:player.ready&&video.paused===true&&!$('#playerOverlay').classList.contains('error')};
  const mode=player.mode==='direct'&&player.ready&&state.status?.ffmpeg?'remux':player.mode;
  await playItem(player.id,mode,target,player.fallbackUsed,options);
}
function requestSeek(position,immediate=false){
  const player=state.player;if(!player||player.item.kind==='live')return;
  clearTimeout(state.seekTimer);player.seekTarget=position;player.scrubbing=true;
  clearEpisodeEnding(player);showPlayerControls(player);
  $('#seekRange').value=String(position);updateSeekDisplay(player);
  const run=()=>{state.seekTimer=null;if(state.player===player)seekTo(position).catch(error=>notify(error.message,true));};
  if(immediate)run();else state.seekTimer=setTimeout(run,220);
}
function skipPlayback(delta){const p=state.player;if(p)requestSeek(Math.max(0,Math.min(p.duration||Infinity,(p.seekTarget??actualPlaybackPosition(p))+delta)));}
async function stopPlayer(close=true,persist=true){
  const player=state.player;
  if(close)state.playGeneration++;
  clearTimeout(state.seekTimer);state.seekTimer=null;
  clearTimeout(player?.controlsTimer);
  clearEpisodeEnding(player);
  hideBuffering();
  if(!player){if(close)closeDialog('playerDialog');return;}
  player.mediaBound=false;
  const progress=persist&&!player.localFile?(player.endProgress||saveProgress(true)):null;
  clearInterval(state.progressTimer);clearInterval(state.pingTimer);state.progressTimer=null;state.pingTimer=null;state.player=null;
  if(state.hls){state.hls.destroy();state.hls=null;}
  const video=$('#video');
  video.pause();video.removeAttribute('src');video.load();
  if(player.blobUrl&&typeof URL!=='undefined'&&URL.revokeObjectURL)URL.revokeObjectURL(player.blobUrl);
  if(player.sessionId){
    const release=()=>fetch(`/api/play/${encodeURIComponent(player.sessionId)}`,{method:'DELETE',keepalive:true}).catch(()=>{});
    if(progress)progress.finally(release);else release();
  }
  if(close){
    if(playerFullscreenElement())exitPlayerFullscreen().catch(()=>{});
    closeDialog('playerDialog');if(state.route==='home')render();
  }
}
function playerFullscreenElement(){
  return document.fullscreenElement||document.webkitFullscreenElement;
}
async function exitPlayerFullscreen(){
  const exit=document.exitFullscreen||document.webkitExitFullscreen;
  if(exit)await exit.call(document);
}
function bindPlayer(){
  const video=$('#video');
  const dialog=$('#playerDialog');
  if(dialog.dataset.bound==='1')return;
  dialog.dataset.bound='1';
  const currentPlayer=()=>{const p=state.player;return p?.mediaBound&&!p.retrying?p:null;};
  const readDuration=()=>{
    const p=currentPlayer();
    if(p&&'playbackRate'in video&&state.playbackRate&&state.playbackRate!==1)video.playbackRate=state.playbackRate;
    if(p?.mode==='direct'&&p.item.kind!=='live'&&Number.isFinite(video.duration)&&video.duration>0){
      p.duration=video.duration;updateSeekDisplay(p);
    }
  };
  const togglePlay=()=>{
    const p=state.player;if(!p||p.retrying)return;
    showPlayerControls(p);
    if(p.ended)replayPlayer(p)?.catch(error=>notify(error.message,true));
    else if($('#playerOverlay').classList.contains('error'))playItem(p.id,p.mode,actualPlaybackPosition(p)).catch(error=>notify(error.message,true));
    else if(p.ready&&video.paused){p.restorePaused=false;playVideo(p);}
    else if(p.ready)video.pause();
  };
  // Dialog elements cannot themselves enter fullscreen. Use an inner surface
  // containing both the video and controls, without fullscreening the catalog.
  const fullscreenRoot=$('#playerSurface');
  const requestFullscreen=fullscreenRoot?.requestFullscreen||fullscreenRoot?.webkitRequestFullscreen;
  const fullscreen=async()=>{
    try{
      if(playerFullscreenElement())await exitPlayerFullscreen();
      else if(requestFullscreen)await requestFullscreen.call(fullscreenRoot);
    }catch{
      notify('Tam ekrana geçilemedi. Yeniden deneyin.',true);
    }
    showPlayerControls();
  };
  video.addEventListener('durationchange',readDuration);
  video.addEventListener('loadedmetadata',()=>{const p=currentPlayer();if(!p)return;p.ready=true;readDuration();if(!p.positioned){p.positioned=true;try{if(p.mode==='direct'&&p.start>0&&p.offset===0)video.currentTime=Math.min(p.start, p.duration?Math.max(0,p.duration-.1):Infinity);else if(p.mode!=='direct'&&p.item.kind!=='live')video.currentTime=0;}catch{}}updateSeekDisplay(p);updateTransport(p);playVideo(p);});
  video.addEventListener('playing',()=>{const p=currentPlayer();if(!p)return;p.ready=true;$('#playerOverlay').classList.remove('error');hideBuffering();$('#playerHint').textContent=playbackHint(p.mode);updateSeekDisplay(p);updateTransport(p);showPlayerControls(p);});
  video.addEventListener('waiting',()=>{const p=currentPlayer();if(!p||!p.ready||video.currentTime<=0)return;clearTimeout(state.waitingTimer);state.waitingTimer=setTimeout(()=>{if(state.player!==p||video.paused||video.readyState>=3)return;$('#playerOverlay').hidden=false;$('#playerOverlay').classList.remove('error');$('#playerOverlay').classList.add('buffering');$('#playerMessage').textContent='Yayın yükleniyor…';},450);});
  video.addEventListener('canplay',()=>{if(currentPlayer())hideBuffering();});
  video.addEventListener('error',()=>{const p=currentPlayer();if(p&&video.error)playbackFailed(p,'Video ya da ses biçimi tarayıcıyla uyumlu olmayabilir. Aşağıdaki alternatif oynatma seçeneklerinden birini dene.');});
  video.addEventListener('pause',()=>{const p=currentPlayer();if(!p)return;saveProgress();updateTransport(p);showPlayerControls(p);if(p.sessionId&&p.mode!=='direct')api(`/api/play/${encodeURIComponent(p.sessionId)}/pause`,{method:'POST',body:{paused:true}}).catch(()=>{});});
  video.addEventListener('play',()=>{const p=currentPlayer();if(!p)return;p.restorePaused=false;updateTransport(p);if(p.sessionId&&p.mode!=='direct')api(`/api/play/${encodeURIComponent(p.sessionId)}/pause`,{method:'POST',body:{paused:false}}).catch(()=>{});});
  video.addEventListener('ended',()=>{const p=currentPlayer();if(p)playerEnded(p);});
  video.addEventListener('volumechange',()=>updateTransport());
  video.addEventListener('timeupdate',()=>{if(currentPlayer())updateSeekDisplay();});
  video.addEventListener('progress',()=>{if(currentPlayer())updateSeekDisplay();});
  video.addEventListener('seeked',()=>{if(currentPlayer()){updateSeekDisplay();pingPlayback();}});
  $('#closePlayer').addEventListener('click',()=>stopPlayer());
  dialog.addEventListener('cancel',event=>{
    event.preventDefault();
    if(playerPanels.some(([panel])=>!$(panel).hidden)){setPlayerPanel();showPlayerControls();}
    else if(state.player?.endingTimer)cancelEpisodeCountdown(state.player);
    else stopPlayer();
  });
  dialog.addEventListener('pointermove',()=>showPlayerControls());
  dialog.addEventListener('focusin',()=>showPlayerControls());
  dialog.addEventListener('click',event=>{
    if(event.target===video){
      if(playerPanels.some(([panel])=>!$(panel).hidden))setPlayerPanel();
      else if(event.pointerType!=='touch'&&!dialog.classList.contains('controls-hidden'))togglePlay();
      showPlayerControls();
    }
  });
  $('#seekRange').addEventListener('input',()=>{if(state.player){state.player.scrubbing=true;clearEpisodeEnding(state.player);updateSeekDisplay(state.player);showPlayerControls();}});
  $('#seekRange').addEventListener('change',e=>requestSeek(Number(e.target.value),true));
  $('#skipBack')?.addEventListener('click',()=>skipPlayback(-10));
  $('#skipForward')?.addEventListener('click',()=>skipPlayback(10));
  for(const [panel,trigger] of playerPanels)$(trigger)?.addEventListener('click',()=>{
    const opening=$(panel).hidden;
    setPlayerPanel(opening?panel:'');
    if(opening&&panel==='#episodeDrawerPanel'&&state.player)populateEpisodeDrawer(state.player);
    showPlayerControls();
  });
  setPlayerPanel();
  $('#speedSelect')?.addEventListener('change',e=>{
    const rate=Math.max(0.5,Math.min(2,Number(e.target.value)||1));
    state.playbackRate=rate;
    if('playbackRate' in video)video.playbackRate=rate;
    showPlayerOsd(`Hız: ${rate}x`);
  });
  $('#fitButton')?.addEventListener('click',()=>{
    state.videoCover=!state.videoCover;
    video.classList?.toggle('video-cover',state.videoCover);
    showPlayerOsd(state.videoCover?'Ekran: Doldur':'Ekran: Sığdır');
  });
  $('#subtitleScaleSelect')?.addEventListener('change',e=>{
    const scale=e.target.value||'1';
    $('#playerSurface')?.style?.setProperty?.('--cue-scale',scale);
    showPlayerOsd(`Altyazı boyutu: ${e.target.selectedOptions?.[0]?.textContent||scale}`);
  });
  $('#pipButton')?.addEventListener('click',async()=>{
    try{
      if(document.pictureInPictureElement)await document.exitPictureInPicture();
      else if(video.requestPictureInPicture)await video.requestPictureInPicture();
    }catch(error){notify(error.message||'Resim içinde resim açılamadı.',true);}
  });
  $('#sleepPanel')?.addEventListener('click',e=>{
    const btn=e.target.closest?.('[data-sleep]');
    if(!btn)return;
    setSleepTimer(Number(btn.dataset.sleep));
    setPlayerPanel();
  });
  video.addEventListener('dblclick',()=>{if(requestFullscreen)fullscreen();});
  $('#togglePlay').addEventListener('click',togglePlay);
  $('#mutePlayer').addEventListener('click',()=>{if(video.volume===0)video.volume=1;else video.muted=!video.muted;});
  $('#playerVolume').addEventListener('input',event=>{video.volume=Number(event.target.value);video.muted=false;});
  $('#cancelNextEpisode').addEventListener('click',()=>{const p=currentPlayer();if(!p)return;if(p.endingTimer)cancelEpisodeCountdown(p);else replayPlayer(p)?.catch(error=>notify(error.message,true));});
  for(const id of ['#playNextEpisode','#nextEpisodeShortcut'])$(id).addEventListener('click',()=>{const p=currentPlayer();if(p)openNextEpisode(p).catch(error=>notify(error.message,true));});
  document.addEventListener('keydown',event=>{
    const active=document.activeElement;
    if(!state.player||!dialog.open||event.altKey||event.ctrlKey||event.metaKey||(active!==$('#seekRange')&&['INPUT','TEXTAREA','SELECT'].includes(active?.tagName)))return;
    const key=event.key.toLowerCase();
    if(event.key==='ArrowLeft'||event.key==='ArrowRight'){
      event.preventDefault();skipPlayback(event.key==='ArrowLeft'?-10:10);
    }else if(event.key==='ArrowUp'||event.key==='ArrowDown'){
      event.preventDefault();
      const nextVol=Math.max(0,Math.min(1,(Number(video.volume)||1)+(event.key==='ArrowUp'?0.1:-0.1)));
      video.volume=Math.round(nextVol*100)/100;video.muted=video.volume===0;
      showPlayerOsd(`Ses: %${Math.round(video.volume*100)}`);
    }else if((event.code==='Space'||key==='k')&&!['BUTTON','INPUT'].includes(active?.tagName)){
      event.preventDefault();togglePlay();
    }else if(key==='m'){
      event.preventDefault();if(video.volume===0)video.volume=1;else video.muted=!video.muted;
      showPlayerOsd(video.muted?'Ses kapalı':`Ses: %${Math.round(video.volume*100)}`);
    }else if(key==='['||key===']'){
      event.preventDefault();
      const steps=[0.5,0.75,1,1.25,1.5,2];
      const idx=steps.indexOf(Number(state.playbackRate)||1);
      const next=steps[Math.max(0,Math.min(steps.length-1,(idx<0?2:idx)+(key===']'?1:-1)))];
      state.playbackRate=next;if('playbackRate' in video)video.playbackRate=next;
      if($('#speedSelect'))$('#speedSelect').value=String(next);
      showPlayerOsd(`Hız: ${next}x`);
    }else if(key==='f'){
      event.preventDefault();fullscreen();
    }else return;
    showPlayerControls();
  });
  document.querySelectorAll('[data-mode]').forEach(b=>b.addEventListener('click',()=>{const p=state.player;if(p)playItem(p.id,b.dataset.mode,actualPlaybackPosition(p)).catch(error=>notify(error.message,true));}));
  $('#fullscreenButton').hidden=!requestFullscreen;
  $('#fullscreenButton').addEventListener('click',fullscreen);
  const updateFullscreen=()=>{
    playbackButton($('#fullscreenButton'),playerFullscreenElement()?'Tam ekrandan çık':'Tam ekran');
    showPlayerControls();
  };
  document.addEventListener('fullscreenchange',updateFullscreen);
  document.addEventListener('webkitfullscreenchange',updateFullscreen);
  window.addEventListener('pagehide',()=>{saveProgress(true);const p=state.player;if(p?.sessionId)fetch(`/api/play/${encodeURIComponent(p.sessionId)}`,{method:'DELETE',keepalive:true}).catch(()=>{});clearMultiView();});
}
function clearMultiView(){
  for(const h of state.multiHls||[]){try{h.destroy();}catch{}}
  state.multiHls=[];
  for(const sid of state.multiSids||[]){
    fetch(`/api/play/${encodeURIComponent(sid)}`,{method:'DELETE',keepalive:true}).catch(()=>{});
  }
  state.multiSids=[];
  document.querySelectorAll('.multiview-tile video').forEach(v=>{
    try{v.pause();v.removeAttribute('src');v.load();}catch{}
  });
}
async function renderMultiView(token){
  clearMultiView();
  const main=$('#main');
  main.innerHTML=pageHeading('Çoklu Ekran (2×2)','Aynı anda dört canlı kanalı izle; istediğin birinin sesini aç.','CANLI MOZAİK')+loading();
  if(!state.cloudStatus){
    try{state.cloudStatus=await api('/api/cloud/status');}catch{}
  }
  const data=await api('/api/catalog?kind=live&limit=100&page=1');
  if(token!==state.renderId)return;
  const channels=remember(data.items||[]);
  const isLinkedNormal=Boolean((state.cloudStatus?.user||state.cloudStatus?.signedIn)&&!state.cloudStatus?.isPro&&state.cloudStatus?.effectivePlan!=='pro');
  const proCallout=isLinkedNormal?`<div class="cloud-upgrade-callout" role="status"><span><strong>Pro Özellik:</strong> Çoklu Ekran (2×2) yalnızca Pro planda kullanılabilir. Normal planda tek kanal oynatma açıktır.</span><a class="button small" href="#settings">Pro’ya Yükselt</a></div>`:'';
  if(!channels.length){
    main.innerHTML=pageHeading('Çoklu Ekran (2×2)','Aynı anda dört canlı kanalı izle.','CANLI MOZAİK')+proCallout+empty('Canlı kanal bulunamadı','Çoklu ekran için canlı TV kanalı içeren bir M3U veya Xtream kaynağı bağla.','live');
    return;
  }
  const initial=[0,1,2,3].map(i=>channels[i%channels.length]);
  const optionsHtml=(selId)=>channels.map(ch=>`<option value="${esc(ch.id)}" ${ch.id===selId?'selected':''}>${esc(ch.name)}</option>`).join('');
  main.innerHTML=pageHeading('Çoklu Ekran (2×2)','Otomatik oynatma kuralları gereği başlangıçta sessiz açılır; ses simgesiyle tek kanalı dinleyebilirsin.','CANLI MOZAİK')
    +proCallout
    +`<div class="multiview-grid">${initial.map((ch,idx)=>`<article class="multiview-tile" data-mv-idx="${idx}"><div class="multiview-video-wrap"><video id="mvVideo${idx}" muted playsinline autoplay></video></div><div class="multiview-bar"><select class="sort-select" data-mv-select="${idx}" aria-label="Kanal ${idx+1}">${optionsHtml(ch.id)}</select><div class="multiview-actions"><button type="button" class="icon-button" data-mv-mute="${idx}" title="Sesi aç" aria-label="Sesi aç" aria-pressed="false">${icon('volumeOff')}</button><button type="button" class="icon-button" data-mv-full="${idx}" title="Tam oynatıcıda aç" aria-label="Tam oynatıcıda aç">${icon('expand')}</button></div></div></article>`).join('')}</div>`;
  const slots=initial.map(ch=>({id:ch.id,sid:null,hls:null}));
  let proToastShown=false;
  const loadSlot=async(idx,itemId)=>{
    const slot=slots[idx];
    if(slot.hls){try{slot.hls.destroy();}catch{}slot.hls=null;}
    if(slot.sid){
      state.multiSids=(state.multiSids||[]).filter(id=>id!==slot.sid);
      fetch(`/api/play/${encodeURIComponent(slot.sid)}`,{method:'DELETE',keepalive:true}).catch(()=>{});
      slot.sid=null;
    }
    const vid=$(`#mvVideo${idx}`);
    if(!vid||token!==state.renderId)return;
    try{
      const res=await api('/api/play',{method:'POST',body:{id:itemId,mode:'direct',start:0,multiview:true,multiviewSlot:idx}});
      if(token!==state.renderId){if(res.sessionId)fetch(`/api/play/${encodeURIComponent(res.sessionId)}`,{method:'DELETE',keepalive:true}).catch(()=>{});return;}
      slot.id=itemId;slot.sid=res.sessionId;
      if(res.sessionId){state.multiSids=state.multiSids||[];state.multiSids.push(res.sessionId);}
      if(res.type==='hls'&&typeof Hls!=='undefined'&&Hls.isSupported()&&!vid.canPlayType('application/vnd.apple.mpegurl')){
        const h=new Hls({lowLatencyMode:true});h.loadSource(res.url);h.attachMedia(vid);slot.hls=h;state.multiHls.push(h);
      }else{
        vid.src=res.url;
      }
      vid.play().catch(()=>{});
    }catch(err){
      if(err.code==='PRO_REQUIRED'){if(!proToastShown){proToastShown=true;notify(err.message,true);}return;}
      notify(`${itemFor(itemId)?.name||'Kanal'}: ${err.message}`,true);
    }
  };
  slots.forEach((_,idx)=>loadSlot(idx,slots[idx].id));
  main.querySelectorAll('[data-mv-select]').forEach(sel=>sel.addEventListener('change',()=>loadSlot(Number(sel.dataset.mvSelect),sel.value)));
  main.querySelectorAll('[data-mv-mute]').forEach(btn=>btn.addEventListener('click',()=>{
    const targetIdx=Number(btn.dataset.mvMute);
    const targetVid=$(`#mvVideo${targetIdx}`);
    const unmute=targetVid.muted;
    slots.forEach((_,i)=>{
      const v=$(`#mvVideo${i}`),b=main.querySelector(`[data-mv-mute="${i}"]`);
      if(v){v.muted=i!==targetIdx||!unmute;}
      if(b){
        const isUnmuted=Boolean(v&&!v.muted);
        b.innerHTML=icon(isUnmuted?'volumeOn':'volumeOff');
        b.setAttribute('aria-pressed',String(isUnmuted));
        b.setAttribute('aria-label',isUnmuted?'Sesi kapat':'Sesi aç');
        b.title=isUnmuted?'Sesi kapat':'Sesi aç';
      }
    });
  }));
  main.querySelectorAll('[data-mv-full]').forEach(btn=>btn.addEventListener('click',()=>{
    const id=slots[Number(btn.dataset.mvFull)]?.id;
    clearMultiView();
    if(id)playItem(id).catch(e=>notify(e.message,true));
  }));
}
async function playLocalFile(file){
  if(!file||typeof URL==='undefined'||!URL.createObjectURL)return;
  if(state.player)await stopPlayer(false);
  const url=URL.createObjectURL(file);
  const player={id:'local:'+file.name,item:{id:'local',name:file.name.replace(/\.[^.]+$/,''),kind:'vod'},mode:'direct',start:0,offset:0,duration:0,sessionId:null,ready:true,mediaBound:true,localFile:true,blobUrl:url};
  state.player=player;
  $('#playerTitle').textContent=player.item.name;
  $('#playerEyebrow').textContent='YEREL DOSYA';
  $('#playerOverlay').hidden=true;$('#playerOverlay').classList.remove('error');
  setPlayerPanel();
  updateTransport(player);
  showPlayerControls(player);
  openDialog('playerDialog');
  const video=$('#video');
  video.src=url;
  video.onloadedmetadata=()=>{if(state.player===player&&Number.isFinite(video.duration)){player.duration=video.duration;updateSeekDisplay(player);}};
  video.play().catch(()=>{});
}
async function pickSurprise(){
  const res=await api('/api/surprise');
  if(!res?.item)throw new Error('Önerilecek içerik bulunamadı.');
  remember([res.item]);
  notify(`Sürpriz seçim: ${res.item.name}`);
  if(res.item.kind==='series')return openDetail(res.item.id);
  return playItem(res.item.id);
}
async function openProfilesDialog(){
  const data=await api('/api/profiles');
  const profiles=data.profiles||[];
  const colors=['#7C3AED','#06B6D4','#34C759','#5E5CE6','#0A84FF','#BF5AF2'];
  $('#listContent').innerHTML=`<h2>Profiller</h2><p>Her profilin kendi favorileri, listeleri ve kaldığı yeri ayrı saklanır.</p>
    <div class="profile-grid">${profiles.map(p=>`<button type="button" class="profile-tile ${p.active?'active':''}" data-pick-profile="${esc(p.id)}" data-has-pin="${p.hasPin?'1':'0'}">
      <div class="profile-tile-avatar" style="background:${esc(p.avatarColor)}">${esc((p.name||'P').charAt(0).toUpperCase())}</div>
      <strong>${esc(p.name)}</strong>
      ${p.isKids?'<span class="profile-badge-kid">Çocuk Modu</span>':''}
      ${p.hasPin?`<span class="profile-pin-tag">${icon('shield')} PIN Korumalı</span>`:''}
      ${p.id!=='default'?`<span class="profile-delete-btn" data-del-profile="${esc(p.id)}" title="Profili sil" aria-label="Profili sil">${icon('close')}</span>`:''}
    </button>`).join('')}</div>
    <div id="pinPromptBox" class="field" hidden><label for="switchPinInput">Profil PIN kodu</label><div style="display:flex;gap:8px"><input id="switchPinInput" type="password" inputmode="numeric" maxlength="8" placeholder="PIN"><button type="button" class="button" id="confirmPinBtn">Geç</button></div><div id="profileError" class="inline-error" role="alert"></div></div>
    <form id="createProfileForm" class="profile-form">
      <strong>Yeni Profil Ekle</strong>
      <div class="field-row">
        <div class="field"><label for="newProfileName">Profil adı</label><input id="newProfileName" maxlength="40" placeholder="Örneğin: Çocuklar" required></div>
        <div class="field"><label for="newProfilePin">PIN (isteğe bağlı, 4-8 rakam)</label><input id="newProfilePin" type="password" inputmode="numeric" pattern="[0-9]{4,8}" placeholder="Boş bırakılabilir"></div>
      </div>
      <div class="field-row" style="align-items:center">
        <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="newProfileKids"> Çocuk Profili (+18 / Korku gizlenir)</label>
        <select id="newProfileColor" aria-label="Profil rengi">${colors.map(col=>`<option value="${col}">${col}</option>`).join('')}</select>
      </div>
      <button type="submit" class="button">${icon('plus')}Profil Oluştur</button>
      <div id="createProfileError" class="inline-error" role="alert"></div>
    </form>`;
  openDialog('listDialog');
  let pendingPinProfile='';
  const doSwitch=async(id,pin='')=>{
    const res=await api('/api/profiles/switch',{method:'POST',body:{id,pin}});
    state.status=await api('/api/status');
    closeDialog('listDialog');
    notify(`${res.profile?.name||'Profil'} aktif edildi.`);
    render();
  };
  $('#listContent').querySelectorAll('[data-del-profile]').forEach(el=>el.addEventListener('click',async e=>{
    e.stopPropagation();
    const id=el.dataset.delProfile;
    try{
      await api(`/api/profiles/${encodeURIComponent(id)}`,{method:'DELETE'});
      openProfilesDialog();
    }catch(err){notify(err.message,true);}
  }));
  $('#listContent').querySelectorAll('[data-pick-profile]').forEach(btn=>btn.addEventListener('click',async()=>{
    const id=btn.dataset.pickProfile;
    if(btn.dataset.hasPin==='1'){
      pendingPinProfile=id;
      $('#pinPromptBox').hidden=false;
      $('#profileError').textContent='';
      $('#switchPinInput').value='';
      $('#switchPinInput').focus();
      return;
    }
    try{await doSwitch(id,'');}catch(err){notify(err.message,true);}
  }));
  $('#confirmPinBtn')?.addEventListener('click',async()=>{
    try{await doSwitch(pendingPinProfile,$('#switchPinInput').value);}catch(err){$('#profileError').textContent=err.message;}
  });
  $('#createProfileForm')?.addEventListener('submit',async e=>{
    e.preventDefault();
    $('#createProfileError').textContent='';
    try{
      await api('/api/profiles',{method:'POST',body:{
        name:$('#newProfileName').value.trim(),
        pin:$('#newProfilePin').value.trim(),
        isKids:$('#newProfileKids').checked,
        avatarColor:$('#newProfileColor').value,
      }});
      openProfilesDialog();
    }catch(err){$('#createProfileError').textContent=err.message;}
  });
}
const actions={reload:async()=>{state.status=await api('/api/status');render();},surprise:()=>pickSurprise(),'open-local-file':()=>$('#localFilePicker')?.click(),'open-profiles':()=>openProfilesDialog(),demo:async()=>{await api('/api/demo',{method:'POST',body:{}});state.status=await api('/api/status');notify('Açık Sinema demo kütüphanesi hazır.');routeTo('home');if(state.route==='home')render();},sync:()=>syncCatalog(),detail:el=>{closeDialog('listDialog');return openDetail(el.dataset.id);},play:el=>playItem(el.dataset.id),favorite:el=>toggleFavorite(el.dataset.id),'item-menu':el=>itemMenu(el.dataset.id),'add-list':el=>addToListDialog(el.dataset.id),'create-list':el=>listNameDialog('',el.dataset.item||''),'rename-list':el=>listNameDialog(el.dataset.list),'open-list':el=>routeTo('playlists/'+encodeURIComponent(el.dataset.list)),'select-list':async el=>{await api(`/api/playlists/${encodeURIComponent(el.dataset.list)}`,{method:'PATCH',body:{itemId:el.dataset.id}});closeDialog('listDialog');notify('İçerik listene eklendi.');if(state.route.startsWith('playlists'))render();},'remove-from-list':async el=>{await api(`/api/playlists/${encodeURIComponent(el.dataset.list)}`,{method:'PATCH',body:{removeItemId:el.dataset.id}});notify('İçerik listeden kaldırıldı.');render();},'delete-list':el=>confirmDialog('Listeyi sil?','Bu liste kaldırılacak. İçerikler ve izleme kayıtları kütüphanende kalır.',async()=>{await api(`/api/playlists/${encodeURIComponent(el.dataset.list)}`,{method:'DELETE'});routeTo('playlists');notify('Liste silindi.');},'Listeyi sil'),reorder:async el=>{const list=state.playlists.find(l=>String(l.id)===el.dataset.list);if(!list)return;const ids=(list.items||[]).map(i=>i.id),i=ids.indexOf(el.dataset.id),j=i+Number(el.dataset.direction);if(i<0||j<0||j>=ids.length)return;[ids[i],ids[j]]=[ids[j],ids[i]];await api(`/api/playlists/${encodeURIComponent(list.id)}`,{method:'PATCH',body:{order:ids}});render();},category:el=>changeCatalog({category:el.dataset.category,page:1}),page:el=>{changeCatalog({page:el.dataset.page});window.scrollTo({top:0,behavior:'smooth'});},'reset-filters':()=>routeTo(state.route),'clear-search':()=>changeCatalog({q:'',page:1}),'favorite-filter':el=>routeTo('favorites',{kind:el.dataset.kind}),'clear-progress':el=>clearProgress(el.dataset.id),export:()=>exportBackup(),import:()=>$('#importFile').click(),copy:async el=>{const value=el.dataset.value;if(navigator.clipboard?.writeText){try{await navigator.clipboard.writeText(value);notify('Adres kopyalandı.');return;}catch{}}const field=document.createElement('textarea');field.value=value;document.body.append(field);field.select();const copied=document.execCommand('copy');field.remove();notify(copied?'Adres kopyalandı.':`Adres: ${value}`,!copied);}};
document.addEventListener('click',async event=>{const close=event.target.closest('[data-close]');if(close){closeDialog(close.dataset.close);return;}const el=event.target.closest('[data-action]');if(!el||el.disabled)return;const action=actions[el.dataset.action];if(!action)return;try{await action(el);}catch(error){notify(error.message,true);}});
document.addEventListener('error',event=>{if(event.target instanceof HTMLImageElement){event.target.hidden=true;event.target.style.display='none';}},true);
['detailDialog','listDialog'].forEach(id=>{$('#'+id).addEventListener('click',event=>{if(event.target===event.currentTarget){const rect=event.currentTarget.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)closeDialog(id);}});});
$('#syncButton').addEventListener('click',()=>syncCatalog().catch(error=>notify(error.message,true)));
$('#searchForm').addEventListener('submit',event=>{event.preventDefault();const q=$('#searchInput').value.trim();if(q)routeTo('search',{q});else routeTo('home');});
document.addEventListener('keydown',event=>{if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)&&!document.querySelector('dialog[open]')){event.preventDefault();$('#searchInput').focus();}});
window.addEventListener('hashchange',()=>{window.scrollTo(0,0);render();});
async function pollStatus(){if(document.hidden||state.player)return;try{const previous=state.status;const next=await api('/api/status');state.status=next;updateShell();if(previous?.catalog?.syncing&&!next.catalog?.syncing){notify(next.catalog?.error?'Eşitleme tamamlanamadı: '+next.catalog.error:'Kütüphanen güncel.',!!next.catalog?.error);render();}else if(previous?.configured!==next.configured||previous?.authorized!==next.authorized||previous?.catalog?.updatedAt!==next.catalog?.updatedAt)render();else if(state.route==='favorites'&&!document.querySelector('dialog[open]')&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){const data=await api('/api/favorites');const sig=JSON.stringify(data.items||[]);if(state.route==='favorites'&&$('#main').dataset.favSignature!==sig){$('#main').dataset.favSignature=sig;renderFavorites(data.items||[]);}}else if(state.route.startsWith('playlists')&&!document.querySelector('dialog[open]')&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){const data=await api('/api/playlists');const sig=JSON.stringify(data.playlists||[]);if(state.route.startsWith('playlists')&&$('#main').dataset.listSignature!==sig){$('#main').dataset.listSignature=sig;state.playlists=data.playlists||[];renderPlaylists();}}else if(state.route==='home'&&!document.querySelector('dialog[open]')){const data=await api('/api/home');if(state.route==='home')renderHome(data);}}catch{/* Leave the current screen usable during a temporary disconnect. */}}
async function init(){
  hydrateIcons();bindPlayer();window.MavieTracks?.bind();
  $('#localFilePicker')?.addEventListener('change',e=>{const f=e.target.files?.[0];if(f)playLocalFile(f);e.target.value='';});
  let dragDepth=0;
  document.addEventListener('dragenter',e=>{if(e.dataTransfer?.types?.includes('Files')){dragDepth++;if($('#dropOverlay'))$('#dropOverlay').hidden=false;}});
  document.addEventListener('dragover',e=>{if(e.dataTransfer?.types?.includes('Files'))e.preventDefault();});
  document.addEventListener('dragleave',()=>{dragDepth=Math.max(0,dragDepth-1);if(!dragDepth&&$('#dropOverlay'))$('#dropOverlay').hidden=true;});
  document.addEventListener('drop',e=>{
    const f=e.dataTransfer?.files?.[0];
    dragDepth=0;if($('#dropOverlay'))$('#dropOverlay').hidden=true;
    if(f&&(/\.(mp4|mkv|avi|mov|m4v|webm|ts)$/i.test(f.name)||f.type?.startsWith('video/'))){e.preventDefault();playLocalFile(f);}
  });
  try{state.status=await api('/api/status');await render();}catch(error){$('#main').innerHTML=empty('Mavie sunucusuna ulaşamadık',error.message,'alert',button('Tekrar bağlan','reload'));}setInterval(pollStatus,15000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollStatus();});if('serviceWorker'in navigator&&window.isSecureContext)navigator.serviceWorker.register('/sw.js').catch(()=>{});
}
init();
