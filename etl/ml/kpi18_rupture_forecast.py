"""
KPI-18 — Prévision de consommation et date de rupture estimée
=============================================================
Uses existing DSI data from FAIT_ECRITURES + FAIT_LIGNES_VENTE to train
a per-article linear regression on consumption velocity, then predicts:
  - daily consumption rate
  - estimated rupture date
  - confidence level

Results stored in ML_KPI18_RUPTURE_FORECAST.

Usage:
    python -m ml.kpi18_rupture_forecast
    python -m ml.kpi18_rupture_forecast --horizon 30   # alert window in days
"""
from __future__ import annotations

import argparse
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

warnings.filterwarnings("ignore")

from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)

_MODEL_DIR = Path(__file__).parent / "models"
_MODEL_DIR.mkdir(exist_ok=True)
_MODEL_PATH = _MODEL_DIR / "kpi18_consumption.joblib"
_MODEL_MAX_AGE_DAYS = 7

# ── DDL ──────────────────────────────────────────────────────────────────────
_DDL = """
IF OBJECT_ID('ML_KPI18_RUPTURE_FORECAST', 'U') IS NULL
CREATE TABLE ML_KPI18_RUPTURE_FORECAST (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    run_date            DATE NOT NULL,
    id_article          INT  NOT NULL,
    AR_Ref_code         INT  NOT NULL,
    famille             NVARCHAR(100) NULL,
    stock_actuel        NUMERIC(18,4) NULL,
    stock_mini          NUMERIC(18,4) NULL,
    conso_jour_moy      NUMERIC(18,4) NULL,   -- avg daily consumption
    conso_jour_pred     NUMERIC(18,4) NULL,   -- ML-predicted daily consumption
    date_rupture_regle  DATE NULL,            -- rule-based: stock/conso_moy
    date_rupture_ml     DATE NULL,            -- ML-predicted rupture date
    jours_avant_rupture INT  NULL,
    priorite            VARCHAR(20) NULL,     -- CRITIQUE / URGENT / ATTENTION / OK
    confiance           NUMERIC(5,2) NULL,    -- model R² score for this article
    en_rupture_actuel   SMALLINT NOT NULL DEFAULT 0
)
"""


def _ensure_table() -> None:
    with DW_ENGINE.begin() as conn:
        conn.execute(text(_DDL))


# ── data loading ─────────────────────────────────────────────────────────────

def _load_stock_snapshot() -> pd.DataFrame:
    """Current stock from FAIT_ECRITURES type_ligne=4."""
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
    """
    Monthly sales quantities per article for the last 24 months.
    Used to train per-article consumption regression.
    """
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


# ── ML: per-article consumption prediction ───────────────────────────────────

