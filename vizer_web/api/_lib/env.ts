/**
 * Accès aux variables d'environnement côté fonctions.
 *
 * `process` existe dans le runtime Vercel mais pas dans les types DOM du
 * projet, et le build type-vérifie `api/` avant d'émettre : sans déclaration,
 * la fonction est écartée en silence et la route répond 404 sans que le
 * déploiement devienne rouge. C'est arrivé une fois, d'où ce module partagé.
 */
declare const process: { env: Record<string, string | undefined> };

/** Valeur non vide, ou `undefined`. */
export function env(name: string): string | undefined {
  const v = process.env[name];
  return v && v.trim() ? v : undefined;
}

/** Première valeur définie parmi plusieurs noms possibles. */
export function envAny(...names: string[]): string | undefined {
  for (const n of names) {
    const v = env(n);
    if (v) return v;
  }
  return undefined;
}

export const isSet = (name: string): boolean => env(name) !== undefined;
