/**
 * Statistiques dérivées des paris suivis et des mouvements de bankroll
 * (écrans Historique et Bankroll).
 */
import { marketFamily } from '../data/markets';
import type { FollowedBet, Transaction } from '../types/bankroll';

export interface ProfitSummary {
  settledCount: number;
  wonCount: number;
  pendingCount: number;
  staked: number;
  net: number;
  /** Retour sur investissement des paris, en fraction. `null` si rien de réglé. */
  roi: number | null;
  winRate: number | null;
  up: boolean;
  down: boolean;
  verdict: string;
}

export function computeProfit(followed: FollowedBet[]): ProfitSummary {
  const settled = followed.filter((f) => f.status === 'won' || f.status === 'lost');
  const won = settled.filter((f) => f.status === 'won');
  const staked = settled.reduce((s, f) => s + f.stake, 0);
  const net = settled.reduce((s, f) => s + (f.pnl ?? 0), 0);

  return {
    settledCount: settled.length,
    wonCount: won.length,
    pendingCount: followed.filter((f) => f.status === 'pending').length,
    staked,
    net,
    roi: staked > 0 ? net / staked : null,
    winRate: settled.length ? won.length / settled.length : null,
    up: net > 0,
    down: net < 0,
    verdict: net > 0 ? 'Tu es rentable' : net < 0 ? 'Tu perds de l’argent' : 'Tu es à l’équilibre',
  };
}

export interface GroupStat {
  key: string;
  count: number;
  winRate: number;
  /** ROI en fraction. */
  roi: number;
  pnl: number;
}

function groupBy(bets: FollowedBet[], keyOf: (b: FollowedBet) => string): GroupStat[] {
  const acc = new Map<string, { n: number; w: number; staked: number; pnl: number }>();
  for (const b of bets) {
    const k = keyOf(b);
    const cur = acc.get(k) ?? { n: 0, w: 0, staked: 0, pnl: 0 };
    cur.n += 1;
    if (b.status === 'won') cur.w += 1;
    cur.staked += b.stake;
    cur.pnl += b.pnl ?? 0;
    acc.set(k, cur);
  }
  return [...acc.entries()]
    .map(([key, v]) => ({
      key,
      count: v.n,
      winRate: v.w / v.n,
      roi: v.staked ? v.pnl / v.staked : 0,
      pnl: v.pnl,
    }))
    .sort((a, b) => b.count - a.count);
}

export interface BreakdownStats {
  hasStats: boolean;
  byMarket: GroupStat[];
  byLeague: GroupStat[];
}

export function computeBreakdown(followed: FollowedBet[]): BreakdownStats {
  const settled = followed.filter((f) => f.status === 'won' || f.status === 'lost');
  return {
    hasStats: settled.length > 0,
    byMarket: groupBy(settled, (b) => (b.combo ? 'Combiné' : marketFamily(b.market))),
    byLeague: groupBy(settled, (b) => b.league || '—'),
  };
}

export interface CurvePoint {
  value: number;
  label: string;
}

/**
 * Série de la courbe de bankroll : point de départ puis un point par
 * mouvement, dans l'ordre chronologique.
 */
export function bankrollSeries(
  startBankroll: number,
  transactions: Transaction[],
): CurvePoint[] {
  const ordered = [...transactions].sort((a, b) => a.ts - b.ts);
  const out: CurvePoint[] = [{ value: startBankroll, label: 'Départ' }];
  let running = startBankroll;
  for (const t of ordered) {
    running += t.amount;
    out.push({
      value: running,
      label: new Date(t.ts).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' }),
    });
  }
  if (out.length < 2) out.push({ value: startBankroll, label: "Aujourd'hui" });
  return out;
}

export interface CurveGeometry {
  points: { x: number; y: number; value: number; label: string; index: number }[];
  line: string;
  area: string;
  width: number;
  height: number;
}

/** Géométrie SVG de la courbe (viewBox 300 × 96, marges de 6). */
export function curveGeometry(series: CurvePoint[]): CurveGeometry {
  const W = 300;
  const H = 96;
  const pad = 6;
  const n = series.length;

  let min = Math.min(...series.map((p) => p.value));
  let max = Math.max(...series.map((p) => p.value));
  if (min === max) {
    const e = Math.max(1, Math.abs(min) * 0.02);
    min -= e;
    max += e;
  }
  const span = max - min;

  const x = (i: number) => (n <= 1 ? W / 2 : pad + (i / (n - 1)) * (W - 2 * pad));
  const y = (v: number) => pad + (1 - (v - min) / span) * (H - 2 * pad);

  const points = series.map((p, i) => ({
    x: Number(x(i).toFixed(1)),
    y: Number(y(p.value).toFixed(1)),
    value: p.value,
    label: p.label,
    index: i,
  }));

  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x} ${p.y}`).join(' ');
  const last = points[points.length - 1];
  const first = points[0];
  const area = `${line} L${last.x} ${H} L${first.x} ${H} Z`;

  return { points, line, area, width: W, height: H };
}
