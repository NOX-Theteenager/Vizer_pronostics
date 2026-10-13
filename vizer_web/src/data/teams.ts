/**
 * Registre des équipes — couleur principale, ville et surnom.
 *
 * Couleurs : design.md §6.4, reprises à l'identique. Elles servent aux
 * pastilles monogrammes (§5.5) et aux dégradés de carte (§3.4).
 * Aucun logo officiel n'est utilisé (droits).
 */
import type { Sport } from '../types/model';

export interface Team {
  code: string;
  city: string;
  /** Surnom — c'est ce qu'affichent les cartes liste (« Maple Leafs »). */
  name: string;
  color: string;
}

const NHL: Record<string, Omit<Team, 'code'>> = {
  ANA: { city: 'Anaheim', name: 'Ducks', color: '#F47A38' },
  ARI: { city: 'Arizona', name: 'Coyotes', color: '#8C2633' },
  BOS: { city: 'Boston', name: 'Bruins', color: '#FFB81C' },
  BUF: { city: 'Buffalo', name: 'Sabres', color: '#003087' },
  CAR: { city: 'Caroline', name: 'Hurricanes', color: '#CC0000' },
  CBJ: { city: 'Columbus', name: 'Blue Jackets', color: '#002654' },
  CGY: { city: 'Calgary', name: 'Flames', color: '#D2001C' },
  CHI: { city: 'Chicago', name: 'Blackhawks', color: '#CF0A2C' },
  COL: { city: 'Colorado', name: 'Avalanche', color: '#6F263D' },
  DAL: { city: 'Dallas', name: 'Stars', color: '#006847' },
  DET: { city: 'Détroit', name: 'Red Wings', color: '#CE1126' },
  EDM: { city: 'Edmonton', name: 'Oilers', color: '#FF4C00' },
  FLA: { city: 'Floride', name: 'Panthers', color: '#C8102E' },
  LAK: { city: 'Los Angeles', name: 'Kings', color: '#A2AAAD' },
  MIN: { city: 'Minnesota', name: 'Wild', color: '#154734' },
  MTL: { city: 'Montréal', name: 'Canadiens', color: '#AF1E2D' },
  NJD: { city: 'New Jersey', name: 'Devils', color: '#CE1126' },
  NSH: { city: 'Nashville', name: 'Predators', color: '#FFB81C' },
  NYI: { city: 'New York', name: 'Islanders', color: '#00539B' },
  NYR: { city: 'New York', name: 'Rangers', color: '#0038A8' },
  OTT: { city: 'Ottawa', name: 'Senators', color: '#C52032' },
  PHI: { city: 'Philadelphie', name: 'Flyers', color: '#F74902' },
  PIT: { city: 'Pittsburgh', name: 'Penguins', color: '#FCB514' },
  SEA: { city: 'Seattle', name: 'Kraken', color: '#99D9D9' },
  SJS: { city: 'San Jose', name: 'Sharks', color: '#006D75' },
  STL: { city: 'St. Louis', name: 'Blues', color: '#002F87' },
  TBL: { city: 'Tampa Bay', name: 'Lightning', color: '#002868' },
  TOR: { city: 'Toronto', name: 'Maple Leafs', color: '#00205B' },
  VAN: { city: 'Vancouver', name: 'Canucks', color: '#00843D' },
  VGK: { city: 'Vegas', name: 'Golden Knights', color: '#B4975A' },
  WPG: { city: 'Winnipeg', name: 'Jets', color: '#041E42' },
  WSH: { city: 'Washington', name: 'Capitals', color: '#C8102E' },
  // Hors liste design.md §6.4 : la franchise d'Arizona a déménagé, le backend
  // peut émettre UTA. Sans entrée, la pastille retomberait sur le gris neutre.
  UTA: { city: 'Utah', name: 'Mammoth', color: '#71AFE5' },
};

const NBA: Record<string, Omit<Team, 'code'>> = {
  ATL: { city: 'Atlanta', name: 'Hawks', color: '#E03A3E' },
  BKN: { city: 'Brooklyn', name: 'Nets', color: '#1a1a1a' },
  BOS: { city: 'Boston', name: 'Celtics', color: '#007A33' },
  CHA: { city: 'Charlotte', name: 'Hornets', color: '#1D1160' },
  CHI: { city: 'Chicago', name: 'Bulls', color: '#CE1141' },
  CLE: { city: 'Cleveland', name: 'Cavaliers', color: '#860038' },
  DAL: { city: 'Dallas', name: 'Mavericks', color: '#00538C' },
  DEN: { city: 'Denver', name: 'Nuggets', color: '#0E2240' },
  DET: { city: 'Détroit', name: 'Pistons', color: '#C8102E' },
  GSW: { city: 'Golden State', name: 'Warriors', color: '#1D428A' },
  HOU: { city: 'Houston', name: 'Rockets', color: '#CE1141' },
  IND: { city: 'Indiana', name: 'Pacers', color: '#002D62' },
  LAC: { city: 'Los Angeles', name: 'Clippers', color: '#C8102E' },
  LAL: { city: 'Los Angeles', name: 'Lakers', color: '#552583' },
  MEM: { city: 'Memphis', name: 'Grizzlies', color: '#5D76A9' },
  MIA: { city: 'Miami', name: 'Heat', color: '#98002E' },
  MIL: { city: 'Milwaukee', name: 'Bucks', color: '#00471B' },
  MIN: { city: 'Minnesota', name: 'Timberwolves', color: '#0C2340' },
  NOP: { city: 'La Nouvelle-Orléans', name: 'Pelicans', color: '#85714D' },
  NYK: { city: 'New York', name: 'Knicks', color: '#006BB6' },
  OKC: { city: 'Oklahoma City', name: 'Thunder', color: '#007AC1' },
  ORL: { city: 'Orlando', name: 'Magic', color: '#0077C0' },
  PHI: { city: 'Philadelphie', name: '76ers', color: '#006BB6' },
  PHX: { city: 'Phoenix', name: 'Suns', color: '#E56020' },
  POR: { city: 'Portland', name: 'Trail Blazers', color: '#E03A3E' },
  SAC: { city: 'Sacramento', name: 'Kings', color: '#5A2D81' },
  SAS: { city: 'San Antonio', name: 'Spurs', color: '#C4CED4' },
  TOR: { city: 'Toronto', name: 'Raptors', color: '#CE1141' },
  UTA: { city: 'Utah', name: 'Jazz', color: '#002B5C' },
  WAS: { city: 'Washington', name: 'Wizards', color: '#002B5C' },
};

const REGISTRY: Record<Sport, Record<string, Omit<Team, 'code'>>> = {
  nhl: NHL,
  nba: NBA,
};

/** Neutre pour un code inconnu : l'app affiche le match, pas une erreur. */
const FALLBACK_COLOR = '#5b667a';

export function getTeam(sport: Sport, code: string): Team {
  const entry = REGISTRY[sport]?.[code?.toUpperCase?.() ?? ''];
  if (!entry) {
    return { code, city: '', name: code, color: FALLBACK_COLOR };
  }
  return { code, ...entry };
}

export function teamColor(sport: Sport, code: string): string {
  return getTeam(sport, code).color;
}

/** « Maple Leafs » — pour les listes. */
export function teamName(sport: Sport, code: string): string {
  return getTeam(sport, code).name;
}

/** « Toronto Maple Leafs » — pour le header de détail (design.md §4.2). */
export function teamFullName(sport: Sport, code: string): string {
  const t = getTeam(sport, code);
  return t.city ? `${t.city} ${t.name}` : t.name;
}
