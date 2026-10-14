/**
 * Auto-test de la couche d'intégration : on compile les modules purs avec
 * esbuild (fourni par Vite), puis on les exécute sur les échantillons réels
 * de public/mock/. Aucune dépendance de test à installer.
 *
 * Usage : node scripts/selftest.mjs
 */
import { build } from 'esbuild';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

let failures = 0;
function check(label, cond, detail = '') {
  if (cond) {
    console.log(`  ✓ ${label}`);
  } else {
    failures += 1;
    console.error(`  ✗ ${label}${detail ? ` — ${detail}` : ''}`);
  }
}

const entry = `
export { normalizeFeed, allValueBets, allGames } from './src/types/normalize.ts';
export { formatMoney, formatPnl, toBase, toDisplay } from './src/lib/currency.ts';
export { computeProfit, computeBreakdown, bankrollSeries, curveGeometry } from './src/lib/stats.ts';
export { followMarkets } from './src/lib/follow.ts';
export { marketFamily } from './src/data/markets.ts';
export { kellyStake, KELLY_CAP } from './src/lib/kelly.ts';
export { normalizeResults } from './src/types/results.ts';
export { settleSelection, settleBet, resultIndex, matchKey, findResult } from './src/lib/settle.ts';
`;

const out = await build({
  stdin: { contents: entry, resolveDir: root, loader: 'ts' },
  bundle: true,
  write: false,
  format: 'esm',
  platform: 'node',
  target: 'node20',
  logLevel: 'silent',
});

const mod = await import(
  `data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`
);

const nhlRaw = JSON.parse(readFileSync(path.join(root, 'public/mock/nhl.json'), 'utf8'));
const nbaRaw = JSON.parse(readFileSync(path.join(root, 'public/mock/nba.json'), 'utf8'));

console.log('\n── Normalisation NHL ──');
const nhl = mod.normalizeFeed('nhl', nhlRaw);
check('3 matchs', nhl.games.length === 3, `reçu ${nhl.games.length}`);
const torMtl = nhl.games.find((g) => g.home === 'TOR');
check('8 marchés sur TOR–MTL', torMtl.markets.length === 8, `reçu ${torMtl.markets.length}`);
check('ordre canonique : moneyline en tête', torMtl.markets[0].key === 'moneyline');
check('P(home) = 45,3 %', Math.abs(torMtl.homeWinProba - 0.453) < 1e-9);
check(
  'total NHL marqué non pariable',
  torMtl.markets.find((m) => m.key === 'total').note?.includes('non pariable'),
);
check(
  'ligne O/U dans le libellé du total',
  torMtl.markets.find((m) => m.key === 'total').label === 'TOTAL BUTS · O/U 5.5',
);
check(
  'score exact tronqué au top 5',
  torMtl.markets.find((m) => m.key === 'exact_score').outcomes.length === 5,
);
check(
  'intervalles dans l’ordre des buckets',
  torMtl.markets.find((m) => m.key === 'goal_intervals').outcomes[0].key === '0-2',
);
const vbNhl = torMtl.valueBets[0];
check('value bet NHL lu (predicted_proba)', Math.abs(vbNhl.predictedProba - 0.547) < 1e-9);
check('kelly NHL lu (kelly_stake)', Math.abs(vbNhl.kellyStake - 0.022) < 1e-9);
check('implicite recalculée', Math.abs(vbNhl.impliedProba - 1 / 2.15) < 1e-9);

console.log('\n── Normalisation NBA ──');
const nba = mod.normalizeFeed('nba', nbaRaw);
check('2 matchs', nba.games.length === 2);
const lal = nba.games.find((g) => g.home === 'LAL');
check('total NBA en « points »', lal.markets.find((m) => m.key === 'total').label === 'TOTAL POINTS');
check('totaux par équipe fusionnés', lal.markets.find((m) => m.key === 'team_totals').teamTotals.length === 2);
check('talent présent', !!lal.markets.find((m) => m.key === 'talent'));
const vbNba = lal.valueBets[0];
check('value bet NBA lu (predicted_proba)', Math.abs(vbNba.predictedProba - 0.582) < 1e-9);
check('kelly NBA lu (kelly_stake)', Math.abs(vbNba.kellyStake - 0.015) < 1e-9);
// Les archives publiées avant l'unification portent les anciens noms : la PWA
// doit continuer à les lire, sinon l'écran Historique perd ses value bets.
const legacyFeed = mod.normalizeFeed('nba', {
  games: [{
    home: 'LAL', away: 'BOS', commence_time: '2026-10-12T23:00Z',
    predictions: { win: { home_win_proba: 0.55, away_win_proba: 0.45 } },
    value_bets: [{
      market: 'win', selection: 'home', predicted_probability: 0.55,
      bookmaker_odds: 2.1, implied_probability: 0.476, edge: 0.074,
      kelly_stake_fraction: 0.02, confidence: 'medium',
    }],
  }],
});
const legacyVb = legacyFeed.games[0].valueBets[0];
check('ancien nom predicted_probability encore lu', Math.abs(legacyVb.predictedProba - 0.55) < 1e-9);
check('ancien nom kelly_stake_fraction encore lu', Math.abs(legacyVb.kellyStake - 0.02) < 1e-9);
check('implicite NBA lue telle quelle', Math.abs(vbNba.impliedProba - 0.5236) < 1e-9);
const gsw = nba.games.find((g) => g.home === 'GSW');
check('has_odds=false propagé', gsw.hasOdds === false);
check('aucun value bet sans cotes', gsw.valueBets.length === 0);

