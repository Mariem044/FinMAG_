import os
import pandas as pd
from sqlalchemy import text
from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)

ALLOW_TABLE_DELETE = os.environ.get("ETL_ALLOW_TABLE_DELETE", "true").strip().lower() in ("1", "true", "yes")


def get_table_columns(table):
    """Retourne la liste des colonnes qui existent dans une table de la base de données."""
    sql = "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = :table"
    with DW_ENGINE.connect() as conn:
        rows = conn.execute(text(sql), {"table": table}).fetchall()
    return [row[0] for row in rows]


def load_dimension(df, table):
    """Supprime toutes les lignes de la table cible puis insère les données extraites."""
    if df.empty:
        logger.info(f"[{table}] DataFrame vide, rien à charger.")
        return

    # Ne garder que les colonnes qui existent dans la table cible
    target_cols = get_table_columns(table)
    valid_cols = [c for c in df.columns if c in target_cols]
    df_clean = df[valid_cols].copy()

    if ALLOW_TABLE_DELETE:
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"DELETE FROM [{table}]"))
    else:
        logger.warning(
            "[%s] ETL_ALLOW_TABLE_DELETE is disabled; %s rows will be appended instead of deleting existing data.",
            table,
            len(df_clean),
        )

    df_clean.to_sql(table, DW_ENGINE, if_exists="append", index=False)
    logger.info(f"[{table}] {len(df_clean)} lignes chargées.")


def load_fact(df, table):
    """Charge une table de faits en utilisant la même stratégie que pour les dimensions."""
    load_dimension(df, table)
