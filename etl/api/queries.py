import json
import logging
import os
import re
import threading
import unicodedata
from typing import List
from pathlib import Path

from google import genai
from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from etl.config import DW_ENGINE, MAG_ENGINE, SEUIL_TENSION_STOCK, AUDIT_TABLE_NAME
from etl import pipeline

app = FastAPI(title="FinMAG API") #
_ETL_RUN_LOCK = threading.Lock()
_ETL_LAST_ERROR = None
_startup_logger = logging.getLogger("api.startup")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
if _GEMINI_API_KEY:
    _GEMINI_CLIENT = genai.Client(api_key=_GEMINI_API_KEY)
    _LLM_READY = True
    _startup_logger.info("Gemini LLM ready.")
else:
    _GEMINI_CLIENT = None
    _LLM_READY = False
    _startup_logger.warning(
        "GEMINI_API_KEY not set - LLM assistant disabled. "
        "Add it to etl/.env to enable."
    )


MONTHS = ["Jan", "Fev", "Mar", "Avr", "Mai", "Jun", "Jul", "Aou", "Sep", "Oct", "Nov", "Dec"]

_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

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


def _clean_filter(val: str):
    if not val:
        return None
    cleaned = str(val).strip().strip('"').strip("'")
    if cleaned.lower() in ("tous", "toutes", "toutes regions", "null", "undefined", ""):
        return None
    return cleaned


