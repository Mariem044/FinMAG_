"""
KPI-22 — Segmentation RFM avancée avec K-Means
===============================================
Upgrades the rule-based RFM scoring in DIM_CLIENT to a proper ML clustering
approach using K-Means on normalized R/F/M scores.

Cluster profiles are auto-labeled by comparing centroid values to
meaningful business thresholds (Champion, Fidèle, À risque, Dormant,
Nouveau) — the same labels as the rule-based version but now data-driven.

Results stored in ML_KPI22_RFM_SEGMENTS and written back to DIM_CLIENT
(rfm_score column) so the existing API/dashboard continues to work.

Usage:
    python -m ml.kpi22_rfm_kmeans
    python -m ml.kpi22_rfm_kmeans --n-clusters 5
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
IF OBJECT_ID('ML_KPI22_RFM_SEGMENTS', 'U') IS NULL
CREATE TABLE ML_KPI22_RFM_SEGMENTS (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    run_date            DATE NOT NULL,
    id_client           INT  NOT NULL,
    CT_Num_code         INT  NOT NULL,
    rfm_recence_jours   INT  NULL,
    rfm_frequence       INT  NULL,
    rfm_montant_12m     NUMERIC(18,4) NULL,
    r_score             SMALLINT NULL,      -- 1-5 recency score
    f_score             SMALLINT NULL,      -- 1-5 frequency score
    m_score             SMALLINT NULL,      -- 1-5 monetary score
    rfm_composite       NUMERIC(5,2) NULL,  -- weighted composite (used for clustering)
    cluster_id          SMALLINT NULL,      -- raw K-Means cluster (0-based)
    rfm_segment         VARCHAR(30) NULL,   -- business label
    silhouette_score    NUMERIC(5,4) NULL,  -- model quality metric
    inertia             NUMERIC(18,2) NULL
)
"""


def _ensure_table() -> None:
    with DW_ENGINE.begin() as conn:
        conn.execute(text(_DDL))


# ── data loading ─────────────────────────────────────────────────────────────

def _load_rfm_data() -> pd.DataFrame:
    """
    Load existing RFM metrics from DIM_CLIENT.
    These are computed by _compute_rfm_scores() in pipeline.py.
    """
    sql = """
        SELECT
            id_client,
            CT_Num_code,
            rfm_recence_jours,
            rfm_frequence,
            rfm_montant_12m
        FROM DIM_CLIENT
        WHERE rfm_recence_jours IS NOT NULL
        OR rfm_frequence IS NOT NULL
        OR rfm_montant_12m IS NOT NULL
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    logger.info(f"[KPI-22] Loaded {len(df)} clients with RFM data")
    return df


# ── feature engineering ───────────────────────────────────────────────────────

def _score_rfm(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert raw R/F/M values to 1-5 quintile scores.
    R: lower recency = better → reverse quintile
    F: higher frequency = better
    M: higher monetary = better
    """
    df = df.copy()

    # Fill nulls with worst-case values for scoring
    df["rfm_recence_jours"] = df["rfm_recence_jours"].fillna(df["rfm_recence_jours"].max() + 1)
    df["rfm_frequence"]     = df["rfm_frequence"].fillna(0)
    df["rfm_montant_12m"]   = df["rfm_montant_12m"].fillna(0)

    def _quintile(series: pd.Series, ascending: bool = True) -> pd.Series:
        """Assign 1-5 quintile labels."""
        try:
            labels = [1, 2, 3, 4, 5] if ascending else [5, 4, 3, 2, 1]
            return pd.qcut(series.rank(method="first"), q=5, labels=labels).astype(int)
        except Exception:
            # Fallback for low-cardinality series
            return pd.Series([3] * len(series), index=series.index)

    df["r_score"] = _quintile(df["rfm_recence_jours"], ascending=False)  # low recency = good
    df["f_score"] = _quintile(df["rfm_frequence"],     ascending=True)
    df["m_score"] = _quintile(df["rfm_montant_12m"],   ascending=True)

    # Weighted composite: M > F > R (monetary impact is most important)
    df["rfm_composite"] = (
        0.25 * df["r_score"] +
        0.30 * df["f_score"] +
        0.45 * df["m_score"]
    )

    return df


# ── K-Means clustering ────────────────────────────────────────────────────────

