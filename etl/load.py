"""
load.py — SIAD MAG Distribution ETL
Bulk load for dimensions (full) and MERGE-based upserts for delta.

FIXES vs previous version
──────────────────────────────────────────────────────────────────────────
FIX-HASH-BULK : _bulk_insert() no longer drops source_hash before
                inserting. On full loads, source_hash is now written to
                the table so the unique index UX_*_source_hash provides
                real dedup protection. row_hash is still kept (used for
                SCD row comparison). Binary columns are hex-encoded via
                the same path as _merge_upsert().
FIX-BINARY    : _merge_upsert() hex-encodes BINARY cols so SQL Server
                receives VARCHAR that it re-casts via CONVERT(VARBINARY).
FIX-PK        : _merge_upsert() no longer tries to guess the PK column
                name. _prepare_for_load() already strips IDENTITY columns
                so the PK is absent from df.columns by the time the MERGE
                is built.
"""
from __future__ import annotations

import hashlib
import datetime as _dt
from typing import Literal, Optional

import pandas as pd
from sqlalchemy import text

from etl.config import DW_ENGINE, CHUNK_SIZE
from etl.utils.logger import get_logger

logger = get_logger(__name__)

Mode = Literal["full", "delta"]

_DROP_IF_EXISTS = (
    "IF OBJECT_ID(N'[dbo].[{name}]', N'U') IS NOT NULL DROP TABLE [{name}]"
)

# Columns that carry raw bytes and need hex-encoding for pandas.to_sql
_BINARY_COLS = {"source_hash", "row_hash"}


# ── Schema helpers ────────────────────────────────────────────────────────────

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
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = :table
        ORDER BY ORDINAL_POSITION
    """
    with DW_ENGINE.connect() as conn:
        rows = conn.execute(text(sql), {"table": table}).fetchall()
    columns      = [row[0] for row in rows]
    identity_cols = {row[0] for row in rows if row[1] == 1}
    if not columns:
        raise ValueError(f"DW table '{table}' does not exist or has no columns")
    return columns, identity_cols


def _prepare_for_load(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Align DataFrame columns to the writable (non-identity) DW columns.

    Also auto-computes row_hash if the table has the column and the df does not.
    Converts date objects to ISO strings for pyodbc compatibility.
    """
    if df.empty:
        return df

    target_cols, identity_cols = _target_columns(table)
    writable_cols = [c for c in target_cols if c not in identity_cols]

    # Auto-compute row_hash if needed
    if "row_hash" in writable_cols and "row_hash" not in df.columns:
        hash_cols = [c for c in writable_cols if c != "row_hash" and c in df.columns]
        df = df.copy()
        df["row_hash"] = df[hash_cols].apply(_sha256_row, axis=1)

    kept_cols    = [c for c in writable_cols if c in df.columns]
    dropped_cols = [c for c in df.columns if c not in kept_cols]

    if dropped_cols:
        logger.debug(f"[LOAD] {table} - dropping non-DW cols: {', '.join(dropped_cols)}")

    if not kept_cols:
        raise ValueError(f"No writable DW columns remain for {table} after schema alignment")

    df = df.loc[:, kept_cols].copy()

    # Convert date objects → ISO string so pyodbc sends DATE not DATETIME
    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna()
            if not sample.empty and isinstance(sample.iloc[0], _dt.date) and not isinstance(sample.iloc[0], _dt.datetime):
                df[col] = df[col].apply(
                    lambda v: v.isoformat() if isinstance(v, _dt.date) else v
                )

    return df


def _sha256_row(row: pd.Series) -> bytearray:
    parts = ["<NULL>" if pd.isna(v) else str(v) for v in row.tolist()]
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
    """Hex-encode binary columns for pandas.to_sql (no 0x prefix, uppercase)."""
    df = df.copy()
    for col in binary_cols:
        df[col] = df[col].apply(
            lambda v: v.hex().upper() if isinstance(v, (bytes, bytearray)) else v
        )
    return df


def _to_python(v):
    """Convert a DataFrame cell to a plain Python scalar for executemany."""
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


# ── Insert strategies ─────────────────────────────────────────────────────────

