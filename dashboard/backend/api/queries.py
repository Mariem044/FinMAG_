import os
import logging
import threading
from typing import Optional
from datetime import datetime

from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from etl.config import DW_ENGINE, MAG_ENGINE, GRT_ENGINE, AUDIT_TABLE_NAME
from etl import pipeline

logger = logging.getLogger(__name__)

APP_ENV = os.environ.get("APP_ENV", "development").lower()
DEV_MODE = APP_ENV != "production"
REQUEST_LOG_FILE = os.environ.get("REQUEST_LOG_FILE")

app = FastAPI(title="FinMAG API")
_ETL_RUN_LOCK = threading.Lock()
_ETL_LAST_ERROR = None

@app.middleware("http")
async def log_requests(request, call_next):
    url = str(request.url)
    timestamp = datetime.now().isoformat()

    if REQUEST_LOG_FILE:
        try:
            log_path = os.path.abspath(REQUEST_LOG_FILE)
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} {request.method} {url}\n")
        except OSError as exc:
            logger.warning("Could not write request log to %s: %s", REQUEST_LOG_FILE, exc)
    else:
        logger.info("Incoming request: %s %s", request.method, url)

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled error while processing request %s %s", request.method, url)
        raise

    logger.info("Request completed: %s %s %s", request.method, url, response.status_code)
    return response

cors_origins = ["*"] if DEV_MODE else os.environ.get("CORS_ALLOW_ORIGINS", "").split(",")
if not DEV_MODE and cors_origins == [""]:
    raise RuntimeError("CORS_ALLOW_ORIGINS must be set in production to restrict allowed origins")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONTHS = ["Jan", "Fev", "Mar", "Avr", "Mai", "Jun", "Jul", "Aou", "Sep", "Oct", "Nov", "Dec"]

def _rows(sql, params=None):
    if _ETL_RUN_LOCK.locked():
        return []
    try:
        with DW_ENGINE.connect() as conn:
            return conn.execute(text(sql), params or {}).fetchall()
    except SQLAlchemyError as exc:
        logging.error(f"Database query error in _rows: {exc}")
        return []


def _row(sql, params=None):
    if _ETL_RUN_LOCK.locked():
        return None
    try:
        with DW_ENGINE.connect() as conn:
            return conn.execute(text(sql), params or {}).fetchone()
    except SQLAlchemyError as exc:
        logging.error(f"Database query error in _row: {exc}")
        return None


def _num(value, default=0.0):
    return float(value) if value is not None else default


def _int(value, default=0):
    return int(value) if value is not None else default


