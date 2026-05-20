"""
value_finder.py — Croise les prédictions du modèle avec les cotes bookmaker
et produit la liste des value bets exploitables.

Utilise les méthodes value_bet() des Markets de vizer_core (calcul Kelly,
edge thresholds, confidence), donc cohérent avec l'architecture MarketBase.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, TYPE_CHECKING

from vizer_core import ValueBet

from .odds_client import GameOdds

if TYPE_CHECKING:
    # Import différé pour éviter une dépendance cyclique au chargement.
    from .unified_predictor import UnifiedPredictor


def find_value_bets(
    predictor: "UnifiedPredictor",
    game_odds: GameOdds,
    date: str | None = None,
    home_talent_ratio: float = 1.0,
    away_talent_ratio: float = 1.0,
) -> list[ValueBet]:
    """
    Pour un match avec ses cotes bookmaker, calcule tous les value bets.

    Marchés couverts :
        - moneyline (home/away) avec best line shopping
        - total over/under sur la ligne consensus (médiane bookmakers)

    Args:
        predictor : UnifiedPredictor déjà chargé.
        game_odds : cotes pour le match (depuis OddsAPIClient).
        date      : date du match (YYYY-MM-DD), pour les features.

    Returns:
        Liste de ValueBet triée par edge décroissant.
    """
    if game_odds.home == "???" or game_odds.away == "???":
        # Équipe non mappée — on skip
        return []

    bets: list[ValueBet] = []

    # ─── Préparer les features une seule fois ─────────────────────────
    features = predictor._prepare_game_features(
        game_odds.home, game_odds.away, date,
        home_talent_ratio, away_talent_ratio,
    )

    # ─── Marché Moneyline ─────────────────────────────────────────────
    try:
        ml_market = predictor._get_moneyline_market()
        ml_pred = ml_market.predict(
            game_odds.home, game_odds.away,
            context={'features_row': features},
        )
        # Best line shopping : on prend la meilleure cote disponible
        best_home_odds, best_away_odds = game_odds.best_moneyline_odds()
        if best_home_odds:
            vb = ml_market.value_bet(ml_pred, 'home', best_home_odds)
            if vb:
                bets.append(vb)
        if best_away_odds:
            vb = ml_market.value_bet(ml_pred, 'away', best_away_odds)
            if vb:
                bets.append(vb)
    except Exception as e:
        print(f"  ⚠️  Échec value bet moneyline ({game_odds.home} vs {game_odds.away}): {e}")

    # ─── Marché Total O/U ─────────────────────────────────────────────
    consensus_line = game_odds.consensus_total_line()
    if consensus_line is not None:
        try:
            total_market = predictor.registry.get('total')
            t_pred = total_market.predict_for_line(
                game_odds.home, game_odds.away,
                line=consensus_line,
                context={'features_row': features},
            )
            best_over, best_under = game_odds.best_over_under_odds(consensus_line)
            if best_over:
                vb = total_market.value_bet(t_pred, f'over_{consensus_line}', best_over)
                if vb:
                    bets.append(vb)
            if best_under:
                vb = total_market.value_bet(t_pred, f'under_{consensus_line}', best_under)
                if vb:
                    bets.append(vb)
        except Exception as e:
            print(f"  ⚠️  Échec value bet total ({game_odds.home} vs {game_odds.away}): {e}")

    # ─── Marchés Team Total O/U (étape 6) ─────────────────────────────
    # Si le registre a les markets et que les cotes existent, on calcule.
    for side in ('home', 'away'):
        market_name = f"{side}_team_total"
        if not predictor.registry.has(market_name):
            continue
        consensus_tt = game_odds.consensus_team_total_line(side)
        if consensus_tt is None:
            continue
        try:
            tt_market = predictor.registry.get(market_name)
            tt_pred = tt_market.predict_for_line(
                game_odds.home, game_odds.away,
                line=consensus_tt,
                context={'features_row': features},
            )
            best_over, best_under = game_odds.best_team_over_under_odds(side, consensus_tt)
            if best_over:
                vb = tt_market.value_bet(tt_pred, f'over_{consensus_tt}', best_over)
                if vb:
                    bets.append(vb)
            if best_under:
                vb = tt_market.value_bet(tt_pred, f'under_{consensus_tt}', best_under)
                if vb:
                    bets.append(vb)
        except Exception as e:
            print(f"  ⚠️  Échec value bet {market_name} "
                  f"({game_odds.home} vs {game_odds.away}): {e}")

    bets.sort(key=lambda b: b.edge, reverse=True)
    return bets


def format_value_bet_human(vb: ValueBet, home: str, away: str) -> str:
    """Format human-readable pour affichage console."""
    selection_human = {
        'home': f"{home} (domicile)",
        'away': f"{away} (visiteur)",
    }.get(vb.selection, vb.selection)
    # Pour over/under, le selection est 'over_222.5' ou 'under_222.5'
    if vb.selection.startswith('over_') or vb.selection.startswith('under_'):
        side, line = vb.selection.split('_')
        # Team totals : préfixer avec le team name pour clarté
        if vb.market_name == 'home_team_total':
            selection_human = f"{home} {side.upper()} {line}"
        elif vb.market_name == 'away_team_total':
            selection_human = f"{away} {side.upper()} {line}"
        else:
            selection_human = f"{side.upper()} {line}"

    conf_emoji = {'high': '🟢', 'medium': '🟡', 'low': '⚪'}.get(vb.confidence, '⚪')

    return (
        f"  {conf_emoji} {vb.market_name:9s} {selection_human:25s} "
        f"@ {vb.bookmaker_odds:5.2f}  "
        f"edge={vb.edge:+.3f}  "
        f"kelly={vb.kelly_stake*100:.2f}% bankroll"
    )


def value_bet_to_dict(vb: ValueBet) -> dict[str, Any]:
    """Sérialise un ValueBet pour JSON."""
    return {
        'market': vb.market_name,
        'selection': vb.selection,
        'predicted_probability': round(vb.predicted_proba, 4),
        'bookmaker_odds': round(vb.bookmaker_odds, 2),
        'implied_probability': round(vb.implied_proba, 4),
        'edge': round(vb.edge, 4),
        'kelly_stake_fraction': round(vb.kelly_stake, 4),
        'expected_value_per_unit': round(vb.expected_value_per_unit, 4),
        'confidence': vb.confidence,
    }
