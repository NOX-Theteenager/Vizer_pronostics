#!/usr/bin/env python
"""
export_performance.py — Mesure ce que valent réellement les prédictions.

La question à laquelle ce script répond n'est pas « comment s'en sort
l'utilisateur » — ça, c'est l'écran Historique, qui ne voit que les paris
suivis — mais « le modèle a-t-il raison », sur **toutes** les prédictions
publiées, y compris celles que personne n'a suivies.

Source : la jointure de `predictions/archive/` et de `results/`. Ce sont des
prédictions publiées avant le coup d'envoi puis confrontées au score réel,
donc une mesure hors échantillon et hors rétrospective — plus honnête que
n'importe quelle métrique calculée à l'entraînement.

Deux pièges, traités explicitement
----------------------------------
1. **Déduplication.** Le même match à venir est republié chaque jour : 2 605
   entrées d'archive ne font qu'une centaine de matchs réels. On ne retient
   qu'une prédiction par match — la dernière publiée **avant** le coup
   d'envoi, c'est-à-dire la plus informée dont l'utilisateur disposait.
2. **Abstention.** Un marché dont on ne sait pas déterminer l'issue sans
   ambiguïté n'est pas compté. Mêmes règles que la clôture des paris côté
   PWA (`vizer_web/src/lib/settle.ts`) : ligne entière tombée pile, score
   exact ou intervalle après prolongation.

Sortie : `performance/summary.json`.

Usage :
    python scripts/export_performance.py --root /tmp/pub
    python scripts/export_performance.py --root /tmp/pub --min-sample 30
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

SPORTS = ('nhl', 'nba')

# Un marché n'est affiché que si l'échantillon dépasse ce seuil. Un taux de
# réussite sur douze matchs n'est pas une mesure, c'est du bruit — et affiché
# sans effectif, c'est une invitation à se tromper.
DEFAULT_MIN_SAMPLE = 20

OVER_UNDER = re.compile(r'^(over|under)_(-?\d+(?:\.\d+)?)$')
EXACT = re.compile(r'^(\d+)-(\d+)$')


# ── Issues réalisées ────────────────────────────────────────────────────────
#
# Pour chaque marché, quelle clé de probabilité s'est réalisée ? `None` =
# abstention. Ces règles doublent celles de `settle.ts` ; les deux doivent
# rester alignées, et c'est le seul endroit du projet où cette logique existe
# deux fois.

def _ou_key(value: float, keys: list[str]) -> Optional[str]:
    """Résout un marché over/under à partir des clés publiées."""
    for key in keys:
        m = OVER_UNDER.match(key)
        if not m:
            continue
        line = float(m.group(2))
        if value == line:
            return None  # ligne tombée pile : mise rendue, rien à mesurer
        return f'over_{m.group(2)}' if value > line else f'under_{m.group(2)}'
    return None


def realised(market: str, keys: list[str], result: dict) -> Optional[str]:
    """Clé réalisée pour ce marché, ou None si indécidable."""
    home, away = result['home_score'], result['away_score']
    total = home + away
    periods = result.get('periods') or []
    p1 = periods[0] if periods else None
    overtime = bool(result.get('overtime'))

    if market in ('moneyline', 'win'):
        if home == away:
            return None
        return 'home' if home > away else 'away'

    if market == 'total':
        return _ou_key(total, keys)

    if market == 'btts':
        return 'yes' if home > 0 and away > 0 else 'no'

    if market == 'home_team_total':
        return _ou_key(home, keys)

    if market == 'away_team_total':
        return _ou_key(away, keys)

    if market == 'p1_winner':
        if p1 is None:
            return None
        if p1['home'] > p1['away']:
            return 'home_lead'
        if p1['away'] > p1['home']:
            return 'away_lead'
        return 'tied'

    if market == 'p1_total':
        return None if p1 is None else _ou_key(p1['home'] + p1['away'], keys)

    if market == 'p1_btts':
        if p1 is None:
            return None
        return 'yes' if p1['home'] > 0 and p1['away'] > 0 else 'no'

    if market == 'exact_score':
        # Après prolongation, le score final ne correspond plus à ce que le
        # marché modélise (temps réglementaire).
        return None if overtime else f'{home}-{away}'

    if market == 'goal_intervals':
        if overtime:
            return None
        for key in keys:
            if key.endswith('+'):
                if total >= int(key[:-1]):
                    return key
                continue
            m = EXACT.match(key)
            if m and int(m.group(1)) <= total <= int(m.group(2)):
                return key
        return None

    return None


# ── Collecte ────────────────────────────────────────────────────────────────

def game_id(sport: str, game: dict) -> str:
    return f"{sport}-{game['away']}@{game['home']}-{(game.get('commence_time') or '')[:10]}"


def last_predictions(root: pathlib.Path, sport: str) -> dict[str, dict]:
    """
    Dernière prédiction publiée avant le coup d'envoi, par match.

    Le feed porte `generated_at` : on ne garde une entrée que si elle a été
    produite avant le début du match — sinon on mesurerait une prédiction
    faite alors que le résultat était déjà connu.
    """
    best: dict[str, tuple[str, dict]] = {}
    archive = root / 'predictions' / 'archive'
    if not archive.is_dir():
        return {}

    for day in sorted(archive.iterdir()):
        path = day / f'{sport}.json'
        if not path.is_file():
            continue
        try:
            feed = json.loads(path.read_text())
        except ValueError:
            continue
        generated = feed.get('generated_at') or ''
        for game in feed.get('games') or []:
            start = game.get('commence_time') or ''
            if not start or (generated and generated >= start):
                continue
            gid = game_id(sport, game)
            if gid not in best or generated > best[gid][0]:
                best[gid] = (generated, game)

    return {gid: game for gid, (_, game) in best.items()}


def load_results(root: pathlib.Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    folder = root / 'results'
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob('*.json')):
        if path.name == 'latest.json':
            continue
        try:
            payload = json.loads(path.read_text())
        except ValueError:
            continue
        for g in payload.get('games') or []:
            key = f"{g['sport']}-{g['away']}@{g['home']}-{(g.get('commence_time') or '')[:10]}"
            out[key] = g
    return out


# ── Agrégats ────────────────────────────────────────────────────────────────

class MarketStats:
    """Justesse, Brier, log-loss et calibration d'un marché."""

    def __init__(self) -> None:
        self.n = 0
        self.hits = 0
        self.brier = 0.0
        self.logloss = 0.0
        # Calibration sur la probabilité attribuée à l'issue la plus probable.
        self.buckets: dict[int, list[float]] = defaultdict(list)

    def add(self, probs: dict[str, float], actual: str) -> None:
        if actual not in probs:
            return
        self.n += 1
        top = max(probs, key=lambda k: probs[k])
        if top == actual:
            self.hits += 1

        # Brier multiclasse : somme des écarts au vecteur one-hot.
        self.brier += sum((p - (1.0 if k == actual else 0.0)) ** 2 for k, p in probs.items())
        p_actual = max(min(probs[actual], 1 - 1e-9), 1e-9)
        self.logloss += -math.log(p_actual)

        bucket = min(9, int(probs[top] * 10))
        self.buckets[bucket].append(1.0 if top == actual else 0.0)

    def to_dict(self, min_sample: int) -> Optional[dict[str, Any]]:
        if self.n < min_sample:
            return {'n': self.n, 'insufficient': True}
        return {
            'n': self.n,
            'accuracy': round(self.hits / self.n, 4),
            'brier': round(self.brier / self.n, 4),
            'log_loss': round(self.logloss / self.n, 4),
            'calibration': [
                {
                    'from': round(b / 10, 1),
                    'to': round((b + 1) / 10, 1),
                    'n': len(vals),
                    'actual': round(sum(vals) / len(vals), 4),
                }
                for b, vals in sorted(self.buckets.items())
                if len(vals) >= 5  # un point de calibration sur 2 cas ne dit rien
            ],
        }