console.log('\n── Hors-saison / erreurs ──');
const empty = mod.normalizeFeed('nhl', { games: [], message: 'no games' });
check('feed vide accepté', empty.games.length === 0 && empty.message === 'no games');
const broken = mod.normalizeFeed('nhl', {
  games: [{ home: 'TOR', away: 'MTL', commence_time: '', predictions: { btts: { error: 'boom' } }, value_bets: [] }],
});
check('marché en erreur isolé', broken.games[0].markets[0].error === 'boom');

console.log('\n── Enrichissements publiés ──');
check('models_trained_at lu', nhl.modelsTrainedAt === '2026-10-06T14:02:11+00:00');
check('model_version lu', nhl.modelVersion === 'v2026.10.06');
check('forme des deux équipes', torMtl.form?.home?.results.length === 5 && torMtl.form?.away?.results.length === 5);
check('bilan de forme', torMtl.form.home.wins === 3 && torMtl.form.home.draws === 1);
check('5 confrontations directes', torMtl.h2h.length === 5);
check('nul h2h conservé', torMtl.h2h.some((h) => h.winner === null));
check('vainqueur h2h relatif au match à venir', torMtl.h2h[0].winner === 'away');
check('3 facteurs SHAP', torMtl.factors.length === 3);
check('direction du facteur dominant', torMtl.factors[0].direction === 'away');
check('facteurs triés par poids', Math.abs(torMtl.factors[0].contribution) >= Math.abs(torMtl.factors[1].contribution));
check('comparatif de books', vbNhl.books.length === 3 && vbNhl.books[0].best === true);
check('books NBA lus', vbNba.books.length === 3);
check('match sans enrichissement toléré', nhl.games[2].h2h.length === 0 && nhl.games[2].factors.length === 0);

console.log('\n── Mise de Kelly ──');
const { kellyStake, KELLY_CAP } = mod;
// f* = (0.547 × 2.15 − 1) / 1.15 = 15,3 % → écrêté par le plafond de 5 %.
check('Kelly plein écrêté par le plafond', kellyStake(0.547, 2.15, 1) === KELLY_CAP);
check('Kelly plein non écrêté sur petit edge', Math.abs(kellyStake(0.52, 2.0, 1) - 0.04) < 1e-9);
check('quart de Kelly', Math.abs(kellyStake(0.547, 2.15, 0.25) - 0.0384) < 0.001);
check('plafonné à 5 %', kellyStake(0.9, 3.0, 1) === KELLY_CAP);
check('aucune mise sans edge', kellyStake(0.4, 2.0, 1) === 0);
check('cote invalide → 0', kellyStake(0.6, 1, 1) === 0);

console.log('\n── Agrégation ──');
const feeds = { nhl, nba };
const all = mod.allValueBets(feeds);
check('4 value bets au total', all.length === 4, `reçu ${all.length}`);
check('tri par edge décroissant', all.every((v, i, a) => i === 0 || a[i - 1].edge >= v.edge));
check('5 matchs au total', mod.allGames(feeds).length === 5);

console.log('\n── Devises ──');
check('FCFA sans décimale', mod.formatMoney(300000, 'FCFA') === '300 000 FCFA');
check('EUR converti', mod.formatMoney(655957, 'EUR') === '1 000,00 €');
check('P&L signé', mod.formatPnl(-7100, 'FCFA') === '– 7 100 FCFA');
check('aller-retour base/affichage', mod.toBase(mod.toDisplay(655957, 'EUR'), 'EUR') === 655957);

