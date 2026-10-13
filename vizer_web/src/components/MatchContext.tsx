import { IconChartAxis, IconH2H, IconInfo } from './Icons';
import { MiniBar } from './Primitives';
import { readableAccent } from '../lib/contrast';
import { formatShortDate } from '../lib/format';
import { useSettings } from '../context/SettingsContext';
import { teamColor, teamName } from '../data/teams';
import type { Factor, Game, HeadToHead, TeamForm } from '../types/model';

/**
 * Forme récente · confrontations directes · facteurs du modèle.
 *
 * Les trois blocs ne s'affichent que si le backend publie la donnée
 * correspondante — la PWA n'invente aucun historique.
 */

const PILL: Record<string, { label: string; color: string }> = {
  W: { label: 'V', color: 'var(--value)' },
  L: { label: 'D', color: 'var(--danger)' },
  D: { label: 'N', color: 'var(--text-muted)' },
};

function record(form: TeamForm, sport: Game['sport']): string {
  // Un « nul » NHL vient d'un match décidé aux tirs au but : les données
  // Moneypuck s'arrêtent à la prolongation.
  return sport === 'nhl'
    ? `${form.wins} V · ${form.draws} TAB · ${form.losses} D`
    : `${form.wins} V · ${form.losses} D`;
}

export function RecentForm({ game }: { game: Game }) {
  const form = game.form;
  if (!form || (!form.home && !form.away)) return null;

  const rows = [
    { code: game.home, name: game.homeName, form: form.home },
    { code: game.away, name: game.awayName, form: form.away },
  ].filter((r) => r.form);

  return (
    <section className="vz-mk">
      <header className="vz-mk__head">
        <h3>
          <IconChartAxis size={14} /> Forme récente · 5 derniers
        </h3>
      </header>
      <div className="vz-form">
        {rows.map((r) => (
          <div className="vz-form__row" key={r.code}>
            <div className="vz-f1">
              <strong className="vz-ellipsis">{r.name}</strong>
              <small>{record(r.form as TeamForm, game.sport)}</small>
            </div>
            <div className="vz-form__pills">
              {(r.form as TeamForm).results.map((res, i) => (
                <span
                  key={i}
                  className="vz-form__pill"
                  style={{ ['--pill' as string]: PILL[res].color }}
                >
                  {PILL[res].label}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function HeadToHeadCard({ game }: { game: Game }) {
  const { resolvedTheme } = useSettings();
  if (game.h2h.length === 0) return null;
  return (
    <section className="vz-mk">
      <header className="vz-mk__head">
        <h3>
          <IconH2H size={14} /> Confrontations directes
        </h3>
      </header>
      <ul className="vz-h2h">
        {game.h2h.map((h: HeadToHead) => {
          const winnerCode = h.winner === 'home' ? game.home : h.winner === 'away' ? game.away : null;
          // Les couleurs officielles très sombres (TOR marine) sont illisibles
          // en texte : on les remonte au contraste AA, la pastille garde la
          // teinte exacte.
          const raw = winnerCode ? teamColor(game.sport, winnerCode) : null;
          const dot = raw ?? 'var(--text-dim)';
          const color = raw ? readableAccent(raw, resolvedTheme) : 'var(--text-dim)';
          return (
            <li key={`${h.date}-${h.home}-${h.away}`}>
              <i style={{ background: dot }} />
              <span className="vz-f1 vz-num">
                {h.home} {h.homeScore}–{h.awayScore} {h.away}
              </span>
              <span className="vz-h2h__date">{formatShortDate(h.date)}</span>
              <strong style={{ color }}>
                {winnerCode ?? '—'}
              </strong>
            </li>
          );
        })}
      </ul>
      <p className="vz-mk__note vz-mk__note--plain">
        La pastille colorée indique le vainqueur.
      </p>
    </section>
  );
}

export function FactorsCard({ game }: { game: Game }) {
  if (game.factors.length === 0) return null;

  const max = Math.max(...game.factors.map((f) => Math.abs(f.contribution)));
  const favoured = (f: Factor) => (f.direction === 'home' ? game.home : game.away);

  return (
    <section className="vz-mk">
      <header className="vz-mk__head">
        <h3>
          <IconInfo size={14} /> Pourquoi cette prédiction
        </h3>
      </header>
      <p className="vz-mk__sub">
        Les {game.factors.length} facteurs qui pèsent le plus, mesurés sur le modèle
        lui-même (contributions SHAP).
      </p>

      <div className="vz-factors">
        {game.factors.map((f) => {
          const code = favoured(f);
          const color = teamColor(game.sport, code);
          return (
            <div className="vz-factor" key={f.feature}>
              <div className="vz-factor__head">
                <span className="vz-factor__team" style={{ background: color }}>
                  {code}
                </span>
                <div className="vz-f1">
                  <strong>{f.label}</strong>
                  <small>
                    en faveur de {teamName(game.sport, code)}
                    {f.value !== null && ` · valeur ${f.value}`}
                  </small>
                </div>
                <span className="vz-num vz-factor__impact">
                  {f.contribution > 0 ? '+' : '−'}
                  {Math.abs(f.contribution).toFixed(3)}
                </span>
              </div>
              <MiniBar ratio={Math.abs(f.contribution) / max} color={color} height={6} />
            </div>
          );
        })}
      </div>
    </section>
  );
}
