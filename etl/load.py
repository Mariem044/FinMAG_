# etl/load.py
"""Loading module for SIAD MAG Distribution ETL.
Provides bulk load for dimensions (full) and MERGE‑based upserts for delta.
All operations are wrapped in a transaction per table.
"""
import logging
from typing import Literal
import pandas as pd
from sqlalchemy import text
from config import DW_ENGINE, CHUNK_SIZE
from utils.logger import get_logger

logger = get_logger(__name__)

Mode = Literal["full", "delta"]


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
    The `key_col` is the surrogate INT code column (e.g. id_client_code).
    """
    if df.empty:
        logger.info(f"[LOAD] {table} – DataFrame vide, rien à MERGE")
        return
    # Crée une table temporaire
    temp_name = f"#tmp_{table}"
    logger.debug(f"[LOAD] {table} – création table temporaire {temp_name}")
    df.to_sql(
        name=temp_name,
        con=DW_ENGINE,
        if_exists="replace",
        index=False,
        chunksize=CHUNK_SIZE,
        method="multi",
    )
    merge_sql = f"""
        MERGE INTO {table} AS target
        USING {temp_name} AS src
        ON target.{key_col} = src.{key_col}
        WHEN MATCHED THEN UPDATE SET 
            {', '.join([f'target.{c}=src.{c}' for c in df.columns if c != key_col])}
        WHEN NOT MATCHED THEN INSERT ({', '.join(df.columns)})
            VALUES ({', '.join([f'src.{c}' for c in df.columns])});
        DROP TABLE {temp_name};
    """
    with DW_ENGINE.begin() as conn:
        conn.execute(text(merge_sql))
    logger.info(f"[LOAD] {table} – MERGE upsert complet ({len(df)} lignes) ")


def load_dimension(df: pd.DataFrame, table: str, mode: Mode) -> None:
    """Load a dimension table.
    - full : truncate puis bulk insert
    - delta: MERGE based on surrogate code column `<table>_code`
    """
    if mode == "full":
        # Truncate avant insertion
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table}"))
        _bulk_insert(df, table)
    else:
        key_col = f"id_{table.lower()}_code" if "_" not in table else f"{table.lower()}_code"
        _merge_upsert(df, table, key_col)


def load_fact(df: pd.DataFrame, table: str, mode: Mode) -> None:
    """Load a fact table.
    - full : désactive les FK, truncate, insert, réactive.
    - delta: uniquement INSERT (les faits sont immuables).
    """
    if mode == "full":
        # désactiver contraintes, tronquer puis insérer
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} NOCHECK CONSTRAINT ALL"))
            conn.execute(text(f"TRUNCATE TABLE {table}"))
        _bulk_insert(df, table)
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} WITH CHECK CHECK CONSTRAINT ALL"))
    else:
        _bulk_insert(df, table)  # seuls les nouveaux en delta

if __name__ == "__main__":
    import sys
    logger.info("module load.py exécuté en mode script – aucune action définie.")
