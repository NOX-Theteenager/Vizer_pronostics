"""
vizer_utils.py — Module partagé VIZER NHL
==========================================
Contient toutes les classes et fonctions utilisées par plusieurs notebooks.
Importer ce module dans chaque notebook garantit que joblib peut retrouver
PlattCalibrator lors du chargement du bundle sauvegardé.

Usage dans chaque notebook :
    from vizer_utils import (
        PlattCalibrator, compute_elo_column, compute_elo_for_inference,
        safe_diff, get_latest_team_stats, compute_real_b2b,
        calculate_over_probability, TEAM_REMAP, TEAM_TO_CODE,
        RECOVERED_FEATURES, MULTI_WINDOW_FEATURES, BASE_FEATURES
    )
"""

import numpy as np
import pandas as pd
import logging
import os
import requests
from datetime import datetime
from sklearn.linear_model import LogisticRegression

# Silence LGB au niveau module
os.environ['LIGHTGBM_VERBOSITY'] = '-1'
logging.getLogger('lightgbm').setLevel(logging.ERROR)


# ==============================================================================
# CALIBRATEUR DE PLATT
# ==============================================================================
class PlattCalibrator:
    """
    Calibration de Platt : régression logistique sur les probabilités brutes.

    Avantages vs IsotonicRegression :
    - 2 paramètres seulement (slope + biais) → impossible d'overfitter
    - Robuste quelle que soit la taille du val set (300 ou 5000 matchs)
    - Interface identique à IsotonicRegression : .fit(raw, y) / .predict(raw)
    - Sérialisable proprement avec joblib

    Résultats observés : AUC 0.5972, Brier 0.2446 (meilleur historique)
    """
    def __init__(self, C: float = 1.0):
        self.lr = LogisticRegression(C=C, random_state=42, max_iter=1000)

    def fit(self, raw_probs, y):
        self.lr.fit(np.array(raw_probs).reshape(-1, 1), np.array(y))
        return self

    def predict(self, raw_probs):
        """Retourne un array de probabilités calibrées."""
        return self.lr.predict_proba(np.array(raw_probs).reshape(-1, 1))[:, 1]


# ==============================================================================
# NORMALISATION DES CODES D'ÉQUIPE
# ==============================================================================
TEAM_REMAP = {
    'T.B': 'TBL',   # Tampa Bay Lightning (ancien code Moneypuck)
    'N.J': 'NJD',   # New Jersey Devils
    'S.J': 'SJS',   # San Jose Sharks
    'L.A': 'LAK',   # Los Angeles Kings
    'PHX': 'ARI',   # Phoenix Coyotes → Arizona
    'UTA': 'ARI',   # Utah Hockey Club → même franchise qu'Arizona
    'ATL': 'WPG',   # Atlanta Thrashers → Winnipeg Jets (racheté en 2011)
}

# Mapping nom complet (API The-Odds) → code Moneypuck
# Inclut les variantes accentuées et orthographiques que l'API peut envoyer
TEAM_TO_CODE = {
    'Anaheim Ducks':          'ANA', 'Utah Hockey Club':        'ARI',
    'Boston Bruins':          'BOS', 'Buffalo Sabres':           'BUF',
    'Calgary Flames':         'CGY', 'Carolina Hurricanes':      'CAR',
    'Chicago Blackhawks':     'CHI', 'Colorado Avalanche':       'COL',
    'Columbus Blue Jackets':  'CBJ', 'Dallas Stars':             'DAL',
    'Detroit Red Wings':      'DET', 'Edmonton Oilers':          'EDM',
    'Florida Panthers':       'FLA', 'Los Angeles Kings':        'LAK',
    'Minnesota Wild':         'MIN',
    'Montreal Canadiens':     'MTL',   # sans accent (ancienne API)
    'Montréal Canadiens':     'MTL',   # avec accent (API actuelle)
    'Nashville Predators':    'NSH', 'New Jersey Devils':        'NJD',
    'New York Islanders':     'NYI', 'New York Rangers':         'NYR',
    'Ottawa Senators':        'OTT', 'Philadelphia Flyers':      'PHI',
    'Pittsburgh Penguins':    'PIT', 'San Jose Sharks':          'SJS',
    'Seattle Kraken':         'SEA',
    'St. Louis Blues':        'STL',   # avec point (format standard)
    'St Louis Blues':         'STL',   # sans point (variante API)
    'Tampa Bay Lightning':    'TBL', 'Toronto Maple Leafs':      'TOR',
    'Vancouver Canucks':      'VAN', 'Vegas Golden Knights':     'VGK',
    'Washington Capitals':    'WSH', 'Winnipeg Jets':            'WPG',
}


