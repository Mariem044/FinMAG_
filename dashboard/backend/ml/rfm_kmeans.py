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

_MODEL_DIR = Path(__file__).parent / "models"
_MODEL_DIR.mkdir(exist_ok=True)
_MODEL_PATH  = _MODEL_DIR / "kmeans.joblib"
_MODEL_MAX_AGE_DAYS = 7

_DDL = """
CREATE TABLE ML_KPI22_RFM_SEGMENTS (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    run_date            DATE NOT NULL,
    recence_jours       INT  NULL,
    frequence_commandes INT  NULL,
    montant_total       NUMERIC(18,4) NULL,
    segment_label       VARCHAR(30) NULL,
    silhouette_score    NUMERIC(5,4) NULL,
    inertia             NUMERIC(18,2) NULL,
    nb_clusters         INT NULL
)
"""

def _ensure_table() -> None:
    with DW_ENGINE.begin() as conn:
        conn.execute(text("IF OBJECT_ID('ML_KPI22_RFM_SEGMENTS', 'U') IS NOT NULL DROP TABLE ML_KPI22_RFM_SEGMENTS"))
        conn.execute(text(_DDL))

def _load_rfm_data() -> pd.DataFrame:
    sql = """
        WITH latest_date AS (
            SELECT MAX(d.date_val) AS max_dt
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DATE d ON d.id_date = f.id_date
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            WHERE dom.DO_Domaine = 0
        ),
        client_stats AS (
            SELECT
                f.id_client,
                COUNT(DISTINCT CONCAT(f.DO_Piece_hash, '-', COALESCE(f.id_type_doc, 0))) AS freq,
                SUM(f.DL_MontantHT) AS mont,
                MAX(d.date_val) AS last_purchase_dt
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DATE d ON d.id_date = f.id_date
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            WHERE dom.DO_Domaine = 0
            GROUP BY f.id_client
        )
        SELECT
            c.id_client,
            c.CT_Num_code,
            DATEDIFF(day, cs.last_purchase_dt, ld.max_dt) AS rfm_recence_jours,
            cs.freq AS rfm_frequence,
            cs.mont AS rfm_montant_12m
        FROM DIM_CLIENT c
        JOIN client_stats cs ON cs.id_client = c.id_client
        CROSS JOIN latest_date ld
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    logger.info(f"[KPI-22] Loaded {len(df)} clients with RFM data")
    return df

def _score_rfm(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["rfm_recence_jours"] = df["rfm_recence_jours"].fillna(df["rfm_recence_jours"].max() + 1)
    df["rfm_frequence"]     = df["rfm_frequence"].fillna(0)
    df["rfm_montant_12m"]   = df["rfm_montant_12m"].fillna(0)

    def _quintile(series: pd.Series, ascending: bool = True) -> pd.Series:
        try:
            labels = [1, 2, 3, 4, 5] if ascending else [5, 4, 3, 2, 1]
            return pd.qcut(series.rank(method="first"), q=5, labels=labels).astype(int)
        except Exception:
            return pd.Series([3] * len(series), index=series.index)

    df["r_score"] = _quintile(df["rfm_recence_jours"], ascending=False)
    df["f_score"] = _quintile(df["rfm_frequence"],     ascending=True)
    df["m_score"] = _quintile(df["rfm_montant_12m"],   ascending=True)

    df["rfm_composite"] = (
        0.25 * df["r_score"] +
        0.30 * df["f_score"] +
        0.45 * df["m_score"]
    )

    return df

def _cluster(
    df: pd.DataFrame,
    n_clusters: int,
) -> tuple[pd.DataFrame, float, float]:
    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import silhouette_score
    except ImportError:
        logger.warning("[KPI-22] scikit-learn missing. Using rules-based RFM scoring.")
        
        def _get_segment(score):
            if score >= 4.0: return "Champion"
            if score >= 3.0: return "Fidèle"
            if score >= 2.0: return "Potentiel"
            if score >= 1.5: return "À risque"
            return "Dormant"
            
        df = df.copy()
        df["segment_label"] = df["rfm_composite"].apply(_get_segment)
        return df, 0.0, 0.0

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
    kmeans.fit(X_scaled)

    labels  = kmeans.predict(X_scaled)
    inertia = float(kmeans.inertia_)
    sil = float(silhouette_score(X_scaled, labels)) if len(set(labels)) > 1 else 0.0

    df = df.copy()
    df["cluster_id"] = labels

    SEGMENT_LABELS = ["Champion", "Fidèle", "Potentiel", "À risque", "Dormant"]

    centroids_raw = scaler.inverse_transform(kmeans.cluster_centers_)
    centroid_df   = pd.DataFrame(centroids_raw, columns=features)
    centroid_df["cluster_id"] = range(n_clusters)

    centroid_df["centroid_composite"] = (
        0.25 * centroid_df["r_score"] +
        0.30 * centroid_df["f_score"] +
        0.45 * centroid_df["m_score"]
    )

    centroid_df = centroid_df.sort_values("centroid_composite", ascending=False)
    centroid_df["segment_label"] = [
        SEGMENT_LABELS[i] if i < len(SEGMENT_LABELS) else f"Cluster {i}"
        for i in range(len(centroid_df))
    ]
    cluster_labels = dict(zip(centroid_df["cluster_id"], centroid_df["segment_label"]))

    df["segment_label"] = df["cluster_id"].map(cluster_labels)

    return df, sil, inertia

def _save(df: pd.DataFrame, sil: float, inertia: float) -> None:
    today = datetime.now(timezone.utc).date()
    with DW_ENGINE.begin() as conn:
        conn.execute(
            text("DELETE FROM ML_KPI22_RFM_SEGMENTS WHERE run_date = :d"),
            {"d": today},
        )

    cols = [
        "rfm_recence_jours", "rfm_frequence", "rfm_montant_12m", "segment_label"
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
        rows.append((today,) + tuple(_v(v) for v in row) + (sil, inertia, 5))

    sql = """
        INSERT INTO ML_KPI22_RFM_SEGMENTS
            (run_date, recence_jours, frequence_commandes, montant_total, segment_label,
             silhouette_score, inertia, nb_clusters)
        VALUES (?,?,?,?,?,?,?,?)
    """
    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    logger.info(f"[KPI-22] Saved {len(rows)} rows to ML_KPI22_RFM_SEGMENTS")

def _writeback_dim_client(df: pd.DataFrame) -> None:
    if "segment_label" not in df.columns:
        return
    updates = df[["id_client", "segment_label"]].dropna(subset=["segment_label"])
    if updates.empty:
        return

    rows = [(row.segment_label, int(row.id_client)) for row in updates.itertuples(index=False)]
    sql = "UPDATE DIM_CLIENT SET rfm_score = ? WHERE id_client = ?"

    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    logger.info(f"[KPI-22] DIM_CLIENT.rfm_score updated for {len(rows)} clients")

def run(n_clusters: int = 5) -> pd.DataFrame:
    _ensure_table()

    df = _load_rfm_data()

    if df.empty:
        logger.warning("[KPI-22] No RFM data found. Run ETL pipeline first.")
        return df

    df = _score_rfm(df)
    df, sil, inertia = _cluster(df, n_clusters)
    
    _save(df, sil, inertia)
    _writeback_dim_client(df)

    return df
