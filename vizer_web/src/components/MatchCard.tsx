import { Link } from 'react-router-dom';
import { useSettings } from '../context/SettingsContext';
import { dayPhrase, formatOdds, formatProbaBare, formatTime, isPast, probaToOdds } from '../lib/format';
import type { Game } from '../types/model';
import { LeagueTag } from './Primitives';

/**
 * Carte match — « arène » aux couleurs des deux équipes, avec la courbe de
 * gradin, le rond VS, les deux grands pourcentages, puis la ligne d'heure et
 * les puces de stats. Reprise de la maquette v2.
 */
export function MatchCard({ game, index = 0 }: { game: Game; index?: number }) {
  const { settings } = useSettings();
  const started = isPast(game.commenceTime);
  const topVb = game.valueBets[0];
  const showVb = !!topVb && !started;
  const hasDuel = game.homeWinProba !== undefined && game.awayWinProba !== undefined;

  const pct = (p?: number) =>
    p === undefined ? '—' : settings.probFormat === 'cote' ? probaToOdds(p) : formatProbaBare(p);

  return (
    <Link
      to={`/match/${game.id}`}
      className={`vz-match${started ? ' is-started' : ''}`}
      style={{ animationDelay: `${index * 70}ms` }}
      aria-label={`${game.home} contre ${game.away}, ${formatTime(game.commenceTime)}`}
    >
      <div
        className="vz-arena"
        style={{
          backgroundImage: `linear-gradient(105deg, ${game.homeColor} 0%, ${game.homeColor} 38%, transparent 60%), linear-gradient(285deg, ${game.awayColor} 0%, ${game.awayColor} 32%, transparent 56%)`,
        }}
      >
        <ArenaCurve height={128} />

        <span className="vz-arena__vs">VS</span>

        <div className="vz-arena__team vz-arena__team--left">
          <strong>{game.home}</strong>
          <span>{game.homeName}</span>
        </div>
        <div className="vz-arena__team vz-arena__team--right">
          <strong>{game.away}</strong>
          <span>{game.awayName}</span>
        </div>

        {hasDuel && (
          <>
            <div className="vz-arena__pct vz-arena__pct--left vz-num">
              {pct(game.homeWinProba)}
              {settings.probFormat === 'pct' && <small>%</small>}
            </div>
            <div className="vz-arena__pct vz-arena__pct--right vz-num">
              {pct(game.awayWinProba)}
              {settings.probFormat === 'pct' && <small>%</small>}
            </div>
          </>
        )}

        {started && <span className="vz-arena__started">● Commencé</span>}
      </div>

      <div className="vz-match__row">
        <span className="vz-row vz-f1">
          <LeagueTag sport={game.sport} />
          <strong className="vz-num vz-match__time">{formatTime(game.commenceTime)}</strong>
          <span className="vz-match__when">{dayPhrase(game.commenceTime)}</span>
        </span>

        {showVb && (
          <span className="vz-match__vb">
            <span className="vz-num vz-match__vbOdds">@ {formatOdds(topVb.bookmakerOdds)}</span>
            <span className="vz-match__vbEdge">+{(topVb.edge * 100).toFixed(1)}%</span>
          </span>
        )}
        {!game.hasOdds && !showVb && <span className="vz-match__noOdds">cotes indispo.</span>}
      </div>

      {game.chips.length > 0 && (
        <div className="vz-match__chips">
          {game.chips.map((c) => (
            <span key={c}>{c}</span>
          ))}
        </div>
      )}
    </Link>
  );
}

/** Courbe de gradin qui traverse l'arène. */
export function ArenaCurve({ height }: { height: number }) {
  const d =
    height > 150
      ? 'M0 96 Q150 150 220 100 T372 140'
      : 'M0 40 Q150 84 220 44 T372 90';
  return (
    <svg
      viewBox={`0 0 372 ${height}`}
      preserveAspectRatio="none"
      className="vz-arena__curve"
      aria-hidden="true"
    >
      <path d={`${d} L372 ${height} L0 ${height} Z`} className="vz-arena__curveFill" />
      <path d={d} className="vz-arena__curveLine" />
    </svg>
  );
}