def get_team_code(team_name_raw):
    """
    Récupère le code Moneypuck depuis le nom complet de l'API The-Odds.

    Gère les accents, la casse, et les variantes d'orthographe.
    L'API peut envoyer 'Montréal Canadiens' ou 'Montreal Canadiens' selon la région.
    """
    import unicodedata

    # 1. Lookup direct
    code = TEAM_TO_CODE.get(team_name_raw)
    if code:
        return code

    # 2. Remplacements courants de l'API avant lookup
    cleaned = (team_name_raw
               .replace('St.', 'St')
               .replace("St ", "St. ")  # reconstruire si supprimé
               .strip())
    code = TEAM_TO_CODE.get(cleaned)
    if code:
        return code

    # 3. Normalisation Unicode : supprimer les diacritiques (é→e, ô→o, etc.)
    normalized = ''.join(
        c for c in unicodedata.normalize('NFD', team_name_raw)
        if unicodedata.category(c) != 'Mn'
    )
    code = TEAM_TO_CODE.get(normalized)
    if code:
        return code

    # 4. Comparaison insensible à la casse en dernier recours
    lower = team_name_raw.lower()
    for name, c in TEAM_TO_CODE.items():
        if name.lower() == lower:
            return c

    return None  # équipe non trouvée


# ==============================================================================
# CONFIGURATION DES FEATURES — V5.4 (post-analyse SHAP/calibration)
# ==============================================================================
# Changements vs V5.3 :
# - Suppression diff_corsi (corrélé à 0.65 avec diff_xGF_pct → redondant)
# - Suppression diff_stress (SHAP 0.0017 → bruit pur)
# - Suppression diff_pk (SHAP 0.0028 → bruit)
# - Ajout diff_xGF_season (fenêtre 50 matchs ≈ saison entière)
# - Remplacement diff_b2b binaire par diff_days_rest continu (0/1/2/3+)
RECOVERED_FEATURES = [
    ('avg_HDcf_10_home',        'avg_HDcf_10_away',        'diff_HDcf'),
    ('avg_panic_score_10_home', 'avg_panic_score_10_away', 'diff_panic_score'),
]

MULTI_WINDOW_FEATURES = [
    ('avg_xGF_pct_5_home',     'avg_xGF_pct_5_away',     'diff_xGF_5'),
    ('avg_xGF_pct_20_home',    'avg_xGF_pct_20_away',    'diff_xGF_20'),
    ('avg_xGF_pct_50_home',    'avg_xGF_pct_50_away',    'diff_xGF_season'),  # NOUVEAU
    ('avg_pp_5_home',           'avg_pp_5_away',           'diff_pp_5'),
    ('avg_pp_20_home',          'avg_pp_20_away',          'diff_pp_20'),
    ('avg_pdo_10_home',         'avg_pdo_10_away',         'diff_pdo'),
    ('momentum_home',           'momentum_away',            'diff_momentum'),
    ('days_rest_home',          'days_rest_away',           'diff_days_rest'),  # NOUVEAU
]

BASE_FEATURES = [
    'diff_xGF_pct',
    # 'diff_corsi'  → SUPPRIMÉ (corr 0.65 avec diff_xGF_pct, redondant)
    'diff_top_line_xGF',
    'diff_pp',
    # 'diff_pk'     → SUPPRIMÉ (SHAP 0.0028 = bruit)
    'diff_forme',
    'diff_b2b',
]

CANDIDATE_FEATURES = BASE_FEATURES + [
    'diff_HDcf', 'diff_panic_score',
    'diff_elo',
    'diff_xGF_5', 'diff_xGF_20', 'diff_xGF_season',  # multi-fenêtres complètes
    'diff_pp_5', 'diff_pp_20',
    'diff_days_rest',
    'interaction_goalie_xgf', 'interaction_forme_xgf',
    # === V5.5 — Nouvelles features (à valider après training) ===
    'diff_csa_pct',           # Score-Adjusted Corsi (remplace l'ancien diff_corsi)
    'h2h_home_dominance',     # Avantage historique du domicile sur cet adversaire
    'h2h_avg_total_goals',    # Tendance de scoring dans ces face-à-face
    'diff_goalie_starter_gsae',  # Différentiel de qualité du gardien partant confirmé
]


