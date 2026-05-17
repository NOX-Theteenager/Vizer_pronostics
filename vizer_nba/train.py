#!/usr/bin/env python
"""
Script d'entraînement unifié pour tous les modèles NBA.

Architecture (post-étape 3a) :
1. Charge config.yaml (chemins, hyperparamètres, marchés actifs, split).
2. Charge les données.
3. Feature engineering.
4. Split temporel par saison (lu depuis config).
5. Vérification anti-leakage avant chaque fit.
6. Pour chaque marché activé dans config, instancie le Market correspondant,
   l'entraîne, l'enregistre dans vizer_core.ModelRegistry.
7. Sauvegarde le registre unifié au chemin défini par config.

Tout paramètre vient de config.yaml. Aucune valeur hardcodée.
"""
import sys
import time
from datetime import datetime
import pandas as pd

from vizer_core import (
    load_config,
    assert_no_leakage,
    LeakageError,
    ModelRegistry,
)
from vizer_core.utils.leakage_check import report_top_correlations

from src.data.loader import NBADataLoader
from src.features.engineer import MatchFeatureEngineer
from src.models.win_predictor import NBAMatchPredictor      # gardé pour anti-leakage probe
from src.models.markets import get_market_class             # NOUVEAU


# Features autorisées à être très corrélées (allowlist anti-leakage).
LEAKAGE_ALLOWLIST: list[str] = []

# Seuil de corrélation jugé suspect.
LEAKAGE_THRESHOLD: float = 0.85


