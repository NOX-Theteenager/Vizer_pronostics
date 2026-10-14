/**
 * Sauvegarde de l'état utilisateur, indexée par une clé secrète.
 *
 * Pourquoi pas un compte
 * ----------------------
 * Pour un utilisateur unique, un écran de connexion protège surtout de
 * soi-même. Ce qu'il faut vraiment, c'est un endroit où poser les données et
 * un moyen de les reprendre sur un autre appareil. C'est exactement ce que
 * fait une clé : l'authentification réduite à son noyau utile, la possession
 * d'un secret — sans mot de passe, sans e-mail, sans parcours de récupération
 * à construire et à sécuriser.
 *
 * Ce que ça implique, et qu'il faut assumer
 * ------------------------------------------
 * **Qui a la clé a les données.** Elle est générée par le navigateur avec
 * `crypto.getRandomValues` sur 32 octets, donc impossible à deviner, mais elle
 * n'est pas récupérable : la perdre, c'est perdre la sauvegarde distante. D'où
 * l'export de fichier, qui reste le filet principal.
 *
 * La clé n'est jamais stockée telle quelle. Redis garde son empreinte SHA-256 :
 * une fuite du contenu du store ne donne pas de quoi lire les états.
 */
import { get, kvConfigured, set } from './_lib/kv.js';

/** Taille d'un état sérialisé au-delà de laquelle on refuse d'écrire. */
const MAX_BYTES = 512 * 1024;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
  });
}

/**
 * La clé arrive en en-tête, jamais en paramètre d'URL : une URL se retrouve
 * dans les journaux d'accès, l'historique du navigateur et le `Referer`.
 */
function presentedKey(request: Request): string | null {
  const header = request.headers.get('x-vizer-key');
  if (!header) return null;
  const key = header.trim();
  // 32 octets en base64url font 43 caractères. On accepte un peu de marge,
  // mais pas une clé courte : ce serait une clé devinable.
  return /^[A-Za-z0-9_-]{32,128}$/.test(key) ? key : null;
}

async function storeKey(key: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(key));
  const hex = [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return `vizer:state:${hex}`;
}

export async function GET(request: Request): Promise<Response> {
  if (!kvConfigured()) return json({ error: 'Store non configuré.' }, 503);
  const key = presentedKey(request);
  if (!key) return json({ error: 'Clé absente ou mal formée.' }, 401);

  try {
    const raw = await get(await storeKey(key));
    // Pas de sauvegarde pour cette clé : ce n'est pas une erreur, c'est le
    // cas d'un premier appareil.
    if (raw === null) return json({ found: false });
    return json({ found: true, state: JSON.parse(raw) });
  } catch (e) {
    return json({ error: e instanceof Error ? e.message : 'Lecture impossible.' }, 502);
  }
}

export async function PUT(request: Request): Promise<Response> {
  if (!kvConfigured()) return json({ error: 'Store non configuré.' }, 503);
  const key = presentedKey(request);
  if (!key) return json({ error: 'Clé absente ou mal formée.' }, 401);

  let body: string;
  try {
    body = await request.text();
  } catch {
    return json({ error: 'Corps illisible.' }, 400);
  }

  if (body.length > MAX_BYTES) {
    return json({ error: 'Sauvegarde trop volumineuse.' }, 413);
  }
  try {
    JSON.parse(body);
  } catch {
    return json({ error: 'Corps JSON invalide.' }, 400);
  }

  try {
    await set(await storeKey(key), body);
    return json({ ok: true, bytes: body.length });
  } catch (e) {
    return json({ error: e instanceof Error ? e.message : 'Écriture impossible.' }, 502);
  }
}
