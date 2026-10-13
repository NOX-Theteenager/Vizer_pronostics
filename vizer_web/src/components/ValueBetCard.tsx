import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSettings } from '../context/SettingsContext';
import { formatMoney } from '../lib/currency';
import { KELLY_SHORT, kellyStake } from '../lib/kelly';
import {
  CONFIDENCE_HINT,
  CONFIDENCE_LABEL,
  dayPhrase,
  formatEdge,
  formatOdds,
  formatProba,
  formatTime,
} from '../lib/format';
import type { ValueBet } from '../types/model';
import { IconBolt, IconCheck, IconInfo, IconPlus, IconTicket } from './Icons';
import { ConfidenceChip, LeagueTag } from './Primitives';

/** Edge à partir duquel la carte passe en variante « hot » (liseré doré). */
export const HOT_EDGE = 0.08;

/**
 * Carte value bet — composant signature. L'edge est la donnée héros ; le
 * panneau « Pourquoi ? » explicite le calcul sans rien inventer.
 */
export function ValueBetCard({
  bet,
  variant = 'rail',
  index = 0,
  bankroll = 0,
  onFollow,
  onAddSlip,
  inSlip = false,
}: {
  bet: ValueBet;
  variant?: 'rail' | 'full';
  index?: number;
  /** Bankroll en unité de base, pour la mise de Kelly chiffrée. */
  bankroll?: number;
  onFollow?: (bet: ValueBet) => void;
  onAddSlip?: (bet: ValueBet) => void;
  inSlip?: boolean;
}) {
  const { settings } = useSettings();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const hot = bet.edge >= HOT_EDGE;
  // Mise recalculée avec la fraction choisie par l'utilisateur, pas celle
  // figée côté backend.
  const kelly = kellyStake(bet.predictedProba, bet.bookmakerOdds, settings.kellyFraction);
  const showStake = settings.bankrollOn && bankroll > 0 && kelly > 0;
  const stake = Math.round(bankroll * kelly);

  const goMatch = () => navigate(`/match/${bet.gameId}`);

  return (
    <article
      className={`vz-vb vz-vb--${variant}${hot ? ' is-hot' : ''}`}
      style={{ animationDelay: `${index * 70}ms` }}
    >
      <button type="button" className="vz-vb__body" onClick={goMatch}>
        <div className="vz-vb__head">
          <span className="vz-vb__market">
            <IconBolt size={12} /> {bet.marketLabel} · {bet.selectionShort}
          </span>
          <ConfidenceChip level={bet.confidence} />
        </div>

        <div className="vz-vb__hero">
          <span
            className="vz-vb__edge vz-num"
            style={{ animationDelay: `${index * 70 + 120}ms` }}
          >
            {formatEdge(bet.edge)}
          </span>
          <span className="vz-vb__odds vz-num">@ {formatOdds(bet.bookmakerOdds)}</span>
        </div>

        <div className="vz-vb__meta">
          <div>
            Modèle {formatProba(bet.predictedProba)} · Implicite{' '}
            {formatProba(bet.impliedProba)}
          </div>
          <div>
            {kelly > 0
              ? `Mise conseillée ${formatProba(kelly)} (${KELLY_SHORT[settings.kellyFraction]} Kelly)`
              : 'Mise conseillée : aucune'}
            {showStake && ` · ${formatMoney(stake, settings.currency)}`}
          </div>
          <div className="vz-vb__match">
            <LeagueTag sport={bet.sport} />
            {bet.away}–{bet.home} · {dayPhrase(bet.commenceTime)}{' '}
            {formatTime(bet.commenceTime)}
          </div>
        </div>
      </button>

      {/* Le rail reste une carte de lecture : les actions sont sur les écrans
          où l'on décide (détail du match, liste Value bets). */}
      {variant === 'full' && (onFollow || onAddSlip) && (
        <div className="vz-vb__actions">
          <button
            type="button"
            className="vz-vb__why"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            <IconInfo size={13} /> Pourquoi ?
          </button>
          {onAddSlip && (
            <button
              type="button"
              className={`vz-vb__slip${inSlip ? ' is-in' : ''}`}
              onClick={() => onAddSlip(bet)}
              title="Ajouter au ticket combiné"
              aria-label="Ajouter au ticket combiné"
            >
              {inSlip ? <IconCheck size={14} /> : <IconTicket size={15} />}
            </button>
          )}
          {onFollow && (
            <button type="button" className="vz-vb__follow" onClick={() => onFollow(bet)}>
              <IconPlus size={13} /> Suivre
            </button>
          )}
        </div>
      )}

      {variant === 'full' && open && (
        <div className="vz-vb__explain">
          <p>
            Le modèle donne <strong>{formatProba(bet.predictedProba)}</strong> à cette
            issue, la cote n'en price que <strong>{formatProba(bet.impliedProba)}</strong>{' '}
            (1 ÷ {formatOdds(bet.bookmakerOdds)}). L'écart de{' '}
            <strong>{formatEdge(bet.edge)}</strong> est ton avantage théorique.
          </p>
          <p className="vz-vb__conf">
            <IconCheck size={13} /> Confiance {CONFIDENCE_LABEL[bet.confidence]} —{' '}
            {CONFIDENCE_HINT[bet.confidence]}
          </p>
          {bet.books.length > 0 ? (
            <>
              <h5 className="vz-vb__booksTitle">
                Meilleure cote parmi {bet.books.length} book
                {bet.books.length > 1 ? 's' : ''}
              </h5>
              <ul className="vz-books">
                {bet.books.map((b) => (
                  <li key={b.name} className={b.best ? 'is-best' : ''}>
                    <span>{b.name}</span>
                    <strong className="vz-num">@ {formatOdds(b.odds)}</strong>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="vz-vb__books">
              Comparatif indisponible pour ce marché — seule la meilleure cote est
              publiée. Ajuste-la au moment de suivre le pari.
            </p>
          )}
        </div>
      )}
    </article>
  );
}
