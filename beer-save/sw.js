const CACHE='beer-save-phase2-v1';
const PREFIX='beer-save-';
const ASSETS=['./','./index.html','./log.html','./beer-core.js','./beer-store.js','./manifest.webmanifest','./icon.svg'];
const ROOT=new URL('./',self.location.href);
const URLS=new Set(ASSETS.map(path=>new URL(path,ROOT).href));
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith(PREFIX)&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);url.search='';url.hash='';
  if(event.request.method!=='GET'||url.origin!==ROOT.origin||!URLS.has(url.href))return;
  const cacheKey=url.pathname===ROOT.pathname?new URL('./index.html',ROOT).href:url.href;
  event.respondWith(fetch(event.request).then(response=>{
    if(response.ok){const copy=response.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(cacheKey,copy)));}
    return response;
  }).catch(()=>caches.open(CACHE).then(cache=>cache.match(cacheKey)).then(response=>response||Response.error())));
});