def _parse_month(month_str: str) -> int:
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
        clauses.append(f"AND {aliases['famille']}.FA_Intitule = :p_famille")
        params["p_famille"] = c_famille

    c_segment = _clean_filter(segment)
    if c_segment and aliases.get("segment"):
        clauses.append(f"AND {aliases['segment']}.libelle_segment = :p_segment")
        params["p_segment"] = c_segment

    c_depot = _clean_filter(depot)
    if c_depot and aliases.get("depot"):
        if "central" in c_depot.lower():
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
        # Auto-retrain ML models after successful ETL run
        try:
            from ml.runner import run_all as run_ml
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
        # 1. Depots from F_DEPOT in Sage (MAG_ENGINE)
        with MAG_ENGINE.connect() as conn:
            depots = [r.DE_Intitule.strip() for r in conn.execute(text("SELECT DISTINCT DE_Intitule FROM F_DEPOT WHERE DE_Intitule IS NOT NULL ORDER BY DE_Intitule")).fetchall()]
        if not depots:
            depots = ["Tous"]
        else:
            depots = ["Tous"] + depots

        # 2. Segments from DIM_SEGMENT
        segments = [r.libelle_segment.strip() for r in _rows("SELECT DISTINCT libelle_segment FROM DIM_SEGMENT WHERE libelle_segment IS NOT NULL ORDER BY libelle_segment")]
        if not segments:
            segments = ["Tous"]
        else:
            segments = ["Tous"] + segments

        # 3. Families from DIM_ARTICLE
        familles = [r.FA_Intitule.strip() for r in _rows("SELECT DISTINCT FA_Intitule FROM DIM_ARTICLE WHERE FA_Intitule IS NOT NULL AND FA_Intitule <> '' ORDER BY FA_Intitule")]
        if not familles:
            familles = ["Toutes"]
        else:
            familles = ["Toutes"] + familles

        # 4. Years from DIM_DATE referenced by sales
        years = [int(r.annee) for r in _rows("SELECT DISTINCT d.annee FROM FAIT_LIGNES_VENTE f JOIN DIM_DATE d ON f.id_date = d.id_date WHERE d.annee IS NOT NULL ORDER BY d.annee DESC")]
        if not years:
            years = [int(r.annee) for r in _rows("SELECT DISTINCT annee FROM DIM_DATE WHERE annee IS NOT NULL ORDER BY annee DESC")]
        if not years:
            years = [2024]

        # 5. Payment Modes from DIM_MODE_REGLEMENT
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
        # Fallback to keep app 100% robust and stable
        return {
            "depots": ["Tous", "Tunis Nord", "Tunis Sud", "Sfax", "Sousse", "Nabeul", "Bizerte", "Dépôt Central"],
            "segments": ["Tous", "DÉTAILLANTS", "SEMI-GROS", "HORECA", "GROSSISTES", "DISTRIBUTEUR"],
            "familles": ["Toutes", "Biscuits", "Boissons", "Conserves", "Produits Laitiers", "Confiserie", "Épicerie", "Huiles", "Pâtes"],
            "years": [2024],
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
    from ml.runner import is_running, get_last_error
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
    from ml.runner import run_all_background
    started = run_all_background()
    return {"started": started, "running": True}


@app.get("/api/ml/forecast-ca")
def get_ml_forecast_ca():
    try:
        rows = _rows("""
            SELECT TOP 50
                CONVERT(VARCHAR(10), ds, 23) AS ds,
                yhat, yhat_lower, yhat_upper, is_historical
            FROM ML_KPI05_CA_FORECAST WITH (NOLOCK)
            WHERE run_date = (SELECT MAX(run_date) FROM ML_KPI05_CA_FORECAST WITH (NOLOCK))
            ORDER BY ds
        """)
        return [
            {
                "ds": r.ds,
                "yhat": _num(r.yhat),
                "yhat_lower": _num(r.yhat_lower),
                "yhat_upper": _num(r.yhat_upper),
                "is_historical": int(r.is_historical),
            }
            for r in rows
        ]
    except Exception:
        return []


@app.get("/api/ml/forecast-tresorerie")
def get_ml_forecast_tresorerie():
    try:
        rows = _rows("""
            SELECT TOP 100
                layer, horizon_bucket, encaissements, nb_reglements
            FROM ML_KPI11_TRESORERIE_FORECAST WITH (NOLOCK)
            WHERE run_date = (SELECT MAX(run_date) FROM ML_KPI11_TRESORERIE_FORECAST WITH (NOLOCK))
            ORDER BY layer, horizon_bucket
        """)
        return [
            {
                "layer": r.layer,
                "horizon_bucket": r.horizon_bucket,
                "encaissements": _num(r.encaissements),
                "nb_reglements": _int(r.nb_reglements),
            }
            for r in rows
        ]
    except Exception:
        return []


@app.get("/api/ml/produits-alerts")
def get_ml_produits_alerts():
    try:
        rows = _rows("""
            SELECT TOP 100
                article, famille, priorite,
                consoJourMoy, consoJourPred, cvConso,
                stockActuel, stockSecurite, r2Score
            FROM ML_KPI18_RUPTURE_FORECAST WITH (NOLOCK)
            WHERE run_date = (SELECT MAX(run_date) FROM ML_KPI18_RUPTURE_FORECAST WITH (NOLOCK))
            ORDER BY priorite DESC, cvConso DESC
        """)
        return [
            {
                "article": r.article,
                "famille": r.famille,
                "priorite": r.priorite,
                "consoJourMoy": _num(r.consoJourMoy),
                "consoJourPred": _num(r.consoJourPred),
                "cvConso": _num(r.cvConso),
                "stockActuel": _num(r.stockActuel),
                "stockSecurite": _num(r.stockSecurite),
                "r2Score": _num(r.r2Score),
            }
            for r in rows
        ]
    except Exception:
        return []


@app.get("/api/ml/rfm-segments")
def get_ml_rfm_segments():
    try:
        meta = _row("""
            SELECT TOP 1 silhouette_score, inertia, nb_clusters
            FROM ML_KPI22_RFM_SEGMENTS WITH (NOLOCK)
            WHERE run_date = (SELECT MAX(run_date) FROM ML_KPI22_RFM_SEGMENTS WITH (NOLOCK))
        """)
        rows = _rows("""
            SELECT TOP 500
                recence_jours AS recence,
                frequence_commandes AS frequence,
                montant_total AS montant,
                segment_label AS segment
            FROM ML_KPI22_RFM_SEGMENTS WITH (NOLOCK)
            WHERE run_date = (SELECT MAX(run_date) FROM ML_KPI22_RFM_SEGMENTS WITH (NOLOCK))
        """)
        return {
            "silhouette": _num(meta.silhouette_score) if meta else 0,
            "inertia": _num(meta.inertia) if meta else 0,
            "segments": [
                {
                    "recence": _num(r.recence),
                    "frequence": _num(r.frequence),
                    "montant": _num(r.montant),
                    "segment": r.segment,
                }
                for r in rows
            ],
        }
    except Exception:
        return {"silhouette": 0, "inertia": 0, "segments": []}


@app.get("/api/dashboard/kpis")
def get_dashboard_kpis(
    year: int = None,
    quarter: str = None,
    month: str = None,
    region: str = None,
    famille: str = None,
    segment: str = None,
    depot: str = None,
    source: str = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=None, # year handled by Python
        quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "famille": "fa", "segment": "s"}
    )
    
    if not year:
        # Get the latest year with data
        year_res = _row("""
            SELECT MAX(d.annee) AS annee
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DATE d ON d.id_date = f.id_date
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            WHERE dom.DO_Domaine = 0
        """)
        year = year_res.annee if year_res else datetime.now().year

    # Get the latest active month for that year
    meta = _row("""
        WITH monthly_stats AS (
            SELECT AVG(CAST(row_cnt AS FLOAT)) AS avg_rows
            FROM (
                SELECT d2.annee, d2.mois, COUNT(*) AS row_cnt
                FROM FAIT_LIGNES_VENTE f2
                JOIN DIM_DOMAINE dom2 ON dom2.id_domaine = f2.id_domaine
                JOIN DIM_DATE d2 ON d2.id_date = f2.id_date
                WHERE dom2.DO_Domaine = 0
                GROUP BY d2.annee, d2.mois
            ) counts
        )
        SELECT
            MAX(CASE WHEN cnt.row_cnt >= ms.avg_rows * 0.5 THEN d.mois ELSE 0 END) AS latest_month
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        JOIN DIM_DATE d ON d.id_date = f.id_date
        CROSS JOIN monthly_stats ms
        JOIN (
            SELECT d2.annee, d2.mois, COUNT(*) AS row_cnt
            FROM FAIT_LIGNES_VENTE f2
            JOIN DIM_DOMAINE dom2 ON dom2.id_domaine = f2.id_domaine
            JOIN DIM_DATE d2 ON d2.id_date = f2.id_date
            WHERE dom2.DO_Domaine = 0
            GROUP BY d2.annee, d2.mois
        ) cnt ON cnt.annee = d.annee AND cnt.mois = d.mois
        WHERE dom.DO_Domaine = 0
        AND d.annee = :year
    """, {"year": year})
    
    latest_month = meta.latest_month if meta and meta.latest_month else 12
    latest_year = year

    # Now the main query is much simpler!
    sql = f"""
        SELECT
            SUM(CASE WHEN d.annee = :latest_year THEN f.DL_MontantHT ELSE 0 END) AS ca_total,
            SUM(CASE WHEN d.annee = :latest_year - 1
                AND d.mois <= :latest_month
                THEN f.DL_MontantHT ELSE 0 END) AS ca_total_n1,
            COUNT(DISTINCT CASE WHEN d.annee = :latest_year AND f.DO_Piece_hash IS NOT NULL THEN
                CONCAT(f.DO_Piece_hash, '-', COALESCE(f.id_type_doc, 0))
            END) AS nb_commandes,
            COUNT(DISTINCT CASE WHEN d.annee = :latest_year - 1 AND d.mois <= :latest_month AND f.DO_Piece_hash IS NOT NULL THEN
                CONCAT(f.DO_Piece_hash, '-', COALESCE(f.id_type_doc, 0))
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
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
        LEFT JOIN DIM_CLIENT c ON c.id_client = f.id_client
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE dom.DO_Domaine = 0
        AND d.annee IN (:latest_year, :latest_year - 1)
        {filt_sql}
    """
    params = {"latest_year": latest_year, "latest_month": latest_month}
    params.update(filt_params)
    row = _row(sql, params)
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
    year: int = None,
    quarter: str = None,
    month: str = None,
    region: str = None,
    famille: str = None,
    segment: str = None,
    depot: str = None,
    source: str = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=None, # handled by year_filter
        quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "famille": "fa", "segment": "s"}
    )
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
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            JOIN DIM_DATE d ON d.id_date = f.id_date
            LEFT JOIN DIM_CLIENT c ON c.id_client = f.id_client
            LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
            LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
            LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
            WHERE dom.DO_Domaine = 0
            {year_filter}
            {filt_sql}
            GROUP BY d.annee, d.mois
        ),
        latest AS (
            SELECT 
                MAX(m.annee) AS latest_year,
                MAX(CASE WHEN m.row_cnt >= ms.avg_rows * 0.5 THEN m.mois ELSE 0 END) AS latest_full_month
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
            WHERE m.row_cnt >= ms.avg_rows * 0.5
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
            AND prev.row_cnt >= ms.avg_rows * 0.1
        WHERE r.annee = latest.latest_year
        ORDER BY r.annee, r.mois
    """
    rows = _rows(sql, filt_params)
    
    # Calculate recovery rate by month
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
    year: int = None,
    quarter: str = None,
    month: str = None,
    region: str = None,
    famille: str = None,
    segment: str = None,
    depot: str = None,
    source: str = None,
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
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        LEFT JOIN DIM_CLIENT c ON c.id_client = f.id_client
        LEFT JOIN DIM_ARTICLE a  ON a.id_article  = f.id_article
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE dom.DO_Domaine = 0
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


@app.get("/api/ventes/ca-by-region")
def get_ca_by_region(
    year: int = None,
    quarter: str = None,
    month: str = None,
    region: str = None,
    famille: str = None,
    segment: str = None,
    depot: str = None,
    source: str = None,
):
    filt_sql, filt_params = _build_dynamic_filters(
        year=None, quarter=quarter, month=month, region=region, famille=famille,
        segment=segment, depot=depot, source=source,
        aliases={"date": "d", "client": "c", "famille": "fa", "segment": "s"}
    )
    year_clause = f"AND d.annee = {year}" if year else "AND d.annee = latest.latest_year"
    sql = f"""
        WITH latest AS (
            SELECT COALESCE(MAX(d.annee), YEAR(GETDATE())) AS latest_year
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            JOIN DIM_DATE d ON d.id_date = f.id_date
            WHERE dom.DO_Domaine = 0
        )
        SELECT 
            COALESCE(NULLIF(c.gouvernorat, ''), 'Autre') AS name,
            SUM(f.DL_MontantHT)            AS ca,
            COUNT(DISTINCT f.id_client)    AS clients,
            COUNT(DISTINCT f.DO_Piece_hash) AS commandes
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_CLIENT  c ON c.id_client  = f.id_client
        LEFT JOIN DIM_DATE    d ON d.id_date    = f.id_date
        LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        CROSS JOIN latest
        WHERE dom.DO_Domaine = 0
        AND {year_clause[4:] if year_clause.startswith('AND ') else year_clause}
        {filt_sql}
        GROUP BY COALESCE(NULLIF(c.gouvernorat, ''), 'Autre')
        HAVING SUM(f.DL_MontantHT) > 0
        ORDER BY ca DESC
    """
    params = {"year": year} if year else {}
    params.update(filt_params)
    return [
        {
            "name": r.name,
            "ca": _num(r.ca),
            "clients": _int(r.clients),
            "commandes": _int(r.commandes),
        }
        for r in _rows(sql, params)
    ]


@app.get("/api/tresorerie/summary")
def get_tresorerie_summary():
    # Deduplicate by RT_Num (one payment may appear multiple times due to
    # the LEFT JOIN with F_LigneBordereauRemise in the ETL extract).
    # Restrict to client receipts only (id_client IS NOT NULL).
    sql = """
        WITH deduped AS (
            SELECT
                RT_Num,
                MAX(RT_Montant)         AS RT_Montant,
                MAX(DR_Regle)           AS DR_Regle,
                MAX(delai_reel_jours)   AS delai_reel_jours
            FROM FAIT_REGLEMENTS
            WHERE RT_Num IS NOT NULL AND id_client IS NOT NULL
            GROUP BY RT_Num
        )
        SELECT
            SUM(CASE WHEN DR_Regle = 1 THEN RT_Montant ELSE 0 END) AS encaissements,
            SUM(CASE WHEN DR_Regle = 0 THEN RT_Montant ELSE 0 END) AS impayes,
            AVG(CAST(delai_reel_jours AS FLOAT)) AS delai_moyen
        FROM deduped
    """
    row = _row(sql)
    encaissements = _num(row.encaissements)
    impayes = _num(row.impayes)
    total = encaissements + impayes
    return {
        "encaissements": encaissements,
        "impayes": impayes,
        "delai_moyen": round(_num(row.delai_moyen)),
        "taux_recouvrement": (encaissements / total * 100) if total else 0,
    }


@app.get("/api/tresorerie/impayes")
def get_impayes():
    sql = """
        WITH buckets AS (
            SELECT DISTINCT
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delai_reel_jours) OVER ()
                    AS p50,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delai_reel_jours) OVER () * 6
                    AS p50x6,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delai_reel_jours) OVER () * 18
                    AS p50x18
            FROM FAIT_REGLEMENTS
            WHERE delai_reel_jours > 0 AND DR_Regle = 0
        ),
        deduped AS (
            SELECT
                id_client,
                RT_Num,
                MAX(RT_Montant) AS RT_Montant,
                MAX(delai_reel_jours) AS delai_reel_jours,
                MAX(DR_Regle) AS DR_Regle
            FROM FAIT_REGLEMENTS
            WHERE id_client IS NOT NULL
            GROUP BY id_client, RT_Num
        )
        SELECT
            c.CT_Num_code,
            c.CT_Intitule,
            SUM(r.RT_Montant) AS montant_impaye,
            MAX(r.delai_reel_jours) AS anciennete,
            MAX(b.p50) AS seuil_attention,
            MAX(b.p50x6) AS seuil_urgent,
            MAX(b.p50x18) AS seuil_critique
        FROM deduped r
        JOIN DIM_CLIENT c ON c.id_client = r.id_client
        CROSS JOIN buckets b
        WHERE r.DR_Regle = 0
        GROUP BY c.CT_Num_code, c.CT_Intitule
        HAVING SUM(r.RT_Montant) > 0
        ORDER BY montant_impaye DESC
    """
    return [
        {
            "client": r.CT_Intitule or f"Client {r.CT_Num_code}",
            "code": str(r.CT_Num_code),
            "montant": _num(r.montant_impaye),
            "montantImpaye": _num(r.montant_impaye),
            "anciennete": _int(r.anciennete),
            "region": "",
            "representant": "",
            "dateEcheance": "",
            "statut": (
                "Critique" if _int(r.anciennete) > _num(r.seuil_critique)
                else "Urgent" if _int(r.anciennete) > _num(r.seuil_urgent)
                else "Attention" if _int(r.anciennete) > _num(r.seuil_attention)
                else "Normal"
            ),
        }
        for r in _rows(sql)
    ]


@app.get("/api/tresorerie/impayes-fournisseurs")
def get_impayes_fournisseurs():
    sql = """
        SELECT 
            f.CT_Num_code,
            f.CT_Intitule,
            SUM(r.RT_Montant) AS montant_impaye,
            MAX(COALESCE(r.delai_reel_jours, DATEDIFF(day, dt_pai.date_val, GETDATE()))) AS anciennete,
            MAX(r.RT_NbJour) AS delai_contractuel
        FROM FAIT_REGLEMENTS r
        JOIN DIM_FOURNISSEUR f ON f.id_fournisseur = r.id_fournisseur
        LEFT JOIN DIM_DATE dt_pai ON dt_pai.id_date = r.id_date_paiement
        WHERE r.DR_Regle = 0
        AND r.id_fournisseur IS NOT NULL
        GROUP BY f.CT_Num_code, f.CT_Intitule
        HAVING SUM(r.RT_Montant) > 0
        ORDER BY montant_impaye DESC
    """
    return [
        {
            "fournisseur": r.CT_Intitule if r.CT_Intitule else f"Fournisseur {r.CT_Num_code}",
            "montant": _num(r.montant_impaye),
            "delaiEffectif": _int(r.anciennete),
            "delaiContractuel": _int(r.delai_contractuel),
            "etat": (
                "Contentieux" if _int(r.anciennete) > 90
                else "Partiel" if _int(r.anciennete) > 30
                else "En cours"
            ),
        }
        for r in _rows(sql)
    ]

@app.get("/api/tresorerie/encaissements-by-mode")
def get_encaissements_by_mode():
    sql = """
        WITH deduped AS (
            SELECT
                id_client,
                id_fournisseur,
                id_mode_reg,
                DR_ModeReg,
                DR_Regle,
                RT_Rapproche,
                RT_Montant
            FROM FAIT_REGLEMENTS
        )
        SELECT
            COALESCE(m.libelle_mode_reg, CONCAT('Mode ', r.DR_ModeReg)) AS mode,
            SUM(CASE WHEN r.id_client IS NOT NULL THEN r.RT_Montant ELSE 0 END) AS mag,
            SUM(CASE WHEN r.id_fournisseur IS NOT NULL THEN r.RT_Montant ELSE 0 END) AS grt,
            AVG(CASE WHEN r.RT_Rapproche = 1 THEN 100.0 ELSE 0.0 END) AS rapprochement
        FROM deduped r
        LEFT JOIN DIM_MODE_REGLEMENT m ON m.id_mode_reg = r.id_mode_reg
        WHERE r.DR_Regle = 1
        GROUP BY m.libelle_mode_reg, r.DR_ModeReg
        ORDER BY
            SUM(CASE WHEN r.id_client IS NOT NULL THEN r.RT_Montant ELSE 0 END)
        + SUM(CASE WHEN r.id_fournisseur IS NOT NULL THEN r.RT_Montant ELSE 0 END)
        DESC
    """
    return [
        {
            "mode": r.mode,
            "mag": _num(r.mag),
            "grt": _num(r.grt),
            "rapprochement": round(_num(r.rapprochement)),
        }
        for r in _rows(sql)
    ]


@app.get("/api/tresorerie/aging")
def get_aging():

    sql = """
        SELECT 
            COALESCE(MAX(c.CT_Intitule), CONVERT(VARCHAR(30), c.CT_Num_code)) AS client,
            SUM(CASE WHEN r.bucket_impaye = 0 THEN r.RT_Montant ELSE 0 END) AS b0,
            SUM(CASE WHEN r.bucket_impaye = 1 THEN r.RT_Montant ELSE 0 END) AS b1,
            SUM(CASE WHEN r.bucket_impaye = 2 THEN r.RT_Montant ELSE 0 END) AS b2,
            SUM(CASE WHEN r.bucket_impaye = 3 THEN r.RT_Montant ELSE 0 END) AS b3
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
        WHERE r.id_client IS NOT NULL
        AND r.DR_Regle = 0
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
        for r in _rows(sql)
    ]


