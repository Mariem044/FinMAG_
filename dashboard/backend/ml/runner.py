import threading
import logging

logger = logging.getLogger("ml.runner")

_ML_RUN_LOCK = threading.Lock()
_ML_LAST_ERROR = None
_ML_IS_RUNNING = False


def is_running():
    """Check if the ML runner is currently executing."""
    global _ML_IS_RUNNING
    return _ML_IS_RUNNING or _ML_RUN_LOCK.locked()


def get_last_error():
    """Get the error message from the last run if any failed."""
    global _ML_LAST_ERROR
    return _ML_LAST_ERROR


def run_all(only=None, skip=None):
    """Run all ML KPI modules synchronously."""
    from ml import (
        kpi05_ca_forecast,
        kpi11_tresorerie_forecast,
        kpi17_reappro_alert,
        kpi18_rupture_forecast,
        kpi22_rfm_kmeans,
    )

    modules = {
        "05": kpi05_ca_forecast,
        "11": kpi11_tresorerie_forecast,
        "17": kpi17_reappro_alert,
        "18": kpi18_rupture_forecast,
        "22": kpi22_rfm_kmeans,
    }

    if only:
        modules = {k: v for k, v in modules.items() if k in only}
    if skip:
        modules = {k: v for k, v in modules.items() if k not in skip}

    results = {}
    for kpi_id, mod in modules.items():
        try:
            logger.info(f"Running ML KPI-{kpi_id}...")
            mod.run()
            results[kpi_id] = "OK"
        except Exception as exc:
            logger.error(f"Error running ML KPI-{kpi_id}: {exc}")
            results[kpi_id] = f"ERROR: {exc}"
    return results


def run_all_background():
    """Acquire the lock and run all ML models in a background thread."""
    global _ML_IS_RUNNING, _ML_LAST_ERROR
    if not _ML_RUN_LOCK.acquire(blocking=False):
        return False

    _ML_IS_RUNNING = True
    _ML_LAST_ERROR = None

    def _run():
        global _ML_IS_RUNNING, _ML_LAST_ERROR
        try:
            logger.info("Starting Machine Learning pipelines in background...")
            run_all()
        except Exception as exc:
            _ML_LAST_ERROR = str(exc)
            logger.error(f"ML Pipeline run crashed: {exc}")
        finally:
            _ML_IS_RUNNING = False
            _ML_RUN_LOCK.release()
            logger.info("Machine Learning background training complete.")

    threading.Thread(target=_run, name="ML_Runner_Thread", daemon=True).start()
    return True
