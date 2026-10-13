#!/usr/bin/env python3
"""
diagnose_auth.py — Pourquoi l'API Kaggle refuse une écriture.

La CLI Kaggle avale le corps des réponses d'erreur : elle n'affiche que
« 403 Client Error: Forbidden for url: ... », ce qui ne permet pas de
distinguer une clé invalide, une permission manquante et un blocage au bord
du réseau. Ce script rejoue les mêmes appels et imprime le corps complet.

Le script essaie les DEUX modes d'authentification que le SDK accepte, parce
que c'est précisément là qu'est le piège : Kaggle a cessé d'accepter le mode
hérité pour les écritures, mais continue de l'accepter pour les lectures. Un
pipeline qui ne fait que lire reste donc vert pendant que les écritures sont
refusées.

  - Bearer      : Authorization: Bearer <jeton>. C'est ce qu'utilise la CLI
                  quand elle trouve KAGGLE_API_TOKEN ou ~/.kaggle/access_token.
  - Basic       : couple (username, key) de ~/.kaggle/kaggle.json. Mode hérité.

Ce qu'il faut lire :
  - Bearer OK, Basic 403 en écriture  → le cas normal depuis octobre 2026 :
                                        il faut passer le jeton en Bearer.
  - 401 partout                       → jeton invalide ou révoqué.
  - Bearer 403 aussi                  → permission applicative (compte,
                                        quota, namespace) ou blocage réseau ;
                                        un corps vide ou HTML indique le
                                        second.

Usage :
    python kaggle/diagnose_auth.py [username]

Lit KAGGLE_USERNAME / KAGGLE_KEY, sinon ~/.kaggle/kaggle.json.
N'écrit rien sur Kaggle : le POST de test est volontairement vide, donc
rejeté avant toute modification.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

BASE = "https://api.kaggle.com/v1"
TIMEOUT = 30


def load_credentials() -> tuple[str, str, str]:
    """Retourne (username, key, provenance)."""
    user, key = os.environ.get("KAGGLE_USERNAME"), os.environ.get("KAGGLE_KEY")
    if user and key:
        return user, key, "variables d'environnement"
    cred = Path.home() / ".kaggle" / "kaggle.json"
    if cred.exists():
        d = json.loads(cred.read_text())
        return d["username"], d["key"], str(cred)
    print("❌ Aucun identifiant : ni KAGGLE_USERNAME/KAGGLE_KEY ni ~/.kaggle/kaggle.json")
    raise SystemExit(2)


def describe_key(key: str) -> str:
    """Empreinte non réversible, pour comparer deux environnements sans
    exposer la clé dans des logs publics."""
    import hashlib
    return (f"longueur={len(key)} sha256[:12]="
            f"{hashlib.sha256(key.encode()).hexdigest()[:12]}")


class BearerAuth(requests.auth.AuthBase):
    """Le SDK Kaggle envoie le jeton en Bearer ; requests ne sait pas le faire
    nativement, d'où cette classe (identique à celle de kagglesdk)."""

    def __init__(self, token: str):
        self.token = token

    def __call__(self, r):
        r.headers["Authorization"] = f"Bearer {self.token}"
        return r


def call(label: str, url: str, auth, payload: dict) -> None:
    print(f"\n── {label}")
    print(f"   POST {url}")
    try:
        r = requests.post(url, json=payload, auth=auth, timeout=TIMEOUT,
                          headers={"Content-Type": "application/json"})
    except Exception as e:
        print(f"   ⚠️  Requête impossible : {type(e).__name__}: {e}")
        return

    ctype = r.headers.get("Content-Type", "?")
    print(f"   → HTTP {r.status_code} | Content-Type: {ctype}")
    for h in ("Server", "Via", "Cf-Ray", "X-Cloud-Trace-Context", "Www-Authenticate"):
        if h in r.headers:
            print(f"   → {h}: {r.headers[h]}")
    body = (r.text or "").strip()
    if not body:
        print("   → corps VIDE (signature d'un refus au bord du réseau)")
    else:
        print(f"   → corps ({len(body)} octets) :")
        for line in body[:1500].splitlines():
            print(f"      {line}")
        if len(body) > 1500:
            print(f"      … tronqué, {len(body) - 1500} octets restants")


def main(argv: list[str]) -> int:
    user, key, origin = load_credentials()
    target = argv[0] if argv else user

    print("=" * 70)
    print("DIAGNOSTIC D'AUTHENTIFICATION KAGGLE")
    print("=" * 70)
    print(f"  Identifiants  : {origin}")
    print(f"  Username      : {user}")
    print(f"  Clé           : {describe_key(key)}")
    print(f"  Namespace visé: {target}")

    if key.startswith("KGAT_"):
        print("  Format        : jeton KGAT_ (nouvelle génération)")
    else:
        print("  Format        : clé héritée (pas de préfixe KGAT_) — le mode "
              "Bearer échouera probablement")

    modes = [
        ("Bearer", BearerAuth(key)),
        ("Basic (hérité)", (user, key)),
    ]
    read_url = f"{BASE}/kernels.KernelsApiService/ListKernels"
    # Corps volontairement vide : une 400 signifie « autorisé mais requête
    # incomplète », donc l'écriture passe. Une 403 signifie refus. Rien n'est
    # modifié sur Kaggle dans les deux cas.
    write_url = f"{BASE}/kernels.KernelsApiService/SaveKernel"

    for name, auth in modes:
        print("\n" + "─" * 70)
        print(f"MODE {name}")
        print("─" * 70)
        call(f"LECTURE — ListKernels [{name}]", read_url, auth,
             {"page_size": 1, "mine": True})
        call(f"ÉCRITURE — SaveKernel [{name}]", write_url, auth, {})

    print("\n" + "=" * 70)
    print("Relire l'en-tête de ce fichier pour interpréter les codes.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
