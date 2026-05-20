"""
value_finder.py — Croise les prédictions NHL avec les cotes bookmaker.

Markets croisables avec The-Odds API NHL :
    - moneyline (home/away) avec best-line shopping
    - total over/under (ligne consensus)

Les autres markets (P1, exact_score, goal_intervals, btts) sont prédits mais
sans cotes API standard → pas de value bet automatique (sauf source externe).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from vizer_core import ValueBet

from .odds_client import GameOdds

if TYPE_CHECKING:
    from .unified_predictor import NHLUnifiedPredictor


def find_value_bets(
    predictor: "NHLUnifiedPredictor",
    game_odds: GameOdds,
) -> list[ValueBet]:
    """
    Pour un match avec ses cotes, calcule les value bets (moneyline + total).

    Returns:
        Liste de ValueBet triée par edge décroissant.
    """
    if game_odds.home == "???" or game_odds.away == "???":
        return []
    if not predictor.has_team(game_odds.home) or not predictor.has_team(game_odds.away):
        return []

    features = predictor._prepare_features(game_odds.home, game_odds.away)
    if features is None:
        return []

    bets: list[ValueBet] = []

    # ─── Moneyline ────────────────────────────────────────────────────
    if predictor.registry.has('moneyline'):
        try:
            ml = predictor.registry.get('moneyline')
            pred = ml.predict(game_odds.home, game_odds.away,
                              context={'features_row': features})
            best_home, best_away = game_odds.best_moneyline_odds()
            if best_home:
                vb = ml.value_bet(pred, 'home', best_home)
                if vb:
                    bets.append(vb)
            if best_away:
                vb = ml.value_bet(pred, 'away', best_away)
                if vb:
                    bets.append(vb)
        except Exception as e:
            print(f"  ⚠️  Échec ML {game_odds.home} vs {game_odds.away}: {e}")

    # ─── Total O/U ────────────────────────────────────────────────────
    consensus_line = game_odds.consensus_total_line()
    if consensus_line is not None and predictor.registry.has('total'):
        try:
            total = predictor.registry.get('total')
            pred = total.predict_for_line(
                game_odds.home, game_odds.away,
                line=consensus_line, context={'features_row': features},
            )
            best_over, best_under = game_odds.best_over_under_odds(consensus_line)
            if best_over:
                vb = total.value_bet(pred, f'over_{consensus_line}', best_over)
                if vb:
                    bets.append(vb)
            if best_under:
                vb = total.value_bet(pred, f'under_{consensus_line}', best_under)
                if vb:
                    bets.append(vb)
        except Exception as e:
            print(f"  ⚠️  Échec Total {game_odds.home} vs {game_odds.away}: {e}")

    bets.sort(key=lambda b: -b.edge)
    return bets
