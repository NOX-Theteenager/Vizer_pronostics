"""
Script de validation de la cohérence des datasets NBA
"""
import pandas as pd
import sys

def validate_datasets():
    """Valide la cohérence entre tous les datasets"""
    
    print("=" * 70)
    print("VALIDATION DES DATASETS NBA")
    print("=" * 70)
    print()
    
    errors = []
    warnings = []
    
    # 1. Charger les datasets
    print("📂 Chargement des datasets...")
    try:
        teams = pd.read_csv('data/NBA_TEAMS.csv')
        print(f"  ✓ NBA_TEAMS.csv: {len(teams)} équipes")
    except Exception as e:
        errors.append(f"Impossible de charger NBA_TEAMS.csv: {e}")
        teams = None
    
    try:
        players = pd.read_csv('data/NBA_PLAYERS.csv')
        print(f"  ✓ NBA_PLAYERS.csv: {len(players):,} joueurs")
    except Exception as e:
        errors.append(f"Impossible de charger NBA_PLAYERS.csv: {e}")
        players = None
    
    try:
        active_players = pd.read_csv('data/NBA_ACTIVE_PLAYERS.csv')
        print(f"  ✓ NBA_ACTIVE_PLAYERS.csv: {len(active_players)} joueurs actifs")
    except Exception as e:
        warnings.append(f"Impossible de charger NBA_ACTIVE_PLAYERS.csv: {e}")
        active_players = None
    
    try:
        games = pd.read_csv('data/NBA_GAMES.csv')
        print(f"  ✓ NBA_GAMES.csv: {len(games):,} entrées")
    except Exception as e:
        errors.append(f"Impossible de charger NBA_GAMES.csv: {e}")
        games = None
    
    try:
        player_games = pd.read_csv('data/NBA_PLAYER_GAMES.csv')
        print(f"  ✓ NBA_PLAYER_GAMES.csv: {len(player_games):,} entrées")
    except Exception as e:
        warnings.append(f"Impossible de charger NBA_PLAYER_GAMES.csv: {e}")
        player_games = None
    
    print()
    
    # 2. Validation des équipes
    if teams is not None:
        print("🏀 Validation des équipes...")
        
        if len(teams) != 30:
            warnings.append(f"Nombre d'équipes incorrect: {len(teams)} (attendu: 30)")
        else:
            print("  ✓ 30 équipes présentes")
        
        required_cols = ['id', 'full_name', 'abbreviation']
        missing = [col for col in required_cols if col not in teams.columns]
        if missing:
            errors.append(f"Colonnes manquantes dans NBA_TEAMS.csv: {missing}")
        else:
            print("  ✓ Toutes les colonnes requises présentes")
        
        if teams['id'].duplicated().any():
            errors.append("IDs d'équipes dupliqués détectés")
        else:
            print("  ✓ Pas de doublons d'IDs")
        
        print()
    
    # 3. Validation des joueurs
    if players is not None:
        print("👤 Validation des joueurs...")
        
        required_cols = ['id', 'full_name', 'is_active']
        missing = [col for col in required_cols if col not in players.columns]
        if missing:
            errors.append(f"Colonnes manquantes dans NBA_PLAYERS.csv: {missing}")
        else:
            print("  ✓ Toutes les colonnes requises présentes")
        
        if players['id'].duplicated().any():
            errors.append("IDs de joueurs dupliqués détectés")
        else:
            print("  ✓ Pas de doublons d'IDs")
        
        active_count = players['is_active'].sum()
        print(f"  ℹ {active_count} joueurs actifs, {len(players) - active_count} inactifs")
        
        print()
    
    # 4. Validation joueurs actifs vs tous joueurs
    if players is not None and active_players is not None:
        print("🔗 Validation joueurs actifs...")
        
        active_in_all = players[players['is_active'] == True]
        
        if len(active_players) != len(active_in_all):
            warnings.append(
                f"Incohérence: {len(active_players)} dans NBA_ACTIVE_PLAYERS.csv "
                f"vs {len(active_in_all)} actifs dans NBA_PLAYERS.csv"
            )
        else:
            print(f"  ✓ Cohérence: {len(active_players)} joueurs actifs")
        
        # Vérifier que tous les IDs sont présents
        missing_ids = set(active_players['id']) - set(players['id'])
        if missing_ids:
            errors.append(f"{len(missing_ids)} joueurs actifs absents de NBA_PLAYERS.csv")
        else:
            print("  ✓ Tous les joueurs actifs sont dans NBA_PLAYERS.csv")
        
        print()
    
    # 5. Validation des matchs
    if games is not None:
        print("🏆 Validation des matchs...")
        
        required_cols = ['SEASON_ID', 'TEAM_ID', 'GAME_ID', 'GAME_DATE', 'WL', 'PTS']
        missing = [col for col in required_cols if col not in games.columns]
        if missing:
            errors.append(f"Colonnes manquantes dans NBA_GAMES.csv: {missing}")
        else:
            print("  ✓ Toutes les colonnes requises présentes")
        
        # Vérifier que chaque match a 2 équipes
        games_per_match = games.groupby('GAME_ID').size()
        invalid_games = games_per_match[games_per_match != 2]
        if len(invalid_games) > 0:
            warnings.append(f"{len(invalid_games)} matchs n'ont pas exactement 2 équipes")
        else:
            print(f"  ✓ Tous les matchs ont 2 équipes ({games['GAME_ID'].nunique():,} matchs)")
        
        # Vérifier W/L équilibré
        w_count = (games['WL'] == 'W').sum()
        l_count = (games['WL'] == 'L').sum()
        if abs(w_count - l_count) > 10:
            warnings.append(f"Déséquilibre W/L: {w_count} victoires vs {l_count} défaites")
        else:
            print(f"  ✓ W/L équilibré: {w_count} victoires, {l_count} défaites")
        
        # Vérifier les IDs d'équipes
        if teams is not None:
            unknown_teams = set(games['TEAM_ID']) - set(teams['id'])
            if unknown_teams:
                errors.append(f"{len(unknown_teams)} IDs d'équipes inconnus dans les matchs")
            else:
                print(f"  ✓ Tous les IDs d'équipes sont valides")
        
        print()
    
    # 6. Validation des stats joueurs
    if player_games is not None:
        print("📊 Validation des stats joueurs...")
        
        required_cols = ['Player_ID', 'Game_ID', 'PTS', 'MIN']
        missing = [col for col in required_cols if col not in player_games.columns]
        if missing:
            errors.append(f"Colonnes manquantes dans NBA_PLAYER_GAMES.csv: {missing}")
        else:
            print("  ✓ Toutes les colonnes requises présentes")
        
        # Vérifier les IDs de joueurs
        if players is not None:
            unknown_players = set(player_games['Player_ID']) - set(players['id'])
            if unknown_players:
                warnings.append(f"{len(unknown_players)} IDs de joueurs inconnus dans les stats")
            else:
                print(f"  ✓ Tous les IDs de joueurs sont valides")
        
        # Vérifier les IDs de matchs
        if games is not None:
            # Normaliser les noms de colonnes
            game_id_col = 'Game_ID' if 'Game_ID' in player_games.columns else 'GAME_ID'
            unknown_games = set(player_games[game_id_col]) - set(games['GAME_ID'])
            if unknown_games:
                warnings.append(f"{len(unknown_games)} IDs de matchs inconnus dans les stats joueurs")
            else:
                print(f"  ✓ Tous les IDs de matchs sont valides")
        
        print()
    
    # 7. Résumé
    print("=" * 70)
    print("RÉSUMÉ DE LA VALIDATION")
    print("=" * 70)
    
    if errors:
        print(f"\n❌ {len(errors)} ERREUR(S) CRITIQUE(S):")
        for error in errors:
            print(f"  • {error}")
    
    if warnings:
        print(f"\n⚠️  {len(warnings)} AVERTISSEMENT(S):")
        for warning in warnings:
            print(f"  • {warning}")
    
    if not errors and not warnings:
        print("\n✅ TOUS LES DATASETS SONT VALIDES ET COHÉRENTS")
    
    print()
    
    return len(errors) == 0


if __name__ == "__main__":
    success = validate_datasets()
    sys.exit(0 if success else 1)
