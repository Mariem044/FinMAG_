# etl/transform.py
"""Transformations for SIAD MAG Distribution ETL.
All functions are pure, typed and unit-testable.
The module expects pandas DataFrames as input and returns transformed DataFrames.

BUG FIXES (v14 → v14.1)
─────────────────────────────────────────────────────────────
BUG-8 : add_fact_ecritures_calcs() — alerte_tension is now NULL (pd.NA)
         for rows where ratio_tension is NULL, instead of 0.
         DDL declares alerte_tension SMALLINT NULL and the schema intent is
         that non-stock rows (type_ligne ≠ 4) carry NULL, not a false 0.
         Using pandas nullable Int8 avoids the silent 0 that (NaN > 0.8)
         previously produced.
"""
import zlib
from typing import Dict, Any, Optional
import pandas as pd

# ---------------------------------------------------------------------------
# Hashing helper – CRC32 → positive 31-bit int (as required by spec)
# ---------------------------------------------------------------------------
def hash_key(value: str) -> int:
    """Return deterministic positive int hash for a natural key.
    Empty or None values return None.
    """
    if pd.isna(value) or value == "":
        return None
    val = str(value).strip().upper().encode("utf-8")
    return zlib.crc32(val) % (2**31 - 1)


# ---------------------------------------------------------------------------
# Generic lookup substitution
# ---------------------------------------------------------------------------
def resolve_fk(
    df: pd.DataFrame,
    source_col: str,
    lookup: Dict[Any, int],
    target_col: str,
    orphan_threshold: Optional[int] = None,
) -> pd.DataFrame:
    """Map a natural key column to surrogate id using *lookup*.

    Parameters
    ----------
    orphan_threshold:
        Maximum number of unmatched (NULL) rows allowed.
        ``None`` (default) = any number tolerated (warning only).
        Provide ``0`` to treat any orphan as fatal.
    """
    df[target_col] = df[source_col].map(lookup)
    orphan_cnt = int(df[target_col].isna().sum())
    if orphan_cnt:
        import logging
        logging.getLogger(__name__).warning(
            f"{orphan_cnt} orphan rows when resolving FK {source_col} → {target_col}"
        )
        if orphan_threshold is not None and orphan_cnt > orphan_threshold:
            raise ValueError(
                f"{orphan_cnt} orphan rows exceed acceptable threshold "
                f"({orphan_threshold}) resolving FK {source_col} → {target_col}"
            )
    return df


# ---------------------------------------------------------------------------
# KPI-specific calculated columns
# ---------------------------------------------------------------------------
def add_fact_lignes_vente_calcs(df: pd.DataFrame) -> pd.DataFrame:
    """Add DO_Piece_hash for RFM KPI-18."""
    df["DO_Piece_hash"] = df["DO_Piece"].apply(hash_key)
    return df


