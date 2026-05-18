from __future__ import annotations

import hashlib
import os
from datetime import timezone, date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import logging
import pandas as _pd

logging.getLogger("pyodbc").setLevel(logging.WARNING)

from dotenv import load_dotenv
from sqlalchemy import create_engine, Engine, event
from sqlalchemy.pool import QueuePool


_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)


def _sqlserver_tls_compat(conn_str: str) -> str:
    lowered = conn_str.lower()
    if "encrypt=" in lowered or "trustservercertificate=" in lowered:
        return conn_str

    if "odbc_connect=" in lowered:
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

    sep = "&" if "?" in conn_str else "?"
    return f"{conn_str}{sep}Encrypt=no&TrustServerCertificate=yes"


def _make_engine(conn_str: str, pool_size: int = 5) -> Engine:
    engine = create_engine(
        _sqlserver_tls_compat(conn_str),
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=10,
        pool_pre_ping=True,
        connect_args={
            "timeout": 30,
            "fast_executemany": True,
        },
    )

    @event.listens_for(engine, "connect")
    def _set_options(dbapi_conn, _rec):
        cursor = dbapi_conn.cursor()
        cursor.execute("SET NOCOUNT ON")
        cursor.close()

    return engine


DW_ENGINE:  Engine = _make_engine(os.environ["DW_CONN"],  pool_size=5)
MAG_ENGINE: Engine = _make_engine(os.environ["MAG_CONN"], pool_size=3)
GRT_ENGINE: Engine = _make_engine(os.environ["GRT_CONN"], pool_size=3)


CHUNK_SIZE:        int = int(os.environ["ETL_CHUNK_SIZE"])
DIM_DATE_START:    date = datetime.strptime(os.environ["DIM_DATE_START"], "%Y-%m-%d").date()
DIM_DATE_END:      date = datetime.strptime(os.environ["DIM_DATE_END"], "%Y-%m-%d").date()
AUDIT_TABLE_NAME:  str = os.environ.get("ETL_AUDIT_TABLE", "ETL_AUDIT")
ERROR_MSG_MAX_LEN: int = int(os.environ.get("ETL_ERROR_MSG_MAX_LEN", "500"))
SEUIL_TENSION_STOCK: float = float(os.environ.get("SEUIL_TENSION_STOCK", "0.5"))

# ── hash configuration ───────────────────────────────────────────────────────
# ETL_HASH_BYTES must be >= 8 to avoid birthday-paradox collisions on large
# datasets. With 4 bytes (31 bits of usable range) collisions are expected
# around 55,000 rows; 8 bytes (63 bits) raises that threshold to ~4.3 billion.
_HASH_BYTES: int = int(os.environ.get("ETL_HASH_BYTES", "8"))
if _HASH_BYTES < 8:
    raise ValueError(
        f"ETL_HASH_BYTES={_HASH_BYTES} is too small. "
        "Set ETL_HASH_BYTES=8 in .env to avoid surrogate key collisions."
    )


def hash_key(value: Optional[str | int | float]) -> Optional[int]:
    if value is None:
        return None
    try:
        if _pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    normalized = str(value).strip().upper()
    if not normalized:
        return None
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return int.from_bytes(digest[:_HASH_BYTES], "big") & ((1 << (_HASH_BYTES * 8 - 1)) - 1)


# ── business mappings ────────────────────────────────────────────────────────
JO_TYPE_TO_TVA_MAPPING = {
    1: 1,  # e.g., Vente -> Collectée
    0: 2,  # e.g., Achat -> Déductible
}

RT_ETAT_SOLDE = 2


DW_TABLES_ORDER: list[str] = [
    "DIM_DATE",
    "DIM_DOMAINE",
    "DIM_TYPE_DOC",
    "DIM_MODE_REGLEMENT",
    "DIM_ETAT_REGLEMENT",
    "DIM_ETAT_DOCREGL",
    "DIM_TYPE_LIGNE",
    "DIM_SENS_ECRITURE",
    "DIM_TYPE_TVA",
    "DIM_TYPE_MVT_CAISSE",
    "DIM_BANQUE",
    "DIM_SEGMENT",
    "DIM_COLLABORATEUR",
    "DIM_JOURNAL",
    "DIM_FOURNISSEUR",
    "DIM_FAMILLE",
    "DIM_CLIENT",
    "DIM_ARTICLE",
    "DIM_DEPOT",
    "DIM_CAISSE",
    "FAIT_LIGNES_VENTE",
    "FAIT_REGLEMENTS",
    "FAIT_ECRITURES",
    "ETL_AUDIT",
]
