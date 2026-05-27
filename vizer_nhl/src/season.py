"""
season.py — Détection automatique de la saison NHL.

Convention Moneypuck : la "saison Y" couvre octobre Y → juin Y+1, et le
fichier de cette saison est nommé avec l'année Y (ex: skaters_2025.csv pour
la saison 2025-2026).

Règle de détection :
  - Octobre, novembre, décembre  → saison = année courante
  - Janvier à septembre          → saison = année courante - 1
    (de janvier à juin on est en pleine saison commencée l'automne précédent ;
     de juillet à septembre c'est l'intersaison, on pointe la dernière saison)
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional


def current_nhl_season(today: Optional[date] = None) -> int:
    """
    Retourne l'année Moneypuck de la saison NHL courante (ou la plus récente
    si on est en intersaison).

    Exemples :
        mai 2026      → 2025  (saison 2025-2026 en cours)
        octobre 2026  → 2026  (nouvelle saison 2026-2027 démarre)
        août 2026     → 2025  (intersaison, dernière saison = 2025-2026)
    """
    today = today or date.today()
    if today.month >= 10:           # oct/nov/déc → nouvelle saison
        return today.year
    return today.year - 1           # jan-sep → saison commencée l'automne d'avant


def is_offseason(today: Optional[date] = None) -> bool:
    """True si on est en intersaison NHL (juillet à mi-septembre)."""
    today = today or date.today()
    return today.month in (7, 8, 9)


def detect_available_seasons(data_dir: str, category: str = 'skaters') -> list[int]:
    """
    Détecte les saisons disponibles localement en scannant les fichiers
    `{category}_*.csv` dans data_dir.

    Gère :
      - fichiers mono-saison : skaters_2025.csv → 2025
      - fichiers multi-saisons : skaters_2008_2024.csv → 2008..2024

    Returns:
        Liste triée des années couvertes par les fichiers présents.
    """
    seasons: set[int] = set()
    for p in Path(data_dir).glob(f'{category}_*.csv'):
        stem = p.stem.replace(f'{category}_', '')
        parts = stem.split('_')
        try:
            if len(parts) == 2:               # ex: 2008_2024
                start, end = int(parts[0]), int(parts[1])
                seasons.update(range(start, end + 1))
            elif len(parts) == 1 and parts[0].isdigit():  # ex: 2025
                seasons.add(int(parts[0]))
        except ValueError:
            continue
    return sorted(seasons)


def detect_dataset_seasons(df, date_col: str = 'gameDate_home') -> list[int]:
    """Retourne les années présentes dans un dataset agrégé (via la date)."""
    import pandas as pd
    years = pd.to_datetime(df[date_col]).dt.year.unique()
    return sorted(int(y) for y in years)


def suggest_train_test_split(seasons: list[int]) -> tuple[int, int]:
    """
    Propose un split train/test automatique : test = dernière saison complète,
    train = tout le reste.

    Returns:
        (train_until_year, test_year)
    """
    if len(seasons) < 2:
        # Pas assez de saisons : tout en train, test = dernière
        y = seasons[-1] if seasons else current_nhl_season()
        return y, y
    test_year = seasons[-1]
    train_until_year = seasons[-2]
    return train_until_year, test_year
