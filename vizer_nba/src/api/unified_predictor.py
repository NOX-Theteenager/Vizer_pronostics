"""
Interface de prédiction unifiée NBA — réécrit pour étape 3b.

Cette classe garde l'API publique de l'ancienne version
(predict_win, predict_total, predict_under_over, predict_all) pour préserver
predict_json.py et predict_today.py qui en dépendent.

En interne :
- charge via vizer_core.ModelRegistry (nouveau format issu de train.py refactoré)
- utilise les Markets (MoneylineMarket, TotalMarket) pour les prédictions
- construit la ligne de features via _prepare_game_features, enrichie avec
  DEF_RATING et SEASON_AVG_TOTAL pour matcher le pipeline d'entraînement.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, List, Dict

import numpy as np
import pandas as pd

from vizer_core import ModelRegistry

from src.data.loader import NBADataLoader


class UnifiedPredictor:
    """
    Façade de prédiction NBA. API stable (compat avec predict_json/predict_today).
    """

    def __init__(self, model_path: str = 'models/nba_model.pkl'):
        self.registry = ModelRegistry.load(model_path)
        self.loader = NBADataLoader()
        self._games_cache: pd.DataFrame | None = None
        self._teams_cache: pd.DataFrame | None = None

    # =============================================================== Win
    def predict_win(
        self,
        home_team: str,
        away_team: str,
        date: Optional[str] = None,
        home_roster: Optional[List[str]] = None,
        away_roster: Optional[List[str]] = None,
        home_talent_ratio: float = 1.0,
        away_talent_ratio: float = 1.0,
    ) -> Dict[str, Any]:
        """Prédit le vainqueur."""
        if home_roster:
            home_talent_ratio = self._calculate_talent_ratio(home_team, home_roster)
        if away_roster:
            away_talent_ratio = self._calculate_talent_ratio(away_team, away_roster)

        features = self._prepare_game_features(
            home_team, away_team, date, home_talent_ratio, away_talent_ratio
        )

        market = self._get_moneyline_market()
        pred = market.predict(home_team, away_team, context={'features_row': features})

        p_home = pred.probabilities['home']
        p_away = pred.probabilities['away']
        max_proba = max(p_home, p_away)

        if max_proba >= 0.90:
            confidence_level = 'very_high'
        elif max_proba >= 0.75:
            confidence_level = 'high'
        elif max_proba >= 0.60:
            confidence_level = 'medium'
        else:
            confidence_level = 'low'

        is_tossup = 0.45 <= p_home <= 0.55

        return {
            'prediction': 1 if p_home > 0.5 else 0,
            'home_win_proba': float(p_home),
            'away_win_proba': float(p_away),
            'confidence_level': confidence_level,
            'is_tossup': is_tossup,
            'home_team': home_team,
            'away_team': away_team,
            'home_talent_ratio': float(home_talent_ratio),
            'away_talent_ratio': float(away_talent_ratio),
        }

    # ============================================================ Total
    def predict_total(
        self,
        home_team: str,
        away_team: str,
        date: Optional[str] = None,
        home_talent_ratio: float = 1.0,
        away_talent_ratio: float = 1.0,
    ) -> Dict[str, Any]:
        """Prédit le total de points."""
        features = self._prepare_game_features(
            home_team, away_team, date, home_talent_ratio, away_talent_ratio
        )
        market = self.registry.get('total')
        pred = market.predict(home_team, away_team, context={'features_row': features})
        return {
            'prediction': float(pred.expected_value),
            'home_team': home_team,
            'away_team': away_team,
        }

    # ========================================================= Under/Over
    def predict_under_over(
        self,
        home_team: str,
        away_team: str,
        line: float,
        date: Optional[str] = None,
        home_talent_ratio: float = 1.0,
        away_talent_ratio: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Prédit under/over pour une ligne. Utilise la calibration gaussienne
        du TotalMarket (sigma = RMSE test) au lieu d'une sigmoid arbitraire.
        """
        features = self._prepare_game_features(
            home_team, away_team, date, home_talent_ratio, away_talent_ratio
        )
        market = self.registry.get('total')
        pred = market.predict_for_line(
            home_team, away_team, line=line, context={'features_row': features}
        )
        p_over = float(pred.probabilities[f'over_{line}'])
        p_under = float(pred.probabilities[f'under_{line}'])
        predicted_total = float(pred.expected_value)
        return {
            'prediction': predicted_total,
            'line': line,
            'over_proba': p_over,
            'under_proba': p_under,
            'recommendation': 'over' if predicted_total > line else 'under',
            'home_team': home_team,
            'away_team': away_team,
        }

    # ============================================================= All
    def predict_all(
        self,
        home_team: str,
        away_team: str,
        date: Optional[str] = None,
        home_roster: Optional[List[str]] = None,
        away_roster: Optional[List[str]] = None,
        home_talent_ratio: float = 1.0,
        away_talent_ratio: float = 1.0,
    ) -> Dict[str, Any]:
        """Toutes les prédictions en une seule construction de features."""
        if home_roster:
            home_talent_ratio = self._calculate_talent_ratio(home_team, home_roster)
        if away_roster:
            away_talent_ratio = self._calculate_talent_ratio(away_team, away_roster)

        features = self._prepare_game_features(
            home_team, away_team, date, home_talent_ratio, away_talent_ratio
        )

        ml_market = self._get_moneyline_market()
        ml_pred = ml_market.predict(home_team, away_team, context={'features_row': features})
        p_home = float(ml_pred.probabilities['home'])
        p_away = float(ml_pred.probabilities['away'])

        total_market = self.registry.get('total')
        t_pred = total_market.predict(home_team, away_team, context={'features_row': features})

        result = {
            'home_team': home_team,
            'away_team': away_team,
            'win': {
                'prediction': 1 if p_home > 0.5 else 0,
                'home_win_proba': p_home,
                'away_win_proba': p_away,
            },
            'total': {
                'prediction': float(t_pred.expected_value),
            },
            'talent': {
                'home_ratio': float(home_talent_ratio),
                'away_ratio': float(away_talent_ratio),
            },
        }

        # Étape 6 : team totals si markets disponibles dans le registre.
        # Optionnel — si home_team_total / away_team_total ne sont pas entraînés,
        # on saute silencieusement (rétrocompat avec anciens modèles).
        if self.registry.has('home_team_total'):
            htt = self.registry.get('home_team_total')
            htt_pred = htt.predict(home_team, away_team, context={'features_row': features})
            result['home_team_total'] = {
                'prediction': float(htt_pred.expected_value),
                'line_default': float(htt_pred.metadata.get('line_used')),
                'over_default_proba': float(
                    htt_pred.probabilities[f"over_{htt_pred.metadata['line_used']}"]
                ),
            }
        if self.registry.has('away_team_total'):
            att = self.registry.get('away_team_total')
            att_pred = att.predict(home_team, away_team, context={'features_row': features})
            result['away_team_total'] = {
                'prediction': float(att_pred.expected_value),
                'line_default': float(att_pred.metadata.get('line_used')),
                'over_default_proba': float(
                    att_pred.probabilities[f"over_{att_pred.metadata['line_used']}"]
                ),
            }

        return result

    # =================================================== Team Total (étape 6)
    def predict_team_total(
        self,
        home_team: str,
        away_team: str,
        side: str = 'home',
        date: Optional[str] = None,
        home_talent_ratio: float = 1.0,
        away_talent_ratio: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Prédit les points d'une équipe seule (home ou away).

        Args:
            side : 'home' ou 'away'.

        Returns:
            {'prediction': float, 'side': 'home'|'away', 'team': abbr, ...}
        """
        if side not in ('home', 'away'):
            raise ValueError(f"side doit être 'home' ou 'away', reçu {side!r}")
        market_name = f"{side}_team_total"
        if not self.registry.has(market_name):
            raise KeyError(
                f"Marché '{market_name}' non disponible. "
                f"Active-le dans config.yaml et relance train.py."
            )

        features = self._prepare_game_features(
            home_team, away_team, date, home_talent_ratio, away_talent_ratio
        )
        market = self.registry.get(market_name)
        pred = market.predict(home_team, away_team, context={'features_row': features})

        return {
            'prediction': float(pred.expected_value),
            'side': side,
            'team': home_team if side == 'home' else away_team,
            'opponent': away_team if side == 'home' else home_team,
            'home_team': home_team,
            'away_team': away_team,
        }

    def predict_team_under_over(
        self,
        home_team: str,
        away_team: str,
        side: str,
        line: float,
        date: Optional[str] = None,
        home_talent_ratio: float = 1.0,
        away_talent_ratio: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Prédit Over/Under sur une ligne précise pour le total d'une équipe.
        Utilise la calibration gaussienne (sigma = RMSE test du market).
        """
        if side not in ('home', 'away'):
            raise ValueError(f"side doit être 'home' ou 'away', reçu {side!r}")
        market_name = f"{side}_team_total"
        if not self.registry.has(market_name):
            raise KeyError(
                f"Marché '{market_name}' non disponible. "
                f"Active-le dans config.yaml et relance train.py."
            )

        features = self._prepare_game_features(
            home_team, away_team, date, home_talent_ratio, away_talent_ratio
        )
        market = self.registry.get(market_name)
        pred = market.predict_for_line(
            home_team, away_team, line=line, context={'features_row': features}
        )
        predicted_pts = float(pred.expected_value)
        p_over = float(pred.probabilities[f'over_{line}'])
        p_under = float(pred.probabilities[f'under_{line}'])

        return {
            'prediction': predicted_pts,
            'side': side,
            'team': home_team if side == 'home' else away_team,
            'line': line,
            'over_proba': p_over,
            'under_proba': p_under,
            'recommendation': 'over' if predicted_pts > line else 'under',
            'home_team': home_team,
            'away_team': away_team,
        }

    # ==================================================== Feature builder
    def _prepare_game_features(
        self,
        home_team: str,
        away_team: str,
        date: Optional[str] = None,
        home_talent_ratio: float = 1.0,
        away_talent_ratio: float = 1.0,
    ) -> pd.DataFrame:
        """
        Construit une ligne de features pour le match.

        Reproduit la logique de engineer.create_features mais pour UN match
        à prédire (qui n'est pas dans le dataset). Inclut DEF_RATING et
        SEASON_AVG_TOTAL pour matcher le pipeline d'entraînement actuel.
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        # Cache games + teams pour ne pas recharger à chaque appel
        if self._games_cache is None:
            self._games_cache = self.loader.load_games()
        if self._teams_cache is None:
            self._teams_cache = self.loader.load_teams()

        games = self._games_cache
        teams = self._teams_cache

        home_id = self._find_team_id(home_team, teams)
        away_id = self._find_team_id(away_team, teams)

        # Historique strictement avant la date
        hist = games[games['GAME_DATE'] < date].copy()

        # Repos
        home_rest = self._rest_days(home_id, hist, date)
        away_rest = self._rest_days(away_id, hist, date)

        # PTS_AGAINST : nécessaire pour DEF_RATING. Calcul vectorisé sur tout l'historique.
        hist['PTS_AGAINST'] = hist.groupby('GAME_ID')['PTS'].transform('sum') - hist['PTS']

        # Rolling stats par équipe (avec DEF_RATING)
        home_stats = self._rolling_stats(home_id, hist)
        away_stats = self._rolling_stats(away_id, hist)

        # SEASON_AVG_TOTAL : moyenne des totaux dans la saison courante avant date
        season_avg_total = self._season_avg_total(hist, pd.to_datetime(date))

        # Assembler la ligne
        row: Dict[str, Any] = {
            'HOME_TEAM_ID': home_id,
            'AWAY_TEAM_ID': away_id,
            'HOME_REST_DAYS': home_rest,
            'AWAY_REST_DAYS': away_rest,
            'HOME_B2B': 1 if home_rest <= 1 else 0,
            'AWAY_B2B': 1 if away_rest <= 1 else 0,
            'HOME_TALENT_RATIO': home_talent_ratio,
            'AWAY_TALENT_RATIO': away_talent_ratio,
            'SEASON_AVG_TOTAL': season_avg_total,
        }
        for k, v in home_stats.items():
            row[f'HOME_{k}'] = v
        for k, v in away_stats.items():
            row[f'AWAY_{k}'] = v
        # TOTAL_PTS sera filtré par exclude_cols, mais on le met pour éviter KeyError
        row['TOTAL_PTS'] = 0

        df = pd.DataFrame([row])

        # S'assurer que toutes les features attendues par chaque market sont là
        for market_name in self.registry.list_markets():
            market = self.registry.get(market_name)
            if hasattr(market, 'predictor') and hasattr(market.predictor, 'feature_columns'):
                expected = market.predictor.feature_columns
                for col in expected:
                    if col not in df.columns:
                        df[col] = 0

        return df

    # ─────────────────── Helpers feature engineering ───────────────────
    @staticmethod
    def _find_team_id(name_or_abbr: str, teams: pd.DataFrame) -> int:
        match = teams[
            (teams['abbreviation'] == name_or_abbr.upper())
            | (teams['full_name'].str.contains(name_or_abbr, case=False, na=False))
        ]
        if len(match) == 0:
            raise ValueError(f"Équipe '{name_or_abbr}' non trouvée")
        return int(match.iloc[0]['id'])

    @staticmethod
    def _rest_days(team_id: int, hist: pd.DataFrame, date: str) -> int:
        tg = hist[hist['TEAM_ID'] == team_id].sort_values('GAME_DATE')
        if len(tg) == 0:
            return 5
        last = pd.to_datetime(tg.iloc[-1]['GAME_DATE'])
        return min(10, int((pd.to_datetime(date) - last).days))

    @staticmethod
    def _rolling_stats(team_id: int, hist: pd.DataFrame, windows=(5, 10, 20)) -> Dict[str, float]:
        """Rolling stats pour une équipe, calculées en interne pour éviter les NaN."""
        stat_cols = [
            'PTS', 'FG_PCT', 'FG3_PCT', 'FT_PCT', 'REB', 'AST', 'STL', 'BLK', 'TOV',
            'EFG_PCT', 'TOV_PCT', 'FT_RATE', 'POSS', 'OFF_RATING', 'DEF_RATING',
        ]
        tg = hist[hist['TEAM_ID'] == team_id].sort_values('GAME_DATE').copy()
        if len(tg) == 0:
            return {f'{c}_AVG_{w}G': 0.0 for w in windows for c in stat_cols}

        # Métriques avancées (mêmes formules que engineer.py)
        tg['EFG_PCT'] = (tg['FGM'] + 0.5 * tg['FG3M']) / tg['FGA']
        tg['TOV_PCT'] = tg['TOV'] / (tg['FGA'] + 0.44 * tg['FTA'] + tg['TOV'])
        tg['FT_RATE'] = tg['FTA'] / tg['FGA']
        tg['POSS'] = tg['FGA'] + 0.44 * tg['FTA'] - tg['OREB'] + tg['TOV']
        tg['OFF_RATING'] = (tg['PTS'] / tg['POSS']) * 100
        # PTS_AGAINST déjà calculé dans hist en amont
        tg['DEF_RATING'] = (tg['PTS_AGAINST'] / tg['POSS']) * 100

        res: Dict[str, float] = {}
        for w in windows:
            recent = tg.tail(w)
            for col in stat_cols:
                val = recent[col].mean() if len(recent) > 0 else 0.0
                res[f'{col}_AVG_{w}G'] = 0.0 if pd.isna(val) else float(val)
        return res

    @staticmethod
    def _season_avg_total(hist: pd.DataFrame, current_date: pd.Timestamp) -> float:
        """Moyenne des totaux dans la saison courante avant la date."""
        # Saison NBA : Oct N → Juin N+1. Approximation par SEASON_ID stocké dans hist.
        # On déduit la saison via la date.
        if current_date.month >= 10:
            season_year = current_date.year
        else:
            season_year = current_date.year - 1
        season_id = 22000 + (season_year - 2000)

        season_hist = hist[hist['SEASON_ID'] == season_id]
        if len(season_hist) > 0:
            totals = season_hist.groupby('GAME_ID')['PTS'].sum()
            return float(totals.mean())

        # Fallback : saison précédente
        prev_hist = hist[hist['SEASON_ID'] == season_id - 1]
        if len(prev_hist) > 0:
            return float(prev_hist.groupby('GAME_ID')['PTS'].sum().mean())

        # Ultime fallback
        return 220.0

    # ─────────────────────── Talent ratio ───────────────────────
    def _calculate_talent_ratio(self, team_name_or_abbr: str, roster: List[str]) -> float:
        """
        Talent ratio basé sur les metadata du registre (player_values, team_baselines).
        Retourne 1.0 si les metadata sont absentes (registre minimaliste).
        """
        player_values = self.registry.get_metadata('player_values', {})
        team_baselines = self.registry.get_metadata('team_baselines', {})
        name_to_id = self.registry.get_metadata('name_to_player_id', {})

        if not player_values or not team_baselines:
            return 1.0  # metadata absentes : pas de signal disponible

        if self._teams_cache is None:
            self._teams_cache = self.loader.load_teams()
        teams = self._teams_cache

        match = teams[
            (teams['abbreviation'] == team_name_or_abbr.upper())
            | (teams['full_name'].str.contains(team_name_or_abbr, case=False, na=False))
        ]
        if len(match) == 0:
            return 1.0
        team_id = int(match.iloc[0]['id'])
        baseline = team_baselines.get(team_id, 200.0)
        if baseline == 0:
            return 1.0

        current_talent = 0.0
        for name in roster:
            pid = name_to_id.get(name)
            if not pid:
                # Fuzzy match insensible à la casse
                name_lower = name.lower()
                for known_name, known_id in name_to_id.items():
                    if name_lower in known_name.lower():
                        pid = known_id
                        break
            if pid and pid in player_values:
                val = player_values[pid]
                if not (isinstance(val, float) and np.isnan(val)):
                    current_talent += val

        if current_talent == 0:
            return 1.0
        return float(np.clip(current_talent / baseline, 0.5, 1.5))

    # ─────────────────────── Helpers ───────────────────────
    def _get_moneyline_market(self):
        """Récupère le marché de victoire, supporte les deux noms (moneyline / win)."""
        if self.registry.has('moneyline'):
            return self.registry.get('moneyline')
        if self.registry.has('win'):
            return self.registry.get('win')
        raise KeyError(
            f"Aucun marché de victoire enregistré. Marchés disponibles : "
            f"{self.registry.list_markets()}"
        )

    # ─────────────────────── Info ───────────────────────
    def get_model_info(self) -> Dict[str, Any]:
        return {
            'sport': self.registry.sport,
            'version': self.registry.version,
            'created_at': self.registry.created_at,
            'markets': self.registry.list_markets(),
        }

    def print_model_summary(self) -> None:
        self.registry.print_summary()
