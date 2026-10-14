#!/usr/bin/env python
"""
check_market_direction.py — Un marché parie-t-il toujours dans le même sens ?

Lit l'archive des prédictions publiées, compte le sens de chaque value bet par
sport et par marché, et écrit son verdict dans `performance/direction.json`.
Ce fichier a deux lecteurs :

- `predict_all.py`, au run suivant, qui retient les paris du côté dominant
  d'un marché déclaré unanime (via `$VIZER_DIRECTION_VERDICTS`) ;
- l'écran Performance de la PWA, qui affiche la répartition **à côté** du ROI,
  pour qu'un rendement unanime ne se lise pas comme une compétence.

Le raisonnement derrière les seuils est dans `vizer_core/direction_guard.py`.
Il tient en une phrase : un marché qui n'a jamais parié de l'autre côté n'a
pas montré qu'il en était capable, donc son rendement n'est pas interprétable.

Pourquoi ce contrôle n'a pas besoin de résultats
------------------------------------------------
Contrairement à `export_performance.py`, qui attend que les matchs soient
joués, le sens d'un pari est connu à la publication. Le défaut est donc
détectable **le jour même**, sans attendre un seul score — ce qui compte,
puisque le biais du `total` a mis trois semaines à devenir visible par le ROI,
et seulement parce que je suis allé le chercher à la main.

Usage :
    python scripts/check_market_direction.py --root /tmp/pub
    python scripts/check_market_direction.py --root /tmp/pub --json
    python scripts/check_market_direction.py --root /tmp/pub --fail-on-withheld
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from vizer_core.direction_guard import (  # noqa: E402
    MIN_SAMPLE, MIN_SAMPLE_IMBALANCE, MINORITY_SHARE, WINDOW_DAYS, scan,
)

SPORTS = ('nhl', 'nba')

_GLYPH = {
    'withheld': '🛑',
    'imbalanced': '⚠️ ',
    'ok': '✅',
    'insufficient': '·',
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Détecte les marchés qui ne parient que dans un sens.")
    ap.add_argument('--root', required=True,
                    help="Racine contenant predictions/archive/")
    ap.add_argument('--out', default=None,
                    help="Fichier de sortie (défaut : <root>/performance/direction.json)")
    ap.add_argument('--window-days', type=int, default=WINDOW_DAYS)
    ap.add_argument('--today', default=None, help="Date de référence (YYYY-MM-DD), pour les tests")
    ap.add_argument('--json', action='store_true', help="Verdict sur stdout, sans écrire")
    ap.add_argument('--fail-on-withheld', action='store_true',
                    help="Code de sortie 1 si au moins un marché est retenu")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    today = date.fromisoformat(args.today) if args.today else None
    verdicts = scan(root, sports=SPORTS, window_days=args.window_days, today=today)

    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'window_days': args.window_days,
        'thresholds': {
            'min_sample': MIN_SAMPLE,
            'min_sample_imbalance': MIN_SAMPLE_IMBALANCE,
            'minority_share': MINORITY_SHARE,
        },
        'sports': {s: [v.to_dict() for v in vs] for s, vs in verdicts.items()},
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        out = pathlib.Path(args.out) if args.out else root / 'performance' / 'direction.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    withheld = []
    for sport, vs in verdicts.items():
        if not vs:
            print(f"  {sport.upper()} : aucun pari directionnel sur la fenêtre", file=sys.stderr)
            continue
        print(f"  {sport.upper()} :", file=sys.stderr)
        for v in vs:
            print(f"    {_GLYPH[v.status]} {v.market:16s} {v.reason}", file=sys.stderr)
            if v.status == 'withheld':
                withheld.append(f"{sport}/{v.market}")

    if not args.json:
        print(f"✅ {out}", file=sys.stderr)
    if withheld and args.fail_on_withheld:
        print(f"🛑 Marché(s) retenu(s) : {', '.join(withheld)}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
