"""
Tests de la demande de marchés à The-Odds API.

Pourquoi ces tests existent
---------------------------
La NBA n'a produit **aucun** value bet entre l'ouverture de sa saison (21/10)
et le 26/10. Cause : `team_totals` était demandé à l'endpoint groupé
`/sports/{key}/odds`, qui ne le sert pas. L'API répondait 422, le client levait,
et h2h et totals étaient perdus avec lui — alors que les prédictions
tournaient et se mesuraient normalement.

Deux protections, testées ici :
  - le défaut ne demande plus que ce que l'endpoint sert ;
  - un 422 pour marché invalide retire le fautif et rejoue, au lieu de tout
    perdre. C'est la protection générique : la même forme de panne — un
    élément refusé emporte le lot entier — peut revenir avec n'importe quel
    nom de marché.
"""
from __future__ import annotations

import json

import pytest

from conftest import load

oc = load('vizer_nba/src/api/odds_client.py', 'nba_api.odds_client')


# Corps d'erreur relevé en production, run #132 du 26/10/2026.
REAL_422 = json.dumps({
    "message": "Markets not supported by this endpoint: team_totals",
    "error_code": "INVALID_MARKET",
    "details_url": "https://the-odds-api.com/liveapi/guides/v4/api-error-codes.html#invalid-market",
})


def test_extrait_le_marche_refuse():
    assert oc._unsupported_markets(REAL_422) == {'team_totals'}


def test_extrait_plusieurs_marches():
    body = json.dumps({
        "message": "Markets not supported by this endpoint: team_totals, alternate_totals",
        "error_code": "INVALID_MARKET",
    })
    assert oc._unsupported_markets(body) == {'team_totals', 'alternate_totals'}


@pytest.mark.parametrize("body", [
    # Un 422 pour une autre raison ne doit pas être lu comme une liste de
    # marchés : sinon on rejouerait la même requête à l'identique.
    json.dumps({"message": "Invalid region: xx", "error_code": "INVALID_REGION"}),
    json.dumps({"message": "quelque chose sans deux-points", "error_code": "INVALID_MARKET"}),
    "pas du json",
    "",
])
def test_corps_non_exploitable_ne_donne_rien(body):
    assert oc._unsupported_markets(body) == set()


def test_defaut_ne_demande_que_le_servi():
    """`team_totals` n'existe que sur l'endpoint par évènement."""
    assert 'team_totals' not in oc.OddsAPIClient.DEFAULT_MARKETS
    assert set(oc.OddsAPIClient.DEFAULT_MARKETS) == {'h2h', 'totals'}


class _Response:
    def __init__(self, status, text='[]'):
        self.status_code = status
        self.text = text
        self.headers = {}

    def json(self):
        return json.loads(self.text)


def test_rejoue_sans_le_marche_fautif(monkeypatch, tmp_path):
    """Le scénario exact de la panne : premier appel refusé, second accepté."""
    client = oc.OddsAPIClient.__new__(oc.OddsAPIClient)
    client.api_key = 'x'
    client.sport_key = 'basketball_nba'

    calls: list[list[str]] = []

    def fake_get(url, params=None, timeout=None):
        asked = params['markets'].split(',')
        calls.append(asked)
        if 'team_totals' in asked:
            return _Response(422, REAL_422)
        return _Response(200, '[{"id": "abc"}]')

    monkeypatch.setattr(oc.requests, 'get', fake_get)
    payload = client._fetch_api(markets=['h2h', 'totals', 'team_totals'], regions='us')

    assert payload == [{'id': 'abc'}]
    assert calls == [['h2h', 'totals', 'team_totals'], ['h2h', 'totals']]


def test_422_sans_marche_recuperable_leve(monkeypatch):
    """Si tout est refusé, il n'y a rien à rejouer : on lève plutôt que de
    boucler ou de rendre une liste vide prise pour « pas de match »."""
    client = oc.OddsAPIClient.__new__(oc.OddsAPIClient)
    client.api_key = 'x'
    client.sport_key = 'basketball_nba'
    body = json.dumps({"message": "Markets not supported by this endpoint: h2h",
                       "error_code": "INVALID_MARKET"})
    monkeypatch.setattr(oc.requests, 'get',
                        lambda *a, **k: _Response(422, body))
    with pytest.raises(oc.OddsAPIError):
        client._fetch_api(markets=['h2h'], regions='us')
