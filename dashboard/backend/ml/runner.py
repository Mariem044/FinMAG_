"""
Module orchestrateur pour les modèles ML FinMAG.
Coordonne l'exécution de tous les modèles de forecast (ARIMA, SARIMA, PROPHET).
Gère l'exécution en arrière-plan avec verrous thread-safe pour éviter les conflits.
"""

import threading
import logging

from . import ca_forecast

logger = logging.getLogger("ml.runner")

# Verrou pour empêcher plusieurs exécutions ML simultanées
_ML_RUN_LOCK = threading.Lock()
# Stocke le dernier message d'erreur du pipeline ML
_ML_LAST_ERROR = None
# Indique si le pipeline ML est actuellement en cours d'exécution
_ML_IS_RUNNING = False

def is_running():
    """
    Vérifie si le pipeline ML est actuellement en cours d'exécution.
    
    Retourne True si :
    - _ML_IS_RUNNING = True (pipeline en cours)
    - Le verrou est bloqué (thread en cours d'exécution)
    
    Returns:
        bool: True si le ML est en cours, False sinon
    """
    global _ML_IS_RUNNING
    return _ML_IS_RUNNING or _ML_RUN_LOCK.locked()

def get_last_error():
    """
    Récupère le dernier message d'erreur du pipeline ML.
    Utilisé pour afficher les erreurs dans le frontend.
    
    Returns:
        str or None: Message d'erreur, ou None si pas d'erreur
    """
    global _ML_LAST_ERROR
    return _ML_LAST_ERROR

def run_all(only=None, skip=None):
    """
    Exécute tous les modèles ML en synchrone (bloquant).
    
    Modules ML disponibles:
    - KPI-05: ca_forecast (prévisions du Chiffre d'Affaires avec ARIMA, SARIMA, PROPHET)
    
    Args:
        only (list, optional): Si fourni, exécute UNIQUEMENT ces KPI (ex: ["05"])
        skip (list, optional): Si fourni, IGNORE ces KPI (ex: ["05"] pour sauter KPI-05)
    
    Returns:
        dict: Résultat pour chaque KPI
              {"05": "OK"} ou {"05": "ERROR: message"}
    """
    # Dictionnaire des modules ML disponibles
    modules = {
        "05": ca_forecast,  # KPI-05 = Prévisions CA (Chiffre d'Affaires)
    }

    # Filtrer selon les paramètres 'only' et 'skip'
    if only:
        modules = {k: v for k, v in modules.items() if k in only}
    if skip:
        modules = {k: v for k, v in modules.items() if k not in skip}

    # Exécuter chaque modèle et stocker les résultats
    results = {}
    for kpi_id, mod in modules.items():
        try:
            logger.info(f"Running ML KPI-{kpi_id} CA forecast (ARIMA, SARIMA, PROPHET)...")
            mod.run()  # Lance l'entraînement des 3 modèles (ARIMA, SARIMA, PROPHET)
            results[kpi_id] = "OK"
        except Exception as exc:
            logger.error(f"Error running ML KPI-{kpi_id}: {exc}")
            results[kpi_id] = f"ERROR: {exc}"
    return results

def run_all_background():
    """
    Lance le pipeline ML en arrière-plan (mode asynchrone).
    Utilise un verrou pour éviter deux exécutions simultanées.
    
    Le pipeline s'exécute dans un thread daemon séparé.
    
    Returns:
        bool: True si le pipeline a démarré avec succès
              False si un pipeline est déjà en cours d'exécution
    """
    global _ML_IS_RUNNING, _ML_LAST_ERROR
    
    # Essayer d'acquérir le verrou sans bloquer
    # Si on ne peut pas le prendre = un pipeline est déjà en cours
    if not _ML_RUN_LOCK.acquire(blocking=False):
        return False

    _ML_IS_RUNNING = True
    _ML_LAST_ERROR = None

    def _run():
        """Fonction interne qui exécute le pipeline dans le thread."""
        global _ML_IS_RUNNING, _ML_LAST_ERROR
        try:
            logger.info("Starting ML KPI-05 pipeline in background...")
            run_all()  # Exécuter tous les modèles
        except Exception as exc:
            _ML_LAST_ERROR = str(exc)
            logger.error(f"ML Pipeline run crashed: {exc}")
        finally:
            # Nettoyer l'état même en cas d'erreur
            _ML_IS_RUNNING = False
            _ML_RUN_LOCK.release()  # Libérer le verrou
            logger.info("ML KPI-05 background training complete.")

    # Démarrer le pipeline dans un thread daemon (s'arrête quand l'app s'arrête)
    threading.Thread(target=_run, name="ML_Runner_Thread", daemon=True).start()
    return True

if __name__ == "__main__":
    """
    Point d'entrée pour exécuter le pipeline ML manuellement depuis la ligne de commande.
    Exemple: python -m dashboard.backend.ml.runner
    """
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
