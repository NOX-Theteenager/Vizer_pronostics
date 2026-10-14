import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { CURRENCIES } from '../lib/currency';
import { resultIndex, settleBet } from '../lib/settle';
import { downloadText, KEYS, readJson, writeJson } from '../lib/storage';
import { markChanged } from '../lib/sync';
import type { GameResult } from '../types/results';
import type {
  BankrollState,
  BetStatus,
  ComboLeg,
  FollowedBet,
  Transaction,
} from '../types/bankroll';
import { useSettings } from './SettingsContext';
import { useToast } from './ToastContext';

/**
 * Bankroll, mouvements et paris suivis (écrans Historique et Bankroll).
 *
 * Règles du domaine, alignées sur la maquette :
 *   - suivre un pari ne débite rien ; seule la clôture bouge la bankroll ;
 *   - un pari gagné crédite `mise × (cote − 1)`, un perdu débite `mise` ;
 *   - chaque clôture crée un mouvement lié (`betId`), si bien que la somme des
 *     mouvements explique toujours exactement l'écart avec la bankroll de
 *     départ — c'est ce qui rend la courbe honnête.
 */
interface BankrollCtx extends BankrollState {
  /** Bankroll avant tout mouvement enregistré. */
  startBankroll: number;
  deposit: (amount: number) => void;
  withdraw: (amount: number) => void;
  editTransaction: (id: string, newAbsAmount: number) => void;
  deleteTransaction: (id: string) => void;
  setGoal: (v: number) => void;
  setStopLoss: (v: number) => void;
  setBankroll: (v: number) => void;
  follow: (bet: Omit<FollowedBet, 'id' | 'ts' | 'status' | 'pnl'>) => void;
  settle: (id: string, win: boolean) => void;
  /** Clôture tous les paris tranchables d'après les scores publiés. */
  settleFromResults: (results: GameResult[]) => number;
  unsettle: (id: string) => void;
  removeFollowed: (id: string) => void;
  addToSlip: (leg: ComboLeg) => void;
  removeSlipLeg: (key: string) => void;
  clearSlip: () => void;
  confirmSlip: (stake: number) => FollowedBet | null;
  slipOdds: number;
  exportTransactionsCsv: () => void;
  exportBetsCsv: () => void;
}

const Ctx = createContext<BankrollCtx | null>(null);

const INITIAL: BankrollState = {
  bankroll: 0,
  goal: 0,
  stopLoss: 0,
  transactions: [],
  followed: [],
  slip: [],
};

const newId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

function csvEscape(v: unknown): string {
  return `"${String(v).replace(/"/g, '""')}"`;
}

