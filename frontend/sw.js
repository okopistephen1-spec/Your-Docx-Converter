const CACHE_NAME = 'your-docx-converter-v2';
const APP_SHELL = [
  './',
  './index.html',
  './converter.html',
  './editor.html',
  './manifest.json',
  './config.js',
  './css/style.css',
  './css/editor.css',
  './js/converter.js',
  './js/editor.js',
  './images/app-icon-192.png',
  './images/app-icon-512.png'
];

const PAGE_ROUTE_MAP = {
  '/': '/index.html',
  '/converter': '/converter.html',
  '/editor': '/editor.html'
};

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

function cacheResponse(request, response) {
  if (!response || !response.ok) {
    return response;
  }

  const responseClone = response.clone();
  return caches.open(CACHE_NAME)
    .then((cache) => cache.put(request, responseClone))
    .then(() => response)
    .catch(() => response);
}

function getCachedPageForNavigation(request) {
  const url = new URL(request.url);
  const mappedPath = PAGE_ROUTE_MAP[url.pathname] || url.pathname;

  if (mappedPath) {
    return caches.match(mappedPath).then((cached) => cached || caches.match('./index.html'));
  }

  return caches.match(request).then((cached) => cached || caches.match('./index.html'));
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') {
    return;
  }

  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || url.pathname.includes('/api/')) {
    return;
  }

  const isPageNavigation = event.request.mode === 'navigate' || url.pathname.endsWith('.html') || url.pathname === '/';

  if (isPageNavigation) {
    event.respondWith(
      fetch(event.request)
        .then((response) => cacheResponse(event.request, response))
        .catch(() => getCachedPageForNavigation(event.request))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        return cached;
      }

      return fetch(event.request)
        .then((response) => cacheResponse(event.request, response))
        .catch(() => caches.match('./index.html'));
    })
  );
});
