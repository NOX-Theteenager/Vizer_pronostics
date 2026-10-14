/**
 * Marchés que l'on accepte de parier, pilotés depuis l'écran Admin.
 *
 * Pourquoi ici et pas dans `config.yaml`
 * --------------------------------------
 * Couper un marché dans la config du sport arrête son **entraînement et sa
 * prédiction**. Deux conséquences qui en font un mauvais bouton de téléphone :
 * un geste malheureux prive l'app d'un marché jusqu'à ce que quelqu'un s'en
 * aperçoive, et le changement demande un commit puis un run de pipeline.
 *
 * Surtout : couper la prédiction, c'est **arrêter de mesurer**. On deviendrait
 * aveugle sur le marché qu'on surveille précisément pour savoir quand le
 * rouvrir. Ce réglage-ci ne touche donc qu'à une chose — ce que l'app propose
 * de parier. Le modèle continue de prédire, le job continue de publier, la
 * mesure continue de tourner.
 *
 * Lecture publique : l'app en a besoin à chaque chargement, et savoir quels
 * marchés sont pariables n'est pas un secret. Écriture derrière la clé
 * d'administration, comme le déclenchement de workflows.
 */
import { env } from './_lib/env.js';
import { get, kvConfigured, set } from './_lib/kv.js';

const KEY = 'vizer:markets:policy';

/** `sport:marché` → pariable. Une entrée absente garde la valeur par défaut. */
type Policy = Record<string, boolean>;

interface Stored {
  updated_at: string;
  markets: Policy;
}

function json(body: unknown, status = 200, cache = 'no-store'): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': cache },
  });
}

/** Comparaison à durée constante : une égalité naïve fuit le secret. */
function sameSecret(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

const EMPTY: Stored = { updated_at: '', markets: {} };

export async function GET(): Promise<Response> {
  if (!kvConfigured()) return json(EMPTY, 200, 'public, max-age=30');
  try {
    const raw = await get(KEY);
    const body = raw ? (JSON.parse(raw) as Stored) : EMPTY;
    // Trente secondes : un marché rebasculé doit se voir vite, mais la
    // lecture a lieu à chaque chargement de l'app.
    return json(body, 200, 'public, max-age=30');
  } catch {
    // Store injoignable : on renvoie la politique vide, donc les valeurs par
    // défaut. L'app reste utilisable.
    return json(EMPTY, 200, 'no-store');
  }
}

export async function PUT(request: Request): Promise<Response> {
  const expected = env('VIZER_ADMIN_SECRET');
  if (!expected) return json({ error: 'VIZER_ADMIN_SECRET non configuré.' }, 503);
  if (!sameSecret(request.headers.get('x-vizer-admin') ?? '', expected)) {
    return json({ error: 'Clé d’administration invalide.' }, 401);
  }
  if (!kvConfigured()) return json({ error: 'Store non configuré.' }, 503);

  let body: { markets?: unknown };
  try {
    body = (await request.json()) as { markets?: unknown };
  } catch {
    return json({ error: 'Corps JSON invalide.' }, 400);
  }
  if (!body.markets || typeof body.markets !== 'object') {
    return json({ error: 'Champ `markets` attendu.' }, 400);
  }

  // On ne stocke que des booléens sous des clés `sport:marché` plausibles :
  // ce document est relu et appliqué à chaque chargement de l'app.
  const clean: Policy = {};
  for (const [key, value] of Object.entries(body.markets as Record<string, unknown>)) {
    if (!/^[a-z]{2,4}:[a-z0-9_]{1,40}$/.test(key)) continue;
    if (typeof value !== 'boolean') continue;
    clean[key] = value;
  }

  const stored: Stored = { updated_at: new Date().toISOString(), markets: clean };
  try {
    await set(KEY, JSON.stringify(stored));
    return json({ ok: true, ...stored });
  } catch (e) {
    return json({ error: e instanceof Error ? e.message : 'Écriture impossible.' }, 502);
  }
}
