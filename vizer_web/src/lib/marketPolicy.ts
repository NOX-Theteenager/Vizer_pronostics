/**
 * Marchés que l'on accepte de parier.
 *
 * La valeur par défaut vient du code (`INDICATIVE_ONLY`) ; l'écran Admin peut
 * la surcharger par marché, et la surcharge vit côté serveur pour valoir sur
 * tous les appareils.
 *
 * Ce réglage ne coupe **pas** la prédiction : le modèle continue de prédire,
 * le job continue de publier, la mesure continue de tourner. Couper la
 * prédiction rendrait aveugle sur le marché qu'on surveille justement pour
 * savoir quand le rouvrir.
 */
import { INDICATIVE_ONLY } from '../data/markets';
import type { Sport } from '../types/model';

export type MarketPolicy = Record<string, boolean>;

export interface PolicyFile {
  updated_at: string;
  markets: MarketPolicy;
}

const URL_ = '/api/markets';

/**
 * La route n'existe que derrière nos fonctions.
 *
 * Le garde sur `window` n'est pas décoratif : ce module est aussi chargé par
 * les auto-tests, sous Node, où `import.meta.env` n'existe pas — le lire sans
 * garde fait échouer l'import du module entier.
 */
export const POLICY_AVAILABLE =
  typeof window !== 'undefined' &&
  (import.meta.env?.VITE_DATA_BASE ?? '').startsWith('/');

export const policyKey = (sport: Sport, market: string): string => `${sport}:${market}`;

/** Valeur par défaut d'un marché, avant toute surcharge. */
export function defaultBettable(sport: Sport, market: string): boolean {
  return !INDICATIVE_ONLY[sport].includes(market);
}

/** Un marché est-il pariable, surcharge appliquée ? */
export function isBettable(policy: MarketPolicy, sport: Sport, market: string): boolean {
  const override = policy[policyKey(sport, market)];
  return typeof override === 'boolean' ? override : defaultBettable(sport, market);
}

export async function fetchPolicy(): Promise<PolicyFile> {
  if (!POLICY_AVAILABLE) return { updated_at: '', markets: {} };
  const res = await fetch(URL_, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as PolicyFile;
}

/**
 * Enregistre la politique complète.
 *
 * On envoie le document entier et non un delta : deux appareils qui modifient
 * en même temps se chevaucheraient de toute façon, et un remplacement complet
 * rend l'état final prévisible plutôt que dépendant de l'ordre d'arrivée.
 */
export async function savePolicy(
  adminKey: string,
  markets: MarketPolicy,
): Promise<string | null> {
  if (!POLICY_AVAILABLE) return 'Indisponible sur ce déploiement.';
  if (!adminKey) return 'Clé d’administration absente.';
  try {
    const res = await fetch(URL_, {
      method: 'PUT',
      headers: { 'content-type': 'application/json', 'x-vizer-admin': adminKey },
      body: JSON.stringify({ markets }),
    });
    if (res.ok) return null;
    const body = (await res.json().catch(() => ({}))) as { error?: string };
    return body.error ?? `Échec (HTTP ${res.status})`;
  } catch (e) {
    return e instanceof Error ? e.message : 'Réseau indisponible.';
  }
}
