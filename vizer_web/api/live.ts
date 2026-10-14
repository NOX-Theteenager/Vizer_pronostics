/**
 * Scores en direct, relayés depuis le scoreboard public d'ESPN.
 *
 * Pourquoi une fonction et pas un fichier publié
 * -----------------------------------------------
 * Tout le reste du contrat passe par des JSON poussés sur `models-artifacts`.
 * Le direct ne peut pas : il change toutes les trente secondes, et republier
 * un fichier à cette cadence ferait enfler le dépôt et entrerait en collision
 * avec le job quotidien. Le relais vit donc ici, caché vingt secondes au bord
 * du réseau — l'app garde une seule origine et ses propres en-têtes, comme
 * pour `/api/data`.
 *
 * Ce que ça ne fait pas
 * ---------------------
 * Le direct **ne clôture aucun pari**. La clôture s'appuie sur
 * `results/latest.json`, publié par le job quotidien : une donnée datée,
 * auditable et rejouable. Un score lu en vol ne l'est pas.
 */
import { envAny } from './_lib/env.js';

const SPORTS = {
  nhl: 'hockey/nhl',
  nba: 'basketball/nba',
} as const;

type Sport = keyof typeof SPORTS;

/**
 * ESPN abrège quelques équipes autrement que le reste du projet. Même table
 * que `scripts/publish_results.py` — UTA → ARI côté NHL n'est pas une coquille :
 * les modèles sont entraînés sur un historique où la franchise de l'Utah
 * prolonge celle de l'Arizona.
 */
const ALIASES: Record<Sport, Record<string, string>> = {
  // `UTA` **et** `UTAH` : ESPN n'abrège pas l'Utah pareil selon l'endpoint —
  // `UTAH` sur la liste des équipes, `UTA` sur le scoreboard. Sans les deux,
  // le match sort sous un code que les prédictions n'emploient jamais et
  // aucun direct ne s'affiche.
  nhl: { LA: 'LAK', NJ: 'NJD', SJ: 'SJS', TB: 'TBL', UTAH: 'ARI', UTA: 'ARI' },
  nba: { GS: 'GSW', NO: 'NOP', NY: 'NYK', SA: 'SAS', UTAH: 'UTA', WSH: 'WAS' },
};

interface Competitor {
  homeAway?: string;
  score?: string;
  team?: { abbreviation?: string };
}

interface Event {
  date?: string;
  competitions?: {
    status?: {
      period?: number;
      displayClock?: string;
      type?: { state?: string; shortDetail?: string; completed?: boolean };
    };
    competitors?: Competitor[];
  }[];
}

export interface LiveGame {
  /** Même construction que `gameId()` côté app : l'appariement est direct. */
  id: string;
  sport: Sport;
  home: string;
  away: string;
  commenceTime: string;
  /** 'in' = en cours, 'post' = terminé. */
  state: 'in' | 'post';
  /** Texte prêt à afficher : « 7:32 - 2nd », « Final/OT »… */
  detail: string;
  period: number | null;
  clock: string | null;
  homeScore: number;
  awayScore: number;
}

const code = (sport: Sport, abbrev: string): string =>
  ALIASES[sport][abbrev] ?? abbrev;

/** `YYYYMMDD` décalé de `days` par rapport à aujourd'hui, en UTC. */
function day(offset: number): string {
  const d = new Date(Date.now() + offset * 86_400_000);
  return d.toISOString().slice(0, 10).replace(/-/g, '');
}

function parse(sport: Sport, payload: { events?: Event[] }): LiveGame[] {
  const out: LiveGame[] = [];

  for (const event of payload.events ?? []) {
    const comp = event.competitions?.[0];
    const status = comp?.status;
    const state = status?.type?.state;
    // 'pre' n'apprend rien : l'app connaît déjà l'heure du coup d'envoi.
    if (state !== 'in' && state !== 'post') continue;

    const sides: Record<string, Competitor> = {};
    for (const c of comp?.competitors ?? []) {
      if (c.homeAway) sides[c.homeAway] = c;
    }
    const home = sides.home?.team?.abbreviation;
    const away = sides.away?.team?.abbreviation;
    if (!home || !away) continue;

    const homeScore = Number(sides.home?.score);
    const awayScore = Number(sides.away?.score);
    if (!Number.isFinite(homeScore) || !Number.isFinite(awayScore)) continue;

    const commenceTime = event.date ?? '';
    const h = code(sport, home);
    const a = code(sport, away);

    out.push({
      id: `${sport}-${a}@${h}-${commenceTime.slice(0, 10) || 'na'}`,
      sport,
      home: h,
      away: a,
      commenceTime,
      state,
      detail: status?.type?.shortDetail ?? '',
      period: typeof status?.period === 'number' ? status.period : null,
      clock: status?.displayClock ?? null,
      homeScore,
      awayScore,
    });
  }

  return out;
}

export async function GET(): Promise<Response> {
  // Trois jours : la date ESPN est celle du fuseau américain, la nôtre est en
  // UTC. Un match à 02:00 UTC est listé par ESPN sous la veille, et son
  // identifiant côté app porte le lendemain. Interroger la fenêtre entière
  // évite d'avoir à raisonner sur le décalage.
  const dates = [day(-1), day(0), day(1)];
  const base = envAny('VIZER_ESPN_BASE') ?? 'https://site.api.espn.com/apis/site/v2/sports';

  const requests: Promise<LiveGame[]>[] = [];
  for (const sport of Object.keys(SPORTS) as Sport[]) {
    for (const d of dates) {
      requests.push(
        fetch(`${base}/${SPORTS[sport]}/scoreboard?dates=${d}`, {
          headers: { 'user-agent': 'vizer-live' },
        })
          .then((r) => (r.ok ? r.json() : { events: [] }))
          .then((p) => parse(sport, p as { events?: Event[] }))
          // Une date ou un sport en panne ne doit pas vider tout le direct.
          .catch(() => []),
      );
    }
  }

  const games = new Map<string, LiveGame>();
  for (const batch of await Promise.all(requests)) {
    // Les fenêtres se recouvrent : la dernière lecture d'un même match gagne.
    for (const g of batch) games.set(g.id, g);
  }

  const list = [...games.values()];
  const anyLive = list.some((g) => g.state === 'in');

  return new Response(
    JSON.stringify({
      generated_at: new Date().toISOString(),
      live: anyLive,
      n_games: list.length,
      games: list,
    }),
    {
      headers: {
        'content-type': 'application/json; charset=utf-8',
        // Vingt secondes quand un match est en cours, cinq minutes sinon :
        // inutile de solliciter ESPN la nuit. `stale-while-revalidate` sert
        // la version précédente pendant le rafraîchissement plutôt que de
        // faire attendre.
        'vercel-cdn-cache-control': anyLive
          ? 'max-age=20, stale-while-revalidate=40'
          : 'max-age=300, stale-while-revalidate=600',
        'cache-control': 'public, max-age=0, must-revalidate',
        'access-control-allow-origin': '*',
      },
    },
  );
}
