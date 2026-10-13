/**
 * Pull-to-refresh (design.md §2 : « le rafraîchissement est un re-fetch »).
 *
 * Implémenté sans dépendance : on n'écoute le geste que lorsque la page est
 * déjà en haut, et on laisse le scroll natif faire son travail sinon.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

const TRIGGER_PX = 72;

export function usePullToRefresh(onRefresh: () => Promise<void> | void) {
  const [indicator, setIndicator] = useState(0);
  const startY = useRef<number | null>(null);
  const armed = useRef(false);

  const reset = useCallback(() => {
    startY.current = null;
    armed.current = false;
    setIndicator(0);
  }, []);

  useEffect(() => {
    const onStart = (e: TouchEvent) => {
      if (window.scrollY > 2 || e.touches.length !== 1) return;
      startY.current = e.touches[0].clientY;
      armed.current = false;
    };

    const onMove = (e: TouchEvent) => {
      if (startY.current === null) return;
      const dy = e.touches[0].clientY - startY.current;
      if (dy <= 0) {
        setIndicator(0);
        return;
      }
      const progress = Math.min(1, dy / TRIGGER_PX);
      setIndicator(progress);
      armed.current = progress >= 1;
    };

    const onEnd = () => {
      if (armed.current) void onRefresh();
      reset();
    };

    window.addEventListener('touchstart', onStart, { passive: true });
    window.addEventListener('touchmove', onMove, { passive: true });
    window.addEventListener('touchend', onEnd, { passive: true });
    window.addEventListener('touchcancel', reset, { passive: true });
    return () => {
      window.removeEventListener('touchstart', onStart);
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onEnd);
      window.removeEventListener('touchcancel', reset);
    };
  }, [onRefresh, reset]);

  return { indicator };
}
