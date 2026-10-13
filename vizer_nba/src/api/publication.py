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
                if abs(t.point - line) < 1e-6:
                    odds = t.over_odds if side == 'over' else t.under_odds
                    if odds:
                        rows.append((b.bookmaker, float(odds)))

    elif market in ('home_team_total', 'away_team_total') and line is not None:
        team_name = game.home_full if market == 'home_team_total' else game.away_full
        for b in game.bookmakers:
            for t in b.team_totals:
                if t.team_full_name == team_name and abs(t.line - line) < 0.01:
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
