/**
 * Choix du texte noir ou blanc sur une couleur d'équipe (design.md §5.5/§9).
 * Luminance relative WCAG — garantit un ratio ≥ 4.5:1 dans les deux sens pour
 * les monogrammes, y compris sur les fonds très clairs (SAS, SEA, LAK).
 */
function srgbToLinear(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '').trim();
  const full =
    h.length === 3
      ? h
          .split('')
          .map((c) => c + c)
          .join('')
      : h;
  const n = Number.parseInt(full.slice(0, 6), 16);
  if (Number.isNaN(n)) return [91, 102, 122];
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function luminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

/** Couleur de texte lisible sur `hex`. */
export function readableOn(hex: string): '#ffffff' | '#0b0e14' {
  return luminance(hex) > 0.4 ? '#0b0e14' : '#ffffff';
}

/** `#AF1E2D` + 0.12 → `rgba(175, 30, 45, 0.12)` pour les dégradés de carte. */
export function rgba(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Surfaces de carte par thème (cf. --surface dans tokens.css). */
const SURFACE: Record<'dark' | 'light', string> = {
  dark: '#141926',
  light: '#ffffff',
};

/** Ratio de contraste WCAG entre deux couleurs. */
export function contrastRatio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

function mix(hex: string, toward: [number, number, number], amount: number): string {
  const [r, g, b] = hexToRgb(hex);
  const c = (x: number, t: number) => Math.round(x + (t - x) * amount);
  return `#${[c(r, toward[0]), c(g, toward[1]), c(b, toward[2])]
    .map((v) => v.toString(16).padStart(2, '0'))
    .join('')}`;
}

/**
 * Couleur d'équipe utilisable **en texte** sur une carte.
 *
 * Certaines couleurs officielles sont quasi noires (DEN #0E2240, WPG #041E42) :
 * telles quelles sur le fond sombre, elles tombent sous 2:1. On les éclaircit
 * (ou assombrit en thème clair) jusqu'à atteindre AA 4.5:1, en gardant la
 * teinte — l'équipe reste reconnaissable, le chiffre reste lisible (§9).
 */
export function readableAccent(hex: string, theme: 'dark' | 'light'): string {
  const bg = SURFACE[theme];
  const target: [number, number, number] = theme === 'dark' ? [255, 255, 255] : [0, 0, 0];
  let out = hex;
  for (let i = 0; i < 12 && contrastRatio(out, bg) < 4.5; i += 1) {
    out = mix(out, target, 0.12);
  }
  return out;
}
