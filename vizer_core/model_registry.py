"""
ModelRegistry — Conteneur unifié pour tous les marchés d'un sport.

Remplace l'idée d'un bundle joblib opaque (NHL V5.6) ET le ModelRegistry
spécifique NBA, en généralisant l'interface.

Persistance :
- Un seul fichier .joblib qui contient tous les marchés + métadonnées.
- Chargement instantané, pas de gestion de fichiers multiples.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import joblib

from .market_base import MarketBase


class ModelRegistry:
    """
    Conteneur de marchés et métadonnées globales.

    Usage typique (entraînement) :
        registry = ModelRegistry(sport='nba')
        registry.register(moneyline_market)
        registry.register(total_market)
        registry.set_metadata('train_seasons', '2000-2025')
        registry.save('models/nba_model.joblib')

    Usage typique (inférence) :
        registry = ModelRegistry.load('models/nba_model.joblib')
        market = registry.get('moneyline')
        prediction = market.predict('LAL', 'GSW')
    """

    REGISTRY_VERSION = "1.0.0"

    def __init__(self, sport: str = "unknown"):
        self.sport: str = sport
        self.version: str = self.REGISTRY_VERSION
        self.created_at: str = datetime.utcnow().isoformat()
        self._markets: dict[str, MarketBase] = {}
        self._metrics: dict[str, dict[str, float]] = {}
        self._metadata: dict[str, Any] = {}

    # =============================================================== Markets
    def register(
        self,
        market: MarketBase,
        metrics: dict[str, float] | None = None,
    ) -> None:
        """Enregistre un marché entraîné dans le registre."""
        if not isinstance(market, MarketBase):
            raise TypeError(
                f"register attend une instance de MarketBase, reçu: {type(market).__name__}"
            )
        if not market.name:
            raise ValueError("Le marché doit avoir un attribut `name` non vide.")
        if market.name in self._markets:
            raise ValueError(
                f"Marché '{market.name}' déjà enregistré. "
                "Utiliser .unregister() d'abord ou recréer le registre."
            )
        self._markets[market.name] = market
        if metrics:
            self._metrics[market.name] = dict(metrics)

    def unregister(self, name: str) -> None:
        self._markets.pop(name, None)
        self._metrics.pop(name, None)

    def get(self, name: str) -> MarketBase:
        if name not in self._markets:
            raise KeyError(
                f"Marché '{name}' non trouvé. "
                f"Marchés disponibles : {self.list_markets()}"
            )
        return self._markets[name]

    def has(self, name: str) -> bool:
        return name in self._markets

    def list_markets(self) -> list[str]:
        return sorted(self._markets.keys())

    def list_enabled(self) -> list[str]:
        return sorted(n for n, m in self._markets.items() if m.enabled)

    # ============================================================ Métadonnées
    def set_metadata(self, key: str, value: Any) -> None:
        """Stocke une métadonnée libre (durée d'entraînement, n_samples, ...)."""
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)

    def set_metrics(self, market_name: str, metrics: dict[str, float]) -> None:
        self._metrics[market_name] = dict(metrics)

    def get_metrics(self, market_name: str) -> dict[str, float]:
        return dict(self._metrics.get(market_name, {}))

    # =========================================================== Persistance
    def save(self, path: str | Path) -> None:
        """Sauvegarde le registre entier dans un fichier joblib."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sport": self.sport,
            "version": self.version,
            "created_at": self.created_at,
            "markets": self._markets,
            "metrics": self._metrics,
            "metadata": self._metadata,
        }
        joblib.dump(payload, path)

    @classmethod
    def load(cls, path: str | Path) -> "ModelRegistry":
        """Charge un registre sauvegardé."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Registre introuvable : {path}")
        payload = joblib.load(path)

        # Validation minimale
        required_keys = {"sport", "version", "markets", "metrics", "metadata"}
        missing = required_keys - set(payload.keys())
        if missing:
            raise ValueError(
                f"Registre invalide (clés manquantes : {sorted(missing)}). "
                f"Probablement un fichier d'une version antérieure."
            )

        registry = cls(sport=payload["sport"])
        registry.version = payload["version"]
        registry.created_at = payload.get("created_at", "unknown")
        registry._markets = payload["markets"]
        registry._metrics = payload["metrics"]
        registry._metadata = payload["metadata"]
        return registry

    # =============================================================== Affichage
    def print_summary(self) -> None:
        """Affiche un résumé console du registre."""
        print("=" * 70)
        print(f"📦 MODEL REGISTRY — {self.sport.upper()}")
        print("=" * 70)
        print(f"Version       : {self.version}")
        print(f"Créé le       : {self.created_at}")
        print(f"Marchés       : {len(self._markets)} ({len(self.list_enabled())} actifs)")
        print()

        if self._markets:
            print("Marchés enregistrés :")
            print("-" * 70)
            for name in self.list_markets():
                market = self._markets[name]
                flag = "✓" if market.enabled else "✗"
                fitted = "fitted" if market.is_fitted else "NOT FITTED"
                print(f"  {flag} {name:20s} ({type(market).__name__}, {fitted})")
                metrics = self._metrics.get(name, {})
                if metrics:
                    # Formater chaque métrique selon son type (les predictors peuvent
                    # stocker des DataFrames de feature_importance, qu'on affiche en résumé)
                    parts = []
                    for k, v in metrics.items():
                        if isinstance(v, bool):
                            parts.append(f"{k}={v}")
                        elif isinstance(v, (int, float)):
                            parts.append(f"{k}={v:.4f}")
                        elif hasattr(v, 'shape'):  # DataFrame ou ndarray
                            parts.append(f"{k}=<{type(v).__name__} {v.shape}>")
                        elif isinstance(v, (list, dict)):
                            parts.append(f"{k}=<{type(v).__name__}[{len(v)}]>")
                        else:
                            parts.append(f"{k}={v!r}")
                    metric_str = ", ".join(parts)
                    print(f"      ↳ {metric_str}")
            print()

        if self._metadata:
            print("Métadonnées :")
            print("-" * 70)
            for key, val in self._metadata.items():
                # Tronquer les valeurs longues (ex: dict de player values)
                display = repr(val)
                if len(display) > 80:
                    display = display[:77] + "..."
                print(f"  • {key:25s} : {display}")
            print()
        print("=" * 70)

    def __repr__(self) -> str:
        return (
            f"<ModelRegistry sport='{self.sport}' "
            f"markets={len(self._markets)} "
            f"enabled={len(self.list_enabled())}>"
        )
