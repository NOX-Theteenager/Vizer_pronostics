"""
direction_guard.py — Détecte un marché qui ne parie que dans un sens.

Le problème
-----------
Le marché `total` du NHL a publié **39 paris, tous `under`, aucun `over`**. Son
rendement mesuré était de +11,6 %, et ce chiffre a servi à le réactiver. Il
était trompeur : un marché qui ne mise jamais que d'un côté ne produit pas
trente-neuf paris indépendants, il produit **un seul pari directionnel joué
trente-neuf fois**. Son ROI ne mesure pas une compétence de sélection, il
mesure si le dé est tombé du bon côté.

La cause mesurée : le modèle prédisait 5,73 buts en moyenne contre 6,05
réellement marqués, et se situait **sous la ligne du marché sur 38 des 39
matchs**, de 0,54 but en moyenne. Ce n'est pas une sélection d'opportunités,
c'est un décalage de niveau.

Aucun contrôle existant ne voyait ça :
- la barrière de qualité juge l'erreur moyenne du régresseur, pas le sens des
  paris qu'il déclenche ;
- l'écran Performance affiche un ROI, et un ROI de pari unanime reste un ROI ;
- le plafond de désaccord (`max_disagreement`) borne l'ampleur d'un écart, pas
  sa constance de signe.

Ce que ce module décide
-----------------------
Deux niveaux, parce que « déséquilibré » et « unanime » n'autorisent pas la
même conclusion.

`WITHHELD` — **unanimité.** Le côté minoritaire n'est jamais apparu sur
    l'échantillon. On n'a donc aucune preuve que le marché *puisse* parier de
    l'autre côté : son historique est compatible avec un simple décalage de
    niveau. Les paris du côté dominant sont retenus ; ceux du côté minoritaire
    passent, et c'est voulu — le premier pari à contre-courant est exactement
    la preuve qui lève le verdict.

`IMBALANCED` — **déséquilibre marqué** sans unanimité. Le côté minoritaire
    existe, donc le marché n'est pas bloqué dans un sens ; mais la répartition
    mérite d'être affichée à côté du ROI. On avertit, on ne retient rien.

Pourquoi pas un test statistique
--------------------------------
La tentation est de tester la répartition contre 50/50. Mesuré sur l'archive
réelle, ça condamne aussi le moneyline (49 `away` contre 9 `home`, p = 9·10⁻⁸)
et éteint l'application entière. Et c'est juste : 50/50 n'est pas le bon
modèle de référence. Le sens d'un value bet dépend du modèle *et* de la
structure des prix — rien n'impose qu'un sélectionneur honnête trouve autant
d'occasions des deux côtés.

L'unanimité, elle, ne demande aucun modèle de référence. Elle énonce un fait
sur ce qu'on peut conclure : un marché qui n'a jamais parié dans l'autre sens
n'a pas démontré qu'il en était capable, donc son rendement n'est pas
interprétable comme une compétence. C'est une règle d'abstention, pas une
hypothèse à rejeter.

Les paris retenus comptent dans la statistique
----------------------------------------------
`predict_all.py` republie les paris retenus sous `withheld_bets`, et le
scanner les compte comme les autres. Sans ça, retenir le côté dominant le
ferait disparaître de l'archive, la fenêtre finirait par l'oublier, et le
marché repartirait aveugle au bout de quelques semaines. La statistique porte
sur **la tendance du modèle**, pas sur ce qu'on a publié : le verdict tient
tant que la tendance tient, et tombe sur une preuve, jamais sur l'usure du
temps.
"""
from __future__ import annotations

import json
import pathlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Literal, Optional

Status = Literal["ok", "imbalanced", "withheld", "insufficient"]

# ── Réglages ────────────────────────────────────────────────────────────────
#
# `MIN_SAMPLE` : en dessous, l'unanimité ne dit rien. Avec une probabilité
# par match aussi modérée que 0,9 pour le côté dominant, ne voir aucun
# minoritaire sur 10 paris arrive une fois sur trois ; sur 12, une fois sur
# quatre. Le seuil n'est pas une frontière de signification, c'est le point
# où le silence du côté minoritaire commence à peser.
MIN_SAMPLE = 12

# Le déséquilibre, lui, demande un échantillon plus large : il se prononce sur
# une proportion, pas sur une absence.
MIN_SAMPLE_IMBALANCE = 20
MINORITY_SHARE = 0.25

# Fenêtre glissante. Assez longue pour qu'un marché peu fréquent atteigne
# `MIN_SAMPLE`, assez courte pour qu'un modèle réentraîné ne traîne pas
# indéfiniment le comportement du précédent.
WINDOW_DAYS = 45

