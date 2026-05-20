"""
odds_client.py — Client The-Odds API pour la NHL.

Récupère les cotes (moneyline + totals de buts) pour les matchs NHL détectés.
Cache local dans `odds_cache/icehockey_nhl_YYYY-MM-DD.json` (économie de crédits).

The-Odds API NHL :
    sport_key = 'icehockey_nhl'
    markets   = 'h2h' (moneyline), 'totals' (over/under buts)
    Note : les markets P1/exact_score/goal_intervals ne sont PAS exposés par
    l'API standard. On ne peut croiser que moneyline + total avec des cotes
    réelles. Les autres markets restent "predict-only".

API doc : https://the-odds-api.com/liveapi/guides/v4/
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

from .team_state import TeamStateBuilder  # noqa: F401 (réexport utilitaire)


# ---------------------------------------------------------------------------
# Normalisation noms d'équipes The-Odds API → codes 3 lettres Moneypuck
# ---------------------------------------------------------------------------

TEAM_NAME_TO_CODE: dict[str, str] = {
    'Anaheim Ducks': 'ANA', 'Arizona Coyotes': 'ARI', 'Utah Hockey Club': 'ARI',
    'Utah Mammoth': 'ARI',
    'Boston Bruins': 'BOS', 'Buffalo Sabres': 'BUF', 'Calgary Flames': 'CGY',
    'Carolina Hurricanes': 'CAR', 'Chicago Blackhawks': 'CHI',
    'Colorado Avalanche': 'COL', 'Columbus Blue Jackets': 'CBJ',
    'Dallas Stars': 'DAL', 'Detroit Red Wings': 'DET', 'Edmonton Oilers': 'EDM',
    'Florida Panthers': 'FLA', 'Los Angeles Kings': 'LAK', 'Minnesota Wild': 'MIN',
    'Montreal Canadiens': 'MTL', 'Montréal Canadiens': 'MTL',
    'Nashville Predators': 'NSH', 'New Jersey Devils': 'NJD',
    'New York Islanders': 'NYI', 'New York Rangers': 'NYR',
    'Ottawa Senators': 'OTT', 'Philadelphia Flyers': 'PHI',
    'Pittsburgh Penguins': 'PIT', 'San Jose Sharks': 'SJS',
    'Seattle Kraken': 'SEA', 'St Louis Blues': 'STL', 'St. Louis Blues': 'STL',
    'Tampa Bay Lightning': 'TBL', 'Toronto Maple Leafs': 'TOR',
    'Vancouver Canucks': 'VAN', 'Vegas Golden Knights': 'VGK',
    'Washington Capitals': 'WSH', 'Winnipeg Jets': 'WPG',
}


def team_name_to_code(name: str) -> str:
    """Convertit un nom complet d'équipe en code 3 lettres, ou '???' si inconnu."""
    return TEAM_NAME_TO_CODE.get(name, '???')


# Mapping inverse code → nom complet (pour affichage lisible).
# On garde le premier nom rencontré par code (les alias comme 'Utah Hockey Club'
# pointent vers ARI mais on affiche le nom canonique).
CODE_TO_TEAM_NAME: dict[str, str] = {}
for _name, _code in TEAM_NAME_TO_CODE.items():
    CODE_TO_TEAM_NAME.setdefault(_code, _name)
# Forcer quelques noms canoniques
CODE_TO_TEAM_NAME.update({
    'ARI': 'Utah Hockey Club',
    'MTL': 'Montreal Canadiens',
    'STL': 'St. Louis Blues',
})


def code_to_team_name(code: str) -> str:
    """Convertit un code 3 lettres en nom complet, ou retourne le code si inconnu."""
    return CODE_TO_TEAM_NAME.get(code, code)


# Mapping inverse : code 3 lettres → nom complet (pour l'affichage).
# On garde le premier nom rencontré pour chaque code (les alias sont ignorés).
CODE_TO_TEAM_NAME: dict[str, str] = {}
for _name, _code in TEAM_NAME_TO_CODE.items():
    CODE_TO_TEAM_NAME.setdefault(_code, _name)
# Surcharges pour des noms canoniques propres
CODE_TO_TEAM_NAME.update({
    'ARI': 'Utah Hockey Club',
    'MTL': 'Montreal Canadiens',
    'STL': 'St. Louis Blues',
})


def code_to_team_name(code: str) -> str:
    """Convertit un code 3 lettres en nom complet, ou retourne le code si inconnu."""
    return CODE_TO_TEAM_NAME.get(code, code)


# ---------------------------------------------------------------------------
# Dataclasses cotes
# ---------------------------------------------------------------------------

@dataclass
class TotalsLine:
    """Une ligne over/under de buts proposée par un bookmaker."""
    point: float
    over_odds: float
    under_odds: float


@dataclass
class BookmakerOdds:
    """Cotes d'un bookmaker pour un match."""
    bookmaker: str
    home_ml: Optional[float] = None
    away_ml: Optional[float] = None
    totals: list[TotalsLine] = field(default_factory=list)


