"""
publication_labels.py — Libellés lisibles des features NHL.

Alignés sur les features réellement utilisées par le moteur moneyline
(`NHLMoneylineEngine.features_used`). Une feature absente de ce dictionnaire
est rendue lisible automatiquement (cf. `vizer_core.explain`).

Toutes les features sont des **différentiels domicile − extérieur** : une
contribution positive pousse la probabilité vers l'équipe à domicile.
"""
FEATURE_LABELS: dict[str, str] = {
    'diff_elo': 'Écart Elo',
    'diff_xGF_pct': 'Part de buts attendus (xGF %)',
    'diff_xGF_5': 'Buts attendus — 5 derniers matchs',
    'diff_xGF_20': 'Buts attendus — 20 derniers matchs',
    'diff_xGF_season': 'Buts attendus — saison',
    'diff_top_line_xGF': 'Rendement de la première ligne',
    'diff_HDcf': 'Occasions de haute qualité',
    'diff_pp': 'Efficacité en supériorité numérique',
    'diff_pp_5': 'Supériorité numérique — 5 derniers matchs',
    'diff_pp_20': 'Supériorité numérique — 20 derniers matchs',
    'diff_forme': 'Forme récente',
    'diff_b2b': 'Matchs consécutifs (back-to-back)',
    'diff_days_rest': 'Jours de repos',
    'diff_panic_score': 'Pression au classement',
    'interaction_goalie_xgf': 'Gardien × buts attendus',
    'interaction_forme_xgf': 'Forme × buts attendus',
}