_OVER_UNDER = re.compile(r'^(over|under)_(-?\d+(?:\.\d+)?)$')

# Axe directionnel par marché. Un marché absent de cette table n'a pas de sens
# de pari défini — `exact_score` et `goal_intervals` choisissent parmi des
# issues ordonnées sans opposé naturel — et n'est donc jamais jugé ici.
_AXES: dict[str, dict[str, str]] = {
    'moneyline': {'home': 'home', 'away': 'away'},
    'win': {'home': 'home', 'away': 'away'},
    'btts': {'yes': 'yes', 'no': 'no'},
    'p1_btts': {'yes': 'yes', 'no': 'no'},
    # `tied` n'est d'aucun côté : un pari sur l'égalité ne témoigne ni d'un
    # biais pro-domicile ni de l'inverse, il est donc ignoré.
    'p1_winner': {'home_lead': 'home', 'away_lead': 'away'},
}
_OU_MARKETS = frozenset({'total', 'home_team_total', 'away_team_total', 'p1_total'})


def direction_of(market: str, selection: str) -> Optional[str]:
    """
    Côté du pari, ou None si la sélection n'est pas directionnelle.

    La ligne est volontairement écartée : `under_5.5` et `under_6.5` sont le
    même sens. C'est le sens qui révèle un décalage de niveau, pas la ligne.
    """
    if market in _OU_MARKETS:
        m = _OVER_UNDER.match(selection or '')
        return m.group(1) if m else None
    return _AXES.get(market, {}).get(selection or '')