# ==============================================================================
# CALIBRATEUR TEMPERATURE SCALING (alternative à PlattCalibrator)
# ==============================================================================
class TemperatureScalingCalibrator:
    """
    Temperature Scaling : 1 seul paramètre T.
    p_calibré = sigmoid(logit(p_brut) / T)

    Avantages vs Platt :
    - 1 paramètre seulement (vs 2 pour Platt)
    - Préserve l'ordre exact des prédictions (AUC inchangée)
    - Optimal sur petits ensembles (impossible d'overfitter)

    Quand utiliser : si tu vois la calibration Platt déformer la courbe ROC,
    Temperature Scaling est strictement plus sûr.
    """
    def __init__(self):
        self.T = 1.0

    def fit(self, raw_probs, y):
        from scipy.optimize import minimize_scalar
        raw = np.clip(np.array(raw_probs), 1e-7, 1 - 1e-7)
        y   = np.array(y)
        logits = np.log(raw / (1 - raw))

        def nll(T):
            p = 1 / (1 + np.exp(-logits / T))
            p = np.clip(p, 1e-7, 1 - 1e-7)
            return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))

        res = minimize_scalar(nll, bounds=(0.1, 10.0), method='bounded')
        self.T = float(res.x)
        return self

    def predict(self, raw_probs):
        raw = np.clip(np.array(raw_probs), 1e-7, 1 - 1e-7)
        logits = np.log(raw / (1 - raw))
        return 1 / (1 + np.exp(-logits / self.T))


# ==============================================================================
# FONCTIONS UTILITAIRES
# ==============================================================================

def normalize_teams(df):
    """Normalise les codes équipe selon TEAM_REMAP."""
    for col in ['team', 'playerTeam', 'homeTeam', 'awayTeam']:
        if col in df.columns:
            df[col] = df[col].replace(TEAM_REMAP)
    return df


def safe_diff(df, col_home, col_away):
    """Différentiel home - away uniquement si les deux colonnes existent."""
    if col_home in df.columns and col_away in df.columns:
        return df[col_home] - df[col_away]
    return None


def compute_elo_column(df, k=20, base=1500, home_bonus=35.0):
    """
    Calcule les ratings Elo pré-match pour chaque ligne.
    Respecte l'ordre chronologique → zéro leakage.
    home_bonus = avantage domicile structurel en NHL (~35 pts Elo).
    """
    df = df.sort_values('gameDate_home').copy()
    elo, rows = {}, []

    for _, r in df.iterrows():
        h, a = r['team_home'], r['team_away']
        rh = elo.get(h, float(base))
        ra = elo.get(a, float(base))
        rows.append({'gameId_home': r['gameId_home'], 'elo_home': rh, 'elo_away': ra})

        exp_h    = 1.0 / (1 + 10 ** ((ra - (rh + home_bonus)) / 400))
        result_h = float(r['home_team_won'])
        elo[h]   = rh + k * (result_h - exp_h)
        elo[a]   = ra + k * ((1 - result_h) - (1 - exp_h))

    return pd.DataFrame(rows)


def compute_elo_for_inference(db, k=20, base=1500, home_bonus=35.0):
    """
    Recrée l'état Elo courant de chaque équipe en rejouant l'historique complet.
    Nécessaire car l'Elo est calculé inline à l'entraînement et non exporté dans le CSV.
    """
    if 'gameDate_home' not in db.columns or 'home_team_won' not in db.columns:
        return {}

    db_sorted = (db[['gameDate_home', 'team_home', 'team_away', 'home_team_won']]
                 .dropna()
                 .sort_values('gameDate_home'))
    elo = {}

    for _, r in db_sorted.iterrows():
        h, a = r['team_home'], r['team_away']
        rh = elo.get(h, float(base))
        ra = elo.get(a, float(base))
        exp_h    = 1.0 / (1 + 10 ** ((ra - (rh + home_bonus)) / 400))
        result_h = float(r['home_team_won'])
        elo[h]   = rh + k * (result_h - exp_h)
        elo[a]   = ra + k * ((1 - result_h) - (1 - exp_h))

    return elo


