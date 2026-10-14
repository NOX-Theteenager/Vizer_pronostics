/**
 * Normalisation des deux schémas backend vers le modèle de vue unique.
 *
 * Seule couche qui connaît les formes brutes. Volontairement tolérante : un
 * marché manquant, en erreur ou inconnu n'empêche jamais l'affichage du reste.
 */
import {
  marketLabel,
  marketRank,
  marketShortLabel,
  outcomeLabel,
  selectionLabel,
} from '../data/markets';
import { teamColor, teamName } from '../data/teams';
import type {
  Book,
  Confidence,
  Factor,
  Game,
  HeadToHead,
  TeamForm,
  MarketView,
  Outcome,
  Sport,
  SportFeed,
  TalentRow,
  TeamTotalRow,
  ValueBet,
} from './model';
import { SPORT_KEYS } from './model';
import type {
  RawContext,
  RawFeed,
  RawForm,
  RawMarketError,
  RawNbaFeed,
  RawNbaGame,
  RawNbaTeamTotal,
  RawNbaValueBet,
  RawNhlFeed,
  RawNhlGame,
  RawNhlMarket,
  RawNhlValueBet,
} from './raw';

/* ── Helpers ───────────────────────────────────────────────────────────── */

function isMarketError(m: unknown): m is RawMarketError {
  return !!m && typeof m === 'object' && typeof (m as RawMarketError).error === 'string';
}

function gameId(sport: Sport, home: string, away: string, commenceTime: string): string {
  return `${sport}-${away}@${home}-${commenceTime ? commenceTime.slice(0, 10) : 'na'}`;
}

/** L'issue la plus probable passe en pleine opacité. */
function markStrongest(outcomes: Outcome[]): Outcome[] {
  if (!outcomes.length) return outcomes;
  const max = Math.max(...outcomes.map((o) => o.probability));
  return outcomes.map((o) => ({ ...o, strong: o.strong ?? o.probability === max }));
}

/** Forme, confrontations et facteurs — mêmes champs pour les deux sports. */
function normalizeContext(raw: RawContext): Pick<Game, 'form' | 'h2h' | 'factors'> {
  const mapForm = (f: RawForm | null | undefined): TeamForm | null =>
    f
      ? {
          results: (f.results ?? []).map((r) => (r === 'W' || r === 'L' ? r : 'D')),
          wins: Number(f.wins) || 0,
          draws: Number(f.draws) || 0,
          losses: Number(f.losses) || 0,
          goalsFor: Number(f.goals_for) || 0,
          goalsAgainst: Number(f.goals_against) || 0,
        }
      : null;

  const h2h: HeadToHead[] = (raw.h2h ?? []).map((h) => ({
    date: h.date,
    home: h.home,
    away: h.away,
    homeScore: Number(h.home_score) || 0,
    awayScore: Number(h.away_score) || 0,
    winner: h.winner ?? null,
  }));

  const factors: Factor[] = (raw.factors ?? [])
    .filter((f) => Number.isFinite(Number(f.contribution)))
    .map((f) => ({
      feature: f.feature,
      label: f.label,
      value: f.value === null || f.value === undefined ? null : Number(f.value),
      contribution: Number(f.contribution),
      direction: f.direction === 'home' ? 'home' : 'away',
    }));

  const form = raw.form
    ? { home: mapForm(raw.form.home), away: mapForm(raw.form.away) }
    : undefined;

  return { ...(form ? { form } : {}), h2h, factors };
}

function normalizeBooks(books: { name: string; odds: number; best: boolean }[] | undefined): Book[] {
  return (books ?? [])
    .filter((b) => Number.isFinite(Number(b.odds)) && Number(b.odds) > 1)
    .map((b) => ({ name: String(b.name), odds: Number(b.odds), best: !!b.best }));
}

/* ── Value bets ────────────────────────────────────────────────────────── */

/**
 * Une seule forme publiée depuis l'unification de `value_finder.py` :
 * `predicted_proba` / `kelly_stake` / `implied_proba`, des deux côtés.
 *
 * Les archives antérieures portent les anciens noms NBA
 * (`predicted_probability`, `kelly_stake_fraction`, `implied_probability`) et
 * restent lisibles : l'écran Historique remonte à plusieurs semaines.
 */
