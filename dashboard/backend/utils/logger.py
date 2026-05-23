"""Configuration de logging pour le backend ETL/API.

Ce module fournit `get_logger(name)` qui retourne un logger configuré
avec :
- un handler fichier rotatif (`RotatingFileHandler`) vers `etl_run.log`
- un handler console (stdout)

Les niveaux et le chemin du fichier peuvent être configurés via
`ETL_LOG_LEVEL` et `ETL_LOG_FILE`.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_LEVEL_MAP: dict[str, int] = {
    "DEBUG":    logging.DEBUG,
    "INFO":     logging.INFO,
    "WARNING":  logging.WARNING,
    "ERROR":    logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_LOG_DIR = Path(__file__).parent.parent
_LOG_FILE = _LOG_DIR / os.getenv("ETL_LOG_FILE", "etl_run.log")
_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
_LOG_LEVEL = _LOG_LEVEL_MAP.get(
    os.getenv("ETL_LOG_LEVEL", "INFO").upper(), logging.INFO
)

_FMT = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_handler_file = RotatingFileHandler(
    _LOG_FILE,
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_handler_file.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))

_handler_console = logging.StreamHandler(sys.stdout)
_handler_console.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger configuré pour l'application.

    Utiliser `get_logger(__name__)` dans les modules pour obtenir un
    logger cohérent (niveau, format, handlers).
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(_LOG_LEVEL)
        logger.addHandler(_handler_file)
        logger.addHandler(_handler_console)
        logger.propagate = False
    return logger
