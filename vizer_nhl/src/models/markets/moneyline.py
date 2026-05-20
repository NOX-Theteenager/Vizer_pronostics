"""
MoneylineMarket — Vainqueur du match NHL (P(home_wins)).

Pattern "service-backed" : le market ne contient PAS son propre modèle. Il
référence le NHLMoneylineEngine (entraîné une fois et stocké dans le registry)
et le consomme à la prédiction.

Avantage : un seul fit du engine alimente plusieurs marchés (moneyline,
close_game proxy via P(home), futurs P1_winner si on l'étend).
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from vizer_core import MarketBase, MarketPrediction

from ...models.moneyline_engine import NHLMoneylineEngine


class MoneylineMarket(MarketBase):
    """
    Marché Moneyline NHL : retourne {'home', 'away'} avec probabilités calibrées.

    Service requis : 'moneyline' (NHLMoneylineEngine pré-entraîné).
    """

    name = "moneyline"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._engine: Optional[NHLMoneylineEngine] = None

    # --------------------------------------------------------- fit (no-op si service injecté)
    def fit(
        self,
        train_df: pd.DataFrame,
        test_df: Optional[pd.DataFrame] = None,
        verbose: bool = True,
        services: Optional[dict[str, Any]] = None,
    ) -> dict[str, float]:
        """
        Le market est "service-backed" : pas d'entraînement propre.
        Reçoit le NHLMoneylineEngine déjà fitted via services.

        Args:
            services : doit contenir {'moneyline': NHLMoneylineEngine fitted}
        """
        if services is None or 'moneyline' not in services:
            raise ValueError(
                "MoneylineMarket requiert services={'moneyline': NHLMoneylineEngine fitted}. "
                "Le service doit être entraîné AVANT le market (cf. train.py orchestration)."
            )
        engine = services['moneyline']
        if not isinstance(engine, NHLMoneylineEngine):
            raise TypeError(
                f"services['moneyline'] doit être NHLMoneylineEngine, "
                f"reçu {type(engine).__name__}"
            )
        if not engine.is_fitted:
            raise RuntimeError(
                "Le NHLMoneylineEngine doit être .fit() avant d'être injecté dans MoneylineMarket."
            )

        self._engine = engine
        self._is_fitted = True

        # Retourne les métriques du engine pour les remonter dans le registre
        if engine.metrics:
            return engine.metrics.to_dict()
        return {}

    # ------------------------------------------------------------- predict
    def predict(
        self,
        home: str,
        away: str,
        context: Optional[dict[str, Any]] = None,
    ) -> MarketPrediction:
        """
        Args:
            context : doit contenir 'features_row' : pd.DataFrame d'une ligne
                      avec toutes les features attendues par l'engine.
        """
        if not self._is_fitted or self._engine is None:
            raise RuntimeError(f"{type(self).__name__} non entraîné.")
        if context is None or 'features_row' not in context:
            raise ValueError(
                "MoneylineMarket.predict requiert context={'features_row': DataFrame}"
            )

        features_row = context['features_row']
        p_home_arr = self._engine.predict_proba_home_wins(features_row)
        p_home = float(p_home_arr[0])
        p_away = 1.0 - p_home

        confidence_proba = max(p_home, p_away)
        if confidence_proba >= 0.65:
            confidence = "high"
        elif confidence_proba >= 0.55:
            confidence = "medium"
        else:
            confidence = "low"

        return MarketPrediction(
            market_name=self.name,
            probabilities={'home': p_home, 'away': p_away},
            expected_value=None,
            confidence=confidence,
            metadata={
                'home_team': home,
                'away_team': away,
                'temperature': self._engine.calibrator.T if self._engine.calibrator else None,
                'best_model': self._engine.best_name,
                'engine': 'NHLMoneylineEngine',
            },
        )

    @property
    def engine(self) -> Optional[NHLMoneylineEngine]:
        return self._engine
