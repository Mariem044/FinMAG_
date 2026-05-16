from __future__ import annotations

import hashlib
import os
from datetime import timezone
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
DIM_DATE_START:    str = os.environ["DIM_DATE_START"]
DIM_DATE_END:      str = os.environ["DIM_DATE_END"]
ERROR_MSG_MAX_LEN: int = int(os.environ.get("ETL_ERROR_MSG_MAX_LEN", "500"))

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

# ── stock tension threshold ──────────────────────────────────────────────────
# Articles with ratio_tension >= SEUIL_TENSION_STOCK are flagged as "tense".
SEUIL_TENSION_STOCK: float = float(os.environ.get("SEUIL_TENSION_STOCK", "0.5"))


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

TYPES_MVT_CAISSE: dict[int, str] = {
    1: "Entree especes",
    2: "Sortie especes",
    3: "Entree cheque",
    4: "Sortie cheque",
    5: "Virement caisse",
    6: "Depot bancaire",
    7: "Retrait bancaire",
    8: "Remise en banque",
    54: "Regularisation caisse",
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

DOMAINES: dict[int, str] = {
    0: "Vente",
    1: "Achat",
    2: "Stock",
    3: "Interne",
}

AUDIT_TABLE_NAME: str = os.environ["ETL_AUDIT_TABLE"]


def hash_key(value: Optional[str | int | float]) -> Optional[int]:
    """
    Compute a stable surrogate key for a natural key value.

    Uses the first _HASH_BYTES bytes of SHA-256 (big-endian, sign-masked)
    so the result fits in a SQL Server BIGINT column without overflow.
    The mask strips the sign bit so all values are positive.

    Returns None for NULL/NaN/empty inputs.
    """
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
