"""
publication.py — Enrichissements publiés dans le JSON quotidien NHL.

Le backend ne publiait jusqu'ici que la meilleure cote retenue. La PWA affiche
aussi le comparatif entre bookmakers : on expose donc, pour chaque value bet,
la cote de **chaque** book sur la même sélection.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .odds_client import GameOdds

_OU = re.compile(r'^(over|under)_(.+)$')


def books_for_bet(game: GameOdds, market: str, selection: str) -> list[dict[str, Any]]:
    """
    Cotes de tous les bookmakers pour (market, selection), triées décroissant.

    Retourne une liste vide si le marché n'est pas couvert par les books — la
    PWA masque alors le comparatif au lieu d'inventer des concurrents.
    """
    rows: list[tuple[str, float]] = []

    if market == 'moneyline':
        for b in game.bookmakers:
            odds = b.home_ml if selection == 'home' else b.away_ml if selection == 'away' else None
            if odds:
                rows.append((b.bookmaker, float(odds)))

    elif market == 'total':
        m = _OU.match(selection)
        if m:
            side, raw_line = m.group(1), m.group(2)
            try:
                line = float(raw_line)
            except ValueError:
                return []
            for b in game.bookmakers:
                for t in b.totals:
                    if abs(t.point - line) < 1e-6:
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
    home_form: Optional[dict[str, Any]] = history.recent_form(home)
    away_form: Optional[dict[str, Any]] = history.recent_form(away)
    if home_form or away_form:
        out['form'] = {'home': home_form, 'away': away_form}
    h2h = history.head_to_head(home, away)
    if h2h:
        out['h2h'] = h2h
    return out
