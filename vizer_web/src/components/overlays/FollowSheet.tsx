import { useEffect, useMemo, useState } from 'react';
import { useSettings } from '../../context/SettingsContext';
import { currencyLabel, formatMoney, stakeStep, toBase, toDisplay } from '../../lib/currency';
import { followMarkets, type FollowOption } from '../../lib/follow';
import type { Game } from '../../types/model';
import { SPORTS } from '../../types/model';
import { Chip, LeagueTag, Stepper } from '../Primitives';
import { Sheet } from '../Sheet';

export interface FollowDraft {
  market: string;
  marketLabel: string;
  selection: string;
  selectionName: string;
  odds: number;
  stake: number;
}

/**
 * Feuille « Suivre un pari » : choix du marché, de la sélection, puis
 * ajustement de la cote et de la mise.
 */
export function FollowSheet({
  game,
  bankroll,
  preset,
  onClose,
  onConfirm,
  onAddToSlip,
}: {
  game: Game | null;
  bankroll: number;
  /** Pré-sélection venue d'une carte value bet. */
  preset?: { market: string; selection: string; odds: number } | null;
  onClose: () => void;
  onConfirm: (draft: FollowDraft) => void;
  onAddToSlip: (draft: FollowDraft) => void;
}) {
  const { settings } = useSettings();
  const markets = useMemo(() => (game ? followMarkets(game) : []), [game]);
  const [marketKey, setMarketKey] = useState('');
  const [selection, setSelection] = useState('');
  const [odds, setOdds] = useState(2);
  const [stake, setStake] = useState(0);

  // Ouverture : on positionne sur la pré-sélection, sinon sur la première
  // option du premier marché.
  useEffect(() => {
    if (!game || markets.length === 0) return;
    const m =
      (preset && markets.find((x) => x.key === preset.market)) ?? markets[0];
    const o =
      (preset && m.options.find((x) => x.selection === preset.selection)) ?? m.options[0];
    setMarketKey(m.key);
    setSelection(o.selection);
    setOdds(preset?.odds ?? o.odds);
    setStake(Math.max(stakeStep(settings.currency), Math.round(bankroll * 0.01)));
  }, [game, markets, preset, bankroll, settings.currency]);

  if (!game) return null;

  const market = markets.find((m) => m.key === marketKey) ?? markets[0];
  const option: FollowOption | undefined = market?.options.find((o) => o.selection === selection);
  const step = stakeStep(settings.currency);

  const draft = (): FollowDraft => ({
    market: market?.key ?? '',
    marketLabel: market?.label ?? '',
    selection,
    selectionName: option?.name ?? selection,
    odds,
    stake,
  });

  return (
    <Sheet open title="Suivre un pari" cancelLabel="Annuler" onClose={onClose}>
      <p className="vz-follow__match">
        <LeagueTag sport={game.sport} />
        {game.home}–{game.away} · {SPORTS[game.sport].label}
      </p>

      {markets.length === 0 ? (
        <p className="vz-note">Aucun marché exploitable pour ce match.</p>
      ) : (
        <>
          <h4 className="vz-seclabel">Marché</h4>
          <div className="vz-chiprow vz-sc">
            {markets.map((m) => (
              <Chip
                key={m.key}
                active={m.key === market?.key}
                onClick={() => {
                  setMarketKey(m.key);
                  const first = m.options[0];
                  setSelection(first.selection);
                  setOdds(first.odds);
                }}
              >
                {m.label}
              </Chip>
            ))}
          </div>

          <h4 className="vz-seclabel">Sélection</h4>
          <div className="vz-stack vz-follow__sels">
            {(market?.options ?? []).map((o) => {
              const active = o.selection === selection;
              return (
                <button
                  key={o.selection}
                  type="button"
                  className={`vz-selrow${active ? ' is-active' : ''}`}
                  onClick={() => {
                    setSelection(o.selection);
                    setOdds(o.odds);
                  }}
                >
                  <span className="vz-row">
                    <i className="vz-selrow__dot" />
                    <span>{o.name}</span>
                  </span>
                  <span className="vz-num">
                    @ {o.odds.toFixed(2)}
                    {!o.real && <small> juste</small>}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="vz-follow__fields">
            <div className="vz-f1">
              <h4 className="vz-seclabel">Cote</h4>
              <Stepper
                label="la cote"
                value={odds.toFixed(2)}
                onDec={() => setOdds((v) => Math.max(1.01, Number((v - 0.05).toFixed(2))))}
                onInc={() => setOdds((v) => Number((v + 0.05).toFixed(2)))}
              />
            </div>
            <div className="vz-f1">
              <h4 className="vz-seclabel">Mise</h4>
              <Stepper
                label="la mise"
                value={formatMoney(stake, settings.currency)}
                onDec={() => setStake((v) => Math.max(step, v - step))}
                onInc={() => setStake((v) => v + step)}
              />
            </div>
          </div>

          <p className="vz-follow__hint">
            La cote est pré-remplie d'après le modèle ou la meilleure cote connue.
            Ajuste-la pour refléter celle que tu obtiens réellement chez ton bookmaker —
            c'est elle qui détermine ton gain.
          </p>

          <div className="vz-follow__gain">
            <span>Gain potentiel</span>
            <strong className="vz-num">
              {formatMoney(Math.round(stake * odds), settings.currency)}
            </strong>
          </div>

          <div className="vz-row vz-follow__actions">
            <button
              type="button"
              className="vz-btn vz-btn--ghost"
              onClick={() => onAddToSlip(draft())}
            >
              + Ticket
            </button>
            <button
              type="button"
              className="vz-btn vz-btn--primary vz-f1"
              disabled={!(stake > 0 && odds > 1)}
              onClick={() => onConfirm(draft())}
            >
              Suivre ce pari
            </button>
          </div>

          <p className="vz-note vz-note--tiny">
            Montants en {currencyLabel(settings.currency)} · mise réglable par pas de{' '}
            {toDisplay(step, settings.currency)} ·{' '}
            {toBase(1, settings.currency) === 1 ? 'devise de base' : 'converti au taux fixe'}
          </p>
        </>
      )}
    </Sheet>
  );
}
