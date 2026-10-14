"""
Tests du garde-fou directionnel.

Ce module décide si un pari est publié ou retenu : une erreur ici fait soit
disparaître des paris valables, soit passer le défaut qu'il est censé
attraper. D'où une couverture des cas limites, pas seulement du cas nominal.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from vizer_core.direction_guard import (
    MIN_SAMPLE, DirectionGuard, Verdict, direction_of, scan,
)


# ── Axes directionnels ──────────────────────────────────────────────────────
@pytest.mark.parametrize("market, selection, expected", [
    ('moneyline', 'home', 'home'),
    ('moneyline', 'away', 'away'),
    ('win', 'home', 'home'),
    # La ligne est écartée volontairement : under_5.5 et under_6.5 sont le
    # même sens, et c'est le sens qui révèle un décalage de niveau.
    ('total', 'under_5.5', 'under'),
    ('total', 'under_6.5', 'under'),
    ('total', 'over_6.0', 'over'),
    ('total', 'over_-1.5', 'over'),
    ('home_team_total', 'under_3.5', 'under'),
    ('p1_total', 'over_1.5', 'over'),
    ('btts', 'yes', 'yes'),
    ('p1_winner', 'home_lead', 'home'),
    # L'égalité n'est d'aucun côté.
    ('p1_winner', 'tied', None),
    # Ces marchés choisissent parmi des issues ordonnées sans opposé naturel.
    ('exact_score', '3-2', None),
    ('goal_intervals', '5-6', None),
    ('total', 'bogus', None),
    ('inconnu', 'home', None),
])
def test_direction_of(market, selection, expected):
    assert direction_of(market, selection) == expected


# ── Verdicts ────────────────────────────────────────────────────────────────
def test_unanimite_retenue():
    v = Verdict('nhl', 'total', {'under': 39})
    assert v.status == 'withheld'
    assert v.to_dict()['withhold'] == 'under'
    # Le motif doit nommer la preuve qui lèverait la retenue.
    assert 'over' in v.reason


def test_desequilibre_avertit_sans_retenir():
    """Cas réel du moneyline : 49 away contre 9 home. Déséquilibré, mais le
    côté minoritaire existe — donc on affiche, on ne retient pas. Tester ce
    cas précisément parce qu'un test contre 50/50 l'aurait condamné et aurait
    éteint le seul marché qui fonctionne."""
    v = Verdict('nhl', 'moneyline', {'away': 49, 'home': 9})
    assert v.status == 'imbalanced'
    assert v.to_dict()['withhold'] is None


def test_echantillon_trop_petit():
    v = Verdict('nhl', 'total', {'under': MIN_SAMPLE - 1})
    assert v.status == 'insufficient'
    assert v.to_dict()['withhold'] is None


def test_unanimite_juste_au_seuil():
    assert Verdict('nhl', 'total', {'under': MIN_SAMPLE}).status == 'withheld'


def test_equilibre_est_ok():
    v = Verdict('nhl', 'moneyline', {'home': 30, 'away': 28})
    assert v.status == 'ok'


def test_desequilibre_sur_petit_echantillon_reste_ok():
    """15 paris dont 2 minoritaires : la proportion est basse, mais se
    prononcer sur une proportion demande plus de matière que constater une
    absence."""
    assert Verdict('nhl', 'moneyline', {'away': 13, 'home': 2}).status == 'ok'


# ── Lecture de l'archive ────────────────────────────────────────────────────
def _write(root, day, sport, games, generated=None):
    folder = root / 'predictions' / 'archive' / day
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{sport}.json').write_text(json.dumps({
        'generated_at': generated or f'{day}T07:00:00+00:00',
        'games': games,
    }), encoding='utf-8')


def _game(home, away, day, bets=(), withheld=()):
    return {
        'home': home, 'away': away,
        'commence_time': f'{day}T23:00:00Z',
        'value_bets': list(bets),
        'withheld_bets': list(withheld),
    }


def _bet(market, selection):
    return {'market': market, 'selection': selection}


def test_deduplication_du_meme_match(tmp_path):
    """Un match à venir est republié chaque jour, et deux fois par jour. Sans
    dédoublonnage, un seul pari compterait quatre fois et n'importe quel
    marché paraîtrait unanime sur un large échantillon."""
    game = _game('WSH', 'MTL', '2026-10-14', [_bet('total', 'under_6.5')])
    for day in ('2026-10-12', '2026-10-13', '2026-10-14'):
        _write(tmp_path, day, 'nhl', [game])

    verdicts = scan(tmp_path, sports=('nhl',), today=date(2026, 10, 14))
    assert [v.counts for v in verdicts['nhl']] == [{'under': 1}]


def test_derniere_publication_prioritaire(tmp_path):
    """Deux passages le même jour : c'est le second, avec des cotes fraîches,
    sur lequel l'utilisateur a pu agir."""
    day = '2026-10-14'
    _write(tmp_path, day, 'nhl',
           [_game('WSH', 'MTL', day, [_bet('total', 'under_6.5')])],
           generated=f'{day}T07:00:00+00:00')
    _write(tmp_path, day, 'nhl',
           [_game('WSH', 'MTL', day, [_bet('total', 'over_6.5')])],
           generated=f'{day}T20:00:00+00:00')
    verdicts = scan(tmp_path, sports=('nhl',), today=date(2026, 10, 14))
    assert [v.counts for v in verdicts['nhl']] == [{'over': 1}]


