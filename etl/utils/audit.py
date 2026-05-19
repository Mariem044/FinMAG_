from datetime import datetime
from sqlalchemy import text
from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)


def get_last_run_info():
    """Retourne la date du dernier run réussi."""
    try:
        with DW_ENGINE.connect() as conn:
            result = conn.execute(
                text("SELECT MAX(run_date) FROM ETL_AUDIT WHERE status = 'SUCCESS' AND table_name = 'PIPELINE'")
            ).scalar()
        if result is None:
            logger.info("Aucun run précédent, chargement complet.")
            return None, "full"
        logger.info(f"Dernier run réussi : {result}")
        return result, "delta"
    except Exception:
        logger.info("Table audit introuvable, chargement complet.")
        return None, "full"


def start_run(mode):
    """Insère un enregistrement RUNNING dans la table audit et retourne son ID."""
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
                    "error_msg": error_msg[:500] if error_msg else None,
                    "run_id": run_id,
                },
            )
        logger.info(f"Pipeline terminé - run_id={run_id}, status={status}")
    except Exception as e:
        logger.error(f"Impossible de mettre à jour la table audit : {e}")