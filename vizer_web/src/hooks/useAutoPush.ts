/**
 * Envoi différé de l'état vers la sauvegarde distante.
 *
 * Suivre un pari, le clôturer, bouger un réglage : chacun de ces gestes change
 * l'état, et déclencher une requête à chaque fois serait absurde — on attend
 * que les changements se calment.
 *
 * L'envoi est silencieux et sans conséquence en cas d'échec : la source de
 * vérité reste l'appareil, le distant n'est qu'une copie. Un réseau coupé ne
 * doit produire ni message d'erreur ni blocage.
 */
import { useEffect, useRef } from 'react';
import { useBankroll } from '../context/BankrollContext';
import { useSettings } from '../context/SettingsContext';
import { localUpdatedAt, pushState, readSyncKey, SYNC_AVAILABLE } from '../lib/sync';

const DEBOUNCE_MS = 8_000;

export function useAutoPush(): void {
  // On ne lit pas ces valeurs : on s'abonne à leurs changements, qui sont le
  // signal qu'il y a quelque chose à envoyer.
  const { followed, transactions, bankroll } = useBankroll();
  const { settings } = useSettings();
  const sent = useRef(0);

  useEffect(() => {
    if (!SYNC_AVAILABLE) return;
    const key = readSyncKey();
    if (!key) return;

    const timer = window.setTimeout(() => {
      const stamp = localUpdatedAt();
      // Rien de neuf depuis le dernier envoi réussi.
      if (stamp <= sent.current) return;
      void pushState(key).then((res) => {
        if (res.ok) sent.current = stamp;
      });
    }, DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [followed, transactions, bankroll, settings]);
}
