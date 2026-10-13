/**
 * Construction des options « suivre un pari » à partir d'un match.
 *
 * Deux sources de cote :
 *   - la **cote réelle** du bookmaker quand le marché/sélection remonte en
 *     value bet (c'est la seule cote que le backend publie) ;
 *   - sinon la **cote juste** du modèle (1 ÷ probabilité), pré-remplie et
 *     clairement ajustable : c'est à l'utilisateur de saisir la cote qu'il
 *     obtient réellement chez son bookmaker.
 */
import { marketShortLabel } from '../data/markets';
import type { Game } from '../types/model';

export interface FollowOption {
  selection: string;
  name: string;
  odds: number;
  /** true = cote bookmaker réelle, false = cote juste du modèle. */
  real: boolean;
}

export interface FollowMarket {
  key: string;
  label: string;
  options: FollowOption[];
}

export function followMarkets(game: Game): FollowMarket[] {
  const out: FollowMarket[] = [];

  for (const m of game.markets) {
    if (m.error) continue;

    if (m.kind === 'bars' && m.outcomes.length >= 2) {
      // Les distributions longues ne font pas de bons paris pré-remplis.
      const outcomes = m.outcomes.slice(0, 5);
      out.push({
        key: m.key,
        label: marketShortLabel(m.key),
        options: outcomes.map((o) => {
          const vb = game.valueBets.find((v) => v.market === m.key && v.selection === o.key);
          return {
            selection: o.key,
            name: o.label,
            odds: vb ? vb.bookmakerOdds : Number((1 / Math.max(o.probability, 0.01)).toFixed(2)),
            real: !!vb,
          };
        }),
      });
    }

    if (m.kind === 'teamTotals') {
      for (const t of m.teamTotals ?? []) {
        if (t.line === undefined || t.overProba === undefined) continue;
        const key = t.team === game.home ? 'home_team_total' : 'away_team_total';
        const mk = (sel: string, p: number) => {
          const vb = game.valueBets.find((v) => v.market === key && v.selection === sel);
          return {
            selection: sel,
            name: `${sel.startsWith('over') ? 'Over' : 'Under'} ${t.line}`,
            odds: vb ? vb.bookmakerOdds : Number((1 / Math.max(p, 0.01)).toFixed(2)),
            real: !!vb,
          };
        };
        out.push({
          key,
          label: `TOTAL ${t.team}`,
          options: [
            mk(`over_${t.line}`, t.overProba),
            mk(`under_${t.line}`, 1 - t.overProba),
          ],
        });
      }
    }
  }

  return out;
}
