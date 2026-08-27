/* Service worker for directory.kiarashs.ir.

   The previous version of this file declared a URL list and nothing else — no
   install, activate or fetch handler — so it never cached anything and one of
   the paths it listed (/css/styles.css) did not exist. This one is small and
   does what it says:

     - the shell (page, stylesheet, script, icons) is precached on install;
     - navigations go to the network first, falling back to the cached page
       when offline, so a new deploy is never masked by a stale copy;
     - other same-origin GETs are served from the cache when present, and
       cached as they are fetched.

   Bump CACHE when the shell changes; older caches are deleted on activate. */

var CACHE = 'directory-v1';

var SHELL = [
  './',
  './index.html',
  './static/css/directory.css',
  './static/js/directory.js',
  './manifest.webmanifest',
  './favicon-32x32.png',
  './apple-touch-icon.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      // addAll rejects the whole install if any single request fails, which
      // is how the old list silently broke. Add them one at a time instead.
      return Promise.all(SHELL.map(function (url) {
        return cache.add(new Request(url, { cache: 'reload' })).catch(function () {});
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        return key === CACHE ? null : caches.delete(key);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') return;

  var url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(function (response) {
          var copy = response.clone();
          caches.open(CACHE).then(function (c) { c.put('./index.html', copy); });
          return response;
        })
        .catch(function () {
          return caches.match('./index.html').then(function (hit) {
            return hit || caches.match('./');
          });
        })
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(function (hit) {
      return hit || fetch(request).then(function (response) {
        if (response && response.ok && response.type === 'basic') {
          var copy = response.clone();
          caches.open(CACHE).then(function (c) { c.put(request, copy); });
        }
        return response;
      });
    })
  );
});
