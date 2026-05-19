import sys
import os
import json
import logging
import re
import threading
import unicodedata
from typing import List, Optional, Union
from pathlib import Path
from datetime import datetime

# Add potential backend paths to sys.path to resolve 'ml' and 'etl' module imports
current_dir = os.path.abspath(os.path.dirname(__file__))
possible_paths = [
    os.path.join(current_dir, "..", "..", ".."),                  # FINMAG root to import 'etl'
    os.path.join(current_dir, "..", "..", "dashboard", "backend"), # from etl/api
    os.path.join(current_dir, ".."),                              # from dashboard/backend/api
    os.path.join(os.getcwd(), "dashboard", "backend"),             # from root
]
for path in possible_paths:
    abs_path = os.path.abspath(path)
    if os.path.exists(abs_path) and abs_path not in sys.path:
        sys.path.insert(0, abs_path)

from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from etl.config import DW_ENGINE, MAG_ENGINE, SEUIL_TENSION_STOCK, AUDIT_TABLE_NAME
from etl import pipeline

app = FastAPI(title="FinMAG API") 
_ETL_RUN_LOCK = threading.Lock()
_ETL_LAST_ERROR = None
_startup_logger = logging.getLogger("api.startup")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MONTHS = ["Jan", "Fev", "Mar", "Avr", "Mai", "Jun", "Jul", "Aou", "Sep", "Oct", "Nov", "Dec"]

def _rows(sql, params=None):
    with DW_ENGINE.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchall()


def _row(sql, params=None):
    with DW_ENGINE.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchone()


def _num(value, default=0.0):
    return float(value) if value is not None else default


def _int(value, default=0):
    return int(value) if value is not None else default


