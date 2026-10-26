"""
publication.py — Enrichissements publiés dans le JSON quotidien NBA.

Même contrat que `vizer_nhl/src/api/publication.py`. Les noms de champs
diffèrent côté client de cotes (`moneyline_home` ici, `home_ml` en NHL), d'où
deux implémentations plutôt qu'une abstraction prématurée.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .odds_client import GameOdds

_OU = re.compile(r'^(over|under)_(.+)$')

# Tolérance de comparaison des lignes. La ligne vient d'un côté du nom de la
# sélection (`under_228.5`, donc d'une chaîne) et de l'autre du JSON de l'API :
# deux chemins de conversion pour la même valeur. Un seul seuil, partagé par
# les deux branches, qui en avaient deux différents.
_LINE_TOL = 0.01


def books_for_bet(game: GameOdds, market: str, selection: str) -> list[dict[str, Any]]:
    """Cotes de tous les bookmakers pour (market, selection), triées décroissant."""
    rows: list[tuple[str, float]] = []
    m = _OU.match(selection)
    line: Optional[float] = None
    side: Optional[str] = None
    if m:
        side = m.group(1)
        try:
            line = float(m.group(2))
        except ValueError:
            line = None

    if market in ('moneyline', 'win'):
        for b in game.bookmakers:
            odds = (
                b.moneyline_home if selection == 'home'
                else b.moneyline_away if selection == 'away'
                else None
            )
            if odds:
                rows.append((b.bookmaker, float(odds)))

    elif market == 'total' and line is not None:
        for b in game.bookmakers:
            for t in b.totals:
                # `t.line`, pas `t.point` : `TotalsLine` n'a jamais eu de champ
                # `point`, et la branche voisine des totals d'équipe écrivait
                # bien `line`. La faute n'est apparue que le 26/10/2026, au
                # premier run où des cotes NBA sont arrivées — la requête
                # échouait en amont depuis l'ouverture de la saison, donc ce
                # code n'avait jamais tourné.
                if abs(t.line - line) < _LINE_TOL:
                    odds = t.over_odds if side == 'over' else t.under_odds
                    if odds:
                        rows.append((b.bookmaker, float(odds)))

    elif market in ('home_team_total', 'away_team_total') and line is not None:
        team_name = game.home_full if market == 'home_team_total' else game.away_full
        for b in game.bookmakers:
            for t in b.team_totals:
                if t.team_full_name == team_name and abs(t.line - line) < _LINE_TOL:
                    odds = t.over_odds if side == 'over' else t.under_odds
                    if odds:
                        rows.append((b.bookmaker, float(odds)))

    if not rows:
        return []

    rows.sort(key=lambda r: r[1], reverse=True)
    best = rows[0][1]
    return [
        {'name': name, 'odds': round(odds, 2), 'best': abs(odds - best) < 1e-9}
        for name, odds in rows
    ]


def match_context(history, home: str, away: str) -> dict[str, Any]:
    """Forme récente des deux équipes + confrontations directes."""
    out: dict[str, Any] = {}
    home_form = history.recent_form(home)
    away_form = history.recent_form(away)
    if home_form or away_form:
        out['form'] = {'home': home_form, 'away': away_form}
    h2h = history.head_to_head(home, away)
    if h2h:
        out['h2h'] = h2h
    return out
