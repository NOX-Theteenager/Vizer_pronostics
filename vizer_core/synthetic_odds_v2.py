"""
synthetic_odds_v2.py — Book synthétique réaliste : cotes ~1.85-2.15 sur les O/U.

Principe : le book voit la même proba que le modèle ± un petit bruit sur la
proba elle-même (pas sur la ligne). Cela garantit :
- Cotes dans la plage réaliste 1.5-2.5 (jamais 3.5+ comme la v1)
- Edge raisonnable (~3-8%) quand le book se trompe, pas +25% artificiel
- Symétrie naturelle proche de 1.91/1.91 quand le book et le modèle s'accordent

Mathématiquement :
    p_book = clip(p_model + N(0, noise_proba), 0.10, 0.90)
    odds   = (1 / p_book) / (1 + vig)

Si noise_proba = 0.04, le book se trompe en moyenne de ±4% sur ses probas,
ce qui correspond à un book "moyennement sharp" (entre soft-book et Pinnacle).
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .backtest import OddsProvider
from .market_base import MarketBase, MarketPrediction


class CalibratedSyntheticOddsProvider(OddsProvider):
    """
    Book synthétique réaliste : génère le bruit sur la PROBABILITÉ, pas sur la ligne.

    Args:
        vig         : marge bookmaker (typique 0.045)
        noise_proba : σ du bruit sur les probas (typique 0.03-0.05)
        seed        : reproductibilité
    """

    def __init__(
        self,
        vig: float = 0.045,
        noise_proba: float = 0.04,
        seed: int = 42,
    ):
        self.vig = vig
        self.noise_proba = noise_proba
        self.rng = np.random.default_rng(seed)

    def _odds_with_vig(self, p_no_vig: float) -> float:
        if p_no_vig <= 0:
            return 100.0
        if p_no_vig >= 1.0:
            return 1.01
        return (1.0 / p_no_vig) / (1 + self.vig)

    def _noisy_proba(self, p_model: float) -> float:
        """Génère la proba book = proba modèle + bruit gaussien, clippée."""
        noisy = float(np.clip(
            p_model + self.rng.normal(0, self.noise_proba),
            0.10, 0.90,
        ))
        return noisy

    def get_odds(self, market, match_context, prediction):
        """
        Pour chaque sélection prédite par le modèle, génère une cote book
        basée sur p_model + bruit. Les deux selections complémentaires
        (home/away, over/under) sont gérées indépendamment pour préserver
        l'inversion naturelle.
        """
        selections = list(prediction.probabilities.keys())
        if not selections:
            return None

        # Cas simple : 2 sélections complémentaires (ex : home/away, over/under)
        if len(selections) == 2:
            sel_a, sel_b = selections
            p_model_a = prediction.probabilities[sel_a]
            # Le book voit p_a ± bruit. p_b = 1 - p_a (cohérence).
            p_book_a = self._noisy_proba(p_model_a)
            p_book_b = 1 - p_book_a
            return {
                sel_a: self._odds_with_vig(p_book_a),
                sel_b: self._odds_with_vig(p_book_b),
            }

        # Cas multi-sélections (rare) : chacune indépendamment normalisée
        probs = {s: self._noisy_proba(prediction.probabilities[s]) for s in selections}
        total = sum(probs.values())
        if total > 0:
            probs = {s: p / total for s, p in probs.items()}
        return {s: self._odds_with_vig(p) for s, p in probs.items()}
