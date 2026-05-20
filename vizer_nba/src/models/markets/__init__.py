"""
Marchés NBA — chaque marché est un module pluggable héritant de
vizer_core.MarketBase. Ajouter un nouveau marché = créer un fichier ici,
sans toucher au reste du pipeline.

Architecture :
    MarketBase (vizer_core)
        ├── MoneylineMarket           (wrap NBAMatchPredictor pour la victoire)
        ├── TotalMarket               (wrap NBATotalPredictor — XGB régresseur)
        ├── TotalPoissonMarket        (wrap PoissonTotalPredictor — Poisson conjoint)
        ├── HomeTeamTotalMarket       (wrap TeamTotalPredictor side='home')
        └── AwayTeamTotalMarket       (wrap TeamTotalPredictor side='away')

À venir : SpreadMarket, PeriodTotalMarket, PeriodWinnerMarket,
TeamTotalPoissonMarket (extension Poisson aux team totals).
"""
from .moneyline import MoneylineMarket
from .total import TotalMarket
from .total_poisson import TotalPoissonMarket
from .team_total import HomeTeamTotalMarket, AwayTeamTotalMarket

# Mapping {nom_marché_config → Classe}.
# Les noms doivent matcher les clés de markets: dans config.yaml.
AVAILABLE_MARKETS: dict[str, type] = {
    'win': MoneylineMarket,                 # nom historique côté NBA (compat)
    'moneyline': MoneylineMarket,           # nom standardisé vizer_core
    'total': TotalMarket,                   # XGB régresseur + sigma gaussien
    'total_poisson': TotalPoissonMarket,    # Poisson conjoint + distribution exacte
    'home_team_total': HomeTeamTotalMarket,
    'away_team_total': AwayTeamTotalMarket,
}


def get_market_class(name: str) -> type:
    """Récupère la classe de marché par son nom, ou lève KeyError explicite."""
    if name not in AVAILABLE_MARKETS:
        raise KeyError(
            f"Marché '{name}' inconnu. "
            f"Disponibles : {sorted(AVAILABLE_MARKETS.keys())}"
        )
    return AVAILABLE_MARKETS[name]


__all__ = [
    "MoneylineMarket",
    "TotalMarket",
    "TotalPoissonMarket",
    "HomeTeamTotalMarket",
    "AwayTeamTotalMarket",
    "AVAILABLE_MARKETS",
    "get_market_class",
]
