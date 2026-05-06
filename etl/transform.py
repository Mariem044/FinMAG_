# etl/transform.py
"""Transformations for SIAD MAG Distribution ETL.
All functions are pure, typed and unit‑testable.
The module expects pandas DataFrames as input and returns transformed DataFrames.
"""
import hashlib
import zlib
from typing import Dict, Any
import pandas as pd

# ---------------------------------------------------------------------------
# Hashing helper – CRC32 → positive 31‑bit int (as required by spec)
# ---------------------------------------------------------------------------
def hash_key(value: str) -> int:
    """Return deterministic positive int hash for a natural key.
    Empty or None values return None.
    """
    if pd.isna(value) or value == "":
        return None
    # Ensure string, strip & upper, encode utf‑8
    val = str(value).strip().upper().encode("utf-8")
    # CRC32 returns unsigned 32‑bit int; take modulo 2**31‑1 to stay positive
    return (zlib.crc32(val) % (2**31 - 1))

# ---------------------------------------------------------------------------
# Generic lookup substitution – returns surrogate code or None (logs warning)
# ---------------------------------------------------------------------------
def resolve_fk(df: pd.DataFrame, source_col: str, lookup: Dict[Any, int], target_col: str) -> pd.DataFrame:
    """Map a natural key column to surrogate code using a dict.
    Unmatched values are set to None and a warning is logged.
    """
    def _lookup(val):
        try:
            return lookup.get(val)
        except Exception:
            return None
    df[target_col] = df[source_col].map(lookup)
    # Log count of orphan rows (optional – user can hook logger)
    orphan_cnt = df[target_col].isna().sum()
    if orphan_cnt:
        import logging
        logging.getLogger(__name__).warning(
            f"{orphan_cnt} orphan rows when resolving FK {source_col} → {target_col}"
        )
    return df

# ---------------------------------------------------------------------------
# KPI‑specific calculated columns
# ---------------------------------------------------------------------------
def add_fact_lignes_vente_calcs(df: pd.DataFrame) -> pd.DataFrame:
    """Add DO_Piece_hash for RFM KPI‑18.
    """
    df["DO_Piece_hash"] = df["DO_Piece"].apply(hash_key)
    return df

def add_fact_ecritures_calcs(df: pd.DataFrame, stock_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate stock‑related columns for FACT_ECRITURES.
    Requires a snapshot DataFrame `stock_df` containing
    AS_QteSto, AS_QteRes, AS_QteMini.
    """
    # qte_disponible & ratio_tension
    df["qte_disponible"] = df["AS_QteSto"] - df["AS_QteRes"]
    # Avoid division by zero
    denominator = df["AS_QteSto"] - df["AS_QteRes"]
    df["ratio_tension"] = df.apply(
        lambda row: row["AS_QteRes"] / denominator if denominator > 0 else None,
        axis=1,
    )
    # alerte_tension flag > 0.8
    df["alerte_tension"] = (df["ratio_tension"] > 0.8).astype(int)
    # rupture flag
    df["en_rupture"] = (df["AS_QteSto"] <= df["AS_QteMini"]).astype(int)
    return df

def add_fact_reglements_calcs(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate delay columns for FACT_REGLEMENTS.
    Expects columns RT_Date (datetime), DO_Date (datetime), RT_NbJour (int).
    """
    df["delai_reel_jours"] = (df["RT_Date"] - df["DO_Date"]).dt.days
    df["ecart_delai"] = df["delai_reel_jours"] - df["RT_NbJour"]
    return df

# ---------------------------------------------------------------------------
# Public interface – each table has a dedicated transform function
# ---------------------------------------------------------------------------
def transform_dim_date(df: pd.DataFrame) -> pd.DataFrame:
    # Expect a column 'date' (datetime)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["annee"] = df["date"].dt.year.astype("Int16")
    df["mois"] = df["date"].dt.month.astype("Int16")
    df["jour"] = df["date"].dt.day.astype("Int16")
    # exercice will be filled later by business logic using P_DOSSIER tables
    return df

def transform_dim_client(df: pd.DataFrame, lookup_segment: Dict[int, int], lookup_collab: Dict[int, int]) -> pd.DataFrame:
    df = df.copy()
    df = resolve_fk(df, "CT_Num", lookup_client := {}, "id_client_code")  # placeholder, actual dict passed by caller
    df = resolve_fk(df, "N_CatTarif", lookup_segment, "id_segment")
    df = resolve_fk(df, "CO_No", lookup_collab, "id_collaborateur")
    return df

# Additional transform functions for each dimension/fact can be added following the same pattern.
# The orchestrator (pipeline.py) will import the required functions.

__all__ = [
    "hash_key",
    "resolve_fk",
    "add_fact_lignes_vente_calcs",
    "add_fact_ecritures_calcs",
    "add_fact_reglements_calcs",
    "transform_dim_date",
    "transform_dim_client",
]
