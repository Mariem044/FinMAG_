from __future__ import annotations

import hashlib
import datetime as _dt
from functools import lru_cache
from typing import Literal, Optional

import pandas as pd
from sqlalchemy import text

from etl.config import DW_ENGINE, CHUNK_SIZE, ERROR_MSG_MAX_LEN
from etl.utils.logger import get_logger

logger = get_logger(__name__)

Mode = Literal["full", "delta"]

_DROP_IF_EXISTS = (
    "IF OBJECT_ID(N'[dbo].[{name}]', N'U') IS NOT NULL DROP TABLE [{name}]"
)

_BINARY_COLS = {"source_hash", "row_hash"}


@lru_cache(maxsize=None)
def _target_columns(table: str) -> tuple[list[str], frozenset[str]]:
    """
    Query INFORMATION_SCHEMA once per table per process lifetime.
    The @lru_cache avoids repeated round-trips during a pipeline run —
    schema does not change while the ETL is executing.
    Returns (ordered_column_names, identity_column_set).
    """
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
    columns       = [row[0] for row in rows]
    identity_cols = frozenset(row[0] for row in rows if row[1] == 1)
    if not columns:
        raise ValueError(f"DW table '{table}' does not exist or has no columns")
    return columns, identity_cols


def _prepare_for_load(df: pd.DataFrame, table: str) -> pd.DataFrame:
    if df.empty:
        return df

    target_cols, identity_cols = _target_columns(table)
    writable_cols = [c for c in target_cols if c not in identity_cols]

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

    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna()
            if not sample.empty and isinstance(sample.iloc[0], _dt.date) and not isinstance(sample.iloc[0], _dt.datetime):
                df[col] = df[col].apply(
                    lambda v: v.isoformat() if isinstance(v, _dt.date) else v
                )

    return df


def _sha256_row(row: pd.Series) -> bytes:
    parts = ["<NULL>" if pd.isna(v) else str(v) for v in row.tolist()]
    return hashlib.sha256("|".join(parts).encode("utf-8")).digest()


def _detect_binary_cols(df: pd.DataFrame) -> list[str]:
    found = []
    for col in df.columns:
        if col in _BINARY_COLS:
            sample = df[col].dropna()
            if not sample.empty and isinstance(sample.iloc[0], (bytes, bytearray)):
                found.append(col)
    return found


