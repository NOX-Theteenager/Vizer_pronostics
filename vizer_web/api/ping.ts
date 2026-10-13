/**
 * Sonde de diagnostic — vérifie que les fonctions de `api/` sont bien émises.
 *
 * Temporaire : à supprimer une fois le proxy confirmé.
 */
export default function handler(): Response {
  return new Response(JSON.stringify({ ok: true, runtime: 'node' }), {
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
}
