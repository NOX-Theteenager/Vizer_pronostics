"""
explain.py — Attribution par match, à partir des contributions SHAP de XGBoost.

XGBoost sait restituer les contributions exactes de chaque feature à une
prédiction (`pred_contribs=True`) : il n'y a donc rien à approximer ni à
inventer pour expliquer « pourquoi cette prédiction ».

Utilitaire ML générique, sans logique métier : chaque sport fournit son propre
dictionnaire de libellés (cf. `vizer_<sport>/src/api/publication.py`).
"""
from __future__ import annotations

import re
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd


def _readable(name: str) -> str:
    """`xGoalsPercentage_diff` → « xGoals percentage (différentiel) »."""
    suffix = ''
    base = name
    for key, label in (('_diff', ' (différentiel)'), ('_home', ' (domicile)'),
                       ('_away', ' (extérieur)'), ('_m', ' (moyenne)')):
        if base.endswith(key):
            base = base[: -len(key)]
            suffix = label
            break
    # camelCase → mots séparés, sans casser les sigles (xGF, HDcf, PP)
    base = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', base).replace('_', ' ')
    base = re.sub(r'\s+', ' ', base).strip()
    return (base[:1].upper() + base[1:]) + suffix


def top_contributions(
    model: Any,
    features_row: pd.DataFrame,
    feature_names: Optional[Sequence[str]] = None,
    top_n: int = 3,
    labels: Optional[dict[str, str]] = None,
    display_row: Optional[pd.DataFrame] = None,
) -> list[dict[str, Any]]:
    """
    Les `top_n` features qui pèsent le plus sur cette prédiction précise.

    Args:
        model          : XGBClassifier/XGBRegressor (ou objet exposant
                         `get_booster()`). Tout autre modèle → liste vide.
        features_row   : une seule ligne de features, déjà transformée.
        feature_names  : noms attendus par le modèle ; déduits sinon.
        labels         : surcharges de libellés, par nom de feature.
        display_row    : mêmes features avant standardisation, pour afficher
                         une valeur lisible plutôt qu'un z-score.

    Returns:
        [{'feature', 'label', 'value', 'contribution', 'direction'}], trié par
        |contribution| décroissante. `direction` vaut 'home' si la feature
        pousse la probabilité vers le haut, 'away' sinon — à interpréter selon
        la cible du modèle.
    """
    booster_fn = getattr(model, 'get_booster', None)
    if booster_fn is None or features_row is None or len(features_row) == 0:
        return []

    try:
        import xgboost as xgb  # noqa: PLC0415 — dépendance optionnelle ici
    except ImportError:
        return []

    try:
        booster = booster_fn()
        names = list(feature_names) if feature_names else list(features_row.columns)
        row = features_row[names].iloc[[0]] if set(names).issubset(features_row.columns) \
            else features_row.iloc[[0]]
        contribs = booster.predict(
            xgb.DMatrix(row, feature_names=list(row.columns)),
            pred_contribs=True,
        )
    except Exception:
        # Un modèle non-XGB, un désalignement de features ou une version de
        # booster trop ancienne ne doivent pas casser la prédiction : la PWA
        # masque simplement la carte d'explication.
        return []

    contribs = np.asarray(contribs)
    if contribs.ndim != 2 or contribs.shape[0] < 1:
        return []

    # La dernière colonne est le biais (valeur de base), pas une feature.
    values = contribs[0][:-1]
    cols = list(row.columns)
    if len(values) != len(cols):
        return []

    order = np.argsort(np.abs(values))[::-1][:top_n]
    labels = labels or {}
    out: list[dict[str, Any]] = []
    for idx in order:
        name = cols[idx]
        contribution = float(values[idx])
        if abs(contribution) < 1e-9:
            continue
        source = display_row if display_row is not None and name in display_row.columns else row
        raw_value = source.iloc[0][name] if source is not row else row.iloc[0, idx]
        out.append({
            'feature': name,
            'label': labels.get(name, _readable(name)),
            'value': None if pd.isna(raw_value) else round(float(raw_value), 4),
            'contribution': round(contribution, 4),
            'direction': 'home' if contribution > 0 else 'away',
        })
    return out
