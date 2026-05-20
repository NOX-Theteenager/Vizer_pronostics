"""
NHL utilities — Temperature Scaling, Elo, features config.

Réutilisable par tous les markets NHL. Reprend les composants éprouvés du
notebook V5.6 (vizer_utils.py original) en version modulaire.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


# =============================================================================
# Calibrateur Temperature Scaling — 1 paramètre, préserve l'AUC
# =============================================================================

class TemperatureScalingCalibrator:
    """
    Temperature Scaling : 1 seul paramètre T.
        p_calibré = sigmoid(logit(p_brut) / T)

    Avantages vs Platt :
    - 1 paramètre seulement (vs 2 pour Platt)
    - Préserve l'ordre exact des prédictions (AUC inchangée)
    - Optimal sur petits ensembles (impossible d'overfitter)

    Interface compatible scikit-learn : .fit(raw, y) / .predict(raw).
    Sérialisable proprement avec joblib.
    """

    def __init__(self):
        self.T: float = 1.0

    def fit(self, raw_probs, y):
        from scipy.optimize import minimize_scalar
        raw = np.clip(np.array(raw_probs), 1e-7, 1 - 1e-7)
        y = np.array(y)
        logits = np.log(raw / (1 - raw))

        def nll(T):
            p = 1 / (1 + np.exp(-logits / T))
            p = np.clip(p, 1e-7, 1 - 1e-7)
            return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))

        res = minimize_scalar(nll, bounds=(0.1, 10.0), method='bounded')
        self.T = float(res.x)
        return self

    def predict(self, raw_probs) -> np.ndarray:
        raw = np.clip(np.array(raw_probs), 1e-7, 1 - 1e-7)
        logits = np.log(raw / (1 - raw))
        return 1 / (1 + np.exp(-logits / self.T))


# =============================================================================
# Normalisation des codes équipes
# =============================================================================

TEAM_REMAP: Dict[str, str] = {
    'T.B': 'TBL', 'N.J': 'NJD', 'S.J': 'SJS', 'L.A': 'LAK',
    'PHX': 'ARI', 'UTA': 'ARI', 'ATL': 'WPG',
}

TEAM_TO_CODE: Dict[str, str] = {
    'Anaheim Ducks': 'ANA', 'Utah Hockey Club': 'ARI',
    'Boston Bruins': 'BOS', 'Buffalo Sabres': 'BUF',
    'Calgary Flames': 'CGY', 'Carolina Hurricanes': 'CAR',
    'Chicago Blackhawks': 'CHI', 'Colorado Avalanche': 'COL',
    'Columbus Blue Jackets': 'CBJ', 'Dallas Stars': 'DAL',
    'Detroit Red Wings': 'DET', 'Edmonton Oilers': 'EDM',
    'Florida Panthers': 'FLA', 'Los Angeles Kings': 'LAK',
    'Minnesota Wild': 'MIN',
    'Montreal Canadiens': 'MTL', 'Montréal Canadiens': 'MTL',
    'Nashville Predators': 'NSH', 'New Jersey Devils': 'NJD',
    'New York Islanders': 'NYI', 'New York Rangers': 'NYR',
    'Ottawa Senators': 'OTT', 'Philadelphia Flyers': 'PHI',
    'Pittsburgh Penguins': 'PIT', 'San Jose Sharks': 'SJS',
    'Seattle Kraken': 'SEA',
    'St. Louis Blues': 'STL', 'St Louis Blues': 'STL',
    'Tampa Bay Lightning': 'TBL', 'Toronto Maple Leafs': 'TOR',
    'Vancouver Canucks': 'VAN', 'Vegas Golden Knights': 'VGK',
    'Washington Capitals': 'WSH', 'Winnipeg Jets': 'WPG',
}


def normalize_team_code(name: str) -> str:
    """Convertit un nom complet en code 3 lettres, ou applique le remap."""
    if name in TEAM_TO_CODE:
        return TEAM_TO_CODE[name]
    return TEAM_REMAP.get(name, name)


# =============================================================================
# Elo dynamique
# =============================================================================

def compute_elo_column(
    df: pd.DataFrame,
    k: float = 20.0,
    base: float = 1500.0,
    home_bonus: float = 35.0,
    date_col: str = 'gameDate_home',
    home_col: str = 'team_home',
    away_col: str = 'team_away',
    target_col: str = 'home_team_won',
    id_col: str = 'gameId_home',
) -> pd.DataFrame:
    """
    Calcule les ratings Elo pré-match pour chaque ligne, en chronologique
    strict (pas de leakage : on ne voit jamais l'avenir).

    home_bonus = ~35 pts pour la NHL.

    Returns:
        DataFrame[id_col, 'elo_home', 'elo_away'] à merger sur le dataset.
    """
    df_sorted = df.sort_values(date_col).copy()
    elo: Dict[str, float] = {}
    rows = []
    for _, r in df_sorted.iterrows():
        h, a = r[home_col], r[away_col]
        rh = elo.get(h, float(base))
        ra = elo.get(a, float(base))
        rows.append({id_col: r[id_col], 'elo_home': rh, 'elo_away': ra})
        exp_h = 1.0 / (1 + 10 ** ((ra - (rh + home_bonus)) / 400))
        result_h = float(r[target_col])
        elo[h] = rh + k * (result_h - exp_h)
        elo[a] = ra + k * ((1 - result_h) - (1 - exp_h))
    return pd.DataFrame(rows)


def compute_team_elos(
    df: pd.DataFrame,
    k: float = 20.0,
    base: float = 1500.0,
    home_bonus: float = 35.0,
    date_col: str = 'gameDate_home',
    home_col: str = 'team_home',
    away_col: str = 'team_away',
    target_col: str = 'home_team_won',
) -> Dict[str, float]:
    """
    Rejoue tout l'historique et retourne l'Elo final de chaque équipe.
    Utilisé à l'inférence pour avoir les ratings courants sans recalcul inline.
    """
    df_sorted = df[[date_col, home_col, away_col, target_col]].dropna().sort_values(date_col)
    elo: Dict[str, float] = {}
    for _, r in df_sorted.iterrows():
        h, a = r[home_col], r[away_col]
        rh = elo.get(h, float(base))
        ra = elo.get(a, float(base))
        exp_h = 1.0 / (1 + 10 ** ((ra - (rh + home_bonus)) / 400))
        result_h = float(r[target_col])
        elo[h] = rh + k * (result_h - exp_h)
        elo[a] = ra + k * ((1 - result_h) - (1 - exp_h))
    return elo


# =============================================================================
# Définition canonique des features V5.6
# =============================================================================
# Reprend exactement la configuration du notebook 03 (CANDIDATE_FEATURES).

# Features récupérées depuis les colonnes _home/_away post-agrégation
RECOVERED_DIFFS: List[Tuple[str, str, str]] = [
    ('avg_HDcf_10_home', 'avg_HDcf_10_away', 'diff_HDcf'),
    ('avg_panic_score_10_home', 'avg_panic_score_10_away', 'diff_panic_score'),
]

# Differentiels multi-fenêtres
MULTI_WINDOW_DIFFS: List[Tuple[str, str, str]] = [
    ('avg_xGF_pct_5_home', 'avg_xGF_pct_5_away', 'diff_xGF_5'),
    ('avg_xGF_pct_20_home', 'avg_xGF_pct_20_away', 'diff_xGF_20'),
    ('avg_xGF_pct_50_home', 'avg_xGF_pct_50_away', 'diff_xGF_season'),
    ('avg_pp_5_home', 'avg_pp_5_away', 'diff_pp_5'),
    ('avg_pp_20_home', 'avg_pp_20_away', 'diff_pp_20'),
    ('avg_pdo_10_home', 'avg_pdo_10_away', 'diff_pdo'),
    ('momentum_home', 'momentum_away', 'diff_momentum'),
    ('days_rest_home', 'days_rest_away', 'diff_days_rest'),
]

# Features de base attendues directement dans le df_final agrégé
BASE_FEATURES: List[str] = [
    'diff_xGF_pct',
    'diff_top_line_xGF',
    'diff_pp',
    'diff_forme',
    'diff_b2b',
]

# Tous les candidats à passer au modèle
CANDIDATE_FEATURES: List[str] = BASE_FEATURES + [
    'diff_HDcf', 'diff_panic_score',
    'diff_elo',
    'diff_xGF_5', 'diff_xGF_20', 'diff_xGF_season',
    'diff_pp_5', 'diff_pp_20',
    'diff_days_rest',
    'interaction_goalie_xgf', 'interaction_forme_xgf',
    # V5.5 — features avancées (optionnelles selon dispo data)
    'diff_csa_pct',
    'h2h_home_dominance',
    'h2h_avg_total_goals',
    'diff_goalie_starter_gsae',
]


def safe_diff(df: pd.DataFrame, col_home: str, col_away: str) -> pd.Series | None:
    """Différentiel home - away uniquement si les deux colonnes existent."""
    if col_home in df.columns and col_away in df.columns:
        return df[col_home] - df[col_away]
    return None
