import { VizerMark } from '../Shell';

/**
 * Écran de démarrage : un système en orbite (ballon, palet, ballon de foot,
 * balle de baseball) autour du logo. Repris de la maquette v2 — les balles
 * contre-tournent pour rester droites.
 */
export function Splash({ open }: { open: boolean }) {
  if (!open) return null;
  return (
    <div className="vz-splash" role="status" aria-label="Chargement de Vizer">
      <div className="vz-splash__orbit">
        <span className="vz-splash__ring vz-splash__ring--out" />
        <span className="vz-splash__ring vz-splash__ring--in" />

        <div className="vz-splash__carriage">
          <OrbitItem pos="top">
            <svg width="60" height="60" viewBox="0 0 64 64" aria-hidden="true">
              <defs>
                <radialGradient id="spBk" cx="36%" cy="30%" r="74%">
                  <stop offset="0" stopColor="#ffb37a" />
                  <stop offset="1" stopColor="#dd6a29" />
                </radialGradient>
              </defs>
              <circle cx="32" cy="32" r="30" fill="url(#spBk)" />
              <g fill="none" stroke="#7a3512" strokeWidth="2.2" opacity=".85">
                <path d="M2 32h60" />
                <path d="M32 2v60" />
                <path d="M9 11q23 21 0 42" />
                <path d="M55 11q-23 21 0 42" />
              </g>
            </svg>
          </OrbitItem>

          <OrbitItem pos="right">
            <svg width="70" height="45" viewBox="0 0 80 52" aria-hidden="true">
              <ellipse cx="40" cy="36" rx="33" ry="12" fill="#0c0c0f" />
              <rect x="7" y="18" width="66" height="18" fill="#1b1b21" />
              <ellipse cx="40" cy="18" rx="33" ry="12" fill="#2d2d35" />
              <ellipse
                cx="40"
                cy="18"
                rx="33"
                ry="12"
                fill="none"
                stroke="#54c8f0"
                strokeWidth="1.8"
                opacity=".75"
              />
            </svg>
          </OrbitItem>

          <OrbitItem pos="bottom">
            <svg width="60" height="60" viewBox="0 0 64 64" aria-hidden="true">
              <circle cx="32" cy="32" r="30" fill="#f4f3ee" />
              <polygon points="32,20 40,26 37,36 27,36 24,26" fill="#17171b" />
              <g fill="none" stroke="#17171b" strokeWidth="2.2">
                <path d="M32 20 32 5" />
                <path d="M40 26 53 18" />
                <path d="M37 36 46 49" />
                <path d="M27 36 18 49" />
                <path d="M24 26 11 18" />
              </g>
              <circle cx="32" cy="32" r="30" fill="none" stroke="#c9c7bf" strokeWidth="1.5" />
            </svg>
          </OrbitItem>

          <OrbitItem pos="left">
            <svg width="58" height="58" viewBox="0 0 64 64" aria-hidden="true">
              <circle cx="32" cy="32" r="30" fill="#f9f6ee" />
              <g fill="none" stroke="#c0392b" strokeWidth="2.2" strokeLinecap="round">
                <path d="M13 8 Q23 32 13 56" />
                <path d="M51 8 Q41 32 51 56" />
              </g>
              <circle cx="32" cy="32" r="30" fill="none" stroke="#dcd9cf" strokeWidth="1.4" />
            </svg>
          </OrbitItem>
        </div>

        <div className="vz-splash__core">
          <VizerMark size={88} />
        </div>
      </div>

      <div className="vz-splash__word">
        <div>VIZER</div>
        <small>GAGNE, MATCH APRÈS MATCH</small>
      </div>

      <div className="vz-splash__dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
    </div>
  );
}

function OrbitItem({ pos, children }: { pos: string; children: React.ReactNode }) {
  return (
    <div className={`vz-splash__slot vz-splash__slot--${pos}`}>
      <div className="vz-splash__counter">{children}</div>
    </div>
  );
}
