const cacheName = 'jupiter-regional-' + BUILD_ID;
const shell = '/mapa-sin-conexion';
const files = OFFLINE_ASSETS;
const publicFiles = new Set(files);
let download;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));

self.addEventListener('message', event => {
  if(event.data !== 'download-regional-map' || !event.ports[0]) return;
  download ??= (async () => {
    const cache = await caches.open(cacheName);
    await cache.addAll(files.map(path => new Request(path, {cache:'reload', credentials:'omit'})));
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key.startsWith('jupiter-regional-') && key !== cacheName)
      .map(key => caches.delete(key)));
  })().finally(() => {download = undefined;});
  event.waitUntil(download.then(() => event.ports[0].postMessage({ready:true}),
    () => event.ports[0].postMessage({ready:false})));
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if(request.method !== 'GET' || url.origin !== self.location.origin) return;
  if(request.mode === 'navigate' && url.pathname === shell) {
    event.respondWith(fetch(request).then(response => {
      if(!response.ok) throw new Error('Red');
      return response;
    }).catch(async () => (await caches.match(shell)) || Response.error()));
  } else if (publicFiles.has(url.pathname) || url.pathname.startsWith('/assets/')) {
    event.respondWith(fetch(request).then(async response => response.ok ? response :
      (await caches.match(url.pathname)) || response).catch(async () => (await caches.match(url.pathname)) || Response.error()));
  }
});
