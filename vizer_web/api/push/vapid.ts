/**
 * Clé publique VAPID, nécessaire au navigateur pour s'abonner.
 *
 * Publique par construction : c'est elle que le client passe à
 * `pushManager.subscribe()`. La clé privée, elle, ne quitte jamais le serveur.
 */
import { env, isSet } from '../_lib/env';
import { kvConfigured } from '../_lib/kv';

export function GET(): Response {
  const key = env('VAPID_PUBLIC_KEY');
  const ready = !!key && isSet('VAPID_PRIVATE_KEY') && kvConfigured();

  return new Response(
    JSON.stringify({
      // `ready` dit au client s'il doit proposer les notifications : sans
      // store ni clé privée, un abonnement réussirait côté navigateur et ne
      // recevrait jamais rien — pire qu'une option absente.
      ready,
      publicKey: ready ? key : null,
    }),
    {
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'public, max-age=300',
      },
    },
  );
}
