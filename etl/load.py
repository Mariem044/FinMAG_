# etl/load.py
"""Loading module for SIAD MAG Distribution ETL.
Provides bulk load for dimensions (full) and MERGE-based upserts for delta.
All operations are wrapped in a transaction per table.

FIXES APPLIED
─────────────────────────────────────────────────────────────
FIX-BINARY : _merge_upsert() — binary columns (source_hash, row_hash)
             are now serialised to hex strings before pandas.to_sql so the
             staging table gets VARCHAR(64) instead of varchar(max).
             The MERGE ON clause and INSERT VALUES use
             CONVERT(VARBINARY(32), src.[col], 2)  (style 2 = hex, no 0x)
             so SQL Server re-materialises them as BINARY(32) correctly.
             This fixes:
               Implicit conversion from data type varchar(max) to binary
               is not allowed. (Error 257)

FIX-NEW : _merge_upsert() — removed broken pk_col name inference
           (f"id_{table.lower()}") which was always wrong for fact tables
           and multi-word table names. Since _prepare_for_load() already
           strips all IDENTITY columns before _merge_upsert() builds its
           column list, the pk_col exclusion was redundant. The fix simply
           excludes key_col from the UPDATE SET clause; the identity column
           is already absent from df.columns at that point.

Original fixes (preserved)
─────────────────────────────────────────────────────────────
Bug 5  – SET clause now excludes the IDENTITY PK column (id_<table>).
Bug 6  – DROP TABLE executed as a separate statement, not inside MERGE body.
Bug 7  – Temp table uses _etl_tmp_ prefix (no #); dropped before and
          after use so pandas.to_sql can create a regular permanent staging
          table without name collisions.
Bug 8  – load_dimension now accepts an explicit key_col parameter;
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

# Columns that carry raw bytes and must be hex-encoded for pandas.to_sql
_BINARY_COLS = {"source_hash", "row_hash"}


def _target_columns(table: str) -> tuple[list[str], set[str]]:
    """Return (all_columns, identity_columns) for *table* in the DW."""
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
    """Align DataFrame columns to the writable (non-identity) DW columns."""
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
        raise ValueError(
            f"No writable DW columns remain for {table} after schema alignment"
        )

    df = df.loc[:, kept_cols].copy()

    # Convert datetime.date objects to ISO string 'YYYY-MM-DD'
    # so pyodbc sends DATE not DATETIME to SQL Server DATE columns.
    import datetime as _dt
    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna()
            if not sample.empty and isinstance(sample.iloc[0], _dt.date) and not isinstance(sample.iloc[0], _dt.datetime):
                df[col] = df[col].apply(
                    lambda v: v.isoformat() if isinstance(v, _dt.date) else v
                )

    return df


def _sha256_row(row: pd.Series) -> bytearray:
    parts = []
    for value in row.tolist():
        if pd.isna(value):
            parts.append("<NULL>")
        else:
            parts.append(str(value))
    return bytearray(hashlib.sha256("|".join(parts).encode("utf-8")).digest())


def _detect_binary_cols(df: pd.DataFrame) -> list[str]:
    """Return column names in *df* that contain bytes/bytearray values."""
    found = []
    for col in df.columns:
        if col in _BINARY_COLS:
            sample = df[col].dropna()
            if not sample.empty and isinstance(sample.iloc[0], (bytes, bytearray)):
                found.append(col)
    return found


def _hex_encode_binary_cols(df: pd.DataFrame, binary_cols: list[str]) -> pd.DataFrame:
    """Return a copy of *df* with binary columns converted to hex strings.

    Uses uppercase hex without '0x' prefix so SQL Server
    CONVERT(VARBINARY(32), value, 2) can re-materialise them correctly.
    """
    df = df.copy()
    for col in binary_cols:
        df[col] = df[col].apply(
            lambda v: v.hex().upper() if isinstance(v, (bytes, bytearray)) else v
        )
    return df


def _bulk_insert(df: pd.DataFrame, table: str) -> None:
    if df.empty:
        logger.info(f"[LOAD] {table} – DataFrame vide, rien à insérer")
        return

    df = _prepare_for_load(df, table)
    df = df.drop(columns=["row_hash", "source_hash"], errors="ignore")

    if df.empty or len(df.columns) == 0:
        logger.info(f"[LOAD] {table} – DataFrame vide après préparation")
        return

    cols = list(df.columns)
    placeholders = ", ".join(["?" for _ in cols])
    col_names = ", ".join([f"[{c}]" for c in cols])
    sql = f"INSERT INTO [{table}] ({col_names}) VALUES ({placeholders})"

    def _to_python(v):
        if v is None:
            return None
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        if hasattr(v, "item"):
            return v.item()
        return v

    rows = [
        tuple(_to_python(v) for v in row)
        for row in df.itertuples(index=False, name=None)
    ]

    logger.info(
        f"[LOAD] {table} – Insertion bulk ({len(df)} lignes via fast_executemany)"
    )
    with DW_ENGINE.begin() as conn:
        raw_conn = conn.connection
        cursor = raw_conn.cursor()
        cursor.fast_executemany = True
        for i in range(0, len(rows), CHUNK_SIZE):
            cursor.executemany(sql, rows[i:i + CHUNK_SIZE])
        cursor.close()


def _merge_upsert(df: pd.DataFrame, table: str, key_col: str) -> None:
    """Perform a MERGE (upsert) on the DW table.

    *key_col* is the natural-key hash column used to match rows
    (e.g. ``CT_Num_code`` or ``source_hash``).

    FIX-BINARY: Binary columns (source_hash, row_hash) are hex-encoded
    before pandas.to_sql so the staging table gets a VARCHAR column rather
    than varchar(max) with raw byte representation. The MERGE ON clause and
    INSERT VALUES clause use CONVERT(VARBINARY(32), src.[col], 2) to
    re-materialise them as BINARY(32), matching the DW column type exactly.

    FIX-NEW: The IDENTITY PK is already stripped by _prepare_for_load()
    before this function builds its column list. There is therefore no need
    to guess the PK column name. The UPDATE SET clause simply excludes
    key_col; the identity column is already absent from df.columns.
    """
    if df.empty:
        logger.info(f"[LOAD] {table} – DataFrame vide, rien à MERGE")
        return

    # _prepare_for_load strips IDENTITY columns — df.columns has no PK after this
    df = _prepare_for_load(df, table)

    # Drop binary hash cols that are NOT the merge key (they go into _bulk_insert path)
    cols_to_drop = [c for c in ["row_hash", "source_hash"] if c != key_col]
    df = df.drop(columns=cols_to_drop, errors="ignore")

    if key_col not in df.columns:
        raise ValueError(
            f"MERGE key column '{key_col}' is missing from {table} load"
        )

    before_dedupe = len(df)
    df = df.drop_duplicates(subset=[key_col], keep="last")

    if len(df) != before_dedupe:
        logger.warning(
            f"[LOAD] {table} - dropped {before_dedupe - len(df)} "
            f"duplicate {key_col} rows"
        )

    # Bug 7: plain permanent staging table (no # prefix)
    temp_name = f"_etl_tmp_{table}"

    # Drop any leftover staging table from a previous failed run
    with DW_ENGINE.begin() as conn:
        conn.execute(text(_DROP_IF_EXISTS.format(name=temp_name)))

    # FIX-BINARY: detect binary columns still present in df (only key_col
    # could be source_hash at this point; row_hash was dropped above).
    binary_cols = _detect_binary_cols(df)

    # Write a hex-encoded copy to the staging table so pandas.to_sql creates
    # a proper VARCHAR column instead of varchar(max) with raw byte data.
    df_staging = _hex_encode_binary_cols(df, binary_cols) if binary_cols else df

    logger.debug(f"[LOAD] {table} – création table temporaire {temp_name}")
    # SQL Server limit: 2100 parameters per statement
    n_cols = len(df_staging.columns)
    sql_server_chunk = max(1, 2099 // n_cols)

    df_staging.to_sql(
        name=temp_name,
        con=DW_ENGINE,
        if_exists="replace",
        index=False,
        chunksize=sql_server_chunk,
        method="multi",
    )

    # Build MERGE clauses
    # UPDATE SET excludes key_col (FIX-NEW)
    update_cols = [c for c in df.columns if c != key_col]
    update_set = (
        ", ".join([f"target.[{c}]=src.[{c}]" for c in update_cols])
        if update_cols
        else f"target.[{key_col}]=target.[{key_col}]"
    )

    all_cols_sql = ", ".join([f"[{c}]" for c in df.columns])

    # FIX-BINARY: INSERT VALUES must convert hex strings back to VARBINARY
    src_vals = []
    for c in df.columns:
        if c in binary_cols:
            src_vals.append(f"CONVERT(VARBINARY(32), src.[{c}], 2)")
        else:
            src_vals.append(f"src.[{c}]")
    src_cols_sql = ", ".join(src_vals)

    # FIX-BINARY: ON clause — if key_col is binary, convert hex staging value
    if key_col in binary_cols:
        # Staging col is hex VARCHAR; target col is BINARY(32)
        on_clause = (
            f"target.[{key_col}] = CONVERT(VARBINARY(32), src.[{key_col}], 2)"
        )
    else:
        on_clause = f"target.[{key_col}] = src.[{key_col}]"

    merge_sql = f"""
        MERGE INTO [{table}] AS target
        USING [{temp_name}] AS src
        ON {on_clause}
        WHEN MATCHED THEN UPDATE SET
            {update_set}
        WHEN NOT MATCHED THEN INSERT ({all_cols_sql})
            VALUES ({src_cols_sql});
    """

    # Bug 6: DROP TABLE as a separate statement after MERGE
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

    - full  : DELETE all rows then bulk insert.
    - delta : MERGE based on *key_col* (the natural-key hash column).

    Bug 8: key_col must be supplied explicitly for delta mode.
    """
    if mode == "full":
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"DELETE FROM [{table}]"))
        _bulk_insert(df, table)
    else:
        if key_col is None:
            raise ValueError(
                f"key_col must be provided explicitly for delta load of '{table}'. "
                "Pass the natural-key hash column name (e.g. 'CT_Num_code')."
            )
        _merge_upsert(df, table, key_col)


def load_fact(
    df: pd.DataFrame,
    table: str,
    mode: Mode,
    key_col: Optional[str] = "source_hash",
) -> None:
    """Load a fact table.

    - full  : disable FK, DELETE all rows, bulk insert, re-enable FK.
    - delta : MERGE on source_hash (idempotent upsert) or append-only
    fallback if source_hash column is absent.
    """
    if mode == "full":
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"ALTER TABLE [{table}] NOCHECK CONSTRAINT ALL"))
            conn.execute(text(f"DELETE FROM [{table}]"))
        _bulk_insert(df, table)
        with DW_ENGINE.begin() as conn:
            conn.execute(
                text(f"ALTER TABLE [{table}] WITH CHECK CHECK CONSTRAINT ALL")
            )
    else:
        if key_col and key_col in df.columns:
            _merge_upsert(df, table, key_col)
        else:
            logger.warning(
                f"[LOAD] {table} - no {key_col} column, "
                "falling back to append-only fact load"
            )
            _bulk_insert(df, table)


if __name__ == "__main__":
    logger.info("module load.py exécuté en mode script – aucune action définie.")