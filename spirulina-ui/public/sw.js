const CACHE_NAME = "spirulina-v1";

// Static assets to pre-cache on install
const PRECACHE_URLS = [
  "/",
  "/favicon.ico",
  "/icon-192.svg",
  "/icon-512.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Never intercept the backend API — always go network-only. The backend
  // is a different origin than this app (NEXT_PUBLIC_API_URL), so this must
  // be origin-based, not just a same-origin path prefix: a path-only check
  // (e.g. "/sensors/") would never even match a cross-origin request here,
  // but would also silently miss same-origin API paths if the app is ever
  // reverse-proxied onto this origin. Checking both covers either setup.
  if (
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/chat") ||
    url.pathname.startsWith("/alerts") ||
    url.pathname.startsWith("/sensors") ||
    url.pathname.startsWith("/models") ||
    url.pathname.startsWith("/conversations") ||
    url.pathname.startsWith("/cpc") ||
    url.pathname.startsWith("/auth") ||
    url.pathname.startsWith("/admin")
  ) {
    return;
  }

  // Next.js _next/data and RSC payloads — network-first, fall back to cache
  if (url.pathname.startsWith("/_next/")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Static assets & pages — cache-first
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      });
    })
  );
});
