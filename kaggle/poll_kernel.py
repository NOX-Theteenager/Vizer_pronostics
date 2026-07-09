#!/usr/bin/env python3
"""
poll_kernel.py — Interroge le statut d'un kernel Kaggle jusqu'à sa fin.

Usage (appelé par GitHub Actions) :
    python kaggle/poll_kernel.py <username> <kernel_slug> [max_wait_seconds]

Arguments :
    username          → nom d'utilisateur Kaggle (ex: nox-theteenager)
    kernel_slug       → slug du kernel (ex: vizer-training-pipeline)
    max_wait_seconds  → timeout en secondes (défaut: 7200 = 2h)

Codes de retour :
    0 → kernel terminé avec succès ("complete")
    1 → kernel échoué ("error", "cancelAcknowledged") ou timeout
    2 → erreur d'utilisation (arguments manquants)
"""
import re
import sys
import time
import subprocess


# Statuts terminaux reconnus par Kaggle
_TERMINAL_OK  = {"complete"}
_TERMINAL_ERR = {"error", "cancelacknowledged", "cancelled", "cancel_acknowledged"}
_POLL_INTERVAL = 60   # secondes entre chaque vérification


def get_kernel_status(username: str, slug: str) -> str:
    """
    Interroge la CLI Kaggle pour obtenir le statut courant du kernel.

    Retourne une chaîne normalisée en minuscules :
      "queued" | "running" | "complete" | "error" | "cancelacknowledged" | "unknown"

    Lève RuntimeError si la CLI échoue ou si la sortie est vide.

    Compatibilité :
      - CLI v2.x  : `owner/slug has status "KernelWorkerStatus.COMPLETE"`
      - CLI v1.6+ : lignes "key: value" (--csv supprimé)
      - CLI v1.5  : CSV header+data (fallback par mots-clés conservé)
    """
    result = subprocess.run(
        ["kaggle", "kernels", "status", f"{username}/{slug}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Échec CLI Kaggle (code {result.returncode}): {err}")

    output = result.stdout.strip()
    if not output:
        raise RuntimeError("La CLI Kaggle a retourné une réponse vide.")

    # Format v2.x : owner/slug has status "KernelWorkerStatus.COMPLETE"
    m = re.search(r'has status "(?:KernelWorkerStatus\.)?([A-Za-z_]+)"', output)
    if m:
        return m.group(1).lower()

    # Format v1.6+ : lignes "key: value"
    # Ex: "statusData: running" ou "status_data: running"
    for line in output.splitlines():
        line = line.strip()
        for key in ("statusdata", "status_data", "status"):
            if line.lower().startswith(key + ":"):
                return line.split(":", 1)[1].strip().lower()

    # Fallback : chercher le statut par mot-clé dans la sortie brute
    output_lower = output.lower()
    for s in ["complete", "running", "queued", "error", "cancel_acknowledged", "cancelacknowledged"]:
        if s in output_lower:
            return s

    # Debug : afficher la sortie brute si on ne reconnaît rien
    print(f"[DEBUG] Sortie brute kaggle kernels status :\n{output}", file=sys.stderr)
    return "unknown"


def poll(username: str, slug: str, max_wait: int = 7200) -> int:
    """
    Boucle de polling principal.

    Retourne 0 si le kernel se termine avec succès, 1 sinon.
    """
    elapsed   = 0
    last_status = ""

    print(f"Polling {username}/{slug} — timeout max: {max_wait}s ({max_wait//60} min)")
    print(f"{'─'*60}")

    while elapsed < max_wait:
        try:
            status = get_kernel_status(username, slug)
        except RuntimeError as e:
            # Erreur réseau ou API — on loggue et on réessaie
            elapsed_fmt = f"{elapsed // 60:02d}m{elapsed % 60:02d}s"
            print(f"  [{elapsed_fmt}] Erreur API (nouvelle tentative dans {_POLL_INTERVAL}s) : {e}")
            time.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
            continue

        elapsed_fmt = f"{elapsed // 60:02d}m{elapsed % 60:02d}s"

        # N'afficher que si le statut change (moins de bruit dans les logs)
        if status != last_status:
            print(f"  [{elapsed_fmt}] Statut : {status}", flush=True)
            last_status = status

        # ── Terminaison réussie ────────────────────────────────────────────
        if status in _TERMINAL_OK:
            print(f"\n  ✅  Kernel terminé avec succès en {elapsed_fmt}.")
            return 0

        # ── Terminaison en erreur ──────────────────────────────────────────
        if status in _TERMINAL_ERR:
            print(f"\n  ❌  Kernel échoué : {status} (après {elapsed_fmt}).")
            print(
                f"  Pour voir les logs : "
                f"kaggle kernels output {username}/{slug} -p /tmp/kernel_logs"
            )
            return 1

        # ── Statut transitoire (queued, running, …) → on attend ───────────
        time.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL

    # ── Timeout ───────────────────────────────────────────────────────────────
    print(
        f"\n  ⏰  Timeout atteint ({max_wait}s). "
        f"Le kernel est toujours en cours ({last_status})."
    )
    print(
        f"  Tu peux suivre manuellement : "
        f"https://www.kaggle.com/{username}/{slug}"
    )
    return 1


# ─── Point d'entrée ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: poll_kernel.py <username> <kernel_slug> [max_wait_seconds]")
        sys.exit(2)

    _username  = sys.argv[1]
    _slug      = sys.argv[2]
    _max_wait  = int(sys.argv[3]) if len(sys.argv) > 3 else 7200

    sys.exit(poll(_username, _slug, _max_wait))
