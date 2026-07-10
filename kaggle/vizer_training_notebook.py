#!/usr/bin/env python3
# =============================================================================
# Vizer Training Pipeline — Script exécuté sur Kaggle
# =============================================================================
#
# Ce fichier est un TEMPLATE. Les placeholders __VIZER_*__ sont substitués
# automatiquement par GitHub Actions avant chaque push vers Kaggle.
# Ne pas remplacer les placeholders manuellement sauf pour un run local.
#
# Flux d'exécution :
#   1. Clone le dépôt GitHub (branche configurée)
#   2. Installe les dépendances manquantes sur Kaggle (lightgbm, nba_api, …)
#   3. [Optionnel] Charge les données historiques NHL depuis un dataset Kaggle
#   4. Lance update_data.py + train.py (NHL) et/ou update_and_train.py (NBA)
#   5. Archive nhl/nba/models/ dans /kaggle/working/vizer_models.zip
#      → téléchargeable via `kaggle kernels output`
#   6. Reverse les données NHL fraîches dans le dataset Kaggle vizer-nhl-data
#      (nouvelle version) pour que le job quotidien de prédictions prédise
#      sur un état d'équipes à jour. Non bloquant en cas d'échec.
#
# Variables substituées par GitHub Actions :
#   __VIZER_SPORT__            → nhl | nba | both
#   __VIZER_GH_REPO__          → owner/repo (ex: NOX-Theteenager/Vizer_pronostics)
#   __VIZER_GH_REF__           → branche git (ex: main)
#   __VIZER_KAGGLE_USERNAME__  → username Kaggle (auth de l'étape 6)
#   __VIZER_KAGGLE_KEY__       → clé API Kaggle (auth de l'étape 6 ; le kernel
#                                est privé, la clé n'est visible que de toi)
#
# Pour un run Kaggle manuel (via l'UI), modifier les trois constantes ci-dessous
# directement et lancer le script.
# =============================================================================

import os
import sys
import shutil
import subprocess
import zipfile
import time
from pathlib import Path

# ─── Paramètres (injectés par GitHub Actions via sed) ─────────────────────────
SPORT    = "__VIZER_SPORT__"       # nhl | nba | both
GH_REPO  = "__VIZER_GH_REPO__"    # NOX-Theteenager/Vizer_pronostics
GH_REF   = "__VIZER_GH_REF__"     # main

# ─── Chemins Kaggle (fixes) ───────────────────────────────────────────────────
CLONE_DIR    = Path("/kaggle/working/vizer")
OUT_DIR      = Path("/kaggle/working")
KAGGLE_INPUT = Path("/kaggle/input")  # datasets Kaggle montés ici si configurés

START_TIME = time.time()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def banner(msg: str) -> None:
    print(f"\n{'='*70}\n{msg}\n{'='*70}", flush=True)


def run(cmd: str, cwd: Path | None = None) -> None:
    """Lance une commande shell, affiche la sortie en temps réel.
    Lève RuntimeError si le code de retour est non-nul."""
    cwd_str = str(cwd) if cwd else None
    label = f"  [cwd: {cwd_str}]" if cwd_str else ""
    print(f"\n$ {cmd}{label}", flush=True)
    result = subprocess.run(cmd, shell=True, cwd=cwd_str)
    if result.returncode != 0:
        raise RuntimeError(
            f"Commande échouée (code {result.returncode}): {cmd}"
        )


