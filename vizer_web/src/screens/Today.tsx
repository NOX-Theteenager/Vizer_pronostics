import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { MatchCard } from '../components/MatchCard';
import { IconBolt } from '../components/Icons';
import { LivePill, MatchSkeletons, NoValueBets, OffSeason, RailSkeletons } from '../components/States';
import { SportTabs } from '../components/Shell';
import { ValueBetCard } from '../components/ValueBetCard';
import { useBankroll } from '../context/BankrollContext';
import { useData } from '../context/DataContext';
import { isPast, timeAgo } from '../lib/format';
import { SPORTS, type Sport, type ValueBet } from '../types/model';

/** Écran principal : sélecteur de sport, rail de value bets, liste des matchs. */
export function Today({
  sport,
  onSportChange,
  onFollow,
  onAddSlip,
}: {
  sport: Sport;
  onSportChange: (s: Sport) => void;
  onFollow: (vb: ValueBet) => void;
  onAddSlip: (vb: ValueBet) => void;
}) {
  const { feeds, loading, refreshing, generatedAt, stale, refresh } = useData();
  const { bankroll, slip } = useBankroll();

  const feed = feeds[sport];
  const other: Sport = sport === 'nhl' ? 'nba' : 'nhl';

  const counts = useMemo<Record<Sport, number | null>>(
    () => ({
      nhl: feeds.nhl ? feeds.nhl.games.length : null,
      nba: feeds.nba ? feeds.nba.games.length : null,
    }),
    [feeds],
  );

  const rail = useMemo(
    () =>
      (feed?.games ?? [])
        .flatMap((g) => g.valueBets)
        .filter((vb) => !isPast(vb.commenceTime))
        .sort((a, b) => b.edge - a.edge),
    [feed],
  );

  const games = feed?.games ?? [];
  const inSlip = (vb: ValueBet) => slip.some((l) => l.key === vb.id);

  return (
    <div className="vz-screen vz-up">
      <SportTabs value={sport} counts={counts} onChange={onSportChange} />

      <div className="vz-leaguerow vz-sc">
        <span className="vz-leaguechip">
          <i />
          {SPORTS[sport].league}
        </span>
        <span className="vz-leaguechip vz-leaguechip--ghost">+ autres ligues bientôt</span>
      </div>

      {loading && !feed ? (
        <>
          <RailSkeletons />
          <MatchSkeletons count={3} />
        </>
      ) : games.length === 0 ? (
        <OffSeason
          sportLabel={SPORTS[sport].label}
          initial={SPORTS[sport].label[0]}
          otherLabel={SPORTS[other].label}
          otherCount={feeds[other]?.games.length ?? 0}
          onSwitch={() => onSportChange(other)}
        />
      ) : (
        <>
          <LivePill
            label={timeAgo(generatedAt)}
            stale={stale}
            busy={refreshing}
            onClick={() => void refresh()}
          />

          <div className="vz-sechead">
            <span>
              <IconBolt size={16} /> Value bets du jour
            </span>
            <Link to="/value-bets" className="vz-link">
              Tout voir →
            </Link>
          </div>

          {rail.length === 0 ? (
            <NoValueBets text="Aucun value bet aujourd'hui — les cotes sont efficientes. On reste patients." />
          ) : (
            <div className="vz-rail vz-sc">
              {rail.map((vb, i) => (
                <ValueBetCard
                  key={vb.id}
                  bet={vb}
                  index={i}
                  variant="rail"
                  bankroll={bankroll}
                  onFollow={onFollow}
                  onAddSlip={onAddSlip}
                  inSlip={inSlip(vb)}
                />
              ))}
            </div>
          )}

          <div className="vz-sechead vz-sechead--tight">
            <span>
              Tous les matchs <small>· {games.length}</small>
            </span>
          </div>

          <div className="vz-stack">
            {games.map((g, i) => (
              <MatchCard key={g.id} game={g} index={i} />
            ))}
          </div>

          {generatedAt && (
            <p className="vz-footmeta">
              Prédictions générées {timeAgo(generatedAt)}
              {feed?.detectionSource ? ` · source ${feed.detectionSource}` : ''}
            </p>
          )}
        </>
      )}
    </div>
  );
}
