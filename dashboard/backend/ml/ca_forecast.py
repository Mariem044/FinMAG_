import warnings
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import numpy as np
from sqlalchemy import text
import joblib

warnings.filterwarnings("ignore")

from config import DW_ENGINE
from utils.logger import get_logger

logger = get_logger(__name__)

_MODEL_DIR = Path(__file__).parent / "models"
_MODEL_DIR.mkdir(exist_ok=True)
_MODEL_PATH = _MODEL_DIR / "ca_prophet.joblib"
_MODEL_MAX_AGE_DAYS = 7

_DDL = """
IF OBJECT_ID('ML_KPI05_CA_FORECAST', 'U') IS NULL
CREATE TABLE ML_KPI05_CA_FORECAST (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    run_date        DATE NOT NULL,
    ds              DATE NOT NULL,
    yhat            NUMERIC(18,4) NOT NULL,
    yhat_lower      NUMERIC(18,4) NOT NULL,
    yhat_upper      NUMERIC(18,4) NOT NULL,
    is_historical   SMALLINT NOT NULL DEFAULT 0
)
"""

def _ensure_table() -> None:
    with DW_ENGINE.begin() as conn:
        conn.execute(text(_DDL))

def _load_monthly_ca() -> pd.DataFrame:
    sql = """
        SELECT
            DATEFROMPARTS(d.annee, d.mois, 1) AS ds,
            SUM(f.DL_MontantHT)               AS y
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        JOIN DIM_DATE    d   ON d.id_date      = f.id_date
        WHERE dom.DO_Domaine = 0
        GROUP BY d.annee, d.mois
        HAVING COUNT(*) > 100
        ORDER BY ds
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"]  = pd.to_numeric(df["y"], errors="coerce")
    df = df.dropna().sort_values("ds").reset_index(drop=True)
    logger.info(f"[KPI-05] Loaded {len(df)} monthly observations "
                f"({df['ds'].min().date()} -> {df['ds'].max().date()})")
    return df

def _train_and_forecast_fallback(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    logger.info("[KPI-05] Running Academic Multiplicative Seasonal Decomposition Fallback...")
    n_obs = len(df)
    t = np.arange(n_obs)
    y = df["y"].values.astype(float)
    
    if n_obs >= 2:
        alpha, beta = np.polyfit(t, y, 1)
    else:
        alpha, beta = 0.0, float(y[0]) if n_obs > 0 else 0.0
    
    trend = alpha * t + beta
    
    trend_safe = np.where(trend <= 0, 1e-5, trend)
    seasonal_ratios = y / trend_safe
    
    df_temp = df.copy()
    df_temp["ratio"] = seasonal_ratios
    df_temp["month"] = df_temp["ds"].dt.month
    
    monthly_seasonality = df_temp.groupby("month")["ratio"].mean().to_dict()
    for m in range(1, 13):
        if m not in monthly_seasonality:
            monthly_seasonality[m] = 1.0
            
    mean_ratio = np.mean(list(monthly_seasonality.values()))
    if mean_ratio > 0:
        for m in monthly_seasonality:
            monthly_seasonality[m] /= mean_ratio
            
    last_ds = df["ds"].max()
    future_dates = [last_ds + pd.DateOffset(months=i) for i in range(1, horizon + 1)]
    future_df = pd.DataFrame({"ds": future_dates})
    future_df["y"] = np.nan
    
    full_df = pd.concat([df, future_df], ignore_index=True)
    full_df["t"] = np.arange(len(full_df))
    full_df["month"] = full_df["ds"].dt.month
    
    pred_trend = alpha * full_df["t"].values + beta
    full_df["yhat"] = pred_trend * full_df["month"].map(monthly_seasonality)
    
    residuals = y - (trend * df_temp["month"].map(monthly_seasonality))
    std_err = np.std(residuals) if len(residuals) > 1 else 0.1 * np.mean(y) if len(y) > 0 else 1.0
    
    full_df["yhat_lower"] = full_df["yhat"] - 1.28 * std_err
    full_df["yhat_upper"] = full_df["yhat"] + 1.28 * std_err
    
    last_hist = df["ds"].max()
    full_df["is_historical"] = (full_df["ds"] <= last_hist).astype(int)
    
    result = full_df[["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical"]].copy()
    result["yhat"]       = result["yhat"].clip(lower=0)
    result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
    result["yhat_upper"] = result["yhat_upper"].clip(lower=0)
    
    return result

def _train_and_forecast(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    try:
        from prophet import Prophet  # type: ignore
    except ImportError:
        logger.warning("[KPI-05] Prophet not installed. Using pure mathematical fallback.")
        return _train_and_forecast_fallback(df, horizon)

    model = None
    if _MODEL_PATH.exists():
        model_age_days = (
            datetime.now(timezone.utc).timestamp() - _MODEL_PATH.stat().st_mtime
        ) / 86400
        if model_age_days < _MODEL_MAX_AGE_DAYS:
            try:
                model = joblib.load(_MODEL_PATH)
                logger.info(
                    f"[KPI-05] Loaded Prophet model from cache "
                    f"(age={model_age_days:.1f}d)"
                )
            except Exception as exc:
                logger.warning(f"[KPI-05] Cache load failed ({exc}), retraining.")
                model = None

    if model is None:
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            seasonality_mode="multiplicative",
            interval_width=0.80,
            changepoint_prior_scale=0.15,
        )
        model.add_seasonality(name="ramadan_approx", period=354.37, fourier_order=3)
        model.fit(df)
        try:
            joblib.dump(model, _MODEL_PATH)
            logger.info(f"[KPI-05] Prophet model saved to {_MODEL_PATH}")
        except Exception as exc:
            logger.warning(f"[KPI-05] Could not save model: {exc}")

    future   = model.make_future_dataframe(periods=horizon, freq="MS")
    forecast = model.predict(future)

    last_hist = df["ds"].max()
    forecast["is_historical"] = (forecast["ds"] <= last_hist).astype(int)

    result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical"]].copy()
    result["yhat"]       = result["yhat"].clip(lower=0)
    result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
    result["yhat_upper"] = result["yhat_upper"].clip(lower=0)

    logger.info(f"[KPI-05] Prévision générée : {horizon} mois futurs")
    return result

def _save_forecast(forecast: pd.DataFrame) -> None:
    today = datetime.now(timezone.utc).date()
    with DW_ENGINE.begin() as conn:
        conn.execute(text("DELETE FROM ML_KPI05_CA_FORECAST WHERE run_date = :d"), {"d": today})

    rows = [
        (
            today,
            row.ds.date(),
            float(row.yhat),
            float(row.yhat_lower),
            float(row.yhat_upper),
            int(row.is_historical),
        )
        for row in forecast.itertuples(index=False)
    ]
    sql = """
        INSERT INTO ML_KPI05_CA_FORECAST
            (run_date, ds, yhat, yhat_lower, yhat_upper, is_historical)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    logger.info(f"[KPI-05] {len(rows)} rows saved to ML_KPI05_CA_FORECAST")

def _evaluate(df_hist: pd.DataFrame, forecast: pd.DataFrame) -> None:
    hist_fc = forecast[forecast["is_historical"] == 1].copy()
    merged = df_hist.merge(hist_fc[["ds", "yhat"]], on="ds", how="inner")
    if merged.empty:
        return
    merged = merged.tail(3)
    mae  = (merged["y"] - merged["yhat"]).abs().mean()
    mape = ((merged["y"] - merged["yhat"]).abs() / merged["y"]).mean() * 100
    logger.info(f"[KPI-05] Back-test (last 3 months) - MAE: {mae:,.0f} | MAPE: {mape:.1f}%")

def run(horizon: int = 12) -> pd.DataFrame:
    _ensure_table()
    df = _load_monthly_ca()

    if len(df) < 12:
        logger.warning("[KPI-05] Less than 12 months of data — forecast may be unreliable")

    forecast = _train_and_forecast(df, horizon)
    _evaluate(df, forecast)
    _save_forecast(forecast)
    return forecast
