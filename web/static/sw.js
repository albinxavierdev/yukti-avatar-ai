/* Yukti service worker — app shell + preloaded 3D/vendor assets */
const CACHE_VERSION = "yukti-v2";
const SHELL_CACHE = `yukti-shell-${CACHE_VERSION}`;

const SHELL_ASSETS = [
  "/offline.html",
  "/static/css/styles.css",
  "/static/css/pwa.css",
  "/static/css/login.css",
  "/static/js/app.js",
  "/static/js/login.js",
  "/static/js/pwa.js",
  "/static/js/talking-head.js",
  "/static/js/load-talkinghead.js",
  "/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/vendor/three@0.170.0/build/three.module.js",
  "/static/vendor/talkinghead/modules/talkinghead.mjs",
  "/static/vendor/talkinghead/modules/lipsync-en.mjs",
  "/static/avatars/avaturn.glb",
  "/static/avatars/brunette.glb",
  "/static/avatars/vroid.glb",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k.startsWith("yukti-shell-") && k !== SHELL_CACHE).map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

function isApiRequest(url) {
  return url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/");
}

function isNavigation(request) {
  return request.mode === "navigate";
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  if (isApiRequest(url)) {
    return;
  }

  if (isNavigation(event.request)) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match("/offline.html"))
    );
    return;
  }

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        const network = fetch(event.request).then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(SHELL_CACHE).then((c) => c.put(event.request, clone));
          }
          return res;
        });
        return cached || network;
      })
    );
  }
});
