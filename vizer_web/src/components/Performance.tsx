import { marketShortLabel } from '../data/markets';
import { isBettable, type MarketPolicy } from '../lib/marketPolicy';
import { Switch } from './Primitives';
import { formatNumber } from '../lib/format';
import type { Sport } from '../types/model';
import type {
  BetPerformance,
  CalibrationBucket,
  DirectionVerdict,
  LevelPerformance,
  SportPerformance,
} from '../types/performance';

/**
 * Ce que valent réellement les prédictions publiées.
 *
 * Règle tenue partout dans ce composant : **jamais un taux sans son
 * effectif.** Un chiffre seul invite à conclure ; « 57 % sur 28 paris » dit
 * aussi qu'il ne faut pas conclure. Les marchés sous le seuil d'échantillon
 * ne sont pas masqués — on affiche l'effectif atteint, qui est l'information
 * utile pour savoir quand revenir.
 */

/**
 * Nom lisible d'un côté de pari.
 *
 * `away`, `under`, `home_lead` sont les clés du modèle. Elles traversaient
 * l'écran telles quelles, y compris dans des phrases destinées à être lues.
 */
const SIDE_LABEL: Record<string, string> = {
  home: 'domicile',
  away: 'extérieur',
  over: 'au-dessus de la ligne',
  under: 'en dessous de la ligne',
  yes: 'oui',
  no: 'non',
  tied: 'égalité',
};

function sideLabel(side: string | null | undefined): string {
  if (!side) return '—';
  return SIDE_LABEL[side] ?? side;
}

/**
 * « X fois sur Y », plutôt qu'un taux.
 *
 * 0,122 ne se lit pas ; « 1 fois sur 8 » se lit. Pour les taux proches de la
 * moitié on garde une base de 10, qui reste plus parlante que « 1 fois sur 2 »
 * quand la valeur est 0,56.
 */
function timesOutOf(rate: number): string {
  if (rate <= 0) return 'jamais';
  if (rate >= 1) return 'à chaque fois';
  if (rate < 0.25) return `1 fois sur ${Math.round(1 / rate)}`;
  return `${Math.round(rate * 10)} fois sur 10`;
}

/**
 * Un mot de verdict avant le chiffre.
 *
 * Règle tenue partout dans cet écran : on ne demande pas au lecteur de savoir
 * si 0,49 de Brier est bon. L'effectif décide d'abord — en dessous du seuil
 * d'échantillon, aucun verdict n'est permis, et le dire est l'information
 * utile.
 */
function verdictWord(kind: 'roi' | 'sample', value: number, n: number): {
  word: string;
  level: '' | 'is-up' | 'is-warn' | 'is-down';
} {
  if (kind === 'sample') {
    return n >= 30
      ? { word: 'mesuré', level: '' }
      : { word: 'trop peu de matchs', level: 'is-warn' };
  }
  // Un rendement se juge contre zéro, et son incertitude est large : ±8 points
  // sur 150 paris. On ne proclame donc « rentable » qu'au-delà de 5 %.
  if (n < 30) return { word: 'pas assez de paris', level: 'is-warn' };
  if (value > 0.05) return { word: 'rentable', level: 'is-up' };
  if (value > -0.05) return { word: 'à l’équilibre', level: '' };
  return { word: 'perdant', level: 'is-down' };
}


/**
 * Sens des paris d'un marché.
 *
 * Posé délibérément **collé au rendement**, et non dans une section à part.
 * Le `total` NHL affichait +11,6 % sur 28 paris et ce chiffre a servi à le
 * réactiver ; ses 39 paris étaient tous des `under`. Un marché qui ne parie
 * jamais de l'autre côté ne produit pas n paris indépendants, il produit un
 * pari directionnel joué n fois — et un ROI vu seul ne le dit pas.
 */
function Direction({ v }: { v: DirectionVerdict }) {
  if (v.status === 'insufficient') return null;
  const sides = Object.entries(v.counts).sort((a, b) => b[1] - a[1]);
  const tone =
    v.status === 'withheld' ? 'is-down' : v.status === 'imbalanced' ? 'is-warn' : '';
  return (
    <small className={`vz-note vz-dir ${tone}`}>
      {v.status === 'withheld' ? '🛑 ' : v.status === 'imbalanced' ? '⚠️ ' : ''}
      {sides.map(([side, n]) => `${n} ${sideLabel(side)}`).join(' · ')}
      {v.status !== 'ok' ? ` — ${v.reason}` : ''}
    </small>
  );
}

