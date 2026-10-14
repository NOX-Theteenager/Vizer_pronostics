/**
 * Clôture d'un pari à partir du score final.
 *
 * Jusqu'ici la clôture était entièrement manuelle : l'utilisateur cochait ✓ ou
 * ✗ dans l'Historique. Le backend publie maintenant les scores finaux
 * (`results/latest.json`, cf. `scripts/publish_results.py`), ce qui permet de
 * régler automatiquement ce qui est réglable **sans ambiguïté**.
 *
 * Le principe directeur est l'abstention. Un pari qu'on ne sait pas trancher
 * reste en attente : une clôture fausse corrompt la bankroll et la courbe, et
 * c'est bien pire qu'une case à cocher. Trois cas d'abstention :
 *
 *   - marché dont la règle de règlement varie selon le bookmaker ;
 *   - ligne entière tombée pile (push : la mise est rendue, ce que le modèle
 *     de bankroll « gagné / perdu » ne sait pas représenter) ;
 *   - score exact et intervalles de buts quand il y a eu prolongation, car
 *     les books règlent les uns sur le temps réglementaire et les autres sur
 *     le score final, et rien dans le pari ne dit lequel.
 */
import type { ComboLeg, FollowedBet } from '../types/bankroll';
import type { GameResult } from '../types/results';

/** `null` = indécidable, on laisse le pari en attente. */
export type Settlement = 'won' | 'lost' | null;

/** Clé d'appariement pari ↔ résultat, identique à `gameId()` du normaliseur. */
export function matchKey(sport: string, home: string, away: string, day: string): string {
  return `${sport}-${away}@${home}-${day || 'na'}`;
}

export function resultIndex(results: GameResult[]): Map<string, GameResult> {
  const map = new Map<string, GameResult>();
  for (const r of results) {
    map.set(matchKey(r.sport, r.home, r.away, r.commenceTime.slice(0, 10)), r);
  }
  return map;
}

/** `YYYY-MM-DD` décalé de `days`, sans toucher au fuseau. */
function shiftDay(day: string, days: number): string | null {
  const t = Date.parse(`${day}T12:00:00Z`);
  if (Number.isNaN(t)) return null;
  return new Date(t + days * 86_400_000).toISOString().slice(0, 10);
}

/**
 * Retrouve le résultat d'un match, à un jour près.
 *
 * L'identifiant d'un match porte la date UTC de son coup d'envoi. Celle du
 * pari vient de l'Odds API, celle du résultat d'ESPN : deux sources qui
 * s'accordent sur l'heure à quelques minutes près, ce qui suffit à les faire
 * tomber de part et d'autre de minuit UTC pour un match du soir américain.
 * On essaie donc la veille et le lendemain avant d'abandonner — les équipes et
 * le sport, eux, lèvent l'ambiguïté.
 */
export function findResult(
  index: Map<string, GameResult>,
  matchId: string,
): GameResult | undefined {
  const exact = index.get(matchId);
  if (exact) return exact;

  const m = /^(.*)-(\d{4}-\d{2}-\d{2})$/.exec(matchId);
  if (!m) return undefined;
  for (const delta of [-1, 1]) {
    const day = shiftDay(m[2], delta);
    if (!day) continue;
    const hit = index.get(`${m[1]}-${day}`);
    if (hit) return hit;
  }
  return undefined;
}

/** Over/Under : `null` si la ligne tombe pile (push), sinon le verdict. */
function overUnder(selection: string, value: number): Settlement {
  const m = /^(over|under)_(-?\d+(?:\.\d+)?)$/.exec(selection);
  if (!m) return null;
  const line = Number(m[2]);
  if (!Number.isFinite(line) || value === line) return null;
  return (m[1] === 'over') === (value > line) ? 'won' : 'lost';
}

function firstPeriod(r: GameResult): { home: number; away: number } | null {
  return r.periods.length ? r.periods[0] : null;
}

/**
 * Verdict d'une sélection simple.
 *
 * @param market    clé backend du marché ('moneyline', 'p1_total'…)
 * @param selection clé de sélection telle que publiée ('home', 'over_5.5'…)
 */
