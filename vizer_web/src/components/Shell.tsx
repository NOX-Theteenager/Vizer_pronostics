import { NavLink } from 'react-router-dom';
import { SPORTS, type Sport } from '../types/model';
import {
  IconBall,
  IconBell,
  IconBolt,
  IconChart,
  IconHome,
  IconMoon,
  IconPuck,
  IconSearch,
  IconShield,
  IconSliders,
  IconSun,
} from './Icons';

/* ── Barre d'application ───────────────────────────────────────────────── */
export function AppBar({
  theme,
  alertCount,
  onToggleTheme,
  onSearch,
  onAlerts,
  onHome,
  onSettings,
  settingsActive,
}: {
  theme: 'dark' | 'light';
  alertCount: number;
  onToggleTheme: () => void;
  onSearch: () => void;
  onAlerts: () => void;
  onHome: () => void;
  onSettings: () => void;
  settingsActive: boolean;
}) {
  return (
    <header className="vz-appbar">
      <div className="vz-appbar__in">
        <button type="button" className="vz-brand" onClick={onHome}>
          <VizerMark size={30} />
          <span>Vizer</span>
        </button>
        <span className="vz-f1" />
        <button type="button" className="vz-iconbtn" onClick={onSearch} aria-label="Rechercher">
          <IconSearch size={17} />
        </button>
        <button
          type="button"
          className="vz-iconbtn"
          onClick={onToggleTheme}
          aria-label="Changer de thème"
        >
          {theme === 'dark' ? <IconSun size={18} /> : <IconMoon size={17} />}
        </button>
        <button
          type="button"
          className="vz-iconbtn"
          onClick={onAlerts}
          aria-label={`Alertes${alertCount ? ` (${alertCount} non lues)` : ''}`}
        >
          <IconBell size={17} />
          {alertCount > 0 && <i className="vz-iconbtn__dot" />}
        </button>
        <button
          type="button"
          className={`vz-iconbtn${settingsActive ? ' is-active' : ''}`}
          onClick={onSettings}
          aria-label="Réglages"
        >
          <IconSliders size={18} />
        </button>
      </div>
    </header>
  );
}

/**
 * Marque Vizer. La maquette référence `VizerLogo.png` (un « V » néon vert) ;
 * il est redessiné ici en SVG pour tenir la contrainte « aucune ressource
 * externe » et suivre le thème — même tracé, mêmes couleurs.
 */
export function VizerMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-label="Vizer" role="img">
      <defs>
        <linearGradient id="vzMarkL" x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0%" stopColor="#4ff09a" />
          <stop offset="100%" stopColor="#13b36a" />
        </linearGradient>
        <linearGradient id="vzMarkR" x1="1" y1="0" x2="0.4" y2="1">
          <stop offset="0%" stopColor="#e9eef5" />
          <stop offset="100%" stopColor="#9aa6b6" />
        </linearGradient>
      </defs>
      {/* Deux lames qui se rejoignent en pointe — le « V » du logo. */}
      <path d="M6 12 L20 12 L33 50 L27 56 Z" fill="url(#vzMarkL)" />
      <path d="M58 12 L44 12 L31 50 L37 56 Z" fill="url(#vzMarkR)" />
      <path
        d="M20 13 L32 48"
        fill="none"
        stroke="#9dffcf"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity=".8"
      />
    </svg>
  );
}

/* ── Sélecteur de sport ────────────────────────────────────────────────── */
export function SportTabs({
  value,
  counts,
  onChange,
}: {
  value: Sport;
  counts: Record<Sport, number | null>;
  onChange: (s: Sport) => void;
}) {
  return (
    <div className="vz-sporttabs" role="tablist" aria-label="Sport">
      {(Object.keys(SPORTS) as Sport[]).map((s) => {
        const meta = SPORTS[s];
        const active = s === value;
        const n = counts[s];
        return (
          <button
            key={s}
            type="button"
            role="tab"
            aria-selected={active}
            className={`vz-sporttab${active ? ' is-active' : ''}`}
            style={{ ['--tab-color' as string]: `var(${meta.colorVar})` }}
            onClick={() => onChange(s)}
          >
            <span className="vz-sporttab__ic">
              {s === 'nhl' ? <IconPuck size={21} /> : <IconBall size={19} />}
            </span>
            <span className="vz-col">
              <strong>{meta.label}</strong>
              <small>
                {meta.league} · {n === null ? '—' : n} match{(n ?? 0) > 1 ? 's' : ''}
              </small>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/* ── Navigation basse ──────────────────────────────────────────────────── */
const TABS = [
  { to: '/', label: "Aujourd'hui", icon: IconHome, end: true },
  { to: '/value-bets', label: 'Value bets', icon: IconBolt, end: false },
  { to: '/historique', label: 'Historique', icon: IconChart, end: false },
  { to: '/admin', label: 'Admin', icon: IconShield, end: false },
] as const;

export function BottomNav() {
  return (
    <nav className="vz-nav" aria-label="Navigation principale">
      {TABS.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) => `vz-nav__item${isActive ? ' is-active' : ''}`}
        >
          <Icon size={to === '/value-bets' ? 20 : 21} />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
