/**
 * Formatage fr-FR : probabilités, cotes, edges, dates.
 * Les montants passent par `lib/currency.ts`.
 */
const pct1 = new Intl.NumberFormat('fr-FR', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const timeFmt = new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' });
const dayFmt = new Intl.DateTimeFormat('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' });
const shortDateFmt = new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: '2-digit' });

/** 0.547 → « 54,7 % ». */
export function formatProba(p: number): string {
  return `${pct1.format(p * 100)} %`;
}

/** 0.547 → « 54,7 » (sans unité). */
export function formatProbaBare(p: number): string {
  return pct1.format(p * 100);
}

/** 0.0819 → « +8,2 % ». */
export function formatEdge(edge: number): string {
  return `${edge >= 0 ? '+' : '−'}${pct1.format(Math.abs(edge) * 100)} %`;
}

/** 2.15 → « 2.15 ». */
export function formatOdds(odds: number): string {
  return odds.toFixed(2);
}

/** Cote équivalente à une probabilité (affichage « cote » des réglages). */
export function probaToOdds(p: number): string {
  return p > 0 ? (1 / p).toFixed(2) : '—';
}

export function formatNumber(value: number, decimals = 2): string {
  return new Intl.NumberFormat('fr-FR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : timeFmt.format(d);
}

export function formatShortDate(iso: string | number): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : shortDateFmt.format(d);
}

export function formatDay(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : dayFmt.format(d);
}

/** « ce soir » / « cette nuit » / « demain ». */
export function dayPhrase(iso: string, now = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((startOf(d) - startOf(now)) / 86_400_000);
  if (diff === 1) return 'demain';
  if (diff === -1) return 'hier';
  if (diff !== 0) return formatDay(iso);
  const h = d.getHours();
  if (h < 5) return 'cette nuit';
  if (h < 12) return 'ce matin';
  if (h < 18) return 'cet après-midi';
  return 'ce soir';
}

/** « il y a 2 h 14 min » — format de la pastille « Prédictions générées ». */
export function timeAgo(iso: string | null, now = Date.now()): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '—';
  const min = Math.max(0, Math.round((now - t) / 60_000));
  if (min < 1) return "à l'instant";
  if (min < 60) return `il y a ${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h < 24) return m ? `il y a ${h} h ${m} min` : `il y a ${h} h`;
  return `il y a ${Math.round(h / 24)} j`;
}

/** Âge des données en heures — bannière « périmées » au-delà de 12 h. */
export function hoursSince(iso: string | null, now = Date.now()): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : (now - t) / 3_600_000;
}

export function isPast(iso: string, now = Date.now()): boolean {
  const t = new Date(iso).getTime();
  return !Number.isNaN(t) && t < now;
}

export const CONFIDENCE_LABEL: Record<string, string> = {
  high: 'élevée',
  medium: 'moyenne',
  low: 'faible',
};

/** Fiabilité historique affichée dans le panneau « Pourquoi ? ». */
export const CONFIDENCE_HINT: Record<string, string> = {
  high: 'le modèle est bien calibré sur ce type de marché',
  medium: 'calibration correcte, échantillon plus bruité',
  low: 'signal faible — à prendre avec prudence',
};
