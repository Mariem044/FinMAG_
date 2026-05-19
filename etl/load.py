import pandas as pd
from sqlalchemy import text
from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)

def get_table_columns(table: str) -> list[str]:
    sql = """
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = :table
    """
    with DW_ENGINE.connect() as conn:
        rows = conn.execute(text(sql), {"table": table}).fetchall()
    return [row[0] for row in rows]

def load_dimension(df: pd.DataFrame, table: str, mode: str = "full", key_col=None) -> None:
    if df.empty:
        logger.info(f"  [LOAD] {table} : DataFrame vide, rien a charger")
        return

    target_cols = get_table_columns(table)

    valid_cols = [c for c in df.columns if c in target_cols]
    df_clean = df[valid_cols].copy()

    with DW_ENGINE.begin() as conn:
        conn.execute(text(f"DELETE FROM [{table}]"))

    import sqlalchemy
    dtypes = {col: sqlalchemy.types.BINARY(32) for col in df_clean.columns if col.lower() in ("source_hash", "row_hash")}

    df_clean.to_sql(table, DW_ENGINE, if_exists="append", index=False, chunksize=5000, dtype=dtypes)
    logger.info(f"  [LOAD SUCCESS] {table} : {len(df_clean)} lignes chargees")

def load_fact(df: pd.DataFrame, table: str, mode: str = "full", key_col=None) -> None:
    load_dimension(df, table, mode, key_col)