console.log('\n── Statistiques de paris ──');
const bets = [
  { id: 'a', status: 'won', stake: 10000, pnl: 7000, odds: 1.7, market: 'btts', league: 'NHL', combo: false, ts: 1 },
  { id: 'b', status: 'lost', stake: 10000, pnl: -10000, odds: 2.15, market: 'moneyline', league: 'NHL', combo: false, ts: 2 },
  { id: 'c', status: 'pending', stake: 5000, pnl: null, odds: 1.9, market: 'total', league: 'NBA', combo: false, ts: 3 },
];
const profit = mod.computeProfit(bets);
check('2 paris réglés', profit.settledCount === 2);
check('1 en attente', profit.pendingCount === 1);
check('net = −3 000', profit.net === -3000);
check('ROI = −15 %', Math.abs(profit.roi + 0.15) < 1e-9);
check('réussite 50 %', profit.winRate === 0.5);
check('verdict perdant', profit.verdict.includes('perds'));
const bd = mod.computeBreakdown(bets);
check('2 familles de marché', bd.byMarket.length === 2);
check('famille Moneyline reconnue', mod.marketFamily('moneyline') === 'Moneyline');
check('famille Total reconnue', mod.marketFamily('away_team_total') === 'Total');

console.log('\n── Courbe de bankroll ──');
const tx = [
  { id: '1', kind: 'deposit', amount: 100000, label: 'Dépôt', ts: 1000 },
  { id: '2', kind: 'loss', amount: -10000, label: 'Perte', ts: 2000 },
];
const series = mod.bankrollSeries(200000, tx);
check('3 points (départ + 2 mouvements)', series.length === 3);
check('départ conservé', series[0].value === 200000);
check('solde final cohérent', series[2].value === 290000);
const geo = mod.curveGeometry(series);
check('géométrie SVG produite', geo.line.startsWith('M') && geo.points.length === 3);
const flat = mod.curveGeometry([{ value: 5, label: 'a' }, { value: 5, label: 'b' }]);
check('série plate sans division par zéro', flat.points.every((p) => Number.isFinite(p.y)));

console.log('\n── Options de suivi ──');
const opts = mod.followMarkets(torMtl);
check('marchés suivables proposés', opts.length >= 3, `reçu ${opts.length}`);
const ml = opts.find((o) => o.key === 'moneyline');
check('cote réelle utilisée quand value bet', ml.options.find((o) => o.selection === 'away').real === true);
check('cote juste sinon', ml.options.find((o) => o.selection === 'home').real === false);
check(
  'cote juste = 1 ÷ proba',
  Math.abs(ml.options.find((o) => o.selection === 'home').odds - 2.21) < 0.02,
);

console.log('\n── Clôture automatique ──');
// Échantillon calqué sur la sortie de scripts/publish_results.py.
const resultsRaw = {
  generated_at: '2026-10-13T07:00:00+00:00',
  games: [
    {
      sport: 'nhl',
      home: 'TOR',
      away: 'MTL',
      commence_time: '2026-10-12T23:00Z',
      home_score: 4,
      away_score: 2,
      overtime: false,
      periods: [{ home: 2, away: 0 }, { home: 1, away: 1 }, { home: 1, away: 1 }],
      winner: 'home',
    },
    {
      sport: 'nhl',
      home: 'BOS',
      away: 'NYR',
      commence_time: '2026-10-12T23:00Z',
      home_score: 3,
      away_score: 2,
      overtime: true,
      periods: [{ home: 0, away: 0 }, { home: 1, away: 2 }, { home: 1, away: 0 }, { home: 1, away: 0 }],
      winner: 'home',
    },
  ],
};
const results = mod.normalizeResults(resultsRaw);
check('2 résultats normalisés', results.length === 2, `reçu ${results.length}`);
check('score final lu', results[0].homeScore === 4 && results[0].awayScore === 2);
check('prolongation détectée', results[1].overtime === true);
check('résultat sans jeu de données ignoré', mod.normalizeResults({ games: [{ sport: 'nhl' }] }).length === 0);