export function BankrollProvider({ children }: { children: ReactNode }) {
  const { settings } = useSettings();
  const { showToast } = useToast();
  const [state, setState] = useState<BankrollState>(() => ({
    ...INITIAL,
    ...readJson<Partial<BankrollState>>(KEYS.bankroll, {}),
  }));

  useEffect(() => {
    // Le ticket en cours n'a pas à survivre à un rechargement : il contient
    // des cotes du jour qui peuvent déjà être périmées.
    const { slip: _slip, ...persisted } = state;
    writeJson(KEYS.bankroll, persisted);
    // Horodate pour la synchronisation : c'est ce qui permet d'arbitrer entre
    // deux appareils sans écraser le plus récent.
    markChanged();
  }, [state]);

  const snapshot = useCallback(() => state, [state]);

  const restore = useCallback((prev: BankrollState) => {
    setState((cur) => ({ ...prev, slip: cur.slip }));
  }, []);

  /* ── Mouvements ──────────────────────────────────────────────────────── */

  const addMoney = useCallback(
    (kind: 'deposit' | 'withdraw', amount: number) => {
      if (!(amount > 0)) return;
      const before = snapshot();
      if (kind === 'withdraw' && amount > before.bankroll) return;
      const signed = kind === 'deposit' ? amount : -amount;
      const tx: Transaction = {
        id: newId(),
        kind,
        amount: signed,
        label: kind === 'deposit' ? 'Dépôt' : 'Retrait',
        ts: Date.now(),
      };
      setState((s) => ({
        ...s,
        bankroll: s.bankroll + signed,
        transactions: [tx, ...s.transactions],
      }));
      showToast(kind === 'deposit' ? 'Dépôt enregistré' : 'Retrait enregistré', () =>
        restore(before),
      );
    },
    [snapshot, restore, showToast],
  );

  const deposit = useCallback((a: number) => addMoney('deposit', a), [addMoney]);
  const withdraw = useCallback((a: number) => addMoney('withdraw', a), [addMoney]);

  const editTransaction = useCallback(
    (id: string, newAbsAmount: number) => {
      const before = snapshot();
      setState((s) => {
        const tx = s.transactions.find((t) => t.id === id);
        if (!tx) return s;
        const sign = tx.amount < 0 ? -1 : 1;
        const next = sign * Math.abs(newAbsAmount);
        return {
          ...s,
          bankroll: s.bankroll + (next - tx.amount),
          transactions: s.transactions.map((t) => (t.id === id ? { ...t, amount: next } : t)),
        };
      });
      showToast('Mouvement modifié', () => restore(before));
    },
    [snapshot, restore, showToast],
  );

  const deleteTransaction = useCallback(
    (id: string) => {
      const before = snapshot();
      setState((s) => {
        const tx = s.transactions.find((t) => t.id === id);
        if (!tx) return s;
        return {
          ...s,
          bankroll: s.bankroll - tx.amount,
          transactions: s.transactions.filter((t) => t.id !== id),
          // Un mouvement issu d'un pari : le pari repasse en attente.
          followed: tx.betId
            ? s.followed.map((b) =>
                b.id === tx.betId ? { ...b, status: 'pending' as BetStatus, pnl: null } : b,
              )
            : s.followed,
        };
      });
      showToast('Mouvement supprimé', () => restore(before));
    },
    [snapshot, restore, showToast],
  );

  const setGoal = useCallback((v: number) => setState((s) => ({ ...s, goal: Math.max(0, v) })), []);
  const setStopLoss = useCallback(
    (v: number) => setState((s) => ({ ...s, stopLoss: Math.max(0, v) })),
    [],
  );
  const setBankroll = useCallback(
    (v: number) => setState((s) => ({ ...s, bankroll: Math.max(0, v) })),
    [],
  );

  /* ── Paris suivis ────────────────────────────────────────────────────── */

  const follow = useCallback(
    (bet: Omit<FollowedBet, 'id' | 'ts' | 'status' | 'pnl'>) => {
      const entry: FollowedBet = { ...bet, id: newId(), ts: Date.now(), status: 'pending', pnl: null };
      setState((s) => ({ ...s, followed: [entry, ...s.followed] }));
      showToast(`${bet.selection} suivi`);
    },
    [showToast],
  );

  const settle = useCallback(
    (id: string, win: boolean) => {
      const before = snapshot();
      setState((s) => {
        const bet = s.followed.find((b) => b.id === id);
        if (!bet || bet.status !== 'pending') return s;
        const pnl = win ? Math.round(bet.stake * (bet.odds - 1)) : -bet.stake;
        const tx: Transaction = {
          id: newId(),
          kind: win ? 'win' : 'loss',
          amount: pnl,
          label: `${win ? 'Gain' : 'Perte'} · ${bet.selection}`,
          ts: Date.now(),
          betId: bet.id,
        };
        return {
          ...s,
          bankroll: Math.max(0, s.bankroll + pnl),
          transactions: [tx, ...s.transactions],
          followed: s.followed.map((b) =>
            b.id === id ? { ...b, status: win ? 'won' : 'lost', pnl } : b,
          ),
        };
      });
      showToast(win ? 'Pari gagné' : 'Pari perdu', () => restore(before));
    },
    [snapshot, restore, showToast],
  );

  /**
   * Clôture en lot d'après les scores finaux publiés.
   *
   * Un seul `setState` pour tout le lot : clôturer dix paris un par un ferait
   * dix rendus et dix toasts. Les paris indécidables sont ignorés en silence —
   * c'est le cas normal, pas une anomalie (cf. `settle.ts`).
   *
   * Retourne le nombre de paris réglés, pour que l'appelant décide s'il y a
   * quelque chose à annoncer.
   */
  const settleFromResults = useCallback(
    (results: GameResult[]): number => {
      if (!results.length) return 0;
      const index = resultIndex(results);
      const before = snapshot();

      const verdicts = before.followed
        .map((bet) => ({ bet, verdict: settleBet(bet, index) }))
        .filter((v): v is { bet: FollowedBet; verdict: 'won' | 'lost' } =>
          v.verdict !== null,
        );
      if (!verdicts.length) return 0;

      setState((s) => {
        const txs: Transaction[] = [];
        let bankroll = s.bankroll;
        const closed = new Map<string, { status: BetStatus; pnl: number }>();

        for (const { bet, verdict } of verdicts) {
          // L'état a pu bouger entre l'évaluation et l'application (clôture
          // manuelle concurrente) : on revérifie sur l'état courant.
          const live = s.followed.find((b) => b.id === bet.id);
          if (!live || live.status !== 'pending') continue;
          const won = verdict === 'won';
          const pnl = won ? Math.round(live.stake * (live.odds - 1)) : -live.stake;
          closed.set(live.id, { status: won ? 'won' : 'lost', pnl });
          bankroll += pnl;
          txs.push({
            id: newId(),
            kind: won ? 'win' : 'loss',
            amount: pnl,
            label: `${won ? 'Gain' : 'Perte'} · ${live.selection}`,
            ts: Date.now(),
            betId: live.id,
          });
        }
        if (!txs.length) return s;

        return {
          ...s,
          bankroll: Math.max(0, bankroll),
          transactions: [...txs, ...s.transactions],
          followed: s.followed.map((b) => {
            const done = closed.get(b.id);
            return done ? { ...b, status: done.status, pnl: done.pnl } : b;
          }),
        };
      });

      showToast(
        verdicts.length === 1
          ? '1 pari clôturé automatiquement'
          : `${verdicts.length} paris clôturés automatiquement`,
        () => restore(before),
      );
      return verdicts.length;
    },
    [snapshot, restore, showToast],
  );

  /** Rouvre un pari : le mouvement lié disparaît avec son effet. */
  const unsettle = useCallback((id: string) => {
    setState((s) => {
      const bet = s.followed.find((b) => b.id === id);
      if (!bet || bet.status === 'pending') return s;
      const pnl = bet.pnl ?? 0;
      return {
        ...s,
        bankroll: Math.max(0, s.bankroll - pnl),
        transactions: s.transactions.filter((t) => t.betId !== id),
        followed: s.followed.map((b) => (b.id === id ? { ...b, status: 'pending', pnl: null } : b)),
      };
    });
  }, []);

  const removeFollowed = useCallback(
    (id: string) => {
      const before = snapshot();
      setState((s) => {
        const bet = s.followed.find((b) => b.id === id);
        if (!bet) return s;
        const pnl = bet.status === 'pending' ? 0 : (bet.pnl ?? 0);
        return {
          ...s,
          bankroll: Math.max(0, s.bankroll - pnl),
          transactions: s.transactions.filter((t) => t.betId !== id),
          followed: s.followed.filter((b) => b.id !== id),
        };
      });
      showToast('Pari retiré', () => restore(before));
    },
    [snapshot, restore, showToast],
  );

  /* ── Ticket combiné ──────────────────────────────────────────────────── */

  const addToSlip = useCallback(
    (leg: ComboLeg) => {
      let added = false;
      setState((s) => {
        if (s.slip.some((l) => l.key === leg.key)) return s;
        added = true;
        return { ...s, slip: [...s.slip, leg] };
      });
      showToast(added ? `${leg.selection} ajouté au ticket` : 'Déjà dans le ticket');
    },
    [showToast],
  );

  const removeSlipLeg = useCallback(
    (key: string) => setState((s) => ({ ...s, slip: s.slip.filter((l) => l.key !== key) })),
    [],
  );

  const clearSlip = useCallback(() => setState((s) => ({ ...s, slip: [] })), []);

  const slipOdds = useMemo(
    () => state.slip.reduce((p, l) => p * l.odds, 1),
    [state.slip],
  );

  const confirmSlip = useCallback(
    (stake: number): FollowedBet | null => {
      if (state.slip.length < 2) return null;
      const odds = Number(slipOdds.toFixed(2));
      const entry: FollowedBet = {
        id: newId(),
        ts: Date.now(),
        matchId: state.slip[0].matchId,
        matchLabel: `${state.slip.length} sélections`,
        // Le combiné se règle quand sa dernière rencontre a commencé.
        commenceTime: state.slip
          .map((l) => l.commenceTime)
          .sort()
          .at(-1) ?? '',
        league: state.slip[0].league,
        sport: state.slip[0].sport,
        market: 'combo',
        marketLabel: 'COMBINÉ',
        selection: state.slip.map((l) => l.selection).join(' + '),
        odds,
        stake,
        status: 'pending',
        pnl: null,
        combo: true,
        legs: state.slip,
      };
      setState((s) => ({ ...s, followed: [entry, ...s.followed], slip: [] }));
      showToast(`Combiné suivi · cote ${odds.toFixed(2)}`);
      return entry;
    },
    [state.slip, slipOdds, showToast],
  );

  /* ── Exports ─────────────────────────────────────────────────────────── */

  const exportTransactionsCsv = useCallback(() => {
    const c = CURRENCIES[settings.currency];
    const conv = (n: number) => (n / c.rate).toFixed(c.decimals);
    const rows: unknown[][] = [['Date', 'Type', 'Libellé', 'Montant', 'Devise']];
    state.transactions.forEach((t) =>
      rows.push([new Date(t.ts).toISOString().slice(0, 10), t.kind, t.label, conv(t.amount), c.code]),
    );
    const csv = rows.map((r) => r.map(csvEscape).join(',')).join('\n');
    showToast(
      downloadText('vizer-bankroll.csv', csv) ? 'Export CSV téléchargé' : 'Export indisponible',
    );
  }, [state.transactions, settings.currency, showToast]);

  const exportBetsCsv = useCallback(() => {
    if (!state.followed.length) {
      showToast('Aucun pari à exporter');
      return;
    }
    const c = CURRENCIES[settings.currency];
    const conv = (n: number) => (n / c.rate).toFixed(c.decimals);
    const label: Record<BetStatus, string> = {
      won: 'Gagné',
      lost: 'Perdu',
      pending: 'En cours',
    };
    const rows: unknown[][] = [
      ['Date', 'Ligue', 'Match', 'Marché', 'Sélection', 'Cote', 'Mise', 'P&L', 'Statut', 'Devise'],
    ];
    state.followed.forEach((f) =>
      rows.push([
        new Date(f.ts).toISOString().slice(0, 10),
        f.league,
        f.matchLabel,
        f.marketLabel,
        f.selection,
        f.odds.toFixed(2),
        conv(f.stake),
        conv(f.pnl ?? 0),
        label[f.status],
        c.code,
      ]),
    );
    const csv = rows.map((r) => r.map(csvEscape).join(',')).join('\n');
    showToast(
      downloadText('vizer-paris.csv', csv) ? 'Historique des paris exporté' : 'Export indisponible',
    );
  }, [state.followed, settings.currency, showToast]);

  const startBankroll = useMemo(
    () => state.bankroll - state.transactions.reduce((s, t) => s + t.amount, 0),
    [state.bankroll, state.transactions],
  );

  const value = useMemo<BankrollCtx>(
    () => ({
      ...state,
      startBankroll,
      deposit,
      withdraw,
      editTransaction,
      deleteTransaction,
      setGoal,
      setStopLoss,
      setBankroll,
      follow,
      settle,
      settleFromResults,
      unsettle,
      removeFollowed,
      addToSlip,
      removeSlipLeg,
      clearSlip,
      confirmSlip,
      slipOdds,
      exportTransactionsCsv,
      exportBetsCsv,
    }),
    [
      state,
      startBankroll,
      deposit,
      withdraw,
      editTransaction,
      deleteTransaction,
      setGoal,
      setStopLoss,
      setBankroll,
      follow,
      settle,
      settleFromResults,
      unsettle,
      removeFollowed,
      addToSlip,
      removeSlipLeg,
      clearSlip,
      confirmSlip,
      slipOdds,
      exportTransactionsCsv,
      exportBetsCsv,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useBankroll(): BankrollCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useBankroll doit être utilisé dans <BankrollProvider>');
  return ctx;
}
