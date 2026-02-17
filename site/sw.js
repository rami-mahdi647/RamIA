const CACHE_NAME = 'ramia-cache-v3';
const ASSET_CACHE = 'ramia-assets-v3';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/rent.html',
  '/security.html',
  '/success.html',
  '/cancel.html',
  '/app.js',
  '/manifest.webmanifest',
  '/icons/icon-192.svg',
  '/icons/icon-512.svg'

];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(ASSET_CACHE).then((cache) => cache.addAll(STATIC_ASSETS)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => ![CACHE_NAME, ASSET_CACHE].includes(k)).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const networkResponse = await fetch(req);
        const navCache = await caches.open(CACHE_NAME);
        navCache.put(req, networkResponse.clone());
        return networkResponse;
      } catch {
        const navCache = await caches.open(CACHE_NAME);
        return (await navCache.match(req)) || (await navCache.match('/index.html')) || Response.error();
      }
    })());
    return;
  }

  event.respondWith((async () => {
    const assetCache = await caches.open(ASSET_CACHE);
    const cached = await assetCache.match(req);
    if (cached) return cached;
    const fresh = await fetch(req);
    assetCache.put(req, fresh.clone());
    return fresh;
  })());
});
