"""
ML Runner — orchestrate all predictive KPIs
============================================
Runs all 5 ML models in dependency order.
Can be called from the ETL pipeline, a cron job, or manually.

Usage:
    python -m ml.runner                  # run all
    python -m ml.runner --kpi 05 18      # run specific KPIs
    python -m ml.runner --skip 11        # skip XGBoost if not installed
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# Ordered list: (kpi_id, module_path, default_kwargs)
_KPI_REGISTRY = [
    ("05", "ml.kpi05_ca_forecast",        {"horizon": 12}),
    ("11", "ml.kpi11_tresorerie_forecast", {"horizon": 90}),
    ("17", "ml.kpi17_reappro_alert",       {"lead_time": 7}),
    ("18", "ml.kpi18_rupture_forecast",    {"horizon": 30}),
    ("22", "ml.kpi22_rfm_kmeans",          {"n_clusters": None}),
]


def run_all(
    only: Optional[list[str]] = None,
    skip: Optional[list[str]] = None,
) -> dict[str, str]:
    """
    Run all registered ML KPIs.

    Parameters
    ----------
    only : list of KPI IDs to run exclusively (e.g. ['05', '18'])
    skip : list of KPI IDs to skip

    Returns
    -------
    dict mapping kpi_id → 'OK' | 'SKIPPED' | 'ERROR: <msg>'
    """
    results: dict[str, str] = {}
    only = only or []
    skip = skip or []

    for kpi_id, module_path, kwargs in _KPI_REGISTRY:
        if only and kpi_id not in only:
            results[kpi_id] = "SKIPPED"
            continue

        if kpi_id in skip:
            results[kpi_id] = "SKIPPED"
            logger.info(f"[ML Runner] KPI-{kpi_id} SKIPPED (--skip)")
            continue

        logger.info(f"[ML Runner] ── Starting KPI-{kpi_id} ──")
        t0 = time.perf_counter()

        try:
            import importlib
            mod = importlib.import_module(module_path)
            mod.run(**{k: v for k, v in kwargs.items() if v is not None})
            elapsed = time.perf_counter() - t0
            results[kpi_id] = "OK"
            logger.info(f"[ML Runner] KPI-{kpi_id} OK ({elapsed:.1f}s)")

        except ImportError as exc:
            results[kpi_id] = f"ERROR: missing dependency — {exc}"
            logger.warning(f"[ML Runner] KPI-{kpi_id} skipped — {exc}")

        except Exception as exc:
            results[kpi_id] = f"ERROR: {exc}"
            logger.error(f"[ML Runner] KPI-{kpi_id} FAILED: {exc}\n{traceback.format_exc()}")

    # Summary
    logger.info("[ML Runner] ══ Summary ══")
    for kpi_id, status in results.items():
        logger.info(f"  KPI-{kpi_id}: {status}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ML Runner — all predictive KPIs")
    parser.add_argument("--kpi",  nargs="*", metavar="ID", help="Run only these KPI IDs (e.g. 05 18)")
    parser.add_argument("--skip", nargs="*", metavar="ID", help="Skip these KPI IDs")
    args = parser.parse_args()

    results = run_all(only=args.kpi, skip=args.skip)
    failed = [k for k, v in results.items() if v.startswith("ERROR")]
    if failed:
        print(f"\nFailed KPIs: {failed}")
        sys.exit(1)
    print("\nAll ML KPIs completed successfully.")