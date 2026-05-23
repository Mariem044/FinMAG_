"""Audit des exécutions ETL : suivi de démarrage, fin et gestion des erreurs.

This module no longer embeds the ETL_AUDIT DDL; it delegates creation to
the central DDL helper when the audit table is missing.
"""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from etl.config import DW_ENGINE, ERROR_MSG_MAX_LEN, AUDIT_TABLE_NAME
from etl.utils.logger import get_logger
from etl import ddl

logger = get_logger(__name__)


def _ensure_audit_table_exists():
    """Ensure the configured audit table exists; create via `etl.ddl` if missing."""
    try:
        if not ddl.table_exists(AUDIT_TABLE_NAME):
            # Create all tables (DDL centrally defines ETL_AUDIT); this avoids
            # duplicated CREATE TABLE SQL in multiple places.
            ddl.create_all_tables(drop_existing=False)
            logger.info("Table %s créée via etl.ddl.create_all_tables", AUDIT_TABLE_NAME)
    except SQLAlchemyError as exc:
        logger.error("Erreur lors de la vérification/création de la table %s: %s", AUDIT_TABLE_NAME, exc)


def start_run(mode):
    """Insert a RUNNING row into the configured audit table and return its ID."""
    _ensure_audit_table_exists()
    sql = text(
        f"INSERT INTO [{AUDIT_TABLE_NAME}] (run_date, mode, table_name, rows_inserted, rows_updated, duration_seconds, status, error_msg) "
        "OUTPUT INSERTED.run_id "
        "VALUES (GETUTCDATE(), :mode, 'PIPELINE', 0, 0, 0, 'RUNNING', NULL)"
    )
    with DW_ENGINE.begin() as conn:
        result = conn.execute(sql, {"mode": mode})
        run_id = result.scalar()
    logger.info("Pipeline démarré - run_id=%s, mode=%s", run_id, mode)
    return run_id


def end_run(run_id, status, error_msg=None):
    """Update the configured audit row when the pipeline finishes."""
    try:
        sql = text(
            f"UPDATE [{AUDIT_TABLE_NAME}] "
            "SET status = :status, error_msg = :error_msg, "
            "duration_seconds = DATEDIFF(SECOND, run_date, GETUTCDATE()) "
            "WHERE run_id = :run_id"
        )
        with DW_ENGINE.begin() as conn:
            conn.execute(
                sql,
                {
                    "status": status,
                    "error_msg": error_msg[:ERROR_MSG_MAX_LEN] if error_msg else None,
                    "run_id": run_id,
                },
            )
        logger.info("Pipeline terminé - run_id=%s, status=%s", run_id, status)
    except SQLAlchemyError as exc:
        logger.error("Impossible de mettre à jour la table audit: %s", exc)
