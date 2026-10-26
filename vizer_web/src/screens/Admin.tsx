import { useCallback, useEffect, useMemo, useState } from 'react';
import { Chip, SectionLabel, SegButton, SegGroup } from '../components/Primitives';
import { marketShortLabel } from '../data/markets';
import { HealthBanner } from '../components/HealthBanner';
import { IconCheck, IconDownload, IconRefresh, IconWarning, IconX } from '../components/Icons';
import { useToast } from '../context/ToastContext';
import { Performance } from '../components/Performance';
import { useData } from '../context/DataContext';
import { policyKey, savePolicy } from '../lib/marketPolicy';
import type {
  DirectionFile,
  FreshnessFile,
  PerformanceFile,
} from '../types/performance';
import {
  fetchDirection,
  fetchFreshness,
  fetchGateStatus,
  fetchModelRegistry,
  fetchPerformance,
  type GateMetric,
  type GateStatus,
  type GateVerdict,
  type ModelInfo,
  type ModelRegistryFile,
} from '../lib/api';
import { formatNumber, formatShortDate, timeAgo } from '../lib/format';
import {
  dispatchWorkflow,
  fetchRuns,
  GH_AVAILABLE,
  readAdminKey,
  REPO,
  writeAdminKey,
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
/**
 * Chiffres de diagnostic, repliés derrière « Détails techniques ».
 *
 * Ils décrivent la fabrication du modèle, pas sa qualité : la température de
 * calibration et le nombre de features n'aident à aucune décision, et les
 * afficher au même rang que les mesures de performance oblige à trier à
 * chaque lecture.
 */
const TECH: { key: string; label: string; digits: number }[] = [
  { key: 'n_features', label: 'Features utilisées', digits: 0 },
  { key: 'temperature', label: 'Température de calibration', digits: 3 },
  { key: 'n_train', label: 'Matchs d’entraînement', digits: 0 },
];

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

/**
 * Règle d'écriture tenue ici : **le verdict d'abord, puis une phrase qui dit
 * ce que le chiffre signifie en matchs ou en buts.** Un AUC de 0,6083 ne dit
 * rien à personne ; « sur deux matchs au hasard, il place le vainqueur devant
 * le perdant 61 fois sur 100 » dit exactement la même chose et se lit.
 *
 * La phrase dépend du marché, pas seulement de la métrique. Plusieurs marchés
 * partagent le moteur de buts du `total` et sont donc jugés sur l'erreur de
 * total — écrire « il se trompe de 1,87 but » sous « Les deux marquent »
 * serait exact sur le chiffre et faux sur le sens.
 */

/** Ce que l'erreur moyenne mesure, pour ce marché. */
const MAE_SUBJECT: Record<string, string> = {
  total: 'le total de buts d’un match',
  p1_total: 'le total de la première période',
  home_team_total: 'les buts de l’équipe à domicile',
  away_team_total: 'les buts de l’équipe à l’extérieur',
};

/** Marchés jugés sur l'erreur du total parce qu'ils en partagent le moteur. */
const SHARES_TOTAL_ENGINE = new Set(['btts', 'exact_score', 'goal_intervals', 'p1_btts']);

function plainMetric(market: string, m: GateMetric): string {
  const pct = (x: number) => Math.round(x * 100);
  switch (m.label) {
    case 'AUC':
      // Lecture exacte de l'AUC, pas une analogie : c'est la probabilité que
      // le modèle classe un vainqueur au-dessus d'un perdant tirés au hasard.
      return `Sur deux matchs au hasard, il place le vainqueur devant le perdant `
        + `${pct(m.value)} fois sur 100. En dessous de ${pct(m.bound)} sur 100, `
        + `le déploiement est refusé.`;
    case 'MAE': {
      const subject = MAE_SUBJECT[market];
      if (subject) {
        return `Il se trompe en moyenne de ${formatNumber(m.value, 2)} but sur `
          + `${subject}. La limite est à ${formatNumber(m.bound, 2)}.`;
      }
      if (SHARES_TOTAL_ENGINE.has(market)) {
        return `Jugé sur le moteur de buts qu’il partage avec le total : `
          + `${formatNumber(m.value, 2)} but d’erreur moyenne, limite `
          + `${formatNumber(m.bound, 2)}. Ce marché n’a pas de mesure propre.`;
      }
      return `Erreur moyenne ${formatNumber(m.value, 2)}, limite `
        + `${formatNumber(m.bound, 2)}.`;
    }
    case 'R²':
      return m.value >= 0
        ? `Il explique ${pct(m.value)} % de l’écart d’un match à l’autre ; `
          + `au-dessous de ${pct(m.bound)} %, autant annoncer la moyenne.`
        : `Il fait un peu moins bien que d’annoncer toujours la moyenne. C’est `
          + `attendu sur un total de buts — presque tout y est irréductible — et `
          + `la limite est posée en négatif pour l’accepter sans le laisser empirer.`;
    default:
      return `${m.label} ${formatNumber(m.value, 3)} · limite `
        + `${formatNumber(m.bound, 3)}.`;
  }
}

/**
 * Ce que vaut le modèle sur des matchs qu'il n'a pas vus.
 *
 * Les seules mesures de généralisation du pipeline. Le modèle déployé est
 * entraîné sur 100 % des matchs et n'en porte aucune — pendant longtemps cet
 * écran affichait donc une grille de cinq tirets suivie d'un paragraphe
 * expliquant pourquoi elle était vide. Ces chiffres existaient : la barrière
 * de qualité évalue un modèle entraîné avec jeu de test réservé, et son
 * verdict était jeté à chaque entraînement réussi.
 */
function GateDetail({
  verdict,
  previous,
  previousDay,
}: {
  verdict: GateVerdict;
  previous?: GateVerdict | null;
  previousDay?: string | null;
}) {
  const checks = (verdict.checks ?? []).filter((c) => (c.metrics ?? []).length > 0);
  if (!checks.length) return null;

  const before = new Map(
    (previous?.checks ?? []).map((c) => [
      c.market,
      new Map((c.metrics ?? []).map((m) => [m.label, m.value])),
    ]),
  );

  return (
    <>
      <SectionLabel>Ce que vaut le modèle sur des matchs qu’il n’a pas vus</SectionLabel>
      <div className="vz-card vz-card--rows">
        <p className="vz-note">
          Mesuré sur <strong>{(verdict.n_test ?? 0).toLocaleString('fr-FR')} matchs</strong>{' '}
          mis de côté avant l’entraînement. C’est la seule mesure qui dise si le modèle
          généralise : le modèle en service, lui, a vu tous les matchs.
        </p>
        {checks.map((c) => (
          <div className="vz-perf__row" key={c.market}>
            <span className="vz-f1">
              <strong>{marketShortLabel(c.market)}</strong>
              {(c.metrics ?? []).map((m) => {
                const old = before.get(c.market)?.get(m.label);
                return (
                  <small className="vz-note vz-dir" key={m.label}>
                    {m.ok ? '' : '⚠️ '}
                    {plainMetric(c.market, m)}
                    {old !== undefined && <Trend metric={m} previous={old} day={previousDay} />}
                  </small>
                );
              })}
            </span>
            <span className={`vz-tx__ic ${c.verdict === 'pass' ? 'is-up' : 'is-down'}`}>
              {c.verdict === 'pass' ? <IconCheck size={14} /> : <IconX size={13} />}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

/**
 * Évolution depuis une version précédente, en mots.
 *
 * « +0,0078 » ne dit pas si c'est bien. Le sens de la métrique le dit, et il
 * est publié avec elle (`higher_is_better`) — on ne le redevine pas ici.
 */
function Trend({
  metric,
  previous,
  day,
}: {
  metric: GateMetric;
  previous: number;
  day?: string | null;
}) {
  const delta = metric.value - previous;
  if (Math.abs(delta) < 1e-6) {
    return (
      <span className="vz-trend">
        {' '}
        · inchangé depuis {day ?? 'la version précédente'}
      </span>
    );
  }
  const better = metric.higher_is_better ? delta > 0 : delta < 0;
  return (
    <span className={`vz-trend ${better ? 'is-up' : 'is-down'}`}>
      {' '}
      · {better ? 'mieux' : 'moins bien'} que le {day ?? 'précédent'}{' '}
      ({formatNumber(previous, 3)} → {formatNumber(metric.value, 3)})
    </span>
  );
}

export function Admin() {
  const { showToast } = useToast();
  const { policy, reloadPolicy } = useData();
  const [sport, setSport] = useState<Sport>('nhl');
  const [registry, setRegistry] = useState<ModelRegistryFile | null>(null);
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [gate, setGate] = useState<GateStatus | null>(null);
  const [perf, setPerf] = useState<PerformanceFile | null>(null);
  /** Sens des paris par marché — se lit collé au rendement, cf. Performance. */
  const [direction, setDirection] = useState<DirectionFile | null>(null);
  /** Les données d'entraînement suivent-elles la saison ? Première ligne du
      bandeau d'état, et le défaut le plus coûteux qu'il ait à montrer. */
  const [freshness, setFreshness] = useState<FreshnessFile | null>(null);
  const [policyBusy, setPolicyBusy] = useState(false);
  /** Deux lectures du même modèle : sa fiche, et ce qu'il vaut en vrai. */
  const [tab, setTab] = useState<'modele' | 'performance'>('modele');
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  const [compareDay, setCompareDay] = useState<string | null>(null);
  /**
   * Verdict d'une version antérieure, pour comparer.
   *
   * On compare les **verdicts de la barrière** et non les registres : le
   * registre du modèle déployé ne porte aucune métrique hors échantillon, donc
   * la comparaison d'avant mettait des tirets en face de tirets.
   */
  const [comparisonGate, setComparisonGate] = useState<GateStatus | null>(null);
  const [adminKey, setAdminKey] = useState(() => readAdminKey());
  const [keyDraft, setKeyDraft] = useState('');
  /** Le serveur a-t-il un jeton GitHub ? Décide du message sur le quota. */
  const [ghAuthenticated, setGhAuthenticated] = useState(true);
  const [runsError, setRunsError] = useState<string | null>(null);
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
      setDirection(await fetchDirection());
    } catch {
      // Idem. Son absence ne doit pas masquer le reste de l'écran : le
      // rendement s'affiche alors sans son contexte directionnel, ce qui
      // était la situation d'avant.
      setDirection(null);
    }
    try {
      setFreshness(await fetchFreshness());
    } catch {
      // Publié par le job quotidien. Son absence vaut « non vérifié », pas
      // « tout va bien » : le bandeau le dit ainsi.
      setFreshness(null);
    }
    try {
      setGate(await fetchGateStatus());
    } catch {
      // Publié par le workflow d'entraînement ; absent tant qu'il n'a pas
      // tourné depuis la mise en place. Rien à signaler à l'utilisateur.
      setGate(null);
    }
    // Un seul appel : le serveur fait les deux lectures en parallèle et rend
    // ce qu'il a pu obtenir.
    try {
      const payload = await fetchRuns(8);
      setRuns(payload.runs);
      setHistory(payload.history);
      setGhAuthenticated(payload.authenticated);
      setRunsError(payload.error);
    } catch (e) {
      setRuns([]);
      setHistory([]);
      setRunsError(e instanceof Error ? e.message : 'GitHub injoignable');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!compareDay) {
      setComparisonGate(null);
      return;
    }
    let alive = true;
    fetchGateStatus(compareDay)
      .then((r) => alive && setComparisonGate(r))
      // Les jours antérieurs à l'archivage du verdict n'en ont pas : on
      // n'affiche alors pas de comparaison, plutôt qu'un zéro trompeur.
      .catch(() => alive && setComparisonGate(null));
    return () => {
      alive = false;
    };
  }, [compareDay]);

  const model: ModelInfo | undefined = registry?.models?.[sport];

  /** Marché de référence pour les métriques affichées. */
  const headlineMarket = useMemo(() => {
    const metrics = model?.metrics ?? {};
    return metrics.moneyline ? 'moneyline' : Object.keys(metrics)[0];
  }, [model]);

  /**
   * Bascule un marché, puis renvoie la politique complète au serveur.
   *
   * On applique localement d'abord : l'interrupteur doit répondre tout de
   * suite. En cas d'échec, on recharge depuis le serveur plutôt que de laisser
   * l'écran afficher un état qui n'existe nulle part.
   */
  const toggleMarket = useCallback(
    (market: string, bettable: boolean) => {
      if (!adminKey) return;
      const next = { ...policy, [policyKey(sport, market)]: bettable };
      setPolicyBusy(true);
      void savePolicy(adminKey, next).then(async (error) => {
        if (error) showToast(error);
        else showToast(bettable ? 'Marché proposé à nouveau' : 'Marché écarté des paris');
        await reloadPolicy();
        setPolicyBusy(false);
      });
    },
    [adminKey, policy, sport, showToast, reloadPolicy],
  );

  const run = useCallback(
    async (key: WorkflowKey, inputs?: Record<string, string>) => {
      if (!adminKey) {
        showToast('Ajoute la clé d’administration pour déclencher les workflows');
        return;
      }
      setBusy(key);
      try {
        await dispatchWorkflow(key, adminKey, 'main', inputs);
        showToast('Workflow déclenché');
        // GitHub met quelques secondes à faire apparaître le run.
        window.setTimeout(() => void load(), 4000);
      } catch (e) {
        showToast(e instanceof Error ? e.message : 'Déclenchement impossible');
      } finally {
        setBusy(null);
      }
    },
    [adminKey, showToast, load],
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

      {/* Avant tout le reste, et avant même le choix du sport : l'état du
          système ne dépend pas de l'onglet qu'on regarde. */}
      <HealthBanner freshness={freshness} gate={gate} direction={direction} />

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
          <Performance
            sport={sport}
            data={perf.sports[sport]!}
            direction={direction?.sports?.[sport]}
            policy={policy}
            busy={policyBusy}
            onToggle={adminKey ? toggleMarket : null}
          />
        ) : (
          <div className="vz-card">
            <p className="vz-note">
              Rien à mesurer encore pour ce sport : il faut des prédictions publiées
              <em> puis</em> des matchs joués. La mesure apparaît d’elle-même, une
              fois par jour, dès que les deux existent.
            </p>
          </div>
        )
      ) : (
      <>
      {registryError && (
        <div className="vz-stopalert">
          <IconWarning size={18} />
          <div>
            <strong>Fiche des modèles illisible</strong>
            <small>
              {registryError}. Les prédictions, elles, peuvent continuer d’être
              publiées — c’est seulement cette fiche qui manque. Elle est réécrite
              à chaque publication quotidienne.
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
              Ce modèle est antérieur à l’enregistrement des dates d’entraînement :
              celle affichée est celle du fichier, pas de l’entraînement. Le prochain
              réentraînement la corrigera — rien à faire.
            </p>
          )}

          {model.error ? (
            <p className="vz-mk__err">{model.error}</p>
          ) : (
            <p className="vz-note">
              {model.n_markets ?? 0} marché(s) entraîné(s). Ce qu’il vaut se lit
              juste en dessous, sur des matchs qu’il n’a pas vus.
            </p>
          )}

          {/*
            Replié, et c'est volontaire. Version du modèle, nombre de features,
            température de calibration : utiles pour diagnostiquer, inutiles
            pour décider. Les laisser en évidence force à trier à chaque
            lecture, et trier à chaque lecture finit par ne plus rien lire.
          */}
          <details className="vz-tech">
            <summary>Détails techniques</summary>
            <div className="vz-tech__body">
              {TECH.map((t) => {
                const raw = model.metrics?.[headlineMarket]?.[t.key];
                const value = Number(raw);
                if (!Number.isFinite(value)) return null;
                return (
                  <div className="vz-tech__row" key={t.key}>
                    <span className="vz-f1">{t.label}</span>
                    <strong className="vz-num">{formatNumber(value, t.digits)}</strong>
                  </div>
                );
              })}
              <div className="vz-tech__row">
                <span className="vz-f1">Version du modèle</span>
                <strong>{model.model_version ?? '—'}</strong>
              </div>
              <div className="vz-tech__row">
                <span className="vz-f1">Marché de référence</span>
                <strong>{headlineMarket ? marketShortLabel(headlineMarket) : '—'}</strong>
              </div>
              <p className="vz-note">
                Le modèle en service est entraîné sur 100 % des matchs : ses champs
                « test » existent mais ne mesurent rien. Ils ne sont donc pas
                affichés ici — c’est la section suivante qui porte les vraies
                mesures.
              </p>
            </div>
          </details>
        </div>
      )}

      {gate?.verdicts?.[sport] && (
        <GateDetail
          verdict={gate.verdicts[sport]!}
          previous={comparisonGate?.verdicts?.[sport] ?? null}
          previousDay={compareDay}
        />
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
      {!GH_AVAILABLE ? (
        <div className="vz-card">
          <p className="vz-note">
            Les actions passent par les fonctions du déploiement, absentes ici
            (développement local ou GitHub Pages).
          </p>
        </div>
      ) : (
        <>
          {!adminKey && (
            <div className="vz-card vz-card--rows">
              <p className="vz-note">
                Les actions déclenchent des workflows GitHub Actions. Le jeton GitHub
                ne passe plus par le navigateur : il vit dans les variables
                d’environnement du déploiement. Ce qu’on colle ici est la{' '}
                <strong>clé d’administration</strong> (<code>VIZER_ADMIN_SECRET</code>),
                qui n’autorise que les trois workflows ci-dessous et n’a aucune valeur
                ailleurs.
              </p>
              <div className="vz-row vz-gap">
                <input
                  className="vz-input vz-f1"
                  type="password"
                  placeholder="Clé d’administration"
                  value={keyDraft}
                  onChange={(e) => setKeyDraft(e.target.value)}
                  aria-label="Clé d’administration"
                  autoComplete="off"
                />
                <button
                  type="button"
                  className="vz-btn vz-btn--primary"
                  disabled={!keyDraft.trim()}
                  onClick={() => {
                    writeAdminKey(keyDraft);
                    setAdminKey(keyDraft.trim());
                    setKeyDraft('');
                    showToast('Clé enregistrée sur cet appareil');
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
                disabled={!adminKey || busy !== null}
                onClick={() => void run(a.key, a.inputs)}
              >
                <strong>{busy === a.key ? 'Déclenchement…' : a.label}</strong>
                <small>{a.sub}</small>
              </button>
            ))}
          </div>

          {adminKey && (
            <button
              type="button"
              className="vz-btn vz-btn--sm vz-btn--ghost vz-btn--block"
              onClick={() => {
                writeAdminKey('');
                setAdminKey('');
                showToast('Clé supprimée de cet appareil');
              }}
            >
              Oublier la clé d’administration
            </button>
          )}
        </>
      )}

      </>
      )}

      <SectionLabel>Journal des exécutions</SectionLabel>
      {runs.length === 0 ? (
        <p className="vz-note vz-note--center">
          {runsError ??
            (ghAuthenticated
              ? 'Aucun run récent.'
              : 'Aucun run lisible. Sans VIZER_GITHUB_TOKEN sur le déploiement, l’API GitHub limite à 60 requêtes/h par IP.')}
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
