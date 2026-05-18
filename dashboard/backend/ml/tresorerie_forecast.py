import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sqlalchemy import text
from xgboost import XGBClassifier  # type: ignore
import joblib

warnings.filterwarnings("ignore")

from config import DW_ENGINE
from utils.logger import get_logger

logger = get_logger(__name__)

_MODEL_DIR = Path(__file__).parent / "models"
_MODEL_DIR.mkdir(exist_ok=True)
_MODEL_PATH = _MODEL_DIR / "tresorerie_xgb.joblib"
_MODEL_MAX_AGE_DAYS = 7

_DDL = """
CREATE TABLE ML_KPI11_TRESORERIE_FORECAST (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    run_date            DATE NOT NULL,
    forecast_date       DATE NOT NULL,
    horizon_bucket      VARCHAR(10) NOT NULL,
    layer               VARCHAR(20) NOT NULL,
    encaissements       NUMERIC(18,4) NULL,
    nb_reglements       INT NULL
)
"""

def _ensure_table() -> None:
    with DW_ENGINE.begin() as conn:
        conn.execute(text("IF OBJECT_ID('ML_KPI11_TRESORERIE_FORECAST', 'U') IS NOT NULL DROP TABLE ML_KPI11_TRESORERIE_FORECAST"))
        conn.execute(text(_DDL))

def _load_open_reglements() -> pd.DataFrame:
    sql = """
        WITH deduped AS (
            SELECT
                RT_Num,
                MAX(RT_Montant)         AS RT_Montant,
                MAX(id_date_echeance)   AS id_date_echeance,
                MAX(id_date_paiement)   AS id_date_paiement,
                MAX(id_client)          AS id_client,
                MAX(DR_Regle)           AS DR_Regle,
                MAX(delai_reel_jours)   AS delai_reel_jours,
                MAX(RT_NbJour)          AS RT_NbJour,
                MAX(id_mode_reg)        AS id_mode_reg
            FROM FAIT_REGLEMENTS
            WHERE RT_Num IS NOT NULL AND id_client IS NOT NULL
            GROUP BY RT_Num
        )
        SELECT
            r.RT_Num,
            r.RT_Montant,
            r.DR_Regle,
            r.delai_reel_jours,
            r.RT_NbJour,
            d_ech.date_val  AS date_echeance,
            d_pay.date_val  AS date_paiement,
            c.rfm_score,
            s.libelle_segment
        FROM deduped r
        LEFT JOIN DIM_DATE d_ech ON d_ech.id_date = r.id_date_echeance
        LEFT JOIN DIM_DATE d_pay ON d_pay.id_date = r.id_date_paiement
        LEFT JOIN DIM_CLIENT c  ON c.id_client   = r.id_client
        LEFT JOIN DIM_SEGMENT s ON s.id_segment  = c.id_segment
        WHERE r.DR_Regle = 0
        AND r.RT_Montant IS NOT NULL
        AND r.RT_Montant > 0
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)

    for col in ["date_echeance", "date_paiement"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    logger.info(f"[KPI-11] Open reglements: {len(df)} rows | total: {df['RT_Montant'].sum():,.0f}")
    return df

def _load_historical_payments() -> pd.DataFrame:
    sql = """
        WITH deduped AS (
            SELECT
                RT_Num,
                MAX(RT_Montant)         AS RT_Montant,
                MAX(id_date_echeance)   AS id_date_echeance,
                MAX(id_date_paiement)   AS id_date_paiement,
                MAX(id_client)          AS id_client,
                MAX(DR_Regle)           AS DR_Regle,
                MAX(delai_reel_jours)   AS delai_reel_jours,
                MAX(RT_NbJour)          AS RT_NbJour,
                MAX(id_mode_reg)        AS id_mode_reg
            FROM FAIT_REGLEMENTS
            WHERE RT_Num IS NOT NULL AND id_client IS NOT NULL
            GROUP BY RT_Num
        )
        SELECT
            r.RT_Montant,
            r.DR_Regle,
            r.delai_reel_jours,
            r.RT_NbJour,
            d_pay.date_val AS date_paiement,
            c.rfm_score,
            s.libelle_segment,
            m.libelle_mode_reg
        FROM deduped r
        LEFT JOIN DIM_DATE d_pay     ON d_pay.id_date     = r.id_date_paiement
        LEFT JOIN DIM_CLIENT c       ON c.id_client       = r.id_client
        LEFT JOIN DIM_SEGMENT s      ON s.id_segment      = c.id_segment
        LEFT JOIN DIM_MODE_REGLEMENT m ON m.id_mode_reg   = r.id_mode_reg
        WHERE r.DR_Regle = 1
        AND d_pay.date_val >= DATEADD(MONTH, -12, CAST(GETDATE() AS DATE))
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["date_paiement"] = pd.to_datetime(df["date_paiement"], errors="coerce")
    logger.info(f"[KPI-11] Historical paid: {len(df)} rows")
    return df

