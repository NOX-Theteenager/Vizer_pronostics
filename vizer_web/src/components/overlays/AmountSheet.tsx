import { useEffect, useState } from 'react';
import { useSettings } from '../../context/SettingsContext';
import { currencyLabel, formatMoney, quickAmounts, toBase, toDisplay } from '../../lib/currency';
import { Sheet } from '../Sheet';

/**
 * Saisie d'un montant (dépôt, retrait, objectif, stop-loss, correction d'un
 * mouvement). Le montant est saisi dans la devise affichée et converti en
 * unité de base à la validation.
 */
export function AmountSheet({
  open,
  title,
  hint,
  initial = 0,
  confirmLabel,
  max,
  overdraftMessage,
  showQuickChips = false,
  projected,
  destructive,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  hint?: string;
  /** Montant initial, en unité de base. */
  initial?: number;
  confirmLabel: string;
  /** Plafond en unité de base (retrait limité au solde). */
  max?: number;
  overdraftMessage?: string;
  showQuickChips?: boolean;
  /** Calcule le solde projeté à partir du montant saisi (unité de base). */
  projected?: (amount: number) => string;
  destructive?: { label: string; onClick: () => void };
  onConfirm: (baseAmount: number) => void;
  onClose: () => void;
}) {
  const { settings } = useSettings();
  const [raw, setRaw] = useState('');

  useEffect(() => {
    if (open) setRaw(initial ? String(toDisplay(initial, settings.currency)) : '');
  }, [open, initial, settings.currency]);

  const parsed = Number.parseFloat(raw.replace(',', '.'));
  const base = Number.isFinite(parsed) ? toBase(parsed, settings.currency) : 0;
  const overdraft = max !== undefined && base > max;
  const invalid = !(base > 0) || overdraft;

  return (
    <Sheet open={open} title={title} cancelLabel="Annuler" onClose={onClose}>
      {hint && <p className="vz-note">{hint}</p>}

      <div className="vz-amount">
        <input
          type="number"
          inputMode="decimal"
          min={0}
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          aria-label={`Montant en ${currencyLabel(settings.currency)}`}
          autoFocus
        />
        <span>{currencyLabel(settings.currency)}</span>
      </div>

      {showQuickChips && (
        <div className="vz-amount__chips">
          {quickAmounts(settings.currency).map((a) => (
            <button
              key={a}
              type="button"
              onClick={() => setRaw(String(toDisplay(base + a, settings.currency)))}
            >
              + {formatMoney(a, settings.currency)}
            </button>
          ))}
        </div>
      )}

      {projected && (
        <div className="vz-amount__projected">
          <span>Solde après opération</span>
          <strong className="vz-num">{projected(base)}</strong>
        </div>
      )}

      {overdraft && <p className="vz-amount__error">{overdraftMessage ?? 'Montant trop élevé.'}</p>}

      <div className="vz-row vz-amount__actions">
        {destructive && (
          <button type="button" className="vz-btn vz-btn--danger" onClick={destructive.onClick}>
            {destructive.label}
          </button>
        )}
        <button
          type="button"
          className="vz-btn vz-btn--primary vz-f1"
          disabled={invalid}
          onClick={() => onConfirm(base)}
        >
          {confirmLabel}
        </button>
      </div>
    </Sheet>
  );
}
