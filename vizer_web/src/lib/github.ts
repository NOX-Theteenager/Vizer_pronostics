/**
 * Accès GitHub pour l'écran Admin.
 *
 * Lecture (runs de workflow, historique des modèles) : l'API publique suffit
 * sur un dépôt public, sans jeton — avec un quota de 60 requêtes/h par IP.
 * Écriture (déclencher un workflow) : impossible sans jeton, donc l'utilisateur
 * colle un **fine-grained PAT** (scope Actions: read & write) stocké en local,
 * jamais envoyé ailleurs qu'à api.github.com.
 */
import { KEYS, readJson, writeJson } from './storage';

const DEFAULT_REPO = 'NOX-Theteenager/Vizer_pronostics';

export const REPO: string = import.meta.env.VITE_GITHUB_REPO || DEFAULT_REPO;
export const API = `https://api.github.com/repos/${REPO}`;

/** Workflows pilotables depuis l'app. */
export const WORKFLOWS = {
  training: 'vizer_training_pipeline.yml',
  predictions: 'vizer_daily_predictions.yml',
  web: 'vizer_web_deploy.yml',
} as const;

export type WorkflowKey = keyof typeof WORKFLOWS;

export function readToken(): string {
  return readJson<string>(KEYS.githubToken, '');
}

export function writeToken(token: string): void {
  writeJson(KEYS.githubToken, token.trim());
}

function headers(token?: string): HeadersInit {
  const h: Record<string, string> = { Accept: 'application/vnd.github+json' };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

export interface WorkflowRun {
  id: number;
  name: string;
  status: string;
  conclusion: string | null;
  createdAt: string;
  url: string;
  workflow: string;
}

/** Derniers runs, tous workflows confondus. */
export async function listRuns(limit = 10, token?: string): Promise<WorkflowRun[]> {
  const res = await fetch(`${API}/actions/runs?per_page=${limit}`, {
    headers: headers(token),
  });
  if (!res.ok) throw new Error(`GitHub ${res.status}`);
  const data = (await res.json()) as {
    workflow_runs?: {
      id: number;
      name: string;
      status: string;
      conclusion: string | null;
      created_at: string;
      html_url: string;
      path: string;
    }[];
  };
  return (data.workflow_runs ?? []).map((r) => ({
    id: r.id,
    name: r.name,
    status: r.status,
    conclusion: r.conclusion,
    createdAt: r.created_at,
    url: r.html_url,
    workflow: r.path.split('/').pop() ?? r.path,
  }));
}

/**
 * Déclenche un workflow (`workflow_dispatch`). Nécessite un jeton.
 * GitHub répond 204 sans corps en cas de succès.
 */
export async function dispatchWorkflow(
  key: WorkflowKey,
  token: string,
  ref = 'main',
  inputs: Record<string, string> = {},
): Promise<void> {
  if (!token) throw new Error('Jeton GitHub absent');
  const res = await fetch(`${API}/actions/workflows/${WORKFLOWS[key]}/dispatches`, {
    method: 'POST',
    headers: { ...headers(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref, inputs }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(
      res.status === 404
        ? "Workflow introuvable, ou le jeton n'a pas le droit Actions sur ce dépôt."
        : `GitHub ${res.status}${detail ? ` — ${detail.slice(0, 120)}` : ''}`,
    );
  }
}

/** Historique des exports de registre publiés (models/history/*.json). */
export async function listModelHistory(token?: string): Promise<string[]> {
  const res = await fetch(`${API}/contents/models/history?ref=models-artifacts`, {
    headers: headers(token),
  });
  if (!res.ok) return [];
  const data = (await res.json()) as { name: string; type: string }[];
  return data
    .filter((f) => f.type === 'file' && f.name.endsWith('.json'))
    .map((f) => f.name.replace(/\.json$/, ''))
    .sort()
    .reverse();
}
