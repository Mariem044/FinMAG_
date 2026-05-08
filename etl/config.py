"""
config.py — SIAD MAG Distribution ETL
Configuration centrale : engines SQLAlchemy, constantes KPI, utilitaires globaux.
"""
from __future__ import annotations

import os
import zlib
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import logging
logging.getLogger("pyodbc").setLevel(logging.WARNING)
from sqlalchemy import create_engine, Engine, event
from sqlalchemy.pool import QueuePool

# ── Chargement .env ─────────────────────────────────────────────────────────
_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)

# ── Connexions ───────────────────────────────────────────────────────────────
def _make_engine(conn_str: str, pool_size: int = 5) -> Engine:
    """Crée un engine SQLAlchemy Core avec pool configurable.

    Bug 20 fix: ``fast_executemany`` is a pyodbc connection-level setting and
    must be passed inside ``connect_args``, not as a top-level keyword to
    ``create_engine`` (where SQLAlchemy silently ignores unknown kwargs).
    """
    engine = create_engine(
        conn_str,
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=10,
        pool_pre_ping=True,
        connect_args={
            "timeout": 30,
            "fast_executemany": True,   # pyodbc bulk-insert optimisation
        },
    )
    # Désactiver autocommit — contrôle explicite des transactions
    @event.listens_for(engine, "connect")
    def _set_options(dbapi_conn, _rec):
        cursor = dbapi_conn.cursor()
        cursor.execute("SET NOCOUNT ON")
        cursor.close()

    return engine


DW_ENGINE:  Engine = _make_engine(os.environ["DW_CONN"],  pool_size=5)
MAG_ENGINE: Engine = _make_engine(os.environ["MAG_CONN"], pool_size=3)
GRT_ENGINE: Engine = _make_engine(os.environ["GRT_CONN"], pool_size=3)

# ── Paramètres ETL ───────────────────────────────────────────────────────────
CHUNK_SIZE:     int = int(os.getenv("ETL_CHUNK_SIZE", "10000"))
DIM_DATE_START: str = os.getenv("DIM_DATE_START", "2015-01-01")
DIM_DATE_END:   str = os.getenv("DIM_DATE_END",   "2030-12-31")

# ── Constantes métier ────────────────────────────────────────────────────────
# Valeurs connues DIM_SEGMENT (P_CATTARIF.cbIndice)
SEGMENTS: dict[int, str] = {
    1: "DÉTAILLANTS",
    2: "GROSSISTES",
    3: "HORECA",
    4: "SEMI-GROS",
    5: "DISTRIBUTEUR",
}

# Valeurs DIM_MODE_REGLEMENT
MODES_REGLEMENT: dict[int, str] = {
    1: "Espèces",
    2: "Chèque",
    3: "Virement",
    4: "Traite",
    5: "LCR",
    7: "Carte",
    8: "Autre",
}

# Valeurs DIM_ETAT_REGLEMENT
ETATS_REGLEMENT: dict[int, str] = {
    0: "En cours",
    1: "Soldé",
    2: "Payé",
}

# Valeurs DIM_ETAT_DOCREGL
ETATS_DOCREGL: dict[int, str] = {
    0: "Non réglé",
    1: "Réglé",
}

# Valeurs DIM_TYPE_LIGNE (discriminant FAIT_ECRITURES)
TYPES_LIGNE: dict[int, str] = {
    1: "Ecriture comptable",
    2: "TVA",
    3: "Mouvement caisse",
    4: "Stock snapshot",
}

# Valeurs DIM_SENS_ECRITURE
SENS_ECRITURE: dict[int, str] = {
    0: "Débit",
    1: "Crédit",
}

# Valeurs DIM_TYPE_TVA
TYPES_TVA: dict[int, str] = {
    1: "TVA collectée",
    2: "TVA déductible",
}

# Valeurs DIM_TYPE_DOC (DO_Type Sage communs)
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

# Domaines DO_Domaine Sage
DOMAINES: dict[int, str] = {
    0: "Vente",
    1: "Achat",
    2: "Stock",
    3: "Interne",
}

# Seuil alerte tension stock KPI-14
SEUIL_TENSION_STOCK: float = 0.8

# Fenêtre RFM glissante (jours) KPI-18
FENETRE_RFM_JOURS: int = 365

# Buckets ancienneté impayés KPI-08 (jours)
BUCKETS_IMPAYE: list[int] = [0, 30, 60, 90]   # bornes inférieures


# ── Fonction de hashage clés naturelles ─────────────────────────────────────
_CRC32_MOD: int = 2**31 - 1   # max INT SQL Server signé


def hash_key(value: Optional[str | int | float]) -> int:
    """
    Convertit une clé naturelle nvarchar Sage en INT surrogate CRC32.

    Règles :
    - strip + upper pour normaliser
    - abs + modulo pour rester dans INT SQL Server signé
    - None / NaN → 0 (clé inconnue)

    >>> hash_key("ART-001")
    1234567890  # exemple
    """
    if value is None:
        return 0
    normalized = str(value).strip().upper()
    if not normalized:
        return 0
    return abs(zlib.crc32(normalized.encode("utf-8"))) % _CRC32_MOD


# ── Noms des tables DW ───────────────────────────────────────────────────────
DW_TABLES_ORDER: list[str] = [
    # Groupe 1 — sans FK sortante
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
    # Groupe 2
    "DIM_SEGMENT",
    "DIM_COLLABORATEUR",
    "DIM_JOURNAL",
    "DIM_FOURNISSEUR",
    # Groupe 3
    "DIM_FAMILLE",
    # Groupe 4
    "DIM_CLIENT",
    # Groupe 5
    "DIM_ARTICLE",
    # Groupe 6
    "DIM_DEPOT",
    "DIM_CAISSE",
    # Groupe 7 — Faits
    "FAIT_LIGNES_VENTE",
    "FAIT_REGLEMENTS",
    "FAIT_ECRITURES",
    # Groupe 8
    "ETL_AUDIT",
]
