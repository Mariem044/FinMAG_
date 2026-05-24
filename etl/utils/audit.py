"""Audit des exécutions ETL : suivi de démarrage, fin et gestion des erreurs.

Ce module gère l'enregistrement simple des runs ETL dans la table
`ETL_AUDIT`. Il veille également à créer la table d'audit via
`etl.ddl` si elle est absente (évite la duplication du DDL ici).

Fonctions principales :
- `_ensure_audit_table_exists()` : vérifie/crée la table d'audit
- `start_run(mode)` : insère une ligne RUNNING et retourne `run_id`
- `end_run(run_id, status, error_msg)` : met à jour la ligne d'audit
"""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from etl.config import DW_ENGINE, ERROR_MSG_MAX_LEN, AUDIT_TABLE_NAME
from etl.utils.logger import get_logger
from etl import ddl

logger = get_logger(__name__)


def _ensure_audit_table_exists():
    """Vérifie que la table d'audit configurée existe, sinon elle la crée via `etl.ddl`."""
    try:
        if not ddl.table_exists(AUDIT_TABLE_NAME):
            # Créer toutes les tables si nécessaire (le DDL définit ETL_AUDIT ici)
            # Cela évite de dupliquer le SQL CREATE TABLE dans plusieurs fichiers.
            ddl.create_all_tables(drop_existing=False)
            logger.info("Table %s créée via etl.ddl.create_all_tables", AUDIT_TABLE_NAME)
    except SQLAlchemyError as exc:
        logger.error("Erreur lors de la vérification/création de la table %s: %s", AUDIT_TABLE_NAME, exc)


def start_run(mode):
    """Insère une ligne RUNNING dans la table d'audit et retourne son ID."""
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
    """Met à jour la ligne d'audit lorsque le pipeline se termine."""
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
