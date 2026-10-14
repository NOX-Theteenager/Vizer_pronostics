import { useMemo, useState } from 'react';
import { EmptyState } from '../components/States';
import { RailSkeletons } from '../components/States';
import { Chip } from '../components/Primitives';
import { ValueBetCard } from '../components/ValueBetCard';
import { useBankroll } from '../context/BankrollContext';
import { useData } from '../context/DataContext';
import { MARKET_FAMILIES, marketShortLabel } from '../data/markets';
import { isPast } from '../lib/format';
import {
  SPORTS,
  SPORT_KEYS,
  type Confidence,
  type Sport,
  type ValueBet,
} from '../types/model';
import { CONFIDENCE_LABEL } from '../lib/format';

type SportFilter = 'all' | Sport;
type ConfFilter = 'all' | Confidence;
type SortMode = 'edge' | 'time';

/** Liste transversale NHL + NBA, avec filtres en puces et slider d'edge. */
export function ValueBets({
  onFollow,
  onAddSlip,
}: {
  onFollow: (vb: ValueBet) => void;
  onAddSlip: (vb: ValueBet) => void;
}) {
  const { valueBets, feeds, loading } = useData();
  const { bankroll, slip } = useBankroll();

  const [sportF, setSportF] = useState<SportFilter>('all');
  const [familyF, setFamilyF] = useState('all');
  const [confF, setConfF] = useState<ConfFilter>('all');
  const [sort, setSort] = useState<SortMode>('edge');
  const [edgeMin, setEdgeMin] = useState(4);
  const [showStarted, setShowStarted] = useState(false);

  /**
   * Marchés dont les paris ont été retenus à la publication.
   *
   * Affiché parce qu'un marché qui se tait sans rien dire est le défaut qu'on
   * cherche à éviter : sans cette ligne, le `total` disparaîtrait de l'écran
   * et rien n'indiquerait que c'est une décision plutôt qu'une absence
   * d'occasion.
   */
  const withheld = useMemo(
    () =>
      SPORT_KEYS.flatMap((s) =>
        (feeds[s]?.withheldMarkets ?? []).map((w) => ({ ...w, sport: s })),
      ),
    [feeds],
  );

  const startedCount = useMemo(
    () => valueBets.filter((vb) => isPast(vb.commenceTime)).length,
    [valueBets],
  );

  const list = useMemo(() => {
    const family = MARKET_FAMILIES.find((f) => f.key === familyF);
    const out = valueBets.filter((vb) => {
      if (sportF !== 'all' && vb.sport !== sportF) return false;
      if (family && familyF !== 'all' && !family.match(vb.market)) return false;
      if (confF !== 'all' && vb.confidence !== confF) return false;
      if (vb.edge * 100 < edgeMin) return false;
      if (!showStarted && isPast(vb.commenceTime)) return false;
      return true;
    });
    return out.sort((a, b) =>
      sort === 'edge'
        ? b.edge - a.edge
        : new Date(a.commenceTime).getTime() - new Date(b.commenceTime).getTime(),
    );
  }, [valueBets, sportF, familyF, confF, edgeMin, showStarted, sort]);

  return (
    <div className="vz-screen vz-up">
      <div className="vz-screen__head">
        <h1>Value bets</h1>
        <span>
          {list.length} · {SPORTS.nhl.label} + {SPORTS.nba.label}
        </span>
      </div>

      <div className="vz-chiprow vz-sc">
        <Chip active={sportF === 'all'} onClick={() => setSportF('all')}>
          Tous
        </Chip>
        {(['nhl', 'nba'] as Sport[]).map((s) => (
          <Chip key={s} active={sportF === s} onClick={() => setSportF(s)}>
            {SPORTS[s].label}
          </Chip>
        ))}
      </div>

      <div className="vz-chiprow vz-sc">
        {MARKET_FAMILIES.map((f) => (
          <Chip key={f.key} active={familyF === f.key} onClick={() => setFamilyF(f.key)}>
            {f.label}
          </Chip>
        ))}
      </div>

      <div className="vz-chiprow vz-sc">
        <Chip active={confF === 'all'} onClick={() => setConfF('all')}>
          Confiance : toutes
        </Chip>
        {(['high', 'medium', 'low'] as Confidence[]).map((c) => (
          <Chip key={c} active={confF === c} onClick={() => setConfF(c)}>
            {CONFIDENCE_LABEL[c]}
          </Chip>
        ))}
        <Chip active={sort === 'edge'} onClick={() => setSort('edge')}>
          Trier par edge
        </Chip>
        <Chip active={sort === 'time'} onClick={() => setSort('time')}>
          Par heure
        </Chip>
        {startedCount > 0 && (
          <Chip active={showStarted} onClick={() => setShowStarted((v) => !v)}>
            {showStarted ? 'Commencés affichés' : `Commencés masqués (${startedCount})`}
          </Chip>
        )}
      </div>

      <div className="vz-edgemin">
        <div className="vz-edgemin__head">
          <span>Edge minimum</span>
          <strong className="vz-num">{edgeMin} %</strong>
        </div>
        <input
          type="range"
          min={0}
          max={15}
          step={1}
          value={edgeMin}
          onChange={(e) => setEdgeMin(Number(e.target.value))}
          aria-label="Edge minimum"
        />
      </div>

      {withheld.length > 0 && (
        <div className="vz-card">
          <p className="vz-note">
            🛑{' '}
            <strong>
              {withheld
                .map((w) => `${marketShortLabel(w.market)} (${w.sport.toUpperCase()})`)
                .join(', ')}
            </strong>{' '}
            — paris non proposés aujourd’hui. Ce marché n’a jamais parié dans l’autre
            sens sur les dernières semaines : son rendement passé ne mesure donc pas sa
            sélection, mais un pari directionnel unique répété. Les prédictions restent
            visibles dans chaque match.
          </p>
        </div>
      )}

      {loading && valueBets.length === 0 ? (
        <RailSkeletons count={2} />
      ) : list.length === 0 ? (
        <EmptyState
          glyph="😌"
          title={
            valueBets.length === 0
              ? "Aucun value bet aujourd'hui"
              : 'Aucun value bet avec ces filtres'
          }
          text={
            valueBets.length === 0
              ? "Les cotes sont efficientes — rien à jouer, et c'est une information en soi."
              : `Baisse l'edge minimum (${edgeMin} %) ou élargis les filtres.`
          }
        />
      ) : (
        <div className="vz-stack">
          {list.map((vb, i) => (
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
      )}
    </div>
  );
}
