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
import type { Toast } from '../types/bankroll';

/**
 * Toast avec action « Annuler » (maquette v2). Une seule notification à la
 * fois ; elle s'efface au bout de 5 s, comme dans la maquette.
 */
interface ToastCtx {
  toast: Toast | null;
  showToast: (msg: string, undo?: () => void) => void;
  dismissToast: () => void;
  runUndo: () => void;
}

const Ctx = createContext<ToastCtx | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const dismissToast = useCallback(() => {
    window.clearTimeout(timer.current);
    setToast(null);
  }, []);

  const showToast = useCallback(
    (msg: string, undo?: () => void) => {
      window.clearTimeout(timer.current);
      setToast({ id: Date.now(), msg, undo });
      timer.current = window.setTimeout(() => setToast(null), 5000);
    },
    [],
  );

  const runUndo = useCallback(() => {
    toast?.undo?.();
    dismissToast();
  }, [toast, dismissToast]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const value = useMemo(
    () => ({ toast, showToast, dismissToast, runUndo }),
    [toast, showToast, dismissToast, runUndo],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useToast(): ToastCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useToast doit être utilisé dans <ToastProvider>');
  return ctx;
}