def _bulk_insert(df: pd.DataFrame, table: str) -> None:
    """Fast bulk insert via pyodbc executemany.

    FIX-HASH-BULK: source_hash and row_hash are NO LONGER dropped before
    insert. They are hex-encoded and written to the table so the unique
    indexes UX_*_source_hash work on full loads too.
    """
    if df.empty:
        logger.info(f"[LOAD] {table} – empty DataFrame, nothing to insert")
        return

    df = _prepare_for_load(df, table)

    if df.empty or len(df.columns) == 0:
        logger.info(f"[LOAD] {table} – empty after schema alignment")
        return

    # Hex-encode any binary columns that survived _prepare_for_load
    binary_cols = _detect_binary_cols(df)
    if binary_cols:
        df = _hex_encode_binary_cols(df, binary_cols)

    cols = list(df.columns)
    col_names    = ", ".join([f"[{c}]" for c in cols])
    placeholders = ", ".join(["?" for _ in cols])

    # For binary cols the placeholder becomes CONVERT(VARBINARY(32), ?, 2)
    value_exprs = []
    for c in cols:
        if c in binary_cols:
            value_exprs.append("CONVERT(VARBINARY(32), ?, 2)")
        else:
            value_exprs.append("?")
    values_sql = ", ".join(value_exprs)

    sql = f"INSERT INTO [{table}] ({col_names}) VALUES ({values_sql})"

    rows = [
        tuple(_to_python(v) for v in row)
        for row in df.itertuples(index=False, name=None)
    ]

    logger.info(f"[LOAD] {table} – bulk insert {len(df)} rows")
    with DW_ENGINE.begin() as conn:
        raw_conn = conn.connection
        cursor = raw_conn.cursor()
        cursor.fast_executemany = True
        for i in range(0, len(rows), CHUNK_SIZE):
            cursor.executemany(sql, rows[i:i + CHUNK_SIZE])
        cursor.close()


def _merge_upsert(df: pd.DataFrame, table: str, key_col: str) -> None:
    """MERGE (upsert) on the DW table keyed by *key_col*.

    Binary columns are hex-encoded for staging; the MERGE ON clause and
    INSERT VALUES use CONVERT(VARBINARY(32), src.[col], 2) to re-materialise
    them as BINARY(32).

    IDENTITY PK is already stripped by _prepare_for_load() so we never need
    to guess the PK column name — it simply isn't in df.columns.
    """
    if df.empty:
        logger.info(f"[LOAD] {table} – empty DataFrame, nothing to MERGE")
        return

    df = _prepare_for_load(df, table)

    if key_col not in df.columns:
        raise ValueError(f"MERGE key column '{key_col}' missing from {table} load")

    before = len(df)
    df = df.drop_duplicates(subset=[key_col], keep="last")
    if len(df) != before:
        logger.warning(f"[LOAD] {table} - dropped {before - len(df)} duplicate {key_col} rows")

    temp_name = f"_etl_tmp_{table}"

    with DW_ENGINE.begin() as conn:
        conn.execute(text(_DROP_IF_EXISTS.format(name=temp_name)))

    binary_cols = _detect_binary_cols(df)
    df_staging  = _hex_encode_binary_cols(df, binary_cols) if binary_cols else df

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

    update_cols = [c for c in df.columns if c != key_col]
    update_set  = (
        ", ".join([f"target.[{c}]=src.[{c}]" for c in update_cols])
        if update_cols
        else f"target.[{key_col}]=target.[{key_col}]"
    )

    all_cols_sql = ", ".join([f"[{c}]" for c in df.columns])

    src_vals = []
    for c in df.columns:
        if c in binary_cols:
            src_vals.append(f"CONVERT(VARBINARY(32), src.[{c}], 2)")
        else:
            src_vals.append(f"src.[{c}]")
    src_cols_sql = ", ".join(src_vals)

    if key_col in binary_cols:
        on_clause = f"target.[{key_col}] = CONVERT(VARBINARY(32), src.[{key_col}], 2)"
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

    drop_sql = _DROP_IF_EXISTS.format(name=temp_name)

    with DW_ENGINE.begin() as conn:
        conn.execute(text(merge_sql))
        conn.execute(text(drop_sql))

    logger.info(f"[LOAD] {table} – MERGE upsert complete ({len(df)} rows)")


# ── Public API ────────────────────────────────────────────────────────────────

def load_dimension(
    df: pd.DataFrame,
    table: str,
    mode: Mode,
    key_col: Optional[str] = None,
) -> None:
    """Load a dimension table.

    full  → DELETE all rows, then bulk insert.
    delta → MERGE on *key_col* (must be supplied explicitly).
    """
    if mode == "full":
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"DELETE FROM [{table}]"))
        _bulk_insert(df, table)
    else:
        if key_col is None:
            raise ValueError(
                f"key_col must be provided for delta load of '{table}'."
            )
        _merge_upsert(df, table, key_col)


def load_fact(
    df: pd.DataFrame,
    table: str,
    mode: Mode,
    key_col: Optional[str] = "source_hash",
) -> None:
    """Load a fact table.

    full  → disable FK, DELETE all rows, bulk insert (source_hash included),
            re-enable FK.
    delta → MERGE on source_hash (idempotent) or append if column absent.
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
                f"[LOAD] {table} - no {key_col} column; falling back to append-only"
            )
            _bulk_insert(df, table)