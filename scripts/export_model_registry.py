#!/usr/bin/env python
"""
export_model_registry.py — Publie les métadonnées des modèles en JSON.

L'écran Admin de la PWA a besoin de savoir ce qui tourne en production :
version, date d'entraînement, volume d'entraînement, marchés actifs et
métriques par marché. Tout cela est déjà dans les registres `.pkl` ; ce script
ne fait que l'extraire sous une forme lisible par le web.

Il ne charge **que** les métadonnées et métriques — jamais les poids — donc il
reste rapide et ne dépend pas des versions ML au-delà du dépickle.

Usage :
    python scripts/export_model_registry.py --out models/registry.json
"""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vizer_core import ModelRegistry

# Modèles connus : code → (chemin par défaut, libellé affiché)
MODELS: dict[str, tuple[str, str]] = {
    'nhl': ('vizer_nhl/models/nhl_model.pkl', 'Hockey · NHL'),
    'nba': ('vizer_nba/models/nba_model.pkl', 'Basket · NBA'),
}

# Métadonnées utiles à l'Admin. Le reste (élos, valeurs joueurs, mapping de
# noms) pèse lourd et n'intéresse pas l'interface.
META_KEYS = (
    'trained_at',
    'model_version',
    'training_mode',
    'metrics_in_sample',
    'train_seasons',
    'train_until_year',
    'test_year',
    'test_season',
    'n_games_train',
    'n_games_test',
    'training_duration_sec',
    'models_trained',
    'models_failed',
    'p1_mode',
)


@contextmanager
def sport_importable(sport_dir: Path):
    """
    Rend `src.*` importable pendant le dépickle.

    Les registres ont été sérialisés depuis `vizer_<sport>/`, où les moteurs
    sont importés en `src.models...`. Sans ce chemin, joblib échoue sur un
    ModuleNotFoundError — c'est aussi pour cela que les workflows lancent
    `predict_all.py` depuis le dossier du sport.
    """
    resolved = str(sport_dir.resolve())
    # Les deux sports exposent chacun un package `src` : si celui de la NHL est
    # déjà en cache, `src.models.win_predictor` (NBA) ne se résout pas. On vide
    # donc le cache avant et après chaque chargement.
    purged = {k: v for k, v in sys.modules.items() if k == 'src' or k.startswith('src.')}
    for name in purged:
        del sys.modules[name]

    sys.path.insert(0, resolved)
    try:
        yield
    finally:
        if resolved in sys.path:
            sys.path.remove(resolved)
        for name in [k for k in sys.modules if k == 'src' or k.startswith('src.')]:
            del sys.modules[name]
        sys.modules.update(purged)


def _clean_metrics(values: dict[str, Any]) -> dict[str, Any]:
    """Garde les nombres en nombres, le reste en chaînes JSON-sûres."""
    out: dict[str, Any] = {}
    for key, val in values.items():
        if isinstance(val, bool):
            out[key] = val
        elif isinstance(val, (int, float)):
            out[key] = round(float(val), 6)
        else:
            out[key] = str(val)
    return out


def describe(code: str, path: Path, label: str) -> dict[str, Any] | None:
    """Résumé d'un registre, ou `None` si le fichier est absent/illisible."""
    if not path.exists():
        print(f"  ℹ️  {code} : {path} absent — ignoré", file=sys.stderr)
        return None
    try:
        # Le dossier du sport est `<...>/vizer_<sport>/models/<fichier>.pkl`.
        with sport_importable(path.parent.parent):
            registry = ModelRegistry.load(path)
    except Exception as e:  # noqa: BLE001 — on veut publier les autres sports
        print(f"  ❌ {code} : chargement impossible ({type(e).__name__}: {e})",
              file=sys.stderr)
        return {'sport': code, 'name': label, 'error': f"{type(e).__name__}: {e}"}

    meta = getattr(registry, '_metadata', {}) or {}
    metrics = getattr(registry, '_metrics', {}) or {}
    markets = registry.list_markets()

    out: dict[str, Any] = {
        'sport': code,
        'name': label,
        'registry_version': registry.version,
        'markets': markets,
        'n_markets': len(markets),
        # Les métriques mélangent des nombres et des libellés
        # (`best_model: 'XGB'`) : on normalise sans tout forcer en float.
        'metrics': {k: _clean_metrics(v) for k, v in metrics.items()},
    }
    for key in META_KEYS:
        if key in meta:
            out[key] = meta[key]

    # Repli si l'entraînement est antérieur à l'ajout de `trained_at` :
    # la date du fichier vaut mieux que rien.
    if not out.get('trained_at'):
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        out['trained_at'] = mtime.isoformat(timespec='seconds')
        out['trained_at_source'] = 'file_mtime'
    if not out.get('model_version'):
        stamp = datetime.fromisoformat(out['trained_at'].replace('Z', '+00:00'))
        out['model_version'] = f"v{stamp:%Y.%m.%d}"

    print(f"  ✓ {code} : {out['model_version']} · {len(markets)} marché(s)", file=sys.stderr)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporte les métadonnées des modèles en JSON")
    parser.add_argument('--out', default='-', help="Fichier de sortie ('-' = stdout)")
    parser.add_argument('--nhl', default=MODELS['nhl'][0])
    parser.add_argument('--nba', default=MODELS['nba'][0])
    args = parser.parse_args()

    paths = {'nhl': Path(args.nhl), 'nba': Path(args.nba)}
    models: dict[str, Any] = {}
    for code, (_, label) in MODELS.items():
        described = describe(code, paths[code], label)
        if described is not None:
            models[code] = described

    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'models': models,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    if args.out == '-':
        print(text)
    else:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding='utf-8')
        print(f"✅ {out} écrit ({len(models)} modèle(s))", file=sys.stderr)

    return 0 if models else 1


if __name__ == '__main__':
    raise SystemExit(main())
