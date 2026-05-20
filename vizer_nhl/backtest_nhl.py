#!/usr/bin/env python
"""
backtest_nhl.py — Backtest des marchés NHL sur la saison de test.

Réutilise vizer_core.Backtester (sport-agnostic) avec un outcome_fn NHL.

Modes :
    --mode calibration  : pas de cotes, juste calibration + Brier
    --mode synthetic    : book naïf (baseline) — sur-évalue le modèle
    --mode calibrated   : book réaliste (voit features + bruit)  [défaut]
    --mode csv          : cotes archivées via --odds-csv

Exemples :
    python backtest_nhl.py
    python backtest_nhl.py --mode calibration
    python backtest_nhl.py --mode calibrated --export-bets bets_nhl.csv
    python backtest_nhl.py --markets moneyline total btts --stake-mode flat
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from vizer_core import (
    ModelRegistry, Backtester, BacktestConfig,
    NullOddsProvider, SyntheticOddsProvider, CalibratedSyntheticOddsProvider,
    CSVOddsProvider, load_config,
)

from src.data.loader import NHLDataLoader
from src.features.engineer import NHLFeatureEngineer


# ===================================================================
# outcome_fn NHL : "la sélection a-t-elle gagné ?"
# ===================================================================

def outcome_fn(row, market_name: str, selection: str):
    """
    Détermine si une sélection NHL a gagné.

    Returns True / False / None (None = indéterminable, ex: push ou data P1 absente).
    """
    home_goals = row.get('finalGoals_home')
    away_goals = row.get('finalGoals_away')
    if pd.isna(home_goals) or pd.isna(away_goals):
        return None
    home_goals = int(home_goals)
    away_goals = int(away_goals)
    total = home_goals + away_goals
    home_won = bool(row.get('home_team_won', home_goals > away_goals))

    # --- Moneyline ---
    if market_name == 'moneyline':
        if selection == 'home':
            return home_won
        if selection == 'away':
            return not home_won
        return None

    # --- Total ---
    if market_name == 'total':
        if '_' not in selection:
            return None
        side, line_str = selection.split('_', 1)
        line = float(line_str)
        if total == line:
            return None  # push
        if side == 'over':
            return total > line
        if side == 'under':
            return total < line
        return None

    # --- BTTS ---
    if market_name == 'btts':
        actual = (home_goals >= 1) and (away_goals >= 1)
        if selection == 'yes':
            return actual
        if selection == 'no':
            return not actual
        return None

    # --- P1 markets : requièrent goals_p1_* ---
    p1_h = row.get('goals_p1_home')
    p1_a = row.get('goals_p1_away')
    has_p1 = not (pd.isna(p1_h) or pd.isna(p1_a))

    if market_name == 'p1_winner':
        if not has_p1:
            return None
        p1_h, p1_a = int(p1_h), int(p1_a)
        if selection == 'home_lead':
            return p1_h > p1_a
        if selection == 'tied':
            return p1_h == p1_a
        if selection == 'away_lead':
            return p1_h < p1_a
        return None

    if market_name == 'p1_total':
        if not has_p1:
            return None
        p1_total = int(p1_h) + int(p1_a)
        if '_' not in selection:
            return None
        side, line_str = selection.split('_', 1)
        line = float(line_str)
        if p1_total == line:
            return None
        if side == 'over':
            return p1_total > line
        if side == 'under':
            return p1_total < line
        return None

    if market_name == 'p1_btts':
        if not has_p1:
            return None
        actual = (int(p1_h) >= 1) and (int(p1_a) >= 1)
        if selection == 'yes':
            return actual
        if selection == 'no':
            return not actual
        return None

    # --- Exact score : selection '<i>-<j>' ---
    if market_name == 'exact_score':
        if '-' not in selection:
            return None
        try:
            i, j = selection.split('-')
            return (home_goals == int(i)) and (away_goals == int(j))
        except ValueError:
            return None

    # --- Goal intervals ---
    if market_name == 'goal_intervals':
        if selection == '0-2':
            return total <= 2
        if selection == '3-4':
            return 3 <= total <= 4
        if selection == '5-6':
            return 5 <= total <= 6
        if selection == '7-8':
            return 7 <= total <= 8
        if selection == '9+':
            return total >= 9
        return None

    return None


# ===================================================================
# Reconstruction du test set
# ===================================================================

def build_test_df(config_path: str) -> pd.DataFrame:
    """Reconstruit le test set avec le même pipeline que train.py."""
    config = load_config(config_path, validate=False)
    paths = config.get('paths', {})
    split_cfg = config.get('data_split', {})
    elo_cfg = config.get('features', {}).get('elo', {})

    loader = NHLDataLoader(
        data_dir=paths.get('data_dir', 'data'),
        filename=paths.get('dataset_filename', 'dataset_agrege_vizer_nhl.csv'),
    )
    df = loader.load(
        exclude_anomalous_seasons=split_cfg.get('exclude_anomalous_seasons', True),
        excluded_years=tuple(split_cfg.get('excluded_years', [2013, 2020])),
    )
    engineer = NHLFeatureEngineer(
        elo_k=elo_cfg.get('k', 20.0),
        elo_home_bonus=elo_cfg.get('home_bonus', 35.0),
        elo_base=elo_cfg.get('base', 1500.0),
        verbose=False,
    )
    df_eng = engineer.fit_transform(df)

    train_until = split_cfg.get('train_until_year')
    test_year = split_cfg.get('test_year')
    if train_until is None:
        max_year = int(df_eng['gameDate_home'].dt.year.max())
        train_until = max_year - 1
        test_year = max_year
    _, test_df = loader.split_chronological(
        df_eng, train_until_year=train_until, test_year=test_year
    )
    return test_df


def main():
    parser = argparse.ArgumentParser(description="Backtest NHL")
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--model', default='models/nhl_model.pkl')
    parser.add_argument('--mode', choices=['calibration', 'synthetic', 'calibrated', 'csv'],
                        default='calibrated')
    parser.add_argument('--odds-csv', default=None)
    parser.add_argument('--bankroll', type=float, default=1000.0)
    parser.add_argument('--max-bet', type=float, default=0.03)
    parser.add_argument('--edge', type=float, default=None)
    parser.add_argument('--kelly-factor', type=float, default=None)
    parser.add_argument('--stop-loss', type=float, default=None)
    parser.add_argument('--stake-mode', choices=['kelly_initial', 'kelly_current', 'flat'],
                        default='kelly_initial')
    parser.add_argument('--edge-cap', type=float, default=0.25)
    parser.add_argument('--markets', nargs='*', default=None)
    parser.add_argument('--export-bets', default=None)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    print("=" * 70)
    print("🏒 BACKTEST NHL")
    print("=" * 70)
    print(f"Modèle : {args.model}  |  Mode : {args.mode}  |  Bankroll : {args.bankroll:.0f}")

    if not Path(args.model).exists():
        print(f"\n❌ Modèle introuvable : {args.model}\n   Lancer 'python train.py' d'abord.")
        return 1

    print("\n📂 Chargement du modèle...", file=sys.stderr)
    registry = ModelRegistry.load(args.model)
    print(f"  ✓ {len(registry.list_markets())} markets : {registry.list_markets()}", file=sys.stderr)

    print("📊 Reconstruction du test set...", file=sys.stderr)
    test_df = build_test_df(args.config)
    print(f"  ✓ {len(test_df):,} matchs (test)", file=sys.stderr)

    # Provider
    if args.mode == 'calibration':
        provider = NullOddsProvider()
        print("\nℹ️  Mode CALIBRATION : pas de paris, calibration seule.", file=sys.stderr)
    elif args.mode == 'synthetic':
        provider = SyntheticOddsProvider(seed=args.seed)
        print("\nℹ️  Mode SYNTHETIC : book naïf (sur-évalue le modèle).", file=sys.stderr)
    elif args.mode == 'calibrated':
        provider = CalibratedSyntheticOddsProvider(seed=args.seed)
        print("\nℹ️  Mode CALIBRATED : book réaliste (features + bruit 4%).", file=sys.stderr)
    elif args.mode == 'csv':
        if not args.odds_csv or not Path(args.odds_csv).exists():
            print("❌ --mode csv requiert --odds-csv valide", file=sys.stderr)
            return 1
        provider = CSVOddsProvider(args.odds_csv)
        print(f"\nℹ️  Mode CSV : {args.odds_csv}", file=sys.stderr)
    else:
        raise ValueError(args.mode)

    config = BacktestConfig(
        initial_bankroll=args.bankroll,
        max_bet_fraction=args.max_bet,
        edge_threshold_override=args.edge,
        kelly_factor_override=args.kelly_factor,
        stop_loss_pct=args.stop_loss,
        stake_mode=args.stake_mode,
        edge_cap=args.edge_cap,
        verbose=True,
    )
    backtester = Backtester(registry, config)
    print("\n🚀 Lancement du backtest...\n", file=sys.stderr)

    result = backtester.run(
        test_df=test_df,
        outcome_fn=outcome_fn,
        odds_provider=provider,
        markets=args.markets,
    )

    print()
    result.print_summary()

    if args.export_bets and result.bets:
        df = result.to_dataframe()
        df.to_csv(args.export_bets, index=False)
        print(f"\n💾 {len(df)} paris exportés : {args.export_bets}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
