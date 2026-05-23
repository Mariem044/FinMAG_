"""Logger simple pour les composants ETL, avec sortie formatée sur stdout.

Fournit `get_logger(name)` qui configure un handler console simple.
Utiliser dans les scripts ETL pour garder un format de log cohérent
et éviter d'initialiser plusieurs fois des handlers.
"""

import logging
import sys
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        ))
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False
    return logger