def _layer1_deterministic(open_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    today  = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=horizon)

    df = open_df[open_df["date_echeance"].notna()].copy()
    df["forecast_date"] = df["date_echeance"].dt.date
    df = df[
        (df["forecast_date"] >= today) &
        (df["forecast_date"] <= cutoff)
    ]

    if df.empty:
        return pd.DataFrame(columns=["forecast_date", "encaissements", "nb_reglements", "layer"])

    daily = (
        df.groupby("forecast_date")["RT_Montant"]
        .agg(encaissements="sum", nb_reglements="count")
        .reset_index()
    )
    daily["layer"] = "deterministic"
    logger.info(f"[KPI-11] Layer 1: {len(daily)} days | {daily['encaissements'].sum():,.0f}")
    return daily

def _layer2_statistical(open_df: pd.DataFrame, hist_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    today = datetime.now(timezone.utc).date()

    if not hist_df.empty and "libelle_segment" in hist_df.columns:
        segment_delay = (
            hist_df.dropna(subset=["delai_reel_jours"])
            .groupby("libelle_segment")["delai_reel_jours"]
            .mean()
            .to_dict()
        )
    else:
        segment_delay = {}

    global_avg_delay = float(hist_df["delai_reel_jours"].mean()) if not hist_df.empty else 30.0

    df = open_df[open_df["date_echeance"].isna()].copy()
    if df.empty:
        return pd.DataFrame(columns=["forecast_date", "encaissements", "nb_reglements", "layer"])

    def _expected_date(row):
        delay = segment_delay.get(row.get("libelle_segment"), global_avg_delay)
        base = row.get("date_paiement")
        if pd.isna(base):
            base = pd.Timestamp(today)
        return (base + pd.Timedelta(days=int(delay))).date()

    df["forecast_date"] = df.apply(_expected_date, axis=1)
    cutoff = today + timedelta(days=horizon)
    df = df[(df["forecast_date"] >= today) & (df["forecast_date"] <= cutoff)]

    if df.empty:
        return pd.DataFrame(columns=["forecast_date", "encaissements", "nb_reglements", "layer"])

    daily = (
        df.groupby("forecast_date")["RT_Montant"]
        .agg(encaissements="sum", nb_reglements="count")
        .reset_index()
    )
    daily["layer"] = "statistical"
    logger.info(f"[KPI-11] Layer 2: {len(daily)} days | {daily['encaissements'].sum():,.0f}")
    return daily

def _layer3_ml(open_df: pd.DataFrame, hist_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    today = datetime.now(timezone.utc).date()

    rfm_categories = hist_df["rfm_score"].dropna().unique() if not hist_df.empty else []
    seg_categories = hist_df["libelle_segment"].dropna().unique() if not hist_df.empty else []

    def _build_features(df: pd.DataFrame) -> pd.DataFrame:
        f = pd.DataFrame()
        f["montant_log"] = np.log1p(pd.to_numeric(df["RT_Montant"], errors="coerce").fillna(0))
        f["nb_jour"]     = pd.to_numeric(df["RT_NbJour"], errors="coerce").fillna(30)
        f["delai_hist"]  = pd.to_numeric(df["delai_reel_jours"], errors="coerce").fillna(0)

        f["rfm_num"] = pd.Categorical(df["rfm_score"], categories=rfm_categories).codes
        f["seg_num"] = pd.Categorical(df["libelle_segment"], categories=seg_categories).codes

        return f

    if hist_df.empty or len(hist_df) < 20:
        logger.warning("[KPI-11] Insufficient history for ML layer")
        return pd.DataFrame(columns=["forecast_date", "encaissements", "nb_reglements", "layer"])

    hist_df = hist_df.copy()
    hist_df["label"] = (
        pd.to_numeric(hist_df["delai_reel_jours"], errors="coerce").fillna(999) <= horizon
    ).astype(int)

    # Fallback if XGBoost is missing
    try:
        from xgboost import XGBClassifier
    except ImportError:
        logger.warning("[KPI-11] XGBoost not installed. Using segment-based historical probabilities.")
        if not hist_df.empty and "libelle_segment" in hist_df.columns:
            seg_probs = hist_df.groupby("libelle_segment")["label"].mean().to_dict()
        else:
            seg_probs = {}
        
        global_prob = hist_df["label"].mean() if not hist_df.empty else 0.5
        
        open_df = open_df.copy()
        open_df["prob_payment"] = open_df["libelle_segment"].map(seg_probs).fillna(global_prob)
        open_df["expected_amount"] = open_df["RT_Montant"] * open_df["prob_payment"]
        
        mid_day = today + timedelta(days=horizon // 2)
        open_df["forecast_date"] = mid_day
        
        daily = (
            open_df.groupby("forecast_date")["expected_amount"]
            .agg(encaissements="sum", nb_reglements="count")
            .reset_index()
        )
        daily["layer"] = "ml"
        logger.info(f"[KPI-11] Layer 3 (Fallback): {daily['encaissements'].sum():,.0f} expected")
        return daily

    X_train = _build_features(hist_df)
    y_train = hist_df["label"].values

    if y_train.sum() == 0 or y_train.sum() == len(y_train):
        logger.warning("[KPI-11] ML layer: degenerate labels — skipping")
        return pd.DataFrame(columns=["forecast_date", "encaissements", "nb_reglements", "layer"])

    model = None
    if _MODEL_PATH.exists():
        age_days = (
            datetime.now(timezone.utc).timestamp() - _MODEL_PATH.stat().st_mtime
        ) / 86400
        if age_days < _MODEL_MAX_AGE_DAYS:
            try:
                model = joblib.load(_MODEL_PATH)
                logger.info(f"[KPI-11] Loaded XGBoost model from cache (age={age_days:.1f}d)")
            except Exception as exc:
                logger.warning(f"[KPI-11] Cache load failed ({exc}), retraining.")

    if model is None:
        model = XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            eval_metric="logloss",
            random_state=42,
            verbosity=0,
        )
        model.fit(X_train, y_train)
        
        try:
            joblib.dump(model, _MODEL_PATH)
            logger.info(f"[KPI-11] Model saved to {_MODEL_PATH}")
        except Exception as exc:
            logger.warning(f"[KPI-11] Could not save model: {exc}")

    X_open = _build_features(open_df)
    proba  = model.predict_proba(X_open)[:, 1]

    open_df = open_df.copy()
    open_df["prob_payment"] = proba
    open_df["expected_amount"] = open_df["RT_Montant"] * open_df["prob_payment"]

    mid_day = today + timedelta(days=horizon // 2)
    open_df["forecast_date"] = mid_day

    daily = (
        open_df.groupby("forecast_date")["expected_amount"]
        .agg(encaissements="sum", nb_reglements="count")
        .reset_index()
    )
    daily["layer"] = "ml"

    logger.info(f"[KPI-11] Layer 3: {daily['encaissements'].sum():,.0f} expected")
    return daily

def _combine_and_bucket(layers: list[pd.DataFrame], horizon: int) -> pd.DataFrame:
    today = datetime.now(timezone.utc).date()

    if not layers or all(d.empty for d in layers):
        return pd.DataFrame()

    df = pd.concat([d for d in layers if not d.empty], ignore_index=True)
    df["forecast_date"] = pd.to_datetime(df["forecast_date"]).dt.date
    df["encaissements"] = pd.to_numeric(df["encaissements"], errors="coerce").fillna(0)
    df["nb_reglements"] = pd.to_numeric(df["nb_reglements"], errors="coerce").fillna(0)

    def _bucket(d) -> str:
        days = (d - today).days
        if days <= 30:
            return "30j"
        if days <= 60:
            return "60j"
        return "90j"

    df["horizon_bucket"] = df["forecast_date"].apply(_bucket)

    agg = (
        df.groupby(["forecast_date", "layer", "horizon_bucket"])
        .agg(
            encaissements=("encaissements", "sum"),
            nb_reglements=("nb_reglements", "sum"),
        )
        .reset_index()
    )

    return agg

def _save(df: pd.DataFrame) -> None:
    today = datetime.now(timezone.utc).date()
    with DW_ENGINE.begin() as conn:
        conn.execute(
            text("DELETE FROM ML_KPI11_TRESORERIE_FORECAST WHERE run_date = :d"),
            {"d": today},
        )

    if df.empty:
        logger.warning("[KPI-11] Nothing to save")
        return

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

    cols = ["forecast_date", "horizon_bucket", "layer", "encaissements", "nb_reglements"]
    rows = []
    for row in df[cols].itertuples(index=False):
        rows.append((today,) + tuple(_v(v) for v in row))

    sql = """
        INSERT INTO ML_KPI11_TRESORERIE_FORECAST
            (run_date, forecast_date, horizon_bucket, layer, encaissements, nb_reglements)
        VALUES (?,?,?,?,?,?)
    """
    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    logger.info(f"[KPI-11] Saved {len(rows)} rows to ML_KPI11_TRESORERIE_FORECAST")

def run(horizon: int = 90) -> pd.DataFrame:
    _ensure_table()

    open_df = _load_open_reglements()
    hist_df = _load_historical_payments()

    if open_df.empty:
        logger.warning("[KPI-11] No open reglements found — forecast will be empty")
        return pd.DataFrame()

    l1 = _layer1_deterministic(open_df, horizon)
    l2 = _layer2_statistical(open_df, hist_df, horizon)
    l3 = _layer3_ml(open_df, hist_df, horizon)

    result = _combine_and_bucket([l1, l2, l3], horizon)
    _save(result)
    return result
