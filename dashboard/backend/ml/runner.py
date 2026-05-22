import threading
import logging

from . import ca_forecast

logger = logging.getLogger("ml.runner")

# Le module runner orchestre l'exécution du ou des scripts ML.
# Il permet d'exécuter le calcul en tâche de fond et de conserver l'état.

_ML_RUN_LOCK = threading.Lock()
_ML_LAST_ERROR = None
_ML_IS_RUNNING = False


def is_running():
    # Indique si un thread ML est déjà en cours d'exécution.
    global _ML_IS_RUNNING
    return _ML_IS_RUNNING or _ML_RUN_LOCK.locked()

def get_last_error():
    global _ML_LAST_ERROR
    return _ML_LAST_ERROR


def run_all(only=None, skip=None):
    # Exécute les modules ML sélectionnés. on peut filtrer avec only ou skip.
    modules = {
        "05": ca_forecast,
    }

    if only:
        modules = {k: v for k, v in modules.items() if k in only}
    if skip:
        modules = {k: v for k, v in modules.items() if k not in skip}

    results = {}
    for kpi_id, mod in modules.items():
        try:
            logger.info(f"Running ML KPI-{kpi_id} CA forecast (ARIMA, SARIMA, PROPHET)...")
            mod.run()
            results[kpi_id] = "OK"
        except Exception as exc:
            logger.error(f"Error running ML KPI-{kpi_id}: {exc}")
            results[kpi_id] = f"ERROR: {exc}"
    return results


def run_all_background():
    # Lance la même exécution que run_all, mais dans un thread séparé.
    global _ML_IS_RUNNING, _ML_LAST_ERROR
    if not _ML_RUN_LOCK.acquire(blocking=False):
        return False

    _ML_IS_RUNNING = True
    _ML_LAST_ERROR = None

    def _run():
        global _ML_IS_RUNNING, _ML_LAST_ERROR
        try:
            logger.info("Starting ML KPI-05 pipeline in background...")
            run_all()
        except Exception as exc:
            _ML_LAST_ERROR = str(exc)
            logger.error(f"ML Pipeline run crashed: {exc}")
        finally:
            _ML_IS_RUNNING = False
            _ML_RUN_LOCK.release()
            logger.info("ML KPI-05 background training complete.")

    threading.Thread(target=_run, name="ML_Runner_Thread", daemon=True).start()
    return True

if __name__ == "__main__":
    # Permet d'exécuter le module en ligne de commande pour tester localement.
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    print("=== FinMAG ML pipeline execution ===")
    results = run_all()
    print("\n=== ML PIPELINE RUN SUMMARY ===")
    for k, v in results.items():
        print(f"KPI-{k}: {v}")
