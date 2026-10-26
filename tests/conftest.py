"""
Chargement des modules testés **par chemin**, sans passer par leur package.

Ces tests ne portent que sur de la logique en bibliothèque standard : sens
d'un pari, formes de prédiction, agrégats arithmétiques. Les importer via
`vizer_core.x` déclencherait `vizer_core/__init__.py`, qui tire joblib,
pandas, scikit-learn et xgboost — 300 Mo de dépendances pour des tests qui
n'en utilisent aucune, et un job de contrôle qui passe de vingt secondes à
plusieurs minutes.

C'est une leçon payée en rouge : le job avait été écrit en supposant que
l'import serait léger, sans le vérifier. `ModuleNotFoundError: joblib`.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import pathlib
import sys
from types import ModuleType

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(relative_path: str, name: str | None = None) -> ModuleType:
    """
    Charge un module depuis son chemin, hors de son package d'origine.

    Un `name` pointé — `mon_pkg.publication` — fabrique au besoin un paquet
    parent synthétique dont le `__path__` désigne le dossier du fichier. Les
    imports relatifs du module (`from .odds_client import GameOdds`) se
    résolvent alors dans ce paquet, sans qu'on ait à importer la vraie
    arborescence `src.api.*` du sport — qui porterait le même nom `src` pour
    les deux sports et ferait se masquer l'un l'autre.

    Charger deux modules du même dossier sous le même préfixe les relie :
        oc  = load('vizer_nba/src/api/odds_client.py', 'nba_api.odds_client')
        pub = load('vizer_nba/src/api/publication.py', 'nba_api.publication')
    """
    path = ROOT / relative_path
    module_name = name or path.stem

    parent = module_name.rpartition('.')[0]
    if parent and parent not in sys.modules:
        spec = importlib.machinery.ModuleSpec(parent, None, is_package=True)
        pkg = importlib.util.module_from_spec(spec)
        pkg.__path__ = [str(path.parent)]
        sys.modules[parent] = pkg

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:   # pragma: no cover
        raise ImportError(f"Chargement impossible : {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
