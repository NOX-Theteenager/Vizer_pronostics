/**
 * Scores en direct, relayés par `/api/live` depuis le scoreboard d'ESPN.
 *
 * C'est la seule donnée de l'app qui ne vienne pas d'un fichier publié : elle
 * change trop vite pour transiter par un commit. Elle est donc **purement
 * d'affichage** — aucun pari n'est clôturé sur un score lu en vol, la clôture
 * reste adossée à `results/latest.json`, daté et rejouable.
 */
import type { Sport } from './model';

export interface LiveGame {
  /** Identique à `Game.id` : l'appariement se fait sans transformation. */
  id: string;
  sport: Sport;
  home: string;
  away: string;
  commenceTime: string;
  state: 'in' | 'post';
  /** Texte prêt à afficher : « 7:32 - 2nd », « Final/OT »… */
  detail: string;
  period: number | null;
  clock: string | null;
  homeScore: number;
  awayScore: number;
}

interface RawLiveGame {
  id?: string;
  sport?: string;
  home?: string;
  away?: string;
  commenceTime?: string;
  state?: string;
  detail?: string;
  period?: number | null;
  clock?: string | null;
  homeScore?: number;
  awayScore?: number;
}

const SPORTS: Sport[] = ['nhl', 'nba'];

export function normalizeLive(raw: unknown): LiveGame[] {
  const feed = raw as { games?: RawLiveGame[] } | null;
  if (!feed || !Array.isArray(feed.games)) return [];

  const out: LiveGame[] = [];
  for (const g of feed.games) {
    if (!g.id || !g.home || !g.away) continue;
    if (!(SPORTS as string[]).includes(g.sport ?? '')) continue;
    if (g.state !== 'in' && g.state !== 'post') continue;
    if (typeof g.homeScore !== 'number' || typeof g.awayScore !== 'number') continue;

    out.push({
      id: g.id,
      sport: g.sport as Sport,
      home: g.home,
      away: g.away,
      commenceTime: g.commenceTime ?? '',
      state: g.state,
      detail: g.detail ?? '',
      period: typeof g.period === 'number' ? g.period : null,
      clock: g.clock ?? null,
      homeScore: g.homeScore,
      awayScore: g.awayScore,
    });
  }
  return out;
}
