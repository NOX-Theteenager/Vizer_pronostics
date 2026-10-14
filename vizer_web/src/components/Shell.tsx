import logoUrl from '../assets/vizer-logo.png';
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
 * Marque Vizer — le logo fourni (`assets/VizerLogo.png`), détouré.
 *
 * Il était jusqu'ici redessiné en SVG pour tenir la contrainte « aucune
 * ressource externe ». Le fichier importé reste local : Vite l'intègre au
 * build avec un nom haché, rien n'est chargé depuis un tiers.
 *
 * `scripts/gen_icons.py` produit `src/assets/vizer-logo.png` et les icônes
 * PWA depuis la même source — une seule image à remplacer pour tout changer.
 */
export function VizerMark({ size = 30 }: { size?: number }) {
  return (
    <img
      src={logoUrl}
      width={size}
      height={size}
      alt="Vizer"
      className="vz-mark"
      // Le logo est purement décoratif à côté du titre, mais il porte le nom
      // de l'app dans l'écran de démarrage et l'onboarding, où aucun texte ne
      // le double : l'alternative textuelle reste utile.
      decoding="async"
      draggable={false}
    />
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
