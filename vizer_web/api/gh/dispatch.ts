/**
 * Déclenche un workflow GitHub Actions.
 *
 * Pourquoi cette route exige un secret
 * ------------------------------------
 * Elle écrit. Le jeton GitHub est désormais sur le serveur, ce qui est un
 * progrès — mais si l'endpoint était ouvert, n'importe qui trouvant l'URL
 * pourrait lancer vos entraînements en boucle. On a déplacé le jeton, pas
 * supprimé le besoin d'autoriser.
 *
 * Le secret présenté par le client (`VIZER_ADMIN_SECRET`) vaut mieux qu'un
 * jeton GitHub collé dans le navigateur, pour trois raisons : il n'a aucune
 * valeur en dehors de ce déploiement, il ne donne accès à rien d'autre qu'aux
 * trois workflows ci-dessous, et il se change sans toucher à GitHub.
 *
 * La liste des workflows est fermée. Relayer un nom de fichier arbitraire
 * reviendrait à exposer *tous* les workflows du dépôt, présents et futurs.
 */
import { env } from '../_lib/env.js';
import { ghHeaders, hasToken, json, REPO } from '../_lib/github.js';

const WORKFLOWS: Record<string, string> = {
  training: 'vizer_training_pipeline.yml',
  predictions: 'vizer_daily_predictions.yml',
  web: 'vizer_web_deploy.yml',
};

/** Comparaison à durée constante : une égalité naïve fuit le secret. */
function sameSecret(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

interface Body {
  workflow?: string;
  ref?: string;
  inputs?: Record<string, string>;
}

export async function POST(request: Request): Promise<Response> {
  const expected = env('VIZER_ADMIN_SECRET');
  if (!expected) {
    return json(
      { error: "Actions désactivées : VIZER_ADMIN_SECRET n'est pas configuré." },
      503,
    );
  }
  const presented = request.headers.get('x-vizer-admin') ?? '';
  if (!sameSecret(presented, expected)) {
    return json({ error: 'Clé d’administration invalide.' }, 401);
  }
  if (!hasToken()) {
    return json(
      { error: "VIZER_GITHUB_TOKEN absent : impossible de déclencher un workflow." },
      503,
    );
  }

  let body: Body;
  try {
    body = (await request.json()) as Body;
  } catch {
    return json({ error: 'Corps JSON invalide.' }, 400);
  }

  const file = WORKFLOWS[body.workflow ?? ''];
  if (!file) return json({ error: 'Workflow inconnu.' }, 400);

  // La référence est contrainte à un nom de branche plausible : elle part
  // dans une URL GitHub.
  const ref = body.ref ?? 'main';
  if (!/^[\w./-]{1,100}$/.test(ref)) return json({ error: 'Référence invalide.' }, 400);

  const res = await fetch(
    `https://api.github.com/repos/${REPO()}/actions/workflows/${file}/dispatches`,
    {
      method: 'POST',
      headers: { ...ghHeaders(), 'content-type': 'application/json' },
      body: JSON.stringify({ ref, inputs: body.inputs ?? {} }),
    },
  );

  // GitHub répond 204 sans corps quand c'est parti.
  if (res.status === 204) return json({ ok: true, workflow: file, ref });

  const detail = await res.text().catch(() => '');
  return json(
    {
      error:
        res.status === 404
          ? "Workflow introuvable, ou le jeton n'a pas la permission Actions sur ce dépôt."
          : `GitHub ${res.status}${detail ? ` — ${detail.slice(0, 160)}` : ''}`,
    },
    502,
  );
}
