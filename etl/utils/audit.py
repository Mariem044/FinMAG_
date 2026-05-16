from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, Optional

import os

from sqlalchemy import text

from etl.config import DW_ENGINE, ERROR_MSG_MAX_LEN
from etl.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = os.environ["ETL_AUDIT_TABLE"]
_STALE_RUNNING_HOURS = int(os.environ["ETL_STALE_RUNNING_HOURS"])


def _abort_stale_runs(conn) -> None:
    conn.execute(
        text(
            f"UPDATE {_TABLE} "
            "SET status = 'ABORTED', "
            "error_msg = COALESCE(error_msg, 'Aborted automatically: stale RUNNING run'), "
            "duration_seconds = DATEDIFF(SECOND, run_date, GETUTCDATE()) "
            "WHERE status = 'RUNNING' "
            "AND table_name = 'PIPELINE' "
            "AND run_date < DATEADD(HOUR, -:hours, GETUTCDATE())"
        ),
        {"hours": _STALE_RUNNING_HOURS},
    )


def acquire_lock() -> bool:
    try:
        with DW_ENGINE.begin() as conn:
            _abort_stale_runs(conn)
            result = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {_TABLE} "
                    "WHERE status = 'RUNNING' "
                    "AND table_name = 'PIPELINE'"
                )
            ).scalar()

        if result > 0:
            logger.error(
                "Another ETL run is already marked RUNNING in ETL_AUDIT. "
                "Aborting to avoid data corruption."
            )
            return False
        return True
    except Exception as exc:
        logger.warning(f"acquire_lock: audit table missing or unavailable - {exc}")
        return True


def release_lock(run_id: int) -> None:
    try:
        with DW_ENGINE.begin() as conn:
            conn.execute(
                text(
                    f"UPDATE {_TABLE} SET status='ABORTED' "
                    "WHERE run_id = :rid AND status = 'RUNNING'"
                ),
                {"rid": run_id},
            )
    except Exception as exc:
        logger.warning(f"release_lock: {exc}")


def get_last_run_info() -> tuple[Optional[datetime], str]:
    try:
        with DW_ENGINE.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT MAX(run_date) FROM {_TABLE} "
                    "WHERE status = 'SUCCESS' "
                    "AND table_name = 'PIPELINE'"
                )
            ).scalar()

        if result is None:
            logger.info("ETL_AUDIT is empty; FULL LOAD mode selected")
            return None, "full"

        logger.info(f"Last successful run: {result}; DELTA mode selected")
        return result, "delta"
    except Exception:
        logger.info("ETL_AUDIT is missing; FULL LOAD mode selected")
        return None, "full"


def start_run(mode: str) -> int:
    with DW_ENGINE.begin() as conn:
        result = conn.execute(
            text(
                "DECLARE @lock_result INT; "
                f"EXEC @lock_result = sp_getapplock "
                f"@Resource = '{_TABLE}_PIPELINE_LOCK', "
                "@LockMode = 'Exclusive', "
                "@LockOwner = 'Transaction', "
                "@LockTimeout = 0; "
                "IF @lock_result < 0 "
                "THROW 51001, 'Could not acquire ETL application lock', 1; "
                f"UPDATE {_TABLE} "
                "SET status = 'ABORTED', "
                "error_msg = COALESCE(error_msg, 'Aborted automatically: stale RUNNING run'), "
                "duration_seconds = DATEDIFF(SECOND, run_date, GETUTCDATE()) "
                "WHERE status = 'RUNNING' "
                "AND table_name = 'PIPELINE' "
                "AND run_date < DATEADD(HOUR, -:hours, GETUTCDATE()); "
                f"IF EXISTS (SELECT 1 FROM {_TABLE} WITH (UPDLOCK, HOLDLOCK) "
                "WHERE status = 'RUNNING' AND table_name = 'PIPELINE') "
                "THROW 51000, 'Another ETL run is already RUNNING', 1; "
                f"INSERT INTO {_TABLE} "
                "(run_date, mode, table_name, rows_inserted, rows_updated, "
                " duration_seconds, status, error_msg) "
                "OUTPUT INSERTED.run_id "
                "VALUES (GETUTCDATE(), :mode, 'PIPELINE', 0, 0, 0, 'RUNNING', NULL)"
            ),
            {"hours": _STALE_RUNNING_HOURS, "mode": mode},
        )
        run_id = result.scalar()

    logger.info(f"[AUDIT] Run started - run_id={run_id}, mode={mode}")
    return run_id


def log_table(
    run_id: int,
    table_name: str,
    rows_inserted: int,
    rows_updated: int,
    duration_seconds: float,
    status: str,
    error_msg: Optional[str] = None,
) -> None:
    try:
        with DW_ENGINE.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {_TABLE} "
                    "(run_date, mode, table_name, rows_inserted, rows_updated, "
                    " duration_seconds, status, error_msg) "
                    "VALUES (:dt, 'TABLE', :tbl, :ins, :upd, :dur, :sta, :err)"
                ),
                {
                    "dt": datetime.utcnow(),
                    "tbl": table_name,
                    "ins": rows_inserted,
                    "upd": rows_updated,
                    "dur": int(duration_seconds),
                    "sta": status,
                    "err": (error_msg or "")[:ERROR_MSG_MAX_LEN] if error_msg else None,
                },
            )
    except Exception as exc:
        logger.error(f"[AUDIT] Could not log table {table_name}: {exc}")


def end_run(run_id: int, status: str, error_msg: Optional[str] = None) -> None:
    try:
        with DW_ENGINE.begin() as conn:
            conn.execute(
                text(
                    f"UPDATE {_TABLE} "
                    "SET status = :sta, "
                    "error_msg = :err, "
                    "duration_seconds = DATEDIFF(SECOND, run_date, GETUTCDATE()) "
                    "WHERE run_id = :rid"
                ),
                {
                    "sta": status,
                    "err": (error_msg or "")[:ERROR_MSG_MAX_LEN] if error_msg else None,
                    "rid": run_id,
                },
            )
        logger.info(f"[AUDIT] Run {run_id} finished - status={status}")
    except Exception as exc:
        logger.error(f"[AUDIT] end_run: {exc}")


@contextmanager
def table_timer(
    run_id: int,
    table_name: str,
    rows_inserted: int = 0,
    rows_updated: int = 0,
) -> Generator[dict, None, None]:
    ctx: dict = {"rows_inserted": rows_inserted, "rows_updated": rows_updated}
    t0 = time.perf_counter()

    try:
        yield ctx
        duration = time.perf_counter() - t0
        log_table(
            run_id,
            table_name,
            ctx["rows_inserted"],
            ctx["rows_updated"],
            duration,
            "SUCCESS",
        )
        logger.info(
            f"[{table_name}] OK {ctx['rows_inserted']} ins / "
            f"{ctx['rows_updated']} upd - {duration:.1f}s"
        )
    except Exception as exc:
        duration = time.perf_counter() - t0
        log_table(run_id, table_name, 0, 0, duration, "ERROR", str(exc))
        logger.error(f"[{table_name}] ERROR: {exc}", exc_info=True)
        raise