def _hex_encode_binary_cols(df: pd.DataFrame, binary_cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in binary_cols:
        df[col] = df[col].apply(
            lambda v: v.hex().upper() if isinstance(v, (bytes, bytearray)) else v
        )
    return df


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


def _bulk_insert(df: pd.DataFrame, table: str) -> None:
    if df.empty:
        logger.info(f"[LOAD] {table} – empty DataFrame, nothing to insert")
        return

    df = _prepare_for_load(df, table)

    if df.empty or len(df.columns) == 0:
        logger.info(f"[LOAD] {table} – empty after schema alignment")
        return

    binary_cols = _detect_binary_cols(df)
    if binary_cols:
        df = _hex_encode_binary_cols(df, binary_cols)

    cols = list(df.columns)
    col_names = ", ".join([f"[{c}]" for c in cols])

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
        cursor.fast_executemany = not bool(binary_cols)
        for i in range(0, len(rows), CHUNK_SIZE):
            cursor.executemany(sql, rows[i:i + CHUNK_SIZE])
        cursor.close()


def _merge_upsert(df: pd.DataFrame, table: str, key_col: str) -> None:
    """
    Upsert df into [table] using a T-SQL MERGE statement.

    Strategy:
      1. Create temp table with the same schema as df.
      2. Bulk-insert all rows into the temp table.
      3. Add a non-clustered index on the merge key column (avoids table scan
         on the USING side of MERGE for large batches).
      4. Execute MERGE in a single transaction.
      5. Drop temp table in the finally block regardless of outcome.

    Both the staging fill and the MERGE run inside the same explicit
    SQLAlchemy transaction so a partial failure never leaves orphaned data.
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

    binary_cols = _detect_binary_cols(df)
    df_staging  = _hex_encode_binary_cols(df, binary_cols) if binary_cols else df
    _one_row    = df_staging.head(0)

    n_cols = len(df_staging.columns)
    sql_server_chunk = max(100, 2099 // max(n_cols, 1))

    # ── helper SQL fragments ──────────────────────────────────────────────────
    def _src_value(c: str) -> str:
        if c in binary_cols:
            return f"CONVERT(VARBINARY(32), src.[{c}], 2)"
        return f"src.[{c}]"

    update_cols  = [c for c in df.columns if c != key_col]
    update_set   = (
        ", ".join([f"target.[{c}]={_src_value(c)}" for c in update_cols])
        if update_cols
        else f"target.[{key_col}]=target.[{key_col}]"
    )
    all_cols_sql = ", ".join([f"[{c}]" for c in df.columns])
    src_cols_sql = ", ".join([_src_value(c) for c in df.columns])

    if key_col in binary_cols:
        on_clause = f"target.[{key_col}] = CONVERT(VARBINARY(32), src.[{key_col}], 2)"
    else:
        on_clause = f"target.[{key_col}] = src.[{key_col}]"

    cols      = list(df_staging.columns)
    col_names = ", ".join([f"[{c}]" for c in cols])
    insert_sql = (
        f"INSERT INTO [{temp_name}] ({col_names}) "
        f"VALUES ({', '.join('?' for _ in cols)})"
    )
    rows = [tuple(_to_python(v) for v in row)
            for row in df_staging.itertuples(index=False, name=None)]

    merge_sql = f"""
        MERGE INTO [{table}] AS target
        USING [{temp_name}] AS src
        ON {on_clause}
        WHEN MATCHED THEN UPDATE SET
            {update_set}
        WHEN NOT MATCHED THEN INSERT ({all_cols_sql})
            VALUES ({src_cols_sql});
    """
    drop_sql  = _DROP_IF_EXISTS.format(name=temp_name)
    index_sql = (
        f"CREATE NONCLUSTERED INDEX [IX_tmp_{table}_{key_col}] "
        f"ON [{temp_name}] ([{key_col}])"
    )

    # ── Drop any leftover temp table from a previous failed run ─────────────
    with DW_ENGINE.begin() as conn:
        conn.execute(text(drop_sql))

    # ── Create schema-only temp table (0 rows) ───────────────────────────────
    dtype_dict = {}
    if df[key_col].dtype == object or str(df[key_col].dtype).startswith("string"):
        from sqlalchemy.types import String
        dtype_dict[key_col] = String(255)

    _one_row.to_sql(
        name=temp_name,
        con=DW_ENGINE,
        if_exists="replace",
        index=False,
        chunksize=sql_server_chunk,
        method="multi",
        dtype=dtype_dict if dtype_dict else None
    )

    # ── Fill temp table + index + MERGE — all in one transaction ─────────────
    try:
        with DW_ENGINE.begin() as conn:
            raw_conn = conn.connection
            cursor   = raw_conn.cursor()
            cursor.fast_executemany = not bool(binary_cols)
            for i in range(0, len(rows), CHUNK_SIZE):
                cursor.executemany(insert_sql, rows[i:i + CHUNK_SIZE])
            cursor.close()

            # Index on the merge key prevents a full temp-table scan during MERGE
            conn.execute(text(index_sql))
            conn.execute(text(merge_sql))
    finally:
        with DW_ENGINE.begin() as conn:
            conn.execute(text(drop_sql))

    logger.info(f"[LOAD] {table} – MERGE upsert complete ({len(df)} rows)")


def load_dimension(
    df: pd.DataFrame,
    table: str,
    mode: Mode,
    key_col: Optional[str] = None,
) -> None:
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
