"""
« Franchie » et « rien à vérifier » ne doivent pas se confondre.

Les deux rendent `passed = True`, et c'est le piège. Au changement de saison le
jeu de test se réduit aux quelques matchs déjà joués : chaque marché part en
abstention et le modèle se déploie sans qu'aucun seuil ne soit contrôlé.

Constaté le 27/10/2026, et causé par une correction : republier le dataset NBA
a fait passer son jeu de test de 6 140 matchs (la saison précédente entière,
puisque les données s'arrêtaient en avril) à **43** — la saison en cours,
ouverte six jours plus tôt. Le log annonçait « ✅ ACCEPTÉ » et l'écran Admin
« Dernier entraînement accepté ».
"""
from __future__ import annotations

import pathlib

import importlib.machinery
import importlib.util
import sys

from conftest import load

# `quality_gate.py` importe `ModelRegistry`, qui tire joblib, pandas et
# scikit-learn. Les dataclasses testées ici — `GateResult`, `MarketCheck` — ne
# s'en servent pas : seules `check_registry()` et le point d'entrée ligne de
# commande la touchent, et aucun des deux n'est exercé. On substitue donc le
# module plutôt que d'installer 300 Mo dans le job de contrôles.
#
# Le substitut est délibérément vide : s'il finissait par être *utilisé*, le
# test échouerait sur un attribut manquant au lieu de passer contre une
# fiction.
_pkg = 'vizer_gate_pkg'
if _pkg not in sys.modules:
    spec = importlib.machinery.ModuleSpec(_pkg, None, is_package=True)
    pkg = importlib.util.module_from_spec(spec)
    pkg.__path__ = [str(pathlib.Path(__file__).resolve().parent.parent / 'vizer_core')]
    sys.modules[_pkg] = pkg

_stub = importlib.util.module_from_spec(
    importlib.machinery.ModuleSpec(f'{_pkg}.model_registry', None))
_stub.ModelRegistry = object
sys.modules[f'{_pkg}.model_registry'] = _stub

qg = load('vizer_core/quality_gate.py', f'{_pkg}.quality_gate')


def _check(market: str, verdict: str):
    return qg.MarketCheck(market, verdict, None, 0.55, 'motif', cause='x')


def test_marches_verifies_sont_juges():
    r = qg.GateResult(checks=[_check('moneyline', 'pass')], n_test=947)
    assert r.passed and r.judged
    assert r.headline() == 'barrière franchie'


def test_abstention_totale_nest_pas_un_jugement():
    """Le cas NBA du 27/10 : un seul marché, en abstention, 43 matchs."""
    r = qg.GateResult(checks=[_check('moneyline', 'skip')], n_test=43)
    assert r.passed is True        # rien ne bloque le déploiement
    assert r.judged is False       # mais rien n'a été vérifié
    assert 'aucun seuil vérifié' in r.headline()
    assert '43' in r.headline()
    assert r.to_dict()['judged'] is False


def test_abstention_partielle_reste_un_jugement():
    """Un marché vérifié suffit : on ne crie pas pour un marché sans règle."""
    r = qg.GateResult(
        checks=[_check('moneyline', 'pass'), _check('total', 'skip')], n_test=947)
    assert r.judged is True
    assert r.headline() == 'barrière franchie'


def test_refus_reste_prioritaire():
    r = qg.GateResult(
        checks=[_check('moneyline', 'fail'), _check('total', 'skip')], n_test=947)
    assert r.passed is False
    assert 'barrière franchie' not in r.headline()


def test_aucun_marche_du_tout():
    """Ni vérifié ni abstenu : il n'y a rien à juger, et c'est aussi à dire."""
    r = qg.GateResult(checks=[], n_test=0)
    assert r.passed is True
    assert r.judged is False
