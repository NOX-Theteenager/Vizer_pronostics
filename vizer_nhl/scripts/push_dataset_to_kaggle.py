#!/usr/bin/env python3
"""
push_dataset_to_kaggle.py — Rafraîchit les données NHL et versionne le dataset
Kaggle `vizer-nhl-data`.

Pourquoi ce script tourne sur un PC et pas dans le cloud :
    Moneypuck refuse `all_teams.csv` depuis les IP de datacenter (403), alors
    que le même fichier se télécharge sans problème depuis une connexion
    résidentielle. Ce n'est pas une question de User-Agent : l'UA par défaut de
    requests passe très bien depuis le PC. Seul ce fichier est protégé — les
    archives de saison (skaters/lines/goalies), servies depuis un autre chemin,
    se téléchargent toujours depuis Kaggle.

    Or `all_teams.csv` est la table des matchs, donc la base de l'agrégat. Sans
    elle, le kernel hebdomadaire réentraîne les modèles sur un jeu figé : au
    13 octobre 2026, le dernier match connu datait encore du 5 octobre alors
    que les statistiques joueurs, elles, étaient à jour. L'écart grandit à
    chaque semaine de saison.

    Même raison que pour NBA (stats.nba.com bloque aussi les IP datacenter),
    d'où deux scripts jumeaux : vizer_nba/scripts/push_dataset_to_kaggle.py.

Étapes :
  1. Note la date du dernier match connu (dataset_agrege_vizer_nhl.csv)
  2. Exécute update_data.py --mode update (Moneypuck + ré-agrégation)
  3. Si aucun match plus récent → stop (rien à versionner)
  4. Stage les fichiers DÉJÀ PUBLIÉS dans le dataset, rafraîchis depuis data/
  5. `kaggle datasets version` → nouvelle version du dataset

Sur le jeu de fichiers publié :
    `kaggle datasets version` remplace l'intégralité du contenu du dataset. Le
    script repart donc de la liste des fichiers actuellement publiés et les
    republie tous : omettre un fichier revient à le supprimer. Il n'ajoute
    jamais de lui-même les historiques volumineux (skaters_2008_2024.csv,
    2,5 Go ; shots_2007-2024.csv, 1,1 Go) — pour les faire entrer dans le
    dataset, les ajouter explicitement avec --include-historical une fois.

Usage :
    python scripts/push_dataset_to_kaggle.py               # fetch + upload si nouveauté
    python scripts/push_dataset_to_kaggle.py --skip-fetch  # upload seul
    python scripts/push_dataset_to_kaggle.py --force       # upload même sans nouveau match
    python scripts/push_dataset_to_kaggle.py --dry-run     # tout sauf l'upload
    python scripts/push_dataset_to_kaggle.py --include-historical  # + les gros fichiers

Prérequis :
  - ~/.kaggle/kaggle.json (pour le username)
  - un jeton Kaggle KGAT_… dans ~/.kaggle/access_token ou $KAGGLE_API_TOKEN.
    `kaggle datasets version` est une ÉCRITURE : depuis octobre 2026 Kaggle la
    refuse en 403 si l'authentification passe par l'ancienne clé en Basic.
    En cas de doute : python ../kaggle/diagnose_auth.py
  - pip install "kaggle~=2.2" (présent dans le venv du projet)

Cron hebdomadaire (dimanche 21h30, après NBA et avant le training du lundi 4h UTC) :
    30 21 * * 0  cd ~/Documents/Projets/Vizer_pronostics/vizer_nhl && ../venv/bin/python scripts/push_dataset_to_kaggle.py >> logs/push_dataset.log 2>&1
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Le script vit dans vizer_nhl/scripts/ ; tout se passe depuis vizer_nhl/.
PKG_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PKG_DIR / "data"

DATASET_SLUG = "vizer-nhl-data"

# Toujours publiés, quoi qu'il arrive :
#   all_teams.csv                → c'est la raison d'être de ce script
#   dataset_agrege_vizer_nhl.csv → ce que télécharge le job de prédictions,
#                                  et ce sur quoi le kernel s'entraîne
#   period_stats.csv             → buts par période ; permet au kernel de
#                                  retrouver le mode P1 « dedicated » s'il doit
#                                  reconstruire l'agrégat (sinon approximation
#                                  à 30 %). 6 Mo, autant l'avoir.
REQUIRED_FILES = [
    "all_teams.csv",
    "dataset_agrege_vizer_nhl.csv",
    "period_stats.csv",
]

# Historiques volumineux : jamais ajoutés automatiquement (3,6 Go à eux deux).
HISTORICAL_FILES = ["skaters_2008_2024.csv", "shots_2007-2024.csv"]


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def last_game_date() -> str | None:
    """Date du dernier match dans l'agrégat, ou None.

    Même colonne que le garde-fou de l'étape 6 du kernel, pour que les deux
    côtés jugent la fraîcheur de la même façon.
    """
    agrege = DATA_DIR / "dataset_agrege_vizer_nhl.csv"
    if not agrege.exists():
        return None
    import pandas as pd
    try:
        return str(pd.read_csv(agrege, usecols=["gameDate_home"])["gameDate_home"].max())
    except Exception as e:
        log(f"⚠️  Lecture de gameDate_home impossible ({e})")
        return None


def run_update() -> None:
    """Télécharge la saison courante depuis Moneypuck et ré-agrège."""
    log("→ update_data.py --mode update")
    result = subprocess.run(
        [sys.executable, "update_data.py", "--mode", "update"], cwd=PKG_DIR
    )
    if result.returncode != 0:
        raise RuntimeError(f"update_data.py a échoué (code {result.returncode})")


def kaggle_username() -> str:
    """Username Kaggle : env var, sinon ~/.kaggle/kaggle.json."""
    if os.environ.get("KAGGLE_USERNAME"):
        return os.environ["KAGGLE_USERNAME"]
    cred_file = Path.home() / ".kaggle" / "kaggle.json"
    if cred_file.exists():
        return json.loads(cred_file.read_text())["username"]
    raise RuntimeError(
        "Credentials Kaggle introuvables : ni $KAGGLE_USERNAME ni ~/.kaggle/kaggle.json"
    )


def kaggle_cli() -> list[str]:
    """Commande CLI Kaggle : binaire `kaggle` si dispo, sinon `python -m kaggle`."""
    if shutil.which("kaggle"):
        return ["kaggle"]
    return [sys.executable, "-m", "kaggle"]


def published_files(username: str) -> list[str]:
    """Noms des fichiers actuellement publiés dans le dataset.

    Sert à ne jamais republier un jeu amputé. En cas d'échec de l'appel, on
    retombe sur REQUIRED_FILES plutôt que de deviner : mieux vaut un upload
    refusé par le garde-fou qu'un dataset tronqué.
    """
    cmd = kaggle_cli() + ["datasets", "files", f"{username}/{DATASET_SLUG}", "--csv"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"⚠️  Liste des fichiers publiés indisponible : "
            f"{(result.stderr or result.stdout).strip()[:200]}")
        return []
    names = []
    for row in csv.DictReader(io.StringIO(result.stdout)):
        name = (row.get("name") or "").strip()
        if name.endswith(".csv"):
            names.append(name)
    return names


def select_files(username: str, include_historical: bool) -> list[str]:
    """Jeu de fichiers à publier : ce qui l'est déjà, plus les indispensables."""
    selected = set(published_files(username)) | set(REQUIRED_FILES)
    if include_historical:
        selected |= set(HISTORICAL_FILES)
    else:
        # Jamais ajoutés d'office, mais conservés s'ils sont déjà publiés
        # (les retirer ici les effacerait du dataset).
        pass
    return sorted(selected)


