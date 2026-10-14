/**
 * Derniers runs GitHub Actions, et dates d'historique des modèles.
 *
 * Lecture seule sur des informations déjà publiques : cette route n'a donc
 * pas de secret à exiger. Elle existe pour que le jeton — qui, lui, lève le
 * quota de 60 requêtes/h par IP — reste sur le serveur.
 *
 * Sans jeton configuré, elle répond quand même : simplement soumise au quota,
 * comme l'était l'app auparavant.
 */
import { BRANCH, ghHeaders, hasToken, json, REPO } from '../_lib/github.js';

interface RawRun {
  id: number;
  name: string;
  status: string;
  conclusion: string | null;
  created_at: string;
  html_url: string;
  path: string;
}

export async function GET(request: Request): Promise<Response> {
  const limit = Math.min(
    30,
    Math.max(1, Number(new URL(request.url).searchParams.get('limit')) || 10),
  );
  const repo = REPO();

  const [runsRes, historyRes] = await Promise.allSettled([
    fetch(`https://api.github.com/repos/${repo}/actions/runs?per_page=${limit}`, {
      headers: ghHeaders(),
    }),
    fetch(
      `https://api.github.com/repos/${repo}/contents/models/history?ref=${BRANCH()}`,
      { headers: ghHeaders() },
    ),
  ]);

  let runs: unknown[] = [];
  let error: string | null = null;

  if (runsRes.status === 'fulfilled' && runsRes.value.ok) {
    const data = (await runsRes.value.json()) as { workflow_runs?: RawRun[] };
    runs = (data.workflow_runs ?? []).map((r) => ({
      id: r.id,
      name: r.name,
      status: r.status,
      conclusion: r.conclusion,
      createdAt: r.created_at,
      url: r.html_url,
      workflow: r.path.split('/').pop() ?? r.path,
    }));
  } else if (runsRes.status === 'fulfilled') {
    error =
      runsRes.value.status === 403 && !hasToken()
        ? 'Quota GitHub atteint. Configurez VIZER_GITHUB_TOKEN pour le lever.'
        : `GitHub ${runsRes.value.status}`;
  } else {
    error = 'GitHub injoignable.';
  }

  // L'historique des modèles est un bonus : son absence ne doit pas priver
  // l'écran du journal des exécutions.
  let history: string[] = [];
  if (historyRes.status === 'fulfilled' && historyRes.value.ok) {
    const files = (await historyRes.value.json()) as { name: string; type: string }[];
    history = files
      .filter((f) => f.type === 'file' && f.name.endsWith('.json'))
      .map((f) => f.name.replace(/\.json$/, ''))
      .sort()
      .reverse();
  }

  return json(
    { repo, authenticated: hasToken(), runs, history, error },
    error && runs.length === 0 ? 502 : 200,
    // Trente secondes : assez pour absorber plusieurs ouvertures de l'écran,
    // assez court pour voir apparaître un run qu'on vient de déclencher.
    'public, max-age=0, must-revalidate',
  );
}
