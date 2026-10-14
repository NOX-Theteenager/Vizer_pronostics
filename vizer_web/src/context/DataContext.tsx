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
import { fetchLatest, readCachedFeeds, readCachedFetchedAt, SPORTS as SPORT_LIST } from '../lib/api';
import { hoursSince } from '../lib/format';
import { fetchPolicy, isBettable, type MarketPolicy } from '../lib/marketPolicy';
import type { FeedOrigin, Game, Sport, SportFeed, ValueBet } from '../types/model';
import { allGames, allValueBets } from '../types/normalize';

/** Seuil de la bannière « données périmées ». */
export const STALE_HOURS = 12;

interface DataCtx {
  feeds: Record<Sport, SportFeed | null>;
  origin: FeedOrigin | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  partialFailures: Sport[];
  online: boolean;
  fetchedAt: number | null;
  generatedAt: string | null;
  stale: boolean;
  valueBets: ValueBet[];
  games: Game[];
  refresh: () => Promise<void>;
  loadDemo: () => Promise<void>;
  findGame: (id: string) => Game | null;
  /**
   * Marchés que l'on accepte de parier, surcharges de l'Admin appliquées.
   * Les marchés écartés restent prédits et affichés — seulement marqués
   * indicatifs, et leurs value bets ne sont plus proposés.
   */
  policy: MarketPolicy;
  reloadPolicy: () => Promise<void>;
}

const Ctx = createContext<DataCtx | null>(null);
const EMPTY: Record<Sport, SportFeed | null> = { nhl: null, nba: null };

export function DataProvider({ children }: { children: ReactNode }) {
  const [feeds, setFeeds] = useState<Record<Sport, SportFeed | null>>(EMPTY);
  const [origin, setOrigin] = useState<FeedOrigin | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [partialFailures, setPartialFailures] = useState<Sport[]>([]);
  const [fetchedAt, setFetchedAt] = useState<number | null>(null);
  const [online, setOnline] = useState(() => navigator.onLine);
  const inFlight = useRef(false);

  const run = useCallback(async (opts: { mock?: boolean; silent?: boolean } = {}) => {
    if (inFlight.current) return;
    inFlight.current = true;
    if (opts.silent) setRefreshing(true);
    else setLoading(true);

    try {
      const res = await fetchLatest({ mock: opts.mock });
      setFeeds(res.feeds);
      setOrigin(res.origin);
      setPartialFailures(res.partialFailures);
      setFetchedAt(res.origin === 'network' ? Date.now() : null);
      setError(null);
    } catch (e) {
      // Repli sur le cache : tout reste consultable hors-ligne.
      const cached = readCachedFeeds();
      if (SPORT_LIST.some((s) => cached[s] !== null)) {
        setFeeds(cached);
        setOrigin('cache');
        setFetchedAt(readCachedFetchedAt());
        setPartialFailures([]);
        setError(null);
      } else {
        setError(e instanceof Error ? e.message : 'Erreur inconnue');
      }
    } finally {
      inFlight.current = false;
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Premier rendu : on peint le cache immédiatement, puis on rafraîchit.
  useEffect(() => {
    const cached = readCachedFeeds();
    if (SPORT_LIST.some((s) => cached[s] !== null)) {
      setFeeds(cached);
      setOrigin('cache');
      setFetchedAt(readCachedFetchedAt());
      setLoading(false);
      void run({ silent: true });
    } else {
      void run();
    }
  }, [run]);

  useEffect(() => {
    const goOnline = () => {
      setOnline(true);
      void run({ silent: true });
    };
    const goOffline = () => setOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, [run]);

  const refresh = useCallback(() => run({ silent: true }), [run]);
  const loadDemo = useCallback(() => run({ mock: true }), [run]);

  const generatedAt = useMemo(() => {
    const stamps = SPORT_LIST.map((s) => feeds[s]?.generatedAt).filter((x): x is string => !!x);
    return stamps.length ? (stamps.sort().at(-1) ?? null) : null;
  }, [feeds]);

  const stale = useMemo(() => {
    const h = hoursSince(generatedAt);
    return h !== null && h > STALE_HOURS;
  }, [generatedAt]);

  const [policy, setPolicy] = useState<MarketPolicy>({});

  const reloadPolicy = useCallback(async () => {
    try {
      setPolicy((await fetchPolicy()).markets);
    } catch {
      // Politique indisponible : on garde les valeurs par défaut du code,
      // ce qui est le comportement d'avant la surcharge.
    }
  }, []);

  useEffect(() => {
    void reloadPolicy();
  }, [reloadPolicy]);

  // Un marché écarté n'est plus *proposé* : ni dans le rail du jour, ni dans
  // l'écran Value bets, ni dans les alertes. Il reste prédit et mesuré.
  const valueBets = useMemo(
    () => allValueBets(feeds).filter((vb) => isBettable(policy, vb.sport, vb.market)),
    [feeds, policy],
  );
  const games = useMemo(() => allGames(feeds), [feeds]);

  const findGame = useCallback(
    (id: string) => games.find((g) => g.id === id) ?? null,
    [games],
  );

  const value = useMemo<DataCtx>(
    () => ({
      feeds,
      origin,
      loading,
      refreshing,
      error,
      partialFailures,
      online,
      fetchedAt,
      generatedAt,
      stale,
      valueBets,
      games,
      refresh,
      loadDemo,
      findGame,
      policy,
      reloadPolicy,
    }),
    [
      feeds,
      origin,
      loading,
      refreshing,
      error,
      partialFailures,
      online,
      fetchedAt,
      generatedAt,
      stale,
      valueBets,
      games,
      refresh,
      loadDemo,
      findGame,
      policy,
      reloadPolicy,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData(): DataCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useData doit être utilisé dans <DataProvider>');
  return ctx;
}