def _date_str(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")


def _clean_filter(val: Optional[Union[str, int]]):
    if not val:
        return None
    cleaned = str(val).strip().strip('"').strip("'")
    if cleaned.lower() in ("tous", "toutes", "toutes regions", "null", "undefined", ""):
        return None
    return cleaned


def _parse_month(month_str: Optional[str]) -> int:
    val = _clean_filter(month_str)
    if not val:
        return 0
    months_map = {
        "jan": 1, "janvier": 1,
        "fev": 2, "fevrier": 2,
        "mar": 3, "mars": 3,
        "avr": 4, "avril": 4,
        "mai": 5,
        "jun": 6, "juin": 6,
        "jul": 7, "juillet": 7,
        "aou": 8, "aout": 8,
        "sep": 9, "septembre": 9,
        "oct": 10, "octobre": 10,
        "nov": 11, "novembre": 11,
        "dec": 12, "decembre": 12
    }
    return months_map.get(val.lower()[:3], 0)


def _build_dynamic_filters(
    year=None, quarter=None, month=None, region=None, famille=None,
    segment=None, depot=None, banque=None, modeBanque=None, modePaiement=None,
    source=None, horizonPrev=None, statutArticle=None,
    aliases=None
) -> tuple[str, dict]:
    if aliases is None:
        aliases = {"date": "d", "client": "c", "famille": "fa", "segment": "s", "depot": "dp", "banque": "b", "article": "a"}
    
    clauses = []
    params = {}
    
    c_year = _clean_filter(year)
    if c_year and aliases.get("date"):
        try:
            y = int(c_year)
            clauses.append(f"AND {aliases['date']}.annee = :p_year")
            params["p_year"] = y
        except ValueError:
            pass

    c_quarter = _clean_filter(quarter)
    if c_quarter and aliases.get("date"):
        q = 0
        if c_quarter.upper() == "Q1": q = 1
        elif c_quarter.upper() == "Q2": q = 2
        elif c_quarter.upper() == "Q3": q = 3
        elif c_quarter.upper() == "Q4": q = 4
        if q > 0:
            clauses.append(f"AND {aliases['date']}.trimestre = :p_quarter")
            params["p_quarter"] = q

    m = _parse_month(month)
    if m > 0 and aliases.get("date"):
        clauses.append(f"AND {aliases['date']}.mois = :p_month")
        params["p_month"] = m

    c_region = _clean_filter(region)
    if c_region and aliases.get("client"):
        clauses.append(f"AND {aliases['client']}.gouvernorat = :p_region")
        params["p_region"] = c_region

    c_famille = _clean_filter(famille)
    if c_famille and aliases.get("famille"):
        clauses.append(f"AND {aliases['famille']}.FA_Intitule LIKE :p_famille")
        params["p_famille"] = f"%{c_famille}%"

    c_segment = _clean_filter(segment)
    if c_segment and aliases.get("segment"):
        clauses.append(f"AND {aliases['segment']}.libelle_segment = :p_segment")
        params["p_segment"] = c_segment

    c_depot = _clean_filter(depot)
    if c_depot:
        if "central" in c_depot.lower():
            if aliases.get("depot"):
                clauses.append(f"AND {aliases['depot']}.DE_Principal = 1")
        else:
            depot_region = c_depot.replace("Depot ", "").replace("Dépôt ", "").split(" ")[0]
            if aliases.get("client") and depot_region != "Tous":
                clauses.append(f"AND {aliases['client']}.gouvernorat = :p_depot_region")
                params["p_depot_region"] = depot_region

    c_statut = _clean_filter(statutArticle)
    if c_statut and aliases.get("article"):
        if "actif" in c_statut.lower():
            clauses.append(f"AND {aliases['article']}.AR_Sommeil = 0")
        elif "sommeil" in c_statut.lower():
            clauses.append(f"AND {aliases['article']}.AR_Sommeil = 1")
        
    return " ".join(clauses), params

def _run_etl_background():
    global _ETL_LAST_ERROR
    try:
        pipeline.run_pipeline()
        _ETL_LAST_ERROR = None

        try:
            from ml.runner import run_all as run_ml  # type: ignore
            run_ml()
        except Exception as ml_exc:
            logger = logging.getLogger("api.etl")
            logger.error(f"Failed to auto-run ML after ETL: {ml_exc}")
    except Exception as exc:
        _ETL_LAST_ERROR = str(exc)
    finally:
        _ETL_RUN_LOCK.release()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/dashboard/filters")
def get_dashboard_filters():
    try:
        
        with MAG_ENGINE.connect() as conn:
            depots = [r.DE_Intitule.strip() for r in conn.execute(text("SELECT DISTINCT DE_Intitule FROM F_DEPOT WHERE DE_Intitule IS NOT NULL ORDER BY DE_Intitule")).fetchall()]
        if not depots:
            depots = ["Tous"]
        else:
            depots = ["Tous"] + depots


        segments = [r.libelle_segment.strip() for r in _rows("SELECT DISTINCT libelle_segment FROM DIM_SEGMENT WHERE libelle_segment IS NOT NULL ORDER BY libelle_segment")]
        if not segments:
            segments = ["Tous"]
        else:
            segments = ["Tous"] + segments

        
        familles = [r.FA_Intitule.strip() for r in _rows("SELECT DISTINCT FA_Intitule FROM DIM_ARTICLE WHERE FA_Intitule IS NOT NULL AND FA_Intitule <> '' ORDER BY FA_Intitule")]
        if not familles:
            familles = ["Toutes"]
        else:
            familles = ["Toutes"] + familles

        
        years = [int(r.annee) for r in _rows("SELECT DISTINCT d.annee FROM FAIT_LIGNES_VENTE f JOIN DIM_DATE d ON f.id_date = d.id_date WHERE d.annee IS NOT NULL ORDER BY d.annee DESC")]
        if not years:
            years = [int(r.annee) for r in _rows("SELECT DISTINCT annee FROM DIM_DATE WHERE annee IS NOT NULL ORDER BY annee DESC")]
        if not years:
            years = [2026]


        modes = [r.libelle_mode_reg.strip() for r in _rows("SELECT DISTINCT libelle_mode_reg FROM DIM_MODE_REGLEMENT WHERE libelle_mode_reg IS NOT NULL AND libelle_mode_reg <> '' ORDER BY libelle_mode_reg")]
        if not modes:
            modes = ["Tous"]
        else:
            modes = ["Tous"] + modes

        return {
            "depots": depots,
            "segments": segments,
            "familles": familles,
            "years": years,
            "modes_paiement": modes
        }
    except Exception as exc:
        logging.error(f"Error fetching dynamic filters: {exc}")
        return {
            "depots": ["Tous", "Tunis Nord", "Tunis Sud", "Sfax", "Sousse", "Nabeul", "Bizerte", "Dépôt Central"],
            "segments": ["Tous", "DÉTAILLANTS", "SEMI-GROS", "HORECA", "GROSSISTES", "DISTRIBUTEUR"],
            "familles": ["Toutes", "Biscuits", "Boissons", "Conserves", "Produits Laitiers", "Confiserie", "Épicerie", "Huiles", "Pâtes"],
            "years": [2026, 2025, 2024, 2023, 2022, 2021, 2020],
            "modes_paiement": ["Tous", "Chèque", "Espèce", "RS", "Traite", "Virement"]
        }


@app.get("/api/etl/status")
def get_etl_status():
    try:
        last_run = _row(
            f"""
            SELECT run_id, run_date, status, duration_seconds, error_msg
            FROM {AUDIT_TABLE_NAME} WITH (NOLOCK)
            WHERE table_name = 'PIPELINE'
            ORDER BY run_date DESC
            """
        )
        counts = _rows(
            """
            SELECT 'clients' AS name, COUNT(*) AS value FROM DIM_CLIENT WITH (NOLOCK)
            UNION ALL SELECT 'articles', COUNT(*) FROM DIM_ARTICLE WITH (NOLOCK)
            UNION ALL SELECT 'ventes', COUNT(*) FROM FAIT_LIGNES_VENTE WITH (NOLOCK)
            UNION ALL SELECT 'reglements', COUNT(*) FROM FAIT_REGLEMENTS WITH (NOLOCK)
            UNION ALL SELECT 'ecritures', COUNT(*) FROM FAIT_ECRITURES WITH (NOLOCK)
            """
        )
    except Exception as exc:
        return {
            "running": _ETL_RUN_LOCK.locked(),
            "lastError": str(exc),
            "lastRun": None,
            "counts": {},
        }
    return {
        "running": _ETL_RUN_LOCK.locked(),
        "lastError": _ETL_LAST_ERROR,
        "lastRun": None if not last_run else {
            "runId": _int(last_run.run_id),
            "date": _date_str(last_run.run_date),
            "status": last_run.status,
            "durationSeconds": _int(last_run.duration_seconds),
            "error": last_run.error_msg,
        },
        "counts": {r.name: _int(r.value) for r in counts},
    }


@app.post("/api/etl/run")
def run_etl(background_tasks: BackgroundTasks):
    if not _ETL_RUN_LOCK.acquire(blocking=False):
        return {"started": False, "running": True}
    background_tasks.add_task(_run_etl_background)
    return {"started": True, "running": True}


@app.get("/api/ml/status")
def get_ml_status():
    from ml.runner import is_running, get_last_error  # type: ignore
    try:
        counts = {}
        tables = {
            "kpi05": "ML_KPI05_CA_FORECAST",
            "kpi11": "ML_KPI11_TRESORERIE_FORECAST",
            "kpi17": "ML_KPI17_REAPPRO_ALERT",
            "kpi18": "ML_KPI18_RUPTURE_FORECAST",
            "kpi22": "ML_KPI22_RFM_SEGMENTS"
        }
        for k, tbl in tables.items():
            try:
                n = _row(f"SELECT COUNT(*) AS c FROM {tbl} WITH (NOLOCK)")
                counts[k] = _int(n.c) if n else 0
            except Exception:
                counts[k] = 0

        last_date = None
        try:
            r = _row("SELECT MAX(run_date) AS d FROM ML_KPI05_CA_FORECAST WITH (NOLOCK)")
            if r and r.d:
                last_date = _date_str(r.d)
        except Exception:
            pass

    except Exception as exc:
        return {
            "running": is_running(),
            "lastError": str(exc),
            "lastRun": None,
            "counts": {},
        }

    return {
        "running": is_running(),
        "lastError": get_last_error(),
        "lastRun": {"date": last_date} if last_date else None,
        "counts": counts,
    }


@app.post("/api/ml/run")
def run_ml_endpoint():
    from ml.runner import run_all_background  # type: ignore
    started = run_all_background()
    return {"started": started, "running": True}


@app.get("/api/ml/forecast-ca")
def get_ml_forecast_ca():
    try:
        rows = _rows("""
            SELECT TOP 200
                CONVERT(VARCHAR(10), ds, 23) AS ds,
                model_name,
                yhat, yhat_lower, yhat_upper, is_historical,
                mape, mae
            FROM ML_KPI05_CA_FORECAST WITH (NOLOCK)
            WHERE run_date = (SELECT MAX(run_date) FROM ML_KPI05_CA_FORECAST WITH (NOLOCK))
            ORDER BY model_name, ds
        """)
        return [
            {
                "ds": r.ds,
                "model_name": r.model_name,
                "yhat": _num(r.yhat),
                "yhat_lower": _num(r.yhat_lower),
                "yhat_upper": _num(r.yhat_upper),
                "is_historical": int(r.is_historical),
                "mape": _num(getattr(r, 'mape', 0)),
                "mae": _num(getattr(r, 'mae', 0)),
            }
            for r in rows
        ]
    except Exception:
        return []




@app.get("/api/dashboard/kpis")
def get_dashboard_kpis(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=None, 
        quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "famille": "fa", "segment": "s"}
    )
    
    max_year_res = _row("""
        SELECT MAX(d.annee) AS annee
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DATE d ON d.id_date = f.id_date
        WHERE f.DO_Domaine = 0
    """)
    max_year = max_year_res.annee if max_year_res else datetime.now().year

    if not year:
        year = max_year

    if year < max_year:
        latest_month = 12
    else:
        meta = _row("""
            WITH counts AS (
                SELECT d2.mois, COUNT(*) AS row_cnt
                FROM FAIT_LIGNES_VENTE f2 WITH (NOLOCK)
                JOIN DIM_DATE d2 WITH (NOLOCK) ON d2.id_date = f2.id_date
                WHERE f2.DO_Domaine = 0 AND d2.annee = :year
                GROUP BY d2.mois
            ),
            monthly_stats AS (
                SELECT AVG(CAST(row_cnt AS FLOAT)) AS avg_rows
                FROM (
                    SELECT d2.annee, d2.mois, COUNT(*) AS row_cnt
                    FROM FAIT_LIGNES_VENTE f2 WITH (NOLOCK)
                    JOIN DIM_DATE d2 WITH (NOLOCK) ON d2.id_date = f2.id_date
                    WHERE f2.DO_Domaine = 0
                    GROUP BY d2.annee, d2.mois
                ) counts_all
            )
            SELECT
                COALESCE(MAX(c.mois), 12) AS latest_month
            FROM counts c
            CROSS JOIN monthly_stats ms
            WHERE c.row_cnt >= ms.avg_rows * 0.5
        """, {"year": year})
        latest_month = meta.latest_month if meta and meta.latest_month else 12
    
    latest_year = year

    sql = f"""
        SELECT
            SUM(CASE WHEN d.annee = :latest_year THEN f.DL_MontantHT ELSE 0 END) AS ca_total,
            SUM(CASE WHEN d.annee = :latest_year - 1
                AND d.mois <= :latest_month
                THEN f.DL_MontantHT ELSE 0 END) AS ca_total_n1,
            COUNT(DISTINCT CASE WHEN d.annee = :latest_year AND f.DO_Piece_hash IS NOT NULL THEN
                CONCAT(f.DO_Piece_hash, '-', COALESCE(f.DO_Type, 0))
            END) AS nb_commandes,
            COUNT(DISTINCT CASE WHEN d.annee = :latest_year - 1 AND d.mois <= :latest_month AND f.DO_Piece_hash IS NOT NULL THEN
                CONCAT(f.DO_Piece_hash, '-', COALESCE(f.DO_Type, 0))
            END) AS nb_commandes_n1,
            COUNT(DISTINCT CASE WHEN d.annee = :latest_year THEN f.id_client END) AS nb_clients_actifs,
            COUNT(DISTINCT CASE WHEN d.annee = :latest_year - 1 AND d.mois <= :latest_month THEN f.id_client END) AS nb_clients_actifs_n1,
            SUM(CASE WHEN d.annee = :latest_year
                        AND f.DL_CMUP IS NOT NULL
                        AND f.DL_CMUP > 0
                        AND f.DL_Qte IS NOT NULL
                        AND f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP)
                THEN f.DL_MontantHT - (f.DL_Qte * f.DL_CMUP)
                ELSE NULL
            END) AS marge_brute,
            SUM(CASE WHEN d.annee = :latest_year
                        AND f.DL_CMUP IS NOT NULL
                        AND f.DL_CMUP > 0
                        AND f.DL_Qte IS NOT NULL
                THEN f.DL_MontantHT
                ELSE 0
            END) AS ca_avec_cout,
            COUNT(CASE WHEN d.annee = :latest_year
                            AND f.DL_CMUP IS NOT NULL
                            AND f.DL_CMUP > 0
                            AND f.DL_Qte IS NOT NULL
                            AND f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP) THEN 1 END) AS nb_lignes_avec_cout,
            SUM(CASE WHEN d.annee = :latest_year - 1
                        AND d.mois <= :latest_month
                        AND f.DL_CMUP IS NOT NULL
                        AND f.DL_CMUP > 0
                        AND f.DL_Qte IS NOT NULL
                        AND f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP)
                THEN f.DL_MontantHT - (f.DL_Qte * f.DL_CMUP)
                ELSE NULL
            END) AS marge_brute_n1,
            SUM(CASE WHEN d.annee = :latest_year - 1
                        AND d.mois <= :latest_month
                        AND f.DL_CMUP IS NOT NULL
                        AND f.DL_CMUP > 0
                        AND f.DL_Qte IS NOT NULL
                THEN f.DL_MontantHT
                ELSE 0
            END) AS ca_avec_cout_n1,
            COUNT(CASE WHEN d.annee = :latest_year - 1
                            AND d.mois <= :latest_month
                            AND f.DL_CMUP IS NOT NULL
                            AND f.DL_CMUP > 0
                            AND f.DL_Qte IS NOT NULL
                            AND f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP) THEN 1 END) AS nb_lignes_avec_cout_n1,
            :latest_year AS computed_year
        FROM FAIT_LIGNES_VENTE f
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
        LEFT JOIN DIM_CLIENT c ON c.id_client = f.id_client
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE f.DO_Domaine = 0
        AND d.annee IN (:latest_year, :latest_year - 1)
        {filt_sql}
    """
    params = {"latest_year": latest_year, "latest_month": latest_month}
    params.update(filt_params)
    row = _row(sql, params)
    if not row:
        return {
            "ca_total": 0.0,
            "nb_commandes": 0,
            "nb_clients_actifs": 0,
            "taux_recouvrement": 0.0,
            "marge_brute_pct": 0.0,
            "ca_total_n1": 0.0,
            "ca_growth_pct": 0.0,
            "nb_commandes_growth_pct": 0.0,
            "nb_clients_actifs_growth_pct": 0.0,
            "taux_recouvrement_growth_pct": 0.0,
            "marge_brute_growth_pct": 0.0,
            "ca_avec_cout": 0.0,
        }

    ca_total = _num(row.ca_total)
    ca_total_n1 = _num(row.ca_total_n1)
    
    nb_cmd = _int(row.nb_commandes)
    nb_cmd_n1 = _int(row.nb_commandes_n1)
    
    nb_cli = _int(row.nb_clients_actifs)
    nb_cli_n1 = _int(row.nb_clients_actifs_n1)
    
    raw_marge = row.marge_brute
    ca_avec_cout = _num(getattr(row, 'ca_avec_cout', 0))
    nb_avec_cout = _int(getattr(row, 'nb_lignes_avec_cout', 0))
    marge_brute_pct = (
        (float(raw_marge) / ca_avec_cout * 100)
        if (ca_avec_cout > 0 and raw_marge is not None and nb_avec_cout > 0)
        else None
    )
    
    raw_marge_n1 = row.marge_brute_n1
    ca_avec_cout_n1 = _num(getattr(row, 'ca_avec_cout_n1', 0))
    nb_avec_cout_n1 = _int(getattr(row, 'nb_lignes_avec_cout_n1', 0))
    marge_brute_pct_n1 = (
        (float(raw_marge_n1) / ca_avec_cout_n1 * 100)
        if (ca_avec_cout_n1 > 0 and raw_marge_n1 is not None and nb_avec_cout_n1 > 0)
        else None
    )
    
    latest_year = _int(row.computed_year) or datetime.now().year
    
    try:
        rec_sql = """
            WITH deduped AS (
                SELECT
                    r.RT_Num,
                    MAX(r.RT_Montant)         AS RT_Montant,
                    MAX(r.DR_Regle)           AS DR_Regle,
                    MAX(r.id_date_paiement)   AS id_date_paiement
                FROM FAIT_REGLEMENTS r WITH (NOLOCK)
                WHERE r.RT_Num IS NOT NULL AND r.id_client IS NOT NULL
                GROUP BY r.RT_Num
            )
            SELECT
                dt.annee,
                SUM(CASE WHEN DR_Regle = 1 THEN RT_Montant ELSE 0 END) AS encaissements,
                SUM(CASE WHEN DR_Regle = 0 THEN RT_Montant ELSE 0 END) AS impayes
            FROM deduped d
            JOIN DIM_DATE dt WITH (NOLOCK) ON dt.id_date = d.id_date_paiement
            WHERE dt.annee IN (:year, :year - 1)
            GROUP BY dt.annee
        """
        rec_rows = _rows(rec_sql, {"year": latest_year})
        rec_n = 0.0
        rec_n1 = 0.0
        for r in rec_rows:
            enc = _num(r.encaissements)
            imp = _num(r.impayes)
            tot = enc + imp
            rate = (enc / tot * 100) if tot else 0.0
            if r.annee == latest_year:
                rec_n = rate
            elif r.annee == latest_year - 1:
                rec_n1 = rate
        taux_recouvrement = rec_n
        taux_recouvrement_growth_pct = round(rec_n - rec_n1, 1)
    except Exception:
        taux_recouvrement = 0.0
        taux_recouvrement_growth_pct = 0.0
        
    return {
        "ca_total": ca_total,
        "nb_commandes": nb_cmd,
        "nb_clients_actifs": nb_cli,
        "taux_recouvrement": taux_recouvrement,
        "marge_brute_pct": marge_brute_pct,
        "ca_total_n1": ca_total_n1,
        "ca_growth_pct": round(((ca_total - ca_total_n1) / ca_total_n1 * 100), 1) if ca_total_n1 else 0.0,
        "nb_commandes_growth_pct": round(((nb_cmd - nb_cmd_n1) / nb_cmd_n1 * 100), 1) if nb_cmd_n1 else 0.0,
        "nb_clients_actifs_growth_pct": round(((nb_cli - nb_cli_n1) / nb_cli_n1 * 100), 1) if nb_cli_n1 else 0.0,
        "taux_recouvrement_growth_pct": taux_recouvrement_growth_pct,
        "marge_brute_growth_pct": round(marge_brute_pct - marge_brute_pct_n1, 1) if (marge_brute_pct is not None and marge_brute_pct_n1 is not None) else 0.0,
        "ca_avec_cout": ca_avec_cout,
    }


