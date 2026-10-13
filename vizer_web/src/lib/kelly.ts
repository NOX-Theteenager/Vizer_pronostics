/**
 * Mise de Kelly, recalculée côté client.
 *
 * Le backend publie déjà `kelly_stake`, mais avec **sa** fraction (0,25 figée
 * dans `config.yaml`). La maquette laisse l'utilisateur choisir son appétit au
 * risque : on recalcule donc depuis la probabilité du modèle et la cote, puis
 * on applique la fraction choisie et un plafond dur.
 *
 *     f* = (p × cote − 1) / (cote − 1)
 */

/** Fractions proposées dans les réglages. */
export const KELLY_FRACTIONS = [1, 0.5, 0.25] as const;
export type KellyFraction = (typeof KELLY_FRACTIONS)[number];

/** Plafond de sécurité : jamais plus de 5 % de la bankroll sur un pari. */
export const KELLY_CAP = 0.05;

export const KELLY_LABEL: Record<number, string> = {
  1: 'Plein',
  0.5: '½ Kelly',
  0.25: '¼ Kelly',
};

/** Libellé court accolé au pourcentage (« 2,2 % (¼ Kelly) »). */
export const KELLY_SHORT: Record<number, string> = {
  1: 'plein',
  0.5: '½',
  0.25: '¼',
};

export const KELLY_HINT: Record<number, string> = {
  1: 'Croissance maximale, mais variance très forte. Réservé aux edges très fiables.',
  0.5: 'Bon compromis : environ 75 % de la croissance pour moitié moins de variance.',
  0.25: "Prudent : recommandé tant que le modèle n'a pas fait ses preuves sur ton historique.",
};

/**
 * Fraction de bankroll à engager, déjà plafonnée.
 * Retourne 0 quand le pari n'a pas d'avantage (edge négatif ou nul).
 */
export function kellyStake(
  predictedProba: number,
  odds: number,
  fraction: number,
): number {
  if (!(odds > 1) || !(predictedProba > 0)) return 0;
  const full = (predictedProba * odds - 1) / (odds - 1);
  if (!(full > 0)) return 0;
  return Math.min(KELLY_CAP, full * fraction);
}