def get_latest_team_stats(db, team_code):
    """Récupère les stats du dernier match connu d'une équipe."""
    df_team = db[(db['team_home'] == team_code) | (db['team_away'] == team_code)].copy()
    if df_team.empty:
        return None

    last_game = df_team.iloc[-1]
    suffix    = '_home' if last_game['team_home'] == team_code else '_away'

    def get(col, default=0.0):
        full_col = f"{col}{suffix}"
        val = last_game.get(full_col, default)
        return float(val) if val is not None else default

    return {
        'xGF_pct':      get('avg_xGF_pct_10'),
        'goalie_impact': get('impact_goalie'),
        'corsi':        get('avg_corsi_10'),
        'top_line_xGF': get('avg_top_line_xGF_10'),
        'pp':           get('avg_pp_10'),
        'pk':           get('avg_pk_10'),
        'forme':        get('Forme_5_matchs'),
        'HDcf':         get('avg_HDcf_10'),
        'panic_score':  get('avg_panic_score_10'),
        'stress':       get('stress_score'),
        'pdo':          get('avg_pdo_10'),
        'momentum':     get('momentum'),
        'xGF_5':        get('avg_xGF_pct_5'),
        'xGF_20':       get('avg_xGF_pct_20'),
        'xGF_season':   get('avg_xGF_pct_50'),    # NOUVEAU V5.4
        'pp_5':         get('avg_pp_5'),
        'pp_20':        get('avg_pp_20'),
        'days_rest':    get('days_rest'),         # NOUVEAU V5.4 (continu)
        'goals_per_game_recent': get('avg_goals_per_game_10'),  # NOUVEAU pour Poisson
        'elo':          0.0,  # Injecté séparément via compute_elo_for_inference()
        'last_game_date': last_game.get(
            'gameDate_home' if suffix == '_home' else 'gameDate_away', None)
    }


def compute_real_b2b(team_stats, game_date_str):
    """Calcul réel du back-to-back depuis la date du dernier match."""
    if team_stats.get('last_game_date') is None:
        return 0
    try:
        last_date  = pd.to_datetime(team_stats['last_game_date'])
        game_date  = pd.to_datetime(game_date_str)
        days_since = (game_date - last_date).days
        return 1 if days_since == 1 else 0
    except Exception:
        return 0


def calculate_over_probability(lambda_h, lambda_a, threshold=5.5):
    """Probabilité Poisson que le total de buts dépasse le seuil."""
    prob_over = 0
    for i in range(15):
        for j in range(15):
            if (i + j) > threshold:
                prob_over += poisson_pmf(i, lambda_h) * poisson_pmf(j, lambda_a)
    return prob_over


# ==============================================================================
# MARCHÉS ÉTENDUS — calculs Poisson dérivés
# ==============================================================================

# Proportion historique des buts marqués en première période NHL.
# Validation sur ~29 000 matchs (2008-2025) : P1 = 29.7%, P2 = 35.2%, P3 = 35.1%.
# La P1 est légèrement sous-représentée car les équipes "tâtent" l'adversaire.
# Les P2/P3 ont plus de buts (transitions, déficit à combler, filet vide en fin de match).
P1_GOAL_RATIO = 0.30


def compute_p1_markets(lambda_h, lambda_a, ratio=P1_GOAL_RATIO):
    """
    Calcule les probas des 3 marchés de première période.
    Approximation : λ_P1 = λ_total × 0.33 (la P1 contient ~1/3 des buts d'un match NHL).

    Retourne un dict avec :
    - p_home_lead_p1 / p_tied_p1 / p_away_lead_p1 (vainqueur P1, 3-way)
    - p_over_1_5_p1, p_over_0_5_p1, p_over_2_5_p1 (totaux P1)
    - p_btts_p1 (les deux équipes marquent au moins 1 but en P1)
    """
    l1_h = lambda_h * ratio
    l1_a = lambda_a * ratio

    # Probabilité qu'une équipe ne marque PAS en P1 (Poisson : P(X=0) = e^(-λ))
    p_h_nogoal = poisson_pmf(0, l1_h)
    p_a_nogoal = poisson_pmf(0, l1_a)

    # BTTS P1 = P(home ≥ 1) × P(away ≥ 1)
    p_btts_p1 = (1 - p_h_nogoal) * (1 - p_a_nogoal)

    # Totaux Over (somme des cas où i+j > seuil)
    p_over = {0.5: 0.0, 1.5: 0.0, 2.5: 0.0}
    for i in range(8):
        for j in range(8):
            p_ij = poisson_pmf(i, l1_h) * poisson_pmf(j, l1_a)
            total = i + j
            for s in p_over:
                if total > s:
                    p_over[s] += p_ij

    # Vainqueur P1 (3-way) — home lead / tied / away lead à la fin de la P1
    p_home_lead, p_tied, p_away_lead = 0.0, 0.0, 0.0
    for i in range(8):
        for j in range(8):
            p_ij = poisson_pmf(i, l1_h) * poisson_pmf(j, l1_a)
            if i > j:   p_home_lead += p_ij
            elif i == j: p_tied      += p_ij
            else:        p_away_lead += p_ij

    return {
        'p_home_lead_p1':  p_home_lead,
        'p_tied_p1':        p_tied,
        'p_away_lead_p1':   p_away_lead,
        'p_over_0_5_p1':    p_over[0.5],
        'p_over_1_5_p1':    p_over[1.5],
        'p_over_2_5_p1':    p_over[2.5],
        'p_btts_p1':        p_btts_p1,
        'lambda_p1_h':      l1_h,
        'lambda_p1_a':      l1_a,
    }


