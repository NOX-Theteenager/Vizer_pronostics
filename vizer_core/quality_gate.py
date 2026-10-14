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
from typing import Any, Literal, Optional

from .model_registry import ModelRegistry

# Noms rencontrés selon le sport : NHL suffixe (`auc_test`), NBA préfixe
# (`test_auc`). Plutôt que d'imposer une convention à des fichiers qui ont déjà
# la leur, on accepte les deux.
_AUC_KEYS = ("auc_test", "test_auc")

# Les marchés non binaires sont des régresseurs : leur qualité ne se lit pas
# en AUC mais en erreur moyenne et en R². La barrière ne gardait donc qu'un
# marché sur huit — les sept autres pouvaient se dégrader sans que rien ne
# l'arrête.
_MAE_KEYS = ("mae_total_test", "mae_p1_total_test", "test_mae", "mae_test")
_R2_KEYS = ("r2_total_test", "test_r2", "r2_test")


@dataclass
class Rule:
    """Un critère et son sens : plancher ou plafond."""
    label: str
    keys: tuple[str, ...]
    bound: float
    higher_is_better: bool

    def verdict(self, metrics: dict[str, Any]) -> tuple[Optional[float], bool]:
        """Valeur mesurée et conformité. `None` = métrique absente."""
        value = _first_number(metrics, self.keys)
        if value is None:
            return None, True
        ok = value >= self.bound if self.higher_is_better else value <= self.bound
        return value, ok


def _first_number(metrics: dict[str, Any], keys: tuple[str, ...]) -> Optional[float]:
    for key in keys:
        value = metrics.get(key)
        if isinstance(value, (int, float)) and value == value:  # écarte NaN
            return float(value)
    return None


def _rules_for(config: dict[str, Any]) -> list[Rule]:
    """Critères déclarés pour un marché, dans l'ordre de lecture."""
    rules: list[Rule] = []
    if "min_test_auc" in config:
        rules.append(Rule("AUC", _AUC_KEYS, float(config["min_test_auc"]), True))
    if "max_test_mae" in config:
        rules.append(Rule("MAE", _MAE_KEYS, float(config["max_test_mae"]), False))
    if "min_test_r2" in config:
        rules.append(Rule("R²", _R2_KEYS, float(config["min_test_r2"]), True))
    return rules

Verdict = Literal["pass", "fail", "skip"]