@app.get("/api/produits/stock-alerts")
def get_stock_alerts():
    sql = """
        SELECT 
            a.AR_Ref_code,
            a.AR_Ref,
            a.AR_Design,
            SUM(f.AS_QteSto)     AS AS_QteSto,
            MAX(f.AS_QteMini)    AS AS_QteMini,
            MAX(f.en_rupture)    AS en_rupture,
            MAX(f.ratio_tension) AS ratio_tension,
            MAX(f.qte_vendue_365j) AS qte_vendue_365j
        FROM FAIT_ECRITURES f
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = f.id_type_ligne
        JOIN DIM_ARTICLE a ON a.id_article = f.id_article
        WHERE tl.type_ligne = 4
        AND f.en_rupture = 1
        AND (f.AS_QteMini > 0 OR COALESCE(f.qte_vendue_365j, 0) > 0)
        AND f.AS_QteSto IS NOT NULL
        AND f.AS_QteSto >= 0
        GROUP BY a.AR_Ref_code, a.AR_Ref, a.AR_Design
        ORDER BY MAX(COALESCE(f.qte_vendue_365j, 0)) DESC
    """
    alerts = []
    for r in _rows(sql):
        stock = _num(r.AS_QteSto)
        seuil = _num(r.AS_QteMini)
        ratio = _num(r.ratio_tension)
        alerts.append({
            "article": r.AR_Ref if r.AR_Ref else f"ART-{r.AR_Ref_code}",
            "designation": r.AR_Design if r.AR_Design else f"Article {r.AR_Ref_code}",
            "stockActuel": stock,
            "seuil": seuil,
            "dateRupture": "",
            "famille": "",
            "fournisseur": "",
            "priorite": (
                "CRITIQUE" if stock <= seuil
                else "URGENT" if ratio >= SEUIL_TENSION_STOCK
                else "ATTENTION"
            ),
            "ratioTension": ratio,
        })
    return alerts


