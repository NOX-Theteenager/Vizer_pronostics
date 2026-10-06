"""
Script pour récupérer les statistiques des joueurs par match
ATTENTION: Ce dataset est très volumineux (peut prendre 30-60 minutes)

Reprise après interruption : les sauvegardes intermédiaires
(data/NBA_PLAYER_GAMES_TEMP.csv, tous les 50 joueurs) sont relues au
démarrage et les joueurs déjà récupérés sont sautés. Sans ça, une
interruption — PC éteint, coupure réseau — faisait repartir de zéro, et le
cron hebdomadaire ne publiait jamais rien : c'est ce qui s'est passé le
16 août 2026, arrêt à 314/530 et dataset Kaggle figé pendant sept semaines.
Pour forcer un fetch complet : --no-resume.
"""
import pandas as pd
import time
from datetime import datetime
from nba_api.stats.endpoints import playergamelog
from nba_api.stats.static import players
import sys
import os

def recent_seasons(n: int = 2):
    """Retourne les n dernières saisons NBA au format 'YYYY-YY' (dynamique)."""
    now = datetime.now()
    end_year = now.year if now.month >= 7 else now.year - 1
    return [f"{y}-{str(y + 1)[-2:]}" for y in range(end_year - n + 1, end_year + 1)]


TEMP_PATH = 'data/NBA_PLAYER_GAMES_TEMP.csv'
# Au-delà de ce délai, la sauvegarde intermédiaire est jetée. Reprendre depuis
# un fichier ancien sauterait des joueurs dont les matchs ont été joués entre
# les deux runs — à cheval sur un début de saison, on publierait un dataset
# amputé sans le voir. Le cron est hebdomadaire : une reprise légitime arrive
# dans les heures qui suivent, jamais après plusieurs jours.
TEMP_MAX_AGE_HOURS = 36


def _load_resume_state(resume: bool):
    """Relit la sauvegarde intermédiaire. Retourne (frames, ids_déjà_faits).

    Toute anomalie de lecture est traitée comme « pas de reprise » : repartir
    de zéro coûte du temps, repartir d'un fichier corrompu coûte un dataset.
    """
    if not resume or not os.path.exists(TEMP_PATH):
        return [], set()
    age_h = (time.time() - os.path.getmtime(TEMP_PATH)) / 3600
    if age_h > TEMP_MAX_AGE_HOURS:
        print(f"⚠️  {TEMP_PATH} date de {age_h / 24:.1f} jour(s) "
              f"(> {TEMP_MAX_AGE_HOURS}h) — ignoré, fetch complet.")
        return [], set()
    try:
        temp_df = pd.read_csv(TEMP_PATH)
        if 'Player_ID' not in temp_df.columns or temp_df.empty:
            print(f"⚠️  {TEMP_PATH} inutilisable (colonnes inattendues) — fetch complet.")
            return [], set()
        done = set(temp_df['Player_ID'].unique())
        print(f"♻️  Reprise depuis {TEMP_PATH} : {len(done)} joueurs déjà "
              f"récupérés ({len(temp_df):,} lignes) — ils seront sautés.")
        return [temp_df], done
    except Exception as e:
        print(f"⚠️  Lecture de {TEMP_PATH} impossible ({e}) — fetch complet.")
        return [], set()


