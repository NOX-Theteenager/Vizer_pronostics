#!/usr/bin/env python
"""
Récupère les matchs du jour et fait des prédictions avec le modèle unifié.

Étape 4 : support --odds pour récupérer automatiquement les cotes via
The-Odds API et calculer les value bets (edge + Kelly).
"""
import sys
import json
from datetime import datetime
from nba_api.live.nba.endpoints import scoreboard

from vizer_core import load_config

from src.api.unified_predictor import UnifiedPredictor
from src.api.odds_client import OddsAPIClient, OddsAPIError
from src.api.value_finder import find_value_bets, format_value_bet_human, value_bet_to_dict


def interactive_mode():
    """
    Mode interactif pour entrer les lignes pour chaque match.
    
    Returns:
        Dictionnaire {game_id: [line1, line2, ...]}
    """
    print("🏀 Récupération des matchs du jour...", file=sys.stderr)
    games = get_today_games()
    
    if not games:
        print("❌ Aucun match trouvé pour aujourd'hui", file=sys.stderr)
        return None, None
    
    print(f"✓ {len(games)} match(s) trouvé(s)", file=sys.stderr)
    print("", file=sys.stderr)
    
    print("=" * 70)
    print("MODE INTERACTIF - Entrez les lignes pour chaque match")
    print("=" * 70)
    print()
    print("Instructions:")
    print("  • Entrez une ou plusieurs lignes séparées par des espaces")
    print("  • Appuyez sur Entrée sans rien taper pour passer le match")
    print("  • Exemples: '220.5' ou '218.0 220.5 223.0'")
    print()
    
    lines_dict = {}
    
    for i, (home, away, game_id) in enumerate(games, 1):
        print(f"Match {i}/{len(games)}: {home} vs {away}")
        print("-" * 70)
        
        while True:
            try:
                user_input = input("Lignes (séparées par espaces, ou Entrée pour passer): ").strip()
                
                if not user_input:
                    print("  ⊘ Match passé (pas de ligne)")
                    print()
                    break
                
                # Parser les lignes
                lines = []
                for line_str in user_input.split():
                    try:
                        line_value = float(line_str)
                        lines.append(line_value)
                    except ValueError:
                        print(f"  ⚠️  '{line_str}' n'est pas un nombre valide, ignoré")
                
                if lines:
                    lines_dict[game_id] = lines
                    print(f"  ✓ {len(lines)} ligne(s) enregistrée(s): {', '.join(map(str, lines))}")
                    print()
                    break
                else:
                    print("  ⚠️  Aucune ligne valide, réessayez")
                    
            except KeyboardInterrupt:
                print()
                print()
                print("❌ Annulé par l'utilisateur")
                return None, None
            except EOFError:
                print()
                print("  ⊘ Match passé")
                print()
                break
    
    print("=" * 70)
    print(f"✓ Configuration terminée: {len(lines_dict)} match(s) avec lignes")
    print("=" * 70)
    print()
    
    return games, lines_dict


def get_today_games():
    """
    Récupère les matchs du jour depuis l'API NBA.
    
    Returns:
        Liste de tuples (home_abbr, away_abbr, game_id)
    """
    try:
        board = scoreboard.ScoreBoard()
        games = board.games.get_dict()
        
        today_games = []
        for game in games:
            home_team = game['homeTeam']['teamTricode']
            away_team = game['awayTeam']['teamTricode']
            game_id = game['gameId']
            
            today_games.append((home_team, away_team, game_id))
        
        return today_games
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des matchs: {e}", file=sys.stderr)
        return []


