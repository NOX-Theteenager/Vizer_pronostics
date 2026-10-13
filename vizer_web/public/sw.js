/* =========================================================================
   Vizer — service worker
   -------------------------------------------------------------------------
   Deux stratégies, parce que les deux ressources n'ont pas la même nature :

   - Le shell de l'app (HTML, JS, CSS, icônes) est versionné par Vite
     (hash dans le nom) → cache-first, mise à jour au changement de CACHE.
   - Les prédictions sont des JSON qui changent tous les jours → network-first
     avec repli sur le cache, pour que l'app reste consultable hors-ligne avec
     les dernières données connues (design.md §2 / §7.7).

   Aucune dépendance : pas de Workbox, pas de CDN (§8).
   ========================================================================= */
const VERSION = 'v3';
const SHELL_CACHE = `vizer-shell-${VERSION}`;
const DATA_CACHE = `vizer-data-${VERSION}`;

/** Ressources connues d'avance ; le reste est mis en cache à l'usage. */
const PRECACHE = ['./', './index.html', './manifest.webmanifest', './icons/icon-192.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      // `addAll` échoue en bloc si une seule URL manque : on tolère.
      .then((cache) => Promise.allSettled(PRECACHE.map((u) => cache.add(u))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith('vizer-') && !k.endsWith(VERSION))
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

/**
 * Une donnée publiée par le backend, par opposition au shell de l'app.
 *
 * Trois familles, qui changent toutes au moins une fois par jour :
 * `predictions/` (les matchs), `results/` (les scores finaux, d'où la clôture
 * automatique) et `models/` (le registre lu par l'écran Admin). Elles passent
 * toutes en network-first, y compris servies depuis notre propre origine via
 * /api/data — une donnée du jour mise en cache-first resterait figée.
 */
function isDataRequest(url) {
  return (
    /\/(predictions|results|models)\//.test(url.pathname) ||
    /\/mock\/\w+\.json$/.test(url.pathname)
  );
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Navigation : on sert le shell, le routing est côté client (hash).
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match('./index.html', { ignoreSearch: true }).then(
          (cached) =>
            cached ??
            new Response('<h1>Vizer est hors ligne</h1>', {
              headers: { 'Content-Type': 'text/html; charset=utf-8' },
              status: 503,
            }),
        ),
      ),
    );
    return;
  }

  if (isDataRequest(url)) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Même origine uniquement : on ne met pas en cache ce qu'on ne maîtrise pas.
  if (url.origin === self.location.origin) {
    event.respondWith(cacheFirst(request));
  }
});

async function networkFirst(request) {
  const cache = await caches.open(DATA_CACHE);
  try {
    const res = await fetch(request);
    if (res.ok) {
      // La requête porte un cache-buster (?cb=…) : on normalise la clé pour
      // que le repli hors-ligne retrouve bien la dernière réponse connue.
      const key = new Request(stripQuery(request.url), { headers: request.headers });
      cache.put(key, res.clone());
    }
    return res;
  } catch (err) {
    const cached = await cache.match(stripQuery(request.url));
    if (cached) return cached;
    throw err;
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request, { ignoreSearch: false });
  if (cached) return cached;
  const res = await fetch(request);
  if (res.ok && res.type === 'basic') {
    const cache = await caches.open(SHELL_CACHE);
    cache.put(request, res.clone());
  }
  return res;
}

function stripQuery(href) {
  const u = new URL(href);
  u.search = '';
  return u.toString();
}

/** Clic sur une notification système : ouvrir le match concerné. */
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const gameId = event.notification.data?.gameId;
  const target = gameId ? `./#/match/${gameId}` : './';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if ('focus' in client) {
          client.navigate?.(target);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