def main(config_path: str = 'config.yaml') -> int:
    start_time = time.time()

    print("=" * 70)
    print("🏀 ENTRAÎNEMENT UNIFIÉ DES MODÈLES NBA (architecture MarketBase)")
    print("=" * 70)
    print(f"Démarré le : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ─── 0. CONFIG ──────────────────────────────────────────────────────────
    print(f"⚙️  Chargement de la configuration : {config_path}")
    print("-" * 70)
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"  ✗ {e}")
        return 1

    enabled_markets = [m for m, c in config['markets'].items() if c.get('enabled')]
    print(f"  ✓ Sport         : {config['sport']}")
    print(f"  ✓ Train seasons : {config['data_split']['train_season_start']} → {config['data_split']['train_season_end']}")
    print(f"  ✓ Test season   : {config['data_split']['test_season']}")
    print(f"  ✓ Marchés actifs: {enabled_markets}")
    print()

    # ─── 1. DONNÉES ─────────────────────────────────────────────────────────
    print("📂 Étape 1/6 : Chargement des données")
    print("-" * 70)
    try:
        loader = NBADataLoader()
        games = loader.load_games()
        player_games = pd.read_csv(config['data']['paths']['player_games'])
        print(f"  ✓ {len(games):,} matchs chargés")
        print(f"  ✓ {len(player_games):,} lignes joueurs chargées")
    except Exception as e:
        print(f"  ✗ {e}")
        return 1
    print()

    # ─── 2. FEATURE ENGINEERING ─────────────────────────────────────────────
    print("🔧 Étape 2/6 : Feature Engineering")
    print("-" * 70)
    try:
        engineer = MatchFeatureEngineer(windows=config['features']['rolling_windows'])
        features_df = engineer.create_features(
            games,
            player_games_df=player_games,
            include_h2h=config['features'].get('include_h2h', False),
        )
        features_df['TOTAL_PTS'] = features_df['HOME_PTS'] + features_df['AWAY_PTS']
        print(f"  ✓ Features prêtes pour {len(features_df):,} matchs")
    except Exception as e:
        print(f"  ✗ {e}")
        return 1
    print()

    # ─── 3. SPLIT ───────────────────────────────────────────────────────────
    print("📊 Étape 3/6 : Split temporel")
    print("-" * 70)
    train_start = config['data_split']['train_season_start']
    train_end = config['data_split']['train_season_end']
    test_season = config['data_split']['test_season']

    train_df = features_df[
        (features_df['SEASON_ID'] >= train_start)
        & (features_df['SEASON_ID'] <= train_end)
    ].copy()
    test_df = features_df[features_df['SEASON_ID'] == test_season].copy()
    print(f"  Train : {len(train_df):,} matchs ({train_start} → {train_end})")
    print(f"  Test  : {len(test_df):,} matchs ({test_season})")
    print()

    # ─── 4. ANTI-LEAKAGE ────────────────────────────────────────────────────
    print("🛡️  Étape 4/6 : Vérification anti-leakage")
    print("-" * 70)
    if any(m in enabled_markets for m in ('win', 'moneyline')):
        _probe = NBAMatchPredictor()
        X_check, y_check = _probe.prepare_features(train_df)
        print(f"  Vérification sur {len(X_check.columns)} features × {len(X_check):,} lignes (target=HOME_WIN)")
        top = report_top_correlations(X_check, y_check, top_n=5)
        print("  Top 5 corrélations |feature ↔ HOME_WIN| :")
        for _, row in top.iterrows():
            print(f"    - {row['feature']:40s} {row['abs_correlation']:.4f}")
        try:
            assert_no_leakage(X_check, y_check, threshold=LEAKAGE_THRESHOLD, allowlist=LEAKAGE_ALLOWLIST)
            print(f"  ✓ Aucune feature ne dépasse {LEAKAGE_THRESHOLD}")
        except LeakageError as e:
            print(str(e))
            if not config['training'].get('continue_on_error', False):
                return 1
            print("  ⚠️  continue_on_error=true → on continue.")
    else:
        print("  ⊘ Aucun marché classification activé : check sauté.")
    print()

    # ─── 5. ENTRAÎNEMENT DES MARCHÉS ────────────────────────────────────────
    print("🎯 Étape 5/6 : Entraînement des marchés")
    print("=" * 70)

    registry = ModelRegistry(sport='nba')
    trained: list[str] = []
    failed: list[tuple[str, str]] = []

    for market_name in enabled_markets:
        market_cfg = config['markets'][market_name]
        print()
        print(f"📍 Marché : '{market_name}'")
        print("-" * 70)
        try:
            MarketClass = get_market_class(market_name)
        except KeyError as e:
            print(f"  ⚠️  {e}")
            print(f"     Marché activé dans config mais sans implémentation. Sauté.")
            failed.append((market_name, "pas d'implémentation"))
            continue

        try:
            market = MarketClass(market_cfg)
            metrics = market.fit(train_df, test_df, verbose=True)
            registry.register(market, metrics=metrics)
            trained.append(market_name)
            print(f"  ✓ Marché '{market_name}' entraîné et enregistré")
        except Exception as e:
            print(f"  ✗ Échec : {e}")
            import traceback
            traceback.print_exc()
            failed.append((market_name, str(e)))
            if not config['training'].get('continue_on_error', False):
                return 1

    # ─── 6. SAUVEGARDE ──────────────────────────────────────────────────────
    print()
    print("💾 Étape 6/6 : Sauvegarde du registre")
    print("-" * 70)
    duration = time.time() - start_time

    registry.set_metadata('training_duration_sec', duration)
    registry.set_metadata('n_games_train', len(train_df))
    registry.set_metadata('n_games_test', len(test_df))
    registry.set_metadata('train_seasons', f"{train_start}-{train_end}")
    registry.set_metadata('test_season', str(test_season))
    registry.set_metadata('models_trained', trained)
    registry.set_metadata('models_failed', [m for m, _ in failed])
    registry.set_metadata('config_path', config_path)

    # Metadata pour le calcul du talent_ratio à l'inférence (UnifiedPredictor)
    try:
        player_df = engineer.calculate_player_values(player_games)
        if 'Game_ID' in player_df.columns:
            player_df = player_df.rename(columns={'Game_ID': 'GAME_ID'})

        # Dernière valeur de PLAYER_VAL_AVG_10G par joueur
        latest_player_vals = (
            player_df.sort_values('GAME_DATE')
            .groupby('Player_ID').last()['PLAYER_VAL_AVG_10G']
            .to_dict()
        )

        # Baseline médian de talent par équipe : on a besoin de TEAM_ID, qui n'est
        # pas dans player_games — on le récupère via games (jointure sur GAME_ID).
        game_teams = games[['GAME_ID', 'TEAM_ID']].drop_duplicates()
        temp_player = player_df.merge(game_teams, on='GAME_ID', how='inner')
        # Note: TEAM_ID ici est celui des matchs joués par chaque joueur, donc
        # un joueur peut "appartenir" à plusieurs équipes si transféré. C'est OK :
        # la baseline est calculée par équipe, on somme tous les joueurs ayant
        # joué pour elle.
        team_talent = (
            temp_player.groupby(['GAME_ID', 'TEAM_ID'])['PLAYER_VAL_AVG_10G']
            .sum().reset_index()
        )
        team_baselines = (
            team_talent.groupby('TEAM_ID')['PLAYER_VAL_AVG_10G']
            .median().to_dict()
        )

        # Mapping nom <-> Player_ID
        try:
            players_meta = pd.read_csv(config['data']['paths']['players'])
            player_id_to_name = players_meta.set_index('id')['full_name'].to_dict()
            name_to_player_id = {n: pid for pid, n in player_id_to_name.items()}
            registry.set_metadata('player_id_to_name', player_id_to_name)
            registry.set_metadata('name_to_player_id', name_to_player_id)
        except Exception as e:
            print(f"  ⚠️ NBA_PLAYERS.csv illisible ({e}) — pas de mapping nom↔ID stocké.")

        registry.set_metadata('player_values', latest_player_vals)
        registry.set_metadata('team_baselines', team_baselines)
        print(f"  ✓ Metadata talent_ratio : {len(latest_player_vals)} joueurs, "
              f"{len(team_baselines)} équipes")
    except Exception as e:
        print(f"  ⚠️ Metadata talent_ratio non enregistrées ({e}) — "
              f"talent_ratio sera 1.0 par défaut à l'inférence.")

    output_path = config['models']['output_path']
    registry.save(output_path)
    print(f"  ✓ Registre sauvegardé : {output_path}")

    # ─── RÉSUMÉ ─────────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("✅ TERMINÉ" if not failed else "⚠️  TERMINÉ (avec erreurs)")
    print("=" * 70)
    registry.print_summary()
    if failed:
        print()
        print("⚠ MARCHÉS ÉCHOUÉS")
        print("-" * 70)
        for name, err in failed:
            print(f"  - {name}: {err}")
    print(f"\nDurée totale : {duration:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Entraînement NBA via MarketBase + config.yaml")
    parser.add_argument('-c', '--config', default='config.yaml')
    args = parser.parse_args()
    sys.exit(main(config_path=args.config))