def compute_total_distribution(lambda_h, lambda_a, max_k=14):
    """
    Distribution exacte du total de buts dans le match.
    Théorème : si X_h ~ Poisson(λ_h) et X_a ~ Poisson(λ_a) indépendants,
    alors X_h + X_a ~ Poisson(λ_h + λ_a).
    Retourne {0: p0, 1: p1, ..., max_k: p_max_k}.
    """
    lambda_total = lambda_h + lambda_a
    return {k: float(poisson_pmf(k, lambda_total)) for k in range(max_k + 1)}


def compute_goal_intervals(lambda_h, lambda_a):
    """
    Probabilités des intervalles classiques de bookmakers.
    Plus utile que les valeurs exactes pour le pari car les intervalles
    ont des cotes proposées.
    """
    dist = compute_total_distribution(lambda_h, lambda_a, max_k=14)
    intervals = {
        '0-2 buts':  sum(dist[k] for k in range(0, 3)),
        '3-4 buts':  sum(dist[k] for k in range(3, 5)),
        '5-6 buts':  sum(dist[k] for k in range(5, 7)),
        '7-8 buts':  sum(dist[k] for k in range(7, 9)),
        '9+ buts':   sum(dist[k] for k in range(9, 15)),
    }
    return intervals


def compute_top_exact_scores(lambda_h, lambda_a, top_n=10, max_score=7):
    """
    Top-N scores exacts les plus probables (i:j où i = buts home, j = buts away).
    Hypothèse : indépendance des scores home/away (raisonnable pour Poisson).
    P(i:j) = P(X_h = i) × P(X_a = j).

    Retourne une liste de tuples (score_str, proba, cote_équitable) triée par
    probabilité décroissante.
    """
    scores = []
    for i in range(max_score + 1):
        for j in range(max_score + 1):
            p = float(poisson_pmf(i, lambda_h) * poisson_pmf(j, lambda_a))
            fair_odd = 1.0 / max(p, 1e-6)
            scores.append((f'{i}-{j}', p, fair_odd))
    scores.sort(key=lambda x: -x[1])
    return scores[:top_n]


def compute_close_game_probability(lambda_h, lambda_a):
    """
    Probabilité que le match soit "serré" (écart ≤ 1 but).
    Proxy intéressant pour P(OT/SO) car les matchs serrés vont souvent en OT.
    Note : ce n'est pas exactement P(OT/SO) — pour ça il faut le modèle binaire
    séparé entraîné dans 03_Entrainement.ipynb.
    """
    p_tied   = sum(poisson_pmf(i, lambda_h) * poisson_pmf(i, lambda_a) for i in range(10))
    p_diff_1 = sum(poisson_pmf(i, lambda_h) * poisson_pmf(j, lambda_a)
                   for i in range(10) for j in range(10) if abs(i - j) == 1)
    return float(p_tied + p_diff_1)


# ==============================================================================
# AMÉLIORATIONS V5.6 — Distributions avancées
# ==============================================================================

def calculate_over_probability_nb(lambda_h, lambda_a, threshold=5.5,
                                    dispersion_h=1.15, dispersion_a=1.15):
    """
    Negative Binomial pour Over/Under — capture la sur-dispersion NHL.
    
    Quand dispersion = 1.0 → identique à Poisson.
    Quand dispersion > 1.0 → variance > moyenne (matchs explosifs/blanchissages plus fréquents).
    
    Paramétrisation : mean=lambda, var=lambda*dispersion
    NB scipy : nbinom(n, p) où p = 1/dispersion, n = lambda/(dispersion-1)
    """
    from scipy.stats import nbinom

    # Fallback à Poisson si dispersion ≤ 1 (NB pas définie)
    if dispersion_h <= 1.0 + 1e-6 and dispersion_a <= 1.0 + 1e-6:
        return calculate_over_probability(lambda_h, lambda_a, threshold)

    def pmf_nb_or_poisson(k, lam, disp):
        if disp <= 1.0 + 1e-6 or lam <= 0:
            return poisson_pmf(k, lam)
        p_param = 1.0 / disp
        n_param = lam * p_param / (1 - p_param)
        return float(nbinom.pmf(k, n_param, p_param))

    prob_over = 0.0
    for i in range(15):
        for j in range(15):
            if (i + j) > threshold:
                prob_over += pmf_nb_or_poisson(i, lambda_h, dispersion_h) * \
                             pmf_nb_or_poisson(j, lambda_a, dispersion_a)
    return prob_over