def push_dataset(include_historical: bool, dry_run: bool = False) -> None:
    username = kaggle_username()
    names = select_files(username, include_historical)

    missing = [f for f in names if not (DATA_DIR / f).exists()]
    if missing:
        # Un fichier absent du staging serait SUPPRIMÉ du dataset par la
        # nouvelle version — on refuse plutôt que de dégrader le dataset.
        raise RuntimeError(
            f"Fichier(s) publié(s) mais absent(s) de data/ : {missing} — upload "
            f"annulé pour ne pas les effacer du dataset."
        )

    with tempfile.TemporaryDirectory(prefix="vizer_nhl_dataset_") as stage:
        stage_path = Path(stage)
        total_mb = 0.0
        for name in names:
            src = DATA_DIR / name
            size_mb = src.stat().st_size / 1024 ** 2
            # Lien physique si possible : copier 1 Go pour rien est inutile.
            dest = stage_path / name
            try:
                os.link(src, dest)
            except OSError:
                shutil.copy2(src, dest)
            total_mb += size_mb
            log(f"  + {name} ({size_mb:.1f} Mo)")

        (stage_path / "dataset-metadata.json").write_text(json.dumps({
            "id": f"{username}/{DATASET_SLUG}",
            "title": DATASET_SLUG,
        }))

        log(f"Total à envoyer : {total_mb:.0f} Mo")
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        cmd = kaggle_cli() + [
            "datasets", "version",
            "-p", str(stage_path),
            "-m", f"maj auto depuis PC {stamp}",
            "-q",
        ]
        if dry_run:
            log(f"[dry-run] {' '.join(cmd)}")
            return
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise RuntimeError(f"kaggle datasets version a échoué (code {result.returncode})")
        log(f"✅ Nouvelle version de {username}/{DATASET_SLUG} publiée ({total_mb:.0f} Mo).")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rafraîchit les données NHL et versionne le dataset Kaggle."
    )
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Ne pas re-télécharger, uploader les CSVs actuels")
    parser.add_argument("--force", action="store_true",
                        help="Uploader même si aucun match plus récent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Tout faire sauf l'upload Kaggle")
    parser.add_argument("--include-historical", action="store_true",
                        help=f"Ajouter aussi {', '.join(HISTORICAL_FILES)} (3,6 Go)")
    args = parser.parse_args()

    log(f"═══ push_dataset_to_kaggle — {DATASET_SLUG} ═══")

    before = last_game_date()
    log(f"Dernier match connu : {before or 'inconnu'}")

    if not args.skip_fetch:
        run_update()
        after = last_game_date()
        log(f"Dernier match après fetch : {after or 'inconnu'}")
        if not args.force and before is not None and after is not None and after <= before:
            log("⊘ Aucun match plus récent (hors-saison ?) — pas de nouvelle version.")
            return 0

    push_dataset(include_historical=args.include_historical, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        log(f"❌ {e}")
        sys.exit(1)
