import { useData } from '../context/DataContext';
import { useSettings } from '../context/SettingsContext';
import { INDICATIVE_NOTE } from '../data/markets';
import { isBettable } from '../lib/marketPolicy';
import { formatNumber, formatProbaBare } from '../lib/format';
import type { MarketView } from '../types/model';
import { ConfidenceChip, MiniBar, ProbBars } from './Primitives';
import { TeamLogo } from './TeamLogo';
import type { Sport } from '../types/model';

/**
 * Carte marché de l'écran détail. Quatre formes selon `kind` :
 * barres, grand chiffre, totaux par équipe, talent effectif.
 */
export function MarketCard({ market, sport }: { market: MarketView; sport: Sport }) {
  const { policy } = useData();
  // Décision révisable depuis l'Admin, pas propriété de la prédiction : le
  // marché reste affiché et mesuré, on signale seulement qu'on ne le parie pas.
  const bettable = isBettable(policy, sport, market.key);
  const { settings } = useSettings();

  if (market.error) {
    return (
      <section className="vz-mk is-error">
        <header className="vz-mk__head">
          <h3>{market.label}</h3>
        </header>
        <p className="vz-mk__unavailable">Indisponible pour ce match.</p>
        <p className="vz-mk__err">{market.error}</p>
      </section>
    );
  }

  return (
    <section className="vz-mk">
      <header className="vz-mk__head">
        <h3>{market.label}</h3>
        {market.confidence && <ConfidenceChip level={market.confidence} />}
      </header>

      {market.kind === 'bars' && (
        <>
          <ProbBars outcomes={market.outcomes} probFormat={settings.probFormat} />
          {market.hero && (
            <p className="vz-mk__heroInline">
              {formatNumber(market.hero.value, market.hero.decimals ?? 2)}{' '}
              <span>{market.hero.unit}</span>
            </p>
          )}
        </>
      )}

      {market.kind === 'hero' && market.hero && (
        <p className="vz-mk__hero">
          <strong className="vz-num">
            {formatNumber(market.hero.value, market.hero.decimals ?? 1)}
          </strong>
          <span>{market.hero.unit}</span>
        </p>
      )}

      {market.kind === 'teamTotals' && (
        <div className="vz-mk__rows">
          {(market.teamTotals ?? []).map((t) => (
            <div className="vz-mk__row" key={t.team}>
              <TeamLogo sport={sport} code={t.team} size={32} />
              <div className="vz-f1">
                <div className="vz-mk__rowHead">
                  <span>
                    <strong>{t.teamName}</strong> · {t.prediction.toFixed(1)} pts
                  </span>
                  <span className="vz-mk__line">
                    {t.line !== undefined && t.overProba !== undefined
                      ? `O ${t.line} : ${formatProbaBare(t.overProba)} %`
                      : 'ligne indisponible'}
                  </span>
                </div>
                <MiniBar ratio={t.overProba ?? 0} />
              </div>
            </div>
          ))}
        </div>
      )}

      {market.kind === 'talent' && (
        <div className="vz-mk__rows">
          {(market.talent ?? []).map((t) => (
            <div className="vz-mk__row" key={t.team}>
              <TeamLogo sport={sport} code={t.team} size={32} />
              <div className="vz-f1">
                <div className="vz-mk__rowHead">
                  <strong>{t.teamName}</strong>
                  <span className="vz-num">{t.ratio.toFixed(2)}</span>
                </div>
                <MiniBar
                  ratio={Math.min(1, t.ratio)}
                  color={t.ratio >= 1 ? 'var(--value)' : 'var(--warning)'}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {!bettable && <p className="vz-mk__note">{INDICATIVE_NOTE}</p>}
      {market.note && <p className="vz-mk__note">{market.note}</p>}
    </section>
  );
}
