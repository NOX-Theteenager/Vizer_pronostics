import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { DEFAULT_SETTINGS, loadSettings, saveSettings, type Settings } from '../lib/settings';
import { markChanged } from '../lib/sync';

interface SettingsCtx {
  settings: Settings;
  /** Thème effectivement appliqué — utile aux calculs de contraste. */
  resolvedTheme: 'dark' | 'light';
  update: (patch: Partial<Settings>) => void;
  reset: () => void;
}

const Ctx = createContext<SettingsCtx | null>(null);

function applyTheme(theme: Settings['theme']): void {
  document.documentElement.setAttribute('data-theme', theme);
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', theme === 'light' ? '#efede4' : '#0b0d12');
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(() => loadSettings());

  useEffect(() => {
    saveSettings(settings);
    applyTheme(settings.theme);
    markChanged();
  }, [settings]);

  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  }, []);

  // `onboarded` survit à une remise à zéro : on ne réimpose pas le tunnel.
  const reset = useCallback(
    () => setSettings((prev) => ({ ...DEFAULT_SETTINGS, onboarded: prev.onboarded })),
    [],
  );

  const value = useMemo(
    () => ({ settings, resolvedTheme: settings.theme, update, reset }),
    [settings, update, reset],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSettings(): SettingsCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useSettings doit être utilisé dans <SettingsProvider>');
  return ctx;
}
