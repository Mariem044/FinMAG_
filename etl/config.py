"""
config.py — SIAD MAG Distribution ETL
Configuration centrale : engines SQLAlchemy, hash_key, constantes métier.

FIXES
──────────────────────────────────────────────────────────────────────────
FIX-HASH : hash_key() defined ONLY here. transform.py imports it from here
           instead of duplicating it — eliminates silent drift risk.

BUG-6 FIX : DOMAINES dict corrected.
  The DBML schema comment said "4=Interne" but Sage Gestion Commerciale
  defines DO_Domaine as:
    0 = Vente, 1 = Achat, 2 = Stock, 3 = Interne
  There is no code 4 in standard Sage GC.  The DDL DIM_DOMAINE note also
  listed "4=Interne" — that note is a copy-paste error from the DBML.
  The extract filter in extract.py correctly uses domain 0 (Vente) only,
  so no data was lost, but the reference dict was wrong and would have
  produced a wrong libelle_domaine label for any domain-3 row loaded into
  DIM_DOMAINE.  Fixed: 3 -> "Interne" (removed the spurious 4 entry).
"""
from __future__ import annotations

import os
import zlib
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import logging
logging.getLogger("pyodbc").setLevel(logging.WARNING)

from dotenv import load_dotenv
from sqlalchemy import create_engine, Engine, event
from sqlalchemy.pool import QueuePool

# ── .env loading ─────────────────────────────────────────────────────────────
_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)

# ── Engine factory ────────────────────────────────────────────────────────────
def _sqlserver_tls_compat(conn_str: str) -> str:
    """Add SQL Server ODBC TLS flags when .env does not specify them."""
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
    """SQLAlchemy engine with pyodbc fast_executemany and pool."""
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

# ── ETL parameters ────────────────────────────────────────────────────────────
CHUNK_SIZE:     int = int(os.getenv("ETL_CHUNK_SIZE", "10000"))
DIM_DATE_START: str = os.getenv("DIM_DATE_START", "2015-01-01")
DIM_DATE_END:   str = os.getenv("DIM_DATE_END",   "2030-12-31")

# ── Business constants ────────────────────────────────────────────────────────
SEGMENTS: dict[int, str] = {
    1: "DÉTAILLANTS",
    2: "GROSSISTES",
    3: "HORECA",
    4: "SEMI-GROS",
    5: "DISTRIBUTEUR",
}

MODES_REGLEMENT: dict[int, str] = {
    1: "Espèces",
    2: "Chèque",
    3: "Virement",
    4: "Traite",
    5: "LCR",
    7: "Carte",
    8: "Autre",
}

ETATS_REGLEMENT: dict[int, str] = {
    0: "En cours",
    1: "Soldé",
    2: "Payé",
}

ETATS_DOCREGL: dict[int, str] = {
    0: "Non réglé",
    1: "Réglé",
}

TYPES_LIGNE: dict[int, str] = {
    1: "Ecriture comptable",
    2: "TVA",
    3: "Mouvement caisse",
    4: "Stock snapshot",
}

SENS_ECRITURE: dict[int, str] = {
    0: "Débit",
    1: "Crédit",
}

TYPES_TVA: dict[int, str] = {
    1: "TVA collectée",
    2: "TVA déductible",
}

TYPES_DOC: dict[int, str] = {
    1:  "Devis",
    2:  "Bon de commande",
    3:  "Bon de livraison",
    4:  "Bon de retour",
    5:  "Bon d'avoir HT",
    6:  "Facture",
    7:  "Avoir",
    11: "Préparation de commande",
    12: "Bon de commande fournisseur",
    13: "Bon de réception",
    14: "Bon de retour fournisseur",
    15: "Bon d'avoir fournisseur HT",
    16: "Facture fournisseur",
    17: "Avoir fournisseur",
}

# BUG-6 FIX: corrected Sage GC domain codes.
# Standard Sage GC: 0=Vente, 1=Achat, 2=Stock, 3=Interne.
# The previous version had 3="Interne" (correct) BUT the DBML comment
# and DIM_DOMAINE DDL note incorrectly wrote "4=Interne".
# There is no domain code 4 in Sage GC — removed the spurious entry.
DOMAINES: dict[int, str] = {
    0: "Vente",
    1: "Achat",
    2: "Stock",
    3: "Interne",
}

SEUIL_TENSION_STOCK: float = 0.8
FENETRE_RFM_JOURS:   int   = 365
BUCKETS_IMPAYE:      list[int] = [0, 30, 60, 90]

# ── Canonical hash function (SINGLE definition for the whole project) ─────────
_CRC32_MOD: int = 2**31 - 1   # max signed SQL Server INT


def hash_key(value: Optional[str | int | float]) -> Optional[int]:
    """
    CRC32-based surrogate for Sage natural keys.

    Rules:
      - strip + upper to normalise
      - abs + modulo to stay within signed SQL Server INT
      - None / NaN / empty string → None  (unknown key, not 0)

    Returns None instead of 0 so FK joins stay NULL-safe.
    """
    if value is None:
        return None
    import pandas as pd
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    normalized = str(value).strip().upper()
    if not normalized:
        return None
    return abs(zlib.crc32(normalized.encode("utf-8"))) % _CRC32_MOD


# ── DW table creation order ───────────────────────────────────────────────────
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
