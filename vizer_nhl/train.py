#!/usr/bin/env python
"""
train.py — Entraînement orchestré du pipeline NHL.

Workflow :
    1. Charge config.yaml
    2. Charge dataset_agrege_vizer_nhl.csv via NHLDataLoader
    3. Feature engineering (Elo + diffs + interactions)
    4. Split temporel chronologique
    5. Vérification anti-leakage (vizer_core.assert_no_leakage)
    6. Entraîne les engines nécessaires (selon les markets activés)
    7. Fit + register chaque market activé (service-backed)
    8. Sauvegarde le registre (joblib) — les engines sont sérialisés via
       les références Python détenues par les markets.

Usage :
    python train.py
    python train.py --config config.yaml --output models/nhl_model.pkl
    python train.py --markets moneyline total btts   # subset
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from vizer_core import (
    ModelRegistry, load_config, assert_no_leakage, LeakageError,
)

from src.data.loader import NHLDataLoader
from src.features.engineer import NHLFeatureEngineer
from src.models.moneyline_engine import NHLMoneylineEngine
from src.models.poisson_engine import NHLPoissonEngine
from src.models.poisson_engine_p1 import NHLPoissonEngineP1
from src.models.markets import get_market_class, MARKET_TO_SERVICE


def build_engine(service_name: str, config: dict, verbose: bool):
    """Instancie un engine à partir de sa config (sans le fit)."""
    services_cfg = config.get('services', {})
    if service_name == 'moneyline':
        ml_cfg = config['markets'].get('moneyline', {}).get('hyperparameters', {})
        return NHLMoneylineEngine(
            xgb_params=ml_cfg.get('xgb'),
            lgb_params=ml_cfg.get('lgb'),
            val_fraction=ml_cfg.get('val_fraction', 0.15),
            verbose=verbose,
        )
    if service_name == 'poisson':
        poi_cfg = services_cfg.get('poisson', {})
        return NHLPoissonEngine(
            xgb_params=poi_cfg.get('xgb'),
            val_fraction=poi_cfg.get('val_fraction', 0.15),
            early_stopping=poi_cfg.get('early_stopping', 30),
            verbose=verbose,
        )
    if service_name == 'poisson_p1':
        p1_cfg = services_cfg.get('poisson_p1', {})
        return NHLPoissonEngineP1(
            xgb_params=p1_cfg.get('xgb'),
            val_fraction=p1_cfg.get('val_fraction', 0.15),
            early_stopping=p1_cfg.get('early_stopping', 30),
            p1_ratio_fallback=p1_cfg.get('p1_ratio_fallback', 0.30),
            verbose=verbose,
        )
    raise ValueError(f"Service inconnu : {service_name}")


def main():
    parser = argparse.ArgumentParser(description="Entraînement pipeline NHL")
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--output', default=None,
                        help="Chemin de sortie du registre (défaut: depuis config)")
    parser.add_argument('--markets', nargs='*', default=None,
                        help="Subset de markets à entraîner (défaut: tous les enabled)")
    parser.add_argument('--quiet', action='store_true', help="Réduit les logs")
    args = parser.parse_args()

    verbose = not args.quiet
    t0 = time.time()

    print("=" * 70)
    print("🏒 ENTRAÎNEMENT PIPELINE NHL")
    print("=" * 70)

    # ---- 1. Config ----
    print(f"\n⚙️  Chargement config : {args.config}")
    config = load_config(args.config, validate=False)
    print(f"  ✓ Sport : {config.get('sport', 'nhl')}")

    paths = config.get('paths', {})
    data_dir = paths.get('data_dir', 'data')
    dataset_filename = paths.get('dataset_filename', 'dataset_agrege_vizer_nhl.csv')
    models_dir = paths.get('models_dir', 'models')
    model_filename = paths.get('model_filename', 'nhl_model.pkl')
    output_path = args.output or str(Path(models_dir) / model_filename)

    # Markets à entraîner
    markets_cfg = config.get('markets', {})
    if args.markets:
        active_markets = [m for m in args.markets if markets_cfg.get(m, {}).get('enabled', False)]
        skipped = [m for m in args.markets if m not in active_markets]
        if skipped:
            print(f"  ⚠️  Ignorés (non activés dans config) : {skipped}")
    else:
        active_markets = [m for m, cfg in markets_cfg.items() if cfg.get('enabled', False)]
    print(f"  ✓ Markets actifs : {active_markets}")

    # ---- 2. Loader ----
    print(f"\n📂 Chargement du dataset")
    split_cfg = config.get('data_split', {})
    loader = NHLDataLoader(data_dir=data_dir, filename=dataset_filename)
    df = loader.load(
        exclude_anomalous_seasons=split_cfg.get('exclude_anomalous_seasons', True),
        excluded_years=tuple(split_cfg.get('excluded_years', [2013, 2020])),
    )
    print(f"  ✓ {len(df):,} matchs chargés")

    # ---- 3. Feature engineering ----
    print(f"\n🔧 Feature engineering")
    elo_cfg = config.get('features', {}).get('elo', {})
    engineer = NHLFeatureEngineer(
        elo_k=elo_cfg.get('k', 20.0),
        elo_home_bonus=elo_cfg.get('home_bonus', 35.0),
        elo_base=elo_cfg.get('base', 1500.0),
        verbose=verbose,
    )
    df_eng = engineer.fit_transform(df)
    features = engineer.features_used
    print(f"  ✓ {len(features)} features finales")

    # ---- 4. Split temporel ----
    print(f"\n📅 Split temporel")
    train_until = split_cfg.get('train_until_year')
    test_year = split_cfg.get('test_year')
    if train_until is None:
        # Auto : dernière année - 1
        max_year = int(df_eng['gameDate_home'].dt.year.max())
        train_until = max_year - 1
        test_year = max_year
    train_df, test_df = loader.split_chronological(
        df_eng, train_until_year=train_until, test_year=test_year
    )
    print(f"  Train : {len(train_df):,} matchs (≤ {train_until})")
    print(f"  Test  : {len(test_df):,} matchs ({test_year})")

    # ---- 5. Anti-leakage ----
    print(f"\n🛡️  Vérification anti-leakage")
    try:
        X_check = train_df.reindex(columns=features, fill_value=0)
        y_check = train_df['home_team_won']
        assert_no_leakage(X_check, y_check, threshold=0.85)
        print(f"  ✓ Aucune feature suspecte (corr < 0.85 avec home_team_won)")
    except LeakageError as e:
        print(f"  ❌ LEAKAGE détecté : {e}")
        return 1
    except Exception as e:
        print(f"  ⚠️  Vérification anti-leakage non concluante : {e}")

    # ---- 6. Entraîner les engines requis ----
    print(f"\n🎯 Entraînement des engines")
    print("=" * 70)
    required_services = {MARKET_TO_SERVICE[m] for m in active_markets}
    engines: dict[str, object] = {}

    # Ordre : poisson AVANT poisson_p1 (fallback dépend de poisson)
    order = ['moneyline', 'poisson', 'poisson_p1']
    for service_name in order:
        if service_name not in required_services:
            continue
        print(f"\n📍 Engine : {service_name}")
        print("-" * 70)
        engine = build_engine(service_name, config, verbose)
        if service_name == 'moneyline':
            engine.fit(train_df, features=features, test_df=test_df)
        elif service_name == 'poisson':
            engine.fit(train_df, features=features, test_df=test_df)
        elif service_name == 'poisson_p1':
            engine.fit(
                train_df, features=features, test_df=test_df,
                fallback_engine=engines.get('poisson'),
            )
        engines[service_name] = engine

    # ---- 7. Fit + register markets ----
    print(f"\n🎲 Entraînement des markets")
    print("=" * 70)
    registry = ModelRegistry(sport='nhl')
    for market_name in active_markets:
        market_cfg = markets_cfg[market_name]
        market = get_market_class(market_name)(market_cfg)
        try:
            metrics = market.fit(train_df, test_df, services=engines)
            registry.register(market, metrics=metrics)
            print(f"  ✓ {market_name:16s} entraîné et enregistré")
        except Exception as e:
            print(f"  ❌ {market_name:16s} échec : {type(e).__name__}: {e}")

    # ---- 8. Sauvegarde ----
    print(f"\n💾 Sauvegarde du registre")
    Path(models_dir).mkdir(parents=True, exist_ok=True)
    # Métadonnées
    registry._metadata = {
        'sport': 'nhl',
        'features_used': features,
        'features_dead': engineer.features_dead,
        'team_elos': engineer.team_elos,
        'n_games_train': len(train_df),
        'n_games_test': len(test_df),
        'train_until_year': train_until,
        'test_year': test_year,
        'p1_mode': engines['poisson_p1'].mode if 'poisson_p1' in engines else None,
        'training_duration_sec': time.time() - t0,
    }
    registry.save(output_path)
    print(f"  ✓ Registre sauvegardé : {output_path}")

    print("\n" + "=" * 70)
    print(f"✅ TERMINÉ en {time.time() - t0:.1f}s")
    print("=" * 70)
    print(registry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
