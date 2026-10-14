/**
 * Proxy des données publiées.
 *
 * Sans lui, la PWA tape directement `raw.githubusercontent.com`, avec trois
 * conséquences : un cache CDN de 5 minutes qu'on ne contrôle pas, un quota
 * par IP (partagé par tous les utilisateurs derrière un même opérateur
 * mobile), et une origine tierce dans chaque requête.
 *
 * Ici, les JSON sont servis depuis la même origine que l'app, avec nos propres
 * en-têtes de cache : le POP Vercel le plus proche de l'utilisateur répond, et
 * ne redemande à GitHub qu'à l'expiration.
 *
 *   /api/data/predictions/latest/nhl.json
 *   /api/data/models/registry.json
 *   /api/data/results/latest.json
 *   /api/data/performance/summary.json
 *
 * Variables d'environnement (facultatives) :
 *   VIZER_REPO    — dépôt source, défaut NOX-Theteenager/Vizer_pronostics
 *   VIZER_BRANCH  — branche de données, défaut models-artifacts
 *   VIZER_GITHUB_TOKEN — nécessaire seulement si le dépôt devient privé
 */
/**
 * Pourquoi une fonction unique plutôt qu'une route attrape-tout
 * -------------------------------------------------------------
 * `api/data/[...path].ts` ne s'enregistrait pas sur ce projet : 404 sur tout
 * `/api/data`, pendant qu'une fonction voisine sans segment dynamique
 * répondait 200. Plutôt que de dépendre d'une convention de nommage qui se
 * comporte mal ici, le chemin arrive en paramètre de requête, posé par une
 * réécriture déclarée dans `vercel.json` :
 *
 *     /api/data/:path*  →  /api/data?path=:path*
 *
 * Les URL vues par l'application sont identiques, et la réécriture est du
 * fichier de configuration, pas de la détection implicite.
 *
 * Signature : `export function GET(request)`, la forme web documentée. Un
 * export par défaut est traité comme `(req, res) => void`, le `Response`
 * retourné est ignoré et la requête part en timeout — le runtime le dit
 * explicitement dans ses logs.
 *
 * Pas de `config = { runtime: 'edge' }` : le runtime Node par défaut répond
 * déjà depuis le POP le plus proche (les logs montrent `cpt1`, Le Cap).
 */

/**
 * `process.env` n'est pas dans les types DOM de ce projet, et le build Vercel
 * type-vérifie cette fonction avant de l'émettre : sans déclaration, la
 * compilation échoue, la fonction est écartée et le build reste vert.
 */
declare const process: { env: Record<string, string | undefined> };

const REPO = process.env.VIZER_REPO || 'NOX-Theteenager/Vizer_pronostics';
const BRANCH = process.env.VIZER_BRANCH || 'models-artifacts';
const TOKEN = process.env.VIZER_GITHUB_TOKEN || '';

/**
 * Durées de fraîcheur côté CDN. Les prédictions sont régénérées une fois par
 * jour à 7h UTC : une minute de cache suffit à absorber une rafale sans jamais
 * faire attendre une donnée fraîche, et `stale-while-revalidate` sert l'ancienne
 * version pendant qu'on va chercher la nouvelle plutôt que de bloquer.
 */
const CACHE: Record<string, { cdn: string; browser: string }> = {
  predictions: {
    cdn: 'max-age=60, stale-while-revalidate=600',
    browser: 'public, max-age=0, must-revalidate',
  },
  results: {
    cdn: 'max-age=300, stale-while-revalidate=3600',
    browser: 'public, max-age=60',
  },
  models: {
    cdn: 'max-age=300, stale-while-revalidate=3600',
    browser: 'public, max-age=60',
  },
  // Recalculée une fois par jour avec les résultats : elle ne bouge pas plus
  // vite que ça.
  performance: {
    cdn: 'max-age=300, stale-while-revalidate=3600',
    browser: 'public, max-age=60',
  },
};

/**
 * Le chemin vient de l'URL : il ne doit pas pouvoir sortir de la branche de
 * données. On n'autorise que les trois racines publiées, et aucun segment
 * `..` — un proxy qui relaie n'importe quel chemin relaie aussi `.git/`.
 */
function safePath(raw: string): string | null {
  const clean = raw.replace(/^\/+/, '');
  if (!clean || clean.includes('..') || clean.includes('//')) return null;
  const root = clean.split('/')[0];
  if (!(root in CACHE)) return null;
  if (!/^[\w./-]+$/.test(clean)) return null;
  return clean;
}

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const path = safePath(url.searchParams.get('path') ?? '');

  if (!path) {
    return new Response(
      JSON.stringify({ error: 'Chemin non autorisé.' }),
      { status: 400, headers: { 'content-type': 'application/json; charset=utf-8' } },
    );
  }

  const upstream = TOKEN
    ? `https://api.github.com/repos/${REPO}/contents/${path}?ref=${BRANCH}`
    : `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${path}`;

  const headers: Record<string, string> = { 'user-agent': 'vizer-edge-proxy' };
  if (TOKEN) {
    headers.authorization = `Bearer ${TOKEN}`;
    headers.accept = 'application/vnd.github.raw';
  }

  let res: Response;
  try {
    res = await fetch(upstream, { headers });
  } catch {
    // GitHub injoignable : la PWA a un cache local, on le lui dit clairement
    // plutôt que de laisser un timeout opaque.
    return new Response(
      JSON.stringify({ error: 'Source de données injoignable.' }),
      { status: 502, headers: { 'content-type': 'application/json; charset=utf-8' } },
    );
  }

  if (!res.ok) {
    return new Response(
      JSON.stringify({ error: `Fichier absent (${res.status}).`, path }),
      {
        status: res.status === 404 ? 404 : 502,
        headers: {
          'content-type': 'application/json; charset=utf-8',
          // Un 404 se met en cache brièvement : un sport sans match du jour
          // est une situation normale, pas la peine de la redemander sans arrêt.
          'cache-control': 'public, s-maxage=60',
        },
      },
    );
  }

  const cache = CACHE[path.split('/')[0]];
  return new Response(res.body, {
    status: 200,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      // Deux caches distincts, deux en-têtes. Un `s-maxage` posé sur
      // Cache-Control est consommé par le CDN puis retiré de la réponse : le
      // navigateur reçoit alors un simple `public` et remet en cache ce qu'on
      // voulait voir expirer. `Vercel-CDN-Cache-Control` pilote l'edge sans
      // toucher à ce que lit le navigateur.
      'vercel-cdn-cache-control': cache.cdn,
      'cache-control': cache.browser,
      // L'app et les données partagent l'origine ; on ouvre quand même en
      // lecture pour qu'un aperçu de déploiement puisse lire la production.
      'access-control-allow-origin': '*',
    },
  });
}
