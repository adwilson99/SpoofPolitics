/* Loony to Westminster — service worker.
   Precaches the app shell so the game boots offline / on flaky pub wifi.
   Game state (/api/) is NEVER cached: the Returning Officer insists on live data. */
"use strict";

const CACHE = "ltw-v2";
const SHELL = [
  "/",
  "/static/css/main.css",
  "/static/js/api.js",
  "/static/js/map.js",
  "/static/js/app.js",
  "/static/map/united-kingdom.svg",
  "/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) {
    return; // game state stays live
  }
  if (event.request.mode === "navigate") {
    // network first so a running server always wins; offline falls back to the shell
    event.respondWith(fetch(event.request).catch(() => caches.match("/")));
    return;
  }
  // Same-origin assets: stale-while-revalidate — serve instantly from cache,
  // refresh the copy in the background so deploys reach players on next load.
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const hit = await cache.match(event.request);
      const network = fetch(event.request)
        .then((res) => {
          if (url.origin === location.origin && res.ok) {
            cache.put(event.request, res.clone());
          }
          return res;
        })
        .catch(() => hit);
      return hit || network;
    })
  );
});
