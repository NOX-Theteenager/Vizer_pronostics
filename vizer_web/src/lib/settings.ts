/**
 * Réglages utilisateur (écran Réglages de la maquette v2).
 * Stockage local uniquement.
 */
import type { CurrencyCode } from './currency';
import type { KellyFraction } from './kelly';
import type { Sport } from '../types/model';
import { KEYS, readJson, writeJson } from './storage';

export type ThemeMode = 'dark' | 'light';
export type ProbFormat = 'pct' | 'cote';

export interface Settings {
  theme: ThemeMode;
  currency: CurrencyCode;
  /** Sport ouvert au lancement. */
  defaultSport: Sport;
  /** Afficher les mises chiffrées sur les value bets. */
  bankrollOn: boolean;
  alertsEnabled: boolean;
  /** Seuil d'edge déclencheur, en points de % (4 à 15). */
  alertThreshold: number;
  probFormat: ProbFormat;
  /** Fraction de Kelly appliquée aux mises conseillées (1, ½ ou ¼). */
  kellyFraction: KellyFraction;
  /**
   * Clôturer les paris automatiquement dès que le score final est publié.
   * Seuls les paris tranchables sans ambiguïté sont réglés (cf. `settle.ts`) ;
   * le reste attend une décision manuelle, et toute clôture reste annulable.
   */
  autoSettle: boolean;
  /** Onboarding terminé au moins une fois. */
  onboarded: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  theme: 'dark',
  currency: 'FCFA',
  defaultSport: 'nhl',
  bankrollOn: true,
  alertsEnabled: false,
  alertThreshold: 8,
  probFormat: 'pct',
  kellyFraction: 0.25,
  autoSettle: true,
  onboarded: false,
};

export function loadSettings(): Settings {
  return { ...DEFAULT_SETTINGS, ...readJson<Partial<Settings>>(KEYS.settings, {}) };
}

export function saveSettings(s: Settings): void {
  writeJson(KEYS.settings, s);
}
