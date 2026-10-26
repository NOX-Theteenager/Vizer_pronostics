/**
 * Performance réelle des prédictions publiées.
 *
 * Produit par `scripts/export_performance.py`, qui joint `predictions/archive/`
 * et `results/`. À ne pas confondre avec l'écran Historique : celui-ci répond
 * à « comment je m'en sors », celui-là à « le modèle a-t-il raison » — sur
 * toutes les prédictions, y compris celles que personne n'a suivies.
 */
import type { Sport } from './model';

/** Un point de la courbe de calibration : prédit vs réalisé. */
export interface CalibrationBucket {
  from: number;
  to: number;
  n: number;
  actual: number;
}

export interface MarketPerformance {
  n: number;
  /** Vrai quand l'échantillon est trop petit : aucun autre champ n'est fourni. */
  insufficient?: boolean;
  accuracy?: number;
  brier?: number;
  log_loss?: number;
  calibration?: CalibrationBucket[];
}

export interface BetPerformance {
  n: number;
  insufficient?: boolean;
  won?: number;
  hit_rate?: number;
  avg_edge?: number;
  /** Rendement à mise plate, une unité par pari. */
  roi_flat?: number;
  /** Rendement rapporté au capital réellement engagé en Kelly. */
  roi_kelly?: number | null;
}

/**
 * Décalage de niveau d'une prédiction ponctuelle (total de buts, de points,
 * total d'équipe) face au réel.
 *
 * Sépare « le modèle se trompe » de « le modèle se trompe toujours du même
 * côté », qui n'appellent pas la même correction. Un Brier ne distingue pas
 * les deux : un modèle qui annonce un demi-but de trop à chaque match peut
 * rester bien classé tout en étant inexploitable.
 */
export interface LevelPerformance {
  n: number;
  insufficient?: boolean;
  mean_predicted?: number;
  mean_actual?: number;
  /** Prédit − réel. Négatif = le modèle annonce moins que ce qui arrive. */
  bias?: number;
  mae?: number;
  sd?: number;
  stderr?: number | null;
  /** Nombre d'erreurs-types entre le biais et zéro. Au-delà de 2, ce n'est plus du hasard. */
  z?: number | null;
}

export interface SportPerformance {
  n_games_predicted: number;
  n_games_settled: number;
  from: string | null;
  to: string | null;
  markets: Record<string, MarketPerformance>;
  /** Absent des résumés produits avant la mise en place de cette mesure. */
  levels?: Record<string, LevelPerformance>;
  value_bets: BetPerformance;
  value_bets_by_market: Record<string, BetPerformance>;
}

export interface PerformanceFile {
  generated_at: string;
  min_sample: number;
  sports: Partial<Record<Sport, SportPerformance>>;
}

/* ── Sens des paris ───────────────────────────────────────────────────────── */

/**
 * Verdict directionnel d'un marché, produit par
 * `scripts/check_market_direction.py`.
 *
 * `withheld`   : le marché n'a jamais parié de l'autre côté sur la fenêtre.
 *                Son rendement n'est donc pas une mesure de sélection — c'est
 *                un pari directionnel unique, joué n fois. Les paris du côté
 *                dominant ne sont plus proposés.
 * `imbalanced` : très déséquilibré, mais le côté minoritaire existe. On
 *                affiche, on ne retient rien.
 */
export type DirectionStatus = 'ok' | 'imbalanced' | 'withheld' | 'insufficient';

export interface DirectionVerdict {
  market: string;
  status: DirectionStatus;
  n: number;
  /** Nombre de paris par sens : `{ under: 39 }`, `{ away: 49, home: 9 }`. */
  counts: Record<string, number>;
  dominant: string | null;
  minority: number;
  /** Sens dont les paris sont retenus à la publication, si verdict `withheld`. */
  withhold: string | null;
  from: string | null;
  to: string | null;
  reason: string;
}

export interface DirectionFile {
  generated_at: string;
  window_days: number;
  thresholds: {
    min_sample: number;
    min_sample_imbalance: number;
    minority_share: number;
  };
  sports: Partial<Record<Sport, DirectionVerdict[]>>;
}


/* ── Fraîcheur des données ────────────────────────────────────────────────── */

/**
 * Les données d'entraînement suivent-elles la saison ?
 *
 * Produit par `scripts/check_data_freshness.py`, qui compare la dernière date
 * du dataset au dernier match **effectivement joué** d'après ESPN — pas au
 * calendrier. Treize jours d'écart en pleine saison sont une panne, les mêmes
 * en juillet ne sont rien.
 *
 * `unknown`   : dataset introuvable ou sans colonne de date — on ne conclut pas.
 * `offseason` : aucun match joué depuis dix jours, rien à rattraper.
 */
export type FreshnessStatus = 'fresh' | 'stale' | 'offseason' | 'unknown';

export interface SportFreshness {
  sport: string;
  status: FreshnessStatus;
  /** Dernier match présent dans le dataset d'entraînement. */
  last_in_data?: string;
  /** Dernier match joué, d'après ESPN. */
  last_played?: string;
  lag_days?: number;
  max_lag_days?: number;
  detail?: string;
}

export interface FreshnessFile {
  generated_at: string;
  /** Sports au-delà du seuil de retard. */
  stale: string[];
  sports: Partial<Record<Sport, SportFreshness>>;
}
