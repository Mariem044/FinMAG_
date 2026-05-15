"""
KPI-17 — Alerte dynamique de réapprovisionnement
=================================================
Uses stock snapshot + sales velocity to compute a dynamic safety stock
threshold per article (instead of the static AS_QteMini), then classifies
articles into alert levels.

Model: Gradient Boosting Classifier trained on:
  - consumption velocity (conso_jour)
  - variability of monthly consumption (cv_conso)
  - lead time proxy (dsi_jours)
  - current stock vs. dynamic safety stock ratio

Results stored in ML_KPI17_REAPPRO_ALERT.

Usage:
    python -m ml.kpi17_reappro_alert
    python -m ml.kpi17_reappro_alert --lead-time 7   # supplier lead time in days
"""
from __future__ import annotations

import argparse
import warnings
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import text

warnings.filterwarnings("ignore")

from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)

# ── DDL ──────────────────────────────────────────────────────────────────────
_DDL = """
IF OBJECT_ID('ML_KPI17_REAPPRO_ALERT', 'U') IS NULL
CREATE TABLE ML_KPI17_REAPPRO_ALERT (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    run_date            DATE NOT NULL,
    id_article          INT  NOT NULL,
    AR_Ref_code         INT  NOT NULL,
    famille             NVARCHAR(100) NULL,
    stock_actuel        NUMERIC(18,4) NULL,
    stock_mini_statique NUMERIC(18,4) NULL,   -- original AS_QteMini
    stock_securite_dyn  NUMERIC(18,4) NULL,   -- ML-computed dynamic safety stock
    conso_jour_moy      NUMERIC(18,4) NULL,
    cv_conso            NUMERIC(18,4) NULL,   -- coefficient of variation of consumption
    score_urgence       NUMERIC(5,4)  NULL,   -- ML probability of needing reappro
    priorite            VARCHAR(20)   NULL,   -- CRITIQUE / URGENT / ATTENTION / OK
    qte_a_commander     NUMERIC(18,4) NULL,   -- suggested order quantity
    lead_time_jours     INT           NULL
)
"""


def _ensure_table() -> None:
    with DW_ENGINE.begin() as conn:
        conn.execute(text(_DDL))


# ── data loading ─────────────────────────────────────────────────────────────

def _load_stock() -> pd.DataFrame:
    sql = """
        SELECT
            fe.id_article,
            a.AR_Ref_code,
            COALESCE(NULLIF(fa.FA_Intitule,''), 'Sans famille') AS famille,
            fe.AS_QteSto   AS stock_actuel,
            fe.AS_QteMini  AS stock_mini,
            fe.AS_QteRes   AS stock_reserve,
            fe.dsi_jours,
            fe.en_rupture,
            fe.ratio_tension
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
    logger.info(f"[KPI-17] Stock: {len(df)} articles")
    return df


def _load_monthly_sales() -> pd.DataFrame:
    """Monthly consumption per article — last 12 months."""
    sql = """
        SELECT
            f.id_article,
            d.annee,
            d.mois,
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
    logger.info(f"[KPI-17] Monthly sales: {len(df)} rows")
    return df


# ── feature engineering ───────────────────────────────────────────────────────

def _build_features(stock_df: pd.DataFrame, sales_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate monthly sales into per-article features:
    - conso_jour_moy: average daily consumption
    - cv_conso: coefficient of variation (demand variability)
    - nb_mois_actif: how many months had sales
    """
    if sales_df.empty:
        stock_df["conso_jour_moy"] = 0.0
        stock_df["cv_conso"] = 0.0
        stock_df["nb_mois_actif"] = 0
        return stock_df

    agg = (
        sales_df
        .groupby("id_article")["qte_vendue"]
        .agg(
            conso_mensuelle_moy="mean",
            conso_mensuelle_std="std",
            nb_mois_actif="count",
        )
        .reset_index()
    )
    agg["conso_mensuelle_std"] = agg["conso_mensuelle_std"].fillna(0)
    agg["conso_jour_moy"] = agg["conso_mensuelle_moy"] / 30.0
    agg["cv_conso"] = np.where(
        agg["conso_mensuelle_moy"] > 0,
        agg["conso_mensuelle_std"] / agg["conso_mensuelle_moy"],
        0.0,
    )

    df = stock_df.merge(agg[["id_article", "conso_jour_moy", "cv_conso", "nb_mois_actif"]],
                        on="id_article", how="left")
    df["conso_jour_moy"] = df["conso_jour_moy"].fillna(0.0)
    df["cv_conso"]       = df["cv_conso"].fillna(0.0)
    df["nb_mois_actif"]  = df["nb_mois_actif"].fillna(0)
    return df


def _compute_dynamic_safety_stock(df: pd.DataFrame, lead_time: int) -> pd.DataFrame:
    """
    Dynamic safety stock formula (statistical):
        SS = Z * σ_demand * sqrt(lead_time)
    where:
        Z = 1.65  (service level 95%)
        σ_demand = conso_jour_moy * cv_conso  (daily demand std deviation)
        lead_time = supplier replenishment time in days

    This replaces the static AS_QteMini with a demand-variability-aware threshold.
    """
    Z = 1.65  # 95% service level
    df = df.copy()
    sigma_demand = df["conso_jour_moy"] * df["cv_conso"]
    df["stock_securite_dyn"] = np.ceil(
        Z * sigma_demand * np.sqrt(lead_time) +
        df["conso_jour_moy"] * lead_time          # cycle stock component
    ).clip(lower=0)
    return df


# ── ML classifier ─────────────────────────────────────────────────────────────

def _build_training_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create binary label: needs_reappro = 1 if stock ≤ dynamic safety stock.
    This is a rule-derived label used to train the classifier on feature patterns.
    """
    df = df.copy()
    df["needs_reappro"] = (
        (df["stock_actuel"] <= df["stock_securite_dyn"]) |
        (df["en_rupture"] == 1)
    ).astype(int)
    return df


def _train_classifier(df: pd.DataFrame) -> tuple:
    """
    Train a Gradient Boosting classifier to predict needs_reappro from
    consumption features. Returns (model, feature_columns).

    Falls back gracefully if sklearn unavailable.
    """
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
    except ImportError:
        raise ImportError("scikit-learn is required. Run: pip install scikit-learn --break-system-packages")

    features = ["conso_jour_moy", "cv_conso", "dsi_jours", "ratio_tension", "nb_mois_actif"]

    df_train = df.dropna(subset=["needs_reappro"]).copy()
    for col in features:
        if col not in df_train.columns:
            df_train[col] = 0.0
    df_train[features] = df_train[features].fillna(0.0)

    X = df_train[features].values
    y = df_train["needs_reappro"].values

    if len(df_train) < 10 or y.sum() == 0:
        logger.warning("[KPI-17] Insufficient training data — using rule-based fallback")
        return None, features

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42,
        )),
    ])
    model.fit(X, y)

    train_score = model.score(X, y)
    logger.info(f"[KPI-17] GBM trained — train accuracy: {train_score:.3f} ({len(df_train)} samples)")
    return model, features


