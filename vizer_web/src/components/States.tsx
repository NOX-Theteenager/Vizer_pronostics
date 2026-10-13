import type { ReactNode } from 'react';
import { formatShortDate } from '../lib/format';
import { IconNoBet, IconRefresh, IconWifiOff } from './Icons';

/* ── Bannières ─────────────────────────────────────────────────────────── */
export function StaleBanner({ generatedAt }: { generatedAt: string | null }) {
  return (
    <div className="vz-banner vz-banner--warn" role="status">
      <i />
      Données du {formatShortDate(generatedAt ?? '')} · les cotes ont pu bouger
    </div>
  );
}

export function OfflineBanner() {
  return (
    <div className="vz-banner vz-banner--muted" role="status">
      <i />
      Hors ligne — dernières prédictions en cache
    </div>
  );
}

export function DemoBanner() {
  return (
    <div className="vz-banner vz-banner--accent" role="status">
      <i />
      Mode démo — échantillons, pas les prédictions du jour
    </div>
  );
}

export function PartialBanner({ sports }: { sports: string[] }) {
  return (
    <div className="vz-banner vz-banner--muted" role="status">
      <i />
      Prédictions {sports.map((s) => s.toUpperCase()).join(' et ')} indisponibles pour ce run
    </div>
  );
}

/* ── Pastille de fraîcheur ─────────────────────────────────────────────── */
export function LivePill({
  label,
  stale,
  busy,
  onClick,
}: {
  label: string;
  stale: boolean;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`vz-livepill${stale ? ' is-stale' : ''}${busy ? ' is-busy' : ''}`}
      onClick={onClick}
    >
      <IconRefresh size={13} /> {busy ? 'actualisation…' : `Prédictions générées ${label}`}
    </button>
  );
}

/* ── Squelettes ────────────────────────────────────────────────────────── */
export function MatchSkeletons({ count = 3 }: { count?: number }) {
  return (
    <div className="vz-stack" role="status" aria-label="Chargement des prédictions">
      {Array.from({ length: count }, (_, i) => (
        <div className="vz-skel" key={i} />
      ))}
    </div>
  );
}

export function RailSkeletons({ count = 2 }: { count?: number }) {
  return (
    <div className="vz-rail" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <div className="vz-skel vz-skel--rail" key={i} />
      ))}
    </div>
  );
}

/* ── États vides ───────────────────────────────────────────────────────── */
export function EmptyState({
  glyph,
  title,
  text,
  action,
  tone = 'accent',
}: {
  glyph: ReactNode;
  title: string;
  text?: ReactNode;
  action?: ReactNode;
  tone?: 'accent' | 'danger' | 'sport';
}) {
  return (
    <div className={`vz-empty vz-empty--${tone}`}>
      <span className="vz-empty__ic">{glyph}</span>
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {action}
    </div>
  );
}

/** Hors-saison — état majoritaire de juin à septembre. */
export function OffSeason({
  sportLabel,
  initial,
  otherLabel,
  otherCount,
  onSwitch,
}: {
  sportLabel: string;
  initial: string;
  otherLabel: string;
  otherCount: number;
  onSwitch: () => void;
}) {
  return (
    <div className="vz-offseason">
      <span className="vz-offseason__disc">{initial}</span>
      <h3>Pas de match {sportLabel} aujourd'hui</h3>
      <p>La saison reprend en octobre. Vizer te préviendra dès le premier value bet.</p>
      {otherCount > 0 && (
        <button type="button" className="vz-btn vz-btn--ghost" onClick={onSwitch}>
          Voir le {otherLabel} →
        </button>
      )}
    </div>
  );
}

/** Aucune donnée, aucun cache. */
export function LoadError({
  online,
  busy,
  onRetry,
  onDemo,
  detail,
}: {
  online: boolean;
  busy: boolean;
  onRetry: () => void;
  onDemo: () => void;
  detail?: string | null;
}) {
  return (
    <div className="vz-empty vz-empty--danger">
      <span className="vz-empty__ic">
        <IconWifiOff size={38} />
      </span>
      <h3>Impossible de charger les prédictions</h3>
      <p>
        {online
          ? "Le fichier de prédictions n'a pas pu être récupéré. Le job quotidien tourne à 7 h UTC."
          : "Vérifie ta connexion. Aucune donnée en cache pour aujourd'hui."}
        {detail && <small className="vz-empty__detail">{detail}</small>}
      </p>
      <div className="vz-row">
        <button type="button" className="vz-btn" onClick={onRetry} disabled={busy}>
          <IconRefresh size={15} /> {busy ? 'Nouvelle tentative…' : 'Réessayer'}
        </button>
        <button type="button" className="vz-btn vz-btn--ghost" onClick={onDemo}>
          Voir une démo
        </button>
      </div>
    </div>
  );
}

export function NoValueBets({ text }: { text: string }) {
  return (
    <div className="vz-norail">
      <IconNoBet size={24} />
      <span>{text}</span>
    </div>
  );
}
