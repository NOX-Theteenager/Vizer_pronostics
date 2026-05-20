"""
Client pour The-Odds API (https://the-odds-api.com/).

Récupère les cotes (moneyline + totals) pour les matchs NBA du jour.
Cache local dans `odds_cache/YYYY-MM-DD.json` pour économiser les crédits API
(450/mois sur le plan gratuit).

API doc : https://the-odds-api.com/liveapi/guides/v4/

Mapping noms NBA → abréviations 3-lettres hardcodé ci-dessous pour ne pas
dépendre de NBA_TEAMS.csv (les noms officiels sont stables).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import requests


# Mapping nom complet → abréviation 3-lettres (utilisée par le modèle).
# Source : NBA officiel, stable depuis ~2014.
TEAM_NAME_TO_ABBR: dict[str, str] = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC",
    "LA Clippers": "LAC",          # variante observée
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}


# Mapping inverse : abréviation → nom complet (pour l'affichage).
ABBR_TO_TEAM_NAME: dict[str, str] = {}
for _name, _abbr in TEAM_NAME_TO_ABBR.items():
    ABBR_TO_TEAM_NAME.setdefault(_abbr, _name)
ABBR_TO_TEAM_NAME["LAC"] = "Los Angeles Clippers"  # nom canonique


def code_to_team_name(code: str) -> str:
    """Convertit une abréviation en nom complet, ou retourne le code si inconnu."""
    return ABBR_TO_TEAM_NAME.get(code, code)


@dataclass
class TotalsLine:
    """Une ligne O/U avec ses cotes over et under."""
    line: float
    over_odds: float
    under_odds: float


@dataclass
class TeamTotalLine:
    """Une ligne O/U sur les points d'une équipe seule."""
    team_full_name: str         # nom complet retourné par The-Odds
    line: float
    over_odds: float
    under_odds: float


@dataclass
class BookmakerOdds:
    """Cotes d'un bookmaker précis pour un match."""
    bookmaker: str
    moneyline_home: Optional[float] = None
    moneyline_away: Optional[float] = None
    totals: list[TotalsLine] = field(default_factory=list)
    # Étape 6 : team totals (un par équipe, parfois plusieurs lignes alternatives)
    team_totals: list[TeamTotalLine] = field(default_factory=list)

    def best_total_line(self) -> Optional[TotalsLine]:
        """Retourne la ligne O/U principale (souvent celle avec cotes ~1.90)."""
        if not self.totals:
            return None
        return min(self.totals, key=lambda t: abs(t.over_odds - 1.91))

    def best_team_total_line(self, team_full_name: str) -> Optional[TeamTotalLine]:
        """Retourne la ligne team total principale pour une équipe donnée."""
        team_lines = [t for t in self.team_totals if t.team_full_name == team_full_name]
        if not team_lines:
            return None
        return min(team_lines, key=lambda t: abs(t.over_odds - 1.91))