class BetStats:
    """Rendement des value bets, à mise plate et à la fraction publiée."""

    def __init__(self) -> None:
        self.n = 0
        self.won = 0
        self.flat_profit = 0.0
        self.kelly_stake = 0.0
        self.kelly_profit = 0.0
        self.edge_sum = 0.0
        # Désaccord entre le modèle et le consensus de marché, quand les deux
        # sont publiés. C'est la quantité qui décide du plafond de sélection :
        # la suivre permet de vérifier que le plafond est au bon endroit.
        self.gap_sum = 0.0
        self.gap_n = 0

    def add(self, odds: float, kelly: float, won: bool, edge: float,
            gap: Optional[float] = None) -> None:
        self.n += 1
        self.edge_sum += edge
        if gap is not None:
            self.gap_sum += gap
            self.gap_n += 1
        if won:
            self.won += 1
            self.flat_profit += odds - 1
            self.kelly_profit += kelly * (odds - 1)
        else:
            self.flat_profit -= 1
            self.kelly_profit -= kelly
        self.kelly_stake += kelly

    def to_dict(self, min_sample: int) -> dict[str, Any]:
        if self.n < min_sample:
            return {'n': self.n, 'insufficient': True}
        return {
            'n': self.n,
            'won': self.won,
            'hit_rate': round(self.won / self.n, 4),
            'avg_edge': round(self.edge_sum / self.n, 4),
            # Mise plate : une unité par pari. C'est le rendement comparable
            # d'un marché à l'autre.
            'roi_flat': round(self.flat_profit / self.n, 4),
            # Kelly : rapporté au capital effectivement engagé, sinon un
            # marché peu misé paraîtrait artificiellement performant.
            'roi_kelly': (
                round(self.kelly_profit / self.kelly_stake, 4) if self.kelly_stake else None
            ),
            'avg_disagreement': (
                round(self.gap_sum / self.gap_n, 4) if self.gap_n else None
            ),
        }