@app.get("/api/produits/articles")
def get_articles():
    sql = """
        WITH sales AS (
            SELECT
                id_article,
                COALESCE(SUM(DL_Qte), 0) AS qte_vendue,
                COALESCE(SUM(DL_MontantHT), 0) AS ca
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            WHERE dom.DO_Domaine = 0
            GROUP BY id_article
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
            JOIN DIM_TYPE_LIGNE tl
            ON tl.id_type_ligne = e.id_type_ligne
            AND tl.type_ligne = 4
            WHERE e.AS_QteSto IS NOT NULL
            GROUP BY e.id_article
        )
        SELECT 
        a.AR_Ref_code,
        a.AR_Ref,
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
            "code": r.AR_Ref if r.AR_Ref else f"ART-{r.AR_Ref_code}",
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
        for r in _rows(sql)
    ]

@app.get("/api/acteurs/clients")
def get_clients():
    sql = """
        SELECT 
            c.CT_Num_code,
            COALESCE(c.CT_Intitule, CONVERT(VARCHAR(30), c.CT_Num_code)) AS nom,
            COALESCE(s.libelle_segment, 'Sans segment') AS segment,
            SUM(v.DL_MontantHT) AS ca_total,
            COUNT(DISTINCT v.DO_Piece_hash) AS nb_commandes,
            FORMAT(MAX(d.date_val), 'yyyy-MM-dd') AS derniere_commande,
            c.CT_SoldeActuel AS solde_impaye,
            c.CT_Sommeil AS sommeil
        FROM DIM_CLIENT c
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        LEFT JOIN FAIT_LIGNES_VENTE v ON v.id_client = c.id_client
        LEFT JOIN DIM_DOMAINE dom ON dom.id_domaine = v.id_domaine
        LEFT JOIN DIM_DATE d ON d.id_date = v.id_date
        WHERE (dom.DO_Domaine = 0 OR dom.DO_Domaine IS NULL)
        GROUP BY c.CT_Num_code, s.libelle_segment, c.CT_SoldeActuel, c.CT_Sommeil, c.CT_Intitule
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
            "nouveau": _int(r.nb_commandes) == 1,  # client with only one order is new
        }
        for r in _rows(sql)
    ]


@app.get("/api/acteurs/rfm")
def get_acteurs_rfm():
    sql = """
        SELECT 
            c.CT_Num_code,
            c.CT_Intitule,
            COALESCE(s.libelle_segment, 'Sans segment') AS segment,
            c.rfm_recence_jours,
            c.rfm_frequence,
            c.rfm_montant_12m
        FROM DIM_CLIENT c
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE c.rfm_montant_12m IS NOT NULL
        OR c.rfm_frequence IS NOT NULL
        ORDER BY COALESCE(c.rfm_montant_12m, 0) DESC
    """
    return [
        {
            "code": str(r.CT_Num_code),
            "name": r.CT_Intitule or f"Client {r.CT_Num_code}",
            "segment": r.segment,
            "frequence": _int(r.rfm_frequence),
            "recence": _int(r.rfm_recence_jours, 999),
            "montant": _num(r.rfm_montant_12m),
        }
        for r in _rows(sql)
    ]


@app.get("/api/acteurs/aging")
def get_acteurs_aging():
    sql = """
        SELECT 
            COALESCE(CONVERT(VARCHAR(30), c.CT_Num_code), 'Client') AS client,
            SUM(CASE WHEN r.bucket_impaye = 0 THEN r.RT_Montant ELSE 0 END) AS b0,
            SUM(CASE WHEN r.bucket_impaye = 1 THEN r.RT_Montant ELSE 0 END) AS b1,
            SUM(CASE WHEN r.bucket_impaye = 2 THEN r.RT_Montant ELSE 0 END) AS b2,
            SUM(CASE WHEN r.bucket_impaye = 3 THEN r.RT_Montant ELSE 0 END) AS b3
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
        WHERE r.id_client IS NOT NULL
        AND r.DR_Regle = 0
        GROUP BY c.CT_Num_code
        ORDER BY b3 DESC
    """
    return [
        {
            "clientCode": str(r.client),
            "client": f"C{r.client}",
            "0-30j": _num(r.b0),
            "31-60j": _num(r.b1),
            "61-90j": _num(r.b2),
            ">90j": _num(r.b3),
        }
        for r in _rows(sql)
    ]


