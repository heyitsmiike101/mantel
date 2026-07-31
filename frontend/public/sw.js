/* Family Calendar service worker.
 *
 * Purpose: a wall display that keeps showing the schedule when the network drops,
 * instead of going blank. Everything else is deliberately conservative.
 *
 * THE RULE THAT MATTERS: this app updates itself by polling /api/version and
 * hard-reloading when the version changes. A service worker that caches either
 * that endpoint or index.html would silently break the update mechanism and
 * strand every screen in the house on an old build. So:
 *
 *   - /api/version is never touched. It always goes to the network.
 *   - navigations are network-first, cache only as an offline fallback.
 *   - hashed assets are immutable and safe to cache forever.
 */

// Taken from the ?v= on the registration URL (see main.tsx). A fixed constant
// would mean the activate cleanup never fires, so every release's content-hashed
// assets would pile up in the cache forever until the browser evicted the whole
// origin -- taking the offline copy with it.
const VERSION = new URL(self.location.href).searchParams.get('v') || 'dev'
const SHELL_CACHE = `famcal-shell-${VERSION}`
const DATA_CACHE = `famcal-data-${VERSION}`

// Every GET a screen needs to render itself from cache; anything not listed
// falls through to the network untouched. The dashboard is the
// recommended kiosk route, so its widget layout belongs here just as much as the
// calendar's events -- without it a network drop leaves the wall showing the
// empty-dashboard placeholder.
const CACHEABLE_API = [
  '/api/events',
  '/api/users',
  '/api/calendars',
  '/api/settings',
  '/api/photos',
  '/api/dashboard/widgets',
  '/api/dashboard/widget-types',
  '/api/lists',
  '/api/weather',
]

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((c) => c.addAll(['/'])))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith('famcal-') && !k.endsWith(`-${VERSION}`))
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  // Never cache the version probe -- see the note at the top of this file.
  if (url.pathname === '/api/version') return

  // Hashed build assets and uploaded photos never change under a given URL.
  if (url.pathname.startsWith('/assets/') || /^\/api\/photos\/\d+\/file$/.test(url.pathname)) {
    event.respondWith(cacheFirst(request, SHELL_CACHE))
    return
  }

  if (CACHEABLE_API.some((p) => url.pathname === p || url.pathname.startsWith(`${p}?`))) {
    event.respondWith(networkFirst(request, DATA_CACHE))
    return
  }

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, SHELL_CACHE))
  }
})

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName)
  const hit = await cache.match(request)
  if (hit) return hit
  const response = await fetch(request)
  if (response.ok) cache.put(request, response.clone())
  return response
}

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName)
  try {
    const response = await fetch(request)
    if (response.ok) cache.put(request, response.clone())
    return response
  } catch (err) {
    const hit = await cache.match(request)
    if (hit) return hit
    // A navigation with nothing cached still needs *something* back.
    if (request.mode === 'navigate') {
      const shell = await cache.match('/')
      if (shell) return shell
    }
    throw err
  }
}
