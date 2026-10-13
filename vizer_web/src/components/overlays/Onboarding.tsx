import { useState } from 'react';
import { CURRENCIES, CURRENCY_CODES, toBase, type CurrencyCode } from '../../lib/currency';
import { SPORTS, type Sport } from '../../types/model';
import { IconBall, IconBolt, IconChartAxis, IconCurrency, IconPuck } from '../Icons';
import { VizerMark } from '../Shell';

export interface OnboardingResult {
  currency: CurrencyCode;
  bankroll: number;
  defaultSport: Sport;
}

const DEFAULT_BANKROLL: Record<CurrencyCode, number> = { FCFA: 100000, EUR: 150, USD: 150 };
const CHIPS: Record<CurrencyCode, number[]> = {
  FCFA: [50000, 100000, 250000, 500000],
  EUR: [50, 100, 250, 500],
  USD: [50, 100, 250, 500],
};

/** Tunnel d'accueil en 4 étapes : présentation, devise, bankroll, sport. */
export function Onboarding({ onFinish }: { onFinish: (r: OnboardingResult) => void }) {
  const [step, setStep] = useState(0);
  const [currency, setCurrency] = useState<CurrencyCode>('FCFA');
  const [amount, setAmount] = useState<number>(DEFAULT_BANKROLL.FCFA);
  const [sport, setSport] = useState<Sport>('nhl');

  const last = step === 3;

  return (
    <div className="vz-ob">
      <div className="vz-ob__top">
        <VizerMark size={52} />
        <div className="vz-ob__dots">
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className={i <= step ? 'is-on' : ''} style={{ width: i === step ? 22 : 7 }} />
          ))}
        </div>
      </div>

      <div className="vz-ob__body vz-sc">
        {step === 0 && (
          <div className="vz-up">
            <h2>Vizer, ton radar à value bets</h2>
            <p className="vz-ob__lead">
              Des prédictions par modèle sur le hockey et le basket, les paris à valeur
              ajoutée détectés pour toi, et un suivi complet de ta bankroll.
            </p>
            <div className="vz-stack">
              <Feature
                icon={<IconBolt size={20} />}
                tone="accent"
                title="Value bets détectés"
                text="Quand la cote d'un book dépasse la proba du modèle, Vizer te signale l'edge."
              />
              <Feature
                icon={<IconChartAxis size={20} />}
                tone="value"
                title="Prédictions par modèle"
                text="Probabilités, totaux, BTTS et marchés de période sur chaque match."
              />
              <Feature
                icon={<IconCurrency size={20} />}
                tone="accent"
                title="Bankroll & rentabilité"
                text="Suis tes paris, ton ROI, ta courbe de bankroll et sache si tu es rentable."
              />
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="vz-up">
            <h2>Choisis ta devise</h2>
            <p className="vz-ob__lead">
              Tous les montants de l'app seront affichés dans cette devise.
            </p>
            <div className="vz-ob__cur">
              {CURRENCY_CODES.map((c) => (
                <button
                  key={c}
                  type="button"
                  className={currency === c ? 'is-active' : ''}
                  onClick={() => {
                    setCurrency(c);
                    setAmount(DEFAULT_BANKROLL[c]);
                  }}
                >
                  <strong>{CURRENCIES[c].symbol}</strong>
                  <small>{CURRENCIES[c].name}</small>
                </button>
              ))}
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="vz-up">
            <h2>Ta bankroll de départ</h2>
            <p className="vz-ob__lead">
              Le capital que tu consacres aux paris. Tu pourras l'ajuster à tout moment.
            </p>
            <div className="vz-amount">
              <input
                type="number"
                inputMode="numeric"
                min={0}
                value={amount}
                onChange={(e) => setAmount(Math.max(0, Number(e.target.value)))}
                aria-label="Bankroll de départ"
              />
              <span>{CURRENCIES[currency].suffix.trim()}</span>
            </div>
            <div className="vz-chiprow vz-sc">
              {CHIPS[currency].map((a) => (
                <button
                  key={a}
                  type="button"
                  className={`vz-chip${amount === a ? ' is-active' : ''}`}
                  onClick={() => setAmount(a)}
                >
                  {a.toLocaleString('fr-FR').replace(/ | /g, ' ')}{' '}
                  {CURRENCIES[currency].suffix.trim()}
                </button>
              ))}
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="vz-up">
            <h2>Ton sport favori</h2>
            <p className="vz-ob__lead">Vizer l'ouvrira en premier à chaque lancement.</p>
            <div className="vz-stack">
              {(Object.keys(SPORTS) as Sport[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`vz-ob__sport${sport === s ? ' is-active' : ''}`}
                  onClick={() => setSport(s)}
                >
                  <span
                    className="vz-ob__sportIc"
                    style={{ ['--tab-color' as string]: `var(${SPORTS[s].colorVar})` }}
                  >
                    {s === 'nhl' ? <IconPuck size={26} /> : <IconBall size={24} />}
                  </span>
                  <span className="vz-f1">
                    <strong>{SPORTS[s].label}</strong>
                    <small>
                      {SPORTS[s].league} ·{' '}
                      {s === 'nhl'
                        ? 'Ligue nationale de hockey'
                        : 'National Basketball Association'}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="vz-ob__foot">
        {step > 0 && (
          <button type="button" className="vz-btn vz-btn--ghost" onClick={() => setStep((s) => s - 1)}>
            ‹
          </button>
        )}
        <button
          type="button"
          className="vz-btn vz-btn--primary vz-f1"
          disabled={step === 2 && !(amount > 0)}
          onClick={() => {
            if (!last) setStep((s) => s + 1);
            else
              onFinish({
                currency,
                bankroll: toBase(amount, currency),
                defaultSport: sport,
              });
          }}
        >
          {last ? 'Commencer' : 'Continuer'}
        </button>
      </div>
    </div>
  );
}

function Feature({
  icon,
  title,
  text,
  tone,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
  tone: 'accent' | 'value';
}) {
  return (
    <div className="vz-ob__feat">
      <span className={`vz-ob__featIc vz-ob__featIc--${tone}`}>{icon}</span>
      <div>
        <strong>{title}</strong>
        <small>{text}</small>
      </div>
    </div>
  );
}