function normalizeValueBet(
  sport: Sport,
  gid: string,
  home: string,
  away: string,
  commenceTime: string,
  raw: RawNhlValueBet | RawNbaValueBet,
): ValueBet | null {
  const odds = Number(raw.bookmaker_odds);
  if (!Number.isFinite(odds) || odds <= 1) return null;

  const predicted = Number(
    (raw as RawNhlValueBet).predicted_proba ?? (raw as RawNbaValueBet).predicted_probability,
  );
  if (!Number.isFinite(predicted)) return null;

  const kelly = Number(
    (raw as RawNhlValueBet).kelly_stake ?? (raw as RawNbaValueBet).kelly_stake_fraction,
  );
  const implied = Number(
    (raw as RawNbaValueBet).implied_proba ??
      (raw as RawNbaValueBet).implied_probability ??
      1 / odds,
  );
  const edge = Number(raw.edge);

  return {
    id: `${gid}#${raw.market}#${raw.selection}`,
    sport,
    gameId: gid,
    home,
    away,
    commenceTime,
    market: raw.market,
    marketLabel: marketShortLabel(raw.market),
    selection: raw.selection,
    selectionLabel: selectionLabel(sport, raw.market, raw.selection, home, away),
    selectionShort: outcomeLabel(sport, raw.market, raw.selection, home, away),
    predictedProba: predicted,
    bookmakerOdds: odds,
    impliedProba: Number.isFinite(implied) ? implied : 1 / odds,
    edge: Number.isFinite(edge) ? edge : predicted - 1 / odds,
    kellyStake: Number.isFinite(kelly) ? kelly : 0,
    confidence: (raw.confidence ?? 'low') as Confidence,
    books: normalizeBooks(raw.books),
  };
}

/* ── NHL ───────────────────────────────────────────────────────────────── */

function nhlMarket(key: string, raw: RawNhlMarket, home: string, away: string): MarketView {
  const sport: Sport = 'nhl';
  const outcomes: Outcome[] = Object.entries(raw.probabilities ?? {}).map(([k, p]) => ({
    key: k,
    label: outcomeLabel(sport, key, k, home, away),
    probability: Number(p) || 0,
    color:
      k === 'home' || k === 'home_lead'
        ? teamColor(sport, home)
        : k === 'away' || k === 'away_lead'
          ? teamColor(sport, away)
          : k === 'yes'
            ? 'var(--value)'
            : undefined,
  }));

  // Le score exact arrive déjà trié par proba ; les intervalles gardent leur
  // ordre de bucket, qui est signifiant (0-2 → 9+).
  const ordered = key === 'exact_score' ? outcomes.slice(0, 5) : outcomes;

  const view: MarketView = {
    key,
    label: marketLabel(key, sport),
    kind: 'bars',
    outcomes: markStrongest(ordered),
    confidence: raw.confidence,
  };

  // Ligne de la cote dans le libellé des totaux : « TOTAL BUTS · O/U 5.5 »
  const line = Object.keys(raw.probabilities ?? {})
    .map((k) => /^over_(.+)$/.exec(k)?.[1])
    .find(Boolean);
  if (line) view.label = `${view.label} · O/U ${line}`;

  const ev = raw.expected_value;
  if (ev !== null && ev !== undefined && Number.isFinite(Number(ev))) {
    view.hero = {
      value: Number(ev),
      unit: key === 'p1_total' ? 'buts (1ʳᵉ période)' : 'buts attendus',
      decimals: 2,
      inline: true,
    };
  }

  // La mention « non pariable » n'est plus posée ici : c'est une décision
  // révisable depuis l'Admin, pas une propriété de la prédiction. Elle est
  // appliquée à l'affichage, avec la politique en vigueur.

  return view;
}