/** Pourcentage signé, teinté selon qu'il est favorable ou non. */
function Signed({ value, digits = 1 }: { value: number; digits?: number }) {
  const positive = value > 0;
  return (
    <strong className={`vz-num ${positive ? 'is-up' : value < 0 ? 'is-down' : ''}`}>
      {positive ? '+' : ''}
      {formatNumber(value * 100, digits)} %
    </strong>
  );
}

/**
 * Courbe de calibration : la mesure la plus informative du lot.
 *
 * Elle répond à « quand le modèle annonce 70 %, est-ce que ça arrive 70 % du
 * temps ? ». Un modèle peut être souvent juste et mal calibré — et c'est la
 * calibration, pas la justesse, qui décide si une probabilité peut servir à
 * calculer une mise.
 */
function Calibration({ buckets }: { buckets: CalibrationBucket[] }) {
  if (!buckets.length) return null;
  return (
    <div className="vz-calib">
      {buckets.map((b) => {
        const predicted = (b.from + b.to) / 2;
        const gap = b.actual - predicted;
        return (
          <div className="vz-calib__row" key={`${b.from}`}>
            <span className="vz-calib__band vz-num">
              {Math.round(b.from * 100)}–{Math.round(b.to * 100)} %
            </span>
            <span className="vz-calib__track">
              {/* Repère du prédit, barre du réalisé : l'écart entre les deux
                  est ce qu'on vient lire. */}
              <i className="vz-calib__target" style={{ left: `${predicted * 100}%` }} />
              <i className="vz-calib__fill" style={{ width: `${b.actual * 100}%` }} />
            </span>
            <span className="vz-calib__out vz-num">
              {Math.round(b.actual * 100)} %
              <small className={Math.abs(gap) < 0.05 ? '' : 'is-warn'}>
                {gap >= 0 ? '+' : '−'}
                {Math.round(Math.abs(gap) * 100)}
              </small>
            </span>
            <small className="vz-calib__n">n={b.n}</small>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Une ligne de marché : son rendement, et l'interrupteur juste à côté.
 *
 * Les deux sont volontairement collés. Décider d'écarter un marché sans voir
 * son chiffre, ou lire son chiffre sans pouvoir agir, c'est la même perte de
 * temps — le but de cet écran est que la décision suive la mesure.
 */
function BetRow({
  label,
  bets,
  direction,
  toggle,
}: {
  label: string;
  bets: BetPerformance;
  direction?: DirectionVerdict;
  toggle?: { on: boolean; busy: boolean; onChange: (v: boolean) => void; label: string };
}) {
  const insufficient = bets.insufficient || bets.roi_flat === undefined;
  const roi = bets.roi_flat ?? 0;
  const verdict = direction?.status === 'withheld'
    ? { word: 'non interprétable', level: 'is-down' as const }
    : verdictWord('roi', roi, bets.n);
  return (
    <div className="vz-perf__row">
      <span className="vz-f1">
        <strong>{label}</strong>
        <small className="vz-note">
          {insufficient
            ? `${bets.n} pari(s) suivis — il en faut une trentaine pour conclure`
            : `${bets.won} gagnés sur ${bets.n}. Pour 1 € misé sur chacun, `
              + `${roi >= 0 ? 'il en revient' : 'il en manque'} `
              + `${formatNumber(Math.abs(roi), 2)} €.`}
        </small>
        {direction ? <Direction v={direction} /> : null}
      </span>
      {!insufficient && (
        <span className="vz-perf__roi">
          {/* Barré quand le marché est retenu : le chiffre reste lisible, mais
              on ne peut plus le prendre pour une mesure de sélection. */}
          <span className={direction?.status === 'withheld' ? 'vz-dir__struck' : undefined}>
            <Signed value={roi} />
          </span>
          <small className={verdict.level}>{verdict.word}</small>
        </span>
      )}
      {toggle && (
        <Switch
          checked={toggle.on}
          disabled={toggle.busy}
          onChange={toggle.onChange}
          label={toggle.label}
        />
      )}
    </div>
  );
}

/**
 * Décalage de niveau des prédictions ponctuelles.
 *
 * La grandeur qui manquait, et qu'il a fallu calculer à la main pour voir que
 * le marché `total` du NHL annonçait 5,73 buts pour 6,05 marqués. Un ROI ne
 * dit pas de quel côté corriger ; un Brier non plus. Ce tableau, oui.
 */
function Levels({ levels }: { levels: Record<string, LevelPerformance> }) {
  const rows = Object.entries(levels).filter(([, l]) => !l.insufficient && l.bias !== undefined);
  const waiting = Object.entries(levels).filter(([, l]) => l.insufficient);
  if (!rows.length && !waiting.length) return null;
  return (
    <>
      <h3 className="vz-seclabel">Niveau des prédictions chiffrées</h3>
      <div className="vz-card vz-card--rows">
        {rows.map(([key, l]) => {
          // Au-delà de deux erreurs-types, le décalage n'est plus
          // attribuable au hasard — en dessous, il ne faut rien en conclure.
          const solid = l.z !== null && l.z !== undefined && Math.abs(l.z) >= 2;
          return (
            <div className="vz-perf__row" key={key}>
              <span className="vz-f1">
                <strong>{marketShortLabel(key)}</strong>
                <small className="vz-note">
                  annonce {formatNumber(l.mean_predicted ?? 0, 2)} · observé{' '}
                  {formatNumber(l.mean_actual ?? 0, 2)} · sur {l.n} matchs
                </small>
              </span>
              <span className="vz-perf__roi">
                <strong className={`vz-num ${solid ? 'is-down' : ''}`}>
                  {(l.bias ?? 0) > 0 ? '+' : '−'}
                  {formatNumber(Math.abs(l.bias ?? 0), 2)}
                </strong>
                <small>
                  {l.z === null || l.z === undefined
                    ? 'écart'
                    : `${formatNumber(Math.abs(l.z), 1)} σ`}
                </small>
              </span>
            </div>
          );
        })}
        {waiting.map(([key, l]) => (
          <div className="vz-perf__row" key={key}>
            <span className="vz-f1">
              <strong>{marketShortLabel(key)}</strong>
              <small className="vz-note">{l.n} matchs — pas assez pour conclure</small>
            </span>
          </div>
        ))}
        <p className="vz-note">
          Écart entre ce que le modèle annonce et ce qui arrive, en unités du marché
          (buts, points). Négatif = il annonce moins que la réalité. La colonne σ
          compte les erreurs-types qui séparent cet écart de zéro :{' '}
          <strong>en dessous de 2, il n’y a rien à conclure</strong>. C’est la mesure
          qui dit de quel côté corriger — un rendement ou un score de Brier ne le
          diront jamais.
        </p>
      </div>
    </>
  );
}

export function Performance({
  sport,
  data,
  direction,
  policy,
  onToggle,
  busy,
}: {
  sport: Sport;
  data: SportPerformance;
  /** Verdicts directionnels par marché ; absent tant que le job n'a pas tourné. */
  direction?: DirectionVerdict[];
  policy: MarketPolicy;
  /** `null` quand l'utilisateur n'a pas de clé d'administration. */
  onToggle: ((market: string, bettable: boolean) => void) | null;
  busy: boolean;
}) {
  const verdicts = new Map((direction ?? []).map((v) => [v.market, v]));
  const withheld = (direction ?? []).filter((v) => v.status === 'withheld');
  const markets = Object.entries(data.markets).sort(
    (a, b) => (b[1].n ?? 0) - (a[1].n ?? 0),
  );
  const moneyline = data.markets.moneyline ?? data.markets.win;

  if (data.n_games_settled === 0) {
    return (
      <div className="vz-card">
        <p className="vz-note">
          Aucun match prédit puis joué pour ce sport. La mesure démarrera dès que
          des prédictions auront été publiées et les scores connus.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="vz-card vz-card--rows">
        <div className="vz-row">
          <div className="vz-f1">
            <strong className="vz-admin__name">{data.n_games_settled} matchs mesurés</strong>
            <small className="vz-note">
              du {data.from} au {data.to} · prédits avant le coup d’envoi, confrontés au
              score réel
            </small>
          </div>
        </div>
        <p className="vz-note">
          Ces chiffres ne disent pas comment <em>vous</em> vous en sortez — c’est
          l’écran Historique — mais si le modèle a raison, sur toutes ses
          prédictions, y compris celles que personne n’a suivies.
        </p>
      </div>

      {moneyline?.calibration?.length ? (
        <>
          <h3 className="vz-seclabel">Calibration du vainqueur</h3>
          <div className="vz-card">
            <Calibration buckets={moneyline.calibration} />
            <p className="vz-note">
              Barre = fréquence réelle, repère = probabilité annoncée. Collées, le
              modèle dit vrai ; écartées, ses probabilités sont biaisées et les mises
              calculées dessus le sont aussi.
            </p>
          </div>
        </>
      ) : null}

      <h3 className="vz-seclabel">Justesse par marché</h3>
      <div className="vz-card vz-card--rows">
        {markets.map(([key, m]) => (
          <div className="vz-perf__row" key={key}>
            <span className="vz-f1">
              <strong>{marketShortLabel(key)}</strong>
              <small className="vz-note">
                {m.insufficient || m.accuracy === undefined
                  ? `${m.n} matchs mesurés — il en faut une trentaine pour conclure`
                  : `Son issue la plus probable se produit ${timesOutOf(m.accuracy)}, `
                    + `sur ${m.n} matchs.`}
              </small>
            </span>
            {!m.insufficient && m.accuracy !== undefined && (
              <span className="vz-perf__roi">
                <strong className="vz-num">{formatNumber(m.accuracy * 100, 0)} %</strong>
                <small className={verdictWord('sample', 0, m.n).level}>
                  {verdictWord('sample', 0, m.n).word}
                </small>
              </span>
            )}
          </div>
        ))}
        <p className="vz-note">
          Un marché à beaucoup d’issues possibles — le score exact en a des dizaines —
          tombe juste rarement sans être mauvais pour autant : il y a simplement plus
          de façons de se tromper. Comparer deux marchés sur ce chiffre n’a donc pas
          de sens ; comparer un marché à lui-même d’une semaine sur l’autre, oui.
        </p>
      </div>

      {data.levels ? <Levels levels={data.levels} /> : null}

      <h3 className="vz-seclabel">Rendement des value bets</h3>
      <div className="vz-card vz-card--rows">
        <BetRow label="Tous marchés" bets={data.value_bets} />
        {Object.entries(data.value_bets_by_market).map(([key, bets]) => (
          <BetRow
            key={key}
            label={marketShortLabel(key)}
            bets={bets}
            direction={verdicts.get(key)}
            toggle={
              onToggle
                ? {
                    on: isBettable(policy, sport, key),
                    busy,
                    label: `Proposer les paris ${marketShortLabel(key)}`,
                    onChange: (v) => onToggle(key, v),
                  }
                : undefined
            }
          />
        ))}
        {onToggle && (
          <p className="vz-note">
            L’interrupteur ne coupe que ce qui vous est <em>proposé</em>. Le modèle
            continue de prédire et la mesure de tourner — sinon vous deviendriez
            aveugle sur le marché que vous surveillez justement pour savoir quand
            le rouvrir.
          </p>
        )}
        <p className="vz-note">
          Rendement si chaque value bet publié avait été joué d’une unité, aux cotes
          réelles enregistrées au moment de la publication. C’est la mesure qui décide
          quels marchés valent la peine — et elle est indépendante de ce que vous avez
          effectivement suivi.
        </p>
        {withheld.length > 0 && (
          <p className="vz-note">
            🛑 <strong>{withheld.map((v) => marketShortLabel(v.market)).join(', ')}</strong>{' '}
            {withheld.length > 1 ? 'ne parient' : 'ne parie'} jamais de l’autre côté.
            Leurs paris du sens dominant ne sont plus proposés — les prédictions, elles,
            continuent d’être publiées et mesurées. Un seul pari à contre-courant suffit
            à lever la retenue : c’est précisément la preuve qui manque.
          </p>
        )}
      </div>
    </>
  );
}
