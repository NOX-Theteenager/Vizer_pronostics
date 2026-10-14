import { useCallback, useEffect, useMemo, useState } from 'react';
import { Chip, SectionLabel, SegButton, SegGroup } from '../components/Primitives';
import { IconCheck, IconDownload, IconRefresh, IconWarning, IconX } from '../components/Icons';
import { useToast } from '../context/ToastContext';
import { Performance } from '../components/Performance';
import type { PerformanceFile } from '../types/performance';
import {
  fetchGateStatus,
  fetchModelRegistry,
  fetchPerformance,
  type GateStatus,
  type ModelInfo,
  type ModelRegistryFile,
} from '../lib/api';
import { formatNumber, formatShortDate, timeAgo } from '../lib/format';
import {
  dispatchWorkflow,
  listModelHistory,
  listRuns,
  readToken,
  REPO,
  writeToken,
  type WorkflowKey,
  type WorkflowRun,
} from '../lib/github';
import { SPORTS, type Sport } from '../types/model';

/**
 * Écran Admin — pilotage réel des modèles et des données.
 *
 * Lecture : `models/registry.json` publié par le workflow quotidien, plus les
 * runs GitHub Actions (API publique). Écriture : `workflow_dispatch`, qui
 * nécessite un jeton à portée Actions, saisi et conservé en local.
 *
 * Rien n'est simulé : sans jeton, les actions sont désactivées et le disent.
 */

/**
 * Métriques mises en avant, par ordre de lecture.
 *
 * Deux orthographes par métrique : la NHL suffixe (`auc_test`), la NBA préfixe
 * (`test_auc`). Les deux registres existent tels quels — la barrière de qualité
 * fait déjà le même compromis plutôt que d'imposer une convention à des
 * fichiers qui ont la leur.
 */
const HEADLINE: { keys: string[]; label: string; digits: number; higherIsBetter: boolean }[] = [
  { keys: ['accuracy_test', 'test_accuracy'], label: 'Précision', digits: 3, higherIsBetter: true },
  { keys: ['auc_test', 'test_auc'], label: 'AUC', digits: 4, higherIsBetter: true },
  {
    keys: ['brier_calibrated_test', 'test_brier_score'],
    label: 'Brier calibré',
    digits: 4,
    higherIsBetter: false,
  },
  { keys: ['temperature'], label: 'Température', digits: 3, higherIsBetter: true },
  { keys: ['n_features'], label: 'Features', digits: 0, higherIsBetter: true },
];

/**
 * Lit une métrique quelle que soit son orthographe.
 *
 * Renvoie `null` si le modèle a été entraîné sur 100 % des données : ses
 * champs `*_test` existent encore mais ne mesurent rien — ils valent 0 côté
 * NHL, et recopient les valeurs d'entraînement côté NBA. Afficher
 * « AUC 0,0000 » ou « AUC 0,9236 » laisserait croire à une mesure de
 * généralisation dans les deux cas.
 */
function metricValue(
  metrics: Record<string, number | string | boolean> | undefined,
  entry: (typeof HEADLINE)[number],
  inSample: boolean,
): number | null {
  if (!metrics) return null;
  const isTestMetric = entry.keys.some((k) => k.includes('test'));
  if (inSample && isTestMetric) return null;
  for (const k of entry.keys) {
    const v = Number(metrics[k]);
    if (Number.isFinite(v)) return v;
  }
  return null;
}

const ACTIONS: { key: WorkflowKey; label: string; sub: string; inputs?: Record<string, string> }[] = [
  {
    key: 'training',
    label: 'Lancer le réentraînement',
    sub: 'Pipeline hebdomadaire sur Kaggle',
  },
  {
    key: 'predictions',
    label: 'Recalculer les prédictions',
    sub: 'Cotes fraîches + value bets du jour',
    inputs: { sport: 'both' },
  },
  { key: 'web', label: 'Redéployer la PWA', sub: 'Build et mise en ligne' },
];

