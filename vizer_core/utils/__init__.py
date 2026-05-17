"""
Utilitaires transverses pour vizer_core.

- leakage_check : détection automatique de data leakage par corrélation feature/target.
"""
from .leakage_check import detect_target_leakage, assert_no_leakage, LeakageError

__all__ = ["detect_target_leakage", "assert_no_leakage", "LeakageError"]
