from __future__ import annotations

"""Configuration partagée pour le backend FinMAG.

Ce module centralise la lecture des variables d'environnement, la
création des moteurs SQLAlchemy (`DW_ENGINE`, `MAG_ENGINE`, `GRT_ENGINE`)
et les utilitaires liés aux connexions (gestion TLS/ODBC, parsing de
dates, génération de clés de hachage stables). Les fonctions exposées
ici sont utilisées par l'ETL, le backend API et les composants ML.

Principaux points :
- `get_required_env(name)` : lève une erreur si la variable d'environnement
    attendue est absente (utile pour fail-fast en démarrage).
- `_make_engine(conn_str)` : fabrique un `Engine` SQLAlchemy avec des
    options par défaut et un pool adapté.
- `hash_key(value)` : génère une clé entière stable à partir d'une valeur
    (utilisée pour créer des surrogate keys déterministes dans l'ETL).
"""

import hashlib
import logging
import math
import os
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

logging.getLogger("pyodbc").setLevel(logging.WARNING)

# Load environment variables from .env, unless DOTENV_PATH points to another file.
DEFAULT_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
DOTENV_PATH = Path(os.environ.get("DOTENV_PATH", DEFAULT_ENV_PATH))
load_dotenv(DOTENV_PATH if DOTENV_PATH.exists() else DEFAULT_ENV_PATH)


def get_required_env(name: str) -> str:
    """Return a required environment variable or raise a clear error."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _sqlserver_tls_compat(conn_str: str) -> str:
    """Ensure SQL Server connection strings include TLS flags."""
    lowered = conn_str.lower()
    if "encrypt=" in lowered or "trustservercertificate=" in lowered:
        return conn_str

    if "odbc_connect=" in lowered:
        return _add_tls_to_odbc_connect(conn_str)

    separator = "&" if "?" in conn_str else "?"
    return f"{conn_str}{separator}Encrypt=no&TrustServerCertificate=yes"


def _add_tls_to_odbc_connect(conn_str: str) -> str:
    parts = urlsplit(conn_str)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    odbc = query.get("odbc_connect")
    if odbc is None:
        return conn_str

    query["odbc_connect"] = f"{odbc};Encrypt=no;TrustServerCertificate=yes"
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query, quote_via=quote_plus),
        parts.fragment,
    ))


def _make_engine(conn_str: str, pool_size: int = 5) -> Engine:
    """Create a SQLAlchemy engine with simple defaults."""
    engine = create_engine(
        _sqlserver_tls_compat(conn_str),
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=10,
        pool_pre_ping=True,
        connect_args={"timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _set_sql_server_options(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("SET NOCOUNT ON")
        cursor.close()

    return engine


def _parse_date(name: str, default: str) -> date:
    """Parse a YYYY-MM-DD date from environment variables."""
    value = os.environ.get(name, default)
    return datetime.strptime(value, "%Y-%m-%d").date()


DW_ENGINE = _make_engine(get_required_env("DW_CONN"), pool_size=5)
MAG_ENGINE = _make_engine(get_required_env("MAG_CONN"), pool_size=3)
GRT_ENGINE = _make_engine(get_required_env("GRT_CONN"), pool_size=3)

DEFAULT_DIM_DATE_START = "2020-01-01"
DEFAULT_DIM_DATE_END = "2026-12-31"
DEFAULT_ERROR_MSG_MAX_LEN = "500"
DEFAULT_SEUIL_TENSION_STOCK = "0.5"
DEFAULT_HASH_BYTES = "8"

DIM_DATE_START = _parse_date("DIM_DATE_START", DEFAULT_DIM_DATE_START)
DIM_DATE_END = _parse_date("DIM_DATE_END", DEFAULT_DIM_DATE_END)
AUDIT_TABLE_NAME = os.environ.get("ETL_AUDIT_TABLE", "ETL_AUDIT")
ERROR_MSG_MAX_LEN = int(os.environ.get("ETL_ERROR_MSG_MAX_LEN", DEFAULT_ERROR_MSG_MAX_LEN))
SEUIL_TENSION_STOCK = float(os.environ.get("SEUIL_TENSION_STOCK", DEFAULT_SEUIL_TENSION_STOCK))

_HASH_BYTES: int = int(os.environ.get("ETL_HASH_BYTES", DEFAULT_HASH_BYTES))
if _HASH_BYTES < 8:
    raise ValueError(
        f"ETL_HASH_BYTES={_HASH_BYTES} is too small. "
        "Set ETL_HASH_BYTES=8 in .env to avoid surrogate key collisions."
    )


def hash_key(value: str | int | float | None) -> int | None:
    """Return a stable integer hash or None for empty values."""
    if value is None:
        return None

    if isinstance(value, float) and math.isnan(value):
        return None

    normalized = str(value).strip().upper()
    if not normalized:
        return None

    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    max_bits = _HASH_BYTES * 8 - 1
    return int.from_bytes(digest[:_HASH_BYTES], "big") & ((1 << max_bits) - 1)
