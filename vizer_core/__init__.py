"""
vizer_core — Abstractions partagées entre les projets de prédiction sportive.

Ce package contient UNIQUEMENT du code agnostique au sport :
- BasePredictor      : contrat d'un modèle ML
- MarketBase         : contrat d'un marché de paris
- MarketPrediction   : dataclass de sortie d'un marché
- ValueBet           : dataclass d'un pari à valeur
- ModelRegistry      : conteneur unifié de marchés
- UnifiedPredictor   : façade haut niveau
- load_config        : chargement et validation de config.yaml

Aucune logique métier (features, API, conventions de saison) ne doit
être ajoutée ici. Voir ARCHITECTURE.md section 12.
"""
from .base_predictor import BasePredictor
from .market_base import MarketBase, MarketPrediction, ValueBet
from .model_registry import ModelRegistry
from .unified_predictor import UnifiedPredictor
from .config_loader import load_config, ConfigError
from .utils import detect_target_leakage, assert_no_leakage, LeakageError
from .backtest import (
    Backtester, BacktestConfig, BacktestResult,
    BetRecord, MarketBacktestSummary, CalibrationBucket,
    OddsProvider, NullOddsProvider, SyntheticOddsProvider, CSVOddsProvider,
)
from .synthetic_odds_v2 import CalibratedSyntheticOddsProvider

__version__ = "0.3.0"

__all__ = [
    "BasePredictor",
    "MarketBase",
    "MarketPrediction",
    "ValueBet",
    "ModelRegistry",
    "UnifiedPredictor",
    "load_config",
    "ConfigError",
    "detect_target_leakage",
    "assert_no_leakage",
    "LeakageError",
    "Backtester",
    "BacktestConfig",
    "BacktestResult",
    "BetRecord",
    "MarketBacktestSummary",
    "CalibrationBucket",
    "OddsProvider",
    "NullOddsProvider",
    "SyntheticOddsProvider",
    "CalibratedSyntheticOddsProvider",
    "CSVOddsProvider",
]