function normalizeNhlGame(raw: RawNhlGame): Game {
  const sport: Sport = 'nhl';
  const home = String(raw.home ?? '');
  const away = String(raw.away ?? '');
  const commenceTime = String(raw.commence_time ?? '');
  const gid = gameId(sport, home, away, commenceTime);

  const markets: MarketView[] = Object.entries(raw.predictions ?? {})
    .map(([key, entry]) =>
      isMarketError(entry)
        ? ({
            key,
            label: marketLabel(key, sport),
            kind: 'bars',
            outcomes: [],
            error: entry.error,
          } satisfies MarketView)
        : nhlMarket(key, entry, home, away),
    )
    .sort((a, b) => marketRank(sport, a.key) - marketRank(sport, b.key));

  const ml = markets.find((m) => m.key === 'moneyline' && !m.error);
  const total = markets.find((m) => m.key === 'total' && !m.error);
  const btts = markets.find((m) => m.key === 'btts' && !m.error);

  const chips: string[] = [];
  if (total?.hero) chips.push(`E[buts] ${total.hero.value.toFixed(1)}`);
  const bttsYes = btts?.outcomes.find((o) => o.key === 'yes')?.probability;
  if (bttsYes !== undefined) chips.push(`BTTS ${Math.round(bttsYes * 100)} %`);

  const valueBets = (raw.value_bets ?? [])
    .map((vb) => normalizeValueBet(sport, gid, home, away, commenceTime, vb))
    .filter((vb): vb is ValueBet => vb !== null)
    .sort((a, b) => b.edge - a.edge);

  return {
    id: gid,
    sport,
    home,
    away,
    homeName: teamName(sport, home),
    awayName: teamName(sport, away),
    homeColor: teamColor(sport, home),
    awayColor: teamColor(sport, away),
    commenceTime,
    homeWinProba: ml?.outcomes.find((o) => o.key === 'home')?.probability,
    awayWinProba: ml?.outcomes.find((o) => o.key === 'away')?.probability,
    chips,
    markets,
    valueBets,
    // Le feed NHL vient de l'Odds API : les cotes sont toujours là.
    hasOdds: true,
    ...normalizeContext(raw),
    ...(markets.length === 0 ? { error: 'Prédictions indisponibles pour ce match.' } : {}),
  };
}

/* ── NBA ───────────────────────────────────────────────────────────────── */

function teamTotalRow(code: string, raw: RawNbaTeamTotal): TeamTotalRow {
  const line = Number(raw.line_default);
  const over = Number(raw.over_default_proba);
  return {
    team: code,
    teamName: teamName('nba', code),
    prediction: Number(raw.prediction),
    ...(Number.isFinite(line) ? { line } : {}),
    ...(Number.isFinite(over) ? { overProba: over } : {}),
  };
}

