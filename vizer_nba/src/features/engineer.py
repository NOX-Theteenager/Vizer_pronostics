"""
Feature Engineering pour la prédiction de matchs NBA

Crée des features à partir des données brutes pour améliorer les prédictions.
"""
import pandas as pd
import numpy as np
from typing import List, Tuple


class MatchFeatureEngineer:
    """Crée des features pour prédire le résultat d'un match"""
    
    def __init__(self, windows: List[int] = [5, 10, 20]):
        """
        Args:
            windows: Fenêtres pour les moyennes mobiles (ex: [5, 10, 20] derniers matchs)
        """
        self.windows = windows
    
    def prepare_match_data(self, games_df: pd.DataFrame) -> pd.DataFrame:
        """
        Prépare les données pour l'entraînement du modèle
        
        Transforme le format "2 lignes par match" en "1 ligne par match"
        avec les stats des deux équipes
        """
        # Supprimer les doublons dans les données sources (évite l'explosion du merge)
        df = games_df.drop_duplicates(subset=['GAME_ID', 'TEAM_ID']).copy()
        
        # Trier par date
        df = df.sort_values('GAME_DATE').copy()
        
        # Séparer équipes à domicile et à l'extérieur
        home_games = df[df['MATCHUP'].str.contains(' vs. ')].copy()
        away_games = df[df['MATCHUP'].str.contains(' @ ')].copy()
        
        # Renommer les colonnes pour différencier home/away
        home_games = home_games.add_prefix('HOME_')
        away_games = away_games.add_prefix('AWAY_')
        
        # Merger sur GAME_ID
        matches = home_games.merge(
            away_games,
            left_on='HOME_GAME_ID',
            right_on='AWAY_GAME_ID',
            how='inner'
        )
        
        # Garder les colonnes importantes
        matches = matches[[
            'HOME_GAME_ID', 'HOME_GAME_DATE', 'HOME_SEASON_ID',
            'HOME_TEAM_ID', 'HOME_TEAM_ABBREVIATION',
            'AWAY_TEAM_ID', 'AWAY_TEAM_ABBREVIATION',
            'HOME_WL', 'HOME_PTS', 'AWAY_PTS',
            'HOME_FG_PCT', 'AWAY_FG_PCT',
            'HOME_FG3_PCT', 'AWAY_FG3_PCT',
            'HOME_FT_PCT', 'AWAY_FT_PCT',
            'HOME_REB', 'AWAY_REB',
            'HOME_AST', 'AWAY_AST',
            'HOME_STL', 'AWAY_STL',
            'HOME_BLK', 'AWAY_BLK',
            'HOME_TOV', 'AWAY_TOV',
        ]].copy()
        
        # Renommer pour simplifier
        matches = matches.rename(columns={
            'HOME_GAME_ID': 'GAME_ID',
            'HOME_GAME_DATE': 'GAME_DATE',
            'HOME_SEASON_ID': 'SEASON_ID',
        })
        
        # Créer la target (1 si home gagne, 0 sinon)
        matches['HOME_WIN'] = (matches['HOME_WL'] == 'W').astype(int)
        
        # Calculer les métriques avancées pour chaque équipe (Four Factors & Pace)
        # eFG% = (FGM + 0.5 * FG3M) / FGA
        # TOV% = TOV / (FGA + 0.44 * FTA + TOV)
        # FT Rate = FTA / FGA
        # Possessions (approx) = FGA + 0.44 * FTA - OREB + TOV
        
        # Charger les données brutes pour récupérer les stats manquantes (FGM, FGA, etc.)
        raw_stats = games_df.copy()
        raw_stats = raw_stats[['GAME_ID', 'TEAM_ID', 'FGM', 'FGA', 'FG3M', 'FTA', 'OREB', 'DREB', 'TOV']]
        
        # Merger avec les stats home
        matches = matches.merge(
            raw_stats.add_prefix('H_'),
            left_on=['GAME_ID', 'HOME_TEAM_ID'],
            right_on=['H_GAME_ID', 'H_TEAM_ID'],
            how='left'
        )
        
        # Merger avec les stats away
        matches = matches.merge(
            raw_stats.add_prefix('A_'),
            left_on=['GAME_ID', 'AWAY_TEAM_ID'],
            right_on=['A_GAME_ID', 'A_TEAM_ID'],
            how='left'
        )
        
        # Calculer les métriques
        for p in ['H', 'A']:
            prefix = 'HOME' if p == 'H' else 'AWAY'
            
            # eFG%
            matches[f'{prefix}_EFG_PCT'] = (matches[f'{p}_FGM'] + 0.5 * matches[f'{p}_FG3M']) / matches[f'{p}_FGA']
            
            # TOV%
            matches[f'{prefix}_TOV_PCT'] = matches[f'{p}_TOV'] / (matches[f'{p}_FGA'] + 0.44 * matches[f'{p}_FTA'] + matches[f'{p}_TOV'])
            
            # FT Rate
            matches[f'{prefix}_FT_RATE'] = matches[f'{p}_FTA'] / matches[f'{p}_FGA']
            
            # Possessions (approx)
            matches[f'{prefix}_POSS'] = matches[f'{p}_FGA'] + 0.44 * matches[f'{p}_FTA'] - matches[f'{p}_OREB'] + matches[f'{p}_TOV']
            
            # Off Rating (Points per 100 possessions)
            matches[f'{prefix}_OFF_RATING'] = (matches[f'{prefix}_PTS'] / matches[f'{prefix}_POSS']) * 100

        # Def Rating (Points concédés par 100 possessions de l'équipe)
        # HOME_DEF_RATING : combien d'efficacement away marque contre home
        # AWAY_DEF_RATING : combien d'efficacement home marque contre away
        # NOTE: ces stats sont du match courant (leakage), à mettre dans exclude_cols.
        matches['HOME_DEF_RATING'] = (matches['AWAY_PTS'] / matches['HOME_POSS']) * 100
        matches['AWAY_DEF_RATING'] = (matches['HOME_PTS'] / matches['AWAY_POSS']) * 100

        # Nettoyer les colonnes temporaires
        temp_cols = [c for c in matches.columns if c.startswith('H_') or c.startswith('A_')]
        matches = matches.drop(columns=temp_cols)
        
        return matches
    
    def add_rolling_features(
        self, 
        matches_df: pd.DataFrame,
        games_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Ajoute des features basées sur les performances récentes
        
        Args:
            matches_df: DataFrame avec 1 ligne par match
            games_df: DataFrame brut avec toutes les stats
            
        Returns:
            DataFrame avec features de moyennes mobiles
        """
        df = matches_df.copy()
        
        # Trier les matchs par équipe et date
        games_sorted = games_df.sort_values(['TEAM_ID', 'GAME_DATE']).copy()
        
        # Stats à calculer
        stats = [
            'PTS', 'FG_PCT', 'FG3_PCT', 'FT_PCT', 'REB', 'AST', 'STL', 'BLK', 'TOV',
            'EFG_PCT', 'TOV_PCT', 'FT_RATE', 'POSS', 'OFF_RATING', 'DEF_RATING'
        ]

        # Calculer les métriques avancées dans games_df avant de faire les moyennes mobiles
        games_sorted['EFG_PCT'] = (games_sorted['FGM'] + 0.5 * games_sorted['FG3M']) / games_sorted['FGA']
        games_sorted['TOV_PCT'] = games_sorted['TOV'] / (games_sorted['FGA'] + 0.44 * games_sorted['FTA'] + games_sorted['TOV'])
        games_sorted['FT_RATE'] = games_sorted['FTA'] / games_sorted['FGA']
        games_sorted['POSS'] = games_sorted['FGA'] + 0.44 * games_sorted['FTA'] - games_sorted['OREB'] + games_sorted['TOV']
        games_sorted['OFF_RATING'] = (games_sorted['PTS'] / games_sorted['POSS']) * 100

        # DEF_RATING : points concédés par 100 possessions de l'équipe
        # PTS_AGAINST = somme PTS du match (2 équipes) - PTS de l'équipe (vectorisé)
        games_sorted['PTS_AGAINST'] = (
            games_sorted.groupby('GAME_ID')['PTS'].transform('sum') - games_sorted['PTS']
        )
        games_sorted['DEF_RATING'] = (games_sorted['PTS_AGAINST'] / games_sorted['POSS']) * 100
        
        # Pour chaque fenêtre
        for window in self.windows:
            for stat in stats:
                # Calculer la moyenne mobile pour chaque équipe
                games_sorted[f'{stat}_AVG_{window}G'] = (
                    games_sorted.groupby('TEAM_ID')[stat]
                    .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
                )
        
        # Créer un dictionnaire pour lookup rapide
        team_stats = {}
        for _, row in games_sorted.iterrows():
            key = (row['TEAM_ID'], row['GAME_DATE'])
            team_stats[key] = row
        
        # Ajouter les stats aux matchs
        for window in self.windows:
            for stat in stats:
                # Stats équipe à domicile
                df[f'HOME_{stat}_AVG_{window}G'] = df.apply(
                    lambda x: team_stats.get(
                        (x['HOME_TEAM_ID'], x['GAME_DATE']), {}
                    ).get(f'{stat}_AVG_{window}G', np.nan),
                    axis=1
                )
                
                # Stats équipe à l'extérieur
                df[f'AWAY_{stat}_AVG_{window}G'] = df.apply(
                    lambda x: team_stats.get(
                        (x['AWAY_TEAM_ID'], x['GAME_DATE']), {}
                    ).get(f'{stat}_AVG_{window}G', np.nan),
                    axis=1
                )
        
        return df
    
    def add_head_to_head_features(
        self,
        matches_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Ajoute des features basées sur l'historique des confrontations directes
        
        Args:
            matches_df: DataFrame avec 1 ligne par match
            
        Returns:
            DataFrame avec features head-to-head
        """
        df = matches_df.copy()
        
        # Initialiser les colonnes
        df['H2H_HOME_WINS'] = 0
        df['H2H_TOTAL_GAMES'] = 0
        df['H2H_HOME_WIN_PCT'] = 0.5  # Valeur par défaut
        
        # Pour chaque match, calculer l'historique H2H
        for idx in range(len(df)):
            current_match = df.iloc[idx]
            home_team = current_match['HOME_TEAM_ID']
            away_team = current_match['AWAY_TEAM_ID']
            current_date = current_match['GAME_DATE']
            
            # Trouver tous les matchs précédents entre ces équipes
            previous_h2h = df[
                (df['GAME_DATE'] < current_date) &
                (
                    ((df['HOME_TEAM_ID'] == home_team) & (df['AWAY_TEAM_ID'] == away_team)) |
                    ((df['HOME_TEAM_ID'] == away_team) & (df['AWAY_TEAM_ID'] == home_team))
                )
            ]
            
            if len(previous_h2h) > 0:
                # Compter les victoires de l'équipe à domicile actuelle
                home_wins = len(previous_h2h[
                    ((previous_h2h['HOME_TEAM_ID'] == home_team) & (previous_h2h['HOME_WIN'] == 1)) |
                    ((previous_h2h['AWAY_TEAM_ID'] == home_team) & (previous_h2h['HOME_WIN'] == 0))
                ])
                
                total_games = len(previous_h2h)
                
                df.at[idx, 'H2H_HOME_WINS'] = home_wins
                df.at[idx, 'H2H_TOTAL_GAMES'] = total_games
                df.at[idx, 'H2H_HOME_WIN_PCT'] = home_wins / total_games if total_games > 0 else 0.5
        
        return df
    
    def add_rest_days(
        self,
        matches_df: pd.DataFrame,
        games_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Ajoute des features sur les jours de repos
        
        Args:
            matches_df: DataFrame avec 1 ligne par match
            games_df: DataFrame brut avec tous les matchs
            
        Returns:
            DataFrame avec features de repos
        """
        df = matches_df.copy()
        
        # Trier par équipe et date
        games_sorted = games_df.sort_values(['TEAM_ID', 'GAME_DATE']).copy()
        games_sorted['GAME_DATE'] = pd.to_datetime(games_sorted['GAME_DATE'])
        
        # Calculer les jours de repos (différence entre dates de matchs consécutifs)
        games_sorted['PREV_GAME_DATE'] = games_sorted.groupby('TEAM_ID')['GAME_DATE'].shift(1)
        games_sorted['REST_DAYS'] = (games_sorted['GAME_DATE'] - games_sorted['PREV_GAME_DATE']).dt.days
        
        # Clipper à 10 jours max pour éviter les outliers (intersaison)
        games_sorted['REST_DAYS'] = games_sorted['REST_DAYS'].clip(upper=10)
        
        # Créer un dictionnaire pour lookup rapide
        rest_dict = {}
        for _, row in games_sorted.iterrows():
            key = (row['TEAM_ID'], row['GAME_DATE'].strftime('%Y-%m-%d'))
            rest_dict[key] = row['REST_DAYS']
        
        # S'assurer que GAME_DATE est au bon format pour le lookup
        df_dates = pd.to_datetime(df['GAME_DATE']).dt.strftime('%Y-%m-%d')
        
        # Ajouter aux matchs
        df['HOME_REST_DAYS'] = [
            rest_dict.get((tid, d), 5) # 5 par défaut (premier match)
            for tid, d in zip(df['HOME_TEAM_ID'], df_dates)
        ]
        
        df['AWAY_REST_DAYS'] = [
            rest_dict.get((tid, d), 5)
            for tid, d in zip(df['AWAY_TEAM_ID'], df_dates)
        ]
        
        # Feature binaire back-to-back (1 jour de repos ou moins)
        df['HOME_B2B'] = (df['HOME_REST_DAYS'] <= 1).astype(int)
        df['AWAY_B2B'] = (df['AWAY_REST_DAYS'] <= 1).astype(int)
        
        return df

    def calculate_player_values(self, player_games: pd.DataFrame) -> pd.DataFrame:
        """
        Calcule une valeur d'impact pour chaque joueur par match (Score Fantasy-style)
        """
        df = player_games.copy()
        # Formule simplifiée d'impact: PTS + 1.2*REB + 1.5*AST + 2*STL + 2*BLK - 1.5*TOV
        df['PLAYER_VAL'] = (
            df['PTS'] + 
            1.2 * df['REB'] + 
            1.5 * df['AST'] + 
            2.0 * df['STL'] + 
            2.0 * df['BLK'] - 
            1.5 * df['TOV']
        )
        
        # Calculer la moyenne mobile de la valeur du joueur (10 derniers matchs)
        df = df.sort_values(['Player_ID', 'GAME_DATE'])
        df['PLAYER_VAL_AVG_10G'] = (
            df.groupby('Player_ID')['PLAYER_VAL']
            .transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean())
        )
        return df

    def add_talent_features(
        self, 
        matches_df: pd.DataFrame, 
        player_games: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calcule le ratio de talent disponible pour chaque équipe.

        ⚠️  HISTORIQUE : la version précédente déterminait l'équipe (HOME/AWAY) d'un
            joueur en croisant son `WL` avec `HOME_WIN`, ce qui constituait une
            fuite de données (target leak) ayant gonflé l'accuracy à 90.6%.
            La version actuelle utilise UNIQUEMENT la colonne `MATCHUP` du joueur,
            au format "LAL vs. GSW" (HOME) ou "LAL @ GSW" (AWAY). Aucune référence
            à la cible ni au TEAM_ID du joueur (qui n'est pas dans le CSV).
        """
        print("👤 Analyse fine du talent par équipe...")
        # Normaliser Game_ID → GAME_ID (le CSV joueur est en CamelCase pour les IDs)
        player_df = player_games.copy()
        if 'Game_ID' in player_df.columns and 'GAME_ID' not in player_df.columns:
            player_df = player_df.rename(columns={'Game_ID': 'GAME_ID'})

        # Garde-fou : MATCHUP est indispensable pour déterminer le côté sans leakage
        if 'MATCHUP' not in player_df.columns:
            available = sorted(player_df.columns.tolist())
            raise KeyError(
                f"Colonne MATCHUP introuvable dans player_games. "
                f"Nécessaire pour déterminer HOME/AWAY sans leakage. "
                f"Colonnes disponibles : {available}"
            )

        player_df = self.calculate_player_values(player_df)

        # Détermination du côté via MATCHUP (sans leakage)
        # Même convention que prepare_match_data : ' vs. ' = HOME, ' @ ' = AWAY
        is_home = player_df['MATCHUP'].str.contains(' vs. ', regex=False, na=False)
        is_away = player_df['MATCHUP'].str.contains(' @ ', regex=False, na=False)

        invalid_mask = ~(is_home | is_away)
        n_invalid = int(invalid_mask.sum())
        if n_invalid > 0:
            print(f"  ⚠️ {n_invalid} lignes joueur avec MATCHUP au format inattendu — filtrées.")
            player_df = player_df[~invalid_mask].copy()
            is_home = is_home[~invalid_mask]

        player_df['SIDE'] = np.where(is_home, 'HOME', 'AWAY')

        # Talent agrégé par match × côté (somme des PLAYER_VAL_AVG_10G)
        match_talent = (
            player_df.groupby(['GAME_ID', 'SIDE'])['PLAYER_VAL_AVG_10G']
            .sum()
            .unstack()
        )
        # Garantir la présence des deux colonnes
        for side in ('HOME', 'AWAY'):
            if side not in match_talent.columns:
                match_talent[side] = np.nan
        match_talent = match_talent.rename(
            columns={'HOME': 'HOME_ACTUAL_TALENT', 'AWAY': 'AWAY_ACTUAL_TALENT'}
        ).reset_index()

        # Fusion avec matches_df
        df = matches_df.copy()
        df = df.merge(match_talent, on='GAME_ID', how='left')

        # Normalisation : ratio = talent actuel / médiane équipe-saison
        for side in ('HOME', 'AWAY'):
            col = f'{side}_ACTUAL_TALENT'
            team_col = f'{side}_TEAM_ID'
            normal_talent = df.groupby(['SEASON_ID', team_col])[col].transform('median')
            df[f'{side}_TALENT_RATIO'] = (df[col] / normal_talent).fillna(1.0).clip(0.5, 1.5)

        # Nettoyage
        df = df.drop(columns=['HOME_ACTUAL_TALENT', 'AWAY_ACTUAL_TALENT'], errors='ignore')
        return df

    def add_season_pace_feature(self, matches_df: pd.DataFrame) -> pd.DataFrame:
        """
        Ajoute SEASON_AVG_TOTAL : moyenne expanding du total marqué dans la saison
        courante, calculée à partir des matchs déjà joués avant le match en cours.

        Cette feature absorbe le distribution shift inter-saisons : elle dit au
        modèle "à quel niveau on score cette saison" sans avoir à le déduire des
        moyennes par équipe.

        Anti-leakage : on shift(1) avant expanding, donc le match courant
        n'entre jamais dans son propre prior. Pour le premier match d'une saison
        (NaN après shift), on utilise la moyenne de la saison précédente.
        """
        df = matches_df.copy()
        df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])

        # Assurer TOTAL_PTS (peut être absent si appelé avant train.py)
        if 'TOTAL_PTS' not in df.columns:
            df['TOTAL_PTS'] = df['HOME_PTS'] + df['AWAY_PTS']

        # Mémoriser l'ordre d'origine pour le restaurer après tri
        df['_orig_idx'] = np.arange(len(df))

        # Trier par (saison, date) puis calculer expanding mean avec shift(1)
        df = df.sort_values(['SEASON_ID', 'GAME_DATE'])
        df['SEASON_AVG_TOTAL'] = (
            df.groupby('SEASON_ID')['TOTAL_PTS']
            .transform(lambda x: x.shift(1).expanding().mean())
        )

        # Prior pour le premier match de chaque saison : moyenne de la saison N-1
        season_means = df.groupby('SEASON_ID')['TOTAL_PTS'].mean()
        season_prior = season_means.shift(1)
        # Pour la première saison (NaN), utiliser sa propre moyenne comme fallback
        season_prior = season_prior.fillna(season_means.iloc[0])

        df['SEASON_AVG_TOTAL'] = df['SEASON_AVG_TOTAL'].fillna(
            df['SEASON_ID'].map(season_prior)
        )
        # Dernier filet de sécurité
        df['SEASON_AVG_TOTAL'] = df['SEASON_AVG_TOTAL'].fillna(df['TOTAL_PTS'].mean())

        # Restaurer l'ordre d'origine
        df = df.sort_values('_orig_idx').drop(columns='_orig_idx').reset_index(drop=True)
        return df

    def create_features(
        self,
        games_df: pd.DataFrame,
        player_games_df: pd.DataFrame = None,
        include_h2h: bool = True
    ) -> pd.DataFrame:
        """
        Pipeline complet de création de features
        """
        print("🔧 Préparation des données...")
        matches = self.prepare_match_data(games_df)
        print(f"  ✓ {len(matches):,} matchs préparés")
        
        if player_games_df is not None:
            matches = self.add_talent_features(matches, player_games_df)
            print(f"  ✓ Features de talent ajoutées")

        print("📅 Calcul du niveau de scoring saisonnier (SEASON_AVG_TOTAL)...")
        matches = self.add_season_pace_feature(matches)
        print(f"  ✓ Feature SEASON_AVG_TOTAL ajoutée")

        print("📊 Calcul des jours de repos...")
        matches = self.add_rest_days(matches, games_df)
        print(f"  ✓ Features de repos ajoutées")
        
        print("📊 Calcul des moyennes mobiles...")
        matches = self.add_rolling_features(matches, games_df)
        print(f"  ✓ Features de moyennes mobiles ajoutées")
        
        if include_h2h:
            print("🤝 Calcul des confrontations directes...")
            matches = self.add_head_to_head_features(matches)
            print(f"  ✓ Features head-to-head ajoutées")
        
        # Supprimer les lignes avec trop de NaN
        initial_len = len(matches)
        matches = matches.dropna(subset=[col for col in matches.columns if '_AVG_' in col])
        print(f"  ℹ {initial_len - len(matches)} matchs supprimés (données insuffisantes)")
        
        print(f"\n✅ Features créées: {len(matches):,} matchs, {len(matches.columns)} colonnes")
        
        return matches


if __name__ == "__main__":
    # Test rapide
    from src.data.loader import NBADataLoader
    
    print("Test du Feature Engineer")
    print("=" * 50)
    
    # Charger les données
    loader = NBADataLoader()
    games = loader.load_games()
    print(f"✓ {len(games):,} matchs chargés")
    
    # Prendre un échantillon pour tester
    sample = games[games['SEASON_ID'] >= 22023].copy()  # Saisons 2023-24 et après
    print(f"✓ Échantillon: {len(sample):,} entrées")
    
    # Créer les features
    engineer = MatchFeatureEngineer(windows=[5, 10])
    features_df = engineer.create_features(sample, include_h2h=False)
    
    print(f"\n✅ Test réussi!")
    print(f"Shape finale: {features_df.shape}")
    print(f"\nPremières colonnes:")
    print(features_df.columns[:20].tolist())
