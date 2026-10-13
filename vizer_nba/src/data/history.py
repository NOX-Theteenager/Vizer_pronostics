"""
history.py — Forme récente et confrontations directes NBA.

`NBA_GAMES.csv` contient une ligne **par équipe et par match** (`GAME_ID`,
`TEAM_ABBREVIATION`, `MATCHUP`, `WL`, `PTS`). On recompose un match par
`GAME_ID` : la colonne `MATCHUP` dit qui recevait (« LAL vs. BOS » à domicile,
« LAL @ BOS » à l'extérieur).

Même contrat de sortie que `vizer_nhl/src/data/history.py` : la PWA ne fait
pas la différence entre les deux sports.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from .loader import normalize_team_abbreviation


class NBAMatchHistory:
    """Index compact des matchs passés, construit une fois au chargement."""

    def __init__(self, games: pd.DataFrame):
        self.games = self._build(games)

    @staticmethod
    def _build(df: pd.DataFrame) -> pd.DataFrame:
        cols = {'GAME_ID', 'TEAM_ABBREVIATION', 'MATCHUP', 'PTS', 'GAME_DATE'}
        empty = pd.DataFrame(columns=['date', 'home', 'away', 'home_score', 'away_score'])
        if not cols.issubset(df.columns):
            return empty

        d = df[list(cols)].copy()
        d['TEAM_ABBREVIATION'] = d['TEAM_ABBREVIATION'].map(
            lambda v: normalize_team_abbreviation(str(v))
        )
        d['PTS'] = pd.to_numeric(d['PTS'], errors='coerce')
        d['date'] = pd.to_datetime(d['GAME_DATE'], errors='coerce')
        # « vs. » = reçoit, « @ » = se déplace.
        d['at_home'] = d['MATCHUP'].astype(str).str.contains('vs', case=False, regex=False)
        d = d.dropna(subset=['PTS', 'date'])

        rows: list[dict[str, Any]] = []
        for _, pair in d.groupby('GAME_ID'):
            if len(pair) != 2:
                continue  # match incomplet dans le dataset
            home = pair[pair['at_home']]
            away = pair[~pair['at_home']]
            if len(home) != 1 or len(away) != 1:
                continue
            h, a = home.iloc[0], away.iloc[0]
            rows.append({
                'date': h['date'].strftime('%Y-%m-%d'),
                'home': h['TEAM_ABBREVIATION'],
                'away': a['TEAM_ABBREVIATION'],
                'home_score': int(h['PTS']),
                'away_score': int(a['PTS']),
            })

        if not rows:
            return empty
        return pd.DataFrame(rows).sort_values('date').reset_index(drop=True)

    # ------------------------------------------------------------------
    def recent_form(self, team: str, n: int = 5) -> Optional[dict[str, Any]]:
        """`n` derniers résultats, du plus ancien au plus récent."""
        code = normalize_team_abbreviation(str(team))
        g = self.games
        if g.empty:
            return None
        played = g[(g['home'] == code) | (g['away'] == code)].tail(n)
        if played.empty:
            return None

        results, pf, pa = [], 0, 0
        for _, row in played.iterrows():
            at_home = row['home'] == code
            scored = int(row['home_score'] if at_home else row['away_score'])
            conceded = int(row['away_score'] if at_home else row['home_score'])
            pf += scored
            pa += conceded
            # Pas de match nul en NBA.
            results.append('W' if scored > conceded else 'L')

        return {
            'results': results,
            'wins': results.count('W'),
            'draws': 0,
            'losses': results.count('L'),
            'goals_for': pf,
            'goals_against': pa,
        }

    # ------------------------------------------------------------------
    def head_to_head(self, home: str, away: str, n: int = 5) -> list[dict[str, Any]]:
        """Dernières confrontations, plus récente d'abord."""
        h = normalize_team_abbreviation(str(home))
        a = normalize_team_abbreviation(str(away))
        g = self.games
        if g.empty:
            return []
        mask = ((g['home'] == h) & (g['away'] == a)) | ((g['home'] == a) & (g['away'] == h))
        rows = g[mask].tail(n).iloc[::-1]

        out: list[dict[str, Any]] = []
        for _, row in rows.iterrows():
            hs, as_ = int(row['home_score']), int(row['away_score'])
            winner = row['home'] if hs > as_ else row['away'] if as_ > hs else None
            out.append({
                'date': row['date'],
                'home': row['home'],
                'away': row['away'],
                'home_score': hs,
                'away_score': as_,
                'winner': None if winner is None else ('home' if winner == h else 'away'),
            })
        return out
