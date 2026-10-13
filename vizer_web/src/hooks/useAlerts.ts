/**
 * Alertes value bets.
 *
 * Trois choses distinctes :
 *   1. `alerts`      — les value bets du jour au-dessus du seuil (centre d'alertes) ;
 *   2. `unseenCount` — la pastille sur la cloche ;
 *   3. la notification système, envoyée une seule fois par value bet.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useData } from '../context/DataContext';
import { useSettings } from '../context/SettingsContext';
import { dayPhrase, formatEdge, formatOdds, formatTime, isPast } from '../lib/format';
import { KEYS, readJson, writeJson } from '../lib/storage';
import type { ValueBet } from '../types/model';

/** Plage silencieuse, telle qu'affichée dans les réglages. */
export const QUIET_START = 23;
export const QUIET_END = 8;

export function inQuietHours(hour = new Date().getHours()): boolean {
  return hour >= QUIET_START || hour < QUIET_END;
}

export type PermissionState = 'default' | 'granted' | 'denied' | 'unsupported';

function currentPermission(): PermissionState {
  if (typeof Notification === 'undefined') return 'unsupported';
  return Notification.permission as PermissionState;
}

type NotifiedStore = Record<string, string>;

/** Purge les envois de plus de 3 jours. */
function purge(store: NotifiedStore, now = Date.now()): NotifiedStore {
  const out: NotifiedStore = {};
  for (const [id, iso] of Object.entries(store)) {
    const t = new Date(iso).getTime();
    if (Number.isFinite(t) && now - t < 3 * 86_400_000) out[id] = iso;
  }
  return out;
}

/** « MTL Canadiens @ 2.15 · MONEYLINE · ce soir 19:00 ». */
export function notificationBody(vb: ValueBet): string {
  return [
    `${vb.selectionLabel} @ ${formatOdds(vb.bookmakerOdds)}`,
    vb.marketLabel,
    `${dayPhrase(vb.commenceTime)} ${formatTime(vb.commenceTime)}`,
  ].join(' · ');
}

export function useAlerts() {
  const { settings } = useSettings();
  const { valueBets } = useData();
  const [permission, setPermission] = useState<PermissionState>(currentPermission);
  const [seen, setSeen] = useState<string[]>(() => readJson<string[]>(KEYS.seenAlerts, []));

  const threshold = settings.alertThreshold / 100;

  const alerts = useMemo(
    () => valueBets.filter((vb) => vb.edge >= threshold && !isPast(vb.commenceTime)),
    [valueBets, threshold],
  );

  const unseenCount = useMemo(
    () => alerts.filter((a) => !seen.includes(a.id)).length,
    [alerts, seen],
  );

  const markAllSeen = useCallback(() => {
    setSeen((prev) => {
      const next = [...new Set([...prev, ...alerts.map((a) => a.id)])].slice(-200);
      writeJson(KEYS.seenAlerts, next);
      return next;
    });
  }, [alerts]);

  const requestPermission = useCallback(async (): Promise<PermissionState> => {
    if (typeof Notification === 'undefined') return 'unsupported';
    const res = (await Notification.requestPermission()) as PermissionState;
    setPermission(res);
    return res;
  }, []);

  useEffect(() => {
    if (!settings.alertsEnabled || permission !== 'granted' || alerts.length === 0) return;
    // Jamais de notification pendant la plage silencieuse.
    if (inQuietHours()) return;

    let store = purge(readJson<NotifiedStore>(KEYS.notified, {}));
    const fresh = alerts.filter((a) => !store[a.id]);
    if (fresh.length === 0) return;

    // Au-delà de trois alertes d'un coup, on marque les suivantes comme
    // envoyées sans les notifier : mieux vaut trois notifications qu'une
    // avalanche.
    fresh.slice(0, 3).forEach((vb) => {
      try {
        const n = new Notification(`⚡ Value bet ${formatEdge(vb.edge)}`, {
          body: notificationBody(vb),
          tag: vb.id,
          icon: `${import.meta.env.BASE_URL}icons/icon-192.png`,
          badge: `${import.meta.env.BASE_URL}icons/icon-192.png`,
          data: { gameId: vb.gameId },
        });
        n.onclick = () => {
          window.focus();
          window.location.hash = `#/match/${vb.gameId}`;
          n.close();
        };
      } catch {
        // Certains navigateurs exigent le service worker : échec silencieux,
        // le centre d'alertes in-app reste la source de vérité.
      }
    });
    const now = new Date().toISOString();
    fresh.forEach((vb) => {
      store = { ...store, [vb.id]: now };
    });
    writeJson(KEYS.notified, store);
  }, [alerts, permission, settings.alertsEnabled]);

  return { alerts, unseenCount, markAllSeen, permission, requestPermission };
}
