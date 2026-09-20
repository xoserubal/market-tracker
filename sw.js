// Market Tracker — service worker minimo, solo para poder instalar el
// sitio como app (PWA) en el movil. Deliberadamente NO cachea HTML,
// /api/* ni /docs/data/* -- este sitio muestra datos de mercado en vivo,
// y servir una version cacheada sin ningun aviso de "obsoleto" iria en
// contra de la disciplina de staleness que ya sigue el resto del proyecto
// (ver duration.html -> staleInfo()). Solo acelera la carga de assets
// realmente estaticos (shared/*.js, iconos, el propio manifest) con un
// patron stale-while-revalidate; todo lo demas pasa directo a la red sin
// que este worker lo intercepte.
const CACHE_NAME = "market-tracker-shell-v1";
const PRECACHE_URLS = [
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isStaticAsset =
    url.pathname.startsWith("/shared/") ||
    url.pathname.startsWith("/icons/") ||
    url.pathname === "/manifest.json";
  if (!isStaticAsset) return; // deja pasar todo lo demas (HTML, /api/, /docs/data/) directo a la red

  event.respondWith(
    caches.match(event.request).then((cached) => {
      const networked = fetch(event.request)
        .then((resp) => {
          if (resp && resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return resp;
        })
        .catch(() => cached);
      return cached || networked;
    })
  );
});
