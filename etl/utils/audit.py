"""
utils/audit.py — SIAD MAG Distribution ETL
Gestion de la table ETL_AUDIT : lock de run, logging métrique, lecture last_run_date.
"""
from __future__ import annotations

import socket
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, Optional

import pandas as pd
from sqlalchemy import text

from config import DW_ENGINE
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Constantes ───────────────────────────────────────────────────────────────
_TABLE = "ETL_AUDIT"
_HOSTNAME = socket.gethostname()


# ── Lock de run concurrent ───────────────────────────────────────────────────
def acquire_lock() -> bool:
    """
    Vérifie qu'aucun run ETL n'est en cours (status='RUNNING').
    Retourne True si le verrou est acquis, False sinon.
    Protection contre les runs concurrents.
    """
    try:
        with DW_ENGINE.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {_TABLE} "
                    "WHERE status = 'RUNNING'"
                )
            ).scalar()
        if result > 0:
            logger.error(
                "ETL déjà en cours (status=RUNNING dans ETL_AUDIT). "
                "Abandon pour éviter la corruption des données."
            )
            return False
        return True
    except Exception as exc:
        # ETL_AUDIT n'existe pas encore (premier run avant DDL)
        logger.warning(f"acquire_lock: table absente ou erreur — {exc}")
        return True


def release_lock(run_id: int) -> None:
    """Passe status='RUNNING' → 'RELEASED' si le pipeline plante avant la fin."""
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


# ── Lecture last_run_date ─────────────────────────────────────────────────────
def get_last_run_info() -> tuple[Optional[datetime], str]:
    """
    Retourne (last_run_date, mode).
    - Si ETL_AUDIT vide ou absente → (None, 'full')
    - Sinon → (MAX(run_date) des runs SUCCESS, 'delta')
    """
    try:
        with DW_ENGINE.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT MAX(run_date) FROM {_TABLE} "
                    "WHERE status = 'SUCCESS'"
                )
            ).scalar()
        if result is None:
            logger.info("ETL_AUDIT vide → mode FULL LOAD détecté")
            return None, "full"
        logger.info(f"Dernier run SUCCESS : {result} → mode DELTA détecté")
        return result, "delta"
    except Exception:
        logger.info("ETL_AUDIT absente → mode FULL LOAD (premier run)")
        return None, "full"


# ── Enregistrement d'un run ───────────────────────────────────────────────────
def start_run(mode: str) -> int:
    """
    Insère un enregistrement RUNNING dans ETL_AUDIT.
    Retourne le run_id généré.
    """
    with DW_ENGINE.begin() as conn:
        result = conn.execute(
            text(
                f"INSERT INTO {_TABLE} "
                "(run_date, mode, table_name, rows_inserted, rows_updated, "
                " duration_seconds, status, error_msg) "
                "OUTPUT INSERTED.run_id "
                "VALUES (:dt, :mode, 'PIPELINE', 0, 0, 0, 'RUNNING', NULL)"
            ),
            {"dt": datetime.utcnow(), "mode": mode},
        )
        run_id = result.scalar()
    logger.info(f"[AUDIT] Run démarré — run_id={run_id}, mode={mode}")
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
    """Insère une ligne d'audit par table traitée."""
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
                    "dt":  datetime.utcnow(),
                    "tbl": table_name,
                    "ins": rows_inserted,
                    "upd": rows_updated,
                    "dur": int(duration_seconds),
                    "sta": status,
                    "err": (error_msg or "")[:500] if error_msg else None,
                },
            )
    except Exception as exc:
        logger.error(f"[AUDIT] Impossible de logger {table_name}: {exc}")


def end_run(run_id: int, status: str, error_msg: Optional[str] = None) -> None:
    """Met à jour le run principal (status, duration)."""
    try:
        with DW_ENGINE.begin() as conn:
            conn.execute(
                text(
                    f"UPDATE {_TABLE} "
                    "SET status = :sta, error_msg = :err "
                    "WHERE run_id = :rid"
                ),
                {
                    "sta": status,
                    "err": (error_msg or "")[:500] if error_msg else None,
                    "rid": run_id,
                },
            )
        logger.info(f"[AUDIT] Run {run_id} terminé → status={status}")
    except Exception as exc:
        logger.error(f"[AUDIT] end_run: {exc}")


# ── Context manager pratique ──────────────────────────────────────────────────
@contextmanager
def table_timer(
    run_id: int,
    table_name: str,
    rows_inserted: int = 0,
    rows_updated: int = 0,
) -> Generator[dict, None, None]:
    """
    Chronomètre + audit automatique pour chaque table.

    Usage :
        with table_timer(run_id, "DIM_CLIENT") as ctx:
            ... charger la table ...
            ctx["rows_inserted"] = n
    """
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
            f"[{table_name}] ✓ {ctx['rows_inserted']} ins / "
            f"{ctx['rows_updated']} upd — {duration:.1f}s"
        )
    except Exception as exc:
        duration = time.perf_counter() - t0
        log_table(run_id, table_name, 0, 0, duration, "ERROR", str(exc))
        logger.error(f"[{table_name}] ✗ ERREUR : {exc}", exc_info=True)
        # Pas de re-raise → rollback par table, pipeline continue
