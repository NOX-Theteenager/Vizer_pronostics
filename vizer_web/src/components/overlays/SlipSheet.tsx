import { useState } from 'react';
import { useBankroll } from '../../context/BankrollContext';
import { useSettings } from '../../context/SettingsContext';
import { formatMoney, stakeStep } from '../../lib/currency';
import { IconX } from '../Icons';
import { LeagueTag, Stepper } from '../Primitives';
import { Sheet } from '../Sheet';

/** Ticket combiné : plusieurs sélections, cote multipliée. */
export function SlipSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { settings } = useSettings();
  const { slip, slipOdds, removeSlipLeg, clearSlip, confirmSlip } = useBankroll();
  const step = stakeStep(settings.currency);
  const [stake, setStake] = useState(step * 5);

  const needMore = slip.length < 2;

  return (
    <Sheet open={open} title="Ticket combiné" onClose={onClose}>
      <div className="vz-slip__head">
        <button type="button" className="vz-slip__clear" onClick={clearSlip}>
          Vider
        </button>
      </div>

      <div className="vz-stack">
        {slip.map((l) => (
          <div className="vz-slip__leg" key={l.key}>
            <div className="vz-f1">
              <div className="vz-row vz-slip__legTop">
                <LeagueTag sport={l.sport} />
                <span>{l.matchLabel}</span>
              </div>
              <strong>
                {l.market} · {l.selection}
              </strong>
            </div>
            <span className="vz-num">@ {l.odds.toFixed(2)}</span>
            <button
              type="button"
              onClick={() => removeSlipLeg(l.key)}
              aria-label={`Retirer ${l.selection}`}
              className="vz-slip__rm"
            >
              <IconX size={11} />
            </button>
          </div>
        ))}
      </div>

      {needMore && (
        <p className="vz-note vz-note--center">
          Ajoute au moins 2 sélections pour former un combiné.
        </p>
      )}

      <div className="vz-slip__row">
        <span>Cote combinée</span>
        <strong className="vz-num vz-slip__odds">{slipOdds.toFixed(2)}</strong>
      </div>

      <div className="vz-slip__row">
        <span>Mise</span>
        <Stepper
          label="la mise"
          value={formatMoney(stake, settings.currency)}
          onDec={() => setStake((v) => Math.max(step, v - step))}
          onInc={() => setStake((v) => v + step)}
        />
      </div>

      <div className="vz-slip__gain">
        <span>Gain potentiel</span>
        <strong className="vz-num">
          {formatMoney(Math.round(stake * slipOdds), settings.currency)}
        </strong>
      </div>

      <button
        type="button"
        className="vz-btn vz-btn--primary vz-btn--block"
        disabled={needMore}
        onClick={() => {
          if (confirmSlip(stake)) onClose();
        }}
      >
        Suivre le combiné
      </button>
    </Sheet>
  );
}