function normalizeNbaGame(raw: RawNbaGame): Game {
  const sport: Sport = 'nba';
  const home = String(raw.home ?? '');
  const away = String(raw.away ?? '');
  const commenceTime = String(raw.commence_time ?? '');
  const gid = gameId(sport, home, away, commenceTime);
  const p = raw.predictions ?? {};
  const markets: MarketView[] = [];

  if (p.win) {
    markets.push({
      key: 'win',
      label: marketLabel('win', sport),
      kind: 'bars',
      outcomes: markStrongest([
        {
          key: 'home',
          label: teamName(sport, home),
          probability: Number(p.win.home_win_proba),
          color: teamColor(sport, home),
        },
        {
          key: 'away',
          label: teamName(sport, away),
          probability: Number(p.win.away_win_proba),
          color: teamColor(sport, away),
        },
      ]),
    });
  }

  if (p.total && Number.isFinite(Number(p.total.prediction))) {
    markets.push({
      key: 'total',
      label: marketLabel('total', sport),
      kind: 'hero',
      outcomes: [],
      hero: { value: Number(p.total.prediction), unit: 'points prédits', decimals: 1 },
    });
  }

  const teamTotals: TeamTotalRow[] = [];
  if (p.home_team_total) teamTotals.push(teamTotalRow(home, p.home_team_total));
  if (p.away_team_total) teamTotals.push(teamTotalRow(away, p.away_team_total));
  if (teamTotals.length) {
    markets.push({
      key: 'team_totals',
      label: marketLabel('team_totals', sport),
      kind: 'teamTotals',
      outcomes: [],
      teamTotals,
    });
  }

  const talent = p.talent
    ? { home: Number(p.talent.home_ratio), away: Number(p.talent.away_ratio) }
    : undefined;

  if (talent) {
    const rows: TalentRow[] = [
      { team: home, teamName: teamName(sport, home), ratio: talent.home },
      { team: away, teamName: teamName(sport, away), ratio: talent.away },
    ];
    markets.push({
      key: 'talent',
      label: marketLabel('talent', sport),
      kind: 'talent',
      outcomes: [],
      talent: rows,
      note: '1.00 = effectif complet · < 1 = joueurs majeurs absents',
    });
  }

  const chips: string[] = [];
  if (p.total && Number.isFinite(Number(p.total.prediction))) {
    chips.push(`Total ${Number(p.total.prediction).toFixed(1)} pts`);
  }

  const valueBets = (raw.value_bets ?? [])
    .map((vb) => normalizeValueBet(sport, gid, home, away, commenceTime, vb))
    .filter((vb): vb is ValueBet => vb !== null)
    .sort((a, b) => b.edge - a.edge);

  return {
    id: gid,
    sport,
    home,
    away,
    homeName: teamName(sport, home),
    awayName: teamName(sport, away),
    homeColor: teamColor(sport, home),
    awayColor: teamColor(sport, away),
    commenceTime,
    homeWinProba: p.win ? Number(p.win.home_win_proba) : undefined,
    awayWinProba: p.win ? Number(p.win.away_win_proba) : undefined,
    chips,
    markets,
    valueBets,
    hasOdds: raw.has_odds !== false,
    talent,
    ...normalizeContext(raw),
    ...(p.error ? { error: p.error } : {}),
  };
}

/* ── Entrées publiques ─────────────────────────────────────────────────── */

function feedMeta<G>(sport: Sport, raw: RawFeed<G>, games: Game[]): SportFeed {
  return {
    sport,
    generatedAt: raw.generated_at ?? null,
    modelsTrainedAt: raw.models_trained_at ?? null,
    modelVersion: raw.model_version ?? null,
    games: games.sort(
      (a, b) => new Date(a.commenceTime).getTime() - new Date(b.commenceTime).getTime(),
    ),
    // Tableau vide plutôt qu'absent : les archives d'avant le garde-fou ne
    // portent pas le champ, et l'appelant n'a pas à distinguer les deux cas.
    withheldMarkets: (raw.withheld_markets ?? []).filter(
      (w) => w && typeof w.market === 'string',
    ),
    ...(raw.message ? { message: raw.message } : {}),
    ...(raw.detection_source ? { detectionSource: raw.detection_source } : {}),
  };
}

export function normalizeFeed(sport: Sport, raw: unknown): SportFeed {
  if (!raw || typeof raw !== 'object') {
    return {
      sport,
      generatedAt: null,
      modelsTrainedAt: null,
      modelVersion: null,
      games: [],
      withheldMarkets: [],
      message: 'no games',
    };
  }
  return sport === 'nhl'
    ? feedMeta('nhl', raw as RawNhlFeed, ((raw as RawNhlFeed).games ?? []).map(normalizeNhlGame))
    : feedMeta('nba', raw as RawNbaFeed, ((raw as RawNbaFeed).games ?? []).map(normalizeNbaGame));
}

/** Tous les value bets des deux sports, triés par edge décroissant. */
export function allValueBets(feeds: Record<Sport, SportFeed | null>): ValueBet[] {
  return SPORT_KEYS.flatMap((s) => feeds[s]?.games.flatMap((g) => g.valueBets) ?? []).sort(
    (a, b) => b.edge - a.edge,
  );
}

/** Tous les matchs des deux sports (recherche globale). */
export function allGames(feeds: Record<Sport, SportFeed | null>): Game[] {
  return SPORT_KEYS.flatMap((s) => feeds[s]?.games ?? []);
}