def bivariate_poisson_pmf(i, j, lambda1, lambda2, lambda3):
    """
    PMF de Karlis-Ntzoufras pour Bivariate Poisson.
    
    Modélise la corrélation entre buts home et away via le paramètre lambda3.
    - X_h = Y1 + Y3 où Y1 ~ Poisson(lambda1), Y3 ~ Poisson(lambda3)
    - X_a = Y2 + Y3 où Y2 ~ Poisson(lambda2)
    - lambda3 = Cov(X_h, X_a)
    
    Si lambda3=0 → indépendance (équivalent au produit P(X_h=i) × P(X_a=j)).
    """
    from math import factorial, exp
    if lambda1 <= 0 or lambda2 <= 0:
        # Fallback à Poisson indépendant
        return float(poisson_pmf(i, lambda1 + lambda3) * poisson_pmf(j, lambda2 + lambda3))
    
    prefix = exp(-(lambda1 + lambda2 + lambda3))
    try:
        prefix *= (lambda1 ** i) / factorial(i) * (lambda2 ** j) / factorial(j)
    except OverflowError:
        return 0.0
    
    sum_term = 0.0
    for k in range(min(i, j) + 1):
        c_i_k = factorial(i) / (factorial(k) * factorial(i - k))
        c_j_k = factorial(j) / (factorial(k) * factorial(j - k))
        ratio = (lambda3 / (lambda1 * lambda2)) ** k
        sum_term += c_i_k * c_j_k * factorial(k) * ratio
    
    return float(prefix * sum_term)


def compute_top_exact_scores_bivariate(lambda_h_total, lambda_a_total, lambda3,
                                         top_n=10, max_score=7):
    """
    Top-N scores exacts via Bivariate Poisson.
    lambda3 est la covariance estimée sur le training set (constante).
    """
    # Décomposition : lambda_h = lambda1 + lambda3 (donc lambda1 = lambda_h - lambda3)
    lambda1 = lambda_h_total - lambda3
    lambda2 = lambda_a_total - lambda3
    
    # Fallback à indépendance si décomposition invalide
    if lambda1 <= 0 or lambda2 <= 0:
        return compute_top_exact_scores(lambda_h_total, lambda_a_total, top_n=top_n, max_score=max_score)
    
    scores = []
    for i in range(max_score + 1):
        for j in range(max_score + 1):
            p = bivariate_poisson_pmf(i, j, lambda1, lambda2, lambda3)
            fair_odd = 1.0 / max(p, 1e-6)
            scores.append((f'{i}-{j}', p, fair_odd))
    scores.sort(key=lambda x: -x[1])
    return scores[:top_n]


def bayesian_p1_winner(lambda_p1_h, lambda_p1_a, team_h_prior=None, team_a_prior=None,
                        n_default=20):
    """
    Combine la likelihood Poisson P1 avec un prior par équipe.
    
    team_X_prior = {'home_p1_lead_rate', 'away_p1_lead_rate', 'n_games'}
    
    Plus l'équipe a de matchs historiques (n_games élevé), plus le prior pèse.
    n_default contrôle l'équilibre prior vs likelihood (plus haut = likelihood domine).
    """
    from scipy.stats import poisson as _poi
    
    # Likelihood depuis Poisson
    p_home_lead_lik = float(sum(_poi.pmf(i, lambda_p1_h) * _poi.pmf(j, lambda_p1_a)
                                  for i in range(8) for j in range(i)))
    p_tied_lik = float(sum(_poi.pmf(i, lambda_p1_h) * _poi.pmf(i, lambda_p1_a) for i in range(8)))
    p_away_lead_lik = 1.0 - p_home_lead_lik - p_tied_lik
    
    # Pas de prior → retour Poisson direct
    if team_h_prior is None or team_a_prior is None:
        return {
            'p_home_lead':  p_home_lead_lik,
            'p_tied':       p_tied_lik,
            'p_away_lead':  max(0, p_away_lead_lik),
            'confidence':   0.30,
            'source':       'Poisson seul (pas de prior équipe)',
        }
    
    # Combinaison bayésienne — pondération selon la force des priors
    prior_h_lead = team_h_prior.get('home_p1_lead_rate', 0.33)
    prior_a_lead = team_a_prior.get('away_p1_lead_rate', 0.33)
    strength_h = team_h_prior.get('n_games', 0)
    strength_a = team_a_prior.get('n_games', 0)
    total_strength = min(strength_h + strength_a, 200)  # cap pour éviter sur-pondération
    
    w_prior = total_strength / (total_strength + n_default * 2)
    w_lik = 1 - w_prior
    
    # Posterior — moyenne pondérée puis renormalisation
    raw_home = prior_h_lead * w_prior + p_home_lead_lik * w_lik
    raw_away = prior_a_lead * w_prior + p_away_lead_lik * w_lik
    raw_tied = p_tied_lik * w_lik + (1 - prior_h_lead - prior_a_lead) * w_prior  # complément
    
    # Renormalisation pour somme = 1
    total = raw_home + raw_away + raw_tied
    if total > 0:
        post_home = raw_home / total
        post_tied = raw_tied / total
        post_away = raw_away / total
    else:
        post_home, post_tied, post_away = p_home_lead_lik, p_tied_lik, p_away_lead_lik
    
    confidence = min(total_strength / 100, 1.0)
    
    return {
        'p_home_lead':  post_home,
        'p_tied':       post_tied,
        'p_away_lead':  post_away,
        'confidence':   confidence,
        'source':       f'Bayesian (n_games={total_strength})',
    }


