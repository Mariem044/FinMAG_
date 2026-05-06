# etl/pipeline.py
"""Main orchestrator for the SIAD MAG Distribution ETL.
It determines the run mode (full load vs. incremental delta),
creates the DW schema if missing, extracts → transforms → loads
all dimension tables (respecting FK order) followed by fact tables,
and records everything in the ETL_AUDIT table.
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from typing import Callable, Dict, List, Tuple, Optional

import pandas as pd

from config import DW_ENGINE, CHUNK_SIZE
from utils.logger import get_logger
from utils.audit import (
    acquire_lock,
    start_run,
    end_run,
    table_timer,
    get_last_run_info,
)
import ddl
import extract
import transform
import load

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helper – build lookup dicts (natural_hash → surrogate_id) after a dimension is loaded
# ---------------------------------------------------------------------------
def _build_lookup(
    table_name: str, natural_hash_col: str, surrogate_id_col: str
) -> Dict[int, int]:
    """Return a dict {natural_hash: surrogate_id} for a dimension.
    The DW tables contain the surrogate column (e.g. id_client_code) and the
    hashed natural key column (e.g. CT_Num_code)."""
    query = (
        f"SELECT {surrogate_id_col} AS sid, {natural_hash_col} AS nhash "
        f"FROM {table_name}"
    )
    df = pd.read_sql(query, DW_ENGINE)
    lookup = dict(zip(df["nhash"], df["sid"]))
    logger.debug(
        f"Lookup built for {table_name}: {len(lookup)} rows (hash→id)"
    )
    return lookup

# ---------------------------------------------------------------------------
# Definition of each ETL step (name, extract fn, optional transform fn, load fn)
# ---------------------------------------------------------------------------
Step = Tuple[
    str,                       # table name (DW table)
    Callable[..., pd.DataFrame],  # extraction function
    Optional[Callable[[pd.DataFrame, Dict[str, Dict[int, int]]], pd.DataFrame],  # transform (may need lookups)
    Callable[[pd.DataFrame, str, str], None],  # load function (df, table, mode)
]

# NOTE: many transform functions are simple hashing; we implement them inline when needed.

def _hash_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Apply `transform.hash_key` on each column listed in *cols*.
    The new column name will be `<original>_code`.
    """
    for col in cols:
        new_name = f"{col}_code"
        df[new_name] = df[col].apply(transform.hash_key)
    return df

# Define steps in the exact FK order required by the DDL (see ddl.ALL_DDL ordering).
# For brevity we only implement a subset that we have concrete extract functions for.
# Missing steps can be added later by the user.
STEPS: List[Step] = [
    # ---------------------------------------------------------------------
    # Dimensions – group 1 (no outgoing FK)
    # ---------------------------------------------------------------------
    (
        "DIM_DATE",
        lambda **kw: pd.DataFrame(),  # generated later in pipeline (no source table)
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode),
    ),
    (
        "DIM_SEGMENT",
        lambda **kw: extract.extract_dim_segment(),
        lambda df, lookups: _hash_columns(df, ["cbIndice"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode),
    ),
    (
        "DIM_COLLABORATEUR",
        lambda **kw: extract.extract_dim_collaborateur(kw.get("last_run")),
        lambda df, lookups: _hash_columns(df, ["CO_No"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode),
    ),
    (
        "DIM_FAMILLE",
        lambda **kw: extract.extract_dim_famille(),
        lambda df, lookups: _hash_columns(df, ["FA_CodeFamille", "CL_Code"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode),
    ),
    (
        "DIM_CLIENT",
        lambda **kw: extract.extract_dim_client_mag(kw.get("last_run")),
        # Resolve FK using lookups built previously
        lambda df, lookups: (
            _hash_columns(df, ["CT_Num"])
            .assign(
                id_segment=df["N_CatTarif"].map(lookups.get("DIM_SEGMENT", {})),
                id_collaborateur=df["CO_No"].map(lookups.get("DIM_COLLABORATEUR", {})),
            )
        ),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode),
    ),
    (
        "DIM_ARTICLE",
        lambda **kw: extract.extract_dim_article(kw.get("last_run")),
        lambda df, lookups: (
            _hash_columns(df, ["AR_Ref", "FA_CodeFamille", "CT_Num_fourn"])
            .assign(
                id_famille=df["FA_CodeFamille"].map(lookups.get("DIM_FAMILLE", {})),
                id_fournisseur=df["CT_Num_fourn"].map(lookups.get("DIM_FOURNISSEUR", {})),
            )
        ),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode),
    ),
    (
        "DIM_DEPOT",
        lambda **kw: extract.extract_dim_depot(kw.get("last_run")),
        lambda df, lookups: _hash_columns(df, ["DE_No"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode),
    ),
    (
        "DIM_CAISSE",
        lambda **kw: extract.extract_dim_caisse_mag(),
        lambda df, lookups: _hash_columns(df, ["CA_No", "JO_Num"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode),
    ),
    # ---------------------------------------------------------------------
    # Facts – FAIT_LIGNES_VENTE (example, many others can be added)
    # ---------------------------------------------------------------------
    (
        "FAIT_LIGNES_VENTE",
        lambda **kw: extract.extract_fait_lignes_vente(kw.get("last_run")),
        lambda df, lookups: (
            transform.add_fact_lignes_vente_calcs(df)
            .assign(
                id_date=df["DO_Date"].apply(lambda d: lookups.get("DIM_DATE", {}).get(d.date())),
                id_client=df["CT_Num"].apply(lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))),
                id_article=df["AR_Ref"].apply(lambda v: lookups.get("DIM_ARTICLE", {}).get(transform.hash_key(v))),
                id_depot=df["DE_No"].apply(lambda v: lookups.get("DIM_DEPOT", {}).get(transform.hash_key(v))),
                id_segment=df["N_CatTarif"].apply(lambda v: lookups.get("DIM_SEGMENT", {}).get(v)),
                id_collab=df["CO_No"].apply(lambda v: lookups.get("DIM_COLLABORATEUR", {}).get(transform.hash_key(v))),
            )
        ),
        lambda df, tbl, mode: load.load_fact(df, tbl, mode),
    ),
    # Additional fact steps (FAIT_REGLEMENTS, FAIT_ECRITURES, …) would follow the same pattern.
]

