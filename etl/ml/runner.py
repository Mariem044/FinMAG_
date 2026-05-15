import threading

_ML_RUN_LOCK = threading.Lock()
_ML_LAST_ERROR = None


def run_all(only=None, skip=None):
    """Run all ML KPI modules. Returns dict of {kpi_id: status_string}."""
    from etl.ml import (
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
            mod.run()
            results[kpi_id] = "OK"
        except Exception as exc:
            results[kpi_id] = f"ERROR: {exc}"
    return results
