/**
 * Domaine bankroll — paris suivis, mouvements d'argent, ticket combiné.
 *
 * Tout est local (aucun compte, aucun bookmaker connecté). Les montants sont
 * en **unité de base** (FCFA) ; la devise n'est qu'un format d'affichage.
 */
import type { Sport } from './model';

export type TxKind = 'deposit' | 'withdraw' | 'win' | 'loss';

export interface Transaction {
  id: string;
  kind: TxKind;
  /** Signé : positif crédite la bankroll, négatif la débite. */
  amount: number;
  label: string;
  ts: number;
  /** Pari à l'origine du mouvement (gains/pertes) — permet de le défaire. */
  betId?: string;
}

export type BetStatus = 'pending' | 'won' | 'lost';

export interface ComboLeg {
  key: string;
  matchId: string;
  matchLabel: string;
  commenceTime: string;
  league: string;
  sport: Sport;
  market: string;
  selection: string;
  odds: number;
}

export interface FollowedBet {
  id: string;
  ts: number;
  matchId: string;
  matchLabel: string;
  /** Coup d'envoi (ISO) — sert à rappeler de régler le pari une fois joué. */
  commenceTime: string;
  league: string;
  sport: Sport;
  /** Clé backend du marché ('moneyline', 'btts'…) — sert aux statistiques. */
  market: string;
  /** Libellé affiché (« MONEYLINE », « TOTAL BOS »). */
  marketLabel: string;
  selection: string;
  odds: number;
  stake: number;
  status: BetStatus;
  /** Renseigné à la clôture seulement. */
  pnl: number | null;
  combo?: boolean;
  legs?: ComboLeg[];
}

export interface BankrollState {
  bankroll: number;
  goal: number;
  stopLoss: number;
  transactions: Transaction[];
  followed: FollowedBet[];
  slip: ComboLeg[];
}

export interface Toast {
  id: number;
  msg: string;
  undo?: () => void;
}
