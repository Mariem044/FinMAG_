from sqlalchemy import text
from etl.config import DW_ENGINE, ERROR_MSG_MAX_LEN
from etl.utils.logger import get_logger

logger = get_logger(__name__)


def _ensure_audit_table_exists():
    sql_check = """
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = 'ETL_AUDIT' AND TABLE_TYPE = 'BASE TABLE'
    """
    sql_create = """
        CREATE TABLE ETL_AUDIT (
            run_id           INT IDENTITY(1,1) PRIMARY KEY,
            run_date         DATETIME NOT NULL DEFAULT GETUTCDATE(),
            mode             VARCHAR(10) NOT NULL,
            table_name       VARCHAR(100) NOT NULL,
            rows_inserted    INT NOT NULL DEFAULT 0,
            rows_updated     INT NOT NULL DEFAULT 0,
            duration_seconds INT NOT NULL DEFAULT 0,
            status           VARCHAR(20) NOT NULL,
            error_msg        NVARCHAR(500) NULL
        )
    """
    try:
        with DW_ENGINE.connect() as conn:
            exists = conn.execute(text(sql_check)).scalar()
        if not exists or exists == 0:
            with DW_ENGINE.begin() as conn:
                conn.execute(text(sql_create))
            logger.info("Table ETL_AUDIT créée avec succès.")
    except Exception as e:
        logger.error(f"Erreur lors de la vérification/création de la table ETL_AUDIT : {e}")


def start_run(mode):
    """Insère un enregistrement RUNNING dans la table audit et retourne son ID."""
    _ensure_audit_table_exists()
    with DW_ENGINE.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO ETL_AUDIT (run_date, mode, table_name, rows_inserted, rows_updated, duration_seconds, status, error_msg) "
                "OUTPUT INSERTED.run_id "
                "VALUES (GETUTCDATE(), :mode, 'PIPELINE', 0, 0, 0, 'RUNNING', NULL)"
            ),
            {"mode": mode},
        )
        run_id = result.scalar()
    logger.info(f"Pipeline démarré - run_id={run_id}, mode={mode}")
    return run_id


def end_run(run_id, status, error_msg=None):
    """Met à jour l'enregistrement audit à la fin du pipeline."""
    try:
        with DW_ENGINE.begin() as conn:
            conn.execute(
                text(
                    "UPDATE ETL_AUDIT "
                    "SET status = :status, error_msg = :error_msg, "
                    "duration_seconds = DATEDIFF(SECOND, run_date, GETUTCDATE()) "
                    "WHERE run_id = :run_id"
                ),
                {
                    "status": status,
                    "error_msg": error_msg[:ERROR_MSG_MAX_LEN] if error_msg else None,
                    "run_id": run_id,
                },
            )
        logger.info(f"Pipeline terminé - run_id={run_id}, status={status}")
    except Exception as e:
        logger.error(f"Impossible de mettre à jour la table audit : {e}")