def seed_data_from_kaggle_dataset(sport: str, pkg_dir: Path) -> bool:
    """
    Copie les fichiers de données depuis un dataset Kaggle source vers pkg_dir/data/.

    NHL — dataset contenant les CSVs Moneypuck (skaters_*, goalies_*, lines_*, …)
    NBA — dataset contenant les 4 CSVs produits par les scripts fetch_nba_*.py
          (NBA_TEAMS.csv, NBA_PLAYERS.csv, NBA_GAMES.csv, NBA_PLAYER_GAMES.csv)

    Activer cette fonctionnalité :
      1. Créer un dataset Kaggle privé nommé "vizer-nhl-data" ou "vizer-nba-data".
      2. Uploader les fichiers CSV correspondants depuis ton dossier local data/.
      3. Ajouter "ton-username/vizer-nhl-data" (et/ou "…/vizer-nba-data") dans
         "dataset_sources" du kernel-metadata.json.
      4. Kaggle monte le dataset dans /kaggle/input/vizer-{sport}-data/ à chaque run.

    Si le dataset n'est pas monté, retourne False — le script télécharge depuis
    la source d'origine (Moneypuck ou stats.nba.com), plus lent mais fonctionnel.
    """
    # Kaggle normalise les slugs de dataset (tirets, minuscules)
    possible_mounts = [
        KAGGLE_INPUT / f"vizer-{sport}-data",
        KAGGLE_INPUT / f"vizer_{sport}_data",
    ]
    mounted = next((p for p in possible_mounts if p.exists()), None)
    if mounted is None:
        print(f"  [info] Pas de dataset {sport.upper()} monté — "
              f"téléchargement depuis la source d'origine.")
        return False

    dest = pkg_dir / "data"
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    total_mb = 0.0
    for src_file in mounted.glob("**/*"):
        if src_file.is_file():
            shutil.copy2(src_file, dest / src_file.name)
            total_mb += src_file.stat().st_size / 1024 ** 2
            count += 1

    print(f"  ✅ {count} fichier(s) copiés depuis {mounted} → {dest} "
          f"({total_mb:.1f} Mo)")
    return count > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Clonage du dépôt GitHub
# ═══════════════════════════════════════════════════════════════════════════════
banner("1/6  CLONAGE DU DÉPÔT")
print(f"  Dépôt  : https://github.com/{GH_REPO}")
print(f"  Branche: {GH_REF}")

CLONE_DIR.mkdir(parents=True, exist_ok=True)
run(
    f"git clone --depth=1 --branch {GH_REF} "
    f"https://github.com/{GH_REPO}.git {CLONE_DIR}"
)

# ═══════════════════════════════════════════════════════════════════════════════
# 2. Installation des dépendances
# ═══════════════════════════════════════════════════════════════════════════════
banner("2/6  INSTALLATION DES DÉPENDANCES")
# Kaggle fournit déjà : xgboost, scikit-learn, pandas, numpy, scipy, joblib, requests.
# On installe uniquement ce qui manque.
run(
    "pip install -q "
    "lightgbm>=4.0.0 "
    "nba_api>=1.5.2 "
    "fuzzywuzzy "
    "python-Levenshtein "
    "tqdm "
    "pyyaml>=6.0",
    cwd=CLONE_DIR,
)
# Installe vizer_core en mode éditable (lit pyproject.toml à la racine du repo)
run("pip install -q -e .", cwd=CLONE_DIR)
print("  ✅ Dépendances installées")

# ═══════════════════════════════════════════════════════════════════════════════
# 3. Données historiques (optionnel — depuis des datasets Kaggle)
# ═══════════════════════════════════════════════════════════════════════════════
banner("3/6  DONNÉES HISTORIQUES (cache Kaggle, optionnel)")
nhl_has_cache = False
nba_has_cache = False

if SPORT in ("nhl", "both"):
    nhl_dir = CLONE_DIR / "vizer_nhl"
    print("── NHL ──")
    nhl_has_cache = seed_data_from_kaggle_dataset("nhl", nhl_dir)

if SPORT in ("nba", "both"):
    nba_dir = CLONE_DIR / "vizer_nba"
    print("── NBA ──")
    nba_has_cache = seed_data_from_kaggle_dataset("nba", nba_dir)

# ═══════════════════════════════════════════════════════════════════════════════
# 4. Entraînement
# ═══════════════════════════════════════════════════════════════════════════════
banner("4/6  ENTRAÎNEMENT DES MODÈLES")
nhl_ok = True
nba_ok = True

