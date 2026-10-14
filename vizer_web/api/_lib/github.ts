/**
 * Appels GitHub côté serveur.
 *
 * Le jeton vit ici et nulle part ailleurs. Avant, il était collé dans l'écran
 * Admin et conservé dans le `localStorage` du navigateur : un jeton capable
 * d'écrire sur le dépôt, à portée de n'importe quelle extension installée et
 * de toute personne ayant accès à l'appareil.
 */
import { env } from './env.js';

export const REPO = (): string => env('VIZER_REPO') ?? 'NOX-Theteenager/Vizer_pronostics';
export const BRANCH = (): string => env('VIZER_BRANCH') ?? 'models-artifacts';

/**
 * En-têtes d'appel. Sans jeton, GitHub répond quand même sur un dépôt public
 * — avec un quota de 60 requêtes/h par IP, qui est précisément ce que ce
 * détour sert à éviter.
 */
export function ghHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    accept: 'application/vnd.github+json',
    'user-agent': 'vizer-admin',
    'x-github-api-version': '2022-11-28',
  };
  const token = env('VIZER_GITHUB_TOKEN');
  if (token) headers.authorization = `Bearer ${token}`;
  return headers;
}

export const hasToken = (): boolean => env('VIZER_GITHUB_TOKEN') !== undefined;

export function json(body: unknown, status = 200, cache = 'no-store'): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': cache },
  });
}