def analyse(root: pathlib.Path, min_sample: int) -> dict[str, Any]:
    results = load_results(root)
    out: dict[str, Any] = {}

    for sport in SPORTS:
        preds = last_predictions(root, sport)
        markets: dict[str, MarketStats] = defaultdict(MarketStats)
        bets = BetStats()
        bets_by_market: dict[str, BetStats] = defaultdict(BetStats)
        matched = 0
        dates: list[str] = []

        for gid, game in preds.items():
            result = results.get(gid)
            if not result:
                continue
            matched += 1
            dates.append((game.get('commence_time') or '')[:10])

            for market, entry in (game.get('predictions') or {}).items():
                probs = (entry or {}).get('probabilities')
                if not isinstance(probs, dict) or not probs:
                    continue
                clean = {k: float(v) for k, v in probs.items()
                         if isinstance(v, (int, float))}
                if not clean:
                    continue
                actual = realised(market, list(clean), result)
                if actual is not None:
                    markets[market].add(clean, actual)

            for vb in game.get('value_bets') or []:
                market = vb.get('market')
                selection = vb.get('selection')
                odds = vb.get('bookmaker_odds')
                if not market or not selection or not isinstance(odds, (int, float)):
                    continue
                # La ligne vient de la **sélection pariée**, pas du marché.
                # Le marché publie ses probabilités sur une ligne par défaut
                # (5.5 buts), alors qu'un value bet porte sur la ligne du
                # bookmaker (6.0, 6.5…). Résoudre contre la ligne du marché
                # déclarait perdants des paris gagnants — un match à 5 buts
                # est bien sous 6.0, même s'il est au-dessus de 5.5.
                actual = realised(market, [selection], result)
                if actual is None:
                    continue
                kelly = float(vb.get('kelly_stake') or vb.get('kelly_stake_fraction') or 0)
                edge = float(vb.get('edge') or 0)
                won = actual == selection
                # Publié depuis l'ajout du consensus de marché ; absent des
                # archives antérieures, d'où la moyenne sur les seuls paris
                # qui le portent.
                model_p, market_p = vb.get('model_proba'), vb.get('market_proba')
                gap = (
                    float(model_p) - float(market_p)
                    if isinstance(model_p, (int, float)) and isinstance(market_p, (int, float))
                    else None
                )
                bets.add(float(odds), kelly, won, edge, gap)
                bets_by_market[market].add(float(odds), kelly, won, edge, gap)

        out[sport] = {
            'n_games_predicted': len(preds),
            'n_games_settled': matched,
            'from': min(dates) if dates else None,
            'to': max(dates) if dates else None,
            'markets': {m: s.to_dict(min_sample) for m, s in sorted(markets.items())},
            'value_bets': bets.to_dict(min_sample),
            'value_bets_by_market': {
                m: s.to_dict(min_sample) for m, s in sorted(bets_by_market.items())
            },
        }

    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Performance réelle des prédictions publiées.")
    ap.add_argument('--root', required=True,
                    help="Racine contenant predictions/archive/ et results/")
    ap.add_argument('--out', default=None,
                    help="Fichier de sortie (défaut : <root>/performance/summary.json)")
    ap.add_argument('--min-sample', type=int, default=DEFAULT_MIN_SAMPLE)
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    out = pathlib.Path(args.out) if args.out else root / 'performance' / 'summary.json'
    out.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'min_sample': args.min_sample,
        'sports': analyse(root, args.min_sample),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    for sport, s in payload['sports'].items():
        print(f"  {sport.upper()} : {s['n_games_settled']}/{s['n_games_predicted']} matchs "
              f"appariés · {len(s['markets'])} marché(s)", file=sys.stderr)
    print(f"✅ {out}", file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
