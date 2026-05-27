"""
config_loader — Chargement et validation de config.yaml.

La règle dure du projet : aucun script ne hardcode de paramètre présent
dans config.yaml. Ce module est le point d'entrée unique.

Usage :
    from vizer_core import load_config

    config = load_config('config.yaml')
    n_estimators = config['markets']['moneyline']['hyperparameters']['n_estimators']
    edge = config['markets']['moneyline']['edge_threshold']
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Erreur de configuration (clé manquante, valeur invalide, ...)."""


# Schéma minimal attendu : (chemin, type accepté)
# Les marchés sont validés séparément.
REQUIRED_KEYS: list[tuple[str, type | tuple[type, ...]]] = [
    ("sport", str),
    ("data", dict),
    ("data.paths", dict),
    ("features", dict),
    ("features.rolling_windows", list),
    ("data_split", dict),
    ("models", dict),
    ("models.output_path", str),
    ("markets", dict),
    ("predictions", dict),
    ("predictions.output_dir", str),
]


def _get_nested(d: dict[str, Any], path: str) -> Any:
    """Navigue dans le dict via une clé en dot-notation. Lève KeyError si absent."""
    keys = path.split(".")
    current: Any = d
    for k in keys:
        if not isinstance(current, dict):
            raise KeyError(path)
        if k not in current:
            raise KeyError(path)
        current = current[k]
    return current


def _validate_schema(config: dict[str, Any]) -> None:
    """Vérifie présence et type des clés obligatoires. Lève ConfigError sinon."""
    errors: list[str] = []
    for path, expected_type in REQUIRED_KEYS:
        try:
            value = _get_nested(config, path)
        except KeyError:
            errors.append(f"Clé manquante : '{path}'")
            continue
        if not isinstance(value, expected_type):
            type_name = (
                expected_type.__name__
                if isinstance(expected_type, type)
                else " | ".join(t.__name__ for t in expected_type)
            )
            errors.append(
                f"Clé '{path}' a un type invalide "
                f"(attendu: {type_name}, reçu: {type(value).__name__})"
            )

    # Validation des marchés : chacun doit avoir au moins `enabled`
    markets = config.get("markets", {})
    for market_name, market_cfg in markets.items():
        if not isinstance(market_cfg, dict):
            errors.append(f"markets.{market_name} doit être un dict")
            continue
        if "enabled" not in market_cfg:
            errors.append(f"markets.{market_name}.enabled manquant")

    if errors:
        msg = "Configuration invalide :\n  - " + "\n  - ".join(errors)
        raise ConfigError(msg)


def load_config(path: str | Path = "config.yaml", validate: bool = True) -> dict[str, Any]:
    """
    Charge et valide un config.yaml.

    Args:
        path     : chemin vers le YAML. Par défaut 'config.yaml' dans le cwd.
        validate : si True (défaut), applique le schéma strict NBA. Mettre à
                   False pour les configs au format différent (ex: NHL qui a
                   sa propre structure paths/services).

    Returns:
        Dict de configuration.

    Raises:
        FileNotFoundError : fichier introuvable.
        ConfigError       : YAML mal formé ou (si validate) schéma invalide.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Configuration introuvable : {path}\n"
            f"Astuce : copier config.template.yaml vers {path} et adapter."
        )

    try:
        with path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML invalide dans {path} : {e}") from e

    if not isinstance(config, dict):
        raise ConfigError(f"{path} doit contenir un dict YAML au niveau racine.")

    # Surcharge de la clé API depuis la variable d'environnement ODDS_API_KEY.
    # Priorité : env var > config.yaml (permet de ne pas exposer la clé dans le dépôt).
    _inject_env_api_key(config)

    if validate:
        _validate_schema(config)
    return config


def _inject_env_api_key(config: dict[str, Any]) -> None:
    """Surcharge la clé Odds API depuis ODDS_API_KEY si la variable est définie.

    Supporte les deux formats de config :
      - NHL : config.odds_api.key
      - NBA : config.apis.odds_api.key
    """
    env_key = os.environ.get("ODDS_API_KEY", "").strip()
    if not env_key:
        return
    # Format NHL
    if isinstance(config.get("odds_api"), dict):
        config["odds_api"]["key"] = env_key
    # Format NBA
    apis = config.get("apis")
    if isinstance(apis, dict) and isinstance(apis.get("odds_api"), dict):
        apis["odds_api"]["key"] = env_key


def get_market_config(config: dict[str, Any], market_name: str) -> dict[str, Any]:
    """
    Récupère la config d'un marché ou lève une erreur explicite.

    Equivalent à `config['markets'][market_name]` mais avec message clair.
    """
    markets = config.get("markets", {})
    if market_name not in markets:
        available = sorted(markets.keys())
        raise ConfigError(
            f"Marché '{market_name}' absent de config.yaml. "
            f"Marchés définis : {available}"
        )
    return markets[market_name]


def enabled_markets(config: dict[str, Any]) -> list[str]:
    """Retourne la liste triée des marchés actifs (`enabled: true`) dans la config."""
    markets = config.get("markets", {})
    return sorted(
        name for name, cfg in markets.items()
        if isinstance(cfg, dict) and cfg.get("enabled", False)
    )
