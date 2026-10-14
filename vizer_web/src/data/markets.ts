/**
 * Métadonnées des marchés : libellés display (majuscules, comme la maquette),
 * ordre d'affichage et règles de pariabilité.
 *
 * Un marché inconnu reste affichable : le backend peut en ajouter sans casser
 * la PWA.
 */
import type { Sport } from '../types/model';
import { teamName } from './teams';

/** Libellés longs, affichés en tête de carte marché. */
const MARKET_LABELS: Record<string, string> = {
  moneyline: 'VAINQUEUR',
  total: 'TOTAL BUTS',
  btts: 'BTTS',
  p1_winner: '1ʳᵉ PÉRIODE · VAINQUEUR',
  p1_total: '1ʳᵉ PÉRIODE · TOTAL',
  p1_btts: '1ʳᵉ PÉRIODE · BTTS',
  goal_intervals: 'INTERVALLES DE BUTS',
  exact_score: 'SCORE EXACT · TOP 5',
  win: 'VAINQUEUR',
  team_totals: 'TOTAUX PAR ÉQUIPE',
  talent: 'TALENT EFFECTIF (blessures)',
};

const MARKET_LABELS_BY_SPORT: Partial<Record<Sport, Record<string, string>>> = {
  nba: { total: 'TOTAL POINTS' },
};

/** Libellés courts, pour les cartes value bet et le suivi de paris. */
const SHORT_LABELS: Record<string, string> = {
  moneyline: 'MONEYLINE',
  win: 'MONEYLINE',
  total: 'TOTAL',
  btts: 'BTTS',
  p1_winner: '1ʳᵉ PÉRIODE',
  p1_total: 'TOTAL 1ʳᵉ P.',
  p1_btts: 'BTTS 1ʳᵉ P.',
  goal_intervals: 'INTERVALLE',
  exact_score: 'SCORE EXACT',
  home_team_total: 'TOTAL ÉQUIPE',
  away_team_total: 'TOTAL ÉQUIPE',
};

/** Ordre canonique par sport. */
export const MARKET_ORDER: Record<Sport, string[]> = {
  nhl: [
    'moneyline',
    'total',
    'btts',
    'p1_winner',
    'p1_total',
    'p1_btts',
    'goal_intervals',
    'exact_score',
  ],
  nba: ['win', 'total', 'team_totals', 'talent'],
};

/**
 * Marchés écartés des paris **par défaut**.
 *
 * Ce n'est plus qu'une valeur de départ : l'écran Admin surcharge la liste
 * par marché, surcharge qui vit côté serveur et vaut sur tous les appareils
 * (cf. `src/lib/marketPolicy.ts`).
 *
 * Vide aujourd'hui : le total NHL était ici sur un backtest à −11 %, mais la
 * mesure sur paris réels lui donne +11,6 %, et il a été réactivé.
 */
export const INDICATIVE_ONLY: Record<Sport, string[]> = { nhl: [], nba: [] };

export const INDICATIVE_NOTE =
  'Indicatif — écarté des paris proposés. La prédiction continue, et la mesure aussi.';

/** Familles de marchés pour les filtres de l'écran Value bets. */
export const MARKET_FAMILIES: { key: string; label: string; match: (m: string) => boolean }[] = [
  { key: 'all', label: 'Tous marchés', match: () => true },
  { key: 'moneyline', label: 'Moneyline', match: (m) => m === 'moneyline' || m === 'win' },
  { key: 'btts', label: 'BTTS', match: (m) => m === 'btts' || m === 'p1_btts' },
  {
    key: 'total',
    label: 'Total',
    match: (m) => m === 'total' || m === 'p1_total' || m.endsWith('team_total'),
  },
  {
    key: 'autres',
    label: 'Autres',
    match: (m) => ['p1_winner', 'goal_intervals', 'exact_score'].includes(m),
  },
];

export function marketLabel(key: string, sport?: Sport): string {
  if (sport) {
    const o = MARKET_LABELS_BY_SPORT[sport]?.[key];
    if (o) return o;
  }
  return MARKET_LABELS[key] ?? key.replace(/_/g, ' ').toUpperCase();
}

export function marketShortLabel(key: string): string {
  return SHORT_LABELS[key] ?? key.replace(/_/g, ' ').toUpperCase();
}

export function isIndicativeOnly(sport: Sport, key: string): boolean {
  return INDICATIVE_ONLY[sport].includes(key);
}

export function marketRank(sport: Sport, key: string): number {
  const i = MARKET_ORDER[sport].indexOf(key);
  return i === -1 ? MARKET_ORDER[sport].length + 1 : i;
}

/** Nom de la famille d'un marché (filtres, stats par marché). */
export function marketFamily(market: string): string {
  const f = MARKET_FAMILIES.find((x) => x.key !== 'all' && x.match(market));
  return f ? f.label : 'Autres';
}

/**
 * Traduit une clé d'issue backend en libellé lisible.
 *   'home'/'away' → nom d'équipe · 'yes'/'no' → Oui/Non
 *   'over_5.5' → Over 5.5 · 'home_lead' → « TOR mène »
 *   '5-6' → « 5–6 » (intervalle) · '2-3' → « 2–3 » (score exact)
 */
export function outcomeLabel(
  sport: Sport,
  market: string,
  key: string,
  home: string,
  away: string,
): string {
  if (key === 'home') return teamName(sport, home);
  if (key === 'away') return teamName(sport, away);
  if (key === 'yes') return 'Oui';
  if (key === 'no') return 'Non';
  if (key === 'tied') return 'Nul';
  if (key === 'home_lead') return `${home} mène`;
  if (key === 'away_lead') return `${away} mène`;

  const ou = /^(over|under)_(.+)$/.exec(key);
  if (ou) return `${ou[1] === 'over' ? 'Over' : 'Under'} ${ou[2]}`;

  if (market === 'goal_intervals' || market === 'exact_score') {
    return key.replace('-', '–');
  }
  return key;
}

/** Sélection d'un value bet, compréhensible hors contexte. */
export function selectionLabel(
  sport: Sport,
  market: string,
  selection: string,
  home: string,
  away: string,
): string {
  if (selection === 'home') return `${home} ${teamName(sport, home)}`;
  if (selection === 'away') return `${away} ${teamName(sport, away)}`;

  const ou = /^(over|under)_(.+)$/.exec(selection);
  if (ou) {
    const word = ou[1] === 'over' ? 'Over' : 'Under';
    if (market === 'home_team_total') return `${home} ${word} ${ou[2]}`;
    if (market === 'away_team_total') return `${away} ${word} ${ou[2]}`;
    return `${word} ${ou[2]}`;
  }
  if (market === 'btts' || market === 'p1_btts') {
    return selection === 'yes' ? 'BTTS oui' : 'BTTS non';
  }
  return outcomeLabel(sport, market, selection, home, away);
}
