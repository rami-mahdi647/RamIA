const CACHE_VERSION = "ramia-v1.1.0";
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/rent.html",
  "/success.html",
  "/cancel.html",
  "/app.js",
  "/manifest.webmanifest"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== STATIC_CACHE).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  if (req.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        const cache = await caches.open(STATIC_CACHE);
        cache.put(req, fresh.clone());
        return fresh;
      } catch {
        const cache = await caches.open(STATIC_CACHE);
        return (await cache.match(req)) || (await cache.match("/index.html"));
      }
    })());
    return;
  }

  event.respondWith((async () => {
    const cache = await caches.open(STATIC_CACHE);
    const hit = await cache.match(req);
    if (hit) return hit;
    const fresh = await fetch(req);
    cache.put(req, fresh.clone());
    return fresh;
  })());
});
