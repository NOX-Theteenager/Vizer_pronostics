/**
 * Jeu d'icônes de la maquette v2 — tracés SVG inline, aucun fichier externe.
 * Toutes héritent de `currentColor` et prennent une taille en pixels.
 */
type P = { size?: number; className?: string };

const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

function svg(size: number, children: React.ReactNode, viewBox = '0 0 24 24', extra = {}) {
  return (
    <svg width={size} height={size} viewBox={viewBox} aria-hidden="true" focusable="false" {...extra}>
      {children}
    </svg>
  );
}

export const IconBolt = ({ size = 14 }: P) =>
  svg(size, <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z" />, '0 0 24 24', { fill: 'currentColor' });

export const IconSearch = ({ size = 17 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <circle cx="11" cy="11" r="7" />
      <line x1="20.5" y1="20.5" x2="16.5" y2="16.5" />
    </g>,
  );

export const IconSun = ({ size = 18 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <circle cx="12" cy="12" r="4.4" />
      <path d="M12 2.5v2.4M12 19.1v2.4M4.3 4.3l1.7 1.7M18 18l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.3 19.7l1.7-1.7M18 6l1.7-1.7" />
    </g>,
  );

export const IconMoon = ({ size = 17 }: P) =>
  svg(size, <path {...stroke} d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />);

export const IconBell = ({ size = 17 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </g>,
  );

export const IconRefresh = ({ size = 14 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <path d="M21 12a9 9 0 1 1-2.6-6.3" />
      <path d="M21 3v5h-5" />
    </g>,
  );

export const IconHome = ({ size = 21 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5.5 9.5V21h13V9.5" />
    </g>,
  );

export const IconChart = ({ size = 21 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <path d="M3 17l5.5-5.5 3.5 3.5L21 6" />
      <path d="M16 6h5v5" />
    </g>,
  );

export const IconChartAxis = ({ size = 20 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <path d="M3 3v18h18" />
      <path d="M7 14l3-3 3 2 5-6" />
    </g>,
  );

export const IconSliders = ({ size = 21 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <line x1="4" y1="8" x2="20" y2="8" />
      <line x1="4" y1="16" x2="20" y2="16" />
      <circle cx="15" cy="8" r="2.6" fill="var(--bg)" />
      <circle cx="9" cy="16" r="2.6" fill="var(--bg)" />
    </g>,
  );

export const IconPlus = ({ size = 13 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={3.2}>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </g>,
  );

export const IconCheck = ({ size = 13 }: P) =>
  svg(size, <path {...stroke} strokeWidth={3.2} d="M5 13l4 4L19 6" />);

export const IconX = ({ size = 12 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={3.2}>
      <line x1="6" y1="6" x2="18" y2="18" />
      <line x1="18" y1="6" x2="6" y2="18" />
    </g>,
  );

export const IconTicket = ({ size = 15 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <rect x="3" y="5" width="18" height="14" rx="2.5" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </g>,
  );

export const IconInfo = ({ size = 13 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="11" x2="12" y2="16.5" />
      <circle cx="12" cy="7.5" r="1.1" fill="currentColor" stroke="none" />
    </g>,
  );

export const IconDownload = ({ size = 15 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={2.2}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </g>,
  );

export const IconArrowDown = ({ size = 16 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={2.4}>
      <line x1="12" y1="5" x2="12" y2="19" />
      <polyline points="6 13 12 19 18 13" />
    </g>,
  );

export const IconArrowUp = ({ size = 16 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={2.4}>
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="6 11 12 5 18 11" />
    </g>,
  );

export const IconTrendUp = ({ size = 22 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={2.4}>
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      <polyline points="16 7 22 7 22 13" />
    </g>,
  );

export const IconTrendDown = ({ size = 22 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={2.4}>
      <polyline points="22 17 13.5 8.5 8.5 13.5 2 7" />
      <polyline points="16 17 22 17 22 11" />
    </g>,
  );

export const IconChevronRight = ({ size = 13 }: P) =>
  svg(size, <polyline {...stroke} strokeWidth={2.4} points="9 6 15 12 9 18" />);

export const IconChevronLeft = ({ size = 18 }: P) =>
  svg(size, <polyline {...stroke} strokeWidth={2.4} points="15 18 9 12 15 6" />);

export const IconMic = ({ size = 17 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <line x1="12" y1="18" x2="12" y2="21.5" />
    </g>,
  );

export const IconClock = ({ size = 17 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={2.2}>
      <circle cx="12" cy="13" r="8" />
      <path d="M12 9v4l2.5 1.5" />
      <path d="M5 3 2 6" />
      <path d="M22 6l-3-3" />
    </g>,
  );

export const IconWifiOff = ({ size = 38 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <path d="M4.5 12.5a10.5 10.5 0 0 1 15 0" />
      <path d="M8 16a5.5 5.5 0 0 1 8 0" />
      <circle cx="12" cy="19.5" r="1" fill="currentColor" stroke="none" />
      <line x1="3.5" y1="3.5" x2="20.5" y2="20.5" />
    </g>,
  );

export const IconWarning = ({ size = 18 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={2.2}>
      <path d="M12 9v4" />
      <path d="M10.3 3.9 2.4 18a1.8 1.8 0 0 0 1.6 2.7h16a1.8 1.8 0 0 0 1.6-2.7L13.7 3.9a1.9 1.9 0 0 0-3.4 0z" />
      <circle cx="12" cy="17" r="0.7" fill="currentColor" stroke="none" />
    </g>,
  );

export const IconEdit = ({ size = 15 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
    </g>,
  );

export const IconCurrency = ({ size = 20 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={2.2}>
      <path d="M12 2v20" />
      <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    </g>,
  );

export const IconH2H = ({ size = 14 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={2.2}>
      <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3m8 0h3a2 2 0 0 0 2-2v-3" />
      <path d="M9 12h6" />
    </g>,
  );

export const IconNoBet = ({ size = 24 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <circle cx="12" cy="12" r="9" />
      <line x1="6.5" y1="6.5" x2="17.5" y2="17.5" />
    </g>,
  );

/** Palet de hockey — pictogramme du sport. */
export const IconPuck = ({ size = 21 }: P) => (
  <svg width={size} height={size * 0.65} viewBox="0 0 80 52" aria-hidden="true" focusable="false">
    <ellipse cx="40" cy="34" rx="30" ry="11" fill="currentColor" opacity=".5" />
    <path d="M10 34V20a30 11 0 0 1 60 0v14" fill="currentColor" opacity=".8" />
    <ellipse cx="40" cy="20" rx="30" ry="11" fill="currentColor" />
  </svg>
);

/** Ballon de basket. */
export const IconBall = ({ size = 19 }: P) => (
  <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
    <circle cx="32" cy="32" r="28" fill="currentColor" />
    <g fill="none" stroke="var(--bg)" strokeWidth="2.6">
      <path d="M4 32h56" />
      <path d="M32 4v56" />
      <path d="M11 13q21 19 0 38" />
      <path d="M53 13q-21 19 0 38" />
    </g>
  </svg>
);

export const IconShield = ({ size = 21 }: P) =>
  svg(
    size,
    <g {...stroke}>
      <path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.3 7.5 9.5 4.3-1.2 7.5-4.9 7.5-9.5V6z" />
      <path d="m9 12 2 2 4-4" />
    </g>,
  );

export const IconShare = ({ size = 13 }: P) =>
  svg(
    size,
    <g {...stroke} strokeWidth={2.4}>
      <path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7" />
      <polyline points="16 6 12 2 8 6" />
      <line x1="12" y1="2" x2="12" y2="15" />
    </g>,
  );
