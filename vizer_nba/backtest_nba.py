#!/usr/bin/env python
"""
backtest_nba.py — Backtest des marchés NBA sur la saison de test.

Charge le registre entraîné, reconstruit les features sur la saison test,
itère sur chaque match en walk-forward, et calcule ROI / drawdown / Sharpe /
calibration par marché.

Modes :
    --mode calibration  : pas de cotes, juste calibration check + Brier
    --mode synthetic    : cotes synthétiques (book naïf vig 4.5%)  [défaut]
    --mode csv          : cotes archivées depuis --odds-csv

Exemples :
    python backtest_nba.py
    python backtest_nba.py --mode calibration
    python backtest_nba.py --mode synthetic --bankroll 5000 --edge 0.06
    python backtest_nba.py --markets total home_team_total --max-bet 0.02
    python backtest_nba.py --mode csv --odds-csv data/odds_archive.csv
    python backtest_nba.py --export-bets bets_22025.csv
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

from src.data.loader import NBADataLoader
from src.features.engineer import MatchFeatureEngineer


# ===================================================================
# outcome_fn : "la sélection a-t-elle gagné ?"
# ===================================================================

def outcome_fn(row, market_name: str, selection: str) -> bool | None:
    """
    Détermine si la sélection a gagné, étant donné une ligne historique.

    Args:
        row          : ligne du test_df (Series pandas), avec HOME_PTS/AWAY_PTS/HOME_WIN
        market_name  : nom du marché (moneyline/total/...)
        selection    : nom de la sélection (home/away/over_X/under_X)

    Returns:
        True si la sélection gagne, False sinon, None si indéterminable.
    """
    home_pts = row.get('HOME_PTS')
    away_pts = row.get('AWAY_PTS')
    if pd.isna(home_pts) or pd.isna(away_pts):
        return None

    total = home_pts + away_pts
    home_won = bool(row.get('HOME_WIN', home_pts > away_pts))

    if market_name in ('moneyline', 'win'):
        if selection == 'home':
            return home_won
        elif selection == 'away':
            return not home_won
        return None

    if market_name in ('total', 'total_poisson'):
        # selection = 'over_224.5' ou 'under_224.5'
        if '_' not in selection:
            return None
        side, line_str = selection.split('_', 1)
        line = float(line_str)
        if total == line:
            return None  # push (rare avec lignes .5 mais possible avec lignes entières)
        if side == 'over':
            return total > line
        elif side == 'under':
            return total < line
        return None

    if market_name == 'home_team_total':
        if '_' not in selection:
            return None
        side, line_str = selection.split('_', 1)
        line = float(line_str)
        if home_pts == line:
            return None
        if side == 'over':
            return home_pts > line
        elif side == 'under':
            return home_pts < line
        return None

    if market_name == 'away_team_total':
        if '_' not in selection:
            return None
        side, line_str = selection.split('_', 1)
        line = float(line_str)
        if away_pts == line:
            return None
        if side == 'over':
            return away_pts > line
        elif side == 'under':
            return away_pts < line
        return None

    return None


# ===================================================================
# Pipeline principal
# ===================================================================

def build_test_df(config_path: str = 'config.yaml') -> pd.DataFrame:
    """
    Reconstruit le DataFrame de test avec exactement le même pipeline que train.py.
    """
    config = load_config(config_path)
    loader = NBADataLoader()
    games = loader.load_games()
    try:
        player_games = loader.load_player_games()
    except Exception:
        player_games = None

    engineer = MatchFeatureEngineer(windows=config['features']['rolling_windows'])
    features_df = engineer.create_features(
        games,
        player_games_df=player_games,
        include_h2h=False,
    )
    features_df['TOTAL_PTS'] = features_df['HOME_PTS'] + features_df['AWAY_PTS']

    test_season = config['data_split']['test_season']
    test_df = features_df[features_df['SEASON_ID'] == test_season].copy()
    return test_df


def main():
    parser = argparse.ArgumentParser(
        description="Backtest walk-forward des marchés NBA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--config', default='config.yaml',
                        help='Chemin du config.yaml (défaut: config.yaml)')
    parser.add_argument('--model', default='models/nba_model.pkl',
                        help='Chemin du registre (défaut: models/nba_model.pkl)')
    parser.add_argument('--mode', choices=['calibration', 'synthetic', 'calibrated', 'csv'],
                        default='calibrated',
                        help='Mode de backtest (défaut: calibrated)\n'
                             '  calibration : pas de paris, juste Brier + calibration\n'
                             '  synthetic   : book naïf (baseline league) — sur-évalue le modèle\n'
                             '  calibrated  : book réaliste (voit les features + bruit) — RECOMMANDÉ\n'
                             '  csv         : cotes archivées depuis --odds-csv')
    parser.add_argument('--odds-csv', default=None,
                        help='CSV de cotes archivées (requis si --mode csv)')
    parser.add_argument('--bankroll', type=float, default=1000.0,
                        help='Bankroll initial (défaut: 1000)')
    parser.add_argument('--max-bet', type=float, default=0.03,
                        help='Cap dur sur la mise Kelly en fraction du bankroll (défaut: 0.03)')
    parser.add_argument('--edge', type=float, default=None,
                        help='Edge threshold override (sinon: défaut du market)')
    parser.add_argument('--kelly-factor', type=float, default=None,
                        help='Kelly factor override (sinon: défaut du market)')
    parser.add_argument('--stop-loss', type=float, default=None,
                        help='Arrête si drawdown >= X (ex: 0.30 = 30%%)')
    parser.add_argument('--markets', nargs='*', default=None,
                        help='Liste des marchés à backtester (défaut: tous activés)')
    parser.add_argument('--export-bets', default=None,
                        help='Exporter les paris en CSV (chemin de sortie)')
    parser.add_argument('--stake-mode', choices=['kelly_initial', 'kelly_current', 'flat'],
                        default='kelly_initial',
                        help='Mode de mise (défaut: kelly_initial = unités fixes RÉALISTE)\n'
                             '  kelly_initial : mise = bankroll INITIAL × kelly_fraction (recommandé)\n'
                             '  kelly_current : mise = bankroll COURANT × kelly_fraction (compound, R&D)\n'
                             '  flat          : mise constante = bankroll initial × max_bet')
    parser.add_argument('--edge-cap', type=float, default=0.25,
                        help='Skip les paris avec edge > X (sanity, défaut: 0.25)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Seed RNG pour cotes synthétiques (défaut: 42)')

    args = parser.parse_args()

    print("=" * 70)
    print("🔁 BACKTEST NBA")
    print("=" * 70)
    print(f"Modèle    : {args.model}")
    print(f"Mode      : {args.mode}")
    print(f"Bankroll  : {args.bankroll:.2f}")
    print(f"Max bet   : {args.max_bet * 100:.1f}%")
    if args.edge is not None:
        print(f"Edge      : {args.edge} (override)")
    print()

    # 1. Charger le registre
    print("📂 Chargement du modèle...", file=sys.stderr)
    if not Path(args.model).exists():
        print(f"❌ Modèle introuvable : {args.model}", file=sys.stderr)
        print(f"   Lancer 'python train.py' d'abord.", file=sys.stderr)
        return 1
    registry = ModelRegistry.load(args.model)
    print(f"  ✓ {len(registry.list_markets())} marché(s) chargé(s) : {registry.list_markets()}",
          file=sys.stderr)

    # 2. Reconstruire test_df
    print("\n📊 Reconstruction du test set...", file=sys.stderr)
    test_df = build_test_df(args.config)
    print(f"  ✓ {len(test_df):,} matchs (saison test)", file=sys.stderr)

    # 3. Provider de cotes
    if args.mode == 'calibration':
        provider = NullOddsProvider()
        print(f"\nℹ️  Mode CALIBRATION : pas de paris, juste check des probas.",
              file=sys.stderr)
    elif args.mode == 'synthetic':
        provider = SyntheticOddsProvider(seed=args.seed)
        print(f"\nℹ️  Mode SYNTHETIC : book naïf (baseline league + bruit, vig 4.5%).",
              file=sys.stderr)
        print(f"   ⚠️  Ce mode SUR-ÉVALUE le modèle (book trop simpliste).",
              file=sys.stderr)
    elif args.mode == 'calibrated':
        provider = CalibratedSyntheticOddsProvider(seed=args.seed)
        print(f"\nℹ️  Mode CALIBRATED : book réaliste (voit features + bruit 4%, vig 4.5%).",
              file=sys.stderr)
        print(f"   Ce mode simule un book moyennement informé. Plus juste que --synthetic.",
              file=sys.stderr)
    elif args.mode == 'csv':
        if not args.odds_csv:
            print("❌ --mode csv requiert --odds-csv", file=sys.stderr)
            return 1
        if not Path(args.odds_csv).exists():
            print(f"❌ CSV introuvable : {args.odds_csv}", file=sys.stderr)
            return 1
        provider = CSVOddsProvider(args.odds_csv)
        print(f"\nℹ️  Mode CSV : cotes archivées {args.odds_csv}", file=sys.stderr)
    else:
        raise ValueError(f"Mode inconnu : {args.mode}")

    # 4. Lancer le backtester
    config = BacktestConfig(
        initial_bankroll=args.bankroll,
        max_bet_fraction=args.max_bet,
        edge_threshold_override=args.edge,
        kelly_factor_override=args.kelly_factor,
        stop_loss_pct=args.stop_loss,
        verbose=True,
        stake_mode=args.stake_mode,
        edge_cap=args.edge_cap,
    )
    backtester = Backtester(registry, config)
    print(f"\n🚀 Lancement du backtest...\n", file=sys.stderr)

    result = backtester.run(
        test_df=test_df,
        outcome_fn=outcome_fn,
        odds_provider=provider,
        markets=args.markets,
    )

    # 5. Affichage rapport
    print()
    result.print_summary()

    # 6. Export CSV
    if args.export_bets and result.bets:
        df = result.to_dataframe()
        df.to_csv(args.export_bets, index=False)
        print(f"\n💾 {len(df)} paris exportés : {args.export_bets}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