@app.get("/api/acteurs/fournisseurs")
def get_acteurs_fournisseurs():
    sql = """
        SELECT 
            f.CT_Num_code,
            f.CT_Intitule,
            f.CT_Encours,
            COUNT(a.id_article) AS nb_articles
        FROM DIM_FOURNISSEUR f
        LEFT JOIN DIM_ARTICLE a ON a.id_fournisseur = f.id_fournisseur
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
        for r in _rows(sql)
    ]


@app.get("/api/acteurs/livreurs")
def get_acteurs_livreurs():
    sql = """
        SELECT 
            cl.id_collab,
            SUM(f.DL_MontantHT) AS montant_total,
            COUNT(DISTINCT f.DO_Piece_hash) AS nb_commandes
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_CLIENT cl ON cl.id_client = f.id_client
        WHERE cl.id_collab IS NOT NULL
        GROUP BY cl.id_collab
        ORDER BY montant_total DESC
    """
    return [
        {
            "code": str(r.id_collab),
            "nom": f"Livreur {r.id_collab}",
            "montantTotal": _num(r.montant_total),
            "nbCommandes": _int(r.nb_commandes),
        }
        for r in _rows(sql)
    ]


@app.get("/api/acteurs/fournisseur-concentration")
def get_fournisseur_concentration():
    sql = """
        WITH achats AS (
            SELECT
                f.id_fournisseur,
                f.CT_Num_code,
                f.CT_Intitule,
                SUM(flv.DL_MontantHT) AS montant_achat,
                COUNT(DISTINCT flv.id_article) AS nb_articles_achetes
            FROM FAIT_LIGNES_VENTE flv
            JOIN DIM_DOMAINE dom ON dom.id_domaine = flv.id_domaine
            JOIN DIM_ARTICLE a ON a.id_article = flv.id_article
            JOIN DIM_FOURNISSEUR f ON f.id_fournisseur = a.id_fournisseur
            WHERE dom.DO_Domaine = 1
            GROUP BY f.id_fournisseur, f.CT_Num_code, f.CT_Intitule
        ),
        total AS (
            SELECT SUM(montant_achat) AS total_achats
            FROM achats
        ),
        hhi_threshold AS (
            SELECT DISTINCT
                POWER(
                    PERCENTILE_CONT(0.8) WITHIN GROUP (ORDER BY montant_achat) OVER ()
                    / NULLIF(total_achats, 0),
                2) AS seuil
            FROM achats
            CROSS JOIN total
        )
        SELECT
            a.CT_Num_code,
            a.CT_Intitule,
            a.montant_achat,
            a.nb_articles_achetes,
            COALESCE(art_count.nb_articles_catalogue, 0) AS nb_articles_catalogue,
            POWER(a.montant_achat / NULLIF(t.total_achats, 0), 2) AS hhi_contribution,
            h.seuil AS hhi_threshold
        FROM achats a
        CROSS JOIN total t
        CROSS JOIN hhi_threshold h
        LEFT JOIN (
            SELECT id_fournisseur, COUNT(*) AS nb_articles_catalogue
            FROM DIM_ARTICLE
            GROUP BY id_fournisseur
        ) art_count ON art_count.id_fournisseur = a.id_fournisseur
        ORDER BY a.montant_achat DESC
    """
    return [
        {
            "fournisseur": r.CT_Intitule if r.CT_Intitule else f"Fournisseur {r.CT_Num_code}",
            "nbArticles": _int(r.nb_articles_catalogue),
            "nbArticlesAchetes": _int(r.nb_articles_achetes),
            "montantAchat": _num(r.montant_achat),
            "hhi": round(_num(r.hhi_contribution), 4),
            "risqueConcentration": _num(r.hhi_contribution) > _num(r.hhi_threshold),
        }
        for r in _rows(sql)
    ]


@app.get("/api/banque/rapprochement")
def get_banque_rapprochement():
    sql = """
        WITH deduped AS (
            SELECT
                RT_Num,
                MAX(RT_Montant)       AS RT_Montant,
                MAX(DR_Regle)         AS DR_Regle,
                MAX(RT_Rapproche)     AS RT_Rapproche,
                MAX(id_banque)        AS id_banque,
                MAX(LB_NbJour)        AS LB_NbJour,
                MAX(LB_Agios)         AS LB_Agios,
                MAX(BR_TauxAgios)     AS BR_TauxAgios,
                MAX(id_date_paiement) AS id_date_paiement,
                MAX(id_date_echeance) AS id_date_echeance
            FROM FAIT_REGLEMENTS
            WHERE RT_Num IS NOT NULL AND id_client IS NOT NULL
            GROUP BY RT_Num
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
        for r in _rows(sql)
    ]


@app.get("/api/banque/rapprochement-breakdown")
def get_banque_rapprochement_breakdown():
    sql = """
        SELECT 
            m.libelle_mode_reg,
            SUM(COALESCE(r.RT_Montant, 0)) AS total_montant
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_MODE_REGLEMENT m ON m.id_mode_reg = r.id_mode_reg
        WHERE COALESCE(r.RT_Rapproche, 0) = 0 AND COALESCE(r.DR_Regle, 0) = 0
        AND r.id_client IS NOT NULL
        GROUP BY m.libelle_mode_reg
    """
    totals = {"Chèque": 0.0, "Traite": 0.0, "Virement": 0.0}
    for r in _rows(sql):
        mode_label = r.libelle_mode_reg or ""
        if "Ch" in mode_label or "ch" in mode_label or "Chéque" in mode_label:
            totals["Chèque"] += _num(r.total_montant)
        elif "Trait" in mode_label or "trait" in mode_label or "LCR" in mode_label:
            totals["Traite"] += _num(r.total_montant)
        elif "Vir" in mode_label or "vir" in mode_label:
            totals["Virement"] += _num(r.total_montant)

    sql_tx = """
        SELECT TOP 25
            r.RT_Num,
            m.libelle_mode_reg,
            COALESCE(r.RT_Montant, 0) AS montant,
            COALESCE(c.CT_Intitule, 'Client Divers') AS client
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_MODE_REGLEMENT m ON m.id_mode_reg = r.id_mode_reg
        LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
        WHERE COALESCE(r.RT_Rapproche, 0) = 0 AND COALESCE(r.DR_Regle, 0) = 0
        AND r.id_client IS NOT NULL
        ORDER BY COALESCE(r.RT_Montant, 0) DESC
    """
    transactions = []
    for r in _rows(sql_tx):
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
def get_caisses():
    sql = """
        WITH seuil AS (
            -- Average solde across all caisses as minimum threshold
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
        CROSS JOIN seuil s
        GROUP BY c.CA_Numero_code
        ORDER BY c.CA_Numero_code
    """
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
            "seuilMin": _num(r.seuil_min),  # computed from real data
            "depot": depot_map.get(r.CA_Numero_code, "Dépôt Central"),
        }
        for r in _rows(sql)
    ]