export function settleSelection(
  market: string,
  selection: string,
  r: GameResult,
): Settlement {
  const totalScore = r.homeScore + r.awayScore;

  switch (market) {
    // 'win' est le nom NBA du moneyline.
    case 'moneyline':
    case 'win':
      if (selection !== 'home' && selection !== 'away') return null;
      // Un nul ne peut pas arriver en NHL ni en NBA (prolongation jusqu'à
      // départage), mais le type l'autorise : on s'abstient plutôt que de
      // trancher au hasard.
      if (r.winner === 'draw') return null;
      return r.winner === selection ? 'won' : 'lost';

    case 'total':
      return overUnder(selection, totalScore);

    case 'btts': {
      if (selection !== 'yes' && selection !== 'no') return null;
      const both = r.homeScore > 0 && r.awayScore > 0;
      return both === (selection === 'yes') ? 'won' : 'lost';
    }

    case 'home_team_total':
      return overUnder(selection, r.homeScore);

    case 'away_team_total':
      return overUnder(selection, r.awayScore);

    case 'p1_winner': {
      const p = firstPeriod(r);
      if (!p) return null;
      const actual =
        p.home > p.away ? 'home_lead' : p.away > p.home ? 'away_lead' : 'tied';
      if (!['home_lead', 'away_lead', 'tied'].includes(selection)) return null;
      return actual === selection ? 'won' : 'lost';
    }

    case 'p1_total': {
      const p = firstPeriod(r);
      return p ? overUnder(selection, p.home + p.away) : null;
    }

    case 'p1_btts': {
      const p = firstPeriod(r);
      if (!p || (selection !== 'yes' && selection !== 'no')) return null;
      const both = p.home > 0 && p.away > 0;
      return both === (selection === 'yes') ? 'won' : 'lost';
    }

    case 'exact_score': {
      // Clé publiée « domicile-extérieur » (cf. exact_score.py).
      if (r.overtime) return null;
      const m = /^(\d+)-(\d+)$/.exec(selection);
      if (!m) return null;
      return Number(m[1]) === r.homeScore && Number(m[2]) === r.awayScore
        ? 'won'
        : 'lost';
    }

    case 'goal_intervals': {
      if (r.overtime) return null;
      if (selection.endsWith('+')) {
        const min = Number(selection.slice(0, -1));
        return Number.isFinite(min) && totalScore >= min ? 'won' : 'lost';
      }
      const m = /^(\d+)-(\d+)$/.exec(selection);
      if (!m) return null;
      return totalScore >= Number(m[1]) && totalScore <= Number(m[2]) ? 'won' : 'lost';
    }

    default:
      return null;
  }
}

/**
 * Verdict d'un combiné : perdu dès qu'une jambe tombe, gagné quand **toutes**
 * sont gagnées. Une seule jambe indécidable laisse tout le ticket en attente —
 * sauf si une autre est déjà perdue, auquel cas le combiné est perdu quoi
 * qu'il arrive.
 */
function settleCombo(legs: ComboLeg[], index: Map<string, GameResult>): Settlement {
  let allWon = true;
  for (const leg of legs) {
    // Une jambe porte le `matchId` du match, même construction que `gameId()`
    // du normaliseur.
    const result = findResult(index, leg.matchId);
    if (!result) {
      allWon = false;
      continue;
    }
    const verdict = settleSelection(leg.market, leg.selection, result);
    if (verdict === 'lost') return 'lost';
    if (verdict !== 'won') allWon = false;
  }
  return allWon ? 'won' : null;
}

/**
 * Verdict d'un pari suivi. `null` tant qu'il n'est pas tranchable.
 *
 * Les paris déjà clôturés ne sont jamais réévalués : l'utilisateur a pu
 * corriger à la main, et sa correction fait foi.
 */
export function settleBet(
  bet: FollowedBet,
  index: Map<string, GameResult>,
): Settlement {
  if (bet.status !== 'pending') return null;

  if (bet.combo && bet.legs?.length) return settleCombo(bet.legs, index);

  const result = findResult(index, bet.matchId);
  if (!result) return null;
  return settleSelection(bet.market, bet.selection, result);
}