def _predict_consumption(sales_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pour chaque article, ajuste une régression linéaire sur la consommation
    mensuelle pour détecter une tendance. Renvoie la consommation prédite
    par jour et le R² par article.

    Persistance : les modèles entraînés sont sauvegardés dans un dict
    sérialisé (joblib). Si le fichier a moins de 7 jours, il est rechargé
    sans ré-entraînement.
    """
    try:
        import joblib
        from sklearn.linear_model import LinearRegression  # type: ignore
        from sklearn.metrics import r2_score               # type: ignore
    except ImportError:
        raise ImportError("scikit-learn and joblib are required.")

    # ── try to load cached models ───────────────────────────────────
    article_ids_set = set(sales_df["id_article"].unique())
    cached_models   = None
    if _MODEL_PATH.exists():
        age_days = (
            datetime.now(timezone.utc).timestamp() - _MODEL_PATH.stat().st_mtime
        ) / 86400
        if age_days < _MODEL_MAX_AGE_DAYS:
            try:
                cached = joblib.load(_MODEL_PATH)
                if cached.get("article_ids") == article_ids_set:
                    cached_models = cached["models"]
                    logger.info(
                        f"[KPI-18] Loaded consumption models from cache "
                        f"(age={age_days:.1f}d, {len(cached_models)} articles)"
                    )
            except Exception as exc:
                logger.warning(f"[KPI-18] Cache load failed ({exc}), retraining.")

    if cached_models is not None:
        # Reconstruct results from cached slopes/intercepts
        results = []
        for id_article, rec in cached_models.items():
            results.append({
                "id_article":      id_article,
                "conso_jour_moy":  rec["conso_jour_moy"],
                "conso_jour_pred": rec["conso_jour_pred"],
                "confiance":       rec["confiance"],
            })
        return pd.DataFrame(results)

    # ── train per-article ───────────────────────────────────────────
    results       = []
    models_cache  = {}
    r2_values     = []

    for id_article, grp in sales_df.groupby("id_article"):
        grp = grp.sort_values("mois_date").copy()
        grp["t"] = range(len(grp))
        n = len(grp)
        y = grp["qte_vendue"].values.astype(float)

        if n < 3:
            conso_moy = float(y.mean()) if n > 0 else 0.0
            r2        = 0.0
            conso_pred = conso_moy
        else:
            X = grp[["t"]].values
            model = LinearRegression()
            model.fit(X, y)
            y_pred     = model.predict(X)
            r2         = max(0.0, float(r2_score(y, y_pred)))
            conso_pred = max(0.0, float(model.predict([[n]])[0]))
            conso_moy  = float(y.mean())

        r2_values.append(r2)
        conso_jour_moy  = conso_moy  / 30.0
        conso_jour_pred = conso_pred / 30.0

        rec = {
            "conso_jour_moy":  conso_jour_moy,
            "conso_jour_pred": conso_jour_pred,
            "confiance":       round(r2 * 100, 2),
        }
        results.append({"id_article": id_article, **rec})
        models_cache[id_article] = rec

    # Log CV summary
    if r2_values:
        import numpy as _np
        logger.info(
            f"[KPI-18] Entraînement terminé — "
            f"R² moyen={_np.mean(r2_values):.3f} ± {_np.std(r2_values):.3f} "
            f"({len(r2_values)} articles)"
        )

    # Save to cache
    try:
        joblib.dump(
            {"models": models_cache, "article_ids": article_ids_set},
            _MODEL_PATH,
        )
        logger.info(f"[KPI-18] Modèles sauvegardés dans {_MODEL_PATH}")
    except Exception as exc:
        logger.warning(f"[KPI-18] Impossible de sauvegarder les modèles : {exc}")

    return pd.DataFrame(results)


# ── rupture date calculation ──────────────────────────────────────────────────

def _compute_rupture_dates(
    stock_df: pd.DataFrame,
    conso_df: pd.DataFrame,
    horizon: int,
) -> pd.DataFrame:
    today = date.today()

    df = stock_df.merge(conso_df, on="id_article", how="left")

    def _rupture_date(stock, conso):
        if conso is None or conso <= 0 or stock is None:
            return None
        days = stock / conso
        return today + timedelta(days=int(days))

    df["date_rupture_regle"] = df.apply(
        lambda r: _rupture_date(r["stock_actuel"], r["conso_jour_moy"]), axis=1
    )
    df["date_rupture_ml"] = df.apply(
        lambda r: _rupture_date(r["stock_actuel"], r["conso_jour_pred"]), axis=1
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
    df["en_rupture_actuel"] = df["en_rupture"].fillna(0).astype(int)

    return df


# ── save results ─────────────────────────────────────────────────────────────

def _save(df: pd.DataFrame) -> None:
    today = datetime.now(timezone.utc).date()
    with DW_ENGINE.begin() as conn:
        conn.execute(
            text("DELETE FROM ML_KPI18_RUPTURE_FORECAST WHERE run_date = :d"),
            {"d": today},
        )

    cols = [
        "id_article", "AR_Ref_code", "famille",
        "stock_actuel", "stock_mini",
        "conso_jour_moy", "conso_jour_pred",
        "date_rupture_regle", "date_rupture_ml",
        "jours_avant_rupture", "priorite", "confiance",
        "en_rupture_actuel",
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
            (run_date, id_article, AR_Ref_code, famille,
             stock_actuel, stock_mini,
             conso_jour_moy, conso_jour_pred,
             date_rupture_regle, date_rupture_ml,
             jours_avant_rupture, priorite, confiance,
             en_rupture_actuel)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    n_critique = (df["priorite"] == "CRITIQUE").sum()
    n_urgent   = (df["priorite"] == "URGENT").sum()
    logger.info(
        f"[KPI-18] Saved {len(rows)} articles — "
        f"CRITIQUE: {n_critique} | URGENT: {n_urgent}"
    )


# ── main ──────────────────────────────────────────────────────────────────────

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KPI-18 Rupture Forecast")
    parser.add_argument("--horizon", type=int, default=30, help="Alert window in days")
    args = parser.parse_args()
    result = run(horizon=args.horizon)

    # Print summary
    print("\n=== KPI-18 RUPTURE FORECAST SUMMARY ===")
    print(result[result["priorite"].isin(["CRITIQUE", "URGENT"])]
          [["AR_Ref_code", "famille", "stock_actuel", "conso_jour_pred",
            "jours_avant_rupture", "priorite", "confiance"]]
          .sort_values("jours_avant_rupture")
          .head(20)
          .to_string(index=False))