/**
 * Accès aux données publiées par le backend.
 *
 * La PWA ne parle à aucune API serveur : elle lit les JSON statiques poussés
 * sur la branche `models-artifacts` par le workflow « Vizer Daily Predictions »
 * (cf. .github/workflows/vizer_daily_predictions.yml) :
 *
 *   <base>/latest/nhl.json
 *   <base>/latest/nba.json
 *   <base>/archive/YYYY-MM-DD/<sport>.json
 *   <base>/../results/latest.json          ← scores finaux, 7 derniers jours
 *
 * Stratégie : réseau d'abord, cache localStorage en repli. Le rafraîchissement
 * est un re-fetch, jamais un recalcul (design.md §2).
 */
import type { Sport, SportFeed } from '../types/model';
import { normalizeFeed } from '../types/normalize';
import { normalizeLive, type LiveGame } from '../types/live';
import type { PerformanceFile } from '../types/performance';
import { normalizeResults, type GameResult } from '../types/results';
import { KEYS, readJson, writeJson } from './storage';

const DEFAULT_BASE =
  'https://raw.githubusercontent.com/NOX-Theteenager/Vizer_pronostics/models-artifacts/predictions';

export const DATA_BASE: string = (
  import.meta.env.VITE_DATA_BASE || DEFAULT_BASE
).replace(/\/+$/, '');

/**
 * Source de secours quand la base configurée est relative.
 *
 * Sur Vercel, `VITE_DATA_BASE` vaut `/api/data/predictions` : les JSON passent
 * par le proxy Edge du dépôt. Si cette fonction tombe — déploiement partiel,
 * panne de la plateforme — l'app n'a plus aucune donnée alors que la source
 * d'origine, elle, répond toujours. On garde donc le chemin direct comme
 * second essai, jamais comme premier (le proxy existe pour de bonnes raisons :
 * cache piloté, quota mutualisé, même origine).
 */
const FALLBACK_BASE = DATA_BASE.startsWith('/') ? DEFAULT_BASE : null;

/**
 * Le proxy a déjà échoué dans cette session : on cesse de l'interroger.
 *
 * Sans ce drapeau, chaque fetch paierait deux allers-retours tant que la
 * fonction est absente. Il n'est pas persisté : un déploiement qui répare la
 * fonction doit reprendre la main au rechargement suivant.
 */
let proxyDown = false;

/** Traduit une URL du proxy vers la source directe. */
function fallbackUrl(url: string): string | null {
  if (!FALLBACK_BASE || !url.startsWith(DATA_BASE)) return null;
  return FALLBACK_BASE + url.slice(DATA_BASE.length);
}

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === '1';

export const SPORTS: Sport[] = ['nhl', 'nba'];

/** Les échantillons de design.md §6, embarqués pour le dev et le mode démo. */
function mockUrl(sport: Sport): string {
  return `${import.meta.env.BASE_URL}mock/${sport}.json`;
}

function latestUrl(sport: Sport): string {
  // `cb` casse le cache CDN de raw.githubusercontent (5 min sinon) sans
  // désactiver le cache HTTP du service worker.
  return `${DATA_BASE}/latest/${sport}.json?cb=${Math.floor(Date.now() / 60_000)}`;
}

function archiveUrl(sport: Sport, day: string): string {
  return `${DATA_BASE}/archive/${day}/${sport}.json`;
}

/**
 * Recale les échantillons sur aujourd'hui.
 *
 * Les fichiers de `public/mock/` portent des dates fixes ; sans recalage, le
 * mode démo afficherait des matchs « commencés » depuis des mois. On décale
 * tout le feed du même nombre de jours, ce qui préserve les heures et les
 * écarts entre matchs.
 */
function shiftMockDates(raw: unknown): unknown {
  if (!raw || typeof raw !== 'object') return raw;
  const feed = raw as { generated_at?: string; games?: { commence_time?: string }[] };
  const base = feed.generated_at ? new Date(feed.generated_at) : null;
  if (!base || Number.isNaN(base.getTime())) return raw;

  const startOfUtcDay = (d: Date) =>
    Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  const offset = startOfUtcDay(new Date()) - startOfUtcDay(base);
  if (offset === 0) return raw;

  const shift = (iso?: string) => {
    if (!iso) return iso;
    const t = new Date(iso).getTime();
    return Number.isNaN(t) ? iso : new Date(t + offset).toISOString();
  };

  return {
    ...feed,
    generated_at: shift(feed.generated_at),
    games: (feed.games ?? []).map((g) => ({ ...g, commence_time: shift(g.commence_time) })),
  };
}