@dataclass
class MarketCheck:
    market: str
    verdict: Verdict
    auc: float | None
    floor: float
    reason: str
    # Pourquoi, en un mot que la CI peut lire. Un refus a deux causes bien
    # distinctes et le log ne doit pas les confondre : un marché sous son
    # plancher n'a rien à voir avec un marché qui n'a pas pu s'entraîner.
    cause: str = ""

    @property
    def symbol(self) -> str:
        return {"pass": "✓", "fail": "❌", "skip": "⊘"}[self.verdict]

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "verdict": self.verdict,
            "auc": self.auc,
            "floor": self.floor,
            "cause": self.cause,
            "reason": self.reason,
        }


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

    def headline(self) -> str:
        """Une phrase qui nomme la vraie cause du refus, pour les logs de CI."""
        if self.passed:
            return "barrière franchie"
        low = [c for c in self.failed if c.cause == "below_floor"]
        missing = [c for c in self.failed if c.cause == "market_missing"]
        parts = []
        if low:
            parts.append(
                "AUC sous le plancher : "
                + ", ".join(f"{c.market} {c.auc:.4f} < {c.floor:.4f}" for c in low)
            )
        if missing:
            parts.append(
                "marché(s) absent(s) du registre, entraînement échoué : "
                + ", ".join(c.market for c in missing)
            )
        return " ; ".join(parts) or "refus sans cause identifiée"

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "enabled": self.enabled,
            "n_test": self.n_test,
            "headline": self.headline(),
            "checks": [c.to_dict() for c in self.checks],
        }

    def report(self) -> str:
        lines = ["─" * 62, "BARRIÈRE DE QUALITÉ", "─" * 62]
        if not self.enabled:
            lines.append("  ⊘ Désactivée dans config.yaml (quality_gate.enabled: false)")
            lines.append("─" * 62)
            return "\n".join(lines)
        lines.append(f"  Matchs de test : {self.n_test:,}")
        for c in self.checks:
            # Le critère varie selon le marché — AUC pour un classifieur,
            # erreur moyenne pour un régresseur. On affiche ce qui a été
            # mesuré plutôt qu'une colonne AUC vide pour six marchés sur sept.
            detail = c.reason or (f"AUC={c.auc:.4f}" if c.auc is not None else "—")
            lines.append(f"  {c.symbol} {c.market:16s} {detail}")
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

    for market, rules_cfg in (gate_cfg.get("markets") or {}).items():
        rules = _rules_for(rules_cfg)
        # Compatibilité : un marché sans critère déclaré garde l'ancien
        # comportement, un plancher d'AUC implicite.
        floor = float(rules_cfg.get("min_test_auc", 0.0))

        if not registry.has(market):
            result.checks.append(MarketCheck(
                market, "fail", None, floor,
                "marché absent du registre — entraînement échoué ou désactivé",
                cause="market_missing",
            ))
            continue

        metrics = registry.get_metrics(market)
        auc = _extract_auc(metrics)

        if n_test < min_games:
            result.checks.append(MarketCheck(
                market, "skip", auc, floor,
                f"abstention : {n_test:,} matchs de test < {min_games:,} requis, "
                f"mesure trop bruitée pour décider",
                cause="too_few_test_games",
            ))
            continue

        if not rules:
            result.checks.append(MarketCheck(
                market, "skip", auc, floor,
                "abstention : aucun critère déclaré pour ce marché",
                cause="no_rule",
            ))
            continue

        measured: list[str] = []
        breaches: list[str] = []
        missing = 0
        for rule in rules:
            value, ok = rule.verdict(metrics)
            if value is None:
                missing += 1
                continue
            measured.append(f"{rule.label}={value:.4f}")
            if not ok:
                sense = "sous" if rule.higher_is_better else "au-dessus de"
                breaches.append(f"{rule.label} {value:.4f} {sense} {rule.bound:.4f}")

        if missing == len(rules):
            result.checks.append(MarketCheck(
                market, "skip", auc, floor,
                "abstention : aucune des métriques attendues n'est présente "
                "(jeu de test à une seule classe ?)",
                cause="no_metric",
            ))
        elif breaches:
            result.checks.append(MarketCheck(
                market, "fail", auc, floor,
                "; ".join(breaches),
                cause="below_floor",
            ))
        else:
            result.checks.append(MarketCheck(
                market, "pass", auc, floor, " · ".join(measured), cause="ok"))

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refuse un modèle dont l'AUC de test passe sous le plancher."
    )
    parser.add_argument("registry", help="Registre issu de train.py en mode split")
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("--json", dest="json_out", default=None,
                        help="Écrit le verdict détaillé en JSON à ce chemin")
    args = parser.parse_args(argv)

    def dump(payload: dict[str, Any]) -> None:
        """Le verdict machine, pour que la CI cite la cause et pas une
        supposition. Un échec d'écriture ne doit pas masquer le verdict."""
        if not args.json_out:
            return
        import json
        try:
            Path(args.json_out).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            print(f"⚠️  Verdict JSON non écrit : {exc}", file=sys.stderr)

    from .config_loader import load_config

    config = load_config(args.config, validate=False)
    gate_cfg = config.get("quality_gate") or {}
    if not gate_cfg:
        print("⚠️  Aucune section quality_gate dans la config — rien à vérifier.",
              file=sys.stderr)
        dump({"passed": True, "enabled": False,
              "headline": "aucune section quality_gate dans la config"})
        return 0

    path = Path(args.registry)
    if not path.exists():
        print(f"❌ Registre introuvable : {path}", file=sys.stderr)
        dump({"passed": False, "headline": f"registre introuvable : {path}",
              "cause": "registry_missing"})
        return 2

    try:
        registry = ModelRegistry.load(path)
    except Exception as e:
        print(f"❌ Lecture du registre impossible : {type(e).__name__}: {e}",
              file=sys.stderr)
        dump({"passed": False, "cause": "registry_unreadable",
              "headline": f"registre illisible : {type(e).__name__}: {e}"})
        return 2

    try:
        result = check_registry(registry, gate_cfg)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        dump({"passed": False, "cause": "in_sample_registry", "headline": str(e)})
        return 2

    print(result.report())
    dump(result.to_dict())
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