def _cluster(df: pd.DataFrame, n_clusters: int) -> tuple[pd.DataFrame, float, float]:
    """
    Fit K-Means on [r_score, f_score, m_score] and return:
    - df with cluster_id column
    - silhouette score
    - inertia
    """
    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import silhouette_score
    except ImportError:
        raise ImportError("scikit-learn required. Run: pip install scikit-learn --break-system-packages")

    features = ["r_score", "f_score", "m_score"]
    X = df[features].values.astype(float)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(
        n_clusters=n_clusters,
        init="k-means++",
        n_init=20,
        max_iter=500,
        random_state=42,
    )
    labels = kmeans.fit_predict(X_scaled)

    # Quality metrics
    sil = float(silhouette_score(X_scaled, labels)) if len(set(labels)) > 1 else 0.0
    inertia = float(kmeans.inertia_)

    logger.info(f"[KPI-22] K-Means: k={n_clusters} | silhouette={sil:.3f} | inertia={inertia:,.0f}")

    df = df.copy()
    df["cluster_id"] = labels

    # Label each cluster by its centroid profile (inverse-transform for readability)
    centroids = scaler.inverse_transform(kmeans.cluster_centers_)
    centroid_df = pd.DataFrame(centroids, columns=features)
    centroid_df["cluster_id"] = range(n_clusters)

    def _label_cluster(row) -> str:
        r = row["r_score"]
        f = row["f_score"]
        m = row["m_score"]
        # High R score (low recency), high F, high M → Champion
        if r >= 4 and f >= 4 and m >= 4:
            return "Champion"
        if r >= 3 and f >= 3 and m >= 3:
            return "Fidèle"
        if r >= 3 and (f >= 2 or m >= 3):
            return "À risque"
        if r <= 2 and f == 1 and m <= 2:
            return "Dormant"
        if f == 1 and m <= 2:
            return "Nouveau"
        return "À risque"

    centroid_df["rfm_segment"] = centroid_df.apply(_label_cluster, axis=1)
    cluster_labels = dict(zip(centroid_df["cluster_id"], centroid_df["rfm_segment"]))

    df["rfm_segment"] = df["cluster_id"].map(cluster_labels)

    logger.info(f"[KPI-22] Cluster distribution:\n{df['rfm_segment'].value_counts().to_string()}")

    return df, sil, inertia


# ── elbow method to find optimal k ───────────────────────────────────────────

def _find_optimal_k(df: pd.DataFrame, k_min: int = 3, k_max: int = 7) -> int:
    """Use silhouette score to pick optimal k."""
    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import silhouette_score
    except ImportError:
        return 4  # safe default

    features = ["r_score", "f_score", "m_score"]
    X = StandardScaler().fit_transform(df[features].values.astype(float))

    best_k, best_sil = k_min, -1.0
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, init="k-means++", n_init=10, random_state=42)
        labels = km.fit_predict(X)
        if len(set(labels)) < 2:
            continue
        sil = float(silhouette_score(X, labels))
        logger.debug(f"[KPI-22] k={k} → silhouette={sil:.3f}")
        if sil > best_sil:
            best_sil, best_k = sil, k

    logger.info(f"[KPI-22] Optimal k={best_k} (silhouette={best_sil:.3f})")
    return best_k


# ── save & write-back ─────────────────────────────────────────────────────────

def _save(df: pd.DataFrame, sil: float, inertia: float) -> None:
    today = date.today()
    with DW_ENGINE.begin() as conn:
        conn.execute(
            text("DELETE FROM ML_KPI22_RFM_SEGMENTS WHERE run_date = :d"),
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
        "id_client", "CT_Num_code",
        "rfm_recence_jours", "rfm_frequence", "rfm_montant_12m",
        "r_score", "f_score", "m_score",
        "rfm_composite", "cluster_id", "rfm_segment",
    ]
    rows = []
    for row in df[cols].itertuples(index=False):
        rows.append((today,) + tuple(_v(v) for v in row) + (round(sil, 4), round(inertia, 2)))

    sql = """
        INSERT INTO ML_KPI22_RFM_SEGMENTS
            (run_date, id_client, CT_Num_code,
             rfm_recence_jours, rfm_frequence, rfm_montant_12m,
             r_score, f_score, m_score,
             rfm_composite, cluster_id, rfm_segment,
             silhouette_score, inertia)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    logger.info(f"[KPI-22] Saved {len(rows)} rows to ML_KPI22_RFM_SEGMENTS")


def _writeback_dim_client(df: pd.DataFrame) -> None:
    """
    Update DIM_CLIENT.rfm_score with ML-derived segments
    so the existing dashboard continues to work without changes.
    """
    updates = df[["id_client", "rfm_segment"]].dropna(subset=["rfm_segment"])
    if updates.empty:
        return

    rows = [(row.rfm_segment, int(row.id_client)) for row in updates.itertuples(index=False)]
    sql = "UPDATE DIM_CLIENT SET rfm_score = ? WHERE id_client = ?"

    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    logger.info(f"[KPI-22] DIM_CLIENT.rfm_score updated for {len(rows)} clients")


# ── main ──────────────────────────────────────────────────────────────────────

def run(n_clusters: int = None) -> pd.DataFrame:
    _ensure_table()

    df = _load_rfm_data()

    if df.empty:
        logger.warning("[KPI-22] No RFM data found. Run ETL pipeline first.")
        return df

    df = _score_rfm(df)

    if n_clusters is None:
        n_clusters = _find_optimal_k(df)

    df, sil, inertia = _cluster(df, n_clusters)
    _save(df, sil, inertia)
    _writeback_dim_client(df)

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KPI-22 RFM K-Means Segmentation")
    parser.add_argument("--n-clusters", type=int, default=None,
                        help="Number of clusters (default: auto via silhouette)")
    args = parser.parse_args()
    result = run(n_clusters=args.n_clusters)

    print("\n=== KPI-22 RFM SEGMENTATION SUMMARY ===")
    if not result.empty:
        print(result["rfm_segment"].value_counts().to_string())
        print("\nSample per segment:")
        print(result[["CT_Num_code", "rfm_recence_jours", "rfm_frequence",
                       "rfm_montant_12m", "r_score", "f_score", "m_score",
                       "rfm_composite", "rfm_segment"]]
              .groupby("rfm_segment").head(3)
              .to_string(index=False))