def test_fenetre_glissante(tmp_path):
    _write(tmp_path, '2026-08-01', 'nhl',
           [_game('A', 'B', '2026-08-01', [_bet('total', 'under_5.5')])])
    _write(tmp_path, '2026-10-14', 'nhl',
           [_game('C', 'D', '2026-10-14', [_bet('total', 'over_5.5')])])
    verdicts = scan(tmp_path, sports=('nhl',), window_days=30, today=date(2026, 10, 14))
    assert [v.counts for v in verdicts['nhl']] == [{'over': 1}]


def test_les_paris_retenus_comptent(tmp_path):
    """L'invariant qui empêche le verdict de s'auto-effacer : si retenir un
    pari le faisait disparaître de l'archive, la fenêtre finirait par oublier
    la tendance et le marché repartirait aveugle."""
    _write(tmp_path, '2026-10-14', 'nhl',
           [_game(f'H{j}', f'A{j}', '2026-10-14',
                  withheld=[_bet('total', 'under_6.5')])
            for j in range(MIN_SAMPLE)])
    verdicts = scan(tmp_path, sports=('nhl',), today=date(2026, 10, 14))
    assert verdicts['nhl'][0].status == 'withheld'


def test_archive_absente(tmp_path):
    assert scan(tmp_path, sports=('nhl',), today=date(2026, 10, 14)) == {'nhl': []}


def test_json_illisible_ignore(tmp_path):
    folder = tmp_path / 'predictions' / 'archive' / '2026-10-14'
    folder.mkdir(parents=True)
    (folder / 'nhl.json').write_text('{ tronqué', encoding='utf-8')
    assert scan(tmp_path, sports=('nhl',), today=date(2026, 10, 14)) == {'nhl': []}


# ── Application ─────────────────────────────────────────────────────────────
class _Bet:
    def __init__(self, market, selection):
        self.market_name = market
        self.selection = selection


def _guard(tmp_path, sports):
    path = tmp_path / 'direction.json'
    path.write_text(json.dumps({'sports': sports}), encoding='utf-8')
    return DirectionGuard.load(path, 'nhl')


def test_split_retient_le_cote_dominant(tmp_path):
    guard = _guard(tmp_path, {'nhl': [
        {'market': 'total', 'status': 'withheld', 'withhold': 'under',
         'reason': 'unanime'},
    ]})
    keep, held = guard.split([
        _Bet('total', 'under_6.5'),
        _Bet('total', 'over_5.5'),      # la preuve attendue : elle passe
        _Bet('moneyline', 'away'),      # marché non visé
    ])
    assert [(b.market_name, b.selection) for b in keep] == [
        ('total', 'over_5.5'), ('moneyline', 'away')]
    assert [b.selection for b, _ in held] == ['under_6.5']
    assert held[0][1] == 'unanime'


def test_marche_signale_mais_non_retenu_laisse_passer(tmp_path):
    guard = _guard(tmp_path, {'nhl': [
        {'market': 'moneyline', 'status': 'imbalanced', 'withhold': None},
    ]})
    assert not guard
    keep, held = guard.split([_Bet('moneyline', 'away')])
    assert len(keep) == 1 and not held


@pytest.mark.parametrize("path", [None, '/introuvable/direction.json'])
def test_garde_fou_inerte_sans_verdict(path):
    """Fail-open assumé : une prédiction publiée sans garde-fou vaut mieux
    qu'une journée sans prédiction."""
    guard = DirectionGuard.load(path, 'nhl')
    assert not guard
    keep, held = guard.split([_Bet('total', 'under_6.5')])
    assert len(keep) == 1 and not held


def test_fichier_corrompu_inerte(tmp_path):
    path = tmp_path / 'direction.json'
    path.write_text('pas du json', encoding='utf-8')
    assert not DirectionGuard.load(path, 'nhl')
