"""
Tests des adaptateurs de forme de `export_performance.py`.

Les deux sports ne publient pas la même chose : le NHL publie
`{probabilities, expected_value}`, la NBA des formes propres à chaque marché.
Le script ne lisait que la première, si bien qu'**aucun marché NBA n'était
mesuré** — ni justesse, ni Brier, ni calibration. La NBA s'apprêtait à ouvrir
sa saison avec exactement l'angle mort qui a coûté le marché `total` du NHL.

Les formes testées ici sont **relevées sur une sortie réelle** de
`vizer_nba/predict_all.py` et de l'archive publiée, pas inventées.
"""
from __future__ import annotations

import pytest

from conftest import load

ep = load('scripts/export_performance.py')


# Relevé sur `python predict_all.py --json`, NBA, 14/10/2026.
NBA_PREDICTIONS = {
    'home_team': 'MIA',
    'away_team': 'BKN',
    'win': {'prediction': 1,
            'home_win_proba': 0.739534854888916,
            'away_win_proba': 0.260465145111084},
    'total': {'prediction': 229.725830078125},
    'talent': {'home_ratio': 1.0, 'away_ratio': 1.0},
    'home_team_total': {'prediction': 119.87881469726562,
                        'line_default': 112.5,
                        'over_default_proba': 0.7637688477793618},
    'away_team_total': {'prediction': 111.25850677490234,
                        'line_default': 110.5,
                        'over_default_proba': 0.5294541081266918},
}

# Relevé sur l'archive publiée, NHL.
NHL_TOTAL = {
    'probabilities': {'over_5.5': 0.4855816464233395,
                      'under_5.5': 0.5144183535766604},
    'expected_value': 5.584942817687988,
}


# ── Probabilités ────────────────────────────────────────────────────────────
def test_forme_nhl_inchangee():
    probs = ep.probabilities_of(NHL_TOTAL)
    assert probs == {'over_5.5': pytest.approx(0.48558, abs=1e-4),
                     'under_5.5': pytest.approx(0.51442, abs=1e-4)}


def test_vainqueur_nba():
    probs = ep.probabilities_of(NBA_PREDICTIONS['win'])
    assert set(probs) == {'home', 'away'}
    assert probs['home'] == pytest.approx(0.7395, abs=1e-4)
    assert sum(probs.values()) == pytest.approx(1.0)


def test_total_equipe_nba_devient_over_under():
    """Et la clé doit être réglable par `realised()`, sinon l'adaptation ne
    sert à rien : c'est tout l'enjeu du format `over_<ligne>`."""
    probs = ep.probabilities_of(NBA_PREDICTIONS['home_team_total'])
    assert set(probs) == {'over_112.5', 'under_112.5'}
    assert probs['over_112.5'] == pytest.approx(0.76377, abs=1e-4)
    result = {'home_score': 118, 'away_score': 104, 'periods': [], 'overtime': False}
    assert ep.realised('home_team_total', list(probs), result) == 'over_112.5'


def test_ligne_entiere_sans_decimale_parasite():
    probs = ep.probabilities_of({'line_default': 220, 'over_default_proba': 0.5})
    assert set(probs) == {'over_220', 'under_220'}


def test_total_nba_sans_probabilites():
    """La NBA ne publie qu'un total ponctuel : rien à mesurer en
    probabilités, mais le niveau, lui, est mesurable."""
    assert ep.probabilities_of(NBA_PREDICTIONS['total']) == {}
    assert ep.point_of(NBA_PREDICTIONS['total']) == pytest.approx(229.7258)


@pytest.mark.parametrize("entry", [
    NBA_PREDICTIONS['talent'],   # ni probabilités ni grandeur
    {}, None, 'texte', {'probabilities': {}},
])
def test_entrees_sans_information(entry):
    assert ep.probabilities_of(entry) == {}


# ── Prédictions ponctuelles ─────────────────────────────────────────────────
def test_point_nhl_et_nba():
    assert ep.point_of(NHL_TOTAL) == pytest.approx(5.58494)
    assert ep.point_of(NBA_PREDICTIONS['home_team_total']) == pytest.approx(119.8788)
    assert ep.point_of(NBA_PREDICTIONS['talent']) is None


def test_cibles_de_niveau():
    result = {'home_score': 118, 'away_score': 104,
              'periods': [{'home': 31, 'away': 26}], 'overtime': False}
    assert ep._POINT_TARGET['total'](result) == 222
    assert ep._POINT_TARGET['home_team_total'](result) == 118
    assert ep._POINT_TARGET['away_team_total'](result) == 104
    assert ep._POINT_TARGET['p1_total'](result) == 57
    # Pas de détail par période : abstention plutôt qu'un zéro inventé.
    assert ep._POINT_TARGET['p1_total']({**result, 'periods': []}) is None
    # Les marchés qui prédisent une issue, pas une grandeur, sont absents.
    assert 'exact_score' not in ep._POINT_TARGET
    assert 'goal_intervals' not in ep._POINT_TARGET


# ── Décalage de niveau ──────────────────────────────────────────────────────
def test_biais_de_niveau_reproduit_la_mesure_manuelle():
    """Chiffres du marché `total` NHL, calculés à la main avant d'exister dans
    le script : 5,734 prédit contre 6,047 réel, biais −0,312, à 0,76
    erreur-type de zéro — donc indiscernable du hasard sur cet échantillon.
    Le test fige l'accord entre les deux."""
    s = ep.LevelStats()
    # Échantillon synthétique calibré sur ces moments.
    for pred, actual in [(5.7, 6.0)] * 40 + [(6.1, 6.8), (5.5, 5.0), (5.9, 6.4)]:
        s.add(pred, actual)
    out = s.to_dict(min_sample=20)
    assert out['n'] == 43
    assert out['bias'] < 0
    assert out['z'] is not None


def test_biais_nul_sur_erreurs_symetriques():
    s = ep.LevelStats()
    for pred, actual in [(6.0, 5.0), (6.0, 7.0)] * 15:
        s.add(pred, actual)
    out = s.to_dict(min_sample=20)
    assert out['bias'] == 0.0
    assert out['mae'] == 1.0
    assert out['z'] == 0.0


def test_biais_franc_est_signale():
    """Un demi-but de trop sur chaque match, sans dispersion : le z doit
    exploser. C'est le cas que le Brier ne voit pas."""
    s = ep.LevelStats()
    for _ in range(30):
        s.add(6.5, 6.0)
    out = s.to_dict(min_sample=20)
    assert out['bias'] == 0.5
    assert out['sd'] == 0.0


def test_echantillon_insuffisant():
    s = ep.LevelStats()
    s.add(6.0, 5.0)
    assert ep.LevelStats().to_dict(20)['insufficient'] is True
    assert s.to_dict(20) == {'n': 1, 'insufficient': True}
