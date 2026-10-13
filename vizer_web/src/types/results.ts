/**
 * Scores finaux publiés par `scripts/publish_results.py`.
 *
 * Fichier lu : `<base>/../results/latest.json` — fenêtre glissante des sept
 * derniers jours, un seul fetch pour clôturer tout ce qui traîne.
 */
import type { Sport } from './model';

export interface PeriodScore {
  home: number;
  away: number;
}

export interface GameResult {
  sport: Sport;
  home: string;
  away: string;
  commenceTime: string;
  homeScore: number;
  awayScore: number;
  /** Prolongation ou tirs au but. */
  overtime: boolean;
  /** Scores par période (NHL) ou par quart-temps (NBA). */
  periods: PeriodScore[];
  winner: 'home' | 'away' | 'draw';
}

interface RawResult {
  sport?: string;
  home?: string;
  away?: string;
  commence_time?: string;
  home_score?: number;
  away_score?: number;
  overtime?: boolean;
  periods?: { home?: number; away?: number }[];
  winner?: string;
}

const SPORTS: Sport[] = ['nhl', 'nba'];

function isSport(v: unknown): v is Sport {
  return typeof v === 'string' && (SPORTS as string[]).includes(v);
}

/** Identifiant stable d'une rencontre, aligné sur celui des prédictions. */
export function resultKey(sport: string, home: string, away: string, commenceTime: string): string {
  return `${sport}:${home}:${away}:${commenceTime.slice(0, 10)}`;
}

export function normalizeResults(raw: unknown): GameResult[] {
  const feed = raw as { games?: RawResult[] } | null;
  if (!feed || !Array.isArray(feed.games)) return [];

  const out: GameResult[] = [];
  for (const g of feed.games) {
    if (!isSport(g.sport) || !g.home || !g.away) continue;
    if (typeof g.home_score !== 'number' || typeof g.away_score !== 'number') continue;
    out.push({
      sport: g.sport,
      home: g.home,
      away: g.away,
      commenceTime: g.commence_time ?? '',
      homeScore: g.home_score,
      awayScore: g.away_score,
      overtime: !!g.overtime,
      periods: (g.periods ?? []).map((p) => ({ home: p.home ?? 0, away: p.away ?? 0 })),
      winner:
        g.winner === 'home' || g.winner === 'away' || g.winner === 'draw'
          ? g.winner
          : g.home_score > g.away_score
            ? 'home'
            : g.away_score > g.home_score
              ? 'away'
              : 'draw',
    });
  }
  return out;
}