def predict_today_games(output_file='predictions_today.json', lines=None,
                         save_history=True, use_odds=False, config_path='config.yaml'):
    """
    Prédit tous les matchs du jour et sauvegarde dans un fichier JSON.

    Args:
        output_file:  Fichier de sortie principal
        lines:        Dictionnaire {game_id: [line1, line2, ...]} ou None
        save_history: Si True, sauvegarde aussi dans predictions/YYYY-MM-DD.json
        use_odds:     Si True, récupère les cotes via The-Odds API et calcule
                      les value bets (consomme 1 crédit API par run).
        config_path:  Chemin du config.yaml (pour la clé API si use_odds).
    """
    from pathlib import Path
    
    print("🏀 Récupération des matchs du jour...", file=sys.stderr)
    games = get_today_games()
    
    if not games:
        print("❌ Aucun match trouvé pour aujourd'hui", file=sys.stderr)
        return
    
    print(f"✓ {len(games)} match(s) trouvé(s)", file=sys.stderr)
    print("", file=sys.stderr)
    
    # Charger le prédicteur unifié
    print("📂 Chargement du modèle unifié...", file=sys.stderr)
    predictor = UnifiedPredictor('models/nba_model.pkl')
    print("✓ Modèle chargé", file=sys.stderr)

    # Récupérer les cotes une seule fois si demandé
    odds_by_match = {}
    if use_odds:
        print("", file=sys.stderr)
        print("💰 Récupération des cotes via The-Odds API...", file=sys.stderr)
        try:
            config = load_config(config_path)
            api_key = config.get('apis', {}).get('odds_api', {}).get('key', '')
            sport_key = config.get('apis', {}).get('odds_api', {}).get('sport', 'basketball_nba')
            if not api_key:
                print("⚠️  config.yaml apis.odds_api.key vide. Cotes désactivées.", file=sys.stderr)
                use_odds = False
            else:
                odds_client = OddsAPIClient(api_key=api_key, sport_key=sport_key)
                games_odds = odds_client.get_odds()
                # Indexer par (home_abbr, away_abbr) pour matching rapide
                for g in games_odds:
                    odds_by_match[(g.home, g.away)] = g
                print(f"✓ Cotes pour {len(games_odds)} match(s) récupérées", file=sys.stderr)
        except OddsAPIError as e:
            print(f"⚠️  Erreur The-Odds API : {e}", file=sys.stderr)
            print(f"   → Les prédictions seront produites sans value bets.", file=sys.stderr)
            use_odds = False
        except Exception as e:
            print(f"⚠️  Erreur inattendue récupération cotes : {e}", file=sys.stderr)
            use_odds = False
    print("", file=sys.stderr)
    
    # Prédire chaque match
    predictions = []
    
    for i, (home, away, game_id) in enumerate(games, 1):
        print(f"📊 Prédiction {i}/{len(games)}: {home} vs {away}", file=sys.stderr)
        
        try:
            # Prédiction de victoire (une seule fois par match)
            win_pred = predictor.predict_win(home, away)
            all_pred = predictor.predict_all(home, away)
            
            # Structure de base du résultat
            result = {
                'game_id': game_id,
                'match': {
                    'home': home,
                    'away': away
                },
                'win_prediction': {
                    'winner': 'home' if win_pred['prediction'] == 1 else 'away',
                    'home_win_proba': win_pred['home_win_proba'],
                    'away_win_proba': win_pred['away_win_proba']
                },
                'total_prediction': {
                    'predicted_total': all_pred['total']['prediction']
                }
            }
            
            print(f"  ✓ Gagnant: {result['win_prediction']['winner']} "
                  f"({result['win_prediction']['home_win_proba' if result['win_prediction']['winner'] == 'home' else 'away_win_proba']:.0%})", 
                  file=sys.stderr)
            print(f"  ✓ Total prédit: {result['total_prediction']['predicted_total']:.1f} points", file=sys.stderr)

            # Value bets via cotes bookmaker
            if use_odds:
                game_odds = odds_by_match.get((home, away))
                if game_odds is None:
                    print(f"  ⊘ Cotes non disponibles pour {home} vs {away}", file=sys.stderr)
                else:
                    bets = find_value_bets(predictor, game_odds)
                    if bets:
                        print(f"  💎 {len(bets)} value bet(s) détecté(s) :", file=sys.stderr)
                        for vb in bets:
                            print(format_value_bet_human(vb, home, away), file=sys.stderr)
                    else:
                        print(f"  💤 Aucun value bet (edge insuffisant)", file=sys.stderr)
                    result['value_bets'] = [value_bet_to_dict(vb) for vb in bets]
                    result['bookmaker_odds'] = {
                        'moneyline_home': game_odds.best_moneyline_odds()[0],
                        'moneyline_away': game_odds.best_moneyline_odds()[1],
                        'consensus_total_line': game_odds.consensus_total_line(),
                    }
            
            # Récupérer les lignes pour ce match
            game_lines = lines.get(game_id, []) if lines else []
            
            if game_lines:
                # Prédictions under/over pour chaque ligne
                result['lines_analysis'] = []
                
                for line in game_lines:
                    uo_pred = predictor.predict_under_over(home, away, line)
                    
                    line_result = {
                        'line': line,
                        'recommendation': uo_pred['recommendation'],
                        'over_proba': uo_pred['over_proba'],
                        'under_proba': uo_pred['under_proba'],
                        'confidence': max(uo_pred['over_proba'], uo_pred['under_proba'])
                    }
                    
                    result['lines_analysis'].append(line_result)
                    
                    print(f"  ✓ Ligne {line}: {uo_pred['recommendation']} "
                          f"({max(uo_pred['over_proba'], uo_pred['under_proba']):.0%})", 
                          file=sys.stderr)
            
            predictions.append(result)
            
        except Exception as e:
            print(f"  ✗ Erreur: {e}", file=sys.stderr)
        
        print("", file=sys.stderr)
    
    # Préparer les données de sortie
    today_date = datetime.now().strftime('%Y-%m-%d')
    output = {
        'date': today_date,
        'count': len(predictions),
        'predictions': predictions
    }
    
    # Sauvegarder dans le fichier principal
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Prédictions sauvegardées: {output_file}", file=sys.stderr)

    # Sauvegarder dans l'historique (un seul bloc — la duplication précédente est corrigée)
    if save_history:
        history_dir = Path('predictions')
        history_dir.mkdir(exist_ok=True)

        history_file = history_dir / f"{today_date}.json"
        with open(history_file, 'w') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"📁 Historique sauvegardé: {history_file}", file=sys.stderr)

    print(f"📊 {len(predictions)} match(s) analysé(s)", file=sys.stderr)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Prédire les matchs du jour avec le modèle unifié')
    parser.add_argument('--output', '-o', default='predictions_today.json', 
                       help='Fichier de sortie (défaut: predictions_today.json)')
    parser.add_argument('--lines', nargs='*', 
                       help='Lignes au format GAME_ID:LINE (ex: 0022500123:220.5). '
                            'Plusieurs lignes pour le même match sont supportées.')
    parser.add_argument('--no-history', action='store_true',
                       help='Ne pas sauvegarder dans l\'historique (predictions/YYYY-MM-DD.json)')
    parser.add_argument('--list-only', action='store_true',
                       help='Afficher uniquement la liste des matchs (GAME_ID et équipes) sans prédictions')
    parser.add_argument('--interactive', '-i', action='store_true',
                       help='Mode interactif: le script demande les lignes pour chaque match')
    parser.add_argument('--odds', action='store_true',
                       help='Récupère les cotes via The-Odds API et calcule les value bets '
                            '(consomme 1 crédit API par run, mis en cache 60min).')
    parser.add_argument('--config', default='config.yaml',
                       help='Chemin du config.yaml (défaut: config.yaml)')
    
    args = parser.parse_args()
    
    # Mode liste seulement
    if args.list_only:
        print("🏀 Récupération des matchs du jour...", file=sys.stderr)
        games = get_today_games()
        
        if not games:
            print("❌ Aucun match trouvé pour aujourd'hui", file=sys.stderr)
            return 1
        
        print(f"✓ {len(games)} match(s) trouvé(s)", file=sys.stderr)
        print("", file=sys.stderr)
        
        # Afficher la liste des matchs
        print("=" * 70)
        print(f"MATCHS DU JOUR - {datetime.now().strftime('%Y-%m-%d')}")
        print("=" * 70)
        print()
        
        for i, (home, away, game_id) in enumerate(games, 1):
            print(f"{i}. {home} vs {away}")
            print(f"   GAME_ID: {game_id}")
            print(f"   Format pour --lines: {game_id}:220.5")
            print()
        
        print("=" * 70)
        print("Pour faire des prédictions avec des lignes:")
        print(f"  python predict_today.py --lines {games[0][2]}:220.5 ...")
        print()
        print("Ou en mode interactif:")
        print("  python predict_today.py --interactive")
        print()
        
        return 0
    
    # Mode interactif
    if args.interactive:
        games, lines_dict = interactive_mode()
        
        if games is None:
            return 1
        
        # Lancer les prédictions
        predict_today_games(args.output, lines_dict, save_history=not args.no_history,
                             use_odds=args.odds, config_path=args.config)
        return 0
    
    # Mode prédiction normal
    # Parser les lignes (supporte plusieurs lignes par match)
    lines_dict = {}
    if args.lines:
        for line_str in args.lines:
            try:
                game_id, line = line_str.split(':')
                line_value = float(line)
                
                # Ajouter la ligne à la liste pour ce game_id
                if game_id not in lines_dict:
                    lines_dict[game_id] = []
                lines_dict[game_id].append(line_value)
                
            except ValueError:
                print(f"⚠️  Format invalide ignoré: {line_str}", file=sys.stderr)
    
    predict_today_games(args.output, lines_dict, save_history=not args.no_history,
                         use_odds=args.odds, config_path=args.config)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
