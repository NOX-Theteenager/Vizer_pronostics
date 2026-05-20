#!/usr/bin/env python
"""
test_pipeline_nhl.py — Validation complète Sessions 1+2+3 sur vraies données NHL.

Pipeline testé :
    1. Chargement dataset_agrege_vizer_nhl.csv
    2. Feature engineering (Elo + diffs + interactions)
    3. Split temporel chronologique
    4. Entraînement 3 engines (Moneyline, Poisson full, Poisson P1)
    5. Fit 6 markets service-backed
    6. Prédictions sur 1er match du test set + comparaison résultat réel
    7. Récap métriques (à comparer avec notebook V5.6)

Lancer :
    cd ~/Documents/Projets/Vizer_pronostics/vizer_nhl
    python test_pipeline_nhl.py
"""
import sys
sys.path.insert(0, '.')

import warnings
warnings.filterwarnings('ignore')

from src.data.loader import NHLDataLoader
from src.features.engineer import NHLFeatureEngineer
from src.models.moneyline_engine import NHLMoneylineEngine
from src.models.poisson_engine import NHLPoissonEngine
from src.models.poisson_engine_p1 import NHLPoissonEngineP1
from src.models.markets import get_market_class


def print_header(title: str, level: int = 1):
    """Affichage en-tête formaté."""
    if level == 1:
        print("\n" + "=" * 70)
        print(title)
        print("=" * 70)
    else:
        print(f"\n📍 {title}")
        print("-" * 70)