export function Admin() {
  const { showToast } = useToast();
  const [sport, setSport] = useState<Sport>('nhl');
  const [registry, setRegistry] = useState<ModelRegistryFile | null>(null);
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [gate, setGate] = useState<GateStatus | null>(null);
  const [perf, setPerf] = useState<PerformanceFile | null>(null);
  /** Deux lectures du même modèle : sa fiche, et ce qu'il vaut en vrai. */
  const [tab, setTab] = useState<'modele' | 'performance'>('modele');
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  const [compareDay, setCompareDay] = useState<string | null>(null);
  const [comparison, setComparison] = useState<ModelRegistryFile | null>(null);
  const [token, setToken] = useState(() => readToken());
  const [tokenDraft, setTokenDraft] = useState('');
  const [busy, setBusy] = useState<WorkflowKey | null>(null);

  const load = useCallback(async () => {
    try {
      setRegistry(await fetchModelRegistry());
      setRegistryError(null);
    } catch (e) {
      setRegistryError(e instanceof Error ? e.message : 'Registre introuvable');
    }
    try {
      setPerf(await fetchPerformance());
    } catch {
      // Publié par le job quotidien ; absent tant qu'il n'a pas tourné.
      setPerf(null);
    }
    try {
      setGate(await fetchGateStatus());
    } catch {
      // Publié par le workflow d'entraînement ; absent tant qu'il n'a pas
      // tourné depuis la mise en place. Rien à signaler à l'utilisateur.
      setGate(null);
    }
    try {
      setRuns(await listRuns(8, readToken() || undefined));
    } catch {
      setRuns([]);
    }
    try {
      setHistory(await listModelHistory(readToken() || undefined));
    } catch {
      setHistory([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!compareDay) {
      setComparison(null);
      return;
    }
    let alive = true;
    fetchModelRegistry(compareDay)
      .then((r) => alive && setComparison(r))
      .catch(() => alive && setComparison(null));
    return () => {
      alive = false;
    };
  }, [compareDay]);

  const model: ModelInfo | undefined = registry?.models?.[sport];
  const previous: ModelInfo | undefined = comparison?.models?.[sport];

  /** Marché de référence pour les métriques affichées. */
  const headlineMarket = useMemo(() => {
    const metrics = model?.metrics ?? {};
    return metrics.moneyline ? 'moneyline' : Object.keys(metrics)[0];
  }, [model]);

  const run = useCallback(
    async (key: WorkflowKey, inputs?: Record<string, string>) => {
      if (!token) {
        showToast('Ajoute un jeton GitHub pour déclencher les workflows');
        return;
      }
      setBusy(key);
      try {
        await dispatchWorkflow(key, token, 'main', inputs);
        showToast('Workflow déclenché');
        // GitHub met quelques secondes à faire apparaître le run.
        window.setTimeout(() => void load(), 4000);
      } catch (e) {
        showToast(e instanceof Error ? e.message : 'Déclenchement impossible');
      } finally {
        setBusy(null);
      }
    },
    [token, showToast, load],
  );

  return (
    <div className="vz-screen vz-up">
      <div className="vz-screen__head">
        <h1>Admin</h1>
        <button type="button" className="vz-btn vz-btn--sm" onClick={() => void load()}>
          <IconRefresh size={14} /> Rafraîchir
        </button>
      </div>
      <p className="vz-note">Pilotage des modèles et des données · {REPO}</p>

      <SegGroup label="Sport">
        {(Object.keys(SPORTS) as Sport[]).map((s) => (
          <SegButton key={s} active={sport === s} onClick={() => setSport(s)}>
            {SPORTS[s].label} · {SPORTS[s].league}
          </SegButton>
        ))}
      </SegGroup>

      <SegGroup label="Vue">
        <SegButton active={tab === 'modele'} onClick={() => setTab('modele')}>
          Modèle
        </SegButton>
        <SegButton active={tab === 'performance'} onClick={() => setTab('performance')}>
          Performance réelle
        </SegButton>
      </SegGroup>

      {tab === 'performance' ? (
        perf?.sports?.[sport] ? (
          <Performance data={perf.sports[sport]!} />
        ) : (
          <div className="vz-card">
            <p className="vz-note">
              Mesure indisponible pour ce sport. Elle est publiée une fois par jour
              par le job de prédictions, dans <code>performance/summary.json</code>.
            </p>
          </div>
        )
      ) : (
      <>
      {registryError && (
        <div className="vz-stopalert">
          <IconWarning size={18} />
          <div>
            <strong>Registre des modèles indisponible</strong>
            <small>
              {registryError} — il est publié par le job quotidien dans
              <code> models/registry.json</code>.
            </small>
          </div>
        </div>
      )}

      {model && (
        <div className="vz-card vz-card--rows">
          <div className="vz-row">
            <div className="vz-f1">
              <strong className="vz-admin__name">
                {model.name} <small>{model.model_version ?? '—'}</small>
              </strong>
              <small className="vz-note">
                {/*
                  `file_mtime` = le registre est antérieur à l'horodatage
                  d'entraînement, et la date lue est celle du fichier — donc
                  celle du dernier checkout, pas de l'entraînement. L'afficher
                  telle quelle annoncerait « entraîné il y a 2 minutes ».
                */}
                {!model.trained_at || model.trained_at_source === 'file_mtime'
                  ? 'Date d’entraînement inconnue — disponible au prochain entraînement'
                  : `Entraîné ${timeAgo(model.trained_at)} · ${formatShortDate(model.trained_at)}`}
                {model.n_games_train ? ` · ${model.n_games_train.toLocaleString('fr-FR')} matchs` : ''}
              </small>
            </div>
            <span className={`vz-admin__status${model.error ? ' is-err' : ''}`}>
              {model.error ? 'ERREUR' : 'EN PROD'}
            </span>
          </div>

          {model.trained_at_source === 'file_mtime' && (
            <p className="vz-note">
              Date déduite du fichier : ce modèle est antérieur à la publication de
              <code> trained_at</code>. Le prochain entraînement la renseignera.
            </p>
          )}

          {model.error ? (
            <p className="vz-mk__err">{model.error}</p>
          ) : (
            <>
              <div className="vz-admin__grid">
                <span>Métrique</span>
                <span>En prod</span>
                <span>{compareDay ?? 'Comparer'}</span>
              </div>
              {HEADLINE.map((m) => {
                const cur = metricValue(
                  model.metrics?.[headlineMarket],
                  m,
                  !!model.metrics_in_sample,
                );
                const old = metricValue(
                  previous?.metrics?.[headlineMarket],
                  m,
                  !!previous?.metrics_in_sample,
                );
                const hasCur = cur !== null;
                const hasOld = old !== null;
                const delta = hasCur && hasOld ? cur - old : null;
                const good = delta === null ? null : m.higherIsBetter ? delta > 0 : delta < 0;
                return (
                  <div className="vz-admin__grid vz-admin__row" key={m.keys[0]}>
                    <span>{m.label}</span>
                    <strong className="vz-num">
                      {hasCur ? formatNumber(cur, m.digits) : '—'}
                    </strong>
                    <span className="vz-num">
                      {hasOld ? formatNumber(old, m.digits) : '—'}
                      {delta !== null && Math.abs(delta) > 1e-9 && (
                        <small className={good ? 'is-up' : 'is-down'}>
                          {' '}
                          {delta > 0 ? '+' : '−'}
                          {formatNumber(Math.abs(delta), m.digits)}
                        </small>
                      )}
                    </span>
                  </div>
                );
              })}
              <p className="vz-note">
                Marché de référence : <strong>{headlineMarket ?? '—'}</strong> ·{' '}
                {model.n_markets ?? 0} marché(s) entraîné(s)
              </p>
              {model.metrics_in_sample && (
                <p className="vz-note">
                  Modèle de production : entraîné sur 100 % des matchs, donc sans jeu
                  de test. Les métriques hors échantillon sont masquées plutôt que
                  remplies avec les valeurs d’entraînement — c’est la barrière de
                  qualité, elle, qui évalue un modèle entraîné en mode split avant
                  d’autoriser le déploiement.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {history.length > 0 && (
        <>
          <SectionLabel>Comparer à une version publiée</SectionLabel>
          <div className="vz-chiprow vz-sc">
            <Chip small active={compareDay === null} onClick={() => setCompareDay(null)}>
              Aucune
            </Chip>
            {history.slice(0, 8).map((d) => (
              <Chip key={d} small active={compareDay === d} onClick={() => setCompareDay(d)}>
                {d}
              </Chip>
            ))}
          </div>
        </>
      )}

      {gate && (
        <>
          <SectionLabel>Barrière de qualité</SectionLabel>
          <div className="vz-card vz-card--rows">
            <div className="vz-row">
              <div className="vz-f1">
                <strong className="vz-admin__name">
                  {gate.passed ? 'Dernier entraînement accepté' : 'Déploiement refusé'}
                </strong>
                <small className="vz-note">
                  Vérifié {timeAgo(gate.checked_at)}
                  {gate.run_number ? ` · run #${gate.run_number}` : ''}
                </small>
              </div>
              <span className={`vz-tx__ic ${gate.passed ? 'is-up' : 'is-down'}`}>
                {gate.passed ? <IconCheck size={14} /> : <IconX size={13} />}
              </span>
            </div>
            {Object.entries(gate.blocked).map(([blockedSport, why]) => (
              <div className="vz-row" key={blockedSport}>
                <div className="vz-f1">
                  <strong>{blockedSport}</strong>
                  <small className="vz-note">{why.headline ?? why.cause ?? 'cause inconnue'}</small>
                </div>
              </div>
            ))}
            <p className="vz-note">
              {gate.passed
                ? 'Aucun marché sous son plancher d’AUC : les modèles entraînés ont été déployés.'
                : 'Les modèles concernés n’ont pas été déployés ; ceux des autres sports l’ont été.'}
            </p>
          </div>
        </>
      )}

      <SectionLabel>Actions</SectionLabel>
      {!token && (
        <div className="vz-card vz-card--rows">
          <p className="vz-note">
            Les actions déclenchent des workflows GitHub Actions. Colle un
            <strong> fine-grained token</strong> avec la permission <em>Actions :
            read & write</em> sur <code>{REPO}</code>. Il reste sur cet appareil.
          </p>
          <div className="vz-row vz-gap">
            <input
              className="vz-input vz-f1"
              type="password"
              placeholder="github_pat_…"
              value={tokenDraft}
              onChange={(e) => setTokenDraft(e.target.value)}
              aria-label="Jeton GitHub"
            />
            <button
              type="button"
              className="vz-btn vz-btn--primary"
              disabled={!tokenDraft.trim()}
              onClick={() => {
                writeToken(tokenDraft);
                setToken(tokenDraft.trim());
                setTokenDraft('');
                showToast('Jeton enregistré localement');
                void load();
              }}
            >
              Enregistrer
            </button>
          </div>
        </div>
      )}

      <div className="vz-admin__actions">
        {ACTIONS.map((a) => (
          <button
            key={a.key}
            type="button"
            className="vz-admin__action"
            disabled={!token || busy !== null}
            onClick={() => void run(a.key, a.inputs)}
          >
            <strong>{busy === a.key ? 'Déclenchement…' : a.label}</strong>
            <small>{a.sub}</small>
          </button>
        ))}
      </div>

      {token && (
        <button
          type="button"
          className="vz-btn vz-btn--sm vz-btn--ghost vz-btn--block"
          onClick={() => {
            writeToken('');
            setToken('');
            showToast('Jeton supprimé de cet appareil');
          }}
        >
          Oublier le jeton GitHub
        </button>
      )}

      </>
      )}

      <SectionLabel>Journal des exécutions</SectionLabel>
      {runs.length === 0 ? (
        <p className="vz-note vz-note--center">
          Aucun run lisible. L'API GitHub limite à 60 requêtes/h sans jeton.
        </p>
      ) : (
        <div className="vz-stack">
          {runs.map((r) => {
            const ok = r.conclusion === 'success';
            const failed = r.conclusion === 'failure' || r.conclusion === 'cancelled';
            return (
              <a
                key={r.id}
                className="vz-tx"
                href={r.url}
                target="_blank"
                rel="noreferrer noopener"
              >
                <span className={`vz-tx__ic ${ok ? 'is-up' : failed ? 'is-down' : ''}`}>
                  {ok ? <IconCheck size={14} /> : failed ? <IconX size={13} /> : <IconRefresh size={14} />}
                </span>
                <span className="vz-f1">
                  <strong className="vz-ellipsis">{r.name}</strong>
                  <small>
                    {r.workflow} · {timeAgo(r.createdAt)} ·{' '}
                    {r.status === 'completed' ? (r.conclusion ?? '—') : r.status}
                  </small>
                </span>
                <IconDownload size={14} />
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
