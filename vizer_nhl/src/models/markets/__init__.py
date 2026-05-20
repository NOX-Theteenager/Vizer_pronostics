"""
Markets NHL disponibles.

Pattern service-backed : chaque market réfère à un engine entraîné une fois
et stocké dans le ModelRegistry. Voir vizer_nhl/train.py pour l'orchestration.

8 markets opérationnels (Sessions 1-4) :
  - moneyline       (NHLMoneylineEngine)
  - total, btts     (NHLPoissonEngine)
  - p1_winner, p1_total, p1_btts  (NHLPoissonEngineP1)
  - exact_score, goal_intervals    (NHLPoissonEngine)
"""
from .moneyline import MoneylineMarket
from .total import TotalMarket
from .btts import BTTSMarket
from .p1_winner import P1WinnerMarket
from .p1_total import P1TotalMarket
from .p1_btts import P1BTTSMarket
from .exact_score import ExactScoreMarket
from .goal_intervals import GoalIntervalsMarket


AVAILABLE_MARKETS: dict[str, type] = {
    'moneyline':       MoneylineMarket,
    'total':           TotalMarket,
    'btts':            BTTSMarket,
    'p1_winner':       P1WinnerMarket,
    'p1_total':        P1TotalMarket,
    'p1_btts':         P1BTTSMarket,
    'exact_score':     ExactScoreMarket,
    'goal_intervals':  GoalIntervalsMarket,
}


# Mapping {market_name → service_name requis} pour orchestration train.py
MARKET_TO_SERVICE: dict[str, str] = {
    'moneyline':       'moneyline',   # NHLMoneylineEngine
    'total':           'poisson',     # NHLPoissonEngine
    'btts':            'poisson',
    'p1_winner':       'poisson_p1',  # NHLPoissonEngineP1
    'p1_total':        'poisson_p1',
    'p1_btts':         'poisson_p1',
    'exact_score':     'poisson',
    'goal_intervals':  'poisson',
}


def get_market_class(name: str) -> type:
    if name not in AVAILABLE_MARKETS:
        raise KeyError(
            f"Market NHL inconnu : '{name}'. "
            f"Disponibles : {sorted(AVAILABLE_MARKETS.keys())}"
        )
    return AVAILABLE_MARKETS[name]


__all__ = [
    'MoneylineMarket', 'TotalMarket', 'BTTSMarket',
    'P1WinnerMarket', 'P1TotalMarket', 'P1BTTSMarket',
    'ExactScoreMarket', 'GoalIntervalsMarket',
    'AVAILABLE_MARKETS', 'MARKET_TO_SERVICE', 'get_market_class',
]