@app.get("/api/ventes/ca-by-month")
def get_ca_by_month(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=None, 
        quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "famille": "fa", "segment": "s"}
    )
    max_year_res = _row("""
        SELECT MAX(d.annee) AS annee
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DATE d ON d.id_date = f.id_date
        WHERE f.DO_Domaine = 0
    """)
    max_year = max_year_res.annee if max_year_res else datetime.now().year

    year_filter = f"AND d.annee IN ({year}, {year - 1})" if year else ""
    sql = f"""
        WITH monthly_stats AS (
            -- Average monthly row count computed from real data
            SELECT AVG(CAST(row_cnt AS FLOAT)) AS avg_rows
            FROM (
                SELECT d.annee, d.mois, COUNT(*) AS row_cnt
                FROM FAIT_LIGNES_VENTE f
                JOIN DIM_DATE d ON d.id_date = f.id_date
                GROUP BY d.annee, d.mois
            ) counts
        ),
        monthly AS (
            SELECT
                d.annee,
                d.mois,
                SUM(f.DL_MontantHT) AS ca,
                COUNT(DISTINCT f.id_client) AS nb_clients_actifs,
                SUM(CASE WHEN f.DL_CMUP IS NOT NULL AND f.DL_CMUP > 0 AND f.DL_Qte IS NOT NULL AND f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP) THEN f.DL_MontantHT - (f.DL_Qte * f.DL_CMUP) ELSE NULL END) AS marge_brute,
                COUNT(*) AS row_cnt
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DATE d ON d.id_date = f.id_date
            LEFT JOIN DIM_CLIENT c ON c.id_client = f.id_client
            LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
            LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
            LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
            WHERE f.DO_Domaine = 0
            {year_filter}
            {filt_sql}
            GROUP BY d.annee, d.mois
        ),
        latest AS (
            SELECT 
                MAX(m.annee) AS latest_year,
                CASE 
                    WHEN MAX(m.annee) = :max_year
                    THEN COALESCE(NULLIF(MAX(CASE WHEN m.row_cnt >= ms.avg_rows * 0.5 THEN m.mois ELSE 0 END), 0), 12)
                    ELSE 12
                END AS latest_full_month
            FROM monthly m
            CROSS JOIN monthly_stats ms
            WHERE m.annee = (SELECT MAX(annee) FROM monthly)
        ),
        rolling AS (
            SELECT 
                m.annee,
                m.mois,
                m.ca,
                m.nb_clients_actifs,
                m.marge_brute,
                m.row_cnt
            FROM monthly m
            CROSS JOIN monthly_stats ms
            CROSS JOIN latest
            WHERE (
                m.annee < :max_year
                OR m.row_cnt >= ms.avg_rows * 0.5
            )
            AND (
                m.annee < latest.latest_year
                OR (m.annee = latest.latest_year AND m.mois <= latest.latest_full_month)
            )
        )
        SELECT
            r.annee,
            r.mois AS month_num,
            r.ca,
            r.nb_clients_actifs,
            r.marge_brute,
            COALESCE(prev.ca, 0) AS caN1
        FROM rolling r
        CROSS JOIN monthly_stats ms
        CROSS JOIN latest
        LEFT JOIN monthly prev
            ON prev.annee = r.annee - 1
            AND prev.mois = r.mois
            AND (
                prev.annee < :max_year
                OR prev.row_cnt >= ms.avg_rows * 0.1
            )
        WHERE r.annee = latest.latest_year
        ORDER BY r.annee, r.mois
    """
    params = {"max_year": max_year}
    params.update(filt_params)
    rows = _rows(sql, params)
    
    rec_by_month = {}
    if rows:
        latest_year = rows[0].annee
        rec_sql = """
            WITH deduped AS (
                SELECT
                    r.RT_Num,
                    MAX(r.RT_Montant)         AS RT_Montant,
                    MAX(r.DR_Regle)           AS DR_Regle,
                    MAX(r.id_date_paiement)   AS id_date_paiement
                FROM FAIT_REGLEMENTS r WITH (NOLOCK)
                WHERE r.RT_Num IS NOT NULL AND r.id_client IS NOT NULL
                GROUP BY r.RT_Num
            )
            SELECT
                dt.mois,
                SUM(CASE WHEN DR_Regle = 1 THEN RT_Montant ELSE 0 END) AS encaissements,
                SUM(CASE WHEN DR_Regle = 0 THEN RT_Montant ELSE 0 END) AS impayes
            FROM deduped d
            JOIN DIM_DATE dt WITH (NOLOCK) ON dt.id_date = d.id_date_paiement
            WHERE dt.annee = :year
            GROUP BY dt.mois
        """
        rec_rows = _rows(rec_sql, {"year": latest_year})
        for r in rec_rows:
            enc = _num(r.encaissements)
            imp = _num(r.impayes)
            tot = enc + imp
            rate = (enc / tot * 100) if tot else 0.0
            rec_by_month[r.mois] = rate

    return [
        {
            "month": f"{MONTHS[r.month_num - 1]} {str(r.annee)[2:]}",
            "ca": _num(r.ca),
            "caN1": _num(r.caN1),
            "nb_clients_actifs": _int(r.nb_clients_actifs),
            "marge_brute": _num(r.marge_brute),
            "taux_recouvrement": rec_by_month.get(r.month_num, 0.0),
            "objectif": round(_num(r.caN1) * 1.10, 2) if _num(r.caN1) > 0 else round(_num(r.ca) * 1.05, 2),
        }
        for r in rows
    ]



