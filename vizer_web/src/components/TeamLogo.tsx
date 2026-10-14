import { useState } from 'react';
import { teamColor, teamName } from '../data/teams';
import { readableOn } from '../lib/contrast';
import type { Sport } from '../types/model';

/**
 * Logo d'équipe, avec repli sur le monogramme coloré.
 *
 * Les fichiers viennent de `public/logos/<sport>/<CODE>.png`, récupérés une
 * fois par `npm run logos` et servis depuis notre origine : pas de requête
 * vers un CDN tiers à chaque écran, et le service worker les met en cache
 * comme le reste de l'app.
 *
 * Le repli n'est pas décoratif. Une franchise nouvelle ou renommée peut ne pas
 * avoir de fichier, et la pastille monogramme — celle que l'app utilisait
 * avant — reprend alors la main sans que rien ne casse. C'est aussi ce qui
 * s'affiche si l'utilisateur bloque les images.
 */
export function TeamLogo({
  sport,
  code,
  size = 32,
  title,
}: {
  sport: Sport;
  code: string;
  size?: number;
  /** Remplace le nom de l'équipe comme texte alternatif. */
  title?: string;
}) {
  const [failed, setFailed] = useState(false);
  const label = title ?? `${teamName(sport, code)} (${code})`;

  if (failed || !code) {
    const bg = teamColor(sport, code);
    return (
      <span
        className="vz-pastille"
        style={{
          width: size,
          height: size,
          background: bg,
          color: readableOn(bg),
          fontSize: Math.round(size * 0.3),
          borderRadius: Math.max(8, Math.round(size * 0.34)),
        }}
        title={label}
      >
        {code}
      </span>
    );
  }

  return (
    <img
      className="vz-teamlogo"
      src={`${import.meta.env.BASE_URL}logos/${sport}/${code}.png`}
      width={size}
      height={size}
      alt={label}
      title={label}
      loading="lazy"
      decoding="async"
      draggable={false}
      onError={() => setFailed(true)}
    />
  );
}
