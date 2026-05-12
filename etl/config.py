from __future__ import annotations

import os
import hashlib
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import logging
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


CHUNK_SIZE:     int = int(os.getenv("ETL_CHUNK_SIZE", "10000"))
DIM_DATE_START: str = os.getenv("DIM_DATE_START", "2015-01-01")
DIM_DATE_END:   str = os.getenv("DIM_DATE_END",   "2030-12-31")


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

SEUIL_TENSION_STOCK: float = 0.8
FENETRE_RFM_JOURS:   int   = 365
BUCKETS_IMPAYE:      list[int] = [0, 30, 60, 90]
FENETRE_DSI_JOURS:   int   = 365

RFM_SEGMENTS: dict[str, list[str]] = {
    "Champion":    ["0-30j", "4-5 cmd", "TOP Montant"],
    "Fidèle":      ["30-60j", "3-4 cmd", "BON Montant"],
    "À risque":    ["60-90j", "1-2 cmd", "MOYEN Montant"],
    "Dormant":     [">90j", "1 cmd", "FAIBLE Montant"],
}


def hash_key(value: Optional[str | int | float]) -> Optional[int]:
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
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    # Return a positive 32-bit int for SQL INT compatibility.
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF



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