@app.get("/api/ventes/top-familles")
def get_top_familles(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "famille": "fa", "segment": "s"}
    )
    sql = f"""
        SELECT 
            COALESCE(NULLIF(fa.FA_Intitule, ''), 'Sans famille') AS name,
            SUM(f.DL_MontantHT) AS ca
        FROM FAIT_LIGNES_VENTE f
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        LEFT JOIN DIM_CLIENT c ON c.id_client = f.id_client
        LEFT JOIN DIM_ARTICLE a  ON a.id_article  = f.id_article
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE f.DO_Domaine = 0
        AND fa.FA_Intitule IS NOT NULL
        AND fa.FA_Intitule <> ''
        {filt_sql}
        GROUP BY fa.FA_Intitule
        ORDER BY ca DESC
    """
    return [
        {"name": r.name, "ca": _num(r.ca)}
        for r in _rows(sql, filt_params)
    ]



@app.get("/api/tresorerie/summary")
def get_tresorerie_summary(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "segment": "s"}
    )
    sql = f"""
        WITH deduped AS (
            SELECT
                r.RT_Num,
                MAX(r.RT_Montant)         AS RT_Montant,
                MAX(r.DR_Regle)           AS DR_Regle,
                MAX(r.delai_reel_jours)   AS delai_reel_jours
            FROM FAIT_REGLEMENTS r
            LEFT JOIN DIM_DATE d ON d.id_date = r.id_date_paiement
            LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
            LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
            WHERE r.RT_Num IS NOT NULL AND r.id_client IS NOT NULL
            {filt_sql}
            GROUP BY r.RT_Num
        )
        SELECT
            SUM(CASE WHEN DR_Regle = 1 THEN RT_Montant ELSE 0 END) AS encaissements,
            SUM(CASE WHEN DR_Regle = 0 THEN RT_Montant ELSE 0 END) AS impayes,
            AVG(CAST(delai_reel_jours AS FLOAT)) AS delai_moyen
        FROM deduped
    """
    row = _row(sql, filt_params)
    if not row:
        return {
            "encaissements": 0.0,
            "impayes": 0.0,
            "delai_moyen": 0,
            "taux_recouvrement": 0.0,
        }
    encaissements = _num(row.encaissements)
    impayes = _num(row.impayes)
    total = encaissements + impayes
    return {
        "encaissements": encaissements,
        "impayes": impayes,
        "delai_moyen": round(_num(row.delai_moyen)),
        "taux_recouvrement": (encaissements / total * 100) if total else 0,
    }





