import type { ReactNode } from 'react';
import { readableOn } from '../lib/contrast';
import { CONFIDENCE_LABEL, formatProbaBare, probaToOdds } from '../lib/format';
import { SPORTS, type Confidence, type Outcome, type Sport } from '../types/model';
import { teamColor } from '../data/teams';

/* ── Pastille équipe (monogramme, aucun logo officiel) ─────────────────── */
export function Pastille({
  sport,
  code,
  size = 32,
  color,
}: {
  sport: Sport;
  code: string;
  size?: number;
  color?: string;
}) {
  const bg = color ?? teamColor(sport, code);
  return (
    <span
      className="vz-pastille"
      style={{
        width: size,
        height: size,
        background: bg,
        color: readableOn(bg),
        fontSize: Math.round(size * 0.3),
        borderRadius: Math.max(8, Math.round(size * 0.34)),
      }}
      aria-hidden="true"
    >
      {code}
    </span>
  );
}

/* ── Étiquette de ligue (NHL / NBA), teintée par le sport ──────────────── */
export function LeagueTag({ sport }: { sport: Sport }) {
  const meta = SPORTS[sport];
  return (
    <span className="vz-tag" style={{ ['--tag-color' as string]: `var(${meta.colorVar})` }}>
      {meta.league}
    </span>
  );
}

/* ── Badge de confiance : forme ET couleur, plus le mot ────────────────── */
export function ConfidenceChip({ level, compact = false }: { level: Confidence; compact?: boolean }) {
  return (
    <span className={`vz-conf vz-conf--${level}`}>
      <i className="vz-conf__box" aria-hidden="true" />
      {compact ? (
        <span className="vz-sr">Confiance {CONFIDENCE_LABEL[level]}</span>
      ) : (
        CONFIDENCE_LABEL[level]
      )}
    </span>
  );
}

/* ── Barres de probabilité ─────────────────────────────────────────────── */
export function ProbBars({
  outcomes,
  probFormat = 'pct',
}: {
  outcomes: Outcome[];
  probFormat?: 'pct' | 'cote';
}) {
  return (
    <div className="vz-bars">
      {outcomes.map((o) => (
        <div className="vz-bar" key={o.key}>
          <div className="vz-bar__head">
            <span className="vz-bar__name">{o.label}</span>
            <span className="vz-bar__val vz-num">
              {probFormat === 'cote'
                ? `@ ${probaToOdds(o.probability)}`
                : `${formatProbaBare(o.probability)} %`}
            </span>
          </div>
          <div className="vz-bar__track">
            <span
              className="vz-bar__fill"
              style={{
                width: `${Math.max(0, Math.min(100, o.probability * 100))}%`,
                background: o.color ?? 'var(--accent)',
                opacity: o.strong ? 1 : 0.42,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Barre seule (totaux par équipe, talent, taux de réussite). */
export function MiniBar({
  ratio,
  color = 'var(--accent)',
  height = 7,
}: {
  ratio: number;
  color?: string;
  height?: number;
}) {
  return (
    <span className="vz-minibar" style={{ height }}>
      <span
        className="vz-minibar__fill"
        style={{ width: `${Math.max(0, Math.min(100, ratio * 100))}%`, background: color }}
      />
    </span>
  );
}

/* ── Contrôles ─────────────────────────────────────────────────────────── */
export function Chip({
  active,
  onClick,
  children,
  small = false,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  small?: boolean;
}) {
  return (
    <button
      type="button"
      className={`vz-chip${active ? ' is-active' : ''}${small ? ' vz-chip--sm' : ''}`}
      aria-pressed={active}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

export function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={`vz-switch${checked ? ' is-on' : ''}`}
      onClick={() => onChange(!checked)}
    >
      <i className="vz-switch__knob" />
    </button>
  );
}

export function SegButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`vz-seg__btn${active ? ' is-active' : ''}`}
      aria-pressed={active}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

export function SegGroup({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div className="vz-seg" role="group" aria-label={label}>
      {children}
    </div>
  );
}

/** Champ « − valeur + » (cote, mise). */
export function Stepper({
  value,
  onDec,
  onInc,
  label,
}: {
  value: string;
  onDec: () => void;
  onInc: () => void;
  label: string;
}) {
  return (
    <div className="vz-stepper">
      <button type="button" onClick={onDec} aria-label={`Diminuer ${label}`}>
        −
      </button>
      <span className="vz-num">{value}</span>
      <button type="button" onClick={onInc} aria-label={`Augmenter ${label}`}>
        +
      </button>
    </div>
  );
}

export function SectionLabel({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="vz-seclabel">
      <span>{children}</span>
      {action}
    </div>
  );
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`vz-card ${className}`.trim()}>{children}</div>;
}