@app.get("/api/caisse/flux-daily")
def get_caisse_flux_daily():
    sql = """
        SELECT 
            d.date_val,
            SUM(COALESCE(e.MC_Credit, 0)) AS credit,
            SUM(COALESCE(e.MC_Debit, 0))  AS debit
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = e.id_type_ligne
        WHERE tl.type_ligne = 3
        AND d.date_val IS NOT NULL
        GROUP BY d.date_val
        ORDER BY d.date_val DESC
    """
    rows = list(reversed(_rows(sql)))
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
def get_caisse_mouvements_by_type():
    sql = """
        SELECT
            COALESCE(tm.libelle_type_mvt, CONCAT('Mouvement ', tm.MC_TypeMvt)) AS name,
            SUM(ABS(COALESCE(e.MC_Credit, 0)) + ABS(COALESCE(e.MC_Debit, 0))) AS value
        FROM FAIT_ECRITURES e
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = e.id_type_ligne
        LEFT JOIN DIM_TYPE_MVT_CAISSE tm ON tm.id_type_mvt = e.id_type_mvt_caisse
        WHERE tl.type_ligne = 3
        GROUP BY tm.libelle_type_mvt, tm.MC_TypeMvt
        ORDER BY SUM(ABS(COALESCE(e.MC_Credit, 0)) + ABS(COALESCE(e.MC_Debit, 0))) DESC
    """
    rows = _rows(sql)
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
def get_fiscalite_kpis():
    row = _row(
        """
        SELECT
            SUM(CASE WHEN tl.type_ligne IN (1, 2) THEN 1 ELSE 0 END) AS nb_ecritures,
            SUM(CASE WHEN tl.type_ligne = 2 AND t.type_tva = 1 THEN COALESCE(e.RT_Montant01, 0) ELSE 0 END) AS tva_collectee,
            SUM(CASE WHEN tl.type_ligne = 2 AND t.type_tva = 2 THEN COALESCE(e.RT_Montant01, 0) ELSE 0 END) AS tva_deductible,
            SUM(CASE
                WHEN tl.type_ligne = 1
                AND ABS(COALESCE(e.EC_Montant, 0)) >= (
    SELECT AVG(ABS(EC_Montant)) + STDEV(ABS(EC_Montant))
    FROM FAIT_ECRITURES
    WHERE EC_Montant IS NOT NULL
)
                THEN 1 ELSE 0
            END) AS anomalies
        FROM FAIT_ECRITURES e
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = e.id_type_ligne
        LEFT JOIN DIM_TYPE_TVA t ON t.id_type_tva = e.id_type_tva
        """
    )
    debit_credit = _row(
        """
        SELECT
            SUM(CASE WHEN s.EC_Sens = 0 THEN ABS(e.EC_Montant) ELSE 0 END) AS debit,
            SUM(CASE WHEN s.EC_Sens = 1 THEN ABS(e.EC_Montant) ELSE 0 END) AS credit
        FROM FAIT_ECRITURES e
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = e.id_type_ligne
        LEFT JOIN DIM_SENS_ECRITURE s ON s.id_sens = e.id_sens_ecriture
        WHERE tl.type_ligne IN (1, 2)
        """
    )
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


@app.get("/api/fiscalite/journaux")
def get_fiscalite_journaux():
    sql = """
        SELECT 
            COALESCE(CONVERT(VARCHAR(30), j.JO_Num_code), 'Sans journal') AS journal,
            SUM(CASE WHEN s.EC_Sens = 0 THEN ABS(e.EC_Montant) ELSE 0 END) AS debit,
            SUM(CASE WHEN s.EC_Sens = 1 THEN ABS(e.EC_Montant) ELSE 0 END) AS credit
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_JOURNAL j ON j.id_journal = e.id_journal
        LEFT JOIN DIM_SENS_ECRITURE s ON s.id_sens = e.id_sens_ecriture
        GROUP BY j.JO_Num_code
        ORDER BY
            SUM(CASE WHEN s.EC_Sens = 0 THEN ABS(e.EC_Montant) ELSE 0 END)
        + SUM(CASE WHEN s.EC_Sens = 1 THEN ABS(e.EC_Montant) ELSE 0 END)
        DESC
    """
    return [{"journal": f"Journal {r.journal}", "debit": _num(r.debit), "credit": _num(r.credit)} for r in _rows(sql)]


@app.get("/api/fiscalite/tva-by-month")
def get_fiscalite_tva_by_month():
    sql = """
        SELECT
            d.mois AS month_num,
            SUM(CASE WHEN tl.type_ligne = 2 AND t.type_tva = 1 THEN COALESCE(e.RT_Montant01, 0) ELSE 0 END) AS collectee,
            SUM(CASE WHEN tl.type_ligne = 2 AND t.type_tva = 2 THEN COALESCE(e.RT_Montant01, 0) ELSE 0 END) AS deductible
        FROM FAIT_ECRITURES e
        JOIN DIM_DATE d ON d.id_date = e.id_date
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = e.id_type_ligne
        LEFT JOIN DIM_TYPE_TVA t ON t.id_type_tva = e.id_type_tva
        WHERE tl.type_ligne = 2
        AND e.RT_Montant01 IS NOT NULL
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
        for r in _rows(sql)
    ]


@app.get("/api/fiscalite/ecritures")
def get_fiscalite_ecritures():
    sql = """
        SELECT 
            FORMAT(d.date_val, 'yyyy-MM-dd') AS date_val,
            e.EC_No,
            COALESCE(CONVERT(VARCHAR(30), j.JO_Num_code), '') AS journal_code,
            e.CG_Num,
            e.EC_Montant,
            s.EC_Sens AS sens
        FROM FAIT_ECRITURES e
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = e.id_type_ligne
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        LEFT JOIN DIM_JOURNAL j ON j.id_journal = e.id_journal
        LEFT JOIN DIM_SENS_ECRITURE s ON s.id_sens = e.id_sens_ecriture
        WHERE tl.type_ligne IN (1, 2)
        AND e.EC_No IS NOT NULL
        AND e.EC_Montant IS NOT NULL
        AND e.EC_Montant <> 0
        ORDER BY e.id_ecriture DESC
    """
    return [
        {
            "date": _date_str(r.date_val) if r.date_val else "",
            "numPiece": f"EC-{r.EC_No}" if r.EC_No else "",
            "journal": f"Journal {r.journal_code}" if r.journal_code else "—",
            "compte": str(r.CG_Num) if r.CG_Num else "—",
            "libelle": f"Écriture {r.EC_No}" if r.EC_No else "—",
            "debit": _num(r.EC_Montant) if _int(r.sens) == 0 else 0,
            "credit": _num(r.EC_Montant) if _int(r.sens) == 1 else 0,
            "solde": _num(r.EC_Montant) * (1 if _int(r.sens) == 0 else -1),
        }
        for r in _rows(sql)
    ]

@app.get("/api/fiscalite/anomalies")
def get_fiscalite_anomalies():
    sql = """
        WITH stats AS (
            -- Compute mean and standard deviation from real data
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
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = e.id_type_ligne
        CROSS JOIN stats
        WHERE e.EC_Montant IS NOT NULL
        AND tl.type_ligne IN (1, 2)
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
        for r in _rows(sql)
    ]

@app.get("/api/fiscalite/balance-by-month")
def get_fiscalite_balance_by_month():
    sql = """
        SELECT
            d.mois AS month_num,
            SUM(CASE WHEN s.EC_Sens = 0 THEN ABS(e.EC_Montant) ELSE 0 END) AS debit,
            SUM(CASE WHEN s.EC_Sens = 1 THEN ABS(e.EC_Montant) ELSE 0 END) AS credit
        FROM FAIT_ECRITURES e
        JOIN DIM_DATE d ON d.id_date = e.id_date
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = e.id_type_ligne
        LEFT JOIN DIM_SENS_ECRITURE s ON s.id_sens = e.id_sens_ecriture
        WHERE tl.type_ligne IN (1, 2)
        GROUP BY d.mois
        ORDER BY d.mois
    """
    return [
        {
            "month": MONTHS[r.month_num - 1],
            "debit": _num(r.debit),
            "credit": _num(r.credit),
            "ecart": _num(r.debit) - _num(r.credit),
        }
        for r in _rows(sql)
    ]





