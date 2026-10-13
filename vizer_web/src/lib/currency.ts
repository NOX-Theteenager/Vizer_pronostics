/**
 * Devises — repris de `CURRENCIES` / `fmtEur` de la maquette v2.
 *
 * Les montants sont **stockés en unité de base (FCFA)** et convertis à
 * l'affichage. Changer de devise ne change donc jamais la valeur enregistrée,
 * seulement sa présentation.
 */
export type CurrencyCode = 'FCFA' | 'EUR' | 'USD';

export interface Currency {
  code: CurrencyCode;
  /** Combien d'unités de base vaut 1 unité de cette devise. */
  rate: number;
  decimals: number;
  /** Suffixe affiché, espace incluse. */
  suffix: string;
  name: string;
  symbol: string;
}

export const CURRENCIES: Record<CurrencyCode, Currency> = {
  FCFA: { code: 'FCFA', rate: 1, decimals: 0, suffix: ' FCFA', name: 'Franc CFA', symbol: 'FCFA' },
  EUR: { code: 'EUR', rate: 655.957, decimals: 2, suffix: ' €', name: 'Euro', symbol: '€' },
  USD: { code: 'USD', rate: 605, decimals: 2, suffix: ' $', name: 'Dollar US', symbol: '$' },
};

export const CURRENCY_CODES: CurrencyCode[] = ['FCFA', 'EUR', 'USD'];

/** Espace fine insécable tous les 3 chiffres, comme la maquette. */
function groupThousands(s: string): string {
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

/**
 * Formate un montant en unité de base vers la devise active.
 * Toujours en valeur absolue : le signe est porté par `formatPnl`.
 */
export function formatMoney(baseAmount: number, code: CurrencyCode): string {
  const c = CURRENCIES[code] ?? CURRENCIES.FCFA;
  const v = Math.abs(baseAmount) / c.rate;
  let s: string;
  if (c.decimals === 0) {
    s = groupThousands(Math.round(v).toString());
  } else {
    const parts = v.toFixed(c.decimals).replace('.', ',').split(',');
    parts[0] = groupThousands(parts[0]);
    s = parts.join(',');
  }
  return s + c.suffix;
}

/** « + 7 100 FCFA » / « – 10 000 FCFA ». */
export function formatPnl(baseAmount: number, code: CurrencyCode): string {
  return (baseAmount >= 0 ? '+ ' : '– ') + formatMoney(baseAmount, code);
}

/** Saisie utilisateur (dans la devise affichée) → unité de base. */
export function toBase(displayAmount: number, code: CurrencyCode): number {
  const c = CURRENCIES[code] ?? CURRENCIES.FCFA;
  return Math.round(displayAmount * c.rate);
}

/** Unité de base → nombre à mettre dans un `<input type="number">`. */
export function toDisplay(baseAmount: number, code: CurrencyCode): number {
  const c = CURRENCIES[code] ?? CURRENCIES.FCFA;
  return Number((baseAmount / c.rate).toFixed(c.decimals));
}

/** Suffixe nu (« FCFA », « € », « $ ») pour les champs de saisie. */
export function currencyLabel(code: CurrencyCode): string {
  return (CURRENCIES[code] ?? CURRENCIES.FCFA).suffix.trim();
}

/** Montants des puces de dépôt rapide, adaptés à l'ordre de grandeur. */
export function quickAmounts(code: CurrencyCode): number[] {
  return code === 'FCFA' ? [5000, 10000, 25000, 50000] : [5000, 10000, 25000, 50000];
}

/** Pas d'incrément de mise, en unité de base. */
export function stakeStep(code: CurrencyCode): number {
  return code === 'FCFA' ? 1000 : Math.round(5 * CURRENCIES[code].rate);
}