async function fetchOnce(url: string, timeoutMs: number): Promise<unknown> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctrl.signal, cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Lit un JSON, avec repli sur la source directe quand on passe par le proxy.
 *
 * Le repli couvre **aussi** le 404. À travers le proxy, un 404 est ambigu : il
 * peut dire « ce fichier n'existe pas » comme « cette fonction n'est pas
 * déployée ». Seule la source directe tranche — et c'est exactement ce qui est
 * arrivé en production : la fonction Edge avait été écartée par une erreur de
 * compilation, le proxy répondait 404 sur tout, et l'app restait vide alors que
 * les prédictions étaient publiées.
 */
async function fetchJson(url: string, timeoutMs = 12_000): Promise<unknown> {
  const direct = fallbackUrl(url);

  if (direct && proxyDown) return await fetchOnce(direct, timeoutMs);

  try {
    return await fetchOnce(url, timeoutMs);
  } catch (err) {
    if (!direct) throw err;
    const payload = await fetchOnce(direct, timeoutMs);
    // La source directe répond là où le proxy a échoué : le proxy est en
    // cause, pas la donnée.
    proxyDown = true;
    return payload;
  }
}

export interface FetchResult {
  feeds: Record<Sport, SportFeed | null>;
  origin: 'network' | 'cache' | 'mock';
  /** Sports dont le fetch a échoué alors qu'un autre a réussi. */
  partialFailures: Sport[];
}

/** Lit les feeds en cache sans toucher au réseau (démarrage instantané). */
export function readCachedFeeds(): Record<Sport, SportFeed | null> {
  const out: Record<Sport, SportFeed | null> = { nhl: null, nba: null };
  for (const sport of SPORTS) {
    const raw = readJson<unknown>(KEYS.feed(sport), null);
    if (raw) out[sport] = normalizeFeed(sport, raw);
  }
  return out;
}

export function readCachedFetchedAt(): number | null {
  return readJson<number | null>(KEYS.fetchedAt, null);
}

/**
 * Récupère les deux sports. Un sport en échec ne bloque pas l'autre : le
 * workflow lui-même publie sport par sport (step 5), donc un seul fichier
 * peut manquer durablement.
 */
export async function fetchLatest(opts: { mock?: boolean } = {}): Promise<FetchResult> {
  const useMock = opts.mock ?? USE_MOCK;
  const feeds: Record<Sport, SportFeed | null> = { nhl: null, nba: null };
  const partialFailures: Sport[] = [];

  const results = await Promise.allSettled(
    SPORTS.map((s) => fetchJson(useMock ? mockUrl(s) : latestUrl(s))),
  );

  results.forEach((res, i) => {
    const sport = SPORTS[i];
    if (res.status === 'fulfilled') {
      const payload = useMock ? shiftMockDates(res.value) : res.value;
      feeds[sport] = normalizeFeed(sport, payload);
      if (!useMock) writeJson(KEYS.feed(sport), payload);
    } else {
      partialFailures.push(sport);
    }
  });

  if (partialFailures.length === SPORTS.length) {
    throw new Error(
      useMock
        ? "Échantillons de démonstration introuvables."
        : "Impossible de joindre les prédictions publiées.",
    );
  }

  if (!useMock) writeJson(KEYS.fetchedAt, Date.now());

  return { feeds, origin: useMock ? 'mock' : 'network', partialFailures };
}

/** Racine des artefacts de modèles, voisine de `predictions/`. */
export const MODELS_BASE = DATA_BASE.replace(/\/predictions\/?$/, '/models');

/** Métriques et métadonnées des modèles en production (écran Admin). */
export interface ModelInfo {
  sport: string;
  name: string;
  model_version?: string;
  trained_at?: string;
  trained_at_source?: string;
  markets?: string[];
  n_markets?: number;
  n_games_train?: number;
  training_mode?: string;
  metrics_in_sample?: boolean;
  train_seasons?: string;
  training_duration_sec?: number;
  metrics?: Record<string, Record<string, number | string | boolean>>;
  error?: string;
}

export interface ModelRegistryFile {
  generated_at: string;
  models: Record<string, ModelInfo>;
}

