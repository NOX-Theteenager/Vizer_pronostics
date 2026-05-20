"""
team_state.py — Reconstruit l'état actuel (forme récente) de chaque équipe NHL.

Pour prédire un match FUTUR (qui n'est pas dans le dataset), on a besoin des
features rolling les plus récentes de chaque équipe. Ce module extrait, depuis
le dataset agrégé, le dernier état connu de chaque équipe (ses moyennes mobiles
xGF, PP, forme, etc. à son dernier match joué).

Limitation importante : la fraîcheur des prédictions dépend de la fraîcheur du
dataset agrégé. Pour prédire les matchs de CE SOIR avec les stats à jour, il
faut avoir relancé les notebooks 01-02 récemment. Sinon, on utilise les
dernières stats disponibles (souvent suffisant : la forme d'équipe bouge
lentement sur quelques jours).
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from ..utils import normalize_team_code


class TeamStateBuilder:
    """
    Construit et stocke l'état (features individuelles) le plus récent de
    chaque équipe à partir du dataset agrégé.

    Le dataset stocke les features par match en colonnes _home / _away. Pour
    reconstruire l'état d'une équipe, on prend son dernier match (qu'il soit
    à domicile ou à l'extérieur) et on extrait ses features individuelles en
    retirant le suffixe.
    """

    def __init__(self, date_col: str = 'gameDate_home'):
        self.date_col = date_col
        # team_code → {feature_individuelle: valeur}
        self.team_latest: Dict[str, Dict[str, float]] = {}
        # Liste des features individuelles disponibles (sans suffixe)
        self.individual_features: List[str] = []
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> "TeamStateBuilder":
        """
        Parcourt le dataset et mémorise, pour chaque équipe, ses features
        individuelles au dernier match connu.
        """
        df = df.sort_values(self.date_col).reset_index(drop=True)

        # Identifier les colonnes _home et _away (paires individuelles)
        home_cols = [c for c in df.columns if c.endswith('_home')]
        away_cols = [c for c in df.columns if c.endswith('_away')]

        # Features individuelles = base des colonnes _home (sans suffixe),
        # en excluant les colonnes méta ET les colonnes non-numériques
        # (le dataset Moneypuck contient des colonnes texte comme opposingTeam_home,
        #  playerTeam_home, situation_home, etc. qu'il ne faut pas traiter en features).
        meta_prefixes = ('team', 'gameId', 'gameDate', 'finalGoals',
                         'goals_p1', 'home_team_won', 'season',
                         'opposingTeam', 'playerTeam', 'name', 'position',
                         'situation', 'home_or_away')
        individual = []
        for c in home_cols:
            base = c[:-len('_home')]
            if any(base.startswith(m) or base == m for m in meta_prefixes):
                continue
            # La paire _away doit exister
            if f'{base}_away' not in df.columns:
                continue
            # CRITIQUE : ne garder que les colonnes numériques (évite les strings type 'T.B')
            if not pd.api.types.is_numeric_dtype(df[c]):
                continue
            if not pd.api.types.is_numeric_dtype(df[f'{base}_away']):
                continue
            individual.append(base)
        self.individual_features = individual

        # Pour chaque ligne (chronologique), mettre à jour l'état des 2 équipes
        # Les codes sont normalisés (T.B → TBL) pour matcher l'Odds API.
        for _, row in df.iterrows():
            home_team = row.get('team_home')
            away_team = row.get('team_away')

            if home_team is not None and not pd.isna(home_team):
                state_h = {}
                for base in individual:
                    col = f'{base}_home'
                    if col in row and not pd.isna(row[col]):
                        state_h[base] = float(row[col])
                if state_h:
                    self.team_latest[normalize_team_code(str(home_team))] = state_h

            if away_team is not None and not pd.isna(away_team):
                state_a = {}
                for base in individual:
                    col = f'{base}_away'
                    if col in row and not pd.isna(row[col]):
                        state_a[base] = float(row[col])
                if state_a:
                    self.team_latest[normalize_team_code(str(away_team))] = state_a

        self._fitted = True
        return self

    def has_team(self, team_code: str) -> bool:
        return team_code in self.team_latest

    def build_matchup_row(
        self,
        home_team: str,
        away_team: str,
    ) -> Optional[pd.DataFrame]:
        """
        Reconstruit une ligne brute (colonnes _home / _away) pour un matchup,
        à partir de l'état le plus récent de chaque équipe.

        Returns:
            DataFrame d'une ligne avec les colonnes individuelles _home/_away
            + team_home/team_away (pour l'Elo) + gameDate_home (date du jour).
            None si une des équipes est inconnue.
        """
        if not self._fitted:
            raise RuntimeError("TeamStateBuilder non fitted. Appeler fit(df).")

        # Normaliser les entrées (au cas où on reçoit 'T.B' au lieu de 'TBL')
        home_team = normalize_team_code(home_team)
        away_team = normalize_team_code(away_team)

        if home_team not in self.team_latest or away_team not in self.team_latest:
            return None

        state_h = self.team_latest[home_team]
        state_a = self.team_latest[away_team]

        row: Dict[str, float] = {}
        for base in self.individual_features:
            if base in state_h:
                row[f'{base}_home'] = state_h[base]
            if base in state_a:
                row[f'{base}_away'] = state_a[base]

        # Méta pour l'Elo + transform
        row['team_home'] = home_team
        row['team_away'] = away_team
        row['gameDate_home'] = pd.Timestamp.now().strftime('%Y-%m-%d')

        return pd.DataFrame([row])

    @property
    def known_teams(self) -> List[str]:
        return sorted(self.team_latest.keys())