@dataclass
class GameOdds:
    """Cotes agrégées pour un match NHL (multi-bookmakers)."""
    home: str          # code 3 lettres
    away: str
    commence_time: str
    bookmakers: list[BookmakerOdds] = field(default_factory=list)

    def best_moneyline_odds(self) -> tuple[Optional[float], Optional[float]]:
        """Meilleure (plus haute) cote moneyline home/away parmi les books."""
        best_home = max((b.home_ml for b in self.bookmakers if b.home_ml), default=None)
        best_away = max((b.away_ml for b in self.bookmakers if b.away_ml), default=None)
        return best_home, best_away

    def consensus_total_line(self) -> Optional[float]:
        """Ligne totale consensus (médiane des points proposés par les books)."""
        points = [t.point for b in self.bookmakers for t in b.totals]
        if not points:
            return None
        points.sort()
        n = len(points)
        return points[n // 2] if n % 2 else (points[n // 2 - 1] + points[n // 2]) / 2

    def best_over_under_odds(self, line: float) -> tuple[Optional[float], Optional[float]]:
        """Meilleures cotes over/under pour une ligne donnée."""
        overs, unders = [], []
        for b in self.bookmakers:
            for t in b.totals:
                if abs(t.point - line) < 1e-6:
                    overs.append(t.over_odds)
                    unders.append(t.under_odds)
        best_over = max(overs) if overs else None
        best_under = max(unders) if unders else None
        return best_over, best_under


# ---------------------------------------------------------------------------
# Client API
# ---------------------------------------------------------------------------

class OddsAPIError(Exception):
    pass


class NHLOddsClient:
    """
    Client The-Odds API pour la NHL avec cache local.

    Usage :
        client = NHLOddsClient(api_key='aaea...')
        games = client.get_odds()   # liste de GameOdds, cachée par jour
    """

    BASE_URL = "https://api.the-odds-api.com/v4"

    def __init__(
        self,
        api_key: str,
        sport_key: str = "icehockey_nhl",
        cache_dir: str | Path = "odds_cache",
        cache_ttl_minutes: int = 60,
    ):
        self.api_key = api_key
        self.sport_key = sport_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)

    def _cache_path(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.cache_dir / f"{self.sport_key}_{today}.json"

    def _is_cache_fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        return age < self.cache_ttl

    def get_odds(
        self,
        markets: tuple[str, ...] = ("h2h", "totals"),
        regions: str = "us",
        force_refresh: bool = False,
    ) -> list[GameOdds]:
        """
        Récupère les cotes NHL (avec cache). Retourne une liste de GameOdds.
        """
        cache_path = self._cache_path()
        if not force_refresh and self._is_cache_fresh(cache_path):
            print(f"📋 Cotes NHL lues depuis cache : {cache_path}", file=sys.stderr)
            with cache_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        else:
            try:
                payload = self._fetch_api(markets=list(markets), regions=regions)
                with cache_path.open("w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                print(f"💾 Cotes NHL sauvegardées : {cache_path}", file=sys.stderr)
            except OddsAPIError as e:
                if cache_path.exists():
                    print(f"⚠️  Réseau indisponible ({e}).", file=sys.stderr)
                    print(f"📋 Repli sur le cache existant : {cache_path}", file=sys.stderr)
                    with cache_path.open("r", encoding="utf-8") as f:
                        payload = json.load(f)
                else:
                    raise

        return self._parse_payload(payload)

    def _fetch_api(self, markets: list[str], regions: str) -> list[dict]:
        url = f"{self.BASE_URL}/sports/{self.sport_key}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": ",".join(markets),
            "oddsFormat": "decimal",
        }
        try:
            last_exc = None
            for attempt in range(3):
                try:
                    r = requests.get(url, params=params, timeout=15)
                    break
                except requests.RequestException as e:
                    last_exc = e
                    if attempt < 2:
                        import time as _t
                        wait = 2 ** attempt
                        print(f"⏳ Tentative {attempt+1}/3 échouée, retry dans {wait}s...",
                              file=sys.stderr)
                        _t.sleep(wait)
            else:
                raise OddsAPIError(f"Erreur réseau (3 tentatives) : {last_exc}") from last_exc
        except requests.RequestException as e:
            raise OddsAPIError(f"Erreur réseau : {e}")
        if r.status_code == 401:
            raise OddsAPIError("Clé API invalide (401).")
        if r.status_code == 429:
            raise OddsAPIError("Quota dépassé (429). Voir https://the-odds-api.com/account/")
        if r.status_code != 200:
            raise OddsAPIError(f"Statut HTTP {r.status_code} : {r.text[:200]}")
        remaining = r.headers.get("x-requests-remaining")
        if remaining is not None:
            print(f"ℹ️  Crédits API restants : {remaining}", file=sys.stderr)
        return r.json()

    def _parse_payload(self, payload: list[dict]) -> list[GameOdds]:
        games: list[GameOdds] = []
        for game in payload:
            home_name = game.get("home_team", "")
            away_name = game.get("away_team", "")
            go = GameOdds(
                home=team_name_to_code(home_name),
                away=team_name_to_code(away_name),
                commence_time=game.get("commence_time", ""),
            )
            for bk in game.get("bookmakers", []):
                bo = BookmakerOdds(bookmaker=bk.get("key", "?"))
                for mkt in bk.get("markets", []):
                    key = mkt.get("key")
                    outcomes = mkt.get("outcomes", [])
                    if key == "h2h":
                        for o in outcomes:
                            name, price = o.get("name"), o.get("price")
                            if name == home_name:
                                bo.home_ml = price
                            elif name == away_name:
                                bo.away_ml = price
                    elif key == "totals":
                        # Regrouper Over/Under par point
                        by_point: dict[float, dict] = {}
                        for o in outcomes:
                            pt = o.get("point")
                            if pt is None:
                                continue
                            by_point.setdefault(pt, {})[o.get("name")] = o.get("price")
                        for pt, od in by_point.items():
                            if "Over" in od and "Under" in od:
                                bo.totals.append(TotalsLine(
                                    point=float(pt),
                                    over_odds=float(od["Over"]),
                                    under_odds=float(od["Under"]),
                                ))
                go.bookmakers.append(bo)
            games.append(go)
        return games
