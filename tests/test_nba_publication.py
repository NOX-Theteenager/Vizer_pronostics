"""
Tests du comparatif bookmakers publié côté NBA.

Pourquoi ces tests existent
---------------------------
`books_for_bet` lisait `t.point` sur un `TotalsLine` qui n'a jamais eu ce
champ — il s'appelle `line`, et la branche voisine des totals d'équipe
l'écrivait correctement. La faute n'est apparue que le 26/10/2026, au premier
run où des cotes NBA sont arrivées : la requête échouait en amont depuis
l'ouverture de la saison, donc cette fonction n'avait jamais tourné en
production.

Du code jamais exécuté n'est pas du code qui marche. Les trois branches sont
couvertes ici, avec les vraies dataclasses du client.
"""
from __future__ import annotations

import pytest

from conftest import load

oc = load('vizer_nba/src/api/odds_client.py', 'nba_api.odds_client')
pub = load('vizer_nba/src/api/publication.py', 'nba_api.publication')


def _game():
    """Un match à trois bookmakers, aux formes réellement publiées."""
    return oc.GameOdds(
        home='MIA', away='BKN',
        home_full='Miami Heat', away_full='Brooklyn Nets',
        commence_time='2026-10-26T23:30Z',
        bookmakers=[
            oc.BookmakerOdds(
                bookmaker='draftkings',
                moneyline_home=1.45, moneyline_away=2.80,
                totals=[oc.TotalsLine(line=228.5, over_odds=1.91, under_odds=1.95)],
                team_totals=[
                    oc.TeamTotalLine(team_full_name='Miami Heat', line=117.5,
                                     over_odds=1.88, under_odds=1.98),
                ],
            ),
            oc.BookmakerOdds(
                bookmaker='fanduel',
                moneyline_home=1.48, moneyline_away=2.70,
                totals=[oc.TotalsLine(line=228.5, over_odds=1.95, under_odds=1.90)],
                team_totals=[],
            ),
            oc.BookmakerOdds(
                bookmaker='betmgm',
                moneyline_home=1.44, moneyline_away=2.85,
                # Ligne différente : ne doit pas être comptée pour 228.5.
                totals=[oc.TotalsLine(line=229.5, over_odds=1.92, under_odds=1.94)],
                team_totals=[],
            ),
        ],
    )


def test_total_under_trouve_ses_bookmakers():
    """Le cas exact qui plantait en production."""
    rows = pub.books_for_bet(_game(), 'total', 'under_228.5')
    assert [r['name'] for r in rows] == ['draftkings', 'fanduel']
    assert rows[0]['odds'] == 1.95 and rows[0]['best'] is True
    assert rows[1]['best'] is False


def test_total_over_et_meilleure_cote():
    rows = pub.books_for_bet(_game(), 'total', 'over_228.5')
    assert [(r['name'], r['odds']) for r in rows] == [
        ('fanduel', 1.95), ('draftkings', 1.91)]
    assert rows[0]['best'] is True


def test_une_autre_ligne_n_est_pas_comptee():
    """betmgm cote 229.5 : l'inclure publierait une cote qui ne correspond
    pas au pari, et faussement comme meilleure."""
    rows = pub.books_for_bet(_game(), 'total', 'under_228.5')
    assert 'betmgm' not in [r['name'] for r in rows]
    rows = pub.books_for_bet(_game(), 'total', 'under_229.5')
    assert [r['name'] for r in rows] == ['betmgm']


def test_moneyline():
    rows = pub.books_for_bet(_game(), 'moneyline', 'away')
    assert [(r['name'], r['odds']) for r in rows] == [
        ('betmgm', 2.85), ('draftkings', 2.8), ('fanduel', 2.7)]
    # La NBA nomme `win` ce que le registre nomme `moneyline` : les deux
    # doivent répondre, sinon le comparatif disparaît selon l'appelant.
    assert pub.books_for_bet(_game(), 'win', 'home')


def test_total_equipe():
    rows = pub.books_for_bet(_game(), 'home_team_total', 'over_117.5')
    assert [r['name'] for r in rows] == ['draftkings']
    # L'équipe doit correspondre : la ligne de Miami n'est pas celle de Brooklyn.
    assert pub.books_for_bet(_game(), 'away_team_total', 'over_117.5') == []


@pytest.mark.parametrize("market, selection", [
    ('total', 'under_999.5'),     # ligne absente
    ('total', 'bogus'),           # sélection non parsable
    ('exact_score', '112-108'),   # marché sans cotes publiées
    ('moneyline', 'draw'),        # issue inexistante au basket
])
def test_absence_rend_une_liste_vide(market, selection):
    assert pub.books_for_bet(_game(), market, selection) == []


def test_match_sans_bookmaker():
    game = oc.GameOdds(home='MIA', away='BKN', home_full='Miami Heat',
                       away_full='Brooklyn Nets', commence_time='', bookmakers=[])
    assert pub.books_for_bet(game, 'total', 'under_228.5') == []
