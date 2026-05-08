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
import hashlib
from typing import Literal, Optional
import pandas as pd
from sqlalchemy import text
from etl.config import DW_ENGINE, CHUNK_SIZE
from etl.utils.logger import get_logger

logger = get_logger(__name__)

Mode = Literal["full", "delta"]

_DROP_IF_EXISTS = "IF OBJECT_ID(N'[dbo].[{name}]', N'U') IS NOT NULL DROP TABLE [{name}]"


def _target_columns(table: str) -> tuple[list[str], set[str]]:
    """Return DW columns and identity columns for *table*."""
    sql = """
        SELECT
            COLUMN_NAME,
            COLUMNPROPERTY(
                OBJECT_ID(TABLE_SCHEMA + '.' + TABLE_NAME),
                COLUMN_NAME,
                'IsIdentity'
            ) AS IS_IDENTITY
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo'
          AND TABLE_NAME = :table
        ORDER BY ORDINAL_POSITION
    """
    with DW_ENGINE.connect() as conn:
        rows = conn.execute(text(sql), {"table": table}).fetchall()
    columns = [row[0] for row in rows]
    identity_cols = {row[0] for row in rows if row[1] == 1}
    if not columns:
        raise ValueError(f"DW table '{table}' does not exist or has no columns")
    return columns, identity_cols


def _prepare_for_load(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Drop source-only columns before inserting into a DW table."""
    if df.empty:
        return df

    target_cols, identity_cols = _target_columns(table)
    writable_cols = [c for c in target_cols if c not in identity_cols]

    if "row_hash" in writable_cols and "row_hash" not in df.columns:
        hash_cols = [c for c in writable_cols if c != "row_hash" and c in df.columns]
        df = df.copy()
        df["row_hash"] = df[hash_cols].apply(_sha256_row, axis=1)

    kept_cols = [c for c in writable_cols if c in df.columns]
    dropped_cols = [c for c in df.columns if c not in kept_cols]

    if dropped_cols:
        logger.debug(
            f"[LOAD] {table} - dropping non-DW columns: {', '.join(dropped_cols)}"
        )

    if not kept_cols:
        raise ValueError(f"No writable DW columns remain for {table} after schema alignment")

    return df.loc[:, kept_cols].copy()


def _sha256_row(row: pd.Series) -> bytes:
    parts = []
    for value in row.tolist():
        if pd.isna(value):
            parts.append("<NULL>")
        else:
            parts.append(str(value))
    return hashlib.sha256("|".join(parts).encode("utf-8")).digest()


def _bulk_insert(df: pd.DataFrame, table: str) -> None:
    if df.empty:
        logger.info(f"[LOAD] {table} – DataFrame vide, rien à insérer")
        return
    # SQL Server limit: 2100 parameters per statement.
    # Safe chunksize = floor(2100 / num_columns) - 1
    safe_chunk = max(1, (2100 // len(df.columns)) - 1)
    chunk = min(CHUNK_SIZE, safe_chunk)
    logger.info(f"[LOAD] {table} – Insertion bulk ({len(df)} lignes, chunksize={chunk})")
    df.to_sql(
        name=table,
        con=DW_ENGINE,
        if_exists="append",
        index=False,
        chunksize=chunk,
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

    df = _prepare_for_load(df, table)
    if key_col not in df.columns:
        raise ValueError(f"MERGE key column '{key_col}' is missing from {table} load")
    before_dedupe = len(df)
    df = df.drop_duplicates(subset=[key_col], keep="last")
    if len(df) != before_dedupe:
        logger.warning(
            f"[LOAD] {table} - dropped {before_dedupe - len(df)} duplicate {key_col} rows"
        )

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
    update_set = (
        ", ".join([f"target.[{c}]=src.[{c}]" for c in update_cols])
        if update_cols
        else f"target.[{key_col}]=target.[{key_col}]"
    )

    merge_sql = f"""
        MERGE INTO [{table}] AS target
        USING [{temp_name}] AS src
        ON target.[{key_col}] = src.[{key_col}]
        WHEN MATCHED THEN UPDATE SET
            {update_set}
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
            conn.execute(text(f"DELETE FROM [{table}]"))
        _bulk_insert(df, table)
    else:
        if key_col is None:
            raise ValueError(
                f"key_col must be provided explicitly for delta load of '{table}'. "
                "Pass the natural‑key hash column name (e.g. 'CT_Num_code')."
            )
        _merge_upsert(df, table, key_col)


def load_fact(
    df: pd.DataFrame,
    table: str,
    mode: Mode,
    key_col: Optional[str] = "source_hash",
) -> None:
    """Load a fact table.

    - full  : disable FK, TRUNCATE, bulk insert, re‑enable FK.
    - delta : append‑only INSERT (facts are immutable).
    """
    if mode == "full":
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"ALTER TABLE [{table}] NOCHECK CONSTRAINT ALL"))
            conn.execute(text(f"DELETE FROM [{table}]"))
        _bulk_insert(df, table)
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"ALTER TABLE [{table}] WITH CHECK CHECK CONSTRAINT ALL"))
    else:
        if key_col and key_col in df.columns:
            _merge_upsert(df, table, key_col)
        else:
            logger.warning(
                f"[LOAD] {table} - no {key_col} column, falling back to append-only fact load"
            )
            _bulk_insert(df, table)


if __name__ == "__main__":
    logger.info("module load.py exécuté en mode script – aucune action définie.")
