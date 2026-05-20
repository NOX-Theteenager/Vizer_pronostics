#!/usr/bin/env python
"""
predict_all.py — Prédit TOUS les matchs NBA détectés par The-Odds API.

Pour chaque match détecté :
  1. Prédit tous les markets (moneyline, total, team totals, etc.)
  2. Croise avec les cotes réelles → value bets
  3. Affiche un récap (ou JSON si --json)

Usage :
    python predict_all.py
    python predict_all.py --api-key aaea026bdcd560b9ab5f8119b39adb38
    python predict_all.py --json > predictions_nba.json
    python predict_all.py --min-edge 0.05 --value-only

La clé API peut venir de --api-key, de la variable d'env ODDS_API_KEY,
ou du fichier config.yaml (apis.odds_api.key).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from src.api.unified_predictor import UnifiedPredictor
from src.api.odds_client import OddsAPIClient, OddsAPIError, code_to_team_name, GameOdds
from src.api.value_finder import find_value_bets, value_bet_to_dict

try:
    from src.api.nba_schedule import NBAScheduleClient, NBAScheduleError
except Exception:
    NBAScheduleClient = None
    NBAScheduleError = Exception

try:
    from vizer_core import load_config
except Exception:
    load_config = None


def resolve_api_key(args, config: dict) -> str | None:
    if args.api_key:
        return args.api_key
    if os.environ.get('ODDS_API_KEY'):
        return os.environ['ODDS_API_KEY']
    # Cherche dans apis.odds_api.key (structure NBA) OU odds_api.key (structure NHL)
    key = (
        config.get('apis', {}).get('odds_api', {}).get('key')
        or config.get('odds_api', {}).get('key')
    )
    return key or None


def main():
    parser = argparse.ArgumentParser(description="Prédit tous les matchs NBA via Odds API")
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--model', default='models/nba_model.pkl')
    parser.add_argument('--api-key', default=None)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--value-only', action='store_true',
                        help='Afficher uniquement les matchs avec value bets')
    parser.add_argument('--min-edge', type=float, default=None)
    parser.add_argument('--force-refresh', action='store_true')
    parser.add_argument('--no-nba-api', action='store_true',
                        help="Désactive la détection via l'API NBA officielle "
                             "(utilise directement Odds API)")
    args = parser.parse_args()

    config = {}
    if load_config is not None:
        try:
            config = load_config(args.config, validate=False)
        except Exception:
            config = {}

    api_key = resolve_api_key(args, config)
    if not api_key:
        print("❌ Pas de clé API. Utilise --api-key, ODDS_API_KEY, ou config.yaml.",
              file=sys.stderr)
        return 1

    print("📂 Chargement du modèle...", file=sys.stderr)
    predictor = UnifiedPredictor(args.model)

    # ── Récupérer les cotes Odds API (pour les value bets + fallback détection) ──
    print("📡 Récupération des cotes NBA (Odds API)...", file=sys.stderr)
    client = OddsAPIClient(api_key=api_key, sport_key='basketball_nba')
    odds_games: list = []
    try:
        odds_games = client.get_odds(force_refresh=args.force_refresh)
    except OddsAPIError as e:
        print(f"⚠️  Odds API indisponible : {e}", file=sys.stderr)

    # Index des cotes par (home, away) pour croisement
    odds_by_matchup = {(g.home, g.away): g for g in odds_games}

    # ── Détection des matchs : NBA API officielle d'abord ──
    games: list = []
    detection_source = None
    if not args.no_nba_api and NBAScheduleClient is not None:
        print("🏀 Détection des matchs via l'API NBA officielle...", file=sys.stderr)
        try:
            sched = NBAScheduleClient().get_today_games()
            if sched:
                detection_source = "NBA API"
                # Construire des GameOdds en fusionnant avec les cotes Odds API
                for sg in sched:
                    key = (sg.home, sg.away)
                    if key in odds_by_matchup:
                        # On a les cotes pour ce match
                        go = odds_by_matchup[key]
                        go.commence_time = go.commence_time or sg.game_time_utc
                        games.append(go)
                    else:
                        # Match détecté sans cotes (prédiction seule)
                        games.append(GameOdds(
                            home=sg.home, away=sg.away,
                            commence_time=sg.game_time_utc,
                            home_full=code_to_team_name(sg.home),
                            away_full=code_to_team_name(sg.away),
                            bookmakers=[],
                        ))
                print(f"  ✓ {len(games)} matchs détectés via NBA API "
                      f"({sum(1 for g in games if g.bookmakers)} avec cotes)",
                      file=sys.stderr)
            else:
                print("  ℹ️  Aucun match NBA aujourd'hui (via NBA API).", file=sys.stderr)
        except NBAScheduleError as e:
            print(f"  ⚠️  NBA API indisponible ({e}), repli sur Odds API.", file=sys.stderr)

    # ── Fallback : Odds API si NBA API n'a rien donné ──
    if not games:
        if odds_games:
            detection_source = "Odds API (fallback)"
            games = odds_games
            print(f"  ✓ {len(games)} matchs détectés via Odds API (fallback)",
                  file=sys.stderr)
        else:
            print("ℹ️  Aucun match NBA détecté (hors-saison ?).", file=sys.stderr)
            if args.json:
                print(json.dumps({'games': [], 'message': 'no games'}, indent=2))
            return 0

    print(f"\n  📍 Source de détection : {detection_source}\n", file=sys.stderr)

    output = {'n_games': len(games), 'detection_source': detection_source, 'games': []}
    for go in games:
        if go.home == "???" or go.away == "???":
            continue

        try:
            all_pred = predictor.predict_all(go.home, go.away)
        except Exception as e:
            all_pred = {'error': f"{type(e).__name__}: {e}"}

        value_bets = find_value_bets(predictor, go)
        if args.min_edge is not None:
            value_bets = [vb for vb in value_bets if vb.edge >= args.min_edge]

        if args.value_only and not value_bets:
            continue

        output['games'].append({
            'home': go.home,
            'away': go.away,
            'commence_time': getattr(go, 'commence_time', ''),
            'has_odds': bool(go.bookmakers),
            'predictions': all_pred,
            'value_bets': [value_bet_to_dict(vb) for vb in value_bets],
        })

    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    else:
        _print_human(output)

    return 0


def _print_human(output: dict):
    from src.api.odds_client import code_to_team_name

    print("=" * 70)
    print(f"🏀 PRÉDICTIONS NBA — {output['n_games']} match(s) détecté(s)")
    print("=" * 70)

    total_vb = 0
    for g in output['games']:
        home_name = code_to_team_name(g['home'])
        away_name = code_to_team_name(g['away'])
        print(f"\n🏀 {home_name} (dom) vs {away_name}")
        if g.get('commence_time'):
            print(f"   ⏰ {g['commence_time']}")

        pred = g.get('predictions', {})
        if isinstance(pred, dict) and 'error' not in pred:
            ml = pred.get('moneyline') or pred.get('win')
            if isinstance(ml, dict):
                ph = ml.get('home_win_proba') or ml.get('probabilities', {}).get('home')
                if ph is not None:
                    print(f"   Moneyline : {home_name} {ph:.1%}  |  {away_name} {1-ph:.1%}")
            tot = pred.get('total')
            if isinstance(tot, dict):
                ev = tot.get('predicted_total') or tot.get('expected_value')
                if ev is not None:
                    print(f"   Total     : E[pts]={ev:.1f}")

        if g['value_bets']:
            total_vb += len(g['value_bets'])
            print(f"   💰 VALUE BETS ({len(g['value_bets'])}):")
            for vb in g['value_bets']:
                sel = vb.get('selection')
                if vb.get('market') == 'moneyline':
                    sel = home_name if sel == 'home' else away_name if sel == 'away' else sel
                print(f"      → {vb.get('market')}/{sel} "
                      f"@ {vb.get('bookmaker_odds')}  edge={vb.get('edge')}  "
                      f"kelly={vb.get('kelly_stake')}")
        else:
            print(f"   (pas de value bet)")

    print("\n" + "=" * 70)
    print(f"📊 TOTAL : {total_vb} value bet(s) sur {output['n_games']} match(s)")
    print("=" * 70)


if __name__ == "__main__":
    sys.exit(main())
