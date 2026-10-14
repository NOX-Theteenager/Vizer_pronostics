/**
 * Accès GitHub pour l'écran Admin — par le serveur.
 *
 * Le jeton GitHub ne passe plus par le navigateur. Il était auparavant collé
 * dans cet écran et conservé dans `localStorage` : un jeton capable d'écrire
 * sur le dépôt, exposé à toute extension installée et à quiconque a accès à
 * l'appareil. Il vit maintenant dans les variables d'environnement du
 * déploiement, et l'app passe par `/api/gh/*`.
 *
 * Ce qui reste côté navigateur est la **clé d'administration** : un secret
 * propre à ce déploiement, qui n'autorise que les trois workflows listés
 * côté serveur et ne donne accès à rien d'autre. Le compromettre ne compromet
 * pas le dépôt, et il se change sans toucher à GitHub.
 */
import { KEYS, readJson, writeJson } from './storage';

const DEFAULT_REPO = 'NOX-Theteenager/Vizer_pronostics';

export const REPO: string = import.meta.env.VITE_GITHUB_REPO || DEFAULT_REPO;

/** Les routes serveur n'existent que derrière nos fonctions. */
export const GH_AVAILABLE = (import.meta.env.VITE_DATA_BASE ?? '').startsWith('/');

/** Workflows pilotables depuis l'app. La liste fermée vit côté serveur. */
export const WORKFLOWS = {
  training: 'vizer_training_pipeline.yml',
  predictions: 'vizer_daily_predictions.yml',
  web: 'vizer_web_deploy.yml',
} as const;

export type WorkflowKey = keyof typeof WORKFLOWS;

/* ── Clé d'administration ─────────────────────────────────────────────── */

export function readAdminKey(): string {
  return readJson<string>(KEYS.adminKey, '');
}

export function writeAdminKey(key: string): void {
  writeJson(KEYS.adminKey, key.trim());
}

/* ── Lecture ──────────────────────────────────────────────────────────── */

export interface WorkflowRun {
  id: number;
  name: string;
  status: string;
  conclusion: string | null;
  createdAt: string;
  url: string;
  workflow: string;
}

export interface RunsPayload {
  runs: WorkflowRun[];
  /** Dates publiées dans `models/history/`. */
  history: string[];
  /** Le serveur dispose d'un jeton : le quota de 60 req/h ne s'applique pas. */
  authenticated: boolean;
  error: string | null;
}

/**
 * Journal des exécutions et historique des modèles, en un appel.
 *
 * Les deux lectures étaient séparées et échouaient séparément ; le serveur
 * les fait en parallèle et renvoie ce qu'il a pu obtenir, parce qu'un
 * historique indisponible ne doit pas priver l'écran de son journal.
 */
export async function fetchRuns(limit = 10): Promise<RunsPayload> {
  if (!GH_AVAILABLE) {
    return { runs: [], history: [], authenticated: false, error: 'Indisponible ici.' };
  }
  const res = await fetch(`/api/gh/runs?limit=${limit}`, { cache: 'no-store' });
  const body = (await res.json()) as Partial<RunsPayload>;
  return {
    runs: body.runs ?? [],
    history: body.history ?? [],
    authenticated: !!body.authenticated,
    error: body.error ?? (res.ok ? null : `HTTP ${res.status}`),
  };
}

/* ── Écriture ─────────────────────────────────────────────────────────── */

/** Déclenche un workflow. Lève avec un message affichable en cas de refus. */
export async function dispatchWorkflow(
  key: WorkflowKey,
  adminKey: string,
  ref = 'main',
  inputs: Record<string, string> = {},
): Promise<void> {
  if (!GH_AVAILABLE) throw new Error('Actions indisponibles sur ce déploiement.');
  if (!adminKey) throw new Error('Clé d’administration absente.');

  const res = await fetch('/api/gh/dispatch', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-vizer-admin': adminKey },
    body: JSON.stringify({ workflow: key, ref, inputs }),
  });
  if (res.status === 204 || res.ok) return;

  const body = (await res.json().catch(() => ({}))) as { error?: string };
  throw new Error(body.error ?? `Échec (HTTP ${res.status})`);
}
