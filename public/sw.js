const CACHE='mavie-static-v5';
const STATIC=['/','/styles.css','/cinema.css','/player.css','/sports.css','/app.js','/tracks.js','/experience.js','/sports.js','/icon.svg','/mavie-mark.svg','/manifest.webmanifest','/vendor/hls.min.js'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(STATIC)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(e.request.method!=='GET'||u.origin!==location.origin||u.pathname.startsWith('/api/')||u.pathname.startsWith('/media/'))return;
  const isAppShell=!u.pathname.startsWith('/vendor/')&&(e.request.mode==='navigate'||u.pathname==='/'||/\.(?:html|js|css)$/i.test(u.pathname));
  if(isAppShell){
    e.respondWith(
      fetch(e.request).then(res=>{
        if(res&&res.ok){
          const copy=res.clone();
          caches.open(CACHE).then(c=>c.put(e.request,copy)).catch(()=>{});
        }
        return res;
      }).catch(()=>caches.match(e.request).then(cached=>cached||(e.request.mode==='navigate'?caches.match('/'):undefined)))
    );
    return;
  }
  e.respondWith(caches.match(e.request).then(cached=>cached||fetch(e.request)));
});