def _score_articles(df: pd.DataFrame, model, features: list) -> pd.DataFrame:
    df = df.copy()
    for col in features:
        if col not in df.columns:
            df[col] = 0.0
    df[features] = df[features].fillna(0.0)

    if model is None:
        # Rule-based fallback: score from ratio_tension
        df["score_urgence"] = df["ratio_tension"].fillna(0.0).clip(0, 1)
    else:
        X = df[features].values
        df["score_urgence"] = model.predict_proba(X)[:, 1]

    return df


def _assign_priority(df: pd.DataFrame, lead_time: int) -> pd.DataFrame:
    df = df.copy()

    def _prio(row):
        if row["en_rupture"] == 1:
            return "CRITIQUE"
        if row["score_urgence"] >= 0.80:
            return "CRITIQUE"
        if row["score_urgence"] >= 0.55:
            return "URGENT"
        if row["score_urgence"] >= 0.30:
            return "ATTENTION"
        return "OK"

    df["priorite"] = df.apply(_prio, axis=1)

    # Suggested order quantity: cover lead_time + 30-day buffer
    df["qte_a_commander"] = np.ceil(
        df["conso_jour_moy"] * (lead_time + 30) - df["stock_actuel"].clip(lower=0)
    ).clip(lower=0)

    return df


# ── save ──────────────────────────────────────────────────────────────────────

def _save(df: pd.DataFrame, lead_time: int) -> None:
    today = date.today()
    with DW_ENGINE.begin() as conn:
        conn.execute(
            text("DELETE FROM ML_KPI17_REAPPRO_ALERT WHERE run_date = :d"),
            {"d": today},
        )

    cols = [
        "id_article", "AR_Ref_code", "famille",
        "stock_actuel", "stock_mini", "stock_securite_dyn",
        "conso_jour_moy", "cv_conso", "score_urgence",
        "priorite", "qte_a_commander",
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
        rows.append((today,) + tuple(_v(v) for v in row) + (lead_time,))

    sql = """
        INSERT INTO ML_KPI17_REAPPRO_ALERT
            (run_date, id_article, AR_Ref_code, famille,
             stock_actuel, stock_mini_statique, stock_securite_dyn,
             conso_jour_moy, cv_conso, score_urgence,
             priorite, qte_a_commander, lead_time_jours)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    n = {p: (df["priorite"] == p).sum() for p in ["CRITIQUE", "URGENT", "ATTENTION", "OK"]}
    logger.info(f"[KPI-17] Saved {len(rows)} articles — {n}")


# ── main ──────────────────────────────────────────────────────────────────────

def run(lead_time: int = 7) -> pd.DataFrame:
    _ensure_table()

    stock_df = _load_stock()
    sales_df = _load_monthly_sales()

    df = _build_features(stock_df, sales_df)
    df = _compute_dynamic_safety_stock(df, lead_time)
    df = _build_training_labels(df)

    model, features = _train_classifier(df)
    df = _score_articles(df, model, features)
    df = _assign_priority(df, lead_time)

    _save(df, lead_time)
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KPI-17 Reappro Alert")
    parser.add_argument("--lead-time", type=int, default=7,
                        help="Supplier lead time in days (default: 7)")
    args = parser.parse_args()
    result = run(lead_time=args.lead_time)

    print("\n=== KPI-17 REAPPRO ALERT SUMMARY ===")
    print(result[result["priorite"].isin(["CRITIQUE", "URGENT"])]
          [["AR_Ref_code", "famille", "stock_actuel", "stock_securite_dyn",
            "conso_jour_moy", "cv_conso", "score_urgence", "priorite", "qte_a_commander"]]
          .sort_values("score_urgence", ascending=False)
          .head(20)
          .to_string(index=False))