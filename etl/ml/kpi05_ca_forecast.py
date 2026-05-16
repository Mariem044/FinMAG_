"""
KPI-05 — Prévision mensuelle du CA (modèle Prophet)
=====================================================
Reads monthly sales from the DW (FAIT_LIGNES_VENTE + DIM_DATE + DIM_DOMAINE),
trains a Prophet model, and stores forecasts in ML_KPI05_CA_FORECAST.

Usage:
    python -m ml.kpi05_ca_forecast            # forecast next 12 months
    python -m ml.kpi05_ca_forecast --horizon 6
"""
from __future__ import annotations

import argparse
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text

warnings.filterwarnings("ignore")

# ── project imports ──────────────────────────────────────────────────────────
from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)

_MODEL_DIR = Path(__file__).parent / "models"
_MODEL_DIR.mkdir(exist_ok=True)
_MODEL_PATH = _MODEL_DIR / "kpi05_prophet.joblib"
_MODEL_MAX_AGE_DAYS = 7

# ── DDL for result table ──────────────────────────────────────────────────────
_DDL = """
IF OBJECT_ID('ML_KPI05_CA_FORECAST', 'U') IS NULL
CREATE TABLE ML_KPI05_CA_FORECAST (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    run_date        DATE NOT NULL,
    ds              DATE NOT NULL,          -- forecast month (1st of month)
    yhat            NUMERIC(18,4) NOT NULL, -- predicted CA HT
    yhat_lower      NUMERIC(18,4) NOT NULL,
    yhat_upper      NUMERIC(18,4) NOT NULL,
    is_historical   SMALLINT NOT NULL DEFAULT 0
)
"""

# ── helpers ──────────────────────────────────────────────────────────────────

def _ensure_table() -> None:
    with DW_ENGINE.begin() as conn:
        conn.execute(text(_DDL))


def _load_monthly_ca() -> pd.DataFrame:
    """
    Pull monthly CA HT from DW.
    Returns a DataFrame with columns [ds, y] expected by Prophet.
    """
    sql = """
        SELECT
            DATEFROMPARTS(d.annee, d.mois, 1) AS ds,
            SUM(f.DL_MontantHT)               AS y
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        JOIN DIM_DATE    d   ON d.id_date      = f.id_date
        WHERE dom.DO_Domaine = 0
        GROUP BY d.annee, d.mois
        HAVING COUNT(*) > 100          -- drop sparse months
        ORDER BY ds
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"]  = pd.to_numeric(df["y"], errors="coerce")
    df = df.dropna().sort_values("ds").reset_index(drop=True)
    logger.info(f"[KPI-05] Loaded {len(df)} monthly observations "
                f"({df['ds'].min().date()} → {df['ds'].max().date()})")
    return df


def _train_and_forecast(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """
    Fit Prophet on df[['ds','y']] and return horizon months of forecasts
    plus the fitted values for historical periods.

    Model persistence:
      The fitted model is serialised to ml/models/kpi05_prophet.joblib.
      On the next run, if the file is < 7 days old, the saved model is
      reused and only prediction is re-run (no refitting), which cuts
      typical runtime from ~60s to < 2s.
    """
    try:
        import joblib
        from prophet import Prophet          # type: ignore
    except ImportError:
        raise ImportError(
            "prophet and joblib are required. "
            "Run: pip install prophet joblib"
        )

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
        # Ramadan seasonality (approximate 354.37-day Islamic year)
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
        # Delete previous run
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
    """Print MAE and MAPE on the last 3 months of known data."""
    hist_fc = forecast[forecast["is_historical"] == 1].copy()
    merged = df_hist.merge(hist_fc[["ds", "yhat"]], on="ds", how="inner")
    if merged.empty:
        return
    merged = merged.tail(3)
    mae  = (merged["y"] - merged["yhat"]).abs().mean()
    mape = ((merged["y"] - merged["yhat"]).abs() / merged["y"]).mean() * 100
    logger.info(f"[KPI-05] Back-test (last 3 months) — MAE: {mae:,.0f} | MAPE: {mape:.1f}%")


# ── main ──────────────────────────────────────────────────────────────────────

def run(horizon: int = 12) -> pd.DataFrame:
    _ensure_table()
    df = _load_monthly_ca()

    if len(df) < 12:
        logger.warning("[KPI-05] Less than 12 months of data — forecast may be unreliable")

    forecast = _train_and_forecast(df, horizon)
    _evaluate(df, forecast)
    _save_forecast(forecast)
    return forecast


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KPI-05 CA Forecast")
    parser.add_argument("--horizon", type=int, default=12, help="Months to forecast")
    args = parser.parse_args()
    run(horizon=args.horizon)