@app.get("/api/tresorerie/aging")
def get_aging(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "segment": "s"}
    )
    sql = f"""
        SELECT 
            COALESCE(MAX(c.CT_Intitule), CONVERT(VARCHAR(30), c.CT_Num_code)) AS client,
            SUM(CASE WHEN r.bucket_impaye = 0 THEN r.RT_Montant ELSE 0 END) AS b0,
            SUM(CASE WHEN r.bucket_impaye = 1 THEN r.RT_Montant ELSE 0 END) AS b1,
            SUM(CASE WHEN r.bucket_impaye = 2 THEN r.RT_Montant ELSE 0 END) AS b2,
            SUM(CASE WHEN r.bucket_impaye = 3 THEN r.RT_Montant ELSE 0 END) AS b3
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
        LEFT JOIN DIM_DATE d ON d.id_date = r.id_date_paiement
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE r.id_client IS NOT NULL
        AND r.DR_Regle = 0
        {filt_sql}
        GROUP BY c.CT_Num_code
        ORDER BY b3 DESC
    """
    return [
        {
            "client": r.client,
            "0-30j": _num(r.b0),
            "31-60j": _num(r.b1),
            "61-90j": _num(r.b2),
            ">90j": _num(r.b3),
        }
        for r in _rows(sql, filt_params)
    ]



@app.get("/api/produits/articles")
def get_articles(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "famille": "fa", "segment": "s"}
    )
    sql = f"""
        WITH sales AS (
            SELECT
                f.id_article,
                COALESCE(SUM(DL_Qte), 0) AS qte_vendue,
                COALESCE(SUM(DL_MontantHT), 0) AS ca
            FROM FAIT_LIGNES_VENTE f
            LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
            LEFT JOIN DIM_CLIENT c ON c.id_client = f.id_client
            LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
            LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
            LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
            WHERE f.DO_Domaine = 0
            {filt_sql}
            GROUP BY f.id_article
        ),
        stock AS (
            SELECT
                e.id_article,
                SUM(e.AS_QteSto)    AS stock,
                MAX(e.dsi_jours)    AS dsi_jours,
                MAX(e.AS_QteMini)   AS stock_mini,
                MAX(e.ratio_tension) AS ratio_tension,
                SUM(e.AS_MontSto)   AS valeur_stock
            FROM FAIT_ECRITURES e
            WHERE e.grain = 4
            AND e.AS_QteSto IS NOT NULL
            GROUP BY e.id_article
        )
        SELECT 
            a.AR_Ref_code,
            a.AR_Design,
            a.id_famille,
            COALESCE(NULLIF(fa.FA_Intitule, ''), 'Sans famille') AS famille,
            CASE
                WHEN COALESCE(a.AR_PrixAch, 0) > 0 THEN a.AR_PrixAch
                WHEN COALESCE(stock.stock, 0) > 0 AND COALESCE(stock.valeur_stock, 0) > 0
                THEN stock.valeur_stock / stock.stock
                ELSE 0
            END AS prix_moyen,
            COALESCE(sales.qte_vendue, 0) AS qte_vendue,
            COALESCE(sales.ca, 0) AS ca,
            COALESCE(stock.stock, 0) AS stock,
            stock.dsi_jours,
            stock.ratio_tension
        FROM DIM_ARTICLE a
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
        LEFT JOIN sales ON sales.id_article = a.id_article
        LEFT JOIN stock ON stock.id_article = a.id_article
        WHERE COALESCE(sales.ca, 0) > 0 OR COALESCE(stock.stock, 0) > 0
        ORDER BY ca DESC
    """
    return [
        {
            "code": r.AR_Ref_code,
            "designation": r.AR_Design if r.AR_Design else f"Article {r.AR_Ref_code}",
            "famille": r.famille,
            "qteVendue": _num(r.qte_vendue),
            "ca": _num(r.ca),
            "prixMoyen": _num(r.prix_moyen),
            "marge": round(
                (_num(r.ca) - _num(r.prix_moyen) * _num(r.qte_vendue)) / _num(r.ca) * 100, 1
            ) if _num(r.ca) > 0 and _num(r.prix_moyen) > 0 else None,
            "stock": _num(r.stock),
            "dsi": _num(r.dsi_jours),
        }
        for r in _rows(sql, filt_params)
    ]

