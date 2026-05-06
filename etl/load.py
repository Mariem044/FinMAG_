# etl/load.py
"""Loading module for SIAD MAG Distribution ETL.
Provides bulk load for dimensions (full) and MERGE‑based upserts for delta.
All operations are wrapped in a transaction per table.

Bug fixes applied
-----------------
Bug 5  – SET clause now excludes the IDENTITY PK column (id_<table>).
Bug 6  – DROP TABLE executed as a separate statement, not inside MERGE body.
Bug 7  – Temp table uses ``_etl_tmp_`` prefix (no ``#``); dropped before and
          after use so pandas.to_sql can create a regular permanent staging
          table without name collisions.
Bug 8  – ``load_dimension`` now accepts an explicit ``key_col`` parameter;
          the broken automatic inference is removed.
"""
import logging
from typing import Literal, Optional
import pandas as pd
from sqlalchemy import text
from etl.config import DW_ENGINE, CHUNK_SIZE
from etl.utils.logger import get_logger

logger = get_logger(__name__)

Mode = Literal["full", "delta"]

_DROP_IF_EXISTS = "IF OBJECT_ID(N'[dbo].[{name}]', N'U') IS NOT NULL DROP TABLE [{name}]"


def _bulk_insert(df: pd.DataFrame, table: str) -> None:
    """Insert DataFrame into DW table using pandas.to_sql (method='multi')."""
    if df.empty:
        logger.info(f"[LOAD] {table} – DataFrame vide, rien à insérer")
        return
    logger.info(f"[LOAD] {table} – Insertion bulk ({len(df)} lignes, chunksize={CHUNK_SIZE})")
    df.to_sql(
        name=table,
        con=DW_ENGINE,
        if_exists="append",
        index=False,
        chunksize=CHUNK_SIZE,
        method="multi",
    )


def _merge_upsert(df: pd.DataFrame, table: str, key_col: str) -> None:
    """Perform a MERGE (upsert) on the DW table.

    The *key_col* is the natural‑key hash column used to match rows
    (e.g. ``CT_Num_code``).  The IDENTITY PK column (``id_<table>``) is
    automatically excluded from the UPDATE SET list so SQL Server does not
    reject the statement.
    """
    if df.empty:
        logger.info(f"[LOAD] {table} – DataFrame vide, rien à MERGE")
        return

    # Bug 7 fix: use a plain permanent staging table name (no # prefix).
    temp_name = f"_etl_tmp_{table}"

    # Drop any leftover staging table from a previous failed run.
    with DW_ENGINE.begin() as conn:
        conn.execute(text(_DROP_IF_EXISTS.format(name=temp_name)))

    logger.debug(f"[LOAD] {table} – création table temporaire {temp_name}")
    df.to_sql(
        name=temp_name,
        con=DW_ENGINE,
        if_exists="replace",
        index=False,
        chunksize=CHUNK_SIZE,
        method="multi",
    )

    # Bug 5 fix: exclude both the natural‑key hash col AND the IDENTITY PK.
    pk_col = f"id_{table.lower()}"
    update_cols = [c for c in df.columns if c not in (key_col, pk_col)]

    merge_sql = f"""
        MERGE INTO [{table}] AS target
        USING [{temp_name}] AS src
        ON target.[{key_col}] = src.[{key_col}]
        WHEN MATCHED THEN UPDATE SET
            {', '.join([f'target.[{c}]=src.[{c}]' for c in update_cols])}
        WHEN NOT MATCHED THEN INSERT ({', '.join([f'[{c}]' for c in df.columns])})
            VALUES ({', '.join([f'src.[{c}]' for c in df.columns])});
    """

    # Bug 6 fix: execute DROP TABLE as a separate statement after MERGE.
    drop_sql = _DROP_IF_EXISTS.format(name=temp_name)

    with DW_ENGINE.begin() as conn:
        conn.execute(text(merge_sql))
        conn.execute(text(drop_sql))

    logger.info(f"[LOAD] {table} – MERGE upsert complet ({len(df)} lignes)")


def load_dimension(
    df: pd.DataFrame,
    table: str,
    mode: Mode,
    key_col: Optional[str] = None,
) -> None:
    """Load a dimension table.

    - full  : TRUNCATE then bulk insert.
    - delta : MERGE based on *key_col* (the natural‑key hash column).

    Bug 8 fix: ``key_col`` must be supplied explicitly for delta mode;
    the previous automatic inference was always wrong for multi‑word table names.
    """
    if mode == "full":
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE [{table}]"))
        _bulk_insert(df, table)
    else:
        if key_col is None:
            raise ValueError(
                f"key_col must be provided explicitly for delta load of '{table}'. "
                "Pass the natural‑key hash column name (e.g. 'CT_Num_code')."
            )
        _merge_upsert(df, table, key_col)


def load_fact(df: pd.DataFrame, table: str, mode: Mode) -> None:
    """Load a fact table.

    - full  : disable FK, TRUNCATE, bulk insert, re‑enable FK.
    - delta : append‑only INSERT (facts are immutable).
    """
    if mode == "full":
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"ALTER TABLE [{table}] NOCHECK CONSTRAINT ALL"))
            conn.execute(text(f"TRUNCATE TABLE [{table}]"))
        _bulk_insert(df, table)
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"ALTER TABLE [{table}] WITH CHECK CHECK CONSTRAINT ALL"))
    else:
        _bulk_insert(df, table)


if __name__ == "__main__":
    logger.info("module load.py exécuté en mode script – aucune action définie.")