# ---------------------------------------------------------------------------
# Helper – generate DIM_DATE rows programmatically (2015‑01‑01 → 2030‑12‑31)
# ---------------------------------------------------------------------------
def _generate_dim_date(start: str = "2015-01-01", end: str = "2030-12-31") -> pd.DataFrame:
    dr = pd.date_range(start=start, end=end, freq="D")
    df = pd.DataFrame({"date_valeur": dr})
    df["annee"] = df["date_valeur"].dt.year.astype("Int16")
    df["mois"] = df["date_valeur"].dt.month.astype("Int16")
    df["jour"] = df["date_valeur"].dt.day.astype("Int16")
    df["semaine_iso"] = df["date_valeur"].dt.isocalendar().week.astype("Int16")
    df["jour_semaine"] = df["date_valeur"].dt.weekday + 1  # 1=Mon … 7=Sun
    df["est_weekend"] = (df["jour_semaine"] >= 6).astype("Int16")
    df["exercice"] = None  # will be filled later by business rule
    return df

# ---------------------------------------------------------------------------
# Main orchestration function
# ---------------------------------------------------------------------------
def run_pipeline() -> None:
    if not acquire_lock():
        logger.error("Another ETL run is active – aborting.")
        sys.exit(1)

    # Determine mode (full vs delta) based on ETL_AUDIT content
    last_run_date, mode = get_last_run_info()
    logger.info(f"Mode détecté : {mode.upper()}")

    # Ensure DW schema exists – create if missing
    # (ddl.create_all_tables will skip existing tables)
    ddl.create_all_tables(drop_existing=False)

    run_id = start_run(mode)
    lookups: Dict[str, Dict[int, int]] = {}
    try:
        for table_name, extract_fn, transform_fn, load_fn in STEPS:
            with table_timer(run_id, table_name) as ctx:
                logger.info(f"--- Processing {table_name} ({mode}) ---")
                # 1️⃣ Extraction
                df_raw = extract_fn(last_run=last_run_date)
                # 2️⃣ Transformation (optional)
                if transform_fn is not None:
                    df = transform_fn(df_raw, lookups)
                else:
                    df = df_raw
                # Special case for DIM_DATE – generate programmatically
                if table_name == "DIM_DATE":
                    df = _generate_dim_date()
                # 3️⃣ Load
                load_fn(df, table_name, mode)
                # 4️⃣ Build / update lookup dicts for later FK resolution
                # Assume the surrogate column follows the pattern id_<tablename>_code
                # and the natural‑key hash column ends with _code.
                # We try to infer the column names.
                # If the table has a column ending with "_code" that is NOT the PK, we use it.
                hash_cols = [c for c in df.columns if c.endswith("_code")]
                if hash_cols:
                    # Choose first hash column as natural key surrogate mapping.
                    natural_hash_col = hash_cols[0]
                    surrogate_id_col = next(
                        (c for c in df.columns if c.startswith("id_") and c.endswith("_code")),
                        None,
                    )
                    if surrogate_id_col is None:
                        # Fallback: DW table primary key is "id_<tablename>"
                        surrogate_id_col = f"id_{table_name.lower()}"
                    lookups[table_name] = _build_lookup(
                        table_name, natural_hash_col, surrogate_id_col
                    )
                ctx["rows_inserted"] = len(df)
                ctx["rows_updated"] = 0  # simple load; MERGE upserts handled inside load module
        end_run(run_id, "SUCCESS")
    except Exception as exc:
        # Capture stack trace for audit
        tb = traceback.format_exc()
        logger.exception("ETL pipeline failed")
        end_run(run_id, "ERROR", error_msg=str(exc))
        # Release lock and re‑raise to stop execution
        raise

if __name__ == "__main__":
    run_pipeline()
