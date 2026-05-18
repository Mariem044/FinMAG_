import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sqlalchemy import text

warnings.filterwarnings("ignore")

from config import DW_ENGINE
from utils.logger import get_logger

logger = get_logger(__name__)

_MODEL_DIR = Path(__file__).parent / "models"
_MODEL_DIR.mkdir(exist_ok=True)
_MODEL_PATH = _MODEL_DIR / "consumption.joblib"
_MODEL_MAX_AGE_DAYS = 7

_DDL = """
CREATE TABLE ML_KPI18_RUPTURE_FORECAST (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    run_date            DATE NOT NULL,
    article             VARCHAR(50) NOT NULL,
    famille             NVARCHAR(100) NULL,
    priorite            VARCHAR(20) NULL,
    consoJourMoy        NUMERIC(18,4) NULL,
    consoJourPred       NUMERIC(18,4) NULL,
    cvConso             NUMERIC(18,4) NULL,
    stockActuel         NUMERIC(18,4) NULL,
    stockSecurite       NUMERIC(18,4) NULL,
    r2Score             NUMERIC(5,2) NULL
)
"""

def _ensure_table() -> None:
    with DW_ENGINE.begin() as conn:
        conn.execute(text("IF OBJECT_ID('ML_KPI18_RUPTURE_FORECAST', 'U') IS NOT NULL DROP TABLE ML_KPI18_RUPTURE_FORECAST"))
        conn.execute(text(_DDL))

def _load_stock_snapshot() -> pd.DataFrame:
    sql = """
        SELECT
            fe.id_article,
            a.AR_Ref_code,
            COALESCE(NULLIF(fa.FA_Intitule,''), 'Sans famille') AS famille,
            fe.AS_QteSto     AS stock_actuel,
            fe.AS_QteMini    AS stock_mini,
            fe.AS_QteRes     AS stock_reserve,
            fe.en_rupture,
            fe.dsi_jours
        FROM FAIT_ECRITURES fe
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
        JOIN DIM_ARTICLE     a  ON a.id_article     = fe.id_article
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille   = a.id_famille
        WHERE tl.type_ligne = 4
        AND fe.AS_QteSto IS NOT NULL
        AND a.AR_Sommeil = 0
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    logger.info(f"[KPI-18] Stock snapshot: {len(df)} articles")
    return df

def _load_sales_history() -> pd.DataFrame:
    sql = """
        SELECT
            f.id_article,
            DATEFROMPARTS(d.annee, d.mois, 1) AS mois_date,
            SUM(f.DL_Qte) AS qte_vendue
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        JOIN DIM_DATE    d   ON d.id_date      = f.id_date
        WHERE dom.DO_Domaine = 0
        AND d.annee >= YEAR(DATEADD(MONTH, -24, GETDATE()))
        AND f.DL_Qte IS NOT NULL
        GROUP BY f.id_article, d.annee, d.mois
        ORDER BY f.id_article, mois_date
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["mois_date"] = pd.to_datetime(df["mois_date"])
    logger.info(f"[KPI-18] Sales history: {len(df)} article-month rows")
    return df

