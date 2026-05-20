#!/usr/bin/env python
"""
Script de prédiction JSON unifié (victoire + total + analyse automatique).

Étape 4 : support --with-odds pour récupérer automatiquement les cotes via
The-Odds API et calculer les value bets (edge + Kelly).
"""
import sys
import json
import argparse
from typing import Optional, List, Dict

from vizer_core import load_config

from src.api.unified_predictor import UnifiedPredictor
from src.api.odds_client import OddsAPIClient, OddsAPIError
from src.api.value_finder import find_value_bets, value_bet_to_dict


def suggest_lines(predicted_total, spread=15):
    """Suggère 3 lignes stratégiques à analyser autour du total prédit"""
    base = round(predicted_total * 2) / 2
    
    # Seulement 3 lignes: une basse, une proche, une haute
    lines = [
        base - 10,  # Ligne basse
        base,       # Ligne proche du total
        base + 10   # Ligne haute
    ]
    
    return [l for l in lines if l > 0]


def analyze_best_lines(home, away, predicted_total, min_confidence=0.65, date=None, silent=False, predictor=None):
    """
    Analyse plusieurs lignes et trouve les meilleures opportunités
    
    Returns:
        Dict avec les meilleures lignes et leurs stats
    """
    if predictor is None:
        predictor = UnifiedPredictor()
    
    suggested_lines = suggest_lines(predicted_total)
    
    if not silent:
        print(f"  🔍 Analyse de {len(suggested_lines)} lignes...", file=sys.stderr)
    
    best_bets = []
    all_results = []
    
    for line in suggested_lines:
        result = predictor.predict_under_over(home, away, line, date)
        
        if 'error' not in result:
            line_result = {
                'line': line,
                'recommendation': result['recommendation'],
                'confidence': max(result['over_proba'], result['under_proba']),
                'over_probability': result['over_proba'],
                'under_probability': result['under_proba'],
                'edge': abs(predicted_total - line)
            }
            
            all_results.append(line_result)
            
            # Garder les bons paris (confiance >= min)
            if line_result['confidence'] >= min_confidence:
                best_bets.append(line_result)
    
    # Trier par confiance décroissante
    best_bets.sort(key=lambda x: x['confidence'], reverse=True)
    
    return {
        'best_bets': best_bets,
        'all_lines_analyzed': all_results,
        'lines_tested': suggested_lines
    }


def predict_match(
    home: str, 
    away: str, 
    line: Optional[float] = None,
    date: Optional[str] = None,
    silent: bool = False,
    auto_analyze: bool = True,
    min_confidence: float = 0.65,
    with_odds: bool = False,
    odds_client: Optional[OddsAPIClient] = None,
    predictor: Optional[UnifiedPredictor] = None,
) -> Dict:
    """
    Prédit un match (victoire + total + analyse automatique).
    
    Args:
        home: Abréviation équipe domicile
        away: Abréviation équipe extérieur
        line: Ligne de total optionnelle (si None, analyse auto)
        date: Date de référence (YYYY-MM-DD)
        silent: Si True, n'affiche pas les messages
        auto_analyze: Si True et line=None, analyse automatiquement les lignes
        min_confidence: Confiance minimale pour recommander
        with_odds: Si True, récupère cotes via The-Odds API et calcule value bets
        odds_client: Client The-Odds API préinstancié (sinon créé à la demande)
        predictor: UnifiedPredictor préinstancié (évite recharge)
        
    Returns:
        Dictionnaire avec les prédictions
    """
    import numpy as np
    
    def convert_types(obj):
        """Convertit les types numpy en types Python"""
        if isinstance(obj, dict):
            return {k: convert_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_types(item) for item in obj]
        elif isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return obj
    
    if predictor is None:
        if not silent:
            print("📂 Chargement des modèles...", file=sys.stderr)
        predictor = UnifiedPredictor()
        if not silent:
            print("✓ Modèles chargés", file=sys.stderr)
    
    try:
        # Prédiction complète
        all_predictions = predictor.predict_all(home, away, date)
        
        # Formater le résultat
        result = {
            'match': {
                'home': {'abbreviation': home, 'name': home},
                'away': {'abbreviation': away, 'name': away},
                'date': date
            },
            'win_prediction': {
                'winner': 'home' if all_predictions['win']['prediction'] == 1 else 'away',
                'winner_name': home if all_predictions['win']['prediction'] == 1 else away,
                'home_win_probability': all_predictions['win']['home_win_proba'],
                'away_win_probability': all_predictions['win']['away_win_proba'],
                'confidence': max(all_predictions['win']['home_win_proba'], 
                                all_predictions['win']['away_win_proba'])
            },
            'total_prediction': {
                'predicted_total': all_predictions['total']['prediction']
            }
        }
        
        # Ajouter la prédiction under/over si une ligne est fournie
        if line is not None:
            uo_result = predictor.predict_under_over(home, away, line, date)
            result['total_prediction'].update({
                'line': line,
                'recommendation': uo_result['recommendation'],
                'over_probability': uo_result['over_proba'],
                'under_probability': uo_result['under_proba'],
                'confidence': max(uo_result['over_proba'], uo_result['under_proba'])
            })
        
        # Analyse automatique si pas de ligne fournie
        if auto_analyze and line is None:
            predicted_total = all_predictions['total']['prediction']
            analysis = analyze_best_lines(home, away, predicted_total, min_confidence, 
                                         date, silent, predictor)
            result['betting_analysis'] = analysis
            
            if not silent and analysis['best_bets']:
                best = analysis['best_bets'][0]
                print(f"  🎯 Meilleur pari: {best['recommendation']} {best['line']} ({best['confidence']:.0%})", file=sys.stderr)
        
        # Récupération cotes + value bets (étape 4)
        if with_odds and odds_client is not None:
            try:
                if not silent:
                    print(f"  💰 Récupération cotes {home} vs {away}...", file=sys.stderr)
                game_odds = odds_client.get_odds_for_match(home, away)
                if game_odds is None:
                    if not silent:
                        print(f"  ⊘ Cotes non disponibles pour {home} vs {away}", file=sys.stderr)
                    result['value_bets'] = []
                    result['bookmaker_odds'] = None
                else:
                    bets = find_value_bets(predictor, game_odds, date)
                    result['value_bets'] = [value_bet_to_dict(vb) for vb in bets]
                    result['bookmaker_odds'] = {
                        'moneyline_home': game_odds.best_moneyline_odds()[0],
                        'moneyline_away': game_odds.best_moneyline_odds()[1],
                        'consensus_total_line': game_odds.consensus_total_line(),
                        'commence_time': game_odds.commence_time,
                    }
                    if not silent:
                        if bets:
                            print(f"  💎 {len(bets)} value bet(s) détecté(s)", file=sys.stderr)
                            for vb in bets:
                                print(f"     • {vb.market_name} {vb.selection} @ {vb.bookmaker_odds:.2f} "
                                      f"edge={vb.edge:+.3f} kelly={vb.kelly_stake*100:.1f}%", file=sys.stderr)
                        else:
                            print(f"  💤 Aucun value bet (edge insuffisant)", file=sys.stderr)
            except OddsAPIError as e:
                if not silent:
                    print(f"  ⚠️  Erreur The-Odds API : {e}", file=sys.stderr)
                result['value_bets'] = []
                result['odds_error'] = str(e)
            except Exception as e:
                if not silent:
                    print(f"  ⚠️  Erreur inattendue cotes : {e}", file=sys.stderr)
                result['value_bets'] = []
                result['odds_error'] = str(e)

        return convert_types(result)
        
    except Exception as e:
        return {'error': str(e)}


def predict_multiple(
    matches: List[tuple],
    lines: Optional[List[float]] = None,
    date: Optional[str] = None,
    silent: bool = False,
    auto_analyze: bool = True,
    min_confidence: float = 0.65,
    with_odds: bool = False,
    odds_client: Optional[OddsAPIClient] = None,
    predictor: Optional[UnifiedPredictor] = None,
) -> List[Dict]:
    """
    Prédit plusieurs matchs avec partage du predictor et de l'odds_client.
    
    Args:
        matches: Liste de tuples (home, away)
        lines: Liste de lignes optionnelles
        date: Date de référence
        silent: Si True, n'affiche pas les messages
        auto_analyze: Si True, analyse automatiquement les lignes
        min_confidence: Confiance minimale
        with_odds: Si True, récupère les cotes pour chaque match
        odds_client: OddsAPIClient préinstancié (sinon créé via config)
        predictor: UnifiedPredictor préinstancié (sinon créé)
        
    Returns:
        Liste de prédictions
    """
    if lines is None:
        lines = [None] * len(matches)
    
    # Partager le predictor entre tous les matchs (évite recharge × N)
    if predictor is None:
        if not silent:
            print("📂 Chargement des modèles (partagé)...", file=sys.stderr)
        predictor = UnifiedPredictor()
        if not silent:
            print("✓ Modèles chargés", file=sys.stderr)
    
    results = []
    for (home, away), line in zip(matches, lines):
        result = predict_match(home, away, line, date, silent=True, 
                             auto_analyze=auto_analyze, min_confidence=min_confidence,
                             with_odds=with_odds, odds_client=odds_client,
                             predictor=predictor)
        results.append(result)
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Prédiction JSON unifiée avec analyse automatique')
    parser.add_argument('matches', nargs='+', help='Match(s) au format HOME:AWAY ou HOME AWAY')
    parser.add_argument('--lines', nargs='*', type=float, help='Lignes de total (même ordre)')
    parser.add_argument('--date', help='Date de référence (YYYY-MM-DD)', default=None)
    parser.add_argument('--pretty', action='store_true', help='JSON formaté')
    parser.add_argument('--silent', action='store_true', help='Pas de messages stderr')
    parser.add_argument('--output', '-o', help='Fichier de sortie (défaut: stdout)')
    parser.add_argument('--no-auto-analyze', action='store_true', 
                       help='Désactiver l\'analyse automatique des lignes')
    parser.add_argument('--min-confidence', type=float, default=0.65,
                       help='Confiance minimale pour recommander (défaut: 0.65)')
    parser.add_argument('--with-odds', action='store_true',
                       help='Récupère cotes via The-Odds API et calcule value bets '
                            '(1 crédit API par run, mis en cache 60min)')
    parser.add_argument('--config', default='config.yaml',
                       help='Chemin du config.yaml (défaut: config.yaml)')
    
    args = parser.parse_args()
    
    # Parser les matchs
    matches = []
    if len(args.matches) == 1 and ':' in args.matches[0]:
        home, away = args.matches[0].split(':')
        matches.append((home.strip(), away.strip()))
    elif len(args.matches) == 2 and ':' not in args.matches[0]:
        matches.append((args.matches[0], args.matches[1]))
    else:
        for match_str in args.matches:
            if ':' in match_str:
                home, away = match_str.split(':')
                matches.append((home.strip(), away.strip()))
            else:
                print(f"❌ Format invalide: {match_str}. Utilisez HOME:AWAY", file=sys.stderr)
                return 1
    
    # Instancier l'OddsAPIClient si --with-odds (réutilisé pour tous les matchs)
    odds_client = None
    if args.with_odds:
        try:
            config = load_config(args.config)
            api_key = config.get('apis', {}).get('odds_api', {}).get('key', '')
            sport_key = config.get('apis', {}).get('odds_api', {}).get('sport', 'basketball_nba')
            if not api_key:
                print(f"⚠️  config.yaml apis.odds_api.key vide → --with-odds désactivé", file=sys.stderr)
            else:
                odds_client = OddsAPIClient(api_key=api_key, sport_key=sport_key)
                if not args.silent:
                    print(f"💰 The-Odds API configuré (sport={sport_key})", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  Échec init The-Odds API : {e} → --with-odds désactivé", file=sys.stderr)
    
    # Prédire
    if len(matches) == 1:
        line = args.lines[0] if args.lines else None
        result = predict_match(
            matches[0][0], 
            matches[0][1], 
            line, 
            args.date, 
            args.silent,
            auto_analyze=not args.no_auto_analyze,
            min_confidence=args.min_confidence,
            with_odds=args.with_odds and odds_client is not None,
            odds_client=odds_client,
        )
    else:
        result = {
            'matches': predict_multiple(
                matches, 
                args.lines, 
                args.date, 
                args.silent,
                auto_analyze=not args.no_auto_analyze,
                min_confidence=args.min_confidence,
                with_odds=args.with_odds and odds_client is not None,
                odds_client=odds_client,
            ),
            'count': len(matches)
        }
    
    # Formater et afficher
    json_str = json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(json_str)
        if not args.silent:
            print(f"✓ Résultats sauvegardés: {args.output}", file=sys.stderr)
    else:
        print(json_str)
    
    return 0 if 'error' not in result else 1


if __name__ == "__main__":
    sys.exit(main())