def fetch_player_games(seasons=None, active_only=True, resume=True):
    """
    Récupère les stats des joueurs par match

    Args:
        seasons: Liste des saisons à récupérer (défaut: 2 dernières, dynamique)
        active_only: Si True, récupère uniquement les joueurs actifs
        resume: Si True, reprend depuis la sauvegarde intermédiaire existante
    """
    if seasons is None:
        seasons = recent_seasons(2)
    
    print("=" * 70)
    print("RÉCUPÉRATION DES STATS JOUEURS PAR MATCH")
    print("=" * 70)
    print(f"Saisons: {', '.join(seasons)}")
    print(f"Mode: {'Joueurs actifs uniquement' if active_only else 'Tous les joueurs'}")
    print()
    
    # Récupérer la liste des joueurs
    if active_only:
        print("📥 Récupération des joueurs actifs...", end=" ", flush=True)
        player_list = players.get_active_players()
    else:
        print("📥 Récupération de tous les joueurs...", end=" ", flush=True)
        player_list = players.get_players()
    
    print(f"✓ {len(player_list)} joueurs")
    
    all_games, already_done = _load_resume_state(resume)
    errors = []
    skipped = 0
    
    total_players = len(player_list)
    
    for idx, player in enumerate(player_list, 1):
        player_id = player['id']
        player_name = player['full_name']

        if player_id in already_done:
            skipped += 1
            continue

        print(f"[{idx}/{total_players}] {player_name}...", end=" ", flush=True)
        
        player_games = []
        
        for season in seasons:
            try:
                # Récupérer les stats du joueur pour la saison
                gamelog = playergamelog.PlayerGameLog(
                    player_id=player_id,
                    season=season,
                    season_type_all_star='Regular Season'
                )
                
                games_df = gamelog.get_data_frames()[0]
                
                if not games_df.empty:
                    player_games.append(games_df)
                
                # Pause pour respecter les limites de l'API
                time.sleep(0.6)
                
            except Exception as e:
                if "not found" not in str(e).lower():
                    errors.append(f"{player_name} ({season}): {str(e)}")
                continue
        
        if player_games:
            combined = pd.concat(player_games, ignore_index=True)
            all_games.append(combined)
            print(f"✓ {len(combined)} matchs")
        else:
            print("⊘ Aucun match")
        
        # Sauvegarde intermédiaire tous les 50 joueurs
        if idx % 50 == 0 and all_games:
            print(f"\n💾 Sauvegarde intermédiaire ({idx} joueurs traités)...")
            temp_df = pd.concat(all_games, ignore_index=True)
            temp_df.to_csv(TEMP_PATH, index=False)

    if skipped:
        print(f"\n♻️  {skipped} joueur(s) sautés (déjà dans la reprise).")

    if not all_games:
        print("\n✗ Aucune donnée récupérée!")
        return None
    
    # Combiner toutes les données
    print("\n📊 Combinaison des données...")
    combined_df = pd.concat(all_games, ignore_index=True)
    # La reprise peut réintroduire des lignes déjà présentes si un joueur a été
    # sauvegardé deux fois (interruption juste après un flush).
    if {'Player_ID', 'Game_ID'} <= set(combined_df.columns):
        before = len(combined_df)
        combined_df = combined_df.drop_duplicates(subset=['Player_ID', 'Game_ID'])
        if before != len(combined_df):
            print(f"  ✓ {before - len(combined_df):,} doublon(s) retiré(s)")
    
    # Trier par date
    if 'GAME_DATE' in combined_df.columns:
        combined_df['GAME_DATE'] = pd.to_datetime(combined_df['GAME_DATE'])
        combined_df = combined_df.sort_values('GAME_DATE')
    
    # Statistiques
    print("\n" + "=" * 70)
    print("RÉSUMÉ")
    print("=" * 70)
    print(f"Total d'entrées:        {len(combined_df):,}")
    print(f"Joueurs uniques:        {combined_df['Player_ID'].nunique() if 'Player_ID' in combined_df.columns else 'N/A'}")
    print(f"Matchs uniques:         {combined_df['Game_ID'].nunique() if 'Game_ID' in combined_df.columns else 'N/A'}")
    print(f"Colonnes:               {len(combined_df.columns)}")
    
    if errors:
        print(f"\n⚠ {len(errors)} erreurs rencontrées")
        if len(errors) <= 10:
            for error in errors:
                print(f"  • {error}")
    
    return combined_df


def save_dataset(df, output_path='data/NBA_PLAYER_GAMES.csv'):
    """Sauvegarde le dataset"""
    
    # Créer une sauvegarde de l'ancien fichier si il existe
    if os.path.exists(output_path):
        backup_path = f'data/NBA_PLAYER_GAMES_OLD_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        print(f"\n💾 Sauvegarde ancien fichier: {backup_path}")
        os.rename(output_path, backup_path)
    
    # Sauvegarder le nouveau dataset
    df.to_csv(output_path, index=False)
    print(f"💾 Nouveau dataset sauvegardé: {output_path}")
    
    # Afficher la taille du fichier
    file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
    print(f"📦 Taille du fichier: {file_size:.2f} MB")
    
    # Supprimer le fichier temporaire si il existe
    if os.path.exists(TEMP_PATH):
        os.remove(TEMP_PATH)
        print("🗑️  Fichier temporaire supprimé")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Récupérer les stats des joueurs par match')
    parser.add_argument('--seasons', nargs='+', default=None,
                        help='Saisons à récupérer (défaut: 2 dernières, auto-détectées)')
    parser.add_argument('--all-players', action='store_true',
                        help='Récupérer tous les joueurs (pas seulement les actifs)')
    parser.add_argument('--no-resume', action='store_true',
                        help='Ignorer la sauvegarde intermédiaire et tout refetcher')
    
    args = parser.parse_args()
    
    print()
    print("⚠️  ATTENTION: Ce script peut prendre 30-60 minutes selon le nombre de saisons")
    print()
    
    df = fetch_player_games(
        seasons=args.seasons,
        active_only=not args.all_players,
        resume=not args.no_resume,
    )
    
    if df is not None:
        save_dataset(df)
        print("\n" + "=" * 70)
        print("✅ TERMINÉ AVEC SUCCÈS")
        print("=" * 70)
        print()
    else:
        print("\n" + "=" * 70)
        print("❌ ÉCHEC")
        print("=" * 70)
        print()
        sys.exit(1)
