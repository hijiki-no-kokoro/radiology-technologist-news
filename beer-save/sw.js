const CACHE='beer-save-live-barcode-20261017-v1';
const PREFIX='beer-save-';
const RUNTIME='beer-ocr-runtime-v1';
const ASSETS=['./','./index.html','./log.html','./beer-core.js','./beer-store.js','./manifest.webmanifest','./icon.svg','./beer-catalog.js','./beer-recognition.js','./beer-photo-engine.js','./beer-camera-ui.js','./beer-live-barcode.js','./beer-session-ui.js','./vendor/zxing-browser-0.2.1.min.js','./vendor/tesseract-7.0.0.min.js','./vendor/tesseract-worker-7.0.0.min.js'];
const ROOT=new URL('./',self.location.href);
const URLS=new Set(ASSETS.map(path=>new URL(path,ROOT).href));
const EXTERNAL=new Set(['jpn','eng'].map(code=>'https://cdn.jsdelivr.net/npm/@tesseract.js-data/'+code+'@1.0.0/4.0.0_best_int/'+code+'.traineddata.gz'));
for(const suffix of ['','-simd','-relaxedsimd','-lstm','-simd-lstm','-relaxedsimd-lstm'])for(const ext of ['.wasm.js','.wasm'])EXTERNAL.add('https://cdn.jsdelivr.net/npm/tesseract.js-core@7.0.0/tesseract-core'+suffix+ext);
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS.map(path=>new Request(new URL(path,ROOT).href,{cache:'reload'})))).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith(PREFIX)&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  if(EXTERNAL.has(event.request.url)){
    event.respondWith(caches.open(RUNTIME).then(async cache=>{const saved=await cache.match(event.request);if(saved)return saved;const response=await fetch(event.request);if(response.ok||response.type==='opaque')event.waitUntil(cache.put(event.request,response.clone()).catch(()=>{}));return response;}));return;
  }
  const url=new URL(event.request.url);url.search='';url.hash='';
  if(url.origin!==ROOT.origin||!URLS.has(url.href))return;
  const cacheKey=url.pathname===ROOT.pathname?new URL('./index.html',ROOT).href:url.href;
  event.respondWith(fetch(event.request).then(response=>{
    if(response.ok){const copy=response.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(cacheKey,copy)));}return response;
  }).catch(()=>caches.open(CACHE).then(cache=>cache.match(cacheKey)).then(response=>response||Response.error())));
});
