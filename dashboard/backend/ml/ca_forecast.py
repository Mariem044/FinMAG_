import warnings
from datetime import datetime
import pandas as pd
import numpy as np
from sqlalchemy import text

warnings.filterwarnings("ignore")

from ..config import DW_ENGINE
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Nom de la table où le forecast de CA est enregistré.
TABLE_NAME = "ML_KPI05_CA_FORECAST"

_DDL = f"""
IF OBJECT_ID('{TABLE_NAME}', 'U') IS NOT NULL 
    AND (
        COL_LENGTH('{TABLE_NAME}', 'model_name') IS NULL
        OR COL_LENGTH('{TABLE_NAME}', 'mape') IS NULL
        OR EXISTS (
            SELECT 1 FROM sys.columns c
            JOIN sys.types t ON c.user_type_id = t.user_type_id
            WHERE c.object_id = OBJECT_ID('{TABLE_NAME}')
AND c.name = 'run_date'
                AND t.name = 'date'
        )
    )
    DROP TABLE {TABLE_NAME};

IF OBJECT_ID('{TABLE_NAME}', 'U') IS NULL
CREATE TABLE {TABLE_NAME} (
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
    # Vérifie que la table de forecast existe et la crée si nécessaire.
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
    # Requête SQL pour obtenir la somme du chiffre d'affaires par année et mois.
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

def _forecast_simple(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    logger.info("Running simple CA forecast...")
    df = df.copy()
    df["month"] = df["ds"].dt.month
    n_obs = len(df)
    t = np.arange(n_obs)
    y = df["y"].values.astype(float)

    if n_obs >= 2:
        alpha, beta = np.polyfit(t, y, 1)
    else:
        alpha, beta = 0.0, float(y[0]) if n_obs > 0 else 0.0

    trend = alpha * t + beta
    trend_safe = np.where(trend <= 0, 1e-5, trend)
    df["seasonal_ratio"] = df["y"] / trend_safe

    # On calcule la saisonnalité moyenne par mois : combien le CA diffère de la tendance.
    monthly_seasonality = df.groupby("month")["seasonal_ratio"].mean().to_dict()
    for m in range(1, 13):
        monthly_seasonality.setdefault(m, 1.0)

    mean_ratio = np.mean(list(monthly_seasonality.values()))
    if mean_ratio > 0:
        for m in monthly_seasonality:
            monthly_seasonality[m] /= mean_ratio

    # Prépare une série de dates qui couvre l'historique et l'horizon de forecast.
    last_ds = df["ds"].max()
    full_dates = pd.date_range(start=df["ds"].min(), periods=n_obs + horizon, freq="MS")
    full_df = pd.DataFrame({"ds": full_dates})
    full_df["t"] = np.arange(len(full_df))
    full_df["month"] = full_df["ds"].dt.month
    full_df["yhat"] = (alpha * full_df["t"] + beta) * full_df["month"].map(monthly_seasonality).fillna(1.0)

    hist_df = full_df[full_df["ds"] <= last_ds].copy()
    hist_df = hist_df.merge(df[["ds", "y"]], on="ds", how="left")
    residuals = hist_df.loc[hist_df["y"].notna(), "y"] - hist_df.loc[hist_df["y"].notna(), "yhat"]
    if len(residuals) > 1:
        std_err = float(np.std(residuals))
    else:
        std_err = max(0.05 * np.mean(y) if len(y) else 1.0, 1.0)

    full_df["yhat_lower"] = (full_df["yhat"] - 1.28 * std_err).clip(lower=0)
    full_df["yhat_upper"] = (full_df["yhat"] + 1.28 * std_err).clip(lower=0)
    full_df["is_historical"] = (full_df["ds"] <= last_ds).astype(int)
    full_df["model_name"] = "SIMPLE"
    full_df["yhat"] = full_df["yhat"].clip(lower=0)

    return full_df[["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical", "model_name"]]

def _save_forecast(forecast: pd.DataFrame) -> None:
    # Enregistre le forecast dans la base de données. Si le forecast est vide, on ne modifie rien.
    if forecast.empty:
        logger.warning(f" Empty forecast, keeping existing {TABLE_NAME} data")
        return

    now_ts = datetime.now()

    # Convertit chaque ligne du forecast en dictionnaire prêt pour l'insertion SQL.
    rows = [
        {
            "run_date": now_ts,
            "model_name": str(row.model_name),
            "ds": row.ds.date(),
            "yhat": float(row.yhat),
            "yhat_lower": float(row.yhat_lower),
            "yhat_upper": float(row.yhat_upper),
            "is_historical": int(row.is_historical),
            "mape": float(row.mape) if hasattr(row, 'mape') and pd.notna(row.mape) else None,
            "mae": float(row.mae) if hasattr(row, 'mae') and pd.notna(row.mae) else None,
        }
        for row in forecast.itertuples(index=False)
    ]
    sql = f"""
        INSERT INTO {TABLE_NAME}
            (run_date, model_name, ds, yhat, yhat_lower, yhat_upper, is_historical, mape, mae)
        VALUES (:run_date, :model_name, :ds, :yhat, :yhat_lower, :yhat_upper, :is_historical, :mape, :mae)
    """
    with DW_ENGINE.begin() as conn:
        conn.execute(text(f"DELETE FROM {TABLE_NAME}"))
        if rows:
            conn.execute(text(sql), rows)

    logger.info(f" {len(rows)} rows saved to {TABLE_NAME}")


def _evaluate(df_hist: pd.DataFrame, forecast: pd.DataFrame) -> tuple[float, float]:
    # Calcule MAE et MAPE sur les données historiques pour valider le modèle.
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
    # Point d'entrée principal pour lancer le forecast de CA.
    # Cette fonction prépare les données, exécute le modèle, l'évalue et enregistre les résultats.
    _ensure_table()
    df = _load_monthly_ca()
    if df.empty:
        logger.warning(" Forecast skipped because no CA history is available")
        return pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical", "model_name", "mae", "mape"])

    if len(df) < 12:
        logger.warning(" Less than 12 months of data — forecast may be unreliable")

    forecast = _forecast_simple(df, horizon)
    mae, mape = _evaluate(df, forecast)
    forecast["mae"] = mae
    forecast["mape"] = mape

    _save_forecast(forecast)
    return forecast