@app.get("/api/acteurs/clients")
def get_clients(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "segment": "s"}
    )
    sql = f"""
        SELECT 
            c.CT_Num_code,
            COALESCE(c.CT_Intitule, CONVERT(VARCHAR(30), c.CT_Num_code)) AS nom,
            COALESCE(s.libelle_segment, 'Sans segment') AS segment,
            COALESCE(SUM(v.DL_MontantHT), 0) AS ca_total,
            COUNT(DISTINCT v.DO_Piece_hash) AS nb_commandes,
            FORMAT(MAX(d.date_val), 'yyyy-MM-dd') AS derniere_commande,
            c.CT_SoldeActuel AS solde_impaye,
            c.CT_Sommeil AS sommeil
        FROM DIM_CLIENT c
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        LEFT JOIN FAIT_LIGNES_VENTE v ON v.id_client = c.id_client AND v.DO_Domaine = 0
        LEFT JOIN DIM_DATE d ON d.id_date = v.id_date
        WHERE 1=1
        {filt_sql}
        GROUP BY c.CT_Num_code, c.CT_Intitule, s.libelle_segment, c.CT_SoldeActuel, c.CT_Sommeil
        ORDER BY ca_total DESC
    """
    return [
        {
            "code": str(r.CT_Num_code),
            "nom": r.nom,
            "region": "",
            "caTotal": _num(r.ca_total),
            "nbCommandes": _int(r.nb_commandes),
            "derniereCommande": r.derniere_commande or "",
            "soldeImpaye": _num(r.solde_impaye),
            "segment": r.segment,
            "actif": _int(r.sommeil) == 0,
            "nouveau": _int(r.nb_commandes) == 1,
        }
        for r in _rows(sql, filt_params)
    ]



@app.get("/api/acteurs/aging")
def get_acteurs_aging(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "segment": "s"}
    )
    sql = f"""
        SELECT 
            c.CT_Num_code,
            COALESCE(c.CT_Intitule, CONVERT(VARCHAR(30), c.CT_Num_code)) AS client_nom,
            SUM(CASE WHEN r.bucket_impaye = 0 THEN r.RT_Montant ELSE 0 END) AS b0,
            SUM(CASE WHEN r.bucket_impaye = 1 THEN r.RT_Montant ELSE 0 END) AS b1,
            SUM(CASE WHEN r.bucket_impaye = 2 THEN r.RT_Montant ELSE 0 END) AS b2,
            SUM(CASE WHEN r.bucket_impaye = 3 THEN r.RT_Montant ELSE 0 END) AS b3
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
        LEFT JOIN DIM_DATE d ON d.id_date = COALESCE(r.id_date_paiement, r.id_date_echeance)
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE r.id_client IS NOT NULL
        AND r.DR_Regle = 0
        {filt_sql}
        GROUP BY c.CT_Num_code, c.CT_Intitule
        ORDER BY b3 DESC
    """
    return [
        {
            "clientCode": str(r.CT_Num_code),
            "client": r.client_nom,
            "0-30j": _num(r.b0),
            "31-60j": _num(r.b1),
            "61-90j": _num(r.b2),
            ">90j": _num(r.b3),
        }
        for r in _rows(sql, filt_params)
    ]


@app.get("/api/acteurs/fournisseurs")
def get_acteurs_fournisseurs(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"famille": "a", "article": "a"}
    )
    sql = f"""
        SELECT 
            f.CT_Num_code,
            f.CT_Intitule,
            f.CT_Encours,
            COUNT(a.id_article) AS nb_articles
        FROM DIM_FOURNISSEUR f
        LEFT JOIN DIM_ARTICLE a ON a.id_fournisseur = f.id_fournisseur
        WHERE 1=1
        {filt_sql}
        GROUP BY f.CT_Num_code, f.CT_Intitule, f.CT_Encours
        ORDER BY nb_articles DESC, f.CT_Encours DESC
    """
    return [
        {
            "code": str(r.CT_Num_code),
            "nom": r.CT_Intitule if r.CT_Intitule else f"Fournisseur {r.CT_Num_code}",
            "encours": _num(r.CT_Encours),
            "nbArticles": _int(r.nb_articles),
        }
        for r in _rows(sql, filt_params)
    ]



@app.get("/api/acteurs/fournisseur-concentration")
def get_fournisseur_concentration(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"famille": "a", "article": "a"}
    )
    sql = f"""
        SELECT
            f.CT_Num_code,
            f.CT_Intitule,
            f.CT_Encours             AS montant_achat,
            COUNT(a.id_article)      AS nb_articles
        FROM DIM_FOURNISSEUR f
        LEFT JOIN DIM_ARTICLE a ON a.id_fournisseur = f.id_fournisseur
        WHERE 1=1
        {filt_sql}
        GROUP BY f.CT_Num_code, f.CT_Intitule, f.CT_Encours
        HAVING COUNT(a.id_article) > 0
        ORDER BY f.CT_Encours DESC
    """
    rows = list(_rows(sql, filt_params))
    total = sum(_num(r.montant_achat) for r in rows)
    return [
        {
            "fournisseur": r.CT_Intitule if r.CT_Intitule else f"Fournisseur {r.CT_Num_code}",
            "nbArticles": _int(r.nb_articles),
            "nbArticlesAchetes": _int(r.nb_articles),
            "montantAchat": _num(r.montant_achat),
            "hhi": round((_num(r.montant_achat) / total) ** 2, 4) if total > 0 else 0,
            "risqueConcentration": (_num(r.montant_achat) / total > 0.3) if total > 0 else False,
        }
        for r in rows
    ]


@app.get("/api/banque/rapprochement")
def get_banque_rapprochement(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "segment": "s"}
    )
    sql = f"""
        WITH deduped AS (
            SELECT
                r.RT_Num,
                MAX(r.RT_Montant)       AS RT_Montant,
                MAX(r.DR_Regle)         AS DR_Regle,
                MAX(r.RT_Rapproche)     AS RT_Rapproche,
                MAX(r.id_banque)        AS id_banque,
                MAX(r.LB_NbJour)        AS LB_NbJour,
                MAX(r.LB_Agios)         AS LB_Agios,
                CAST(NULL AS FLOAT)     AS BR_TauxAgios,
                MAX(r.id_date_paiement) AS id_date_paiement,
                MAX(r.id_date_echeance) AS id_date_echeance
            FROM FAIT_REGLEMENTS r
            LEFT JOIN DIM_DATE d ON d.id_date = COALESCE(r.id_date_paiement, r.id_date_echeance)
            LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
            LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
            WHERE r.RT_Num IS NOT NULL AND r.id_client IS NOT NULL
            {filt_sql}
            GROUP BY r.RT_Num
        )
        SELECT
            d.mois AS month_num,
            AVG(CASE
                WHEN r.RT_Rapproche = 1 THEN 100.0
                WHEN r.DR_Regle = 1     THEN 100.0
                ELSE 0.0
            END) AS taux,
            SUM(CASE
                WHEN COALESCE(r.RT_Rapproche, 0) = 0 AND COALESCE(r.DR_Regle, 0) = 0
                THEN 1 ELSE 0
            END) AS non_rapproches,
            AVG(CAST(NULLIF(r.LB_NbJour, 0) AS FLOAT)) AS nb_jour,
            SUM(COALESCE(r.LB_Agios, 0)) AS agios,
            AVG(CAST(NULLIF(r.BR_TauxAgios, 0) AS FLOAT)) AS taux_agios
        FROM deduped r
        LEFT JOIN DIM_DATE d ON d.id_date = COALESCE(r.id_date_paiement, r.id_date_echeance)
        WHERE d.mois IS NOT NULL
        AND r.RT_Montant IS NOT NULL
        GROUP BY d.mois
        ORDER BY d.mois
    """
    return [
        {
            "month": MONTHS[r.month_num - 1],
            "taux": round(_num(r.taux)),
            "nonRapproches": _int(r.non_rapproches),
            "nbJour": None if r.nb_jour is None else round(_num(r.nb_jour), 1),
            "agios": _num(r.agios),
            "tauxAgios": None if r.taux_agios is None else round(_num(r.taux_agios), 2),
        }
        for r in _rows(sql, filt_params)
    ]