# ── 4a. NHL ───────────────────────────────────────────────────────────────────
if SPORT in ("nhl", "both"):
    print("\n─── NHL ────────────────────────────────────────────────────────────")
    nhl_dir = CLONE_DIR / "vizer_nhl"

    try:
        # update_data.py télécharge la saison courante depuis Moneypuck et agrège.
        # Si les données historiques sont déjà seedées via Kaggle dataset (step 3),
        # le downloader détectera les fichiers présents et ne re-téléchargera que
        # la saison courante (comportement natif de MoneypuckDownloader).
        run("python update_data.py --mode update", cwd=nhl_dir)
        run("python train.py", cwd=nhl_dir)
        print("  ✅ NHL — entraînement terminé")
    except RuntimeError as e:
        print(f"  ❌ NHL — ÉCHEC : {e}", file=sys.stderr)
        nhl_ok = False

# ── 4b. NBA ───────────────────────────────────────────────────────────────────
if SPORT in ("nba", "both"):
    print("\n─── NBA ────────────────────────────────────────────────────────────")
    nba_dir = CLONE_DIR / "vizer_nba"

    try:
        if nba_has_cache:
            # Les CSVs historiques sont déjà là via le dataset Kaggle.
            # --skip-fetch évite les centaines d'appels HTTP vers stats.nba.com
            # et le rate limiting associé (~20-40 min économisées).
            print("  [info] Cache NBA détecté — skip fetch, entraînement direct.")
            run("python update_and_train.py --skip-fetch --skip-validation", cwd=nba_dir)
        else:
            # Téléchargement complet depuis stats.nba.com (lent mais fonctionnel).
            run("python update_and_train.py --skip-validation", cwd=nba_dir)
        print("  ✅ NBA — entraînement terminé")
    except RuntimeError as e:
        print(f"  ❌ NBA — ÉCHEC : {e}", file=sys.stderr)
        nba_ok = False

# Stopper si les deux ont échoué
if not nhl_ok and not nba_ok:
    raise SystemExit("❌ Les deux entraînements (NHL + NBA) ont échoué. Vérifier les logs ci-dessus.")

# ═══════════════════════════════════════════════════════════════════════════════
# 5. Archivage des artefacts → /kaggle/working/vizer_models.zip
# ═══════════════════════════════════════════════════════════════════════════════
banner("5/6  ARCHIVAGE DES ARTEFACTS")

archive_path = OUT_DIR / "vizer_models.zip"
files_added: list[str] = []
errors: list[str] = []

with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for sport_key, pkg_name, ok in [
        ("nhl", "vizer_nhl", nhl_ok),
        ("nba", "vizer_nba", nba_ok),
    ]:
        if SPORT not in (sport_key, "both"):
            continue
        if not ok:
            errors.append(sport_key.upper())
            continue

        models_dir = CLONE_DIR / pkg_name / "models"
        if not models_dir.exists():
            msg = f"{pkg_name}/models/ introuvable après entraînement"
            print(f"  ⚠️  {msg}", file=sys.stderr)
            errors.append(sport_key.upper())
            continue

        for f in sorted(models_dir.rglob("*")):
            if not f.is_file():
                continue
            arc_name = f"{sport_key}/{f.relative_to(models_dir)}"
            zf.write(f, arc_name)
            files_added.append(arc_name)
            print(f"  + {arc_name}  ({f.stat().st_size / 1024:.0f} KB)")

# ═══════════════════════════════════════════════════════════════════════════════
# 6. Mise à jour du dataset Kaggle NHL (données fraîches → vizer-nhl-data)
# ═══════════════════════════════════════════════════════════════════════════════
# Le kernel vient de télécharger la saison courante depuis Moneypuck et de
# ré-agréger dataset_agrege_vizer_nhl.csv : on reverse ces données dans le
# dataset Kaggle pour que le job quotidien de prédictions (GitHub Actions)
# travaille sur un état d'équipes à jour. Upload Kaggle→Kaggle : rapide.
#
# Le dataset NBA, lui, est mis à jour depuis le PC (stats.nba.com bloque les
# IP datacenter) : voir vizer_nba/scripts/push_dataset_to_kaggle.py.
banner("6/6  MISE À JOUR DU DATASET KAGGLE NHL")

# Fichiers historiques volumineux absents du dataset Kaggle — ne jamais uploader
_NHL_DATASET_EXCLUDE = {"skaters_2008_2024.csv", "shots_2007-2024.csv"}


