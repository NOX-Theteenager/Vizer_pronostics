/**
 * Persistance locale. Tout accès est protégé : navigation privée, quota plein
 * ou stockage bloqué ne doivent jamais casser l'app.
 */
const PREFIX = 'vizer:';

export const KEYS = {
  settings: `${PREFIX}settings:v2`,
  bankroll: `${PREFIX}bankroll:v2`,
  feed: (sport: string) => `${PREFIX}feed:${sport}:v1`,
  fetchedAt: `${PREFIX}feed:fetchedAt:v1`,
  /** Scores finaux publiés — sert à clôturer les paris hors-ligne. */
  results: `${PREFIX}results:v1`,
  notified: `${PREFIX}notified:v1`,
  seenAlerts: `${PREFIX}alerts:seen:v1`,
  recentSearches: `${PREFIX}search:recent:v1`,
  dismissedReminders: `${PREFIX}reminders:dismissed:v1`,
  /** Jeton GitHub de l'écran Admin — local, jamais synchronisé. */
  githubToken: `${PREFIX}github:token:v1`,
} as const;

export function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeJson(key: string, value: unknown): boolean {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function removeKey(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

/** Vide le cache de données sans toucher aux réglages ni à la bankroll. */
export function clearDataCache(): void {
  try {
    const doomed: string[] = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const k = localStorage.key(i);
      if (k && k.startsWith(`${PREFIX}feed:`)) doomed.push(k);
    }
    doomed.forEach((k) => localStorage.removeItem(k));
  } catch {
    /* ignore */
  }
}

/** Télécharge un contenu texte (export CSV). */
export function downloadText(filename: string, content: string, mime = 'text/csv'): boolean {
  try {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return true;
  } catch {
    return false;
  }
}