# ── Verdict ─────────────────────────────────────────────────────────────────
@dataclass
class Verdict:
    sport: str
    market: str
    counts: dict[str, int] = field(default_factory=dict)
    window_from: Optional[str] = None
    window_to: Optional[str] = None

    @property
    def n(self) -> int:
        return sum(self.counts.values())

    @property
    def dominant(self) -> Optional[str]:
        return max(self.counts, key=lambda k: self.counts[k]) if self.counts else None

    @property
    def minority(self) -> int:
        """Nombre de paris hors du côté dominant."""
        return self.n - max(self.counts.values()) if self.counts else 0

    @property
    def status(self) -> Status:
        if self.n < MIN_SAMPLE:
            return 'insufficient'
        if self.minority == 0:
            return 'withheld'
        if self.n >= MIN_SAMPLE_IMBALANCE and self.minority / self.n < MINORITY_SHARE:
            return 'imbalanced'
        return 'ok'

    @property
    def reason(self) -> str:
        if self.status == 'withheld':
            return (
                f"{self.n} paris, tous « {self.dominant} », aucun dans l'autre sens : "
                f"le rendement de ce marché n'est pas une mesure de sélection. "
                f"Un seul pari « {self._other()} » lève la retenue."
            )
        if self.status == 'imbalanced':
            return (
                f"{self.counts.get(self.dominant, 0)} paris sur {self.n} du même côté "
                f"(« {self.dominant} ») : le rendement affiché dépend surtout de ce sens."
            )
        if self.status == 'insufficient':
            return f"{self.n} paris sur la fenêtre — trop peu pour se prononcer."
        return f"{self.n} paris, répartition {self._fmt()}."

    def _other(self) -> str:
        if self.market in _OU_MARKETS:
            return 'over' if self.dominant == 'under' else 'under'
        sides = set(_AXES.get(self.market, {}).values())
        rest = sides - {self.dominant}
        return next(iter(sorted(rest)), 'autre')

    def _fmt(self) -> str:
        return ' / '.join(f"{k} {v}" for k, v in sorted(self.counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            'market': self.market,
            'status': self.status,
            'n': self.n,
            'counts': dict(sorted(self.counts.items())),
            'dominant': self.dominant,
            'minority': self.minority,
            # Côté retenu à la publication, s'il y a lieu. C'est le champ que
            # lit le filtre : il évite au consommateur de redéduire la règle.
            'withhold': self.dominant if self.status == 'withheld' else None,
            'from': self.window_from,
            'to': self.window_to,
            'reason': self.reason,
        }


# ── Lecture de l'archive ────────────────────────────────────────────────────

def _game_key(sport: str, game: dict) -> str:
    return f"{sport}-{game.get('away')}@{game.get('home')}-{(game.get('commence_time') or '')[:10]}"


def scan(
    root: pathlib.Path,
    sports: Iterable[str] = ('nhl', 'nba'),
    window_days: int = WINDOW_DAYS,
    today: Optional[date] = None,
) -> dict[str, list[Verdict]]:
    """
    Compte les sens des paris publiés, par sport et par marché.

    Déduplication indispensable : un même match à venir est republié chaque
    jour, et deux passages quotidiens le réécrivent. Sans dédoublonnage, un
    seul pari compterait trois ou quatre fois et n'importe quel marché
    paraîtrait unanime sur un large échantillon.
    """
    today = today or datetime.now(timezone.utc).date()
    floor = (today - timedelta(days=window_days)).isoformat()
    archive = root / 'predictions' / 'archive'
    out: dict[str, list[Verdict]] = {}

    for sport in sports:
        # On garde la dernière publication de chaque match, celle sur
        # laquelle l'utilisateur a effectivement pu agir.
        # (clé) → (generated_at, paris, date du match)
        latest: dict[str, tuple[str, list[dict], str]] = {}
        if archive.is_dir():
            for day in sorted(archive.iterdir()):
                if not day.is_dir() or day.name < floor:
                    continue
                path = day / f'{sport}.json'
                if not path.is_file():
                    continue
                try:
                    feed = json.loads(path.read_text(encoding='utf-8'))
                except (ValueError, OSError):
                    continue
                generated = feed.get('generated_at') or day.name
                for game in feed.get('games') or []:
                    key = _game_key(sport, game)
                    if key in latest and generated <= latest[key][0]:
                        continue
                    bets = list(game.get('value_bets') or [])
                    # Les paris retenus par ce même garde-fou comptent : la
                    # statistique mesure la tendance du modèle, pas la sortie.
                    bets += list(game.get('withheld_bets') or [])
                    latest[key] = (generated, bets, (game.get('commence_time') or day.name)[:10])

        counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        dates: dict[str, list[str]] = defaultdict(list)
        for _, bets, played_on in latest.values():
            for bet in bets:
                market = bet.get('market')
                side = direction_of(market or '', bet.get('selection') or '')
                if not market or not side:
                    continue
                counts[market][side] += 1
                dates[market].append(played_on)

        out[sport] = [
            Verdict(
                sport=sport,
                market=market,
                counts=dict(sides),
                window_from=min(dates[market]) if dates[market] else None,
                window_to=max(dates[market]) if dates[market] else None,
            )
            for market, sides in sorted(counts.items())
        ]

    return out


# ── Application à la publication ────────────────────────────────────────────
@dataclass
class DirectionGuard:
    """
    Applique les verdicts du jour aux paris d'un sport.

    Volontairement inerte quand le fichier de verdicts est absent ou illisible :
    une prédiction publiée sans garde-fou vaut mieux qu'une journée sans
    prédiction. L'absence est signalée, pas silencieuse.
    """
    withhold: dict[str, str] = field(default_factory=dict)   # marché → côté retenu
    reasons: dict[str, str] = field(default_factory=dict)
    source: Optional[str] = None

    @classmethod
    def load(cls, path: str | pathlib.Path | None, sport: str) -> "DirectionGuard":
        if not path:
            return cls()
        p = pathlib.Path(path)
        if not p.is_file():
            return cls()
        try:
            payload = json.loads(p.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            return cls()
        withhold: dict[str, str] = {}
        reasons: dict[str, str] = {}
        for entry in (payload.get('sports') or {}).get(sport) or []:
            side = entry.get('withhold')
            if side:
                withhold[entry['market']] = side
                reasons[entry['market']] = entry.get('reason') or ''
        return cls(withhold=withhold, reasons=reasons, source=str(p))

    def verdict_for(self, market: str, selection: str) -> Optional[str]:
        """Motif de retenue pour ce pari, ou None s'il peut être publié."""
        side = self.withhold.get(market)
        if not side:
            return None
        if direction_of(market, selection) != side:
            # Le côté minoritaire passe : c'est la preuve attendue.
            return None
        return self.reasons.get(market) or f"marché {market} unanime « {side} »"

    def split(self, bets: list) -> tuple[list, list[tuple[Any, str]]]:
        """Sépare (publiables, [(retenu, motif)])."""
        keep: list = []
        held: list[tuple[Any, str]] = []
        for bet in bets:
            market = getattr(bet, 'market_name', None) or getattr(bet, 'market', '')
            selection = getattr(bet, 'selection', '')
            reason = self.verdict_for(market, selection)
            (held.append((bet, reason)) if reason else keep.append(bet))
        return keep, held

    def __bool__(self) -> bool:
        return bool(self.withhold)