@dataclass
class GameOdds:
    """Cotes agrégées pour un match."""
    home: str                    # abréviation 3 lettres
    away: str
    commence_time: str           # ISO datetime
    home_full: str               # nom complet (debug)
    away_full: str
    bookmakers: list[BookmakerOdds] = field(default_factory=list)

    def best_moneyline_odds(self) -> tuple[Optional[float], Optional[float]]:
        """Best line shopping : retourne (best_home_odds, best_away_odds)."""
        ml_homes = [b.moneyline_home for b in self.bookmakers if b.moneyline_home]
        ml_aways = [b.moneyline_away for b in self.bookmakers if b.moneyline_away]
        return (max(ml_homes) if ml_homes else None,
                max(ml_aways) if ml_aways else None)

    def consensus_total_line(self) -> Optional[float]:
        """Médiane des lignes O/U principales entre bookmakers."""
        lines = []
        for b in self.bookmakers:
            main = b.best_total_line()
            if main:
                lines.append(main.line)
        if not lines:
            return None
        lines.sort()
        return lines[len(lines) // 2]

    def best_over_under_odds(self, line: float) -> tuple[Optional[float], Optional[float]]:
        """Best line shopping pour over/under sur une ligne donnée."""
        overs, unders = [], []
        for b in self.bookmakers:
            for t in b.totals:
                if abs(t.line - line) < 0.01:
                    overs.append(t.over_odds)
                    unders.append(t.under_odds)
        return (max(overs) if overs else None,
                max(unders) if unders else None)

    # ========================================== Étape 6 : team totals
    def consensus_team_total_line(self, side: str) -> Optional[float]:
        """
        Médiane des lignes team-total principales entre bookmakers pour un côté.

        Args:
            side : 'home' ou 'away'.
        """
        if side == 'home':
            team_name = self.home_full
        elif side == 'away':
            team_name = self.away_full
        else:
            raise ValueError(f"side doit être 'home' ou 'away', reçu {side!r}")

        lines = []
        for b in self.bookmakers:
            main = b.best_team_total_line(team_name)
            if main:
                lines.append(main.line)
        if not lines:
            return None
        lines.sort()
        return lines[len(lines) // 2]

    def best_team_over_under_odds(
        self,
        side: str,
        line: float,
    ) -> tuple[Optional[float], Optional[float]]:
        """Best line shopping pour over/under team-total sur une ligne donnée."""
        if side == 'home':
            team_name = self.home_full
        elif side == 'away':
            team_name = self.away_full
        else:
            raise ValueError(f"side doit être 'home' ou 'away', reçu {side!r}")

        overs, unders = [], []
        for b in self.bookmakers:
            for t in b.team_totals:
                if t.team_full_name == team_name and abs(t.line - line) < 0.01:
                    overs.append(t.over_odds)
                    unders.append(t.under_odds)
        return (max(overs) if overs else None,
                max(unders) if unders else None)


class OddsAPIError(Exception):
    """Erreur lors d'un appel The-Odds API."""


class OddsAPIClient:
    """
    Client The-Odds API avec cache local.

    Usage :
        client = OddsAPIClient(api_key='aaea...', sport_key='basketball_nba')
        games = client.get_odds()  # liste de GameOdds, cachée par jour
    """

    BASE_URL = "https://api.the-odds-api.com/v4"

    def __init__(
        self,
        api_key: str,
        sport_key: str = "basketball_nba",
        cache_dir: str | Path = "odds_cache",
        cache_ttl_minutes: int = 60,
    ):
        if not api_key:
            raise ValueError("api_key vide. Renseigner config.yaml apis.odds_api.key")
        self.api_key = api_key
        self.sport_key = sport_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)

    # ================================================================ API
    def get_odds(
        self,
        markets: list[str] = ("h2h", "totals", "team_totals"),
        regions: str = "us",
        force_refresh: bool = False,
    ) -> list[GameOdds]:
        """
        Récupère les cotes pour les prochains matchs.

        Args:
            markets : marchés demandés ('h2h', 'totals', 'spreads')
            regions : régions des bookmakers ('us', 'eu', 'uk', ...)
            force_refresh : ignore le cache local.

        Returns:
            Liste de GameOdds (1 par match upcoming/live).
        """
        cache_path = self._cache_path()
        if not force_refresh and self._is_cache_fresh(cache_path):
            print(f"📋 Cotes lues depuis cache : {cache_path}", file=sys.stderr)
            with cache_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        else:
            try:
                payload = self._fetch_api(markets=list(markets), regions=regions)
                with cache_path.open("w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                print(f"💾 Cotes sauvegardées : {cache_path}", file=sys.stderr)
            except OddsAPIError as e:
                # Fallback : utiliser le cache existant (même périmé) si dispo
                if cache_path.exists():
                    print(f"⚠️  Réseau indisponible ({e}).", file=sys.stderr)
                    print(f"📋 Repli sur le cache existant : {cache_path}", file=sys.stderr)
                    with cache_path.open("r", encoding="utf-8") as f:
                        payload = json.load(f)
                else:
                    raise

        return [self._parse_game(g) for g in payload]

    def get_odds_for_match(
        self,
        home_abbr: str,
        away_abbr: str,
        **kwargs,
    ) -> Optional[GameOdds]:
        """Récupère les cotes pour un match précis (par abréviations)."""
        games = self.get_odds(**kwargs)
        for g in games:
            if g.home == home_abbr.upper() and g.away == away_abbr.upper():
                return g
        return None

    # ============================================================== Privé
    def _cache_path(self) -> Path:
        """Cache par jour : odds_cache/YYYY-MM-DD.json"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.cache_dir / f"{self.sport_key}_{today}.json"

    def _is_cache_fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        return age < self.cache_ttl

    def _fetch_api(self, markets: list[str], regions: str) -> list[dict]:
        """Appel HTTP brut à The-Odds API."""
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
                        wait = 2 ** attempt  # 1s, 2s
                        print(f"⏳ Tentative {attempt+1}/3 échouée, retry dans {wait}s...",
                              file=sys.stderr)
                        _t.sleep(wait)
            else:
                raise OddsAPIError(f"Erreur réseau (3 tentatives) : {last_exc}") from last_exc
        except requests.RequestException as e:
            raise OddsAPIError(f"Erreur réseau : {e}") from e

        if r.status_code == 401:
            raise OddsAPIError("Clé API invalide (401)")
        if r.status_code == 429:
            raise OddsAPIError("Quota dépassé (429). Voir https://the-odds-api.com/account/")
        if r.status_code != 200:
            raise OddsAPIError(f"HTTP {r.status_code} : {r.text[:200]}")

        # Affiche les crédits restants (header retourné par l'API)
        remaining = r.headers.get("x-requests-remaining")
        used = r.headers.get("x-requests-used")
        if remaining:
            print(f"🔑 The-Odds API : {used} utilisés, {remaining} restants",
                  file=sys.stderr)

        return r.json()

    @staticmethod
    def _parse_game(raw: dict) -> GameOdds:
        """Convertit la réponse brute d'un match en GameOdds."""
        home_full = raw.get("home_team", "")
        away_full = raw.get("away_team", "")
        home_abbr = TEAM_NAME_TO_ABBR.get(home_full, "???")
        away_abbr = TEAM_NAME_TO_ABBR.get(away_full, "???")

        bookmakers = []
        for bk_raw in raw.get("bookmakers", []):
            bk = BookmakerOdds(bookmaker=bk_raw.get("title", "?"))
            for mkt in bk_raw.get("markets", []):
                key = mkt.get("key")
                outcomes = mkt.get("outcomes", [])
                if key == "h2h":
                    for o in outcomes:
                        name = o.get("name", "")
                        price = o.get("price")
                        if name == home_full:
                            bk.moneyline_home = price
                        elif name == away_full:
                            bk.moneyline_away = price
                elif key == "totals":
                    # outcomes contient Over + Under pour chaque point
                    by_point: dict[float, dict] = {}
                    for o in outcomes:
                        point = o.get("point")
                        if point is None:
                            continue
                        by_point.setdefault(point, {})[o.get("name")] = o.get("price")
                    for point, side_prices in by_point.items():
                        bk.totals.append(TotalsLine(
                            line=float(point),
                            over_odds=float(side_prices.get("Over", 0)),
                            under_odds=float(side_prices.get("Under", 0)),
                        ))
                elif key == "team_totals":
                    # outcomes : { name: Over|Under, description: team_full_name,
                    #              point: line, price: odds }
                    # Grouper par (team, line) puis assembler les lignes
                    by_team_line: dict[tuple[str, float], dict] = {}
                    for o in outcomes:
                        team = o.get("description", "")
                        point = o.get("point")
                        side_name = o.get("name", "")  # "Over" ou "Under"
                        price = o.get("price")
                        if not team or point is None or not price:
                            continue
                        key_tl = (team, float(point))
                        by_team_line.setdefault(key_tl, {})[side_name] = float(price)
                    for (team, point), prices in by_team_line.items():
                        if "Over" in prices and "Under" in prices:
                            bk.team_totals.append(TeamTotalLine(
                                team_full_name=team,
                                line=point,
                                over_odds=prices["Over"],
                                under_odds=prices["Under"],
                            ))
            bookmakers.append(bk)

        return GameOdds(
            home=home_abbr,
            away=away_abbr,
            commence_time=raw.get("commence_time", ""),
            home_full=home_full,
            away_full=away_full,
            bookmakers=bookmakers,
        )
