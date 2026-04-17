// Minimal service worker — enables PWA installability.
// v1: online only; no offline caching strategy.
self.addEventListener('install', (event) => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

self.addEventListener('fetch', (event) => {
  // Pass through — no caching in v1.
})
