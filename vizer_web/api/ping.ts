/**
 * Sonde de diagnostic — vérifie que les fonctions de `api/` sont bien émises
 * et routées. Temporaire.
 */
export function GET(): Response {
  return new Response(JSON.stringify({ ok: true }), {
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
}
