/**
 * Petit client Redis par API REST (Upstash, tel que câblé par Vercel KV).
 *
 * Pourquoi pas de SDK : les quatre commandes utilisées ici — `sadd`, `srem`,
 * `smembers`, `set` avec TTL — tiennent en une requête HTTP chacune. Ajouter
 * une dépendance au shell de build pour ça coûterait plus que ça ne rapporte.
 *
 * Les noms de variables viennent de l'intégration : `KV_REST_API_URL` et
 * `KV_REST_API_TOKEN` côté Vercel KV, `UPSTASH_REDIS_REST_URL` et
 * `UPSTASH_REDIS_REST_TOKEN` côté Upstash direct. On accepte les deux plutôt
 * que d'imposer un câblage.
 */
import { envAny } from './env';

function credentials(): { url: string; token: string } | null {
  const url = envAny('KV_REST_API_URL', 'UPSTASH_REDIS_REST_URL');
  const token = envAny('KV_REST_API_TOKEN', 'UPSTASH_REDIS_REST_TOKEN');
  return url && token ? { url: url.replace(/\/+$/, ''), token } : null;
}

export const kvConfigured = (): boolean => credentials() !== null;

/**
 * Exécute une commande Redis.
 *
 * Le corps est la commande sous forme de tableau — c'est la forme qui échappe
 * correctement les valeurs, contrairement à l'URL où une clé contenant `/`
 * casserait la route.
 */
async function command<T>(args: (string | number)[]): Promise<T> {
  const creds = credentials();
  if (!creds) throw new Error('Store non configuré (KV_REST_API_URL / _TOKEN).');

  const res = await fetch(creds.url, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${creds.token}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify(args),
  });

  if (!res.ok) {
    throw new Error(`Store HTTP ${res.status} sur ${String(args[0])}`);
  }
  const payload = (await res.json()) as { result?: T; error?: string };
  if (payload.error) throw new Error(`Store: ${payload.error}`);
  return payload.result as T;
}

export const sadd = (key: string, member: string) =>
  command<number>(['SADD', key, member]);

export const srem = (key: string, member: string) =>
  command<number>(['SREM', key, member]);

export const smembers = (key: string) => command<string[]>(['SMEMBERS', key]);

/** `SET key value NX EX ttl` — renvoie `true` si la clé n'existait pas. */
export async function setIfAbsent(key: string, ttlSeconds: number): Promise<boolean> {
  const res = await command<string | null>(['SET', key, '1', 'NX', 'EX', ttlSeconds]);
  return res === 'OK';
}
