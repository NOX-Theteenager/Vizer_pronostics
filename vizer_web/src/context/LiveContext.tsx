import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { fetchLive, LIVE_URL } from '../lib/api';
import type { LiveGame } from '../types/live';
import { useData } from './DataContext';

/**
 * Scores en direct, partagés par tous les écrans.
 *
 * Un seul sondage pour toute l'application : la carte match, le détail et
 * l'historique lisent la même table. Trois règles tiennent la consommation —
 * data et batterie — à un niveau raisonnable :
 *
 *   1. on ne sonde que si un match de la journée a commencé, ou commence dans
 *      la demi-heure ; en dehors de ces fenêtres il n'y a rien à suivre ;
 *   2. on ne sonde pas quand l'onglet est masqué, et on rattrape au retour ;
 *   3. la cadence suit l'état réel — trente secondes tant qu'un match est en
 *      cours, cinq minutes sinon.
 *
 * Le relais met déjà en cache au bord du réseau : deux utilisateurs qui
 * regardent le même match ne déclenchent pas deux appels à ESPN.
 */
interface LiveCtx {
  /** Indexé par `Game.id`. */
  byGame: Map<string, LiveGame>;
  /** Au moins un match est en cours. */
  anyLive: boolean;
  /** Le relais existe sur ce déploiement. */
  available: boolean;
}

const Ctx = createContext<LiveCtx>({ byGame: new Map(), anyLive: false, available: false });

const LIVE_MS = 30_000;
const IDLE_MS = 300_000;
/** On commence à suivre un match une demi-heure avant le coup d'envoi. */
const LEAD_MS = 30 * 60_000;

export function LiveProvider({ children }: { children: ReactNode }) {
  const { games } = useData();
  const [live, setLive] = useState<LiveGame[]>([]);
  const timer = useRef<number | null>(null);

  /** Y a-t-il quelque chose à suivre dans le feed du jour ? */
  const watching = useMemo(
    () =>
      games.some((g) => {
        const t = Date.parse(g.commenceTime);
        if (!Number.isFinite(t)) return false;
        // Au-delà de six heures après le coup d'envoi, le match est fini même
        // dans le pire des scénarios de prolongation.
        return Date.now() >= t - LEAD_MS && Date.now() <= t + 6 * 3_600_000;
      }),
    [games],
  );

  const anyLive = live.some((g) => g.state === 'in');

  const poll = useCallback(async () => {
    try {
      setLive(await fetchLive());
    } catch {
      // ESPN injoignable ou relais absent : l'app garde les derniers scores
      // connus et continue de fonctionner sans direct.
    }
  }, []);

  useEffect(() => {
    if (!LIVE_URL || !watching) return;

    const schedule = () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(run, anyLive ? LIVE_MS : IDLE_MS);
    };
    const run = async () => {
      if (document.visibilityState === 'visible') await poll();
      schedule();
    };

    void run();

    // Au retour sur l'onglet, on rattrape immédiatement : le dernier score vu
    // peut dater de plusieurs minutes.
    const onVisible = () => {
      if (document.visibilityState === 'visible') void poll();
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [watching, anyLive, poll]);

  const value = useMemo<LiveCtx>(
    () => ({
      byGame: new Map(live.map((g) => [g.id, g])),
      anyLive,
      available: LIVE_URL !== null,
    }),
    [live, anyLive],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLive(): LiveCtx {
  return useContext(Ctx);
}

/** Direct d'un match précis, ou `null`. */
export function useLiveGame(gameId: string | undefined): LiveGame | null {
  const { byGame } = useLive();
  return gameId ? (byGame.get(gameId) ?? null) : null;
}