def _nhl_data_is_fresher(new_csv: Path, seed_csv: Path) -> bool:
    """Compare la date de match max du CSV agrégé frais vs la version du dataset.
    Au moindre doute (colonne absente, erreur de lecture), considère frais :
    mieux vaut une version identique en trop qu'un dataset qui stagne."""
    try:
        import pandas as pd
        col = "gameDate_home"
        new_max = pd.read_csv(new_csv, usecols=[col])[col].max()
        old_max = pd.read_csv(seed_csv, usecols=[col])[col].max()
        print(f"  Dernier match — fraîchement agrégé : {new_max} | dataset : {old_max}")
        return bool(new_max > old_max)
    except Exception as e:
        print(f"  [warn] Comparaison de fraîcheur impossible ({e}) — upload par prudence.")
        return True


def update_nhl_kaggle_dataset() -> None:
    creds_user = "__VIZER_KAGGLE_USERNAME__"
    creds_key  = "__VIZER_KAGGLE_KEY__"
    if creds_user.startswith("__") or creds_key.startswith("__"):
        print("  ⊘ Credentials non injectés (run manuel ?) — mise à jour sautée.")
        return

    data_dir = CLONE_DIR / "vizer_nhl" / "data"
    agrege = data_dir / "dataset_agrege_vizer_nhl.csv"
    if not agrege.exists():
        print("  ⊘ dataset_agrege_vizer_nhl.csv introuvable — rien à uploader.")
        return

    seed = KAGGLE_INPUT / "vizer-nhl-data" / "dataset_agrege_vizer_nhl.csv"
    if seed.exists() and not _nhl_data_is_fresher(agrege, seed):
        print("  ⊘ Aucun match plus récent que la version du dataset — upload sauté "
              "(hors-saison ?).")
        return

    # Staging HORS de /kaggle/working : le contenu de working devient la sortie
    # du kernel, et on ne veut pas dupliquer ~1 Go dans les outputs.
    stage = Path("/tmp/vizer_nhl_dataset_stage")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    total_mb = 0.0
    for f in sorted(data_dir.glob("*.csv")):
        if f.name in _NHL_DATASET_EXCLUDE:
            continue
        shutil.copy2(f, stage / f.name)
        total_mb += f.stat().st_size / 1024 ** 2
        print(f"  + {f.name} ({f.stat().st_size / 1024 ** 2:.0f} Mo)")

    import json
    (stage / "dataset-metadata.json").write_text(json.dumps({
        "id": f"{creds_user}/vizer-nhl-data",
        "title": "vizer-nhl-data",
    }))

    os.environ["KAGGLE_USERNAME"] = creds_user
    os.environ["KAGGLE_KEY"] = creds_key
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    run(f'kaggle datasets version -p {stage} -m "maj auto post-training {stamp}" -q')
    shutil.rmtree(stage)
    print(f"  ✅ Nouvelle version de vizer-nhl-data publiée ({total_mb:.0f} Mo).")


if SPORT in ("nhl", "both") and nhl_ok:
    try:
        update_nhl_kaggle_dataset()
    except Exception as e:
        # L'upload du dataset ne doit JAMAIS faire échouer le pipeline :
        # les modèles sont déjà archivés, le training est un succès.
        print(f"  ⚠️  Mise à jour du dataset NHL échouée (non bloquant) : {e}",
              file=sys.stderr)
else:
    print("  ⊘ NHL non entraîné dans ce run — pas de mise à jour du dataset.")

# Résumé
elapsed = time.time() - START_TIME
size_mb = archive_path.stat().st_size / 1024 ** 2

print(f"\n{'─'*70}")
print(f"  Archive  : {archive_path}")
print(f"  Taille   : {size_mb:.1f} MB")
print(f"  Fichiers : {len(files_added)} ajoutés")
if errors:
    print(f"  ⚠️  Sports échoués (absents de l'archive) : {', '.join(errors)}")
print(f"  Durée    : {elapsed:.0f}s ({elapsed/60:.1f} min)")
print(f"\n✅ Pipeline Vizer terminé — artefacts disponibles dans {OUT_DIR}")
