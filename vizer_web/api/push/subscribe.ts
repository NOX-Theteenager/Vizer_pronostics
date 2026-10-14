/**
 * Enregistre ou retire un abonnement aux notifications.
 *
 * Le navigateur produit un objet `PushSubscription` dont l'`endpoint` est
 * l'identifiant : on stocke l'abonnement sérialisé dans un ensemble Redis, et
 * on s'en sert tel quel au moment d'envoyer.
 *
 * Aucune donnée personnelle n'est demandée — pas de compte, pas d'e-mail.
 * L'endpoint est fourni par le service de push du navigateur et ne désigne
 * que ce navigateur-là.
 */
import { kvConfigured, sadd, smembers, srem } from '../_lib/kv.js';

export const SUBS_KEY = 'vizer:push:subs';

interface Body {
  subscription?: { endpoint?: string; keys?: { p256dh?: string; auth?: string } };
  /** Seuil d'edge en points de % (4 à 15), aligné sur le réglage de l'app. */
  threshold?: number;
  action?: 'subscribe' | 'unsubscribe';
}

function bad(message: string, status = 400): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
}

export async function POST(request: Request): Promise<Response> {
  if (!kvConfigured()) return bad('Store non configuré.', 503);

  let body: Body;
  try {
    body = (await request.json()) as Body;
  } catch {
    return bad('Corps JSON invalide.');
  }

  const sub = body.subscription;
  if (!sub?.endpoint || !sub.keys?.p256dh || !sub.keys.auth) {
    return bad('Abonnement incomplet.');
  }

  // L'ensemble est dédoublonné par Redis sur la valeur exacte : on normalise
  // donc ce qu'on y met, sinon un même navigateur s'y retrouverait deux fois
  // avec deux seuils différents.
  const threshold = Math.min(15, Math.max(4, Number(body.threshold) || 8));
  const record = JSON.stringify({
    endpoint: sub.endpoint,
    keys: { p256dh: sub.keys.p256dh, auth: sub.keys.auth },
    threshold,
  });

  try {
    if (body.action === 'unsubscribe') {
      // Le seuil a pu changer depuis l'abonnement : on retire par endpoint,
      // pas par valeur exacte, sinon le retrait échouerait en silence.
      for (const entry of await smembers(SUBS_KEY)) {
        try {
          if ((JSON.parse(entry) as { endpoint?: string }).endpoint === sub.endpoint) {
            await srem(SUBS_KEY, entry);
          }
        } catch {
          // Entrée illisible : on la retire aussi, elle ne servira jamais.
          await srem(SUBS_KEY, entry);
        }
      }
      return new Response(JSON.stringify({ ok: true, subscribed: false }), {
        headers: { 'content-type': 'application/json; charset=utf-8' },
      });
    }

    // Réabonnement avec un seuil différent : on nettoie l'ancien enregistrement
    // du même endpoint avant d'ajouter le nouveau.
    for (const entry of await smembers(SUBS_KEY)) {
      try {
        if (
          (JSON.parse(entry) as { endpoint?: string }).endpoint === sub.endpoint &&
          entry !== record
        ) {
          await srem(SUBS_KEY, entry);
        }
      } catch {
        await srem(SUBS_KEY, entry);
      }
    }
    await sadd(SUBS_KEY, record);
    return new Response(JSON.stringify({ ok: true, subscribed: true, threshold }), {
      headers: { 'content-type': 'application/json; charset=utf-8' },
    });
  } catch (e) {
    return bad(e instanceof Error ? e.message : 'Store injoignable.', 502);
  }
}
