import { marketShortLabel } from '../data/markets';
import { isBettable, type MarketPolicy } from '../lib/marketPolicy';
import { Switch } from './Primitives';
import { formatNumber } from '../lib/format';
import type { Sport } from '../types/model';
import type {
  BetPerformance,
  CalibrationBucket,
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
  toggle,
}: {
  label: string;
  bets: BetPerformance;
  toggle?: { on: boolean; busy: boolean; onChange: (v: boolean) => void; label: string };
}) {
  const insufficient = bets.insufficient || bets.roi_flat === undefined;
  return (
    <div className="vz-perf__row">
      <span className="vz-f1">
        <strong>{label}</strong>
        <small className="vz-note">
          {insufficient
            ? `${bets.n} pari(s) — pas assez pour conclure`
            : `${bets.won}/${bets.n} gagnés · edge moyen ${formatNumber((bets.avg_edge ?? 0) * 100, 1)} %`}
        </small>
      </span>
      {!insufficient && (
        <span className="vz-perf__roi">
          <Signed value={bets.roi_flat!} />
          <small>mise plate</small>
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

export function Performance({
  sport,
  data,
  policy,
  onToggle,
  busy,
}: {
  sport: Sport;
  data: SportPerformance;
  policy: MarketPolicy;
  /** `null` quand l'utilisateur n'a pas de clé d'administration. */
  onToggle: ((market: string, bettable: boolean) => void) | null;
  busy: boolean;
}) {
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
        <div className="vz-perf__head">
          <span className="vz-f1">Marché</span>
          <span>n</span>
          <span>Justesse</span>
          <span>Brier</span>
        </div>
        {markets.map(([key, m]) => (
          <div className="vz-perf__grid" key={key}>
            <span className="vz-f1">{marketShortLabel(key)}</span>
            <span className="vz-num">{m.n}</span>
            {m.insufficient || m.accuracy === undefined ? (
              <span className="vz-note" style={{ gridColumn: 'span 2' }}>
                échantillon insuffisant
              </span>
            ) : (
              <>
                <strong className="vz-num">{formatNumber(m.accuracy * 100, 1)} %</strong>
                <span className="vz-num">{formatNumber(m.brier ?? 0, 3)}</span>
              </>
            )}
          </div>
        ))}
        <p className="vz-note">
          La justesse compte les fois où l’issue la plus probable s’est produite. Un
          marché à beaucoup d’issues (score exact) a mécaniquement une justesse basse
          sans être mauvais : le Brier, lui, est comparable d’un marché à l’autre —
          plus il est bas, mieux c’est.
        </p>
      </div>

      <h3 className="vz-seclabel">Rendement des value bets</h3>
      <div className="vz-card vz-card--rows">
        <BetRow label="Tous marchés" bets={data.value_bets} />
        {Object.entries(data.value_bets_by_market).map(([key, bets]) => (
          <BetRow
            key={key}
            label={marketShortLabel(key)}
            bets={bets}
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
      </div>
    </>
  );
}
