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

export interface SportPerformance {
  n_games_predicted: number;
  n_games_settled: number;
  from: string | null;
  to: string | null;
  markets: Record<string, MarketPerformance>;
  value_bets: BetPerformance;
  value_bets_by_market: Record<string, BetPerformance>;
}

export interface PerformanceFile {
  generated_at: string;
  min_sample: number;
  sports: Partial<Record<Sport, SportPerformance>>;
}
