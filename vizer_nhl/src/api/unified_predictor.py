"""
unified_predictor.py — Interface de prédiction haut-niveau pour la NHL.

Charge le registre entraîné + reconstruit les features d'un matchup futur via
TeamStateBuilder + NHLFeatureEngineer.transform(), puis prédit les 8 markets.

Usage :
    up = NHLUnifiedPredictor('models/nhl_model.pkl', 'data/dataset_agrege_vizer_nhl.csv')
    result = up.predict_all('TOR', 'MTL')
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from vizer_core import ModelRegistry, top_contributions

from ..data.history import NHLMatchHistory
from ..data.loader import NHLDataLoader
from ..features.engineer import NHLFeatureEngineer
from .team_state import TeamStateBuilder


class NHLUnifiedPredictor:
    """
    Prédicteur unifié NHL. Reconstruit les features d'un matchup et prédit
    tous les markets enregistrés dans le modèle.
    """

    def __init__(
        self,
        model_path: str = 'models/nhl_model.pkl',
        dataset_path: str = 'data/dataset_agrege_vizer_nhl.csv',
        data_dir: str = 'data',
        dataset_filename: str = 'dataset_agrege_vizer_nhl.csv',
    ):
        self.registry = ModelRegistry.load(model_path)
        # La config des marchés est figée dans le pickle à l'entraînement :
        # on réapplique celle du dépôt pour qu'un changement de seuil, de
        # facteur Kelly ou de `enabled` prenne effet sans réentraîner.
        self._apply_live_config()
        self.meta = getattr(self.registry, '_metadata', {}) or {}

        # Charger le dataset pour reconstruire l'état des équipes
        self.loader = NHLDataLoader(data_dir=data_dir, filename=dataset_filename)
        df = self.loader.load(exclude_anomalous_seasons=False)

        # Reconstruire l'engineer avec les Elo finaux stockés au training.
        # On normalise les codes (T.B → TBL) pour cohérence avec team_state.
        from ..utils import normalize_team_code
        elo_meta_raw = self.meta.get('team_elos', {})
        elo_meta = {normalize_team_code(k): v for k, v in elo_meta_raw.items()}
        self.engineer = NHLFeatureEngineer(verbose=False)
        self.engineer.team_elos = elo_meta
        self.engineer.features_used = self.meta.get('features_used', [])

        # Construire le snapshot état-équipe
        self.team_state = TeamStateBuilder().fit(df)

        # Forme récente et confrontations directes. Source distincte du
        # dataset de features, qui est en 5-contre-5 : il faut les scores finaux.
        self.history = NHLMatchHistory.from_data_dir(data_dir)

    # ------------------------------------------------------------------
    def _prepare_features(self, home: str, away: str) -> Optional[pd.DataFrame]:
        """Reconstruit la ligne de features pour un matchup futur."""
        raw_row = self.team_state.build_matchup_row(home, away)
        if raw_row is None:
            return None
        # Appliquer les transformations terminales (diffs, elo, interactions)
        transformed = self.engineer.transform(raw_row)
        return transformed

    # ------------------------------------------------------------------
    def predict_all(self, home: str, away: str) -> Dict[str, Any]:
        """
        Prédit tous les markets enregistrés pour un matchup.

        Returns:
            dict {market_name: MarketPrediction-as-dict} + méta.
            Si une équipe est inconnue, retourne {'error': ...}.
        """
        features = self._prepare_features(home, away)
        if features is None:
            known = self.team_state.known_teams
            missing = [t for t in (home, away) if t not in known]
            return {
                'error': f"Équipe(s) inconnue(s) : {missing}",
                'home': home, 'away': away,
                'known_teams': known,
            }

        results: Dict[str, Any] = {
            'home': home,
            'away': away,
            'markets': {},
        }

        for market_name in self.registry.list_markets():
            market = self.registry.get(market_name)
            if not market.enabled or not market.is_fitted:
                continue
            try:
                pred = market.predict(home, away, context={'features_row': features})
                results['markets'][market_name] = {
                    'probabilities': pred.probabilities,
                    'expected_value': pred.expected_value,
                    'confidence': pred.confidence,
                    'metadata': pred.metadata,
                }
            except Exception as e:
                results['markets'][market_name] = {'error': f"{type(e).__name__}: {e}"}

        return results

    # ------------------------------------------------------------------
    def explain(self, home: str, away: str, top_n: int = 3) -> list[dict[str, Any]]:
        """
        Facteurs qui pèsent le plus sur la probabilité moneyline de ce match.

        Contributions SHAP exactes du booster XGBoost — pas une heuristique.
        Retourne une liste vide si le marché n'est pas un modèle XGB.
        """
        features = self._prepare_features(home, away)
        if features is None or not self.registry.has('moneyline'):
            return []
        engine = getattr(self.registry.get('moneyline'), '_engine', None)
        model = getattr(engine, 'xgb_model', None)
        if model is None or not getattr(engine, 'features_used', None):
            return []

        # Le booster a vu des features réindexées puis standardisées : on doit
        # lui présenter exactement la même matrice (cf. predict_proba_home_wins).
        aligned = features.reindex(columns=engine.features_used, fill_value=0)
        try:
            scaled = pd.DataFrame(
                engine.scaler.transform(aligned),
                columns=engine.features_used,
                index=aligned.index,
            )
        except Exception:
            return []

        from ..publication_labels import FEATURE_LABELS
        return top_contributions(
            model, scaled, top_n=top_n, labels=FEATURE_LABELS, display_row=aligned,
        )

    def predict_market(
        self,
        home: str,
        away: str,
        market_name: str,
        line: Optional[float] = None,
    ):
        """Prédit un market spécifique (avec ligne optionnelle pour les O/U)."""
        features = self._prepare_features(home, away)
        if features is None:
            return None
        if not self.registry.has(market_name):
            raise KeyError(f"Market '{market_name}' absent du registre.")
        market = self.registry.get(market_name)
        ctx = {'features_row': features}
        if line is not None and hasattr(market, 'predict_for_line'):
            return market.predict_for_line(home, away, line=line, context=ctx)
        return market.predict(home, away, context=ctx)

    def has_team(self, team_code: str) -> bool:
        return self.team_state.has_team(team_code)

    @property
    def known_teams(self) -> list[str]:
        return self.team_state.known_teams

    # ------------------------------------------------------------------
    def _apply_live_config(self, config_path: str = 'config.yaml') -> None:
        """Réapplique `config.yaml` aux marchés du registre chargé."""
        try:
            from vizer_core import load_config
            cfg = load_config(config_path, validate=False)
        except Exception:
            # Config introuvable (exécution hors du dossier du sport) : on
            # garde les réglages du pickle plutôt que d'échouer au chargement.
            return
        self.registry.reconfigure(cfg.get('markets') or {})