def _predict_consumption(sales_df: pd.DataFrame) -> pd.DataFrame:
    article_ids_set = set(sales_df["id_article"].unique())
    results = []
    r2_values = []

    for id_article, grp in sales_df.groupby("id_article"):
        grp = grp.sort_values("mois_date").copy()
        grp["t"] = range(len(grp))
        n = len(grp)
        y = grp["qte_vendue"].values.astype(float)

        mean_y = float(y.mean()) if n > 0 else 0.0
        std_y = float(np.std(y)) if n > 1 else 0.0
        cv_conso = std_y / mean_y if mean_y > 0 else 0.0

        if n < 3:
            conso_moy = mean_y
            r2 = 0.0
            conso_pred = conso_moy
        else:
            t = grp["t"].values.astype(float)
            alpha, beta = np.polyfit(t, y, 1)
            y_pred = alpha * t + beta
            
            
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = max(0.0, 1 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
            
            conso_pred = max(0.0, alpha * n + beta)
            conso_moy = mean_y

        r2_values.append(r2)
        conso_jour_moy  = conso_moy  / 30.0
        conso_jour_pred = conso_pred / 30.0

        results.append({
            "id_article": id_article,
            "consoJourMoy": conso_jour_moy,
            "consoJourPred": conso_jour_pred,
            "cvConso": cv_conso,
            "r2Score": round(r2 * 100, 2),
        })

    if r2_values:
        logger.info(
            f"[KPI-18] OLS Regression finished - "
            f"Mean R2={np.mean(r2_values):.3f} "
            f"({len(r2_values)} articles)"
        )

    return pd.DataFrame(results)

def _compute_rupture_dates(
    stock_df: pd.DataFrame,
    conso_df: pd.DataFrame,
    horizon: int,
) -> pd.DataFrame:
    today = datetime.now(timezone.utc).date()

    df = stock_df.merge(conso_df, on="id_article", how="left")

    def _rupture_date(stock, conso):
        if pd.isna(stock) or pd.isna(conso) or stock is None or conso is None or conso <= 0:
            return None
        days = stock / conso
        if pd.isna(days) or np.isinf(days) or days < 0 or days > 36500:
            return None
        try:
            return today + timedelta(days=int(days))
        except Exception:
            return None

    df["date_rupture_regle"] = df.apply(
        lambda r: _rupture_date(r["stock_actuel"], r["consoJourMoy"]), axis=1
    )
    df["date_rupture_ml"] = df.apply(
        lambda r: _rupture_date(r["stock_actuel"], r["consoJourPred"]), axis=1
    )

    def _jours(rupture_date):
        if rupture_date is None:
            return None
        return (rupture_date - today).days

    df["jours_avant_rupture"] = df["date_rupture_ml"].apply(_jours)

    def _priorite(row):
        if row["en_rupture"] == 1:
            return "CRITIQUE"
        j = row["jours_avant_rupture"]
        if j is None:
            return "OK"
        if j <= 7:
            return "CRITIQUE"
        if j <= horizon // 2:
            return "URGENT"
        if j <= horizon:
            return "ATTENTION"
        return "OK"

    df["priorite"] = df.apply(_priorite, axis=1)
    
    
    df = df.rename(columns={
        "AR_Ref_code": "article",
        "stock_actuel": "stockActuel",
        "stock_mini": "stockSecurite"
    })
    
    
    df["article"] = "ART-" + df["article"].astype(str)

    return df

def _save(df: pd.DataFrame) -> None:
    today = datetime.now(timezone.utc).date()
    with DW_ENGINE.begin() as conn:
        conn.execute(
            text("DELETE FROM ML_KPI18_RUPTURE_FORECAST WHERE run_date = :d"),
            {"d": today},
        )

    cols = [
        "article", "famille", "priorite",
        "consoJourMoy", "consoJourPred", "cvConso",
        "stockActuel", "stockSecurite", "r2Score"
    ]
    df_out = df[cols].copy()

    def _v(v):
        if v is None:
            return None
        try:
            if pd.isna(v):
                return None
        except Exception:
            pass
        if hasattr(v, "item"):
            return v.item()
        return v

    rows = []
    for row in df_out.itertuples(index=False):
        rows.append((today,) + tuple(_v(v) for v in row))

    sql = """
        INSERT INTO ML_KPI18_RUPTURE_FORECAST
            (run_date, article, famille, priorite,
             consoJourMoy, consoJourPred, cvConso,
             stockActuel, stockSecurite, r2Score)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """
    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    n_critique = (df["priorite"] == "CRITIQUE").sum()
    n_urgent   = (df["priorite"] == "URGENT").sum()
    logger.info(
        f"[KPI-18] Saved {len(rows)} articles - "
        f"CRITIQUE: {n_critique} | URGENT: {n_urgent}"
    )

def run(horizon: int = 30) -> pd.DataFrame:
    _ensure_table()

    stock_df = _load_stock_snapshot()
    sales_df = _load_sales_history()

    if sales_df.empty:
        logger.warning("[KPI-18] No sales history found — using rule-based only")
        sales_df_agg = pd.DataFrame(columns=["id_article", "conso_jour_moy", "conso_jour_pred", "confiance"])
    else:
        sales_df_agg = _predict_consumption(sales_df)

    df_result = _compute_rupture_dates(stock_df, sales_df_agg, horizon)
    _save(df_result)
    return df_result
