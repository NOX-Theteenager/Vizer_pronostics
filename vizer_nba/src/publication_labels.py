"""
publication_labels.py — Libellés lisibles des features NBA.

Utilisés par la carte « Pourquoi cette prédiction ». Une feature absente est
rendue lisible automatiquement (cf. `vizer_core.explain`).
"""
FEATURE_LABELS: dict[str, str] = {
    'elo_diff': 'Écart Elo entre les deux équipes',
    'net_rating_diff': 'Différentiel de net rating',
    'off_rating_diff': 'Différentiel d’attaque',
    'def_rating_diff': 'Différentiel de défense',
    'pace_diff': 'Différentiel de rythme (pace)',
    'rest_days_diff': 'Différentiel de jours de repos',
    'talent_ratio_diff': 'Différentiel d’effectif disponible',
    'pts_m_diff': 'Différentiel de points marqués (moyenne)',
    'reb_m_diff': 'Différentiel de rebonds',
    'ast_m_diff': 'Différentiel de passes décisives',
    'fg3_pct_m_diff': 'Différentiel d’adresse à 3 points',
    'is_home': 'Avantage du terrain',
    'b2b_home': 'Match consécutif pour l’équipe à domicile',
    'b2b_away': 'Match consécutif pour l’équipe à l’extérieur',
}
