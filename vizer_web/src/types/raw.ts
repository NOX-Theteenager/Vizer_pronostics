/**
 * Formes JSON **réellement** produites par le backend.
 *
 * Source : `vizer_nhl/predict_all.py --json` et `vizer_nba/predict_all.py --json`,
 * publiées par le workflow « Vizer Daily Predictions » sur la branche
 * models-artifacts sous `predictions/latest/<sport>.json`.
 *
 * ⚠️ Les deux sports ne partagent PAS le même schéma, et pas non plus la même
 * sérialisation de value bet :
 *   - NHL (`vizer_nhl/src/api/value_finder.py`) → predicted_proba / kelly_stake
 *   - NBA (`vizer_nba/src/api/value_finder.py`) → mêmes noms depuis
 *     l'unification ; les archives plus anciennes portent
 *     predicted_probability / kelly_stake_fraction / implied_probability,
 *     que le normaliseur accepte toujours.
 * La normalisation (`src/types/normalize.ts`) absorbe cet écart ; aucun écran
 * ne lit ces types directement.
 */
export type Sport = 'nhl' | 'nba';
export type Confidence = 'high' | 'medium' | 'low';

/** Un marché en erreur est publié tel quel : le reste du match reste valide. */
export interface RawMarketError {
  error: string;
}

/** NHL : MarketPrediction sérialisé (cf. vizer_core/market_base.py). */
export interface RawNhlMarket {
  probabilities: Record<string, number>;
  expected_value: number | null;
  confidence: Confidence;
  metadata?: Record<string, unknown>;
}

export type RawNhlMarketEntry = RawNhlMarket | RawMarketError;

/** Value bet NHL. */
export interface RawNhlValueBet {
  market: string;
  selection: string;
  predicted_proba: number;
  bookmaker_odds: number;
  edge: number;
  kelly_stake: number;
  confidence: Confidence;
  books?: RawBook[];
}

/** Cote d'un bookmaker sur la même sélection (comparatif). */
export interface RawBook {
  name: string;
  odds: number;
  best: boolean;
}

/** Forme récente d'une équipe sur ses 5 derniers matchs. */
export interface RawForm {
  /** 'W' | 'L' | 'D' — un 'D' NHL signifie « décidé aux tirs au but ». */
  results: string[];
  wins: number;
  draws: number;
  losses: number;
  goals_for: number;
  goals_against: number;
}

/** Une confrontation directe passée. */
export interface RawH2H {
  date: string;
  home: string;
  away: string;
  home_score: number;
  away_score: number;
  /** Vainqueur exprimé par rapport au match À VENIR ('home' | 'away' | null). */
  winner: 'home' | 'away' | null;
}

/** Contribution SHAP d'une feature à la prédiction de ce match. */
export interface RawFactor {
  feature: string;
  label: string;
  value: number | null;
  /** Positif = pousse vers l'équipe à domicile. */
  contribution: number;
  direction: 'home' | 'away';
}

/** Champs d'enrichissement communs aux deux sports. */
export interface RawContext {
  form?: { home: RawForm | null; away: RawForm | null };
  h2h?: RawH2H[];
  factors?: RawFactor[];
}

export interface RawNhlGame extends RawContext {
  home: string;
  away: string;
  commence_time: string;
  /** `predictions` = `results['markets']` côté backend. */
  predictions: Record<string, RawNhlMarketEntry>;
  value_bets: RawNhlValueBet[];
}

/**
 * Value bet NBA.
 *
 * Les noms sont désormais ceux de la NHL — la sérialisation a été unifiée dans
 * `vizer_nba/src/api/value_finder.py`. Les anciens noms restent déclarés et
 * acceptés : les archives publiées avant l'unification les portent toujours, et
 * l'écran Historique les relit.
 */
export interface RawNbaValueBet {
  market: string;
  selection: string;
  predicted_proba?: number;
  bookmaker_odds: number;
  implied_proba?: number;
  edge: number;
  kelly_stake?: number;
  expected_value_per_unit?: number;
  confidence: Confidence;
  books?: RawBook[];
  /** @deprecated archives antérieures à l'unification. */
  predicted_probability?: number;
  /** @deprecated archives antérieures à l'unification. */
  implied_probability?: number;
  /** @deprecated archives antérieures à l'unification. */
  kelly_stake_fraction?: number;
}

export interface RawNbaTeamTotal {
  prediction: number;
  line_default: number;
  over_default_proba: number;
}

export interface RawNbaPredictions {
  home_team?: string;
  away_team?: string;
  win?: { prediction: number; home_win_proba: number; away_win_proba: number };
  total?: { prediction: number };
  talent?: { home_ratio: number; away_ratio: number };
  home_team_total?: RawNbaTeamTotal;
  away_team_total?: RawNbaTeamTotal;
  /** `predict_all.py` encapsule toute exception de prédiction ici. */
  error?: string;
}

export interface RawNbaGame extends RawContext {
  home: string;
  away: string;
  commence_time: string;
  has_odds: boolean;
  predictions: RawNbaPredictions;
  value_bets: RawNbaValueBet[];
}

/** Enveloppe commune aux deux sports. */
export interface RawFeed<G> {
  /** Injecté par le workflow (step « Injecter generated_at »). */
  generated_at?: string;
  n_games?: number;
  /** NBA uniquement : 'nba_api' | 'odds_api' | … */
  detection_source?: string;
  /** Date d'entraînement des modèles qui ont produit ces prédictions. */
  models_trained_at?: string | null;
  /** Version lisible du modèle (« v2026.10.06 »). */
  model_version?: string | null;
  games: G[];
  /**
   * Marchés dont les paris ont été retenus par le garde-fou directionnel.
   * Absent des archives antérieures à sa mise en service.
   */
  withheld_markets?: { market: string; side: string; reason: string }[];
  /** Hors-saison : `{ games: [], message: 'no games' }`. */
  message?: string;
}

export type RawNhlFeed = RawFeed<RawNhlGame>;
export type RawNbaFeed = RawFeed<RawNbaGame>;