@app.get("/api/banque/rapprochement-breakdown")
def get_banque_rapprochement_breakdown(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "segment": "s"}
    )
    sql = f"""
        SELECT 
            CASE r.RT_Mode
                WHEN 1 THEN 'Espèce'
                WHEN 2 THEN 'Chèque'
                WHEN 3 THEN 'Virement'
                WHEN 4 THEN 'Traite'
                WHEN 5 THEN 'Carte Bancaire'
                ELSE 'Autre'
            END AS libelle_mode_reg,
            SUM(COALESCE(r.RT_Montant, 0)) AS total_montant
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_DATE d ON d.id_date = COALESCE(r.id_date_paiement, r.id_date_echeance)
        LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE COALESCE(r.RT_Rapproche, 0) = 0 AND COALESCE(r.DR_Regle, 0) = 0
        AND r.id_client IS NOT NULL
        {filt_sql}
        GROUP BY r.RT_Mode
    """
    totals = {"Chèque": 0.0, "Traite": 0.0, "Virement": 0.0}
    for r in _rows(sql, filt_params):
        mode_label = r.libelle_mode_reg or ""
        if "Ch" in mode_label or "ch" in mode_label or "Chéque" in mode_label:
            totals["Chèque"] += _num(r.total_montant)
        elif "Trait" in mode_label or "trait" in mode_label or "LCR" in mode_label:
            totals["Traite"] += _num(r.total_montant)
        elif "Vir" in mode_label or "vir" in mode_label:
            totals["Virement"] += _num(r.total_montant)

    sql_tx = f"""
        SELECT TOP 25
            r.RT_Num,
            CASE r.RT_Mode
                WHEN 1 THEN 'Espèce'
                WHEN 2 THEN 'Chèque'
                WHEN 3 THEN 'Virement'
                WHEN 4 THEN 'Traite'
                WHEN 5 THEN 'Carte Bancaire'
                ELSE 'Autre'
            END AS libelle_mode_reg,
            COALESCE(r.RT_Montant, 0) AS montant,
            COALESCE(c.CT_Intitule, 'Client Divers') AS client
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_DATE d ON d.id_date = COALESCE(r.id_date_paiement, r.id_date_echeance)
        LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE COALESCE(r.RT_Rapproche, 0) = 0 AND COALESCE(r.DR_Regle, 0) = 0
        AND r.id_client IS NOT NULL
        {filt_sql}
        ORDER BY COALESCE(r.RT_Montant, 0) DESC
    """
    transactions = []
    for r in _rows(sql_tx, filt_params):
        mode_label = r.libelle_mode_reg or ""
        mode_mapped = "Autre"
        if "Ch" in mode_label or "ch" in mode_label:
            mode_mapped = "Chèque"
        elif "Trait" in mode_label or "trait" in mode_label or "LCR" in mode_label:
            mode_mapped = "Traite"
        elif "Vir" in mode_label or "vir" in mode_label:
            mode_mapped = "Virement"
        elif "Esp" in mode_label or "esp" in mode_label:
            mode_mapped = "Espèce"

        transactions.append({
            "reference": r.RT_Num,
            "mode": mode_mapped,
            "montant": _num(r.montant),
            "client": r.client
        })

    return {
        "totals": totals,
        "transactions": transactions
    }


@app.get("/api/caisse/caisses")
def get_caisses(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=None, source=source,
        aliases={"date": "d"}
    )
    c_depot = _clean_filter(depot)
    depot_clause = ""
    depot_params = {}
    if c_depot:
        rev_map = {"tunis nord": 1425916589894576877, "tunis sud": 1085862494906140374, "sfax": 2798417896384401189, "sousse": 6528386168626322420}
        depot_code = rev_map.get(c_depot.lower())
        if depot_code:
            depot_clause = "AND c.CA_Numero_code = :p_caisse_depot"
            depot_params["p_caisse_depot"] = depot_code

    sql = f"""
        WITH seuil AS (
            SELECT AVG(ABS(CA_SoldeEspece)) AS seuil_min
            FROM FAIT_ECRITURES
            WHERE CA_SoldeEspece IS NOT NULL
            AND CA_SoldeEspece > 0
        )
        SELECT 
            c.CA_Numero_code,
            MAX(e.CA_SoldeEspece) AS especes,
            MAX(e.CA_SoldeCheque) AS cheques,
            MAX(s.seuil_min)      AS seuil_min
        FROM DIM_CAISSE c
        LEFT JOIN FAIT_ECRITURES e ON e.id_caisse = c.id_caisse
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        CROSS JOIN seuil s
        WHERE 1=1
        {depot_clause}
        {filt_sql}
        GROUP BY c.CA_Numero_code
        ORDER BY c.CA_Numero_code
    """
    params = {}
    params.update(filt_params)
    params.update(depot_params)
    depot_map = {
        1425916589894576877: "Tunis Nord",
        1085862494906140374: "Tunis Sud",
        2798417896384401189: "Sfax",
        6528386168626322420: "Sousse"
    }
    return [
        {
            "id": f"CA-{r.CA_Numero_code}",
            "nom": f"Caisse {depot_map.get(r.CA_Numero_code, 'Dépôt Central')}",
            "especes": abs(_num(r.especes)),
            "cheques": abs(_num(r.cheques)),
            "seuilMin": _num(r.seuil_min),  
            "depot": depot_map.get(r.CA_Numero_code, "Dépôt Central"),
        }
        for r in _rows(sql, params)
    ]


@app.get("/api/caisse/flux-daily")
def get_caisse_flux_daily(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=None, source=source,
        aliases={"date": "d"}
    )
    c_depot = _clean_filter(depot)
    depot_clause = ""
    depot_params = {}
    if c_depot:
        rev_map = {"tunis nord": 1425916589894576877, "tunis sud": 1085862494906140374, "sfax": 2798417896384401189, "sousse": 6528386168626322420}
        depot_code = rev_map.get(c_depot.lower())
        if depot_code:
            depot_clause = "AND e.id_caisse = (SELECT id_caisse FROM DIM_CAISSE WHERE CA_Numero_code = :p_caisse_depot)"
            depot_params["p_caisse_depot"] = depot_code

    sql = f"""
        SELECT 
            d.date_val,
            SUM(COALESCE(e.MC_Credit, 0)) AS credit,
            SUM(COALESCE(e.MC_Debit, 0))  AS debit
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        WHERE e.grain = 3
        AND d.date_val IS NOT NULL
        {depot_clause}
        {filt_sql}
        GROUP BY d.date_val
        ORDER BY d.date_val DESC
    """
    params = {}
    params.update(filt_params)
    params.update(depot_params)
    rows = list(reversed(_rows(sql, params)))
    cumul = 0.0
    data = []
    for i, r in enumerate(rows):
        credit = _num(r.credit)
        debit  = _num(r.debit)
        net    = credit - debit
        cumul += net
        data.append({
            "day": f"J-{len(rows) - i}",
            "credit": credit,
            "debit": -debit,
            "net": net,
            "cumul": cumul,
        })
    return data