const tor = results[0];
const ot = results[1];
check('moneyline gagnant', mod.settleSelection('moneyline', 'home', tor) === 'won');
check('moneyline perdant', mod.settleSelection('moneyline', 'away', tor) === 'lost');
check('win (NBA) traité comme moneyline', mod.settleSelection('win', 'home', tor) === 'won');
check('BTTS oui', mod.settleSelection('btts', 'yes', tor) === 'won');
check('BTTS non', mod.settleSelection('btts', 'no', tor) === 'lost');
check('over 5.5 sur 6 buts', mod.settleSelection('total', 'over_5.5', tor) === 'won');
check('under 5.5 sur 6 buts', mod.settleSelection('total', 'under_5.5', tor) === 'lost');
check('ligne entière pile = abstention', mod.settleSelection('total', 'over_6', tor) === null);
check('total équipe domicile', mod.settleSelection('home_team_total', 'over_3.5', tor) === 'won');
check('total équipe extérieur', mod.settleSelection('away_team_total', 'over_2.5', tor) === 'lost');
check('P1 vainqueur', mod.settleSelection('p1_winner', 'home_lead', tor) === 'won');
check('P1 nul', mod.settleSelection('p1_winner', 'tied', ot) === 'won');
check('P1 total', mod.settleSelection('p1_total', 'under_1.5', tor) === 'lost');
check('P1 BTTS non', mod.settleSelection('p1_btts', 'no', tor) === 'won');
check('score exact gagnant', mod.settleSelection('exact_score', '4-2', tor) === 'won');
check('score exact perdant', mod.settleSelection('exact_score', '3-2', tor) === 'lost');
check(
  'score exact après prolongation = abstention',
  mod.settleSelection('exact_score', '3-2', ot) === null,
);
check('intervalle de buts', mod.settleSelection('goal_intervals', '5-6', tor) === 'won');
check('intervalle haut (9+)', mod.settleSelection('goal_intervals', '9+', tor) === 'lost');
check(
  'intervalle après prolongation = abstention',
  mod.settleSelection('goal_intervals', '5-6', ot) === null,
);
check('marché inconnu = abstention', mod.settleSelection('talent', 'home', tor) === null);

const index = mod.resultIndex(results);
check(
  'clé d\'index alignée sur gameId()',
  index.has('nhl-MTL@TOR-2026-10-12'),
  [...index.keys()].join(', '),
);
const pendingBet = {
  id: 'b1', ts: 0, matchId: 'nhl-MTL@TOR-2026-10-12', matchLabel: 'TOR–MTL',
  commenceTime: '2026-10-12T23:00Z', league: 'NHL', sport: 'nhl',
  market: 'moneyline', marketLabel: 'MONEYLINE', selection: 'home',
  odds: 1.95, stake: 5000, status: 'pending', pnl: null,
};
check('pari suivi clôturé', mod.settleBet(pendingBet, index) === 'won');
check(
  'résultat retrouvé à un jour près (minuit UTC)',
  mod.findResult(index, 'nhl-MTL@TOR-2026-10-13')?.homeScore === 4,
);
check(
  'écart de deux jours refusé',
  mod.findResult(index, 'nhl-MTL@TOR-2026-10-14') === undefined,
);
check(
  'pari daté de la veille clôturé quand même',
  mod.settleBet({ ...pendingBet, matchId: 'nhl-MTL@TOR-2026-10-11' }, index) === 'won',
);
check(
  'pari déjà clôturé jamais réévalué',
  mod.settleBet({ ...pendingBet, status: 'lost' }, index) === null,
);
check(
  'match sans résultat publié = en attente',
  mod.settleBet({ ...pendingBet, matchId: 'nhl-XXX@YYY-2026-10-12' }, index) === null,
);
const combo = {
  ...pendingBet, id: 'c1', combo: true, market: 'combo', marketLabel: 'COMBINÉ',
  legs: [
    { key: 'l1', matchId: 'nhl-MTL@TOR-2026-10-12', matchLabel: 'TOR–MTL', commenceTime: '', league: 'NHL', sport: 'nhl', market: 'moneyline', selection: 'home', odds: 1.95 },
    { key: 'l2', matchId: 'nhl-NYR@BOS-2026-10-12', matchLabel: 'BOS–NYR', commenceTime: '', league: 'NHL', sport: 'nhl', market: 'moneyline', selection: 'home', odds: 2.1 },
  ],
};
check('combiné gagnant si toutes les jambes passent', mod.settleBet(combo, index) === 'won');
check(
  'combiné perdu dès qu\'une jambe tombe',
  mod.settleBet(
    { ...combo, legs: [combo.legs[0], { ...combo.legs[1], selection: 'away' }] },
    index,
  ) === 'lost',
);
check(
  'combiné en attente si une jambe est inconnue',
  mod.settleBet(
    { ...combo, legs: [combo.legs[0], { ...combo.legs[1], matchId: 'nhl-A@B-2026-10-12' }] },
    index,
  ) === null,
);

console.log(
  failures === 0
    ? '\n✅ Tous les contrôles passent.\n'
    : `\n❌ ${failures} contrôle(s) en échec.\n`,
);
process.exit(failures === 0 ? 0 : 1);
