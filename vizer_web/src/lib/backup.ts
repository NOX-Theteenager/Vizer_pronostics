/**
 * Sauvegarde et restauration de l'état utilisateur.
 *
 * Tout ce que l'app sait de vous vit dans `localStorage` : bankroll, paris
 * suivis, mouvements, réglages. C'est délibéré — aucune donnée de pari ne
 * quitte l'appareil — mais ça rend la perte brutale : un « effacer les données
 * du site », une éviction du stockage par le système sous pression mémoire, et
 * la courbe de bankroll disparaît avec son historique.
 *
 * Ce module produit un fichier unique qui contient tout, et sait le relire.
 *
 * **Le jeton GitHub n'y figure jamais.** C'est une crédence, pas une donnée :
 * elle n'a rien à faire dans un fichier qu'on copie, qu'on envoie par message
 * ou qu'on téléverse. Elle se resaisit en dix secondes dans l'écran Admin.
 */
import type { BankrollState } from '../types/bankroll';
import { DEFAULT_SETTINGS, type Settings } from './settings';
import { KEYS, readJson, writeJson } from './storage';

export const BACKUP_FORMAT = 'vizer-backup';
export const BACKUP_VERSION = 1;

export interface Backup {
  format: typeof BACKUP_FORMAT;
  version: number;
  exportedAt: string;
  /** Horodatage du dernier changement d'état, pour arbitrer une synchro. */
  updatedAt: number;
  settings: Settings;
  bankroll: BankrollState;
}

/** Ce qu'une restauration a trouvé, avant de l'appliquer. */
export interface BackupSummary {
  exportedAt: string;
  bets: number;
  transactions: number;
  bankroll: number;
}

/* ── Production ──────────────────────────────────────────────────────────── */

/** État courant, lu directement du stockage pour ne dépendre d'aucun contexte. */
export function collectBackup(updatedAt = Date.now()): Backup {
  const settings = { ...DEFAULT_SETTINGS, ...readJson<Partial<Settings>>(KEYS.settings, {}) };
  const bankroll = readJson<Partial<BankrollState>>(KEYS.bankroll, {});

  return {
    format: BACKUP_FORMAT,
    version: BACKUP_VERSION,
    exportedAt: new Date().toISOString(),
    updatedAt,
    settings,
    bankroll: {
      bankroll: Number(bankroll.bankroll) || 0,
      goal: Number(bankroll.goal) || 0,
      stopLoss: Number(bankroll.stopLoss) || 0,
      transactions: Array.isArray(bankroll.transactions) ? bankroll.transactions : [],
      followed: Array.isArray(bankroll.followed) ? bankroll.followed : [],
      // Le ticket en cours ne se sauvegarde pas : il porte des cotes du jour
      // qui seront périmées à la restauration.
      slip: [],
    },
  };
}

/* ── Lecture ─────────────────────────────────────────────────────────────── */

/**
 * Valide un fichier de sauvegarde.
 *
 * Un import écrase tout : on refuse plutôt que d'appliquer à moitié. Les
 * contrôles portent sur la forme, pas sur le contenu — un montant aberrant
 * reste l'affaire de l'utilisateur, une structure cassée est la nôtre.
 */
export function parseBackup(raw: unknown): { backup: Backup } | { error: string } {
  if (!raw || typeof raw !== 'object') return { error: 'Fichier illisible.' };
  const b = raw as Partial<Backup>;

  if (b.format !== BACKUP_FORMAT) {
    return { error: "Ce fichier n'est pas une sauvegarde Vizer." };
  }
  if (typeof b.version !== 'number' || b.version > BACKUP_VERSION) {
    return {
      error: `Sauvegarde en version ${String(b.version)}, cette app lit jusqu'à ${BACKUP_VERSION}.`,
    };
  }
  if (!b.bankroll || typeof b.bankroll !== 'object') {
    return { error: 'Sauvegarde incomplète : bankroll absente.' };
  }

  const bank = b.bankroll as Partial<BankrollState>;
  if (!Array.isArray(bank.followed) || !Array.isArray(bank.transactions)) {
    return { error: 'Sauvegarde incomplète : paris ou mouvements absents.' };
  }

  return {
    backup: {
      format: BACKUP_FORMAT,
      version: b.version,
      exportedAt: typeof b.exportedAt === 'string' ? b.exportedAt : '',
      updatedAt: Number(b.updatedAt) || 0,
      settings: { ...DEFAULT_SETTINGS, ...(b.settings ?? {}) },
      bankroll: {
        bankroll: Number(bank.bankroll) || 0,
        goal: Number(bank.goal) || 0,
        stopLoss: Number(bank.stopLoss) || 0,
        transactions: bank.transactions,
        followed: bank.followed,
        slip: [],
      },
    },
  };
}

export function summarize(backup: Backup): BackupSummary {
  return {
    exportedAt: backup.exportedAt,
    bets: backup.bankroll.followed.length,
    transactions: backup.bankroll.transactions.length,
    bankroll: backup.bankroll.bankroll,
  };
}

/**
 * Écrit la sauvegarde dans le stockage.
 *
 * L'app relit son état au montage des contextes : l'appelant recharge la page
 * après coup plutôt que de tenter de réconcilier des états React déjà montés.
 */
export function applyBackup(backup: Backup): void {
  writeJson(KEYS.settings, backup.settings);
  writeJson(KEYS.bankroll, backup.bankroll);
}

/** Nom de fichier daté, pour que plusieurs sauvegardes cohabitent. */
export function backupFilename(now = new Date()): string {
  return `vizer-sauvegarde-${now.toISOString().slice(0, 10)}.json`;
}