@app.get("/api/caisse/mouvements-by-type")
def get_caisse_mouvements_by_type(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=None, source=source,
        aliases={"date": "d"}
    )
    c_depot = _clean_filter(depot)
    depot_clause = ""
    depot_params = {}
    if c_depot:
        rev_map = {"tunis nord": 1425916589894576877, "tunis sud": 1085862494906140374, "sfax": 2798417896384401189, "sousse": 6528386168626322420}
        depot_code = rev_map.get(c_depot.lower())
        if depot_code:
            depot_clause = "AND e.id_caisse = (SELECT id_caisse FROM DIM_CAISSE WHERE CA_Numero_code = :p_caisse_depot)"
            depot_params["p_caisse_depot"] = depot_code

    sql = f"""
        SELECT
            CASE tm.MC_TypeMvt
                WHEN 1 THEN 'Recette'
                WHEN 2 THEN 'Dépense'
                WHEN 3 THEN 'Transfert'
                ELSE CONCAT('Mouvement ', tm.MC_TypeMvt)
            END AS name,
            SUM(ABS(COALESCE(e.MC_Credit, 0)) + ABS(COALESCE(e.MC_Debit, 0))) AS value
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_TYPE_MVT_CAISSE tm ON tm.id_type_mvt = e.id_type_mvt_caisse
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        WHERE e.grain = 3
        {depot_clause}
        {filt_sql}
        GROUP BY tm.MC_TypeMvt
        ORDER BY SUM(ABS(COALESCE(e.MC_Credit, 0)) + ABS(COALESCE(e.MC_Debit, 0))) DESC
    """
    params = {}
    params.update(filt_params)
    params.update(depot_params)
    rows = _rows(sql, params)
    total = sum(_num(r.value) for r in rows)
    if total <= 0:
        return []
    return [
        {
            "name": r.name,
            "value": round(_num(r.value) / total * 100, 1),
            "amount": _num(r.value),
        }
        for r in rows
    ]


@app.get("/api/fiscalite/kpis")
def get_fiscalite_kpis(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d"}
    )
    sql_kpis = f"""
        SELECT
            SUM(CASE WHEN e.grain IN (1, 2) THEN 1 ELSE 0 END) AS nb_ecritures,
            SUM(CASE WHEN e.grain = 2 AND j.JO_Type = 0 THEN COALESCE(e.RT_Montant01, 0) ELSE 0 END) AS tva_collectee,
            SUM(CASE WHEN e.grain = 2 AND j.JO_Type = 1 THEN COALESCE(e.RT_Montant01, 0) ELSE 0 END) AS tva_deductible,
            SUM(CASE
                WHEN e.grain = 1
                AND ABS(COALESCE(e.EC_Montant, 0)) >= (
                    SELECT AVG(ABS(EC_Montant)) + STDEV(ABS(EC_Montant))
                    FROM FAIT_ECRITURES
                    WHERE EC_Montant IS NOT NULL
                )
                THEN 1 ELSE 0
            END) AS anomalies
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_JOURNAL j ON j.id_journal = e.id_journal
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        WHERE 1=1
        {filt_sql}
    """
    row = _row(sql_kpis, filt_params)

    sql_dc = f"""
        SELECT
            SUM(CASE WHEN e.EC_Sens = 0 THEN ABS(e.EC_Montant) ELSE 0 END) AS debit,
            SUM(CASE WHEN e.EC_Sens = 1 THEN ABS(e.EC_Montant) ELSE 0 END) AS credit
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        WHERE e.grain IN (1, 2)
        {filt_sql}
    """
    debit_credit = _row(sql_dc, filt_params)

    if not row or not debit_credit:
        return {
            "nb_ecritures": 0,
            "tva_collectee": 0.0,
            "tva_deductible": 0.0,
            "anomalies": 0,
            "equilibre_pct": 100.0,
        }

    debit = _num(debit_credit.debit)
    credit = _num(debit_credit.credit)
    total = max(debit, credit)
    return {
        "nb_ecritures": _int(row.nb_ecritures),
        "tva_collectee": _num(row.tva_collectee),
        "tva_deductible": _num(row.tva_deductible),
        "anomalies": _int(row.anomalies),
        "equilibre_pct": (min(debit, credit) / total * 100) if total else 100,
    }


@app.get("/api/fiscalite/tva-by-month")
def get_fiscalite_tva_by_month(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d"}
    )
    sql = f"""
        SELECT
            d.mois AS month_num,
            SUM(CASE WHEN e.grain = 2 AND j.JO_Type = 0 THEN COALESCE(e.RT_Montant01, 0) ELSE 0 END) AS collectee,
            SUM(CASE WHEN e.grain = 2 AND j.JO_Type = 1 THEN COALESCE(e.RT_Montant01, 0) ELSE 0 END) AS deductible
        FROM FAIT_ECRITURES e
        JOIN DIM_DATE d ON d.id_date = e.id_date
        LEFT JOIN DIM_JOURNAL j ON j.id_journal = e.id_journal
        WHERE e.grain = 2
        AND e.RT_Montant01 IS NOT NULL
        {filt_sql}
        GROUP BY d.mois
        ORDER BY d.mois
    """
    return [
        {
            "month": MONTHS[r.month_num - 1],
            "collectee": _num(r.collectee),
            "deductible": _num(r.deductible),
            "soldeNet": _num(r.collectee) - _num(r.deductible),
        }
        for r in _rows(sql, filt_params)
    ]


@app.get("/api/fiscalite/anomalies")
def get_fiscalite_anomalies(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    source: Optional[str] = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=year, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d"}
    )
    sql = f"""
        WITH stats AS (
            SELECT 
                AVG(ABS(EC_Montant))  AS avg_montant,
                STDEV(ABS(EC_Montant)) AS stdev_montant
            FROM FAIT_ECRITURES
            WHERE EC_Montant IS NOT NULL
        )
        SELECT 
            d.date_val,
            COALESCE(CONVERT(VARCHAR(30), j.JO_Num_code), 'Journal') AS journal,
            ABS(COALESCE(e.EC_Montant, 0)) AS montant,
            CASE
                WHEN ABS(e.EC_Montant) >= stats.avg_montant + 3 * stats.stdev_montant THEN 0.95
                WHEN ABS(e.EC_Montant) >= stats.avg_montant + 2 * stats.stdev_montant THEN 0.85
                WHEN ABS(e.EC_Montant) >= stats.avg_montant + 1 * stats.stdev_montant THEN 0.70
                ELSE 0.25
            END AS score
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        LEFT JOIN DIM_JOURNAL j ON j.id_journal = e.id_journal
        CROSS JOIN stats
        WHERE e.EC_Montant IS NOT NULL
        AND e.grain IN (1, 2)
        {filt_sql}
        ORDER BY montant DESC
    """
    return [
        {
            "date": _date_str(r.date_val),
            "score": _num(r.score),
            "montant": _num(r.montant),
            "journal": r.journal,
            "anomalie": _num(r.score) >= 0.8,
        }
        for r in _rows(sql, filt_params)
    ]



