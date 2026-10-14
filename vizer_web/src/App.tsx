import { useCallback, useEffect, useMemo, useState } from 'react';
import { Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { IconTicket } from './components/Icons';
import { AppBar, BottomNav } from './components/Shell';
import {
  DemoBanner,
  OfflineBanner,
  PartialBanner,
  StaleBanner,
} from './components/States';
import { ToastHost } from './components/ToastHost';
import { AlertsSheet, InstallPrompt, NotifPreview, PermissionPrompt } from './components/overlays/Alerts';
import { FollowSheet, type FollowDraft } from './components/overlays/FollowSheet';
import { Onboarding, type OnboardingResult } from './components/overlays/Onboarding';
import { SearchOverlay } from './components/overlays/SearchOverlay';
import { SlipSheet } from './components/overlays/SlipSheet';
import { Splash } from './components/overlays/Splash';
import { useBankroll } from './context/BankrollContext';
import { useData } from './context/DataContext';
import { useSettings } from './context/SettingsContext';
import { useAlerts } from './hooks/useAlerts';
import { useAutoPush } from './hooks/useAutoPush';
import { useAutoSettle } from './hooks/useAutoSettle';
import { usePullToRefresh } from './hooks/usePullToRefresh';
import { Admin } from './screens/Admin';
import { Bankroll } from './screens/Bankroll';
import { History } from './screens/History';
import { MatchDetail } from './screens/MatchDetail';
import { Settings } from './screens/Settings';
import { Today } from './screens/Today';
import { ValueBets } from './screens/ValueBets';
import { LoadError } from './components/States';
import { SPORTS, type Game, type Sport, type ValueBet } from './types/model';

type Overlay = 'search' | 'alerts' | 'notif' | 'permission' | 'install' | 'slip' | null;

/** Évènement d'installation PWA, non typé par la lib DOM. */
interface InstallEvent extends Event {
  prompt: () => Promise<void>;
}

export function App() {
  const { settings, update } = useSettings();
  const {
    error,
    origin,
    online,
    stale,
    generatedAt,
    partialFailures,
    refresh,
    refreshing,
    loadDemo,
    games,
    findGame,
  } = useData();
  const { unseenCount, markAllSeen, permission, requestPermission } = useAlerts();
  const { slip, addToSlip, follow, setBankroll, bankroll } = useBankroll();
  const navigate = useNavigate();
  const location = useLocation();

  const [sport, setSport] = useState<Sport>(settings.defaultSport);
  const [touchedSport, setTouchedSport] = useState(false);
  const [overlay, setOverlay] = useState<Overlay>(null);
  const [splash, setSplash] = useState(true);
  const [onboarding, setOnboarding] = useState(false);
  const [followTarget, setFollowTarget] = useState<{
    game: Game;
    preset: { market: string; selection: string; odds: number } | null;
  } | null>(null);
  const [installEvent, setInstallEvent] = useState<InstallEvent | null>(null);

  /* Splash 2,6 s, puis onboarding si nécessaire (comme la maquette). */
  useEffect(() => {
    const t = window.setTimeout(() => {
      setSplash(false);
      if (!settings.onboarded) setOnboarding(true);
    }, 2600);
    return () => window.clearTimeout(t);
    // Volontairement au montage seulement.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* Le sport par défaut s'applique tant que l'utilisateur n'a pas basculé. */
  useEffect(() => {
    if (!touchedSport) setSport(settings.defaultSport);
  }, [settings.defaultSport, touchedSport]);

  /* L'accent de sport pilote les teintes de l'écran courant. */
  useEffect(() => {
    document.documentElement.style.setProperty('--sport', `var(${SPORTS[sport].colorVar})`);
  }, [sport]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'auto' });
  }, [location.pathname]);

  useEffect(() => {
    const onInstall = (e: Event) => {
      e.preventDefault();
      setInstallEvent(e as InstallEvent);
    };
    window.addEventListener('beforeinstallprompt', onInstall);
    return () => window.removeEventListener('beforeinstallprompt', onInstall);
  }, []);

  const pull = usePullToRefresh(refresh);

  /* Les scores finaux sont publiés : ce qui est tranchable se clôture seul. */
  useAutoSettle(generatedAt, online);

  /* Copie distante de l'état, envoyée une fois les changements calmés. */
  useAutoPush();

  /* ── Suivi de pari ─────────────────────────────────────────────────── */

  const openFollowFromBet = useCallback(
    (vb: ValueBet) => {
      const game = findGame(vb.gameId);
      if (!game) return;
      setFollowTarget({
        game,
        preset: { market: vb.market, selection: vb.selection, odds: vb.bookmakerOdds },
      });
    },
    [findGame],
  );

  const openFollowFromGame = useCallback(
    (game: Game) => setFollowTarget({ game, preset: null }),
    [],
  );

  const addBetToSlip = useCallback(
    (vb: ValueBet) => {
      addToSlip({
        key: vb.id,
        matchId: vb.gameId,
        matchLabel: `${vb.away}–${vb.home}`,
        commenceTime: vb.commenceTime,
        league: SPORTS[vb.sport].league,
        sport: vb.sport,
        market: vb.marketLabel,
        selection: vb.selectionLabel,
        odds: vb.bookmakerOdds,
      });
    },
    [addToSlip],
  );

  const confirmFollow = useCallback(
    (draft: FollowDraft) => {
      const game = followTarget?.game;
      if (!game) return;
      follow({
        matchId: game.id,
        matchLabel: `${game.home}–${game.away}`,
        commenceTime: game.commenceTime,
        league: SPORTS[game.sport].league,
        sport: game.sport,
        market: draft.market,
        marketLabel: draft.marketLabel,
        selection: draft.selectionName,
        odds: draft.odds,
        stake: draft.stake,
      });
      setFollowTarget(null);
      navigate('/historique');
    },
    [followTarget, follow, navigate],
  );

  const slipFromDraft = useCallback(
    (draft: FollowDraft) => {
      const game = followTarget?.game;
      if (!game) return;
      addToSlip({
        key: `${game.id}#${draft.market}#${draft.selection}`,
        matchId: game.id,
        matchLabel: `${game.home}–${game.away}`,
        commenceTime: game.commenceTime,
        league: SPORTS[game.sport].league,
        sport: game.sport,
        market: draft.marketLabel,
        selection: draft.selectionName,
        odds: draft.odds,
      });
      setFollowTarget(null);
    },
    [followTarget, addToSlip],
  );

  const finishOnboarding = useCallback(
    (r: OnboardingResult) => {
      update({
        currency: r.currency,
        defaultSport: r.defaultSport,
        onboarded: true,
      });
      setBankroll(r.bankroll);
      setSport(r.defaultSport);
      setOnboarding(false);
    },
    [update, setBankroll],
  );

  const sportCounts = useMemo(() => games.length, [games]);

  if (splash) return <Splash open />;
  if (onboarding) return <Onboarding onFinish={finishOnboarding} />;

  const onSportChange = (s: Sport) => {
    setSport(s);
    setTouchedSport(true);
  };

  return (
    <div className="vz-app">
      <AppBar
        theme={settings.theme}
        alertCount={unseenCount}
        onToggleTheme={() => update({ theme: settings.theme === 'dark' ? 'light' : 'dark' })}
        onSearch={() => setOverlay('search')}
        onAlerts={() => {
          setOverlay('alerts');
          markAllSeen();
        }}
        onHome={() => navigate('/')}
        onSettings={() => navigate('/reglages')}
        settingsActive={
          location.pathname === '/reglages' || location.pathname === '/bankroll'
        }
      />

      {pull.indicator > 0 && (
        <div className="vz-pull" style={{ opacity: pull.indicator }}>
          {refreshing ? 'actualisation…' : '↑ Relâcher pour actualiser'}
        </div>
      )}

      <main className="vz-main">
        <div className="vz-banners">
          {!online && <OfflineBanner />}
          {origin === 'mock' && <DemoBanner />}
          {online && origin !== 'mock' && stale && <StaleBanner generatedAt={generatedAt} />}
          {partialFailures.length > 0 && <PartialBanner sports={partialFailures} />}
        </div>

        {error && sportCounts === 0 ? (
          <div className="vz-screen">
            <LoadError
              online={online}
              busy={refreshing}
              detail={error}
              onRetry={() => void refresh()}
              onDemo={() => void loadDemo()}
            />
          </div>
        ) : (
          <Routes>
            <Route
              path="/"
              element={
                <Today
                  sport={sport}
                  onSportChange={onSportChange}
                  onFollow={openFollowFromBet}
                  onAddSlip={addBetToSlip}
                />
              }
            />
            <Route
              path="/match/:gameId"
              element={
                <MatchDetail
                  onFollow={openFollowFromBet}
                  onFollowMatch={openFollowFromGame}
                  onAddSlip={addBetToSlip}
                />
              }
            />
            <Route
              path="/value-bets"
              element={<ValueBets onFollow={openFollowFromBet} onAddSlip={addBetToSlip} />}
            />
            <Route path="/historique" element={<History />} />
            <Route path="/bankroll" element={<Bankroll />} />
            <Route path="/admin" element={<Admin />} />
            <Route
              path="/reglages"
              element={
                <Settings
                  onOpenAlerts={() => setOverlay('alerts')}
                  onOpenNotif={() => setOverlay('notif')}
                  onOpenPermission={() => setOverlay('permission')}
                  onOpenInstall={() => setOverlay('install')}
                  onReplayOnboarding={() => setOnboarding(true)}
                />
              }
            />
            <Route
              path="*"
              element={
                <Today
                  sport={sport}
                  onSportChange={onSportChange}
                  onFollow={openFollowFromBet}
                  onAddSlip={addBetToSlip}
                />
              }
            />
          </Routes>
        )}
      </main>

      {slip.length > 0 && (
        <button type="button" className="vz-fab" onClick={() => setOverlay('slip')}>
          <IconTicket size={17} /> Ticket · {slip.length}
        </button>
      )}

      <BottomNav />
      <ToastHost />

      <SearchOverlay open={overlay === 'search'} onClose={() => setOverlay(null)} />
      <AlertsSheet open={overlay === 'alerts'} onClose={() => setOverlay(null)} />
      <NotifPreview open={overlay === 'notif'} onClose={() => setOverlay(null)} />
      <PermissionPrompt
        open={overlay === 'permission'}
        permission={permission}
        onEnable={async () => {
          const res = await requestPermission();
          if (res === 'granted') update({ alertsEnabled: true });
          setOverlay(null);
        }}
        onClose={() => setOverlay(null)}
      />
      <InstallPrompt
        open={overlay === 'install'}
        canInstall={!!installEvent}
        onInstall={() => {
          void installEvent?.prompt();
          setInstallEvent(null);
          setOverlay(null);
        }}
        onClose={() => setOverlay(null)}
      />
      <SlipSheet open={overlay === 'slip'} onClose={() => setOverlay(null)} />
      <FollowSheet
        game={followTarget?.game ?? null}
        preset={followTarget?.preset ?? null}
        bankroll={bankroll}
        onClose={() => setFollowTarget(null)}
        onConfirm={confirmFollow}
        onAddToSlip={slipFromDraft}
      />
    </div>
  );
}
