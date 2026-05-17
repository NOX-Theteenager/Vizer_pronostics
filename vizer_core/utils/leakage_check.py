"""
Détection automatique de data leakage dans les features.

Le data leakage (fuite de données) survient quand une feature encode directement
ou indirectement la target. Symptôme typique : accuracy/AUC anormalement élevée
sur le test set (>85% sur problèmes difficiles comme la prédiction sportive).

Ce module fournit deux niveaux de détection :
- `detect_target_leakage` : retourne les features suspectes (à inspecter manuellement)
- `assert_no_leakage` : lève une exception si des features dépassent le seuil
                       (à appeler avant chaque .fit() en safety net)

Limites :
- Détecte les corrélations LINÉAIRES (Pearson) ou MONOTONIQUES (Spearman).
- Ne détecte PAS les leakages non-linéaires (ex: XOR de deux features).
  Pour ça, il faudrait entraîner un decision stump par feature et regarder
  l'accuracy. À ajouter si besoin.
- Faux positifs possibles : certaines features peuvent être *légitimement*
  très corrélées (ex: rating ELO calculé correctement). Utiliser `allowlist`
  pour les exclure.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd


class LeakageError(ValueError):
    """Levée par assert_no_leakage quand une fuite est détectée."""


def detect_target_leakage(
    X: pd.DataFrame,
    y: pd.Series | np.ndarray,
    threshold: float = 0.9,
    method: Literal["pearson", "spearman"] = "pearson",
) -> dict[str, float]:
    """
    Identifie les features dont la corrélation absolue avec la target dépasse `threshold`.

    Args:
        X         : DataFrame de features (colonnes numériques uniquement testées).
        y         : Target (Series ou array de même longueur que X).
        threshold : Seuil de corrélation absolue. 0.9 par défaut = très conservateur.
                    En sport, une feature légitime dépasse rarement 0.5.
        method    : 'pearson' (linéaire) ou 'spearman' (monotonique, plus robuste
                    aux features ordinales / discrètes).

    Returns:
        Dict {feature_name: |correlation|} trié par corrélation décroissante.
        Vide si aucune feature suspecte.
    """
    if len(X) != len(y):
        raise ValueError(
            f"X ({len(X)} lignes) et y ({len(y)} lignes) ont des longueurs différentes."
        )

    y_series = pd.Series(np.asarray(y)).reset_index(drop=True)
    suspicious: dict[str, float] = {}

    for col in X.columns:
        s = X[col]
        # Ignorer non-numériques (catégorielles textuelles)
        if not np.issubdtype(s.dtype, np.number):
            continue
        # Ignorer constantes (corr indéfinie)
        if s.nunique(dropna=True) <= 1:
            continue
        try:
            corr = s.reset_index(drop=True).corr(y_series, method=method)
        except Exception:
            continue
        if pd.isna(corr):
            continue
        abs_corr = abs(float(corr))
        if abs_corr >= threshold:
            suspicious[col] = abs_corr

    return dict(sorted(suspicious.items(), key=lambda kv: kv[1], reverse=True))


def assert_no_leakage(
    X: pd.DataFrame,
    y: pd.Series | np.ndarray,
    threshold: float = 0.9,
    method: Literal["pearson", "spearman"] = "pearson",
    allowlist: list[str] | None = None,
) -> None:
    """
    Lève LeakageError si des features dépassent le seuil de corrélation.

    À appeler systématiquement avant `fit()` dans les scripts d'entraînement.

    Args:
        allowlist : Features autorisées à être très corrélées (ex: 'elo_diff' calculé
                    correctement avec shift). Évite les faux positifs.

    Raises:
        LeakageError : si des features non-allowlistées dépassent threshold.
    """
    suspicious = detect_target_leakage(X, y, threshold=threshold, method=method)
    if allowlist:
        allowed = set(allowlist)
        suspicious = {k: v for k, v in suspicious.items() if k not in allowed}

    if suspicious:
        details = "\n".join(f"    - {name:40s} |corr| = {corr:.4f}" for name, corr in suspicious.items())
        raise LeakageError(
            f"\n⚠️  DATA LEAKAGE SUSPECT (corrélation absolue ≥ {threshold:.2f}, méthode={method}) :\n"
            f"{details}\n\n"
            f"Ces features encodent peut-être directement la target.\n"
            f"Actions possibles :\n"
            f"  1. Inspecter le code qui les calcule (utilisent-elles la target ?).\n"
            f"  2. Si la corrélation est légitime, ajouter la feature à `allowlist`.\n"
            f"  3. Si c'est un bug, retirer ou corriger la feature avant fit().\n"
        )


def report_top_correlations(
    X: pd.DataFrame,
    y: pd.Series | np.ndarray,
    top_n: int = 10,
    method: Literal["pearson", "spearman"] = "pearson",
) -> pd.DataFrame:
    """
    Helper de debug : retourne les `top_n` features les plus corrélées à y,
    sans seuil. Utile pour avoir une vue d'ensemble avant de fixer un threshold.

    Returns:
        DataFrame avec colonnes ['feature', 'abs_correlation', 'correlation'].
    """
    y_series = pd.Series(np.asarray(y)).reset_index(drop=True)
    rows = []
    for col in X.columns:
        s = X[col]
        if not np.issubdtype(s.dtype, np.number):
            continue
        if s.nunique(dropna=True) <= 1:
            continue
        try:
            corr = s.reset_index(drop=True).corr(y_series, method=method)
        except Exception:
            continue
        if pd.isna(corr):
            continue
        rows.append({"feature": col, "abs_correlation": abs(float(corr)), "correlation": float(corr)})

    df = pd.DataFrame(rows).sort_values("abs_correlation", ascending=False)
    return df.head(top_n).reset_index(drop=True)
