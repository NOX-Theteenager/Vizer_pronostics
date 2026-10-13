import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArenaCurve } from '../components/MatchCard';
import { FactorsCard, HeadToHeadCard, RecentForm } from '../components/MatchContext';
import { MarketCard } from '../components/MarketCard';
import { IconBolt, IconPlus } from '../components/Icons';
import { EmptyState } from '../components/States';
import { ValueBetCard } from '../components/ValueBetCard';
import { useBankroll } from '../context/BankrollContext';
import { useData } from '../context/DataContext';
import { useSettings } from '../context/SettingsContext';
import { CONFIDENCE_LABEL, dayPhrase, formatEdge, formatOdds, formatProbaBare, formatTime, isPast, probaToOdds } from '../lib/format';
import { SPORTS, type Game, type ValueBet } from '../types/model';

/** Détail d'un match : arène, value bets, puis tous les marchés du sport. */
export function MatchDetail({
  onFollow,
  onFollowMatch,
  onAddSlip,
}: {
  onFollow: (vb: ValueBet) => void;
  onFollowMatch: (game: Game) => void;
  onAddSlip: (vb: ValueBet) => void;
}) {
  const { gameId = '' } = useParams();
  const navigate = useNavigate();
  const { findGame, loading } = useData();
  const { settings } = useSettings();
  const { bankroll, slip } = useBankroll();

  const game = findGame(gameId);

  if (!game) {
    return (
      <div className="vz-screen">
        <EmptyState
          glyph={loading ? '⏳' : '🔍'}
          title={loading ? 'Chargement…' : 'Match introuvable'}
          text={
            loading
              ? undefined
              : "Ce match n'est pas dans les prédictions du jour — il a peut-être été archivé."
          }
          action={
            <Link to="/" className="vz-btn vz-btn--primary">
              Retour aux matchs
            </Link>
          }
        />
      </div>
    );
  }

  const started = isPast(game.commenceTime);
  const hasDuel = game.homeWinProba !== undefined && game.awayWinProba !== undefined;
  const homeFav = (game.homeWinProba ?? 0) >= (game.awayWinProba ?? 0);
  const topVb = game.valueBets[0];
  const showVbs = game.valueBets.length > 0 && game.hasOdds && !started;

  const pct = (p?: number) =>
    p === undefined ? '—' : settings.probFormat === 'cote' ? probaToOdds(p) : formatProbaBare(p);

  return (
    <div className="vz-up">
      <div
        className="vz-arena vz-arena--xl"
        style={{
          backgroundImage: `linear-gradient(105deg, ${game.homeColor} 0%, ${game.homeColor} 40%, transparent 60%), linear-gradient(285deg, ${game.awayColor} 0%, ${game.awayColor} 34%, transparent 56%)`,
        }}
      >
        <ArenaCurve height={186} />

        <button type="button" className="vz-arena__back" onClick={() => navigate(-1)}>
          ‹ Retour
        </button>
        <span className="vz-arena__badge">
          {SPORTS[game.sport].league} · {formatTime(game.commenceTime)}
        </span>

        <span className="vz-arena__vs vz-arena__vs--xl">VS</span>

        <div className="vz-arena__team vz-arena__team--left vz-arena__team--xl">
          <strong>{game.home}</strong>
          <span>{game.homeName}</span>
          <small>DOMICILE</small>
        </div>
        <div className="vz-arena__team vz-arena__team--right vz-arena__team--xl">
          <strong>{game.away}</strong>
          <span>{game.awayName}</span>
          <small>EXTÉRIEUR</small>
        </div>

        {hasDuel && (
          <>
            <div className="vz-arena__pct vz-arena__pct--left vz-arena__pct--xl vz-num">
              {pct(game.homeWinProba)}
              {settings.probFormat === 'pct' && <small>%</small>}
            </div>
            <div className="vz-arena__pct vz-arena__pct--right vz-arena__pct--xl vz-num">
              {pct(game.awayWinProba)}
              {settings.probFormat === 'pct' && <small>%</small>}
            </div>
          </>
        )}
      </div>

      <div className="vz-detail__fav">
        <span className="vz-f1">
          {hasDuel
            ? `${homeFav ? game.homeName : game.awayName} favori`
            : 'Probabilités indisponibles'}
          {game.markets[0]?.confidence &&
            ` · confiance ${CONFIDENCE_LABEL[game.markets[0].confidence]}`}
        </span>
        {topVb && !started && game.hasOdds && (
          <span className="vz-detail__topvb">
            <IconBolt size={11} /> {formatEdge(topVb.edge)} @ {formatOdds(topVb.bookmakerOdds)}
          </span>
        )}
      </div>

      <div className="vz-screen vz-detail__body">
        {started && (
          <div className="vz-detail__started">
            ● Match commencé — la prédiction pré-match est caduque.
          </div>
        )}

        {!started && (
          <button
            type="button"
            className="vz-btn vz-btn--primary vz-btn--block"
            onClick={() => onFollowMatch(game)}
          >
            <IconPlus size={13} /> Suivre un pari sur ce match
          </button>
        )}

        <RecentForm game={game} />
        <HeadToHeadCard game={game} />
        <FactorsCard game={game} />

        {showVbs && (
          <section>
            <div className="vz-sechead vz-sechead--tight">
              <span>
                <IconBolt size={14} /> Value bets de ce match
              </span>
            </div>
            <div className="vz-stack">
              {game.valueBets.map((vb, i) => (
                <ValueBetCard
                  key={vb.id}
                  bet={vb}
                  index={i}
                  variant="full"
                  bankroll={bankroll}
                  onFollow={onFollow}
                  onAddSlip={onAddSlip}
                  inSlip={slip.some((l) => l.key === vb.id)}
                />
              ))}
            </div>
          </section>
        )}

        {!game.hasOdds && (
          <div className="vz-detail__noodds">
            Cotes indisponibles pour ce match — prédictions à titre indicatif.
          </div>
        )}

        {game.markets.length === 0 ? (
          <EmptyState
            glyph="⚠️"
            tone="danger"
            title="Prédictions indisponibles"
            text={game.error ?? "Le backend n'a publié aucun marché pour ce match."}
          />
        ) : (
          <div className="vz-stack">
            {game.markets.map((m) => (
              <MarketCard key={m.key} market={m} sport={game.sport} />
            ))}
          </div>
        )}

        <p className="vz-footmeta">
          {game.away} chez {game.home} · {dayPhrase(game.commenceTime)}{' '}
          {formatTime(game.commenceTime)}
        </p>
      </div>
    </div>
  );
}