def btts_p1_quality(lambda_p1_h, lambda_p1_a):
    """
    Évalue la fiabilité d'une prédiction BTTS P1.
    Renvoie un tag de qualité — éviter de parier si 'Faible'.
    """
    min_lambda = min(lambda_p1_h, lambda_p1_a)
    if min_lambda < 0.7:
        return ('⚠️ Faible', 'Une équipe a λ_P1 < 0.7 — signal fragile, éviter ce pari')
    if min_lambda < 0.85:
        return ('🟡 Modéré', 'Modèle utilisable mais avec mise réduite')
    return ('✅ Fiable', 'Les deux équipes ont un scoring P1 robuste')


# ==============================================================================
# API NHL.com — Gardien partant confirmé
# ==============================================================================
# Endpoints publics utilisables sans clé API :
# - https://api-web.nhle.com/v1/schedule/{date}        → matchs du jour
# - https://api-web.nhle.com/v1/gamecenter/{gameId}/right-rail → gardiens probables
# - https://api-web.nhle.com/v1/club-stats/{team}/now  → stats équipe (incl. gardiens)
#
# Les gardiens "probables" sont publiés ~2-4h avant le match. Avant ça, fallback
# sur le gardien le plus utilisé récemment (icetime).

import requests as _requests  # alias pour rester compatible avec l'ancien code

