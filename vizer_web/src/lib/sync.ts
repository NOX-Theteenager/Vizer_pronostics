/**
 * Synchronisation de l'état entre appareils, par clé secrète.
 *
 * Pas de compte : la clé *est* la crédence. L'app en génère une au premier
 * usage ; la coller sur un second appareil suffit à y retrouver sa bankroll.
 *
 * Deux règles qui évitent les mauvaises surprises :
 *
 *   - **on n'écrase jamais en silence.** Au démarrage, l'app compare les
 *     horodatages et propose la restauration si le distant est plus récent.
 *     Deux appareils modifiés hors ligne restent un conflit, et c'est à
 *     l'utilisateur de trancher, pas à une heuristique ;
 *   - **l'envoi est différé.** Chaque clic sur « suivre » ne déclenche pas une
 *     requête : on attend que les changements se calment.
 */
import { collectBackup, parseBackup, type Backup } from './backup';
import { KEYS, readJson, writeJson } from './storage';

const STATE_URL = '/api/state';

/** Le relais n'existe que derrière nos fonctions (cf. `LIVE_URL`). */
export const SYNC_AVAILABLE =
  typeof window !== 'undefined' &&
  (import.meta.env.VITE_DATA_BASE ?? '').startsWith('/');

/* ── Clé ─────────────────────────────────────────────────────────────────── */

/** 32 octets aléatoires en base64url — 43 caractères, indevinable. */
function generateKey(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

export function readSyncKey(): string | null {
  return readJson<string | null>(KEYS.syncKey, null);
}

export function writeSyncKey(key: string | null): void {
  writeJson(KEYS.syncKey, key);
}

/** Clé existante, ou nouvelle clé créée et conservée. */
export function ensureSyncKey(): string {
  const existing = readSyncKey();
  if (existing) return existing;
  const key = generateKey();
  writeSyncKey(key);
  return key;
}

/** Une clé saisie à la main est-elle plausible ? */
export function isValidKey(key: string): boolean {
  return /^[A-Za-z0-9_-]{32,128}$/.test(key.trim());
}

/* ── Horodatage local ────────────────────────────────────────────────────── */

export function localUpdatedAt(): number {
  return readJson<number>(KEYS.syncUpdatedAt, 0);
}

export function markChanged(ts = Date.now()): void {
  writeJson(KEYS.syncUpdatedAt, ts);
}

/* ── Transport ───────────────────────────────────────────────────────────── */

export type PushResult = { ok: true; bytes: number } | { ok: false; error: string };

export async function pushState(key: string): Promise<PushResult> {
  if (!SYNC_AVAILABLE) return { ok: false, error: 'Synchronisation indisponible ici.' };
  const payload = collectBackup(localUpdatedAt() || Date.now());
  try {
    const res = await fetch(STATE_URL, {
      method: 'PUT',
      headers: { 'content-type': 'application/json', 'x-vizer-key': key },
      body: JSON.stringify(payload),
    });
    const body = (await res.json()) as { ok?: boolean; bytes?: number; error?: string };
    if (!res.ok || !body.ok) return { ok: false, error: body.error ?? `HTTP ${res.status}` };
    return { ok: true, bytes: body.bytes ?? 0 };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'Réseau indisponible.' };
  }
}

export type PullResult =
  | { status: 'found'; backup: Backup }
  | { status: 'empty' }
  | { status: 'error'; error: string };

export async function pullState(key: string): Promise<PullResult> {
  if (!SYNC_AVAILABLE) return { status: 'error', error: 'Synchronisation indisponible ici.' };
  try {
    const res = await fetch(STATE_URL, {
      headers: { 'x-vizer-key': key },
      cache: 'no-store',
    });
    const body = (await res.json()) as { found?: boolean; state?: unknown; error?: string };
    if (!res.ok) return { status: 'error', error: body.error ?? `HTTP ${res.status}` };
    if (!body.found) return { status: 'empty' };

    const parsed = parseBackup(body.state);
    if ('error' in parsed) return { status: 'error', error: parsed.error };
    return { status: 'found', backup: parsed.backup };
  } catch (e) {
    return { status: 'error', error: e instanceof Error ? e.message : 'Réseau indisponible.' };
  }
}
