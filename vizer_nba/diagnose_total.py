#!/usr/bin/env python
"""
diagnose_total.py — Diagnostic du modèle Total NBA.

Identifie l'origine probable du MAE=15.16 / R²=0.07 :
  1. Distribution shift inter-saisons
  2. Comparaison à des baselines naïves (référence MAE)
  3. Stabilité du scoring sur les saisons récentes
  4. Recommandation chiffrée

Usage :
    cd vizer_nba/
    python diagnose_total.py

Sortie : affichage console + fichier diagnostic_report.txt
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from vizer_core import load_config


# MAE du modèle XGB actuel (rapporté par train.py)
XGB_MAE_REPORTED = 15.16


def _tee_print(buffer: StringIO, *args, **kwargs):
    """Affiche ET capture dans le buffer."""
    print(*args, **kwargs)
    kwargs.pop('file', None)
    print(*args, file=buffer, **kwargs)


def main(config_path: str = 'config.yaml') -> int:
    buf = StringIO()
    p = lambda *a, **k: _tee_print(buf, *a, **k)

    p("=" * 70)
    p("🔍 DIAGNOSTIC MODÈLE TOTAL NBA")
    p("=" * 70)
    p()

    # ─── Setup ──────────────────────────────────────────────────────────────
    config = load_config(config_path)
    games_path = config['data']['paths']['games']
    games = pd.read_csv(games_path)
    train_start = config['data_split']['train_season_start']
    train_end = config['data_split']['train_season_end']
    test_season = config['data_split']['test_season']

    p(f"Données       : {games_path}")
    p(f"Lignes totales: {len(games):,}")
    p(f"Train seasons : {train_start} → {train_end}")
    p(f"Test season   : {test_season}")
    p()

    # ─── Calcul du total par match ──────────────────────────────────────────
    # Le CSV a 2 lignes par GAME_ID (une par équipe). Total = somme des 2 PTS.
    totals = games.groupby('GAME_ID').agg(
        season=('SEASON_ID', 'first'),
        date=('GAME_DATE', 'first'),
        total=('PTS', 'sum'),
        n_teams=('TEAM_ID', 'count'),
    ).reset_index()
    totals = totals[totals['n_teams'] == 2].copy()  # sanity : match complet
    p(f"Matchs valides (avec 2 équipes) : {len(totals):,}")
    p()

    # ─── Section 1 : Évolution par saison ───────────────────────────────────
    p("=" * 70)
    p("📈 SECTION 1 — TOTAL MOYEN PAR SAISON")
    p("=" * 70)
    p()
    season_stats = (
        totals.groupby('season')['total']
        .agg(['mean', 'std', 'count'])
        .rename(columns={'mean': 'Mean', 'std': 'Std', 'count': 'Count'})
    )
    p(season_stats.round(1).to_string())
    p()

    # ─── Section 2 : Distribution shift ─────────────────────────────────────
    p("=" * 70)
    p("⚠️  SECTION 2 — DISTRIBUTION SHIFT TRAIN vs TEST")
    p("=" * 70)
    p()

    train_mask = (totals['season'] >= train_start) & (totals['season'] <= train_end)
    test_mask = totals['season'] == test_season
    train_totals = totals.loc[train_mask, 'total']
    test_totals = totals.loc[test_mask, 'total']

    if test_totals.empty:
        p(f"⚠️ Aucun match trouvé pour la saison test {test_season}. Diagnostic interrompu.")
        Path('diagnostic_report.txt').write_text(buf.getvalue())
        return 1

    p(f"Train ({train_start}-{train_end}):")
    p(f"  N matches : {len(train_totals):,}")
    p(f"  Total mean: {train_totals.mean():.1f}")
    p(f"  Total std : {train_totals.std():.1f}")
    p()
    p(f"Test  ({test_season}):")
    p(f"  N matches : {len(test_totals):,}")
    p(f"  Total mean: {test_totals.mean():.1f}")
    p(f"  Total std : {test_totals.std():.1f}")
    p()
    shift = test_totals.mean() - train_totals.mean()
    p(f"SHIFT : {shift:+.1f} points")
    if abs(shift) > 5:
        p(f"  🔴 Shift important : le modèle entraîné sur ~{train_totals.mean():.0f} pts")
        p(f"     est testé sur des matchs qui font en moyenne {test_totals.mean():.0f} pts.")
    elif abs(shift) > 2:
        p(f"  🟡 Shift modéré.")
    else:
        p(f"  ✓ Shift faible.")
    p()

    # ─── Section 3 : Baselines ──────────────────────────────────────────────
    p("=" * 70)
    p("🎯 SECTION 3 — BASELINES NAÏVES (MAE sur la saison test)")
    p("=" * 70)
    p()
    p("Référence pour juger si XGB (MAE=15.16) apporte vraiment de la valeur.")
    p()

    y_test = test_totals.values

    # B1 : prédire la moyenne du train
    mae_b1 = float(np.mean(np.abs(y_test - train_totals.mean())))

    # B2 : prédire la moyenne du test lui-même (oracle, référence minimale absolue)
    mae_b2 = float(np.mean(np.abs(y_test - test_totals.mean())))

    # B3 : prédire la moyenne de la saison précédente
    prev_season = test_season - 1
    prev_totals = totals.loc[totals['season'] == prev_season, 'total']
    prev_mean = float(prev_totals.mean()) if len(prev_totals) else float('nan')
    mae_b3 = float(np.mean(np.abs(y_test - prev_mean))) if not np.isnan(prev_mean) else float('nan')

    # B4 : prédire la moyenne des 5 dernières saisons (5-year rolling mean)
    recent_seasons = list(range(test_season - 5, test_season))
    recent_totals = totals.loc[totals['season'].isin(recent_seasons), 'total']
    recent_mean = float(recent_totals.mean()) if len(recent_totals) else float('nan')
    mae_b4 = float(np.mean(np.abs(y_test - recent_mean))) if not np.isnan(recent_mean) else float('nan')

    p(f"{'Baseline':<55s} {'MAE':>7s}")
    p("-" * 65)
    p(f"{'B1 — moyenne train (' + f'{train_totals.mean():.1f}' + ')':<55s} {mae_b1:>7.2f}")
    p(f"{'B2 — moyenne test, oracle (' + f'{test_totals.mean():.1f}' + ')':<55s} {mae_b2:>7.2f}")
    if not np.isnan(mae_b3):
        p(f"{'B3 — moyenne saison N-1 (' + f'{prev_mean:.1f}' + ')':<55s} {mae_b3:>7.2f}")
    if not np.isnan(mae_b4):
        p(f"{'B4 — moyenne 5 saisons récentes (' + f'{recent_mean:.1f}' + ')':<55s} {mae_b4:>7.2f}")
    p(f"{'XGB actuel (rapporté par train.py)':<55s} {XGB_MAE_REPORTED:>7.2f}")
    p()

    # Verdict
    best_baseline = min(b for b in [mae_b3, mae_b4] if not np.isnan(b))
    p("Verdict :")
    if XGB_MAE_REPORTED > best_baseline:
        p(f"  🔴 XGB ({XGB_MAE_REPORTED}) est PIRE qu'une baseline naïve ({best_baseline:.2f}).")
        p(f"     Le modèle n'apporte pas de valeur dans son état actuel.")
    elif XGB_MAE_REPORTED > best_baseline - 2:
        p(f"  🟡 XGB ({XGB_MAE_REPORTED}) bat à peine la meilleure baseline ({best_baseline:.2f}).")
        p(f"     Marge < 2 pts : insuffisant pour bookmakers.")
    else:
        p(f"  ✓ XGB ({XGB_MAE_REPORTED}) bat clairement la baseline ({best_baseline:.2f}).")
    p()

    # ─── Section 4 : Stabilité récente ──────────────────────────────────────
    p("=" * 70)
    p("💡 SECTION 4 — RECOMMANDATION")
    p("=" * 70)
    p()
    n_recent = 7
    recent_window = season_stats.tail(n_recent)
    p(f"Scoring sur les {n_recent} dernières saisons :")
    p(recent_window.round(1).to_string())
    p()
    recent_range = recent_window['Mean'].max() - recent_window['Mean'].min()
    p(f"Range Mean sur la fenêtre : {recent_range:.1f} pts")
    p()

    if recent_range < 5:
        p("  ✓ Très stable. Recommandation :")
        p(f"    → train_season_start: {test_season - n_recent + 1}")
        p(f"    → garder le modèle XGB tel quel, juste raccourcir la fenêtre.")
    elif recent_range < 10:
        p("  🟡 Stabilité modérée. Recommandation :")
        p(f"    → train_season_start: {test_season - 5} (5 dernières saisons)")
        p(f"    → ajouter une feature SEASON_AVG_TOTAL pour absorber le shift résiduel.")
    else:
        p("  🔴 Shift inter-saison majeur. Recommandation :")
        p(f"    → train_season_start: {test_season - 3} (fenêtre courte, 3 saisons)")
        p(f"    → ajouter feature SEASON_AVG_TOTAL OBLIGATOIRE.")
        p(f"    → envisager un modèle Poisson sur (PACE × EFFICIENCY) au lieu de XGB direct.")
    p()

    # ─── Sauvegarde ─────────────────────────────────────────────────────────
    report_path = Path('diagnostic_report.txt')
    report_path.write_text(buf.getvalue())
    print(f"📄 Rapport sauvegardé : {report_path.resolve()}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
