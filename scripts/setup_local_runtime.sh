#!/usr/bin/env bash
# =============================================================================
# venv-runtime — un environnement local identique à celui de production
# =============================================================================
# Pourquoi un second environnement
# --------------------------------
# Les modèles sont entraînés sur Kaggle et chargés ailleurs. `requirements-
# runtime.txt` épingle les versions qui traversent le pickle, et le `venv/`
# principal a dérivé :
#
#     bibliothèque     épinglé    venv/      écart
#     scikit-learn     1.6.1      1.8.0      MAJEUR pour la sérialisation
#     pandas           2.3.3      3.0.3      version MAJEURE
#     numpy            2.4.6      2.4.5      mineur
#     xgboost          3.2.0      3.2.0      —
#
# `requirements-runtime.txt` prévient lui-même que « >= 1.8 : cv='prefit' a été
# supprimé de CalibratedClassifierCV ». Le venv principal est donc **passé** le
# point de rupture documenté.
#
# Conséquence concrète, pas théorique : charger un pickle de production dans
# `venv/` émet un `InconsistentVersionWarning` — scikit-learn ne garantit
# aucune compatibilité de sérialisation entre versions mineures, et le message
# dit « may lead to invalid results ». Toute probabilité calculée localement
# dans `venv/` à partir d'un modèle de production est donc suspecte.
#
# On ne touche pas à `venv/` : il sert à autre chose, et rétrograder pandas en
# 2.x y casserait peut-être du code. Un second environnement, dédié au travail
# sur modèle, règle le problème sans rien déplacer.
#
# Ce que ça débloque
# ------------------
# Un vrai aller-retour local : modifier, mesurer, comparer, et ne pousser que
# si c'est mieux. L'entraînement d'évaluation NHL prend **9 secondes** sur ce
# PC — la boucle est plus rapide en local que sur Kaggle, où elle demande un
# push de kernel et plusieurs minutes d'attente.
#
# Usage
# -----
#     bash scripts/setup_local_runtime.sh
#     venv-runtime/bin/python vizer_nhl/train.py --output /tmp/essai.pkl
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
TARGET=venv-runtime

if [ ! -d "$TARGET" ]; then
  echo "→ création de $TARGET"
  python3 -m venv "$TARGET"
fi

echo "→ versions épinglées (requirements-runtime.txt)"
"$TARGET/bin/pip" install --quiet --upgrade pip
"$TARGET/bin/pip" install --quiet -r requirements-runtime.txt

echo "→ dépendances d'exécution du chemin de prédiction"
"$TARGET/bin/pip" install --quiet pyyaml requests python-dateutil
"$TARGET/bin/pip" install --quiet -e .

echo "→ contrôle"
"$TARGET/bin/python" - <<'PYCHECK'
import importlib.metadata as md
import pathlib
import sys

pins = {}
for line in pathlib.Path('requirements-runtime.txt').read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '==' not in line:
        continue
    name, _, want = line.partition('==')
    pins[name.strip()] = want.strip()

bad = []
for name, want in sorted(pins.items()):
    try:
        got = md.version(name)
    except md.PackageNotFoundError:
        bad.append(f"  {name}: absent (attendu {want})")
        continue
    mark = '✓' if got == want else '✗'
    print(f"  {mark} {name}: {got}")
    if got != want:
        bad.append(f"  {name}: {got} au lieu de {want}")

if bad:
    print("\n❌ Environnement non conforme :", file=sys.stderr)
    print("\n".join(bad), file=sys.stderr)
    raise SystemExit(1)
print("\n✅ venv-runtime conforme aux versions de production.")
PYCHECK
