/**
 * État de configuration du déploiement.
 *
 * Répond à une question qu'on ne peut pas poser autrement : *quelles*
 * capacités sont configurées sur cet environnement. Les variables ne sont pas
 * lisibles depuis l'extérieur, et il serait absurde de les exposer pour le
 * savoir.
 *
 * Cette route ne renvoie donc **que des booléens** : la présence d'une clé,
 * jamais sa valeur, jamais un fragment de valeur. Elle est publique et doit le
 * rester sans risque — c'est la seule forme acceptable pour ce diagnostic.
 */

/** `process` existe dans le runtime Vercel, pas dans les types DOM du projet. */
declare const process: { env: Record<string, string | undefined> };

/** `true` si la variable est définie et non vide. */
const set = (name: string): boolean => !!process.env[name]?.trim();

/** Première variable définie parmi plusieurs noms possibles. */
const anySet = (...names: string[]): boolean => names.some(set);

export function GET(): Response {
  const body = {
    ok: true,
    checked_at: new Date().toISOString(),
    data: {
      // Source des JSON publiés. Les valeurs par défaut suffisent, ces clés
      // ne servent qu'à déplacer la source sans rebuild.
      repo_override: set('VIZER_REPO'),
      branch_override: set('VIZER_BRANCH'),
    },
    admin: {
      // Lecture des runs : le jeton lève seulement le quota, la route marche
      // sans lui. Écriture : les deux sont nécessaires.
      github_token: set('VIZER_GITHUB_TOKEN'),
      admin_secret: set('VIZER_ADMIN_SECRET'),
    },
    push: {
      // Notifications hors application : il faut les deux clés VAPID.
      vapid_public: set('VAPID_PUBLIC_KEY'),
      vapid_private: set('VAPID_PRIVATE_KEY'),
      vapid_subject: set('VAPID_SUBJECT'),
    },
    store: {
      // Un store d'abonnements, quel qu'il soit. On déclare ce qu'on sait
      // reconnaître plutôt que d'imposer un fournisseur.
      blob: anySet('BLOB_READ_WRITE_TOKEN'),
      kv: anySet('KV_REST_API_URL', 'KV_URL'),
      redis: anySet('REDIS_URL', 'UPSTASH_REDIS_REST_URL'),
      postgres: anySet('POSTGRES_URL', 'DATABASE_URL'),
      edge_config: anySet('EDGE_CONFIG'),
    },
  };

  return new Response(JSON.stringify(body, null, 2), {
    headers: {
      'content-type': 'application/json; charset=utf-8',
      // Jamais de cache : c'est un diagnostic, il doit refléter l'instant.
      'cache-control': 'no-store',
    },
  });
}