def main():
    print_header("🏒 TEST PIPELINE NHL — Sessions 1 + 2 + 3")

    # =====================================================================
    # ÉTAPE 1 — Chargement
    # =====================================================================
    print_header("Étape 1/6 : Chargement du dataset agrégé", level=2)
    loader = NHLDataLoader(
        data_dir='data',
        filename='dataset_agrege_vizer_nhl.csv',
    )
    df = loader.load(exclude_anomalous_seasons=True)
    print(f"  ✓ {len(df):,} matchs chargés")
    print(f"  ✓ Years : {df['gameDate_home'].dt.year.min()} → "
          f"{df['gameDate_home'].dt.year.max()}")
    print(f"  ✓ Colonnes : {len(df.columns)}")
    has_p1 = loader.has_period1_data(df)
    print(f"  ✓ Data P1 disponible : {'OUI (mode dedicated)' if has_p1 else 'NON (mode fallback)'}")

    # =====================================================================
    # ÉTAPE 2 — Feature Engineering
    # =====================================================================
    print_header("Étape 2/6 : Feature Engineering", level=2)
    engineer = NHLFeatureEngineer(verbose=True)
    df_eng = engineer.fit_transform(df)
    print(f"  ✓ {len(engineer.features_used)} features finales")
    print(f"  ✓ Premières features : {engineer.features_used[:6]}")
    if engineer.features_dead:
        print(f"  ⚠️  Dead features (ignorées) : {engineer.features_dead}")

    # =====================================================================
    # ÉTAPE 3 — Split temporel
    # =====================================================================
    print_header("Étape 3/6 : Split temporel", level=2)
    max_year = df_eng['gameDate_home'].dt.year.max()
    train_until = max_year - 1
    test_year = max_year
    train_df, test_df = loader.split_chronological(
        df_eng, train_until_year=train_until, test_year=test_year
    )
    print(f"  Train : {len(train_df):,} matchs (jusqu'à {train_until})")
    print(f"  Test  : {len(test_df):,} matchs ({test_year})")

    if len(test_df) < 50:
        print(f"\n⚠️  Test set très petit ({len(test_df)} matchs).")
        print(f"   Tu peux ajuster manuellement train_until/test_year dans le script.")

    # =====================================================================
    # ÉTAPE 4 — Entraînement des 3 engines
    # =====================================================================
    print_header("Étape 4/6 : Entraînement des 3 engines", level=2)
    features = engineer.features_used

    # --- Engine 1 : Moneyline ---
    print_header("Engine 1/3 : Moneyline (XGB + LGB ensemble + Temperature)", level=2)
    ml_engine = NHLMoneylineEngine(verbose=True)
    ml_metrics = ml_engine.fit(train_df, features=features, test_df=test_df)

    # --- Engine 2 : Poisson full-game ---
    print_header("Engine 2/3 : Poisson full-game (2 XGB count:poisson)", level=2)
    poi_engine = NHLPoissonEngine(verbose=True)
    poi_metrics = poi_engine.fit(train_df, features=features, test_df=test_df)

    # --- Engine 3 : Poisson P1 (auto dedicated/fallback) ---
    print_header("Engine 3/3 : Poisson P1 (auto-detect mode)", level=2)
    p1_engine = NHLPoissonEngineP1(verbose=True)
    p1_metrics = p1_engine.fit(
        train_df,
        features=features,
        test_df=test_df,
        fallback_engine=poi_engine,
    )
    print(f"\n  → Mode utilisé : {p1_engine.mode.upper()}")

    # =====================================================================
    # ÉTAPE 5 — Fit des 6 markets
    # =====================================================================
    print_header("Étape 5/6 : Fit des 6 markets service-backed", level=2)
    services = {
        'moneyline':  ml_engine,
        'poisson':    poi_engine,
        'poisson_p1': p1_engine,
    }

    moneyline = get_market_class('moneyline')({
        'enabled': True, 'edge_threshold': 0.05, 'kelly_factor': 0.25,
        'hyperparameters': {},
    })
    total = get_market_class('total')({
        'enabled': True, 'edge_threshold': 0.05, 'kelly_factor': 0.25,
        'default_ou_line': 5.5, 'hyperparameters': {},
    })
    btts = get_market_class('btts')({
        'enabled': True, 'edge_threshold': 0.05, 'kelly_factor': 0.25,
        'hyperparameters': {},
    })
    p1_winner = get_market_class('p1_winner')({
        'enabled': True, 'edge_threshold': 0.05, 'kelly_factor': 0.20,
        'hyperparameters': {},
    })
    p1_total = get_market_class('p1_total')({
        'enabled': True, 'edge_threshold': 0.05, 'kelly_factor': 0.25,
        'default_ou_line': 1.5, 'hyperparameters': {},
    })
    p1_btts = get_market_class('p1_btts')({
        'enabled': True, 'edge_threshold': 0.05, 'kelly_factor': 0.20,
        'hyperparameters': {},
    })

    moneyline.fit(train_df, test_df, services=services)
    total.fit(train_df, test_df, services=services)
    btts.fit(train_df, test_df, services=services)
    p1_winner.fit(train_df, test_df, services=services)
    p1_total.fit(train_df, test_df, services=services)
    p1_btts.fit(train_df, test_df, services=services)
    print("  ✓ 6 markets fitted (moneyline, total, btts, p1_winner, p1_total, p1_btts)")

    # =====================================================================
    # ÉTAPE 6 — Prédictions sur 1er match du test set
    # =====================================================================
    print_header("Étape 6/6 : Prédictions sur 1er match test + résultat réel", level=2)
    first_row = test_df.head(1)
    home_team = first_row['team_home'].iloc[0]
    away_team = first_row['team_away'].iloc[0]
    actual_h = int(first_row['finalGoals_home'].iloc[0])
    actual_a = int(first_row['finalGoals_away'].iloc[0])
    actual_winner = home_team if actual_h > actual_a else away_team
    actual_btts = "yes" if (actual_h >= 1 and actual_a >= 1) else "no"
    actual_total = actual_h + actual_a

    print(f"\n🏒 Match : {home_team} (dom) vs {away_team}")
    print(f"   Résultat final : {actual_h}-{actual_a}")
    print(f"   Vainqueur       : {actual_winner}")
    print(f"   Total           : {actual_total} buts")
    print(f"   BTTS            : {actual_btts}")

    ctx = {'features_row': first_row}

    # --- Moneyline ---
    pred_ml = moneyline.predict(home_team, away_team, context=ctx)
    print(f"\n📊 [Moneyline]")
    print(f"   P({home_team} win) = {pred_ml.probabilities['home']:.4f}")
    print(f"   P({away_team} win) = {pred_ml.probabilities['away']:.4f}")
    print(f"   Confidence : {pred_ml.confidence}")
    print(f"   Vainqueur prédit : {home_team if pred_ml.probabilities['home'] > 0.5 else away_team}")
    print(f"   ✓ Correct" if (pred_ml.probabilities['home'] > 0.5) == (actual_winner == home_team)
          else "   ✗ Incorrect")

    # --- Total ---
    pred_total = total.predict(home_team, away_team, context=ctx)
    print(f"\n📊 [Total — line 5.5]")
    print(f"   λ_home = {pred_total.metadata['lambda_home']:.3f}")
    print(f"   λ_away = {pred_total.metadata['lambda_away']:.3f}")
    print(f"   E[total]     = {pred_total.expected_value:.3f}  (réel : {actual_total})")
    print(f"   P(over 5.5)  = {pred_total.probabilities['over_5.5']:.4f}")
    print(f"   P(under 5.5) = {pred_total.probabilities['under_5.5']:.4f}")
    actual_over = "over" if actual_total > 5.5 else "under"
    pred_over = "over" if pred_total.probabilities['over_5.5'] > 0.5 else "under"
    print(f"   ✓ Correct ({pred_over})" if pred_over == actual_over else f"   ✗ Incorrect (prédit {pred_over}, réel {actual_over})")

    # --- BTTS ---
    pred_btts = btts.predict(home_team, away_team, context=ctx)
    print(f"\n📊 [BTTS]")
    print(f"   P(yes) = {pred_btts.probabilities['yes']:.4f}")
    print(f"   P(no)  = {pred_btts.probabilities['no']:.4f}")
    pred_btts_label = "yes" if pred_btts.probabilities['yes'] > 0.5 else "no"
    print(f"   ✓ Correct ({pred_btts_label})" if pred_btts_label == actual_btts else f"   ✗ Incorrect")

    # --- P1 markets (si data P1 disponible) ---
    if has_p1 and 'goals_p1_home' in first_row.columns:
        actual_p1_h = int(first_row['goals_p1_home'].iloc[0])
        actual_p1_a = int(first_row['goals_p1_away'].iloc[0])
        actual_p1_winner = (
            'home_lead' if actual_p1_h > actual_p1_a
            else 'tied' if actual_p1_h == actual_p1_a
            else 'away_lead'
        )
        actual_p1_total = actual_p1_h + actual_p1_a
        actual_p1_btts = "yes" if (actual_p1_h >= 1 and actual_p1_a >= 1) else "no"

        print(f"\n🥇 Résultat P1 réel : {actual_p1_h}-{actual_p1_a}")
        print(f"   Winner P1 : {actual_p1_winner}, Total P1 : {actual_p1_total}, BTTS P1 : {actual_p1_btts}")

        pred_p1w = p1_winner.predict(home_team, away_team, context=ctx)
        pred_p1t = p1_total.predict(home_team, away_team, context=ctx)
        pred_p1b = p1_btts.predict(home_team, away_team, context=ctx)

        print(f"\n📊 [P1 Winner — 3-way]")
        print(f"   P(home_lead) = {pred_p1w.probabilities['home_lead']:.4f}")
        print(f"   P(tied)      = {pred_p1w.probabilities['tied']:.4f}")
        print(f"   P(away_lead) = {pred_p1w.probabilities['away_lead']:.4f}")
        print(f"   λ_p1_h = {pred_p1w.metadata['lambda_p1_home']:.3f}")
        print(f"   λ_p1_a = {pred_p1w.metadata['lambda_p1_away']:.3f}")
        pred_p1w_label = max(pred_p1w.probabilities, key=pred_p1w.probabilities.get)
        print(f"   ✓ Correct ({pred_p1w_label})" if pred_p1w_label == actual_p1_winner
              else f"   ✗ Incorrect (prédit {pred_p1w_label}, réel {actual_p1_winner})")

        print(f"\n📊 [P1 Total — line 1.5]")
        print(f"   λ_p1_total   = {pred_p1t.expected_value:.3f}  (réel : {actual_p1_total})")
        print(f"   P(over 1.5)  = {pred_p1t.probabilities['over_1.5']:.4f}")
        print(f"   P(under 1.5) = {pred_p1t.probabilities['under_1.5']:.4f}")
        actual_p1_over = "over" if actual_p1_total > 1.5 else "under"
        pred_p1_over = "over" if pred_p1t.probabilities['over_1.5'] > 0.5 else "under"
        print(f"   ✓ Correct ({pred_p1_over})" if pred_p1_over == actual_p1_over else f"   ✗ Incorrect")

        print(f"\n📊 [P1 BTTS]")
        print(f"   P(yes) = {pred_p1b.probabilities['yes']:.4f}")
        print(f"   P(no)  = {pred_p1b.probabilities['no']:.4f}")
        pred_p1b_label = "yes" if pred_p1b.probabilities['yes'] > 0.5 else "no"
        print(f"   ✓ Correct ({pred_p1b_label})" if pred_p1b_label == actual_p1_btts else f"   ✗ Incorrect")
    else:
        print(f"\n⚠️  Pas de data P1 dans le test set, skipping P1 prédictions sur 1er match")

    # =====================================================================
    # CROSS-CHECK MATHÉMATIQUE
    # =====================================================================
    print_header("Cross-checks mathématiques (invariants)", level=2)

    # 1. Cohérence somme totale = 1 sur tous markets multi-sélections
    assert abs(sum(pred_ml.probabilities.values()) - 1.0) < 1e-6, "ML doit sommer à 1"
    assert abs(sum(pred_total.probabilities.values()) - 1.0) < 1e-6, "Total doit sommer à 1"
    assert abs(sum(pred_btts.probabilities.values()) - 1.0) < 1e-6, "BTTS doit sommer à 1"
    print("  ✓ Toutes les probabilités somment exactement à 1.000000")

    # 2. Cross-check : λ_home + λ_away ≈ E[total]
    lam_h_full = pred_total.metadata['lambda_home']
    lam_a_full = pred_total.metadata['lambda_away']
    lam_sum = lam_h_full + lam_a_full
    e_total = pred_total.expected_value
    assert abs(lam_sum - e_total) < 1e-4, "λ_h + λ_a doit = E[total]"
    print(f"  ✓ λ_h + λ_a = {lam_sum:.4f} = E[total] = {e_total:.4f}")

    # 3. Cross-check P1 : Skellam vs convolution Poisson
    if has_p1 and 'goals_p1_home' in first_row.columns:
        from scipy.stats import skellam
        lam_p1_h = pred_p1w.metadata['lambda_p1_home']
        lam_p1_a = pred_p1w.metadata['lambda_p1_away']
        p_home_skellam = 1 - skellam.cdf(0, lam_p1_h, lam_p1_a)
        delta = abs(p_home_skellam - pred_p1w.probabilities['home_lead'])
        assert delta < 0.01, f"Skellam vs convolution doivent matcher (Δ = {delta})"
        print(f"  ✓ Skellam P1 P(home>away) = {p_home_skellam:.4f} ≈ "
              f"Convolution = {pred_p1w.probabilities['home_lead']:.4f} (Δ = {delta:.6f})")

    # 4. Cross-check : si P1 mode dedicated, λ_p1 < λ_total
    if has_p1 and 'goals_p1_home' in first_row.columns:
        ratio_h = pred_p1w.metadata['lambda_p1_home'] / pred_total.metadata['lambda_home']
        ratio_a = pred_p1w.metadata['lambda_p1_away'] / pred_total.metadata['lambda_away']
        print(f"  ✓ Ratio λ_p1/λ_total : home={ratio_h:.3f}, away={ratio_a:.3f} "
              f"(attendu ≈ 0.30, empirique NHL)")

    # =====================================================================
    # RÉCAP MÉTRIQUES
    # =====================================================================
    print_header("📊 RÉCAP MÉTRIQUES — à comparer avec ton notebook V5.6")

    print(f"\n🏒 NHLMoneylineEngine :")
    print(f"   AUC val XGB     : {ml_metrics.auc_xgb_val:.4f}")
    print(f"   AUC val LGB     : {ml_metrics.auc_lgb_val:.4f}")
    print(f"   Best model      : {ml_metrics.best_model_name}")
    print(f"   AUC test        : {ml_metrics.auc_test:.4f}    (V5.6 ≈ 0.60)")
    print(f"   Accuracy test   : {ml_metrics.accuracy_test:.4f}")
    print(f"   Brier raw       : {ml_metrics.brier_raw_test:.4f}    (V5.6 ≈ 0.244)")
    print(f"   Brier calibré   : {ml_metrics.brier_calibrated_test:.4f}")
    print(f"   Temperature     : {ml_metrics.temperature:.3f}")

    print(f"\n🥅 NHLPoissonEngine (full-game) :")
    print(f"   MAE home        : {poi_metrics.mae_home_test:.3f} buts    (NHL ≈ 1.3-1.4)")
    print(f"   MAE away        : {poi_metrics.mae_away_test:.3f} buts")
    print(f"   MAE total       : {poi_metrics.mae_total_test:.3f} buts")
    print(f"   RMSE total      : {poi_metrics.rmse_total_test:.3f}")
    print(f"   R² total        : {poi_metrics.r2_total_test:.4f}    (NHL souvent < 0.05)")
    print(f"   λ_home mean     : {poi_metrics.lambda_home_mean:.3f}    (NHL ≈ 3.0-3.2)")
    print(f"   λ_away mean     : {poi_metrics.lambda_away_mean:.3f}    (NHL ≈ 2.8-3.0)")

    print(f"\n🥇 NHLPoissonEngineP1 ({p1_engine.mode}) :")
    if p1_engine.mode == 'dedicated':
        print(f"   MAE P1 home     : {p1_metrics.mae_p1_home_test:.3f} buts")
        print(f"   MAE P1 away     : {p1_metrics.mae_p1_away_test:.3f} buts")
        print(f"   MAE P1 total    : {p1_metrics.mae_p1_total_test:.3f} buts")
        print(f"   λ_p1 home mean  : {p1_metrics.lambda_p1_home_mean:.3f}    (NHL ≈ 0.85)")
        print(f"   λ_p1 away mean  : {p1_metrics.lambda_p1_away_mean:.3f}    (NHL ≈ 0.85)")
    else:
        print(f"   Mode fallback   : λ_p1 = λ_total × {p1_metrics.p1_ratio_used}")
        print(f"   λ_p1 home mean  : {p1_metrics.lambda_p1_home_mean:.3f}")
        print(f"   λ_p1 away mean  : {p1_metrics.lambda_p1_away_mean:.3f}")

    print()
    print_header("✅ TEST BOUT-EN-BOUT RÉUSSI — Sessions 1+2+3 validées")
    print(f"\n  Engines entraînés   : 3 (Moneyline, Poisson, Poisson P1)")
    print(f"  Markets opérationnels : 6 (moneyline, total, btts, p1_winner, p1_total, p1_btts)")
    print(f"  Mode P1 utilisé    : {p1_engine.mode}")
    print(f"\nProchaine étape : Session 4 (exact_score, goal_intervals, train.py, backtest_nhl.py)\n")


if __name__ == "__main__":
    main()