def add_fact_ecritures_calcs(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate stock-related columns for FAIT_ECRITURES.

    Expects columns AS_QteSto, AS_QteRes, AS_QteMini already present in *df*
    (the pipeline merges the artstock snapshot into the fact DataFrame before
    calling this function).

    Bug fixes applied
    -----------------
    * Removed unused ``stock_df`` parameter (Bug 2).
    * ``ratio_tension`` is now fully vectorised — no ``apply`` with a Series
      denominator compared as a scalar (Bug 1).
    * BUG-8: ``alerte_tension`` is now NULL (pd.NA) when ``ratio_tension``
      is NULL instead of silently emitting 0. DDL declares SMALLINT NULL;
      non-stock rows must be NULL, not 0.
    """
    df["qte_disponible"] = df["AS_QteSto"] - df["AS_QteRes"]
    denominator = df["AS_QteSto"] - df["AS_QteRes"]
    # Where denominator <= 0 set ratio to None; otherwise divide vectorially.
    df["ratio_tension"] = (df["AS_QteRes"] / denominator).where(
        denominator > 0, other=None
    )
    df["en_rupture"] = (df["AS_QteSto"] <= df["AS_QteMini"]).astype("Int8")

    # BUG-8 fix: use nullable Int8 so rows where ratio_tension is NaN/None
    # receive pd.NA (→ SQL NULL) rather than 0.
    # (NaN > 0.8) evaluates to False in numpy, producing a misleading 0.
    tension_flag = df["ratio_tension"].where(df["ratio_tension"].notna())
    df["alerte_tension"] = (
        (tension_flag > 0.8)
        .where(tension_flag.notna())        # NaN rows stay NaN
        .astype("Int8")                     # converts True→1, False→0, NaN→pd.NA
    )

    return df


def add_fact_reglements_calcs(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate delay columns for FAIT_REGLEMENTS.
    Expects RT_Date (datetime), DO_Date (datetime), RT_NbJour (int).

    Note: delai_reel_jours and ecart_delai are stored as INT in the DDL
    (not SMALLINT) to avoid truncation for debts older than ~90 years.
    """
    df = df.copy()
    df["RT_Date"] = pd.to_datetime(df["RT_Date"], errors="coerce")
    df["DO_Date"] = pd.to_datetime(df["DO_Date"], errors="coerce")
    df["RT_NbJour"] = pd.to_numeric(df["RT_NbJour"], errors="coerce")
    # Use plain Python int (not int16/int32) — pandas will cast to nullable
    # Int64 via _prepare_for_load when writing to SQL Server INT column.
    df["delai_reel_jours"] = (df["RT_Date"] - df["DO_Date"]).dt.days
    df["ecart_delai"] = df["delai_reel_jours"] - df["RT_NbJour"]
    return df


def add_fact_reglements_bucket(df: pd.DataFrame) -> pd.DataFrame:
    """Assign bucket_impaye based on delai_reel_jours and DR_Regle (KPI-08).

    Buckets:
        0 = 0–30 days
        1 = 31–60 days
        2 = 61–90 days
        3 = > 90 days

    Only unpaid rows (DR_Regle == 0) receive a bucket; paid rows get NULL.
    """
    def _bucket(row) -> Optional[int]:
        if row.get("DR_Regle", 1) != 0:
            return None
        days = row.get("delai_reel_jours")
        if days is None or pd.isna(days):
            return None
        days = int(days)
        if days <= 30:
            return 0
        if days <= 60:
            return 1
        if days <= 90:
            return 2
        return 3

    df = df.copy()
    df["bucket_impaye"] = df.apply(_bucket, axis=1)
    return df


# ---------------------------------------------------------------------------
# Public interface – each table has a dedicated transform function
# ---------------------------------------------------------------------------
def transform_dim_date(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["annee"] = df["date"].dt.year.astype("Int16")
    df["mois"] = df["date"].dt.month.astype("Int16")
    df["jour"] = df["date"].dt.day.astype("Int16")
    return df


def transform_dim_client(
    df: pd.DataFrame,
    lookup_segment: Dict[int, int],
    lookup_collab: Dict[int, int],
) -> pd.DataFrame:
    """Hash CT_Num natural key and resolve FK columns for DIM_CLIENT.

    CT_Num → CT_Num_code : CRC32 hash stored as the surrogate natural key
                           (no FK lookup — the hash *is* the code column).
    N_CatTarif → id_segment : FK to DIM_SEGMENT (lookup keys are CRC32 hashes
                              of cbIndice, not raw ints — hash N_CatTarif first).
    CO_No      → id_collab  : FK to DIM_COLLABORATEUR (DDL column = id_collab,
                              not id_collaborateur).
    """
    df = df.copy()
    df["CT_Num_code"] = df["CT_Num"].apply(hash_key)
    # Bug fix #2: hash N_CatTarif before lookup — DIM_SEGMENT keys are CRC32 hashes
    df["_N_CatTarif_hash"] = df["N_CatTarif"].apply(hash_key)
    df = resolve_fk(df, "_N_CatTarif_hash", lookup_segment, "id_segment")
    df = df.drop(columns=["_N_CatTarif_hash"])
    # Bug fix #3: column must be id_collab to match DDL DIM_COLLABORATEUR PK ref
    df = resolve_fk(df, "CO_No", lookup_collab, "id_collab")
    return df


__all__ = [
    "hash_key",
    "resolve_fk",
    "add_fact_lignes_vente_calcs",
    "add_fact_ecritures_calcs",
    "add_fact_reglements_calcs",
    "add_fact_reglements_bucket",
    "transform_dim_date",
    "transform_dim_client",
]