export async function fetchModelRegistry(day?: string): Promise<ModelRegistryFile> {
  const url = day
    ? `${MODELS_BASE}/history/${day}.json`
    : `${MODELS_BASE}/registry.json?cb=${Math.floor(Date.now() / 300_000)}`;
  return (await fetchJson(url)) as ModelRegistryFile;
}

/* ── Barrière de qualité ─────────────────────────────────────────────────── */

/**
 * Dernier verdict de la barrière de qualité, publié par le workflow
 * d'entraînement (`models/gate.json`).
 *
 * Sans lui, savoir pourquoi un sport n'a pas été redéployé demandait d'aller
 * lire les logs GitHub Actions.
 */
export interface GateRefusal {
  cause?: string;
  headline?: string;
  n_test?: number;
  checks?: { market?: string; verdict?: string; auc?: number; floor?: number; reason?: string }[];
}

export interface GateStatus {
  checked_at: string;
  run_number?: string;
  run_id?: string;
  sport?: string;
  passed: boolean;
  blocked: Record<string, GateRefusal>;
}

export async function fetchGateStatus(): Promise<GateStatus> {
  const url = `${MODELS_BASE}/gate.json?cb=${Math.floor(Date.now() / 300_000)}`;
  return (await fetchJson(url)) as GateStatus;
}

/* ── Performance ─────────────────────────────────────────────────────────── */

/** Racine des mesures de performance, voisine de `predictions/`. */
export const PERFORMANCE_BASE = DATA_BASE.replace(/\/predictions\/?$/, '/performance');

/**
 * Ce que valent réellement les prédictions publiées.
 *
 * Recalculé une fois par jour par le job de publication : un cache de cinq
 * minutes suffit, et le chiffre ne bouge pas plus vite que ça.
 */
export async function fetchPerformance(): Promise<PerformanceFile> {
  const url = `${PERFORMANCE_BASE}/summary.json?cb=${Math.floor(Date.now() / 300_000)}`;
  return (await fetchJson(url)) as PerformanceFile;
}

/** Archive d'un jour donné — utilisée par l'écran Historique. */
export async function fetchArchive(sport: Sport, day: string): Promise<SportFeed | null> {
  try {
    const raw = await fetchJson(archiveUrl(sport, day));
    return normalizeFeed(sport, raw);
  } catch {
    return null;
  }
}

/* ── Résultats ───────────────────────────────────────────────────────────── */

/** Racine des scores finaux, voisine de `predictions/`. */
export const RESULTS_BASE = DATA_BASE.replace(/\/predictions\/?$/, '/results');

/**
 * Scores finaux des sept derniers jours — un seul fichier, donc un seul fetch
 * pour clôturer tout l'historique en attente.
 *
 * Le cache-buster est à la demi-heure : les résultats ne bougent qu'une fois
 * par jour, inutile de contourner le CDN plus souvent.
 */
export async function fetchResults(): Promise<GameResult[]> {
  const url = `${RESULTS_BASE}/latest.json?cb=${Math.floor(Date.now() / 1_800_000)}`;
  const raw = await fetchJson(url);
  const results = normalizeResults(raw);
  writeJson(KEYS.results, raw);
  return results;
}

/** Derniers résultats connus, sans réseau (clôture hors-ligne au démarrage). */
export function readCachedResults(): GameResult[] {
  const raw = readJson<unknown>(KEYS.results, null);
  return raw ? normalizeResults(raw) : [];
}

/* ── Direct ──────────────────────────────────────────────────────────────── */

/**
 * URL du relais de scores en direct, ou `null` s'il n'existe pas ici.
 *
 * Le relais est une fonction servie à côté de l'app. Quand `DATA_BASE` est
 * relatif, c'est qu'on tourne derrière nos propres fonctions — sur GitHub
 * Pages ou en `npm run dev`, elles n'existent pas, et il vaut mieux désactiver
 * le direct que de laisser l'app tenter un appel voué au 404.
 *
 * `VITE_LIVE_URL` force l'adresse, ce qui permet de pointer un déploiement
 * réel depuis le développement local.
 */
export const LIVE_URL: string | null =
  import.meta.env.VITE_LIVE_URL || (DATA_BASE.startsWith('/') ? '/api/live' : null);

/** Scores en direct. Lève si le relais est absent ou injoignable. */
export async function fetchLive(): Promise<LiveGame[]> {
  if (!LIVE_URL) return [];
  return normalizeLive(await fetchOnce(LIVE_URL, 8_000));
}
