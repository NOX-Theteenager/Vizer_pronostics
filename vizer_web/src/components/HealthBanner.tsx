import { marketShortLabel } from '../data/markets';
import { timeAgo } from '../lib/format';
import { SPORTS, type Sport } from '../types/model';
import type { DirectionFile, FreshnessFile } from '../types/performance';
import type { GateStatus } from '../lib/api';

/**
 * « Est-ce que ça va ? » — et quoi faire si non.
 *
 * C'était le manque le plus coûteux de l'écran Admin : il disait ce qui avait
 * été entraîné et ce que ça avait rapporté, mais jamais si le système était en
 * bon état. Le fait le plus lourd de la semaine du 20 octobre 2026 — données
 * d'entraînement gelées depuis treize jours, pendant que l'application
 * continuait de proposer des paris qui ont rendu −27 % — n'apparaissait
 * nulle part. Le run GitHub passait au rouge, mais personne ne lit les runs.
 *
 * Trois règles d'écriture, qui valent pour tout cet écran :
 *
 *   1. un verdict en mots avant tout chiffre ;
 *   2. une phrase qui dit ce que le chiffre signifie en matchs ou en jours ;
 *   3. tout état anormal porte son action, sinon il n'appelle rien.
 */

type Level = 'ok' | 'warn' | 'bad' | 'unknown';

interface Row {
  level: Level;
  topic: string;
  verdict: string;
  detail: string;
  action?: string;
}

const GLYPH: Record<Level, string> = { ok: '✅', warn: '⚠️', bad: '🛑', unknown: '·' };
const RANK: Record<Level, number> = { bad: 0, warn: 1, unknown: 2, ok: 3 };

function sportName(s: string): string {
  return SPORTS[s as Sport]?.label ?? s.toUpperCase();
}

/** Les données d'entraînement suivent-elles la saison ? */
function dataRow(freshness: FreshnessFile | null): Row {
  if (!freshness) {
    return {
      level: 'unknown',
      topic: 'Données',
      verdict: 'Non vérifiée',
      detail: 'Le contrôle de fraîcheur n’a pas encore publié de verdict.',
    };
  }

  const stale = freshness.stale ?? [];
  if (stale.length === 0) {
    const days = Object.values(freshness.sports ?? {})
      .map((s) => s?.lag_days)
      .filter((d): d is number => typeof d === 'number');
    const worst = days.length ? Math.max(...days) : null;
    return {
      level: 'ok',
      topic: 'Données',
      verdict: 'À jour',
      detail:
        worst === null
          ? 'Hors saison, ou aucun match joué récemment : rien à rattraper.'
          : worst === 0
            ? 'Les modèles ont vu tous les matchs joués jusqu’à hier.'
            : `Les modèles ont ${worst} jour(s) de matchs de retard, sous le seuil.`,
    };
  }

  const detail = stale
    .map((s) => {
      const lag = freshness.sports?.[s as Sport]?.lag_days;
      return `${sportName(s)} : ${lag ?? '?'} jours de matchs non vus`;
    })
    .join(' · ');

  return {
    level: 'bad',
    topic: 'Données',
    verdict: 'En retard sur la saison',
    // Dire ce que ça fait, pas seulement que c'est anormal : un retard de
    // données ne se voit pas dans les prédictions, qui restent d'apparence
    // normale. C'est précisément ce qui l'avait rendu invisible.
    detail:
      `${detail}. Les prédictions de ce ou ces sports décrivent un championnat `
      + `dépassé, et leurs paris ne sont pas fiables.`,
    action: 'Republier le dataset depuis le PC, puis réentraîner.',
  };
}

/**
 * Le dernier entraînement a-t-il été accepté — et a-t-il seulement été jugé ?
 *
 * « Accepté » et « pas assez de matchs pour juger » donnent tous deux un
 * `passed: true`, et c'est le piège. Au changement de saison, le jeu de test
 * se réduit aux quelques matchs déjà joués : la barrière s'abstient sur chaque
 * marché et laisse passer. Constaté le 27/10/2026 — la NBA entrait dans sa
 * saison avec 43 matchs de test contre 300 requis, et le modèle se déployait
 * sans qu'aucun seuil ne soit vérifié, sous un écran annonçant « accepté ».
 */
