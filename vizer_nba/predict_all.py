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
from src.api.publication import books_for_bet, match_context
from src.api.value_finder import find_value_bets, value_bet_to_dict

try:
    from src.api.nba_schedule import (
        NBAScheduleClient, NBAScheduleError, espn_today_games,
    )
except Exception:
    NBAScheduleClient = None
    NBAScheduleError = Exception
    espn_today_games = None

try:
    from vizer_core import DirectionGuard, load_config
except Exception:
    DirectionGuard = None
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
    # `config.yaml` déclarait déjà `markets: ['h2h', 'totals']` — la bonne
    # liste — mais personne ne la lisait : l'appel sans argument laissait le
    # défaut Python l'emporter, et ce défaut contenait `team_totals`. Un
    # réglage qui existe, a l'air juste, et n'est pas branché.
    odds_cfg = (config.get('apis', {}) or {}).get('odds_api') or config.get('odds_api') or {}
    sport_key = odds_cfg.get('sport') or odds_cfg.get('sport_key') or 'basketball_nba'
    client = OddsAPIClient(api_key=api_key, sport_key=sport_key)
    odds_markets = odds_cfg.get('markets') or None
    odds_games: list = []
    try:
        odds_games = client.get_odds(markets=odds_markets,
                                     force_refresh=args.force_refresh)
    except OddsAPIError as e:
        print(f"⚠️  Odds API indisponible : {e}", file=sys.stderr)

    # Index des cotes par (home, away) pour croisement
    odds_by_matchup = {(g.home, g.away): g for g in odds_games}

    # ── Détection des matchs ──────────────────────────────────────────────
    #
    # Trois sources, dans cet ordre, et chacune a sa raison d'être :
    #
    # 1. `cdn.nba.com` — horaires et statuts officiels, mais répond 403 depuis
    #    une IP de datacenter, donc depuis un runner GitHub.
    # 2. ESPN — joignable partout, déjà la source des scores finaux du projet.
    # 3. Odds API — ne voit un match que si un bookmaker a ouvert un marché
    #    dessus, donc perd les matchs sans cotes.
    #
    # Les trois sont nécessaires parce que la défaillance de la première est
    # silencieuse : sans la deuxième, un hors-saison et un détecteur en panne
    # produisent la même sortie — `no games` — et c'est l'état dans lequel la
    # NBA est restée 97 jours sans qu'on puisse le savoir.
    def _merge(sched: list, source: str) -> list:
        """Croise des matchs détectés avec les cotes disponibles."""
        out: list = []
        for sg in sched:
            go = odds_by_matchup.get((sg.home, sg.away))
            if go is not None:
                go.commence_time = go.commence_time or sg.game_time_utc
                out.append(go)
            else:
                # Match détecté sans cotes : prédiction seule, pas de value bet.
                out.append(GameOdds(
                    home=sg.home, away=sg.away,
                    commence_time=sg.game_time_utc,
                    home_full=code_to_team_name(sg.home),
                    away_full=code_to_team_name(sg.away),
                    bookmakers=[],
                ))
        print(f"  ✓ {len(out)} matchs détectés via {source} "
              f"({sum(1 for g in out if g.bookmakers)} avec cotes)", file=sys.stderr)
        return out

    games: list = []
    detection_source = None
    if not args.no_nba_api and NBAScheduleClient is not None:
        print("🏀 Détection des matchs via l'API NBA officielle...", file=sys.stderr)
        try:
            sched = NBAScheduleClient().get_today_games()
            if sched:
                detection_source = "NBA API"
                games = _merge(sched, detection_source)
            else:
                print("  ℹ️  Aucun match NBA aujourd'hui (via NBA API).", file=sys.stderr)
        except NBAScheduleError as e:
            print(f"  ⚠️  NBA API indisponible ({e})", file=sys.stderr)

    if not games and not args.no_nba_api and espn_today_games is not None:
        print("🏀 Détection des matchs via ESPN...", file=sys.stderr)
        try:
            sched = espn_today_games()
            if sched:
                detection_source = "ESPN"
                games = _merge(sched, detection_source)
            else:
                print("  ℹ️  Aucun match NBA aujourd'hui (via ESPN).", file=sys.stderr)
        except NBAScheduleError as e:
            print(f"  ⚠️  ESPN indisponible ({e})", file=sys.stderr)

    # ── Dernier recours : Odds API, si aucun calendrier n'a répondu ──
    if not games:
        if odds_games:
            detection_source = "Odds API (fallback)"
            games = odds_games
            print(f"  ✓ {len(games)} matchs détectés via Odds API (fallback)",
                  file=sys.stderr)
        else:
            # Les trois sources sont muettes. Deux lectures possibles — pas de
            # match ce jour, ou trois pannes simultanées — et le message les
            # distingue, parce que `no games` publié sans contexte a laissé la
            # NBA invisible pendant trois mois.
            print("ℹ️  Aucun match détecté par aucune des trois sources.",
                  file=sys.stderr)
            print("    Calendrier NBA officiel, ESPN et Odds API muets : jour "
                  "sans match, ou hors-saison.", file=sys.stderr)
            if args.json:
                print(json.dumps({
                    'games': [],
                    'message': 'no games',
                    'detection_source': 'aucune (3 sources interrogées)',
                }, indent=2))
            return 0

    print(f"\n  📍 Source de détection : {detection_source}\n", file=sys.stderr)

    # Garde-fou directionnel : retient les paris d'un marché qui n'a jamais
    # parié que d'un côté sur la fenêtre récente (cf. direction_guard.py).
    guard = (DirectionGuard.load(os.environ.get('VIZER_DIRECTION_VERDICTS'), 'nba')
             if DirectionGuard is not None else None)
    if guard:
        for market, side in sorted(guard.withhold.items()):
            print(f"  🛑 {market} : paris « {side} » retenus — {guard.reasons.get(market, '')}",
                  file=sys.stderr)
    elif guard is not None and not os.environ.get('VIZER_DIRECTION_VERDICTS'):
        print("  ℹ️  pas de verdict directionnel fourni — aucun marché retenu",
              file=sys.stderr)

    meta = getattr(predictor.registry, '_metadata', {}) or {}
    output = {
        'n_games': len(games),
        'detection_source': detection_source,
        # Horodatage et version des modèles : affichés par la PWA et l'Admin.
        'models_trained_at': meta.get('trained_at'),
        'model_version': meta.get('model_version'),
        # Marchés dont les paris sont retenus ce jour, et pourquoi. Publié
        # pour que l'absence d'un marché dans le feed ne soit jamais muette.
        'withheld_markets': [
            {'market': m, 'side': side, 'reason': guard.reasons.get(m, '')}
            for m, side in sorted(guard.withhold.items())
        ] if guard else [],
        'games': [],
    }
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

        withheld: list = []
        if guard:
            value_bets, withheld = guard.split(value_bets)

        if args.value_only and not value_bets and not withheld:
            continue

        output['games'].append({
            'home': go.home,
            'away': go.away,
            'commence_time': getattr(go, 'commence_time', ''),
            'has_odds': bool(go.bookmakers),
            'predictions': all_pred,
            'value_bets': [
                # Comparatif entre bookmakers sur la même sélection.
                {**value_bet_to_dict(vb),
                 'books': books_for_bet(go, vb.market_name, vb.selection)}
                for vb in value_bets
            ],
            # Paris détectés puis retenus par le garde-fou directionnel. Ils
            # sont publiés — jamais supprimés — pour deux raisons : le scanner
            # les recompte, et l'utilisateur voit ce qui a été écarté plutôt
            # qu'un marché devenu silencieux sans explication.
            'withheld_bets': [
                {**value_bet_to_dict(vb),
                 'books': books_for_bet(go, vb.market_name, vb.selection),
                 'withheld_reason': reason}
                for vb, reason in withheld
            ],
            # Forme récente et confrontations directes.
            **match_context(predictor.history, go.home, go.away),
            # Facteurs SHAP de la prédiction de victoire.
            'factors': predictor.explain(go.home, go.away),
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