def _date_str(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")


def _parse_month(month_str):
    if not month_str:
        return 0
    val = str(month_str).strip().lower()
    months_map = {
        "jan": 1, "fev": 2, "mar": 3, "avr": 4,
        "mai": 5, "jun": 6, "jul": 7, "aou": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    return months_map.get(val[:3], 0)


def _build_filters_ventes(year=None, quarter=None, month=None, segment=None, famille=None):
    """Filtres pour les endpoints ventes (FAIT_LIGNES_VENTE)."""
    sql = ""
    params = {}

    if year:
        sql += " AND d.annee = :year"
        params["year"] = int(year)

    if quarter and quarter not in ("Tous", "Toutes", ""):
        q_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
        q = q_map.get(str(quarter).upper())
        if q:
            sql += " AND d.trimestre = :quarter"
            params["quarter"] = q

    m = _parse_month(month)
    if m > 0:
        sql += " AND d.mois = :month"
        params["month"] = m

    if segment and segment not in ("Tous", "Toutes", ""):
        sql += " AND s.libelle_segment = :segment"
        params["segment"] = segment

    if famille and famille not in ("Tous", "Toutes", ""):
        sql += " AND fa.FA_Intitule LIKE :famille"
        params["famille"] = f"%{famille}%"

    return sql, params


def _build_filters_reglements(year=None, quarter=None, month=None, segment=None):
    """Filtres pour les endpoints règlements/trésorerie (FAIT_REGLEMENTS)."""
    sql = ""
    params = {}

    if year:
        sql += " AND d.annee = :year"
        params["year"] = int(year)

    if quarter and quarter not in ("Tous", "Toutes", ""):
        q_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
        q = q_map.get(str(quarter).upper())
        if q:
            sql += " AND d.trimestre = :quarter"
            params["quarter"] = q

    m = _parse_month(month)
    if m > 0:
        sql += " AND d.mois = :month"
        params["month"] = m

    if segment and segment not in ("Tous", "Toutes", ""):
        sql += " AND s.libelle_segment = :segment"
        params["segment"] = segment

    return sql, params


def _build_filters_ecritures(year=None, quarter=None, month=None):
    """Filtres pour les endpoints fiscalité/écritures (FAIT_ECRITURES)."""
    sql = ""
    params = {}

    if year:
        sql += " AND d.annee = :year"
        params["year"] = int(year)

    if quarter and quarter not in ("Tous", "Toutes", ""):
        q_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
        q = q_map.get(str(quarter).upper())
        if q:
            sql += " AND d.trimestre = :quarter"
            params["quarter"] = q

    m = _parse_month(month)
    if m > 0:
        sql += " AND d.mois = :month"
        params["month"] = m

    return sql, params


def _build_filters_bordereaux(year=None, quarter=None, month=None, banque=None):
    """Filtres pour F_BordereauRemise, source reelle des bordereaux banque."""
    sql = ""
    params = {}

    if year:
        sql += " AND YEAR(br.BR_Date) = :year"
        params["year"] = int(year)

    if quarter and quarter not in ("Tous", "Toutes", ""):
        q_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
        q = q_map.get(str(quarter).upper())
        if q:
            sql += " AND DATEPART(QUARTER, br.BR_Date) = :quarter"
            params["quarter"] = q

    m = _parse_month(month)
    if m > 0:
        sql += " AND MONTH(br.BR_Date) = :month"
        params["month"] = m

    if banque and banque not in ("Tous", "Toutes", ""):
        sql += " AND br.BQ_ABREGE = :banque"
        params["banque"] = banque

    return sql, params


def _rows_grt(sql, params=None):
    try:
        with GRT_ENGINE.connect() as conn:
            return conn.execute(text(sql), params or {}).fetchall()
    except SQLAlchemyError as exc:
        logging.error(f"GRT query error in _rows_grt: {exc}")
        return []


def _row_grt(sql, params=None):
    try:
        with GRT_ENGINE.connect() as conn:
            return conn.execute(text(sql), params or {}).fetchone()
    except SQLAlchemyError as exc:
        logging.error(f"GRT query error in _row_grt: {exc}")
        return None


def _mode_reg_key(mode_label, mode_code=None):
    label = (mode_label or "").strip()
    low = label.lower()
    if "cheque" in low or "chèque" in low or "chq" in low:
        return "Chèque"
    if "traite" in low or "lcr" in low or "effet" in low:
        return "Traite"
    if "virement" in low or low.startswith("vir"):
        return "Virement"

    try:
        code = int(mode_code)
    except (TypeError, ValueError):
        code = None
    return {1: "Chèque", 2: "Traite", 3: "Virement"}.get(code)

def _run_etl_background():
    global _ETL_LAST_ERROR
    try:
        pipeline.run_pipeline()
        _ETL_LAST_ERROR = None

        try:
            from ..ml.runner import run_all as run_ml  # type: ignore
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

        return {
            "depots": depots,
            "segments": segments,
            "familles": familles,
            "years": years
        }
    except SQLAlchemyError as exc:
        logging.error(f"Error fetching dynamic filters: {exc}")
        return {
            "depots": ["Tous", "Tunis Nord", "Tunis Sud", "Sfax", "Sousse", "Nabeul", "Bizerte", "Dépôt Central"],
            "segments": ["Tous", "DÉTAILLANTS", "SEMI-GROS", "HORECA", "GROSSISTES", "DISTRIBUTEUR"],
            "familles": ["Toutes", "Biscuits", "Boissons", "Conserves", "Produits Laitiers", "Confiserie", "Épicerie", "Huiles", "Pâtes"],
            "years": [2026, 2025, 2024, 2023, 2022, 2021, 2020]
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
    except SQLAlchemyError as exc:
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
            "kpi05": "ML_KPI05_CA_FORECAST"
        }
        for k, tbl in tables.items():
            try:
                n = _row(f"SELECT COUNT(*) AS c FROM {tbl} WITH (NOLOCK)")
                counts[k] = _int(n.c) if n else 0
            except SQLAlchemyError:
                counts[k] = 0

        last_date = None
        try:
            r = _row("SELECT MAX(run_date) AS d FROM ML_KPI05_CA_FORECAST WITH (NOLOCK)")
            if r and r.d:
                last_date = _date_str(r.d)
        except SQLAlchemyError:
            pass

    except SQLAlchemyError as exc:
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
    except SQLAlchemyError:
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
):
    filt_sql, filt_params = _build_filters_ventes(
        quarter=quarter, month=month, segment=segment, famille=famille
    )
    
    max_year_res = _row("""
        SELECT MAX(d.annee) AS annee
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DATE d ON d.id_date = f.id_date
        WHERE f.DO_Domaine = 0
    """)
    max_year = max_year_res.annee if (max_year_res and max_year_res.annee is not None) else datetime.now().year

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
                        AND f.DL_Qte IS NOT NULL                THEN f.DL_MontantHT - (f.DL_Qte * f.DL_CMUP)
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
                        AND f.DL_Qte IS NOT NULL                THEN f.DL_MontantHT - (f.DL_Qte * f.DL_CMUP)
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
    if ca_avec_cout > 0 and raw_marge is not None:
        marge_brute_pct = round(float(raw_marge) / ca_avec_cout * 100, 2)
    else:
        marge_brute_pct = None
    
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
                    MAX(COALESCE(r.id_date_paiement, r.id_date_echeance)) AS id_date
                FROM FAIT_REGLEMENTS r WITH (NOLOCK)
                WHERE r.RT_Num IS NOT NULL AND r.id_client IS NOT NULL
                GROUP BY r.RT_Num
            )
            SELECT
                dt.annee,
                SUM(CASE WHEN DR_Regle = 1 THEN RT_Montant ELSE 0 END) AS encaissements,
                SUM(CASE WHEN DR_Regle = 0 THEN RT_Montant ELSE 0 END) AS impayes
            FROM deduped d
            JOIN DIM_DATE dt WITH (NOLOCK) ON dt.id_date = d.id_date
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
    except SQLAlchemyError:
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
):
    filt_sql, filt_params = _build_filters_ventes(
        quarter=quarter, month=month, segment=segment, famille=famille
    )
    max_year_res = _row("""
        SELECT MAX(d.annee) AS annee
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DATE d ON d.id_date = f.id_date
        WHERE f.DO_Domaine = 0
    """)
    max_year = max_year_res.annee if (max_year_res and max_year_res.annee is not None) else datetime.now().year

    # Récupérer les données mensuelles pour l'année sélectionnée et N-1
    params = {"year": year, "year_n1": year - 1}
    params.update(filt_params)

    sql = f"""
        SELECT
            d.annee,
            d.mois AS month_num,
            SUM(f.DL_MontantHT) AS ca,
            COUNT(DISTINCT f.id_client) AS nb_clients_actifs,
            SUM(CASE
                WHEN f.DL_CMUP IS NOT NULL AND f.DL_CMUP > 0 AND f.DL_Qte IS NOT NULL
                     AND f.DL_MontantHT > (f.DL_Qte * f.DL_CMUP)
                THEN f.DL_MontantHT - (f.DL_Qte * f.DL_CMUP)
                ELSE NULL
            END) AS marge_brute
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DATE d ON d.id_date = f.id_date
        LEFT JOIN DIM_CLIENT c ON c.id_client = f.id_client
        LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE f.DO_Domaine = 0
        AND d.annee IN (:year, :year_n1)
        {filt_sql}
        GROUP BY d.annee, d.mois
        ORDER BY d.annee, d.mois
    """
    all_rows = _rows(sql, params)

    # Séparer année courante et N-1 en Python
    rows = [r for r in all_rows if r.annee == year]
    prev_year_dict = {r.month_num: _num(r.ca) for r in all_rows if r.annee == year - 1}
    
    # Récupérer le taux de recouvrement par mois
    rec_by_month = {}
    rec_rows = _rows("""
        SELECT
            dt.mois,
            SUM(CASE WHEN r.DR_Regle = 1 THEN r.RT_Montant ELSE 0 END) AS encaissements,
            SUM(CASE WHEN r.DR_Regle = 0 THEN r.RT_Montant ELSE 0 END) AS impayes
        FROM FAIT_REGLEMENTS r
        JOIN DIM_DATE dt ON dt.id_date = COALESCE(r.id_date_paiement, r.id_date_echeance)
        WHERE dt.annee = :year
        AND r.RT_Num IS NOT NULL
        GROUP BY dt.mois
    """, {"year": year})
    for r in rec_rows:
        enc = _num(r.encaissements)
        imp = _num(r.impayes)
        tot = enc + imp
        rec_by_month[r.mois] = (enc / tot * 100) if tot else 0.0

    return [
        {
            "month": f"{MONTHS[r.month_num - 1]} {str(year)[2:]}",
            "ca": _num(r.ca),
            "caN1": prev_year_dict.get(r.month_num, 0.0),
            "nb_clients_actifs": _int(r.nb_clients_actifs),
            "marge_brute": _num(r.marge_brute),
            "taux_recouvrement": rec_by_month.get(r.month_num, 0.0),
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
):
    filt_sql, filt_params = _build_filters_ventes(
        year=year, quarter=quarter, month=month, segment=segment, famille=famille
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
):
    filt_sql, filt_params = _build_filters_reglements(
        year=year, quarter=quarter, month=month, segment=segment
    )
    sql = f"""
        WITH deduped AS (
            SELECT
                r.RT_Num,
                MAX(r.RT_Montant)         AS RT_Montant,
                MAX(r.DR_Regle)           AS DR_Regle,
                MAX(r.delai_reel_jours)   AS delai_reel_jours
            FROM FAIT_REGLEMENTS r
            LEFT JOIN DIM_DATE d ON d.id_date = COALESCE(r.id_date_paiement, r.id_date_echeance)
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
):
    filt_sql, filt_params = _build_filters_reglements(
        year=year, quarter=quarter, month=month, segment=segment
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
        LEFT JOIN DIM_DATE d ON d.id_date = COALESCE(r.id_date_paiement, r.id_date_echeance)
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
):
    filt_sql, filt_params = _build_filters_ventes(
        year=year, quarter=quarter, month=month, segment=segment
    )

    # Filtre dépôt pour le stock
    depot_clause = ""
    if depot and depot not in ("Tous", "Toutes", ""):
        if "central" in depot.lower():
            depot_clause = "AND dp.DE_Principal = 1"
        else:
            depot_clause = "AND dp.DE_Intitule = :p_depot_name"
            filt_params["p_depot_name"] = depot

    # Filtre famille pour la requête principale
    famille_clause = ""
    if famille and famille not in ("Tous", "Toutes", ""):
        famille_clause = "AND fa.FA_Intitule LIKE :p_famille_main"
        filt_params["p_famille_main"] = f"%{famille}%"

    # Nombre de jours selon la période sélectionnée
    days_in_period = 365.0
    if month and str(month).strip() not in ("", "Tous"):
        days_in_period = 30.0
    elif quarter and str(quarter).strip() not in ("", "Tous"):
        days_in_period = 90.0
    filt_params["p_days_in_period"] = days_in_period

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
            LEFT JOIN DIM_DEPOT dp ON dp.id_depot = e.id_depot
            WHERE e.grain = 4
            AND e.AS_QteSto IS NOT NULL
            {depot_clause}
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
            CASE 
                WHEN COALESCE(sales.qte_vendue, 0) > 0 
                THEN COALESCE(stock.stock, 0) / (sales.qte_vendue / :p_days_in_period)
                ELSE NULL 
            END AS dsi_jours,
            stock.ratio_tension
        FROM DIM_ARTICLE a
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
        LEFT JOIN sales ON sales.id_article = a.id_article
        LEFT JOIN stock ON stock.id_article = a.id_article
        WHERE (COALESCE(sales.ca, 0) > 0 OR COALESCE(stock.stock, 0) > 0)
        {famille_clause}
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


@app.get("/api/banque/rapprochement")
def get_banque_rapprochement(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    region: Optional[str] = None,
    famille: Optional[str] = None,
    segment: Optional[str] = None,
    depot: Optional[str] = None,
    banque: Optional[str] = None,
):
    filt_sql, filt_params = _build_filters_reglements(
        year=year, quarter=quarter, month=month, segment=segment
    )
    if banque and banque not in ("Tous", "Toutes", ""):
        filt_sql += " AND b.EB_Abrege_code = :banque"
        filt_params["banque"] = banque
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
            LEFT JOIN DIM_BANQUE b ON b.id_banque = r.id_banque
            WHERE r.RT_Num IS NOT NULL
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
    banque: Optional[str] = None,
):
    filt_sql, filt_params = _build_filters_bordereaux(
        year=year, quarter=quarter, month=month, banque=banque
    )
    sql = f"""
        SELECT
            COALESCE(NULLIF(br.BQ_ABREGE, ''), NULLIF(eb.EB_Abrege, ''), 'Non spécifiée') AS banque,
            br.BR_ModeReg AS mode_reg,
            COALESCE(NULLIF(mr.MR_Designation, ''), CONCAT('Mode ', br.BR_ModeReg)) AS libelle_mode_reg,
            SUM(COALESCE(NULLIF(br.BR_TotalReglement, 0), NULLIF(br.BR_Montant, 0), 0)) AS total_montant
        FROM F_BordereauRemise br WITH (NOLOCK)
        LEFT JOIN P_ModeReglements mr WITH (NOLOCK) ON mr.MR_Code = br.BR_ModeReg
        LEFT JOIN F_EBANQUE eb WITH (NOLOCK)
            ON REPLACE(COALESCE(br.BR_CompteBanque, ''), ' ', '') =
               CONCAT(COALESCE(eb.EB_Banque, ''), COALESCE(eb.EB_Guichet, ''), COALESCE(eb.EB_Compte, ''), COALESCE(eb.EB_Cle, ''))
            OR (
                NULLIF(eb.EB_Compte, '') IS NOT NULL
                AND REPLACE(COALESCE(br.BR_CompteBanque, ''), ' ', '') LIKE CONCAT('%', REPLACE(COALESCE(eb.EB_Compte, ''), ' ', ''), '%')
            )
        WHERE br.BR_Date IS NOT NULL
        AND COALESCE(NULLIF(br.BR_TotalReglement, 0), NULLIF(br.BR_Montant, 0), 0) <> 0
        {filt_sql}
        GROUP BY br.BQ_ABREGE, eb.EB_Abrege, br.BR_ModeReg, mr.MR_Designation
    """
    totals = {"Chèque": 0.0, "Traite": 0.0, "Virement": 0.0}
    bank_data = {}
    for r in _rows_grt(sql, filt_params):
        bank_name = r.banque or "Non spécifiée"
        mode_key = _mode_reg_key(r.libelle_mode_reg, r.mode_reg)
        val = _num(r.total_montant)
        if mode_key:
            totals[mode_key] += val

        if bank_name not in bank_data:
            bank_data[bank_name] = {"banque": bank_name, "Chèque": 0.0, "Traite": 0.0, "Virement": 0.0}
        if mode_key:
            bank_data[bank_name][mode_key] += val

    sql_tx = f"""
        SELECT TOP 25
            br.BR_Num,
            br.BR_ModeReg AS mode_reg,
            COALESCE(NULLIF(mr.MR_Designation, ''), CONCAT('Mode ', br.BR_ModeReg)) AS libelle_mode_reg,
            COALESCE(NULLIF(br.BR_TotalReglement, 0), NULLIF(br.BR_Montant, 0), 0) AS montant,
            COALESCE(NULLIF(br.BQ_ABREGE, ''), NULLIF(eb.EB_Abrege, ''), NULLIF(br.BR_IntituleBanque, ''), 'Banque') AS banque
        FROM F_BordereauRemise br WITH (NOLOCK)
        LEFT JOIN P_ModeReglements mr WITH (NOLOCK) ON mr.MR_Code = br.BR_ModeReg
        LEFT JOIN F_EBANQUE eb WITH (NOLOCK)
            ON REPLACE(COALESCE(br.BR_CompteBanque, ''), ' ', '') =
               CONCAT(COALESCE(eb.EB_Banque, ''), COALESCE(eb.EB_Guichet, ''), COALESCE(eb.EB_Compte, ''), COALESCE(eb.EB_Cle, ''))
            OR (
                NULLIF(eb.EB_Compte, '') IS NOT NULL
                AND REPLACE(COALESCE(br.BR_CompteBanque, ''), ' ', '') LIKE CONCAT('%', REPLACE(COALESCE(eb.EB_Compte, ''), ' ', ''), '%')
            )
        WHERE br.BR_Date IS NOT NULL
        AND COALESCE(NULLIF(br.BR_TotalReglement, 0), NULLIF(br.BR_Montant, 0), 0) <> 0
        {filt_sql}
        ORDER BY COALESCE(NULLIF(br.BR_TotalReglement, 0), NULLIF(br.BR_Montant, 0), 0) DESC
    """
    transactions = []
    for r in _rows_grt(sql_tx, filt_params):
        transactions.append({
            "reference": r.BR_Num,
            "mode": _mode_reg_key(r.libelle_mode_reg, r.mode_reg) or r.libelle_mode_reg,
            "montant": _num(r.montant),
            "client": r.banque,
        })

    return {
        "totals": totals,
        "banques": list(bank_data.values()),
        "transactions": transactions,
    }


@app.get("/api/banque/debug-bordereaux")
def debug_bordereaux_banque(
    year: Optional[int] = None,
    quarter: Optional[str] = None,
    month: Optional[str] = None,
    banque: Optional[str] = None,
):
    filt_sql, filt_params = _build_filters_bordereaux(
        year=year, quarter=quarter, month=month, banque=banque
    )
    join_sql = """
        LEFT JOIN F_EBANQUE eb WITH (NOLOCK)
            ON REPLACE(COALESCE(br.BR_CompteBanque, ''), ' ', '') =
               CONCAT(COALESCE(eb.EB_Banque, ''), COALESCE(eb.EB_Guichet, ''), COALESCE(eb.EB_Compte, ''), COALESCE(eb.EB_Cle, ''))
            OR (
                NULLIF(eb.EB_Compte, '') IS NOT NULL
                AND REPLACE(COALESCE(br.BR_CompteBanque, ''), ' ', '') LIKE CONCAT('%', REPLACE(COALESCE(eb.EB_Compte, ''), ' ', ''), '%')
            )
    """
    summary = _row_grt(f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN COALESCE(NULLIF(br.BQ_ABREGE, ''), NULLIF(eb.EB_Abrege, '')) IS NULL THEN 1 ELSE 0 END) AS sans_banque,
            SUM(CASE WHEN NULLIF(br.BQ_ABREGE, '') IS NOT NULL THEN 1 ELSE 0 END) AS avec_bq_abrege,
            SUM(CASE WHEN NULLIF(eb.EB_Abrege, '') IS NOT NULL THEN 1 ELSE 0 END) AS resolus_par_compte
        FROM F_BordereauRemise br WITH (NOLOCK)
        {join_sql}
        WHERE br.BR_Date IS NOT NULL
        AND COALESCE(NULLIF(br.BR_TotalReglement, 0), NULLIF(br.BR_Montant, 0), 0) <> 0
        {filt_sql}
    """, filt_params)
    samples = _rows_grt(f"""
        SELECT TOP 20
            br.BR_Num,
            br.BQ_ABREGE,
            br.BR_CompteBanque,
            eb.EB_Abrege,
            br.BR_IntituleBanque,
            br.BR_ModeReg,
            COALESCE(NULLIF(br.BR_TotalReglement, 0), NULLIF(br.BR_Montant, 0), 0) AS montant
        FROM F_BordereauRemise br WITH (NOLOCK)
        {join_sql}
        WHERE br.BR_Date IS NOT NULL
        AND COALESCE(NULLIF(br.BR_TotalReglement, 0), NULLIF(br.BR_Montant, 0), 0) <> 0
        AND COALESCE(NULLIF(br.BQ_ABREGE, ''), NULLIF(eb.EB_Abrege, '')) IS NULL
        {filt_sql}
        ORDER BY COALESCE(NULLIF(br.BR_TotalReglement, 0), NULLIF(br.BR_Montant, 0), 0) DESC
    """, filt_params)
    return {
        "total": _int(summary.total) if summary else 0,
        "sansBanque": _int(summary.sans_banque) if summary else 0,
        "avecBqAbrege": _int(summary.avec_bq_abrege) if summary else 0,
        "resolusParCompte": _int(summary.resolus_par_compte) if summary else 0,
        "samplesSansBanque": [
            {
                "BR_Num": r.BR_Num,
                "BQ_ABREGE": r.BQ_ABREGE,
                "BR_CompteBanque": r.BR_CompteBanque,
                "EB_Abrege": r.EB_Abrege,
                "BR_IntituleBanque": r.BR_IntituleBanque,
                "BR_ModeReg": _int(r.BR_ModeReg),
                "montant": _num(r.montant),
            }
            for r in samples
        ],
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
):
    filt_sql, filt_params = _build_filters_ecritures(
        year=year, quarter=quarter, month=month
    )
    c_depot = str(depot).strip() if depot else ""
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
):
    filt_sql, filt_params = _build_filters_ecritures(
        year=year, quarter=quarter, month=month
    )
    depot_clause = ""
    depot_params = {}
    if depot and depot not in ("Tous", "Toutes", ""):
        rev_map = {"tunis nord": 1425916589894576877, "tunis sud": 1085862494906140374, "sfax": 2798417896384401189, "sousse": 6528386168626322420}
        depot_code = rev_map.get(depot.lower())
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
):
    filt_sql, filt_params = _build_filters_ecritures(
        year=year, quarter=quarter, month=month
    )
    depot_clause = ""
    depot_params = {}
    if depot and depot not in ("Tous", "Toutes", ""):
        rev_map = {"tunis nord": 1425916589894576877, "tunis sud": 1085862494906140374, "sfax": 2798417896384401189, "sousse": 6528386168626322420}
        depot_code = rev_map.get(depot.lower())
        if depot_code:
            depot_clause = "AND e.id_caisse = (SELECT id_caisse FROM DIM_CAISSE WHERE CA_Numero_code = :p_caisse_depot)"
            depot_params["p_caisse_depot"] = depot_code

    sql = f"""
        SELECT
            COALESCE(
                NULLIF(tm.MC_IntituleTypeMvt, ''),
                CASE tm.MC_TypeMvt
                    WHEN 1 THEN 'Recette'
                    WHEN 2 THEN 'Dépense'
                    WHEN 3 THEN 'Transfert'
                    ELSE CONCAT('Mouvement ', tm.MC_TypeMvt)
                END
            ) AS name,
            SUM(ABS(COALESCE(e.MC_Credit, 0)) + ABS(COALESCE(e.MC_Debit, 0))) AS value
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_TYPE_MVT_CAISSE tm ON tm.id_type_mvt = e.id_type_mvt_caisse
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        WHERE e.grain = 3
        {depot_clause}
        {filt_sql}
        GROUP BY tm.MC_TypeMvt, tm.MC_IntituleTypeMvt
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
):
    filt_sql, filt_params = _build_filters_ecritures(
        year=year, quarter=quarter, month=month
    )
    sql_kpis = f"""
        WITH stats AS (
            SELECT 
                AVG(ABS(EC_Montant))  AS avg_montant,
                STDEV(ABS(EC_Montant)) AS stdev_montant
            FROM FAIT_ECRITURES
            WHERE EC_Montant IS NOT NULL
        )
        SELECT
            SUM(CASE WHEN e.grain IN (1, 2) THEN 1 ELSE 0 END) AS nb_ecritures,
            SUM(CASE WHEN e.grain = 2 AND j.JO_Type = 0 THEN COALESCE(e.RT_Montant01, 0) ELSE 0 END) AS tva_collectee,
            SUM(CASE WHEN e.grain = 2 AND j.JO_Type = 1 THEN COALESCE(e.RT_Montant01, 0) ELSE 0 END) AS tva_deductible,
            SUM(CASE
                WHEN e.grain = 1
                AND ABS(COALESCE(e.EC_Montant, 0)) >= stats.avg_montant + 2 * stats.stdev_montant
                THEN 1 ELSE 0
            END) AS anomalies
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_JOURNAL j ON j.id_journal = e.id_journal
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        CROSS JOIN stats
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
):
    filt_sql, filt_params = _build_filters_ecritures(
        year=year, quarter=quarter, month=month
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
):
    filt_sql, filt_params = _build_filters_ecritures(
        year=year, quarter=quarter, month=month
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



