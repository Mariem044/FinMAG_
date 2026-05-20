import warnings
from datetime import datetime
import pandas as pd
import numpy as np
from sqlalchemy import text

warnings.filterwarnings("ignore")

from config import DW_ENGINE
from utils.logger import get_logger

logger = get_logger(__name__)

_DDL = """
IF OBJECT_ID('ML__CA_FORECAST', 'U') IS NOT NULL 
    AND (
        COL_LENGTH('ML__CA_FORECAST', 'model_name') IS NULL
        OR COL_LENGTH('ML__CA_FORECAST', 'mape') IS NULL
        OR EXISTS (
            SELECT 1 FROM sys.columns c
            JOIN sys.types t ON c.user_type_id = t.user_type_id
            WHERE c.object_id = OBJECT_ID('ML__CA_FORECAST')
AND c.name = 'run_date'
                AND t.name = 'date'
        )
    )
    DROP TABLE ML__CA_FORECAST;

IF OBJECT_ID('ML__CA_FORECAST', 'U') IS NULL
CREATE TABLE ML__CA_FORECAST (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    run_date        DATETIME NOT NULL,
    model_name      VARCHAR(20) NOT NULL DEFAULT 'PROPHET',
    ds              DATE NOT NULL,
    yhat            NUMERIC(18,4) NOT NULL,
    yhat_lower      NUMERIC(18,4) NOT NULL,
    yhat_upper      NUMERIC(18,4) NOT NULL,
    is_historical   SMALLINT NOT NULL DEFAULT 0,
    mape            NUMERIC(10,4) NULL,
    mae             NUMERIC(18,4) NULL
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
        JOIN DIM_DATE    d   ON d.id_date      = f.id_date
        WHERE f.DO_Domaine = 0
        GROUP BY d.annee, d.mois
        HAVING COUNT(*) > 10
        ORDER BY ds
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"]  = pd.to_numeric(df["y"], errors="coerce")
    df = df.dropna().sort_values("ds").reset_index(drop=True)
    if df.empty:
        logger.warning(" No monthly CA observations found")
        return df
    logger.info(f" Loaded {len(df)} monthly observations "
                f"({df['ds'].min().date()} -> {df['ds'].max().date()})")
    return df

def _forecast_seasonal_fallback(df: pd.DataFrame, horizon: int, model_name: str) -> pd.DataFrame:
    logger.info(f" Running Seasonal Decomposition Fallback for {model_name}...")
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
    result["model_name"] = model_name
    return result

def _forecast_trend_fallback(df: pd.DataFrame, horizon: int, model_name: str) -> pd.DataFrame:
    logger.info(f" Running Linear Trend Fallback for {model_name}...")
    n_obs = len(df)
    t = np.arange(n_obs)
    y = df["y"].values.astype(float)
    
    if n_obs >= 2:
        alpha, beta = np.polyfit(t, y, 1)
    else:
        alpha, beta = 0.0, float(y[0]) if n_obs > 0 else 0.0
        
    last_ds = df["ds"].max()
    future_dates = [last_ds + pd.DateOffset(months=i) for i in range(1, horizon + 1)]
    future_df = pd.DataFrame({"ds": future_dates})
    
    full_df = pd.concat([df, future_df], ignore_index=True)
    full_df["t"] = np.arange(len(full_df))
    
    full_df["yhat"] = alpha * full_df["t"].values + beta
    
    residuals = y - (alpha * t + beta)
    std_err = np.std(residuals) if len(residuals) > 1 else 0.1 * np.mean(y) if len(y) > 0 else 1.0
    
    full_df["yhat_lower"] = full_df["yhat"] - 1.28 * std_err
    full_df["yhat_upper"] = full_df["yhat"] + 1.28 * std_err
    
    last_hist = df["ds"].max()
    full_df["is_historical"] = (full_df["ds"] <= last_hist).astype(int)
    
    result = full_df[["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical"]].copy()
    result["yhat"]       = result["yhat"].clip(lower=0)
    result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
    result["yhat_upper"] = result["yhat_upper"].clip(lower=0)
    result["model_name"] = model_name
    return result

def _forecast_arima(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    logger.info(" Training ARIMA model...")
    df_ts = df.set_index("ds").copy()
    df_ts = df_ts.asfreq("MS")
    y = df_ts["y"].ffill().fillna(0)
    
    try:
        from statsmodels.tsa.arima.model import ARIMA
        model = ARIMA(y, order=(1, 1, 1))
        res = model.fit()
        
        hist_pred = res.fittedvalues
        hist_pred = hist_pred.fillna(y.iloc[0])
        
        fc = res.get_forecast(steps=horizon)
        fc_mean = fc.predicted_mean
        fc_ci = fc.conf_int(alpha=0.20) # 80% CI
        
        future_dates = pd.date_range(start=y.index[-1] + pd.DateOffset(months=1), periods=horizon, freq="MS")
        
        hist_df = pd.DataFrame({
            "ds": y.index,
            "yhat": hist_pred.values,
            "yhat_lower": hist_pred.values * 0.95,
            "yhat_upper": hist_pred.values * 1.05,
            "is_historical": 1
        })
        
        future_df = pd.DataFrame({
            "ds": future_dates,
            "yhat": fc_mean.values,
            "yhat_lower": fc_ci.iloc[:, 0].values,
            "yhat_upper": fc_ci.iloc[:, 1].values,
            "is_historical": 0
        })
        
        result = pd.concat([hist_df, future_df], ignore_index=True)
        result["model_name"] = "ARIMA"
        logger.info(" ARIMA model finished successfully.")
        return result
    except Exception as e:
        logger.error(f" ARIMA fitting failed: {e}. Using trend fallback.")
        return _forecast_trend_fallback(df, horizon, "ARIMA")

def _forecast_sarima(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    logger.info(" Training SARIMA model...")
    df_ts = df.set_index("ds").copy()
    df_ts = df_ts.asfreq("MS")
    y = df_ts["y"].ffill().fillna(0)
    
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        if len(y) < 24:
            logger.warning(" Series too short for SARIMA(12). Using seasonal period 3.")
            model = SARIMAX(y, order=(1, 1, 1), seasonal_order=(1, 1, 1, 3), enforce_stationarity=False, enforce_invertibility=False)
        else:
            model = SARIMAX(y, order=(1, 1, 1), seasonal_order=(1, 1, 1, 12), enforce_stationarity=False, enforce_invertibility=False)
        
        res = model.fit(disp=False)
        
        hist_pred = res.fittedvalues
        hist_pred = hist_pred.fillna(y.iloc[0])
        
        fc = res.get_forecast(steps=horizon)
        fc_mean = fc.predicted_mean
        fc_ci = fc.conf_int(alpha=0.20) # 80% CI
        
        future_dates = pd.date_range(start=y.index[-1] + pd.DateOffset(months=1), periods=horizon, freq="MS")
        
        hist_df = pd.DataFrame({
            "ds": y.index,
            "yhat": hist_pred.values,
            "yhat_lower": hist_pred.values * 0.95,
            "yhat_upper": hist_pred.values * 1.05,
            "is_historical": 1
        })
        
        future_df = pd.DataFrame({
            "ds": future_dates,
            "yhat": fc_mean.values,
            "yhat_lower": fc_ci.iloc[:, 0].values,
            "yhat_upper": fc_ci.iloc[:, 1].values,
            "is_historical": 0
        })
        
        result = pd.concat([hist_df, future_df], ignore_index=True)
        result["model_name"] = "SARIMA"
        logger.info(" SARIMA model finished successfully.")
        return result
    except Exception as e:
        logger.error(f" SARIMA fitting failed: {e}. Using seasonal fallback.")
        return _forecast_seasonal_fallback(df, horizon, "SARIMA")

def _forecast_prophet(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    logger.info(" Training Prophet model...")
    try:
        from prophet import Prophet
        
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
        
        future = model.make_future_dataframe(periods=horizon, freq="MS")
        forecast = model.predict(future)
        
        last_hist = df["ds"].max()
        forecast["is_historical"] = (forecast["ds"] <= last_hist).astype(int)
        
        result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical"]].copy()
        result["yhat"]       = result["yhat"].clip(lower=0)
        result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
        result["yhat_upper"] = result["yhat_upper"].clip(lower=0)
        result["model_name"] = "PROPHET"
        logger.info(" Prophet model finished successfully.")
        return result
    except Exception as e:
        logger.error(f" Prophet training failed: {e}. Using seasonal fallback.")
        return _forecast_seasonal_fallback(df, horizon, "PROPHET")

def _save_forecast(forecast: pd.DataFrame) -> None:
    if forecast.empty:
        logger.warning(" Empty forecast, keeping existing ML__CA_FORECAST data")
        return

    now_ts = datetime.now()
    with DW_ENGINE.begin() as conn:
        conn.execute(text("DELETE FROM ML__CA_FORECAST"))

    rows = [
        (
            now_ts,
            str(row.model_name),
            row.ds.date(),
            float(row.yhat),
            float(row.yhat_lower),
            float(row.yhat_upper),
            int(row.is_historical),
            float(row.mape) if hasattr(row, 'mape') and pd.notna(row.mape) else None,
            float(row.mae) if hasattr(row, 'mae') and pd.notna(row.mae) else None,
        )
        for row in forecast.itertuples(index=False)
    ]
    sql = """
        INSERT INTO ML__CA_FORECAST
            (run_date, model_name, ds, yhat, yhat_lower, yhat_upper, is_historical, mape, mae)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    logger.info(f" {len(rows)} rows saved to ML__CA_FORECAST")

