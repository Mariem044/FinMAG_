"""Configuration de l'ETL : paramètres, connexions et utilitaires partagés."""

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables from .env, unless DOTENV_PATH points to another file.
DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
DOTENV_PATH = Path(os.environ.get("DOTENV_PATH", DEFAULT_ENV_PATH))
# Charger les variables d'environnement à partir du fichier .env ou d'un chemin personnalisé
load_dotenv(DOTENV_PATH if DOTENV_PATH.exists() else DEFAULT_ENV_PATH)


def _sqlserver_tls_compat(conn_str: str) -> str:
    """Ajouter les paramètres TLS aux chaînes de connexion SQL Server si nécessaire."""
    if not conn_str.startswith("mssql+pyodbc"):
        return conn_str

    lower = conn_str.lower()
    if "encrypt=" in lower or "trustservercertificate=" in lower:
        return conn_str

    if "odbc_connect=" in lower:
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


def _replace_database(conn_str: str, database: str) -> str:
    """Remplacer le nom de base de données dans une chaîne de connexion."""
    lower = conn_str.lower()
    if "odbc_connect=" in lower:
        parts = urlsplit(conn_str)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        odbc = query.get("odbc_connect")
        if odbc is None:
            return conn_str

        chunks = []
        replaced = False
        for chunk in odbc.split(";"):
            if "=" not in chunk:
                chunks.append(chunk)
                continue
            key, value = chunk.split("=", 1)
            if key.strip().lower() in ("database", "initial catalog"):
                chunks.append(f"{key}={database}")
                replaced = True
            else:
                chunks.append(f"{key}={value}")

        if not replaced:
            chunks.append(f"Database={database}")

        query["odbc_connect"] = ";".join(chunks)
        return urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query, quote_via=quote_plus),
            parts.fragment,
        ))

    parts = urlsplit(conn_str)
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        f"/{database}",
        parts.query,
        parts.fragment,
    ))


def _database_name(conn_str: str) -> Optional[str]:
    """Extraire le nom de la base de données depuis une chaîne de connexion."""
    if "odbc_connect=" in conn_str.lower():
        parts = urlsplit(conn_str)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        odbc = query.get("odbc_connect")
        if not odbc:
            return None

        for chunk in odbc.split(";"):
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            if key.strip().lower() in ("database", "initial catalog"):
                return value.strip() or None
        return None

    return urlsplit(conn_str).path.strip("/") or None


def _quote_sqlserver_identifier(identifier: str) -> str:
    return f"[{identifier.replace(']', ']]')}]"


def ensure_dw_database_exists() -> None:
    """Create the DW database if it does not already exist."""
    dw_conn = os.environ["DW_CONN"]
    if dw_conn.startswith("sqlite"):
        return

    db_name = _database_name(dw_conn)
    if not db_name or db_name.lower() == "master":
        return

    master_conn_str = _replace_database(dw_conn, "master")
    master_engine = create_engine(_sqlserver_tls_compat(master_conn_str), isolation_level="AUTOCOMMIT")

    with master_engine.connect() as conn:
        exists = conn.execute(text("SELECT DB_ID(:db_name)"), {"db_name": db_name}).scalar()
        if exists is None:
            conn.execute(text(f"CREATE DATABASE {_quote_sqlserver_identifier(db_name)}"))


def _make_engine(conn_str: str):
    """Créer un moteur SQLAlchemy pour la chaîne de connexion fournie."""
    return create_engine(_sqlserver_tls_compat(conn_str))


DW_ENGINE = _make_engine(os.environ["DW_CONN"])
MAG_ENGINE = _make_engine(os.environ["MAG_CONN"])
GRT_ENGINE = _make_engine(os.environ["GRT_CONN"])

# ETL parameters with default values.
DEFAULT_DIM_DATE_START = "2020-01-01"
DEFAULT_DIM_DATE_END = "2026-12-31"
DEFAULT_ERROR_MSG_MAX_LEN = "500"
DEFAULT_HASH_BYTES = "8"

DIM_DATE_START = datetime.strptime(
    os.environ.get("DIM_DATE_START", DEFAULT_DIM_DATE_START), "%Y-%m-%d"
).date()
DIM_DATE_END = datetime.strptime(
    os.environ.get("DIM_DATE_END", DEFAULT_DIM_DATE_END), "%Y-%m-%d"
).date()

AUDIT_TABLE_NAME = os.environ.get("ETL_AUDIT_TABLE", "ETL_AUDIT")
ERROR_MSG_MAX_LEN = int(os.environ.get("ETL_ERROR_MSG_MAX_LEN", DEFAULT_ERROR_MSG_MAX_LEN))

_HASH_BYTES: int = int(os.environ.get("ETL_HASH_BYTES", DEFAULT_HASH_BYTES))
if _HASH_BYTES < 8:
    raise ValueError(
        f"ETL_HASH_BYTES={_HASH_BYTES} is too small. "
        "Set ETL_HASH_BYTES=8 in .env to avoid surrogate key collisions."
    )


def hash_key(value) -> int | None:
    """Return a deterministic integer hash or None for empty values."""
    if value is None:
        return None

    try:
        import pandas as _pd
        if _pd.isna(value):
            return None
    except (ImportError, TypeError, ValueError):
        pass

    normalized = str(value).strip().upper()
    if not normalized:
        return None

    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return int.from_bytes(digest[:_HASH_BYTES], "big") & ((1 << (_HASH_BYTES * 8 - 1)) - 1)
