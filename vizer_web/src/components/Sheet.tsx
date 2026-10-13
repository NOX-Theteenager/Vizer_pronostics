import { useEffect, useRef, type ReactNode } from 'react';

/**
 * Feuille modale basse (maquette v2) : poignée, scrim cliquable, fermeture à
 * l'Échap, scroll interne et focus déplacé dans le panneau.
 */
export function Sheet({
  open,
  title,
  onClose,
  cancelLabel = 'Fermer',
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  cancelLabel?: string;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="vz-sheet">
      <button type="button" className="vz-sheet__scrim" aria-label="Fermer" onClick={onClose} />
      <div
        className="vz-sheet__panel vz-sc"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={panel}
      >
        <span className="vz-sheet__grip" aria-hidden="true" />
        <div className="vz-sheet__head">
          <h2 className="vz-sheet__title">{title}</h2>
          <span className="vz-f1" />
          <button type="button" className="vz-sheet__close" onClick={onClose}>
            {cancelLabel}
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Plein écran (recherche, onboarding, splash, notification). */
export function FullOverlay({
  open,
  children,
  onBackdrop,
  className = '',
  label,
}: {
  open: boolean;
  children: ReactNode;
  onBackdrop?: () => void;
  className?: string;
  label: string;
}) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open) return null;
  return (
    <div
      className={`vz-overlay ${className}`.trim()}
      role="dialog"
      aria-modal="true"
      aria-label={label}
      onClick={onBackdrop}
    >
      {children}
    </div>
  );
}