def _evaluate(df_hist: pd.DataFrame, forecast: pd.DataFrame) -> tuple[float, float]:
    hist_fc = forecast[forecast["is_historical"] == 1].copy()
    merged = df_hist.merge(hist_fc[["ds", "yhat"]], on="ds", how="inner")
    if merged.empty:
        return 0.0, 0.0
    merged = merged.tail(3)
    mae  = float((merged["y"] - merged["yhat"]).abs().mean())
    non_zero = merged[merged["y"] != 0]
    mape = 0.0 if non_zero.empty else float(((non_zero["y"] - non_zero["yhat"]).abs() / non_zero["y"]).mean() * 100)
    model_name = forecast["model_name"].iloc[0] if "model_name" in forecast.columns else "UNKNOWN"
    logger.info(f" {model_name} In-sample validation (last 3 months) - MAE: {mae:,.0f} | MAPE: {mape:.1f}%")
    return mae, mape

def run(horizon: int = 12) -> pd.DataFrame:
    _ensure_table()
    df = _load_monthly_ca()
    if df.empty:
        logger.warning(" Forecast skipped because no CA history is available")
        return pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical", "model_name", "mae", "mape"])

    if len(df) < 12:
        logger.warning(" Less than 12 months of data — forecast may be unreliable")

    # Train all 3 models!
    arima_fc = _forecast_arima(df, horizon)
    arima_mae, arima_mape = _evaluate(df, arima_fc)
    arima_fc["mae"] = arima_mae
    arima_fc["mape"] = arima_mape
    
    sarima_fc = _forecast_sarima(df, horizon)
    sarima_mae, sarima_mape = _evaluate(df, sarima_fc)
    sarima_fc["mae"] = sarima_mae
    sarima_fc["mape"] = sarima_mape
    
    prophet_fc = _forecast_prophet(df, horizon)
    prophet_mae, prophet_mape = _evaluate(df, prophet_fc)
    prophet_fc["mae"] = prophet_mae
    prophet_fc["mape"] = prophet_mape
    
    # Combine forecasts
    combined_forecast = pd.concat([arima_fc, sarima_fc, prophet_fc], ignore_index=True)
    
    # Save all forecasts!
    _save_forecast(combined_forecast)
    return combined_forecast
