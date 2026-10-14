/**
 * Envoie une notification pour les value bets du jour.
 *
 * Appelé par le cron Vercel déclaré dans `vercel.json`, calé après la
 * publication des prédictions (7h UTC). C'est ce qui manquait pour que les
 * alertes arrivent téléphone verrouillé : jusqu'ici elles ne partaient que si
 * l'application était ouverte.
 *
 * Deux protections contre l'envoi répété, parce que l'URL est publiquement
 * joignable :
 *
 *   - `CRON_SECRET`, si la variable existe, doit être présentée en
 *     `Authorization: Bearer` — c'est ce que Vercel Cron envoie tout seul ;
 *   - chaque couple (abonné, pari) est marqué dans le store pour 20 heures,
 *     donc un second appel le même jour ne renotifie personne. Cette
 *     déduplication est nécessaire de toute façon : sans elle, deux exécutions
 *     du cron enverraient deux fois la même alerte.
 */
import webpush from 'web-push';

import { env } from '../_lib/env.js';
import { kvConfigured, setIfAbsent, smembers, srem } from '../_lib/kv.js';
import { SUBS_KEY } from './subscribe.js';

/** Un abonnement tel que stocké par `subscribe`. */
interface StoredSub {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  threshold: number;
}

/** Forme minimale d'un value bet publié, commune aux deux sports. */
interface RawBet {
  market?: string;
  selection?: string;
  edge?: number;
  bookmaker_odds?: number;
}

interface RawGame {
  home?: string;
  away?: string;
  commence_time?: string;
  value_bets?: RawBet[];
}

const SPORTS = ['nhl', 'nba'] as const;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
}

/**
 * Prédictions du jour, lues à la source.
 *
 * On passe par `raw.githubusercontent.com` et non par notre propre proxy :
 * une fonction qui s'appelle elle-même à travers le CDN ajoute un point de
 * panne et un cache là où on veut la donnée fraîche.
 */
async function fetchBets(): Promise<{ sport: string; game: RawGame; bet: RawBet }[]> {
  const repo = env('VIZER_REPO') ?? 'NOX-Theteenager/Vizer_pronostics';
  const branch = env('VIZER_BRANCH') ?? 'models-artifacts';
  const out: { sport: string; game: RawGame; bet: RawBet }[] = [];

  for (const sport of SPORTS) {
    const url = `https://raw.githubusercontent.com/${repo}/${branch}/predictions/latest/${sport}.json`;
    try {
      const res = await fetch(url, { headers: { 'user-agent': 'vizer-push' } });
      if (!res.ok) continue;
      const feed = (await res.json()) as { games?: RawGame[] };
      for (const game of feed.games ?? []) {
        // Un match déjà commencé n'intéresse plus personne.
        const start = Date.parse(game.commence_time ?? '');
        if (Number.isFinite(start) && start < Date.now()) continue;
        for (const bet of game.value_bets ?? []) out.push({ sport, game, bet });
      }
    } catch {
      // Un sport indisponible ne doit pas empêcher de notifier l'autre.
    }
  }
  return out;
}

/** Identifiant stable d'un pari, pour la déduplication. */
function betId(sport: string, game: RawGame, bet: RawBet): string {
  const day = (game.commence_time ?? '').slice(0, 10);
  return `${sport}:${game.away}@${game.home}:${day}:${bet.market}:${bet.selection}`;
}

export async function GET(request: Request): Promise<Response> {
  const secret = env('CRON_SECRET');
  if (secret && request.headers.get('authorization') !== `Bearer ${secret}`) {
    return json({ error: 'Non autorisé.' }, 401);
  }

  const publicKey = env('VAPID_PUBLIC_KEY');
  const privateKey = env('VAPID_PRIVATE_KEY');
  if (!publicKey || !privateKey) return json({ error: 'Clés VAPID absentes.' }, 503);
  if (!kvConfigured()) return json({ error: 'Store non configuré.' }, 503);

  // `mailto:` est ce que la spécification attend ; un `https:` est accepté
  // aussi. Sans sujet, certains services de push refusent la requête.
  webpush.setVapidDetails(env('VAPID_SUBJECT') ?? 'mailto:contact@vizer.app', publicKey, privateKey);

  const candidates = await fetchBets();
  if (candidates.length === 0) return json({ ok: true, sent: 0, reason: 'aucun value bet' });

  const subs: StoredSub[] = [];
  for (const entry of await smembers(SUBS_KEY)) {
    try {
      subs.push(JSON.parse(entry) as StoredSub);
    } catch {
      await srem(SUBS_KEY, entry);
    }
  }
  if (subs.length === 0) return json({ ok: true, sent: 0, reason: 'aucun abonné' });

  let sent = 0;
  let skipped = 0;
  let dropped = 0;

  for (const sub of subs) {
    // Le meilleur pari au-dessus du seuil de cet abonné, et lui seul : une
    // notification par jour vaut mieux que dix, qu'on désactive après deux.
    const eligible = candidates
      .filter((c) => (c.bet.edge ?? 0) * 100 >= sub.threshold)
      .sort((a, b) => (b.bet.edge ?? 0) - (a.bet.edge ?? 0));
    const best = eligible[0];
    if (!best) continue;

    const key = `vizer:push:done:${sub.endpoint.slice(-24)}:${betId(best.sport, best.game, best.bet)}`;
    if (!(await setIfAbsent(key, 20 * 3600))) {
      skipped += 1;
      continue;
    }

    const edgePct = Math.round((best.bet.edge ?? 0) * 1000) / 10;
    const payload = JSON.stringify({
      title: `Value bet · ${best.sport.toUpperCase()}`,
      body: `${best.game.away} @ ${best.game.home} — ${best.bet.selection} @ ${best.bet.bookmaker_odds} (edge ${edgePct} %)`,
      // Le service worker ouvre le match concerné au clic.
      gameId: `${best.sport}-${best.game.away}@${best.game.home}-${(best.game.commence_time ?? '').slice(0, 10)}`,
      count: eligible.length,
    });

    try {
      await webpush.sendNotification(
        { endpoint: sub.endpoint, keys: sub.keys },
        payload,
      );
      sent += 1;
    } catch (e) {
      // 404 / 410 : l'abonnement a expiré côté navigateur, il ne reviendra
      // pas. On le retire plutôt que de le réessayer tous les jours.
      const status = (e as { statusCode?: number }).statusCode;
      if (status === 404 || status === 410) {
        await srem(SUBS_KEY, JSON.stringify(sub));
        dropped += 1;
      }
    }
  }

  return json({ ok: true, subscribers: subs.length, sent, skipped, dropped });
}