@app.get("/api/notifications")
def get_notifications():
    try:
        stock = [a for a in get_stock_alerts() if a["priorite"] == "CRITIQUE"]
    except Exception as e:
        logging.getLogger(__name__).warning(f"notifications: stock_alerts failed: {e}")
        stock = []
    try:
        impayes = [i for i in get_impayes() if i["anciennete"] > 90]
    except Exception as e:
        logging.getLogger(__name__).warning(f"notifications: impayes failed: {e}")
        impayes = []
    items = []
    for a in stock:
        items.append({
            "id": f"stock-{a['article']}",
            "type": "stock",
            "severity": "critical" if a["priorite"] == "CRITIQUE" else "warning",
            "title": a["designation"],
            "message": f"Stock critique - {a['stockActuel']:.0f} unites restantes",
            "meta": a["famille"],
            "time": "",
        })
    for i in impayes:
        items.append({
            "id": f"pay-{i['code']}-{i['anciennete']}",
            "type": "payment",
            "severity": "critical" if i["anciennete"] > 90 else "warning",
            "title": i["client"],
            "message": f"Impaye {i['anciennete']}j - {i['montantImpaye']:.0f} DT",
            "meta": i["region"],
            "time": i["dateEcheance"] or "",
        })
    return items


@app.get("/api/search")
def search(q: str = ""):
    q = q.strip()[:100]  # limit length to prevent abuse
    if not q:
        return {"clients": [], "articles": [], "ecritures": [], "fournisseurs": []}
    needle = f"%{q}%"
    clients = _rows(
        "SELECT  CT_Num_code, CT_SoldeActuel, CT_Intitule FROM DIM_CLIENT "
        "WHERE CONVERT(VARCHAR(30), CT_Num_code) LIKE :q OR CT_Intitule LIKE :q ORDER BY CT_Num_code",
        {"q": needle},
    )
    articles = _rows(
        "SELECT  AR_Ref_code, AR_Ref, AR_Design, id_famille FROM DIM_ARTICLE "
        "WHERE CONVERT(VARCHAR(30), AR_Ref_code) LIKE :q OR AR_Ref LIKE :q OR AR_Design LIKE :q ORDER BY AR_Ref_code",
        {"q": needle},
    )
    ecritures = _rows(
        "SELECT  EC_No, CG_Num, EC_Montant FROM FAIT_ECRITURES "
        "WHERE CONVERT(VARCHAR(30), EC_No) LIKE :q OR CONVERT(VARCHAR(30), CG_Num) LIKE :q "
        "ORDER BY id_ecriture DESC",
        {"q": needle},
    )
    fournisseurs = _rows(
        "SELECT  CT_Num_code, CT_Intitule, CT_Encours FROM DIM_FOURNISSEUR "
        "WHERE CONVERT(VARCHAR(30), CT_Num_code) LIKE :q OR CT_Intitule LIKE :q ORDER BY CT_Num_code",
        {"q": needle},
    )
    return {
        "clients": [{"label": r.CT_Intitule or f"Client {r.CT_Num_code}", "subtitle": f"Solde {round(_num(r.CT_SoldeActuel))} DT", "to": "/acteurs"} for r in clients],
        "articles": [{"label": r.AR_Design if r.AR_Design else (r.AR_Ref if r.AR_Ref else f"Article {r.AR_Ref_code}"), "subtitle": f"Famille {r.id_famille or 'N/A'}", "to": "/produits"} for r in articles],
        "ecritures": [{"label": f"Ecriture {r.EC_No or ''}", "subtitle": f"Compte {r.CG_Num or ''} - {round(_num(r.EC_Montant))} DT", "to": "/fiscalite"} for r in ecritures],
        "fournisseurs": [{"label": r.CT_Intitule if r.CT_Intitule else f"Fournisseur {r.CT_Num_code}", "subtitle": f"Encours {round(_num(r.CT_Encours))} DT", "to": "/acteurs"} for r in fournisseurs],
    }


