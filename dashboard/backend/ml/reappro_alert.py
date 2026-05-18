import warnings
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sqlalchemy import text

warnings.filterwarnings("ignore")

from config import DW_ENGINE
from utils.logger import get_logger

logger = get_logger(__name__)

_DDL = """
IF OBJECT_ID('ML_KPI17_REAPPRO_ALERT', 'U') IS NULL
CREATE TABLE ML_KPI17_REAPPRO_ALERT (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    run_date            DATE NOT NULL,
    id_article          INT  NOT NULL,
    AR_Ref_code         BIGINT NOT NULL,
    famille             NVARCHAR(100) NULL,
    stock_actuel        NUMERIC(18,4) NULL,
    stock_mini_statique NUMERIC(18,4) NULL,
    stock_securite_dyn  NUMERIC(18,4) NULL,
    conso_jour_moy      NUMERIC(18,4) NULL,
    cv_conso            NUMERIC(18,4) NULL,
    lead_time_jours     INT  NULL,
    score_urgence       NUMERIC(18,4) NULL,
    priorite            VARCHAR(20) NULL,
    qte_a_commander     NUMERIC(18,4) NULL
)
"""

def _ensure_table() -> None:
    with DW_ENGINE.begin() as conn:
        try:
            conn.execute(text(
                "IF OBJECT_ID('ML_KPI17_REAPPRO_ALERT', 'U') IS NOT NULL AND "
                "(SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='ML_KPI17_REAPPRO_ALERT' AND COLUMN_NAME='AR_Ref_code')='int' "
                "DROP TABLE ML_KPI17_REAPPRO_ALERT"
            ))
        except Exception:
            pass
        conn.execute(text(_DDL))

def _load_stock_snapshot() -> pd.DataFrame:
    sql = """
        SELECT
            fe.id_article,
            a.AR_Ref_code,
            COALESCE(NULLIF(fa.FA_Intitule,''), 'Sans famille') AS famille,
            fe.AS_QteSto  AS stock_actuel,
            fe.AS_QteMini AS stock_mini,
            14 AS delai_fab,
            7 AS delai_trans
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
    logger.info(f"[KPI-17] Stock snapshot : {len(df)} articles actifs")
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
        AND d.annee >= YEAR(DATEADD(MONTH, -12, GETDATE()))
        AND f.DL_Qte IS NOT NULL
        GROUP BY f.id_article, d.annee, d.mois
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    logger.info(f"[KPI-17] Ventes mensuelles : {len(df)} lignes article-mois")
    return df

def _compute_reappro(
    stock_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    service_level_z: float = 1.65,
) -> pd.DataFrame:
    if sales_df.empty:
        agg = pd.DataFrame(columns=["id_article", "conso_jour_moy", "cv_conso"])
    else:
        agg = sales_df.groupby("id_article").agg(
            moyenne_mensuelle=("qte_vendue", "mean"),
            ecart_type_mensuel=("qte_vendue", "std")
        ).reset_index()

        agg["conso_jour_moy"] = agg["moyenne_mensuelle"] / 30.0
        agg["ecart_type_mensuel"] = agg["ecart_type_mensuel"].fillna(0)
        agg["cv_conso"] = np.where(
            agg["moyenne_mensuelle"] > 0,
            agg["ecart_type_mensuel"] / agg["moyenne_mensuelle"],
            0.0
        )

    df = stock_df.merge(agg[["id_article", "conso_jour_moy", "cv_conso"]], on="id_article", how="left")
    df["conso_jour_moy"] = df["conso_jour_moy"].fillna(0)
    df["cv_conso"]       = df["cv_conso"].fillna(0)

    df["delai_fab"]   = pd.to_numeric(df["delai_fab"], errors="coerce").fillna(0)
    df["delai_trans"] = pd.to_numeric(df["delai_trans"], errors="coerce").fillna(0)
    df["lead_time_jours"] = df["delai_fab"] + df["delai_trans"]
    df["lead_time_jours"] = df["lead_time_jours"].replace(0, 7)

    def _securite(row):
        lt = row["lead_time_jours"]
        z  = service_level_z
        sigma_m = row["cv_conso"] * (row["conso_jour_moy"] * 30.0)
        sigma_jour = sigma_m / np.sqrt(30)
        return z * sigma_jour * np.sqrt(lt)

    df["stock_securite_dyn"] = df.apply(_securite, axis=1)

    df["seuil_alerte"] = (df["conso_jour_moy"] * df["lead_time_jours"]) + df["stock_securite_dyn"]
    df["seuil_alerte"] = df[["seuil_alerte", "stock_mini"]].max(axis=1)

    def _score(row):
        actuel = row["stock_actuel"]
        seuil  = row["seuil_alerte"]
        if seuil <= 0:
            return 0.0
        return (seuil - actuel) / seuil

    df["score_urgence"] = df.apply(_score, axis=1)

    def _priorite(s):
        if s > 0.5:   return "CRITIQUE"
        if s > 0.0:   return "URGENT"
        if s > -0.2:  return "ATTENTION"
        return "OK"

    df["priorite"] = df["score_urgence"].apply(_priorite)

    def _qte(row):
        if row["priorite"] == "OK":
            return 0.0
        max_stock = row["seuil_alerte"] * 2.5
        qte = max_stock - row["stock_actuel"]
        return max(0.0, qte)

    df["qte_a_commander"] = df.apply(_qte, axis=1)

    return df

def _save(df: pd.DataFrame) -> None:
    today = datetime.now(timezone.utc).date()
    with DW_ENGINE.begin() as conn:
        conn.execute(
            text("DELETE FROM ML_KPI17_REAPPRO_ALERT WHERE run_date = :d"),
            {"d": today},
        )

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

    cols = [
        "id_article", "AR_Ref_code", "famille",
        "stock_actuel", "stock_mini", "stock_securite_dyn",
        "conso_jour_moy", "cv_conso", "lead_time_jours",
        "score_urgence", "priorite", "qte_a_commander"
    ]
    rows = []
    for row in df[cols].itertuples(index=False):
        rows.append((today,) + tuple(_v(v) for v in row))

    sql = """
        INSERT INTO ML_KPI17_REAPPRO_ALERT
            (run_date, id_article, AR_Ref_code, famille,
             stock_actuel, stock_mini_statique, stock_securite_dyn,
             conso_jour_moy, cv_conso, lead_time_jours,
             score_urgence, priorite, qte_a_commander)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    n_crit = (df["priorite"] == "CRITIQUE").sum()
    n_urg  = (df["priorite"] == "URGENT").sum()
    n_att  = (df["priorite"] == "ATTENTION").sum()
    logger.info(
        f"[KPI-17] {len(rows)} articles sauvegardes - "
        f"CRITIQUE: {n_crit} | URGENT: {n_urg} | ATTENTION: {n_att}"
    )

def run(service_level_z: float = 1.65) -> pd.DataFrame:
    _ensure_table()
    stock_df = _load_stock_snapshot()
    sales_df = _load_sales_history()
    df_result = _compute_reappro(stock_df, sales_df, service_level_z)
    _save(df_result)
    return df_result
