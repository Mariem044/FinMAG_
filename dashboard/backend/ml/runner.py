import threading
import logging

logger = logging.getLogger("ml.runner")

_ML_RUN_LOCK = threading.Lock()
_ML_LAST_ERROR = None
_ML_IS_RUNNING = False

def is_running():
    global _ML_IS_RUNNING
    return _ML_IS_RUNNING or _ML_RUN_LOCK.locked()

def get_last_error():
    global _ML_LAST_ERROR
    return _ML_LAST_ERROR

def run_all(only=None, skip=None):
    modules = {}

    if only:
        modules = {k: v for k, v in modules.items() if k in only}
    if skip:
        modules = {k: v for k, v in modules.items() if k not in skip}

    results = {}
    for kpi_id, mod in modules.items():
        try:
            logger.info(f"Running ML KPI-{kpi_id} (ARIMA, SARIMA, PROPHET)...")
            mod.run()
            results[kpi_id] = "OK"
        except Exception as exc:
            logger.error(f"Error running ML KPI-{kpi_id}: {exc}")
            results[kpi_id] = f"ERROR: {exc}"
    return results

def run_all_background():
    global _ML_IS_RUNNING, _ML_LAST_ERROR
    if not _ML_RUN_LOCK.acquire(blocking=False):
        return False

    _ML_IS_RUNNING = True
    _ML_LAST_ERROR = None

    def _run():
        global _ML_IS_RUNNING, _ML_LAST_ERROR
        try:
            logger.info("Starting Statistical pipelines in background...")
            run_all()
        except Exception as exc:
            _ML_LAST_ERROR = str(exc)
            logger.error(f"ML Pipeline run crashed: {exc}")
        finally:
            _ML_IS_RUNNING = False
            _ML_RUN_LOCK.release()
            logger.info("Statistical background training complete.")

    threading.Thread(target=_run, name="ML_Runner_Thread", daemon=True).start()
    return True

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    print("=== FinMAG Advanced Analytics pipeline execution ===")
    results = run_all()
    print("\n=== ML PIPELINE RUN SUMMARY ===")
    for k, v in results.items():
        print(f"KPI-{k}: {v}")
