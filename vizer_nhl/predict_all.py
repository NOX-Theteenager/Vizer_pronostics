#!/usr/bin/env python
"""
predict_all.py — Prédit TOUS les matchs NHL détectés par The-Odds API.

Pour chaque match détecté :
  1. Prédit les 8 markets (moneyline, total, btts, p1_*, exact_score, goal_intervals)
  2. Croise moneyline + total avec les cotes réelles → value bets
  3. Affiche un récap (ou JSON si --json)

Usage :
    python predict_all.py
    python predict_all.py --api-key aaea026bdcd560b9ab5f8119b39adb38
    python predict_all.py --json > predictions_nhl.json
    python predict_all.py --min-edge 0.05 --value-only

La clé API peut venir de --api-key, de la variable d'env ODDS_API_KEY,
ou du fichier config.yaml (clé odds_api.key).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from vizer_core import load_config

from src.api.odds_client import NHLOddsClient, OddsAPIError, code_to_team_name
from src.api.unified_predictor import NHLUnifiedPredictor
from src.api.value_finder import find_value_bets


def resolve_api_key(args, config: dict) -> str | None:
    """Cherche la clé API dans : --api-key, env, config.yaml."""
    if args.api_key:
        return args.api_key
    if os.environ.get('ODDS_API_KEY'):
        return os.environ['ODDS_API_KEY']
    return config.get('odds_api', {}).get('key')


def main():
    parser = argparse.ArgumentParser(description="Prédit tous les matchs NHL via Odds API")
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--model', default=None, help='Chemin du registre')
    parser.add_argument('--api-key', default=None, help='Clé The-Odds API')
    parser.add_argument('--json', action='store_true', help='Sortie JSON')
    parser.add_argument('--value-only', action='store_true',
                        help='Afficher uniquement les matchs avec value bets')
    parser.add_argument('--min-edge', type=float, default=None,
                        help='Filtre les value bets sous ce edge')
    parser.add_argument('--force-refresh', action='store_true',
                        help='Ignorer le cache des cotes')
    args = parser.parse_args()

    config = load_config(args.config, validate=False)
    paths = config.get('paths', {})
    model_path = args.model or str(Path(paths.get('models_dir', 'models'))
                                   / paths.get('model_filename', 'nhl_model.pkl'))
    dataset_filename = paths.get('dataset_filename', 'dataset_agrege_vizer_nhl.csv')
    data_dir = paths.get('data_dir', 'data')

    api_key = resolve_api_key(args, config)
    if not api_key:
        print("❌ Pas de clé API. Utilise --api-key, ODDS_API_KEY, ou config.yaml.",
              file=sys.stderr)
        return 1

    # Charger le prédicteur
    print("📂 Chargement du modèle...", file=sys.stderr)
    predictor = NHLUnifiedPredictor(
        model_path=model_path,
        data_dir=data_dir,
        dataset_filename=dataset_filename,
    )
    print(f"  ✓ {len(predictor.registry.list_markets())} markets, "
          f"{len(predictor.known_teams)} équipes connues", file=sys.stderr)

    # Récupérer les cotes
    print("📡 Récupération des cotes NHL...", file=sys.stderr)
    client = NHLOddsClient(api_key=api_key)
    try:
        games = client.get_odds(force_refresh=args.force_refresh)
    except OddsAPIError as e:
        print(f"❌ Erreur Odds API : {e}", file=sys.stderr)
        return 1

    if not games:
        print("ℹ️  Aucun match NHL détecté (hors-saison ?).", file=sys.stderr)
        if args.json:
            print(json.dumps({'games': [], 'message': 'no games'}, indent=2))
        return 0

    print(f"  ✓ {len(games)} matchs détectés\n", file=sys.stderr)

    # Prédire chaque match
    output = {'n_games': len(games), 'games': []}
    for go in games:
        if go.home == "???" or go.away == "???":
            continue

        all_pred = predictor.predict_all(go.home, go.away)
        value_bets = find_value_bets(predictor, go)
        if args.min_edge is not None:
            value_bets = [vb for vb in value_bets if vb.edge >= args.min_edge]

        if args.value_only and not value_bets:
            continue

        game_entry = {
            'home': go.home,
            'away': go.away,
            'commence_time': go.commence_time,
            'predictions': all_pred.get('markets', {}),
            'value_bets': [
                {
                    'market': vb.market_name,
                    'selection': vb.selection,
                    'predicted_proba': round(vb.predicted_proba, 4),
                    'bookmaker_odds': vb.bookmaker_odds,
                    'edge': round(vb.edge, 4),
                    'kelly_stake': round(vb.kelly_stake, 4),
                    'confidence': vb.confidence,
                }
                for vb in value_bets
            ],
        }
        output['games'].append(game_entry)

    # Sortie
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        _print_human(output)

    return 0


def _print_human(output: dict):
    """Affichage lisible dans la console."""
    from src.api.odds_client import code_to_team_name

    print("=" * 70)
    print(f"🏒 PRÉDICTIONS NHL — {output['n_games']} match(s) détecté(s)")
    print("=" * 70)

    total_value_bets = 0
    for g in output['games']:
        home_name = code_to_team_name(g['home'])
        away_name = code_to_team_name(g['away'])
        print(f"\n🏒 {home_name} (dom) vs {away_name}")
        print(f"   ⏰ {g['commence_time']}")

        m = g['predictions']
        if 'moneyline' in m and 'probabilities' in m['moneyline']:
            p = m['moneyline']['probabilities']
            print(f"   Moneyline : {home_name} {p.get('home', 0):.1%}  |  "
                  f"{away_name} {p.get('away', 0):.1%}")
        if 'total' in m and m['total'].get('expected_value') is not None:
            ev = m['total']['expected_value']
            print(f"   Total     : E[buts]={ev:.2f}")
        if 'btts' in m and 'probabilities' in m['btts']:
            print(f"   BTTS      : P(yes)={m['btts']['probabilities'].get('yes', 0):.1%}")
        if 'p1_winner' in m and 'probabilities' in m['p1_winner']:
            p = m['p1_winner']['probabilities']
            print(f"   P1 Winner : {home_name} {p.get('home_lead',0):.1%} | "
                  f"nul {p.get('tied',0):.1%} | {away_name} {p.get('away_lead',0):.1%}")

        if g['value_bets']:
            total_value_bets += len(g['value_bets'])
            print(f"   💰 VALUE BETS ({len(g['value_bets'])}):")
            for vb in g['value_bets']:
                sel = vb['selection']
                if vb['market'] == 'moneyline':
                    sel = home_name if sel == 'home' else away_name if sel == 'away' else sel
                print(f"      → {vb['market']}/{sel} @ {vb['bookmaker_odds']:.2f}  "
                      f"edge={vb['edge']:.1%}  kelly={vb['kelly_stake']:.1%}  [{vb['confidence']}]")
        else:
            print(f"   (pas de value bet)")

    print("\n" + "=" * 70)
    print(f"📊 TOTAL : {total_value_bets} value bet(s) sur {output['n_games']} match(s)")
    print("=" * 70)


if __name__ == "__main__":
    sys.exit(main())
