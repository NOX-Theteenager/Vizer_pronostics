"""
UnifiedPredictor — Façade pour l'inférence multi-marchés.

Utilisée par predict_today.py et predict_json.py. Cache la complexité du
registre et offre une API simple :

    predictor = UnifiedPredictor('models/nba_model.joblib')
    results = predictor.predict('LAL', 'GSW')
    # → {'moneyline': MarketPrediction, 'total': MarketPrediction, ...}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .market_base import MarketPrediction, ValueBet
from .model_registry import ModelRegistry


class UnifiedPredictor:
    """Façade d'inférence."""

    def __init__(self, registry_path: str | Path):
        """
        Args:
            registry_path : Chemin vers le fichier .joblib du registre.
        """
        self._registry: ModelRegistry = ModelRegistry.load(registry_path)
        self._registry_path = Path(registry_path)

    # =============================================================== Inférence
    def predict(
        self,
        home: str,
        away: str,
        markets: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, MarketPrediction]:
        """
        Prédit pour un match sur les marchés demandés (ou tous si None).

        Args:
            home, away : abréviations 3 lettres.
            markets    : liste des noms de marchés à interroger.
                         None → tous les marchés enregistrés ET actifs.
            context    : passé tel quel à chaque marché (gardiens, repos, ...).

        Returns:
            Dict {market_name: MarketPrediction}.
            Les marchés qui lèvent une exception sont silencieusement omis
            mais loggés via print stderr.
        """
        import sys

        target_markets = markets if markets is not None else self._registry.list_enabled()
        context = context or {}
        results: dict[str, MarketPrediction] = {}

        for name in target_markets:
            if not self._registry.has(name):
                print(f"⚠️  Marché '{name}' non enregistré, ignoré.", file=sys.stderr)
                continue
            market = self._registry.get(name)
            if not market.enabled:
                continue
            try:
                results[name] = market.predict(home, away, context=context)
            except Exception as e:
                print(f"✗ Erreur prédiction '{name}' ({home} vs {away}): {e}", file=sys.stderr)

        return results

    # ============================================================== Value bets
    def value_bets(
        self,
        home: str,
        away: str,
        odds: dict[str, dict[str, float]],
        context: dict[str, Any] | None = None,
    ) -> list[ValueBet]:
        """
        Calcule les value bets pour un match donné.

        Args:
            odds : dict imbriqué {market_name: {selection: bookmaker_odds}}.
                   Exemple :
                   {
                       'moneyline': {'home': 1.85, 'away': 2.10},
                       'total':     {'over': 1.95, 'under': 1.90},
                   }

        Returns:
            Liste de ValueBet triée par edge décroissant.
        """
        # Ne prédire que les marchés pour lesquels on a des cotes
        markets_to_predict = [m for m in odds.keys() if self._registry.has(m)]
        predictions = self.predict(home, away, markets=markets_to_predict, context=context)

        bets: list[ValueBet] = []
        for market_name, market_odds in odds.items():
            if market_name not in predictions:
                continue
            pred = predictions[market_name]
            market = self._registry.get(market_name)
            for selection, book_odds in market_odds.items():
                bet = market.value_bet(pred, selection, book_odds)
                if bet is not None:
                    bets.append(bet)

        bets.sort(key=lambda b: b.edge, reverse=True)
        return bets

    # ================================================================ Helpers
    @property
    def sport(self) -> str:
        return self._registry.sport

    @property
    def registry(self) -> ModelRegistry:
        """Accès direct au registre pour cas avancés (debug, inspection)."""
        return self._registry

    def list_markets(self) -> list[str]:
        return self._registry.list_enabled()

    def __repr__(self) -> str:
        return (
            f"<UnifiedPredictor sport='{self.sport}' "
            f"markets={self.list_markets()}>"
        )
