import { useMemo, useState } from 'react';
import { BankrollCurve } from '../components/BankrollCurve';
import {
  IconCheck,
  IconChartAxis,
  IconClock,
  IconDownload,
  IconTrendDown,
  IconShare,
  IconTrendUp,
  IconX,
} from '../components/Icons';
import { Chip, LeagueTag, MiniBar } from '../components/Primitives';
import { EmptyState } from '../components/States';
import { ShareSheet } from '../components/overlays/ShareSheet';
import { useBankroll } from '../context/BankrollContext';
import { useSettings } from '../context/SettingsContext';
import { marketFamily } from '../data/markets';
import { formatMoney, formatPnl } from '../lib/currency';
import { formatEdge, formatShortDate, isPast } from '../lib/format';
import { bankrollSeries, computeBreakdown, computeProfit } from '../lib/stats';
import { KEYS, readJson, writeJson } from '../lib/storage';
import type { BetStatus, FollowedBet } from '../types/bankroll';

type ResultFilter = 'all' | BetStatus;
type PeriodFilter = 'all' | '7' | '30';
type SortMode = 'recent' | 'pnl';

/** Historique : rentabilité, courbe de bankroll, paris suivis et statistiques. */
export function History() {
  const { settings } = useSettings();
  const {
    followed,
    transactions,
    startBankroll,
    settle,
    unsettle,
    removeFollowed,
    exportBetsCsv,
  } = useBankroll();

  const [league, setLeague] = useState('all');
  const [result, setResult] = useState<ResultFilter>('all');
  const [family, setFamily] = useState('all');
  const [period, setPeriod] = useState<PeriodFilter>('all');
  const [sort, setSort] = useState<SortMode>('recent');
  const [dismissed, setDismissed] = useState<string[]>(() =>
    readJson<string[]>(KEYS.dismissedReminders, []),
  );
  const [shareBet, setShareBet] = useState<FollowedBet | null>(null);

  const profit = useMemo(() => computeProfit(followed), [followed]);
  const breakdown = useMemo(() => computeBreakdown(followed), [followed]);
  const series = useMemo(
    () => bankrollSeries(startBankroll, transactions),
    [startBankroll, transactions],
  );

  /** Paris en attente dont la rencontre a déjà commencé. */
  const reminders = useMemo(
    () =>
      followed.filter(
        (f) =>
          f.status === 'pending' &&
          !dismissed.includes(f.id) &&
          f.commenceTime &&
          isPast(f.commenceTime),
      ),
    [followed, dismissed],
  );

  const dismiss = (id: string) =>
    setDismissed((prev) => {
      const next = [...prev, id];
      writeJson(KEYS.dismissedReminders, next);
      return next;
    });

  const leagues = useMemo(
    () => [...new Set(followed.map((f) => f.league))].filter(Boolean),
    [followed],
  );
  const families = useMemo(
    () => [...new Set(followed.map((f) => (f.combo ? 'Combiné' : marketFamily(f.market))))],
    [followed],
  );

  const list = useMemo(() => {
    const cutoff =
      period === 'all' ? 0 : Date.now() - (period === '7' ? 7 : 30) * 86_400_000;
    const out = followed.filter((f) => {
      if (f.ts < cutoff) return false;
      if (league !== 'all' && f.league !== league) return false;
      if (result !== 'all' && f.status !== result) return false;
      if (family !== 'all' && (f.combo ? 'Combiné' : marketFamily(f.market)) !== family)
        return false;
      return true;
    });
    return out.sort((a, b) =>
      sort === 'pnl' ? (b.pnl ?? 0) - (a.pnl ?? 0) : b.ts - a.ts,
    );
  }, [followed, period, league, result, family, sort]);

  if (followed.length === 0) {
    return (
      <div className="vz-screen vz-up">
        <h1 className="vz-screen__title">Historique</h1>
        <EmptyState
          glyph={<IconChartAxis size={34} />}
          title="Aucun pari suivi pour l'instant"
          text="Suis ta première prédiction depuis un match : tes stats, ta rentabilité et ta courbe s'afficheront ici."
        />
      </div>
    );
  }

  return (
    <div className="vz-screen vz-up">
      <div className="vz-screen__head">
        <h1>Historique</h1>
        <button type="button" className="vz-btn vz-btn--sm" onClick={exportBetsCsv}>
          <IconDownload size={15} /> Exporter
        </button>
      </div>

      {profit.settledCount > 0 && (
        <div
          className={`vz-profit ${profit.up ? 'is-up' : profit.down ? 'is-down' : 'is-flat'}`}
        >
          <div className="vz-profit__top">
            <span className="vz-profit__ic">
              {profit.down ? <IconTrendDown size={22} /> : <IconTrendUp size={22} />}
            </span>
            <div className="vz-f1">
              <strong>{profit.verdict}</strong>
              <small>
                {profit.settledCount} pari{profit.settledCount > 1 ? 's' : ''} réglé
                {profit.settledCount > 1 ? 's' : ''} ·{' '}
                {formatMoney(profit.staked, settings.currency)} misés
              </small>
            </div>
          </div>
          <div className="vz-profit__tiles">
            <Tile label="Résultat net" value={formatPnl(profit.net, settings.currency)} accent />
            <Tile
              label="ROI paris"
              value={profit.roi === null ? '—' : formatEdge(profit.roi)}
              accent
            />
            <Tile
              label="Réussite"
              value={profit.winRate === null ? '—' : `${Math.round(profit.winRate * 100)} %`}
            />
          </div>
        </div>
      )}

      {reminders.length > 0 && (
        <div className="vz-stack vz-reminders">
          {reminders.map((f) => (
            <div className="vz-reminder" key={f.id}>
              <div className="vz-reminder__top">
                <IconClock size={17} />
                <div className="vz-f1">
                  <strong>Match terminé — règle ton pari</strong>
                  <small>
                    <LeagueTag sport={f.sport} /> {f.matchLabel} · {f.selection}
                  </small>
                </div>
                <button type="button" className="vz-link" onClick={() => dismiss(f.id)}>
                  Plus tard
                </button>
              </div>
              <div className="vz-row">
                <button
                  type="button"
                  className="vz-btn vz-btn--won vz-f1"
                  onClick={() => settle(f.id, true)}
                >
                  Gagné
                </button>
                <button
                  type="button"
                  className="vz-btn vz-btn--lost vz-f1"
                  onClick={() => settle(f.id, false)}
                >
                  Perdu
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {series.length >= 2 && <BankrollCurve series={series} />}

      <div className="vz-chiprow vz-sc">
        {(['all', 'pending', 'won', 'lost'] as ResultFilter[]).map((r) => (
          <Chip key={r} small active={result === r} onClick={() => setResult(r)}>
            {r === 'all' ? 'Tous' : r === 'pending' ? 'En cours' : r === 'won' ? 'Gagnés' : 'Perdus'}
          </Chip>
        ))}
        {leagues.length > 1 && (
          <>
            <span className="vz-chiprow__sep" />
            <Chip small active={league === 'all'} onClick={() => setLeague('all')}>
              Toutes
            </Chip>
            {leagues.map((l) => (
              <Chip key={l} small active={league === l} onClick={() => setLeague(l)}>
                {l}
              </Chip>
            ))}
          </>
        )}
      </div>

      <div className="vz-chiprow vz-sc">
        {families.length > 1 && (
          <>
            <Chip small active={family === 'all'} onClick={() => setFamily('all')}>
              Tous marchés
            </Chip>
            {families.map((f) => (
              <Chip key={f} small active={family === f} onClick={() => setFamily(f)}>
                {f}
              </Chip>
            ))}
            <span className="vz-chiprow__sep" />
          </>
        )}
        {(['all', '7', '30'] as PeriodFilter[]).map((p) => (
          <Chip key={p} small active={period === p} onClick={() => setPeriod(p)}>
            {p === 'all' ? 'Toute période' : `${p} j`}
          </Chip>
        ))}
        <span className="vz-chiprow__sep" />
        <Chip small active={sort === 'recent'} onClick={() => setSort('recent')}>
          Récent
        </Chip>
        <Chip small active={sort === 'pnl'} onClick={() => setSort('pnl')}>
          P&amp;L
        </Chip>
      </div>

      <div className="vz-sechead vz-sechead--tight">
        <span>
          Mes paris{' '}
          {profit.pendingCount > 0 && <small className="vz-badge">{profit.pendingCount} en cours</small>}
        </span>
      </div>

      {list.length === 0 ? (
        <p className="vz-note vz-note--center">Aucun pari pour ces filtres.</p>
      ) : (
        <div className="vz-stack">
          {list.map((f) => (
            <BetRow
              key={f.id}
              bet={f}
              currency={settings.currency}
              onWin={() => settle(f.id, true)}
              onLose={() => settle(f.id, false)}
              onReopen={() => unsettle(f.id)}
              onRemove={() => removeFollowed(f.id)}
              onShare={() => setShareBet(f)}
            />
          ))}
        </div>
      )}

      {breakdown.hasStats && (
        <>
          <h4 className="vz-seclabel">Performance par marché</h4>
          <div className="vz-stack">
            {breakdown.byMarket.map((s) => (
              <div className="vz-stat" key={s.key}>
                <div className="vz-stat__head">
                  <strong>{s.key}</strong>
                  <span>
                    {s.count} pari{s.count > 1 ? 's' : ''}
                  </span>
                </div>
                <div className="vz-row">
                  <span className="vz-f1">
                    <MiniBar ratio={s.winRate} />
                  </span>
                  <span className="vz-num">{Math.round(s.winRate * 100)} %</span>
                  <strong
                    className={`vz-num vz-stat__roi ${s.roi >= 0 ? 'is-up' : 'is-down'}`}
                  >
                    ROI {formatEdge(s.roi)}
                  </strong>
                </div>
              </div>
            ))}
          </div>

          <h4 className="vz-seclabel">Par ligue</h4>
          <div className="vz-row vz-stats__league">
            {breakdown.byLeague.map((s) => (
              <div className="vz-stat vz-f1" key={s.key}>
                <strong>{s.key}</strong>
                <small>
                  {s.count} · {Math.round(s.winRate * 100)} %
                </small>
                <strong className={`vz-num vz-stat__roi ${s.roi >= 0 ? 'is-up' : 'is-down'}`}>
                  ROI {formatEdge(s.roi)}
                </strong>
              </div>
            ))}
          </div>
        </>
      )}

      <ShareSheet bet={shareBet} onClose={() => setShareBet(null)} />
    </div>
  );
}

function Tile({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="vz-profit__tile">
      <strong className={`vz-num${accent ? ' is-accent' : ''}`}>{value}</strong>
      <small>{label}</small>
    </div>
  );
}

function BetRow({
  bet,
  currency,
  onWin,
  onLose,
  onReopen,
  onRemove,
  onShare,
}: {
  bet: FollowedBet;
  currency: Parameters<typeof formatMoney>[1];
  onWin: () => void;
  onLose: () => void;
  onReopen: () => void;
  onRemove: () => void;
  onShare: () => void;
}) {
  const pending = bet.status === 'pending';
  return (
    <article className={`vz-bet vz-bet--${bet.status}`}>
      <div className="vz-bet__top">
        <span className="vz-row vz-f1">
          <LeagueTag sport={bet.sport} />
          <span className="vz-ellipsis">{bet.matchLabel}</span>
        </span>
        {pending ? (
          <span className="vz-bet__pending">
            <i /> En cours
          </span>
        ) : (
          <strong className={`vz-num vz-bet__pnl ${bet.status === 'won' ? 'is-up' : 'is-down'}`}>
            {formatPnl(bet.pnl ?? 0, currency)}
          </strong>
        )}
      </div>

      <strong className="vz-bet__sel">
        {bet.marketLabel} · {bet.selection}
      </strong>
      <small className="vz-bet__meta">
        Cote {bet.odds.toFixed(2)} · Mise {formatMoney(bet.stake, currency)} · Gain potentiel{' '}
        {formatMoney(Math.round(bet.stake * bet.odds), currency)}
        {bet.ts ? ` · ${formatShortDate(bet.ts)}` : ''}
      </small>

      <div className="vz-row vz-bet__actions">
        {pending ? (
          <>
            <button type="button" className="vz-btn vz-btn--won vz-f1" onClick={onWin}>
              <IconCheck size={13} /> Gagné
            </button>
            <button type="button" className="vz-btn vz-btn--lost vz-f1" onClick={onLose}>
              <IconX size={12} /> Perdu
            </button>
          </>
        ) : (
          <button type="button" className="vz-btn vz-btn--ghost vz-f1" onClick={onReopen}>
            ↩ Annuler le résultat
          </button>
        )}
        <button
          type="button"
          className="vz-btn vz-btn--icon"
          onClick={onShare}
          aria-label="Partager ce pari"
        >
          <IconShare size={13} />
        </button>
        <button
          type="button"
          className="vz-btn vz-btn--icon"
          onClick={onRemove}
          aria-label="Retirer ce pari"
        >
          <IconX size={12} />
        </button>
      </div>
    </article>
  );
}
