import hashlib
import pandas as pd
from sqlalchemy import text
from etl.config import DW_ENGINE, CHUNK_SIZE, ERROR_MSG_MAX_LEN
from etl.utils.logger import get_logger

logger = get_logger(__name__)


def _to_python(value):
    """Convertit un scalaire pandas/numpy en type Python natif (None si NA)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _sha256_row(row: "pd.Series") -> bytes:
    """Retourne un hash SHA-256 de 32 octets, stable et déterministe."""
    h = hashlib.sha256()
    for v in row:
        h.update(str(_to_python(v)).encode())
        h.update(b"\x00")
    return h.digest()


def get_table_columns(table):
    """Retourne la liste des colonnes qui existent dans une table de la base de données."""
    sql = "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = :table"
    with DW_ENGINE.connect() as conn:
        rows = conn.execute(text(sql), {"table": table}).fetchall()
    return [row[0] for row in rows]


def load_dimension(df, table):
    """Supprime toutes les lignes de la table puis insère les nouvelles données."""
    if df.empty:
        logger.info(f"[{table}] DataFrame vide, rien à charger.")
        return

    # Ne garder que les colonnes qui existent dans la table cible
    target_cols = get_table_columns(table)
    valid_cols = [c for c in df.columns if c in target_cols]
    df_clean = df[valid_cols].copy()

    with DW_ENGINE.begin() as conn:
        conn.execute(text(f"DELETE FROM [{table}]"))

    df_clean.to_sql(table, DW_ENGINE, if_exists="append", index=False, chunksize=CHUNK_SIZE)
    logger.info(f"[{table}] {len(df_clean)} lignes chargées.")


def load_fact(df, table):
    """Charge une table de faits (même stratégie que les dimensions)."""
    load_dimension(df, table)