def get_nhl_schedule(date_str=None):
    """
    Récupère le calendrier NHL pour une date (YYYY-MM-DD) ou aujourd'hui.
    Retourne une liste de dicts {gameId, home, away, startTime}.
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    try:
        r = _requests.get(f'https://api-web.nhle.com/v1/schedule/{date_str}', timeout=8)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f'⚠️  NHL API schedule erreur : {e}')
        return []

    games = []
    for week in data.get('gameWeek', []):
        if week.get('date') == date_str:
            for g in week.get('games', []):
                games.append({
                    'gameId':    g.get('id'),
                    'home':      g.get('homeTeam', {}).get('abbrev'),
                    'away':      g.get('awayTeam', {}).get('abbrev'),
                    'startTime': g.get('startTimeUTC'),
                })
    return games


def get_probable_starters(game_id):
    """
    Récupère les gardiens partants probables pour un match.
    Retourne un dict {home_goalie, away_goalie, confirmed: bool}.
    """
    try:
        r = _requests.get(f'https://api-web.nhle.com/v1/gamecenter/{game_id}/right-rail',
                          timeout=8)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return {'home_goalie': None, 'away_goalie': None, 'confirmed': False}

    home_g = None
    away_g = None
    # La structure exacte varie — on cherche dans plusieurs endroits possibles
    game_info = data.get('gameInfo', {})
    for key in ['homeTeam', 'awayTeam']:
        team_info = game_info.get(key, {})
        goalie = team_info.get('goalie', {})
        if goalie:
            name = f"{goalie.get('firstName','')} {goalie.get('lastName','')}".strip()
            if key == 'homeTeam':  home_g = name
            else:                  away_g = name

    return {
        'home_goalie': home_g if home_g else None,
        'away_goalie': away_g if away_g else None,
        'confirmed':   bool(home_g and away_g),
    }


def get_likely_starter_from_history(goalies_df, team_code, recent_window=10):
    """
    Fallback : identifie le gardien le plus probable comme partant
    en se basant sur les patterns d'icetime des derniers matchs.
    """
    if goalies_df is None or goalies_df.empty:
        return None
    recent = goalies_df[goalies_df.get('team', '') == team_code].tail(recent_window * 2)
    if recent.empty:
        return None
    icetime_col = 'icetime' if 'icetime' in recent.columns else 'icetime_m'
    if icetime_col not in recent.columns:
        return None
    # Le gardien avec le plus de temps de glace cumulé = #1 starter
    return recent.groupby('name')[icetime_col].sum().idxmax()


def get_goalie_rolling_gsae(goalies_df, goalie_name, before_date=None, window=10):
    """
    Récupère le GSAE (Goals Saved Above Expected) rolling d'un gardien.
    Si goalie_name introuvable → retourne 0 (gardien moyen).
    """
    if goalies_df is None or goalies_df.empty or not goalie_name:
        return 0.0
    games = goalies_df[goalies_df.get('name', '') == goalie_name]
    if before_date is not None and 'gameDate' in games.columns:
        games = games[games['gameDate'] < before_date]
    games = games.tail(window)
    if games.empty:
        return 0.0
    # GSAE = xGoalsAgainst - goalsAgainst (positif = gardien meilleur que prévu)
    if 'xGoalsAgainst' in games.columns and 'goalsAgainst' in games.columns:
        return float((games['xGoalsAgainst'] - games['goalsAgainst']).sum())
    return 0.0


def poisson_pmf(k, lam):
    """PMF de la loi de Poisson (évite import scipy dans le module)."""
    from scipy.stats import poisson
    return poisson.pmf(k, lam)


def build_input_vector(feat_name, h_stats, a_stats, b2b_h=0, b2b_a=0):
    """Construit la valeur d'une feature différentielle pour l'inférence."""
    FEAT_MAP = {
        'diff_xGF_pct':           ('xGF_pct',       'xGF_pct'),
        'diff_goalie_impact':     ('goalie_impact', 'goalie_impact'),
        'diff_corsi':             ('corsi',         'corsi'),
        'diff_top_line_xGF':      ('top_line_xGF',  'top_line_xGF'),
        'diff_pp':                ('pp',             'pp'),
        'diff_pk':                ('pk',             'pk'),
        'diff_forme':             ('forme',          'forme'),
        'diff_HDcf':              ('HDcf',           'HDcf'),
        'diff_panic_score':       ('panic_score',    'panic_score'),
        'diff_stress':            ('stress',         'stress'),
        'diff_elo':               ('elo',            'elo'),
        'diff_pdo':               ('pdo',            'pdo'),
        'diff_xGF_5':             ('xGF_5',          'xGF_5'),
        'diff_xGF_20':            ('xGF_20',         'xGF_20'),
        'diff_xGF_season':        ('xGF_season',     'xGF_season'),    # NOUVEAU V5.4
        'diff_pp_5':              ('pp_5',            'pp_5'),
        'diff_pp_20':             ('pp_20',           'pp_20'),
        'diff_momentum':          ('momentum',        'momentum'),
        'diff_days_rest':         ('days_rest',       'days_rest'),    # NOUVEAU V5.4
        'diff_csa_pct':           ('csa_pct',         'csa_pct'),       # NOUVEAU V5.5
        'diff_goalie_starter_gsae': ('goalie_starter_gsae', 'goalie_starter_gsae'),  # NOUVEAU V5.5
    }
    # Features H2H (pas un différentiel — directement value du match)
    if feat_name == 'h2h_home_dominance':
        return h_stats.get('h2h_home_dominance', 0.0)
    if feat_name == 'h2h_avg_total_goals':
        return h_stats.get('h2h_avg_total_goals', 5.7)
    if feat_name == 'diff_b2b':
        return b2b_h - b2b_a
    if feat_name == 'interaction_goalie_xgf':
        return ((h_stats['goalie_impact'] - a_stats['goalie_impact']) *
                (h_stats['xGF_pct'] - a_stats['xGF_pct']))
    if feat_name == 'interaction_forme_xgf':
        return ((h_stats['forme'] - a_stats['forme']) *
                (h_stats['xGF_pct'] - a_stats['xGF_pct']))
    if feat_name in FEAT_MAP:
        hk, ak = FEAT_MAP[feat_name]
        return h_stats.get(hk, 0.0) - a_stats.get(ak, 0.0)
    return 0.0
