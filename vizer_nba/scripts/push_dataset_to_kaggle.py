#!/usr/bin/env python3
"""
push_dataset_to_kaggle.py — Rafraîchit les données NBA et versionne le dataset
Kaggle `vizer-nba-data`.

Pourquoi ce script tourne sur un PC (ou un Raspberry Pi) et pas dans le cloud :
stats.nba.com bloque les IP de datacenters (GitHub Actions, Kaggle). Il faut
une IP résidentielle pour le fetch. L'upload vers Kaggle, lui, passe partout.

Étapes :
  1. Note la date du dernier match connu (data/NBA_GAMES.csv)
  2. Exécute les scripts fetch_nba_*.py (équipes, joueurs, matchs, stats joueurs)
  3. Si aucun match plus récent n'est apparu → stop (rien à versionner)
  4. Copie les 5 CSVs dans un dossier de staging + dataset-metadata.json
  5. `kaggle datasets version` → nouvelle version du dataset

Usage :
    python scripts/push_dataset_to_kaggle.py               # fetch + upload si nouveauté
    python scripts/push_dataset_to_kaggle.py --skip-fetch  # upload seul (données déjà à jour)
    python scripts/push_dataset_to_kaggle.py --force       # upload même sans nouveau match
    python scripts/push_dataset_to_kaggle.py --dry-run     # tout sauf l'upload

Prérequis :
  - ~/.kaggle/kaggle.json (ou KAGGLE_USERNAME/KAGGLE_KEY en env)
  - pip install "kaggle~=2.2" (présent dans le venv du projet)

Cron hebdomadaire (dimanche 21h, avant le training du lundi 4h UTC) :
    0 21 * * 0  cd ~/Documents/Projets/Vizer_pronostics/vizer_nba && ../venv/bin/python scripts/push_dataset_to_kaggle.py >> logs/push_dataset.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Le script vit dans vizer_nba/scripts/ ; tout se passe depuis vizer_nba/.
PKG_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PKG_DIR / "data"

DATASET_SLUG = "vizer-nba-data"
DATASET_FILES = [
    "NBA_TEAMS.csv",
    "NBA_PLAYERS.csv",
    "NBA_ACTIVE_PLAYERS.csv",
    "NBA_GAMES.csv",
    "NBA_PLAYER_GAMES.csv",
]
FETCH_SCRIPTS = [
    "scripts/fetch_nba_teams.py",
    "scripts/fetch_nba_players.py",
    "scripts/fetch_nba_games.py",
    "scripts/fetch_nba_player_games.py",
]


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def last_game_date() -> str | None:
    """Date (str ISO) du dernier match dans NBA_GAMES.csv, ou None."""
    games = DATA_DIR / "NBA_GAMES.csv"
    if not games.exists():
        return None
    import pandas as pd
    try:
        return str(pd.read_csv(games, usecols=["GAME_DATE"])["GAME_DATE"].max())
    except Exception as e:
        log(f"⚠️  Lecture de GAME_DATE impossible ({e})")
        return None


def run_fetch_scripts() -> None:
    """Exécute les 4 scripts de fetch depuis vizer_nba/ (chemins relatifs data/)."""
    for script in FETCH_SCRIPTS:
        log(f"→ {script}")
        result = subprocess.run([sys.executable, script], cwd=PKG_DIR)
        if result.returncode != 0:
            raise RuntimeError(f"{script} a échoué (code {result.returncode})")


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


def push_dataset(dry_run: bool = False) -> None:
    """Stage les 5 CSVs et publie une nouvelle version du dataset."""
    missing = [f for f in DATASET_FILES if not (DATA_DIR / f).exists()]
    if missing:
        # Un fichier absent du staging serait SUPPRIMÉ du dataset par la
        # nouvelle version — on refuse plutôt que de dégrader le dataset.
        raise RuntimeError(f"Fichier(s) manquant(s) dans data/ : {missing} — upload annulé")

    username = kaggle_username()
    with tempfile.TemporaryDirectory(prefix="vizer_nba_dataset_") as stage:
        stage_path = Path(stage)
        total_mb = 0.0
        for name in DATASET_FILES:
            src = DATA_DIR / name
            shutil.copy2(src, stage_path / name)
            total_mb += src.stat().st_size / 1024 ** 2
            log(f"  + {name} ({src.stat().st_size / 1024 ** 2:.1f} Mo)")

        (stage_path / "dataset-metadata.json").write_text(json.dumps({
            "id": f"{username}/{DATASET_SLUG}",
            "title": DATASET_SLUG,
        }))

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
        description="Rafraîchit les données NBA et versionne le dataset Kaggle."
    )
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Ne pas re-télécharger, uploader les CSVs actuels")
    parser.add_argument("--force", action="store_true",
                        help="Uploader même si aucun match plus récent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Tout faire sauf l'upload Kaggle")
    args = parser.parse_args()

    log(f"═══ push_dataset_to_kaggle — {DATASET_SLUG} ═══")

    before = last_game_date()
    log(f"Dernier match connu : {before or 'inconnu'}")

    if not args.skip_fetch:
        run_fetch_scripts()
        after = last_game_date()
        log(f"Dernier match après fetch : {after or 'inconnu'}")
        if not args.force and before is not None and after is not None and after <= before:
            log("⊘ Aucun match plus récent (hors-saison ?) — pas de nouvelle version.")
            return 0

    push_dataset(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        log(f"❌ {e}")
        sys.exit(1)
