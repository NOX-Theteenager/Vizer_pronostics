"""
quality_gate.py — Refuse le déploiement d'un modèle sous-performant.

Le pipeline entraînait et déployait sans jamais regarder ce que valaient les
modèles. Un marché qui se dégrade partait en production le lundi suivant sans
que rien ne le signale. Cette barrière lit les métriques hors échantillon d'un
registre et bloque si elles passent sous un plancher.

Sur quoi elle juge
------------------
L'AUC, et non l'accuracy. L'accuracy dépend du seuil de décision et du
déséquilibre des classes : prédire toujours « domicile » donne déjà 52,8 % en
NHL et 54,7 % en NBA. L'AUC vaut 0,5 pour un modèle sans information, quel que
soit l'équilibre des classes — c'est un plancher qui a le même sens pour les
deux sports.

Ce qu'elle exige en entrée
--------------------------
Un registre entraîné en mode **split** (`train.py` sans `--full`). Un registre
de production (`--full`) n'a pas de jeu de test : ses métriques sont in-sample
et `metadata['metrics_in_sample']` vaut True. La barrière refuse d'évaluer un
tel registre plutôt que de valider sur des chiffres qui ne mesurent rien.

Abstention
----------
Quand le jeu de test est trop petit, la mesure n'est pas fiable : en début de
saison NHL il n'y a que quelques centaines de matchs, et une AUC calculée
là-dessus bouge de plusieurs centièmes d'une semaine à l'autre. Sous
`min_test_games`, la barrière s'abstient explicitement au lieu de bloquer sur
du bruit. Même chose si l'AUC est absente (jeu de test à une seule classe).
Une abstention est tracée dans le rapport, jamais silencieuse.

Configuration (config.yaml de chaque sport)
-------------------------------------------
    quality_gate:
      enabled: true
      min_test_games: 300
      markets:
        moneyline:
          min_test_auc: 0.55

Usage CLI (depuis le dossier du sport, pour que le pickle retrouve `src`) :
    python -m vizer_core.quality_gate models/eval.pkl --config config.yaml

Codes de retour : 0 = accepté (ou abstention), 1 = refusé, 2 = erreur d'usage.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .model_registry import ModelRegistry

# Noms rencontrés selon le sport : NHL suffixe (`auc_test`), NBA préfixe
# (`test_auc`). Plutôt que d'imposer une convention à des fichiers qui ont déjà
# la leur, on accepte les deux.
_AUC_KEYS = ("auc_test", "test_auc")

Verdict = Literal["pass", "fail", "skip"]


@dataclass
class MarketCheck:
    market: str
    verdict: Verdict
    auc: float | None
    floor: float
    reason: str

    @property
    def symbol(self) -> str:
        return {"pass": "✓", "fail": "❌", "skip": "⊘"}[self.verdict]


@dataclass
class GateResult:
    checks: list[MarketCheck] = field(default_factory=list)
    n_test: int = 0
    enabled: bool = True

    @property
    def failed(self) -> list[MarketCheck]:
        return [c for c in self.checks if c.verdict == "fail"]

    @property
    def passed(self) -> bool:
        return not self.failed

    def report(self) -> str:
        lines = ["─" * 62, "BARRIÈRE DE QUALITÉ", "─" * 62]
        if not self.enabled:
            lines.append("  ⊘ Désactivée dans config.yaml (quality_gate.enabled: false)")
            lines.append("─" * 62)
            return "\n".join(lines)
        lines.append(f"  Matchs de test : {self.n_test:,}")
        for c in self.checks:
            auc = f"{c.auc:.4f}" if c.auc is not None else "n/a"
            lines.append(f"  {c.symbol} {c.market:14s} AUC={auc:>6s}  plancher={c.floor:.4f}")
            if c.reason:
                lines.append(f"      {c.reason}")
        lines.append("─" * 62)
        lines.append("  ✅ ACCEPTÉ" if self.passed else "  ❌ REFUSÉ — déploiement bloqué")
        lines.append("─" * 62)
        return "\n".join(lines)


def _extract_auc(metrics: dict[str, Any]) -> float | None:
    for key in _AUC_KEYS:
        value = metrics.get(key)
        if isinstance(value, (int, float)) and value == value:  # écarte NaN
            return float(value)
    return None


def check_registry(registry: ModelRegistry, gate_cfg: dict[str, Any]) -> GateResult:
    """Évalue un registre de mode split contre la configuration de la barrière."""
    if not gate_cfg.get("enabled", True):
        return GateResult(enabled=False)

    if registry.get_metadata("metrics_in_sample"):
        raise ValueError(
            "Registre entraîné en mode production (metrics_in_sample=True) : ses "
            "métriques sont calculées sur les données d'entraînement et ne "
            "mesurent aucune généralisation. Fournir un registre issu de "
            "`train.py` sans --full."
        )

    n_test = int(registry.get_metadata("n_games_test") or 0)
    min_games = int(gate_cfg.get("min_test_games", 0))
    result = GateResult(n_test=n_test)

    for market, rules in (gate_cfg.get("markets") or {}).items():
        floor = float(rules.get("min_test_auc", 0.0))

        if not registry.has(market):
            result.checks.append(MarketCheck(
                market, "fail", None, floor,
                "marché absent du registre — entraînement échoué ou désactivé",
            ))
            continue

        auc = _extract_auc(registry.get_metrics(market))

        if n_test < min_games:
            result.checks.append(MarketCheck(
                market, "skip", auc, floor,
                f"abstention : {n_test:,} matchs de test < {min_games:,} requis, "
                f"mesure trop bruitée pour décider",
            ))
        elif auc is None:
            result.checks.append(MarketCheck(
                market, "skip", None, floor,
                "abstention : aucune AUC dans les métriques (jeu de test à une "
                "seule classe ?)",
            ))
        elif auc < floor:
            result.checks.append(MarketCheck(
                market, "fail", auc, floor,
                f"sous le plancher de {floor - auc:.4f}",
            ))
        else:
            result.checks.append(MarketCheck(market, "pass", auc, floor, ""))

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refuse un modèle dont l'AUC de test passe sous le plancher."
    )
    parser.add_argument("registry", help="Registre issu de train.py en mode split")
    parser.add_argument("-c", "--config", default="config.yaml")
    args = parser.parse_args(argv)

    from .config_loader import load_config

    config = load_config(args.config, validate=False)
    gate_cfg = config.get("quality_gate") or {}
    if not gate_cfg:
        print("⚠️  Aucune section quality_gate dans la config — rien à vérifier.",
              file=sys.stderr)
        return 0

    path = Path(args.registry)
    if not path.exists():
        print(f"❌ Registre introuvable : {path}", file=sys.stderr)
        return 2

    try:
        registry = ModelRegistry.load(path)
    except Exception as e:
        print(f"❌ Lecture du registre impossible : {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2

    try:
        result = check_registry(registry, gate_cfg)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    print(result.report())
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