@app.get("/api/assistant/summary")
def get_assistant_summary():
    result = {
        "kpis": {}, "tresorerie": {}, "articles": [],
        "clients": [], "impayes": [], "stockAlerts": [],
    }
    with DW_ENGINE.connect() as conn:
        def _q(sql, params=None):
            return conn.execute(text(sql), params or {}).fetchall()
        def _qone(sql, params=None):
            return conn.execute(text(sql), params or {}).fetchone()

        try:
            kpi_row = _qone("""
                WITH latest AS (
                    SELECT MAX(d.annee) AS latest_year
                    FROM FAIT_LIGNES_VENTE f
                    JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
                    JOIN DIM_DATE d ON d.id_date = f.id_date
                    WHERE dom.DO_Domaine = 0
                )
                SELECT SUM(f.DL_MontantHT) AS ca_total,
                    COUNT(DISTINCT f.DO_Piece_hash) AS nb_commandes,
                    COUNT(DISTINCT f.id_client) AS nb_clients_actifs,
                    SUM(CASE WHEN a.AR_PrixAch IS NOT NULL AND a.AR_PrixAch > 0
                        AND f.DL_Qte IS NOT NULL
                        AND f.DL_MontantHT > (f.DL_Qte * a.AR_PrixAch)
                        THEN f.DL_MontantHT - (f.DL_Qte * a.AR_PrixAch)
                        ELSE NULL END) AS marge_brute,
                    SUM(CASE WHEN a.AR_PrixAch IS NOT NULL AND a.AR_PrixAch > 0
                        AND f.DL_Qte IS NOT NULL
                        AND f.DL_MontantHT > (f.DL_Qte * a.AR_PrixAch)
                        THEN f.DL_MontantHT
                        ELSE 0 END) AS ca_avec_cout
                FROM FAIT_LIGNES_VENTE f
                JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
                LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
                LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
                CROSS JOIN latest
                WHERE dom.DO_Domaine = 0 AND d.annee = latest.latest_year
            """)
            ca = _num(kpi_row.ca_total)
            ca_avec_cout = _num(kpi_row.ca_avec_cout) if kpi_row.ca_avec_cout is not None else 0
            result["kpis"] = {
                "ca_total": ca,
                "nb_commandes": _int(kpi_row.nb_commandes),
                "nb_clients_actifs": _int(kpi_row.nb_clients_actifs),
                "marge_brute_pct": (_num(kpi_row.marge_brute) / ca_avec_cout * 100) if (ca_avec_cout > 0 and kpi_row.marge_brute is not None) else 0,
                "taux_recouvrement": 0,
            }
        except Exception:
            pass

        try:
            tr = _qone("""
                WITH deduped AS (
                    SELECT
                        RT_Num,
                        MAX(RT_Montant)       AS RT_Montant,
                        MAX(DR_Regle)         AS DR_Regle,
                        MAX(delai_reel_jours) AS delai_reel_jours
                    FROM FAIT_REGLEMENTS
                    WHERE RT_Num IS NOT NULL AND id_client IS NOT NULL
                    GROUP BY RT_Num
                )
                SELECT SUM(CASE WHEN DR_Regle=1 THEN RT_Montant ELSE 0 END) AS enc,
                    SUM(CASE WHEN DR_Regle=0 THEN RT_Montant ELSE 0 END) AS imp,
                    AVG(CAST(delai_reel_jours AS FLOAT)) AS delai
                FROM deduped
            """)
            enc = _num(tr.enc); imp = _num(tr.imp); tot = enc + imp
            result["tresorerie"] = {
                "encaissements": enc, "impayes": imp,
                "delai_moyen": round(_num(tr.delai)),
                "taux_recouvrement": (enc / tot * 100) if tot else 0,
            }
            result["kpis"]["taux_recouvrement"] = result["tresorerie"]["taux_recouvrement"]
        except Exception:
            pass

        try:
            result["articles"] = [
                {"code": f"ART-{r.AR_Ref_code}", "ca": _num(r.ca),
                "stock": _num(r.stock), "dsi": _num(r.dsi_jours)}
                for r in _q("""
                    WITH sales AS (
                        SELECT id_article, COALESCE(SUM(DL_MontantHT),0) AS ca
                        FROM FAIT_LIGNES_VENTE f
                        JOIN DIM_DOMAINE dom ON dom.id_domaine=f.id_domaine
                        WHERE dom.DO_Domaine=0 GROUP BY id_article
                    ),
                    stock AS (
                        SELECT e.id_article, MAX(e.AS_QteSto) AS stock, MAX(e.dsi_jours) AS dsi_jours
                        FROM FAIT_ECRITURES e
                        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne=e.id_type_ligne AND tl.type_ligne=4
                        GROUP BY e.id_article
                    )
                    SELECT a.AR_Ref_code, COALESCE(sales.ca,0) AS ca,
                        stock.stock, stock.dsi_jours
                    FROM DIM_ARTICLE a
                    LEFT JOIN sales ON sales.id_article=a.id_article
                    LEFT JOIN stock ON stock.id_article=a.id_article
                    ORDER BY ca DESC
                """)
            ]
        except Exception:
            pass

        try:
            result["clients"] = [
                {"code": str(r.CT_Num_code), "rfm_recence": _int(r.rfm_recence_jours, 999),
                "rfm_frequence": _int(r.rfm_frequence), "rfm_montant": _num(r.rfm_montant_12m),
                "soldeImpaye": _num(r.solde_impaye)}
                for r in _q("""
                    SELECT  c.CT_Num_code, c.rfm_recence_jours, c.rfm_frequence,
                        c.rfm_montant_12m, c.CT_SoldeActuel AS solde_impaye
                    FROM DIM_CLIENT c
                    ORDER BY c.rfm_montant_12m DESC
                """)
            ]
        except Exception:
            pass

        try:
            result["impayes"] = [
                {"client": r.nom or f"Client {r.CT_Num_code}", "montant": _num(r.montant_impaye),
                "anciennete": _int(r.anciennete)}
                for r in _q("""
                    SELECT  c.CT_Num_code, MAX(c.CT_Intitule) AS nom, SUM(r.RT_Montant) AS montant_impaye,
                        MAX(r.delai_reel_jours) AS anciennete
                    FROM FAIT_REGLEMENTS r JOIN DIM_CLIENT c ON c.id_client=r.id_client
                    WHERE r.DR_Regle=0 AND r.id_client IS NOT NULL
                    GROUP BY c.CT_Num_code
                    HAVING SUM(r.RT_Montant)>0 ORDER BY montant_impaye DESC
                """)
            ]
        except Exception:
            pass

        try:
            result["stockAlerts"] = [
                {"article": f"ART-{r.AR_Ref_code}", "stockActuel": _num(r.AS_QteSto),
                "seuil": _num(r.AS_QteMini), "ratioTension": _num(r.ratio_tension)}
                for r in _q("""
                    SELECT  a.AR_Ref_code, f.AS_QteSto, f.AS_QteMini, f.ratio_tension
                    FROM FAIT_ECRITURES f
                    JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne=f.id_type_ligne
                    JOIN DIM_ARTICLE a ON a.id_article=f.id_article
                    WHERE tl.type_ligne=4 AND f.en_rupture=1
                    AND f.AS_QteSto IS NOT NULL AND f.ratio_tension IS NOT NULL
                    ORDER BY f.ratio_tension DESC
                """)
            ]
        except Exception:
            pass

    return result




class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]

_FINANCIAL_KEYWORDS = {
    "ca", "chiffre", "client", "clients", "stock", "stocks", "impaye", "impayes",
    "tresorerie", "marge", "vente", "ventes", "article", "articles", "kpi",
    "analyse", "analyser", "donnee", "donnees", "rapport",
}
_CASUAL_CA_PHRASES = {"ca va", "comment ca va", "ca marche", "ca roule"}

    
def _normalize_intent_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _asks_financial_question(text: str) -> bool:
    normalized = _normalize_intent_text(text)
    compact = " ".join(normalized.split())
    if any(phrase in compact for phrase in _CASUAL_CA_PHRASES):
        compact = re.sub(r"ca (va|marche|roule)|comment ca va", "", compact)
    words = set(re.findall(r"[a-z0-9]+", compact))
    if words & _FINANCIAL_KEYWORDS:
        return True
    return "chiffre d affaires" in compact or "data warehouse" in compact


def _build_dw_context() -> str:
    ctx: dict = {}
    try:
        summary = get_assistant_summary()
        ctx["kpis"]          = summary.get("kpis", {})
        ctx["tresorerie"]    = summary.get("tresorerie", {})
        ctx["top_articles"]  = summary.get("articles", [])[:10]
        ctx["top_clients"]   = summary.get("clients", [])[:10]
        ctx["impayes"]       = summary.get("impayes", [])[:10]
        ctx["alertes_stock"] = summary.get("stockAlerts", [])[:10]
    except Exception as exc:
        ctx["error"] = str(exc)
    return json.dumps(ctx, ensure_ascii=False, default=str)


def _gemini_history(messages: List[ChatMessage]) -> list:
    return [
        genai.types.Content(
            role="user" if msg.role == "user" else "model",
            parts=[genai.types.Part(text=msg.content)],
        )
        for msg in messages[:-1]
    ]


@app.get("/api/assistant/status")
def get_assistant_status():
    return {"llm_ready": _LLM_READY, "model": _GEMINI_MODEL if _LLM_READY else None}


@app.post("/api/assistant/chat")
def assistant_chat(req: ChatRequest):
    if not _LLM_READY or _GEMINI_CLIENT is None:
        def _no_key():
            yield "data: Ajoutez GEMINI_API_KEY dans etl/.env pour activer l'IA.\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_no_key(), media_type="text/event-stream")

    if not req.messages:
        return StreamingResponse(iter(["data: [DONE]\n\n"]), media_type="text/event-stream")

    current_user_text = req.messages[-1].content
    is_financial_question = _asks_financial_question(current_user_text)

    if is_financial_question:
        dw_ctx = _build_dw_context()
        prompt = (
            "[DONNEES LIVE DU DATA WAREHOUSE - MAG Distribution]\n"
            + dw_ctx
            + "\n\n[QUESTION UTILISATEUR]\n"
            + current_user_text
        )
        contents = _gemini_history(req.messages) + [
            genai.types.Content(role="user", parts=[genai.types.Part(text=prompt)])
        ]
    else:
        contents = [
            genai.types.Content(role="user", parts=[genai.types.Part(text=current_user_text)])
        ]

    def _stream():
        try:
            response = _GEMINI_CLIENT.models.generate_content_stream(
                model=_GEMINI_MODEL,
                contents=contents,
                config=genai.types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
            )
            for chunk in response:
                text_chunk = chunk.text if chunk.text else ""
                if text_chunk:
                    for line in text_chunk.splitlines(keepends=True):
                        yield f"data: {line}"
                    if not text_chunk.endswith("\n"):
                        yield "\n"
                    yield "\n"
        except Exception as exc:
            yield f"data: Erreur LLM : {exc}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
