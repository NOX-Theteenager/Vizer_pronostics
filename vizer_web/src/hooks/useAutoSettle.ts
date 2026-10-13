/**
 * Clôture automatique des paris dès que les scores finaux sont publiés.
 *
 * Deux déclenchements, aucun polling :
 *   - au démarrage, sur les résultats déjà en cache (donc hors-ligne aussi) ;
 *   - à chaque rafraîchissement du feed, qui est aussi le moment où de
 *     nouveaux résultats ont des chances d'exister.
 *
 * Le réglage `autoSettle` coupe le mécanisme sans rien casser : les paris
 * restent clôturables à la main, comme avant.
 */
import { useEffect, useRef } from 'react';
import { useBankroll } from '../context/BankrollContext';
import { useSettings } from '../context/SettingsContext';
import { fetchResults, readCachedResults } from '../lib/api';

export function useAutoSettle(generatedAt: string | null, online: boolean): void {
  const { settings } = useSettings();
  const { settleFromResults, followed } = useBankroll();
  const lastFetch = useRef(0);

  const pending = followed.some((b) => b.status === 'pending');

  useEffect(() => {
    if (!settings.autoSettle || !pending) return;

    // Cache d'abord : instantané, et c'est la seule voie hors-ligne.
    const cached = readCachedResults();
    if (cached.length) settleFromResults(cached);

    if (!online) return;
    // Les résultats ne bougent qu'une fois par jour : un fetch toutes les
    // quinze minutes suffit largement, même si le feed est rafraîchi souvent.
    if (Date.now() - lastFetch.current < 15 * 60_000) return;
    lastFetch.current = Date.now();

    let cancelled = false;
    void fetchResults()
      .then((results) => {
        if (!cancelled) settleFromResults(results);
      })
      .catch(() => {
        // Pas de résultats publiés, ou réseau coupé : la clôture manuelle
        // reste disponible, rien à signaler.
      });
    return () => {
      cancelled = true;
    };
    // `generatedAt` sert de signal « le feed vient d'être rafraîchi ».
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.autoSettle, pending, online, generatedAt]);
}