function modelRow(gate: GateStatus | null): Row {
  if (!gate) {
    return {
      level: 'unknown',
      topic: 'Modèles',
      verdict: 'État inconnu',
      detail: 'Aucun verdict d’entraînement publié pour l’instant.',
    };
  }
  const blocked = Object.keys(gate.blocked ?? {});
  if (blocked.length) {
    return {
      level: 'bad',
      topic: 'Modèles',
      verdict: 'Déploiement refusé',
      detail: blocked
        .map((s) => `${sportName(s)} : ${gate.blocked[s]?.headline ?? 'cause inconnue'}`)
        .join(' · '),
      action: 'Les modèles précédents restent en service — rien d’urgent à faire.',
    };
  }

  // Un sport dont *tous* les marchés sont en abstention n'a pas été jugé.
  const unjudged = Object.entries(gate.verdicts ?? {}).filter(([, v]) => {
    const checks = v?.checks ?? [];
    return checks.length > 0 && checks.every((c) => c.verdict === 'skip');
  });

  if (unjudged.length) {
    return {
      level: 'warn',
      topic: 'Modèles',
      verdict: 'Déployés sans avoir été jugés',
      detail: unjudged
        .map(([s, v]) => `${sportName(s)} : ${v?.n_test ?? 0} matchs de test, `
          + `trop peu pour vérifier un seuil`)
        .join(' · '),
      action:
        'Normal en début de saison : le jeu de test se remplit avec les matchs '
        + 'joués. En attendant, c’est la mesure sur les prédictions publiées qui '
        + 'fait foi — onglet Performance réelle.',
    };
  }

  return {
    level: 'ok',
    topic: 'Modèles',
    verdict: 'Dernier entraînement accepté',
    detail:
      `Vérifié ${timeAgo(gate.checked_at)} sur des matchs mis de côté avant `
      + `l’entraînement. Aucun marché sous sa limite.`,
  };
}

/** Des marchés sont-ils retenus, et pourquoi ? */
function marketRow(direction: DirectionFile | null): Row {
  const rows = Object.entries(direction?.sports ?? {}).flatMap(
    ([sport, list]) => (list ?? []).map((v) => ({ sport, v })),
  );
  const withheld = rows.filter((r) => r.v.status === 'withheld');
  const warned = rows.filter((r) => r.v.status === 'imbalanced');

  if (withheld.length) {
    return {
      level: 'bad',
      topic: 'Marchés',
      verdict: `${withheld.length} marché(s) mis en pause`,
      detail: withheld
        .map((r) => `${marketShortLabel(r.v.market)} (${sportName(r.sport)}) : `
          + `${r.v.counts[r.v.dominant ?? ''] ?? 0} paris sur ${r.v.n} du même côté`)
        .join(' · '),
      action:
        'Leurs paris ne sont plus proposés ; les prédictions continuent d’être '
        + 'publiées et mesurées. La pause tombera d’elle-même si le modèle se recale.',
    };
  }
  if (warned.length) {
    return {
      level: 'warn',
      topic: 'Marchés',
      verdict: 'Tous proposés, un déséquilibre à l’œil',
      detail: warned
        .map((r) => `${marketShortLabel(r.v.market)} penche vers « ${r.v.dominant} » `
          + `(${r.v.counts[r.v.dominant ?? ''] ?? 0}/${r.v.n})`)
        .join(' · '),
    };
  }
  return {
    level: rows.length ? 'ok' : 'unknown',
    topic: 'Marchés',
    verdict: rows.length ? 'Tous proposés' : 'Pas encore de verdict',
    detail: rows.length
      ? 'Aucun marché ne parie systématiquement du même côté.'
      : 'Le sens des paris sera mesuré dès qu’il y en aura assez.',
  };
}

export function HealthBanner({
  freshness,
  gate,
  direction,
}: {
  freshness: FreshnessFile | null;
  gate: GateStatus | null;
  direction: DirectionFile | null;
}) {
  // Le plus grave en premier : un écran lu en diagonale doit montrer le
  // problème, pas l'ordre dans lequel on a écrit le code.
  const rows = [dataRow(freshness), modelRow(gate), marketRow(direction)].sort(
    (a, b) => RANK[a.level] - RANK[b.level],
  );
  const worst = rows[0].level;

  return (
    <div className={`vz-card vz-card--rows vz-health is-${worst}`}>
      {rows.map((r) => (
        <div className="vz-health__row" key={r.topic}>
          <span className="vz-health__glyph" aria-hidden>
            {GLYPH[r.level]}
          </span>
          <span className="vz-f1">
            <strong className="vz-health__verdict">
              {r.topic} · {r.verdict}
            </strong>
            <small className="vz-note">{r.detail}</small>
            {r.action && <small className="vz-health__action">→ {r.action}</small>}
          </span>
        </div>
      ))}
    </div>
  );
}
