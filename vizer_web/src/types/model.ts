/**
 * Modèle de vue unifié — la seule forme que les écrans connaissent.
 *
 * NHL et NBA arrivent avec deux schémas backend différents (cf. `raw.ts`) ;
 * tout est aplati ici pour que carte match, carte marché et carte value bet
 * soient partagées entre les deux sports.
 */
import type { Confidence, Sport } from './raw';

export type { Confidence, Sport };

/** Métadonnées d'affichage d'un sport (libellés de la maquette v2). */
export interface SportMeta {
  key: Sport;
  /** « Hockey » / « Basket » — ce que voit l'utilisateur. */
  label: string;
  /** « NHL » / « NBA » — la ligue. */
  league: string;
  /** Variable CSS de l'accent de sport. */
  colorVar: string;
}

export const SPORTS: Record<Sport, SportMeta> = {
  nhl: { key: 'nhl', label: 'Hockey', league: 'NHL', colorVar: '--hockey' },
  nba: { key: 'nba', label: 'Basket', league: 'NBA', colorVar: '--basket' },
};

export const SPORT_KEYS: Sport[] = ['nhl', 'nba'];

/** Une issue d'un marché, prête à être barrée à l'écran. */
export interface Outcome {
  key: string;
  label: string;
  probability: number;
  /** Couleur imposée (couleur d'équipe, vert pour « oui »). */
  color?: string;
  /** Issue mise en avant — barre pleine opacité. */
  strong?: boolean;
}

export interface TeamTotalRow {
  team: string;
  teamName: string;
  prediction: number;
  line?: number;
  overProba?: number;
}

export interface TalentRow {
  team: string;
  teamName: string;
  ratio: number;
}

export type MarketKind = 'bars' | 'hero' | 'teamTotals' | 'talent';

export interface MarketView {
  key: string;
  /** Libellé display en majuscules (« TOTAL BUTS · O/U 5.5 »). */
  label: string;
  kind: MarketKind;
  outcomes: Outcome[];
  /** Stat héro : grand chiffre (kind 'hero') ou ligne sous les barres. */
  hero?: { value: number; unit: string; decimals?: number; inline?: boolean };
  teamTotals?: TeamTotalRow[];
  talent?: TalentRow[];
  confidence?: Confidence;
  /** Mention en italique ambre (« Indicatif — non pariable »). */
  note?: string;
  /** Erreur backend → carte « Indisponible pour ce match ». */
  error?: string;
}

export interface Book {
  name: string;
  odds: number;
  best: boolean;
}

export interface TeamForm {
  results: ('W' | 'L' | 'D')[];
  wins: number;
  draws: number;
  losses: number;
  goalsFor: number;
  goalsAgainst: number;
}

export interface HeadToHead {
  date: string;
  home: string;
  away: string;
  homeScore: number;
  awayScore: number;
  winner: 'home' | 'away' | null;
}

export interface Factor {
  feature: string;
  label: string;
  value: number | null;
  contribution: number;
  direction: 'home' | 'away';
}

export interface ValueBet {
  id: string;
  sport: Sport;
  gameId: string;
  home: string;
  away: string;
  commenceTime: string;
  market: string;
  /** Libellé display court (« MONEYLINE », « BTTS OUI »). */
  marketLabel: string;
  selection: string;
  /** Sélection lisible hors contexte (« MTL Canadiens », « BTTS oui »). */
  selectionLabel: string;
  /** Libellé court, pour les cartes qui affichent déjà le marché (« Oui »). */
  selectionShort: string;
  predictedProba: number;
  bookmakerOdds: number;
  impliedProba: number;
  edge: number;
  /** Fraction de bankroll, déjà fractionnée par kelly_factor côté backend. */
  kellyStake: number;
  confidence: Confidence;
  /** Comparatif entre bookmakers ; vide si le marché n'est pas couvert. */
  books: Book[];
}

export interface Game {
  id: string;
  sport: Sport;
  home: string;
  away: string;
  homeName: string;
  awayName: string;
  homeColor: string;
  awayColor: string;
  commenceTime: string;
  homeWinProba?: number;
  awayWinProba?: number;
  /** Puces sous la carte (« E[buts] 5.9 », « BTTS 88 % »). */
  chips: string[];
  markets: MarketView[];
  valueBets: ValueBet[];
  hasOdds: boolean;
  talent?: { home: number; away: number };
  /** Forme récente des deux équipes (absente si le backend ne la publie pas). */
  form?: { home: TeamForm | null; away: TeamForm | null };
  h2h: HeadToHead[];
  /** Facteurs SHAP de la prédiction (vide si le modèle n'est pas explicable). */
  factors: Factor[];
  error?: string;
}

/**
 * Un marché dont les paris ont été retenus à la publication, et pourquoi.
 *
 * Publié par `predict_all.py` quand le garde-fou directionnel s'est déclenché.
 * Existe pour que l'absence d'un marché ne soit jamais muette : un marché qui
 * disparaît sans explication est exactement le défaut qu'on cherche à éviter.
 */
export interface WithheldMarket {
  market: string;
  side: string;
  reason: string;
}

export interface SportFeed {
  sport: Sport;
  generatedAt: string | null;
  modelsTrainedAt: string | null;
  modelVersion: string | null;
  games: Game[];
  withheldMarkets: WithheldMarket[];
  message?: string;
  detectionSource?: string;
}

export type FeedOrigin = 'network' | 'cache' | 'mock';
