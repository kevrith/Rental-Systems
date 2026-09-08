/// <reference lib="webworker" />
/**
 * RentFlow service worker.
 *
 * Two jobs:
 *
 *   1. Keep the app shell available offline so a caretaker with no signal can
 *      still open it and record work (US-024, US-025). API responses are
 *      deliberately *not* cached — stale rent balances are worse than no data,
 *      and the offline queue is what makes writes safe.
 *   2. Receive Web Push messages and route clicks to the right screen (US-030).
 */
import { cleanupOutdatedCaches, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { CacheFirst, NetworkOnly, StaleWhileRevalidate } from 'workbox-strategies'
import { ExpirationPlugin } from 'workbox-expiration'
import { createHandlerBoundToURL } from 'workbox-precaching'

declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<{ url: string; revision: string | null }>
}

precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

// Every in-app navigation is served from the cached shell; React Router takes
// over from there, so the app opens instantly and works offline.
registerRoute(
  new NavigationRoute(createHandlerBoundToURL('index.html'), {
    denylist: [/^\/api\//],
  }),
)

// Fonts and images change rarely and are expensive on 3G.
registerRoute(
  ({ request }) => request.destination === 'font' || request.destination === 'image',
  new CacheFirst({
    cacheName: 'rentflow-assets',
    plugins: [new ExpirationPlugin({ maxEntries: 80, maxAgeSeconds: 60 * 60 * 24 * 30 })],
  }),
)

registerRoute(
  ({ request }) => request.destination === 'style' || request.destination === 'script',
  new StaleWhileRevalidate({ cacheName: 'rentflow-static' }),
)

// API calls always go to the network. A cached balance or arrears figure that
// looks current but isn't would be worse than an honest offline state.
registerRoute(({ url }) => url.pathname.startsWith('/api/'), new NetworkOnly())

self.addEventListener('install', () => {
  void self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

self.addEventListener('message', (event) => {
  // A service worker only ever hears from clients it controls, which the
  // browser restricts to this same origin — but the listener otherwise has
  // no origin check of its own, so add one explicitly rather than relying on
  // that platform guarantee.
  if (event.origin !== self.location.origin) return
  if (event.data?.type === 'SKIP_WAITING') void self.skipWaiting()
})

// ------------------------------------------------------------------- web push

interface PushPayload {
  title?: string
  body?: string
  url?: string
  type?: string
}

self.addEventListener('push', (event) => {
  let payload: PushPayload = {}
  try {
    payload = (event.data?.json() as PushPayload) ?? {}
  } catch {
    payload = { title: 'RentFlow', body: event.data?.text() ?? '' }
  }

  event.waitUntil(
    self.registration.showNotification(payload.title ?? 'RentFlow', {
      body: payload.body ?? '',
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      tag: payload.type,
      data: { url: payload.url ?? '/' },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = (event.notification.data as { url?: string })?.url ?? '/'

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      // Reuse an already-open tab rather than piling up new ones.
      for (const client of clients) {
        if ('focus' in client) {
          void client.focus()
          if ('navigate' in client) void client.navigate(target)
          return
        }
      }
      return self.clients.openWindow(target)
    }),
  )
})
