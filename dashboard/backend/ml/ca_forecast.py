"""
Module de prévision du Chiffre d'Affaires (CA) avec trois modèles ML:
- ARIMA: AutoRegressive Integrated Moving Average (séries temporelles classiques)
- SARIMA: Seasonal ARIMA (ajoute la saisonnalité)
- PROPHET: Framework Facebook (gère tendances, saisonnalité, jours fériés)

Le module charge l'historique CA mensuel de la base de données,
entraîne les 3 modèles en parallèle, et sauvegarde les prévisions.
"""

import warnings
from datetime import datetime
import pandas as pd
import numpy as np
from sqlalchemy import text

warnings.filterwarnings("ignore")

from ..config import DW_ENGINE  # Moteur de connexion à la base de données
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Nom de la table où sont stockées les prévisions
TABLE_NAME = "ML_KPI05_CA_FORECAST"

# Commande SQL pour créer la table des prévisions
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
    run_date        DATETIME NOT NULL,              -- Quand le forecast a été généré
    model_name      VARCHAR(20) NOT NULL DEFAULT 'PROPHET',  -- Nom du modèle (ARIMA, SARIMA, PROPHET)
    ds              DATE NOT NULL,                  -- Date de la prévision
    yhat            NUMERIC(18,4) NOT NULL,         -- Valeur prédite
    yhat_lower      NUMERIC(18,4) NOT NULL,         -- Limite basse de l'intervalle de confiance
    yhat_upper      NUMERIC(18,4) NOT NULL,         -- Limite haute de l'intervalle de confiance
    is_historical   SMALLINT NOT NULL DEFAULT 0,    -- 1 si c'est une donnée historique, 0 si prévision
    mape            NUMERIC(10,4) NULL,             -- MAPE: Mean Absolute Percentage Error (% d'erreur)
    mae             NUMERIC(18,4) NULL              -- MAE: Mean Absolute Error (erreur moyenne)
)
"""

def _ensure_table() -> None:
    """
    Crée la table de prévisions si elle n'existe pas.
    Supprime la table si le schéma est incompatible (migration de colonne).
    
    Cette fonction s'exécute automatiquement au début du forecast.
    """
    with DW_ENGINE.begin() as conn:
        conn.execute(text(_DDL))

def _load_monthly_ca() -> pd.DataFrame:
    """
    Charge l'historique mensuel du Chiffre d'Affaires depuis la base de données.
    
    Requête SQL:
    - Agrège les lignes de vente par mois (année + mois)
    - Filtre sur DO_Domaine = 0 (exclus certains domaines)
    - Garde seulement les mois avec > 10 lignes de vente (évite bruits mineurs)
    - Trie par date croissante
    
    Returns:
        pd.DataFrame: Dataframe avec colonnes:
            - ds (datetime): Date du mois
            - y (float): CA total du mois en TND
    """
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
    
    # Convertir les colonnes en types corrects
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"]  = pd.to_numeric(df["y"], errors="coerce")
    
    # Nettoyer les valeurs manquantes et trier
    df = df.dropna().sort_values("ds").reset_index(drop=True)
    
    if df.empty:
        logger.warning(" No monthly CA observations found")
        return df
    
    logger.info(f" Loaded {len(df)} monthly observations "
                f"({df['ds'].min().date()} -> {df['ds'].max().date()})")
    return df

def _forecast_seasonal_fallback(df: pd.DataFrame, horizon: int, model_name: str) -> pd.DataFrame:
    """
    Plan de secours: Prévision par décomposition saisonnière + trend linéaire.
    
    Utilisé si ARIMA ou SARIMA échouent.
    
    Processus:
    1. Ajuster une tendance linéaire (y = ax + b) sur l'historique
    2. Calculer les ratios mensuels (saisonnalité) pour chaque mois
    3. Appliquer la tendance + saisonnalité pour prédire l'avenir
    4. Ajouter des intervales de confiance basés sur les résidus historiques
    
    Args:
        df (pd.DataFrame): Données historiques (colonnes: ds, y)
        horizon (int): Nombre de mois à prévoir (ex: 12)
        model_name (str): Nom du modèle (pour logging)
    
    Returns:
        pd.DataFrame: Prévisions avec colonnes:
            - ds, yhat (valeur prédite), yhat_lower, yhat_upper (intervalle de confiance)
            - is_historical (1=historique, 0=prévision)
            - model_name
    """
    logger.info(f" Running Seasonal Decomposition Fallback for {model_name}...")
    n_obs = len(df)
    t = np.arange(n_obs)
    y = df["y"].values.astype(float)
    
    # Ajuster une droite y = alpha*t + beta
    if n_obs >= 2:
        alpha, beta = np.polyfit(t, y, 1)
    else:
        alpha, beta = 0.0, float(y[0]) if n_obs > 0 else 0.0
    
    # Extraire la tendance et calculer la saisonnalité (ratios)
    trend = alpha * t + beta
    trend_safe = np.where(trend <= 0, 1e-5, trend)  # Éviter division par 0
    seasonal_ratios = y / trend_safe
    
    # Grouper par mois pour calculer la saisonnalité moyenne
    df_temp = df.copy()
    df_temp["ratio"] = seasonal_ratios
    df_temp["month"] = df_temp["ds"].dt.month
    
    monthly_seasonality = df_temp.groupby("month")["ratio"].mean().to_dict()
    
    # Remplir les mois manquants avec 1.0 (pas de saisonnalité)
    for m in range(1, 13):
        if m not in monthly_seasonality:
            monthly_seasonality[m] = 1.0
    
    # Normaliser les facteurs saisonniers (moyenne = 1.0)
    mean_ratio = np.mean(list(monthly_seasonality.values()))
    if mean_ratio > 0:
        for m in monthly_seasonality:
            monthly_seasonality[m] /= mean_ratio
    
    # Générer les dates futures
    last_ds = df["ds"].max()
    future_dates = [last_ds + pd.DateOffset(months=i) for i in range(1, horizon + 1)]
    future_df = pd.DataFrame({"ds": future_dates})
    future_df["y"] = np.nan
    
    # Combiner historique + futur et calculer prévisions
    full_df = pd.concat([df, future_df], ignore_index=True)
    full_df["t"] = np.arange(len(full_df))
    full_df["month"] = full_df["ds"].dt.month
    
    pred_trend = alpha * full_df["t"].values + beta
    full_df["yhat"] = pred_trend * full_df["month"].map(monthly_seasonality)
    
    # Calculer les intervales de confiance basés sur les résidus historiques
    residuals = y - (trend * df_temp["month"].map(monthly_seasonality))
    std_err = np.std(residuals) if len(residuals) > 1 else 0.1 * np.mean(y) if len(y) > 0 else 1.0
    
    full_df["yhat_lower"] = full_df["yhat"] - 1.28 * std_err  # 80% CI
    full_df["yhat_upper"] = full_df["yhat"] + 1.28 * std_err
    
    # Marquer quelles lignes sont historiques
    last_hist = df["ds"].max()
    full_df["is_historical"] = (full_df["ds"] <= last_hist).astype(int)
    
    result = full_df[["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical"]].copy()
    result["yhat"]       = result["yhat"].clip(lower=0)  # Pas de CA négatif!
    result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
    result["yhat_upper"] = result["yhat_upper"].clip(lower=0)
    result["model_name"] = model_name
    return result

def _forecast_trend_fallback(df: pd.DataFrame, horizon: int, model_name: str) -> pd.DataFrame:
    """
    Plan de secours simple: Prévision par tendance linéaire UNIQUEMENT.
    
    Utilisé si ARIMA échoue (et aucune saisonnalité détectable).
    
    Processus:
    1. Ajuster y = ax + b sur l'historique
    2. Projeter cette ligne droite dans l'avenir
    3. Ajouter des intervales de confiance
    
    Args:
        df (pd.DataFrame): Données historiques
        horizon (int): Nombre de mois à prévoir
        model_name (str): Nom du modèle
    
    Returns:
        pd.DataFrame: Prévisions avec colonnes standard
    """
    logger.info(f" Running Linear Trend Fallback for {model_name}...")
    n_obs = len(df)
    t = np.arange(n_obs)
    y = df["y"].values.astype(float)
    
    # Ajuster la tendance linéaire
    if n_obs >= 2:
        alpha, beta = np.polyfit(t, y, 1)
    else:
        alpha, beta = 0.0, float(y[0]) if n_obs > 0 else 0.0
    
    # Générer les dates futures
    last_ds = df["ds"].max()
    future_dates = [last_ds + pd.DateOffset(months=i) for i in range(1, horizon + 1)]
    future_df = pd.DataFrame({"ds": future_dates})
    
    # Combiner et appliquer la tendance
    full_df = pd.concat([df, future_df], ignore_index=True)
    full_df["t"] = np.arange(len(full_df))
    
    full_df["yhat"] = alpha * full_df["t"].values + beta
    
    # Intervales de confiance
    residuals = y - (alpha * t + beta)
    std_err = np.std(residuals) if len(residuals) > 1 else 0.1 * np.mean(y) if len(y) > 0 else 1.0
    
    full_df["yhat_lower"] = full_df["yhat"] - 1.28 * std_err
    full_df["yhat_upper"] = full_df["yhat"] + 1.28 * std_err
    
    # Marquer historique
    last_hist = df["ds"].max()
    full_df["is_historical"] = (full_df["ds"] <= last_hist).astype(int)
    
    result = full_df[["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical"]].copy()
    result["yhat"]       = result["yhat"].clip(lower=0)
    result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
    result["yhat_upper"] = result["yhat_upper"].clip(lower=0)
    result["model_name"] = model_name
    return result

def _train_test_split(df: pd.DataFrame, validation_months: int = 6) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = len(df)
    if n < 4:
        return df.copy(), pd.DataFrame(columns=df.columns)
    validation_months = min(validation_months, max(1, n // 4))
    train = df.iloc[:-validation_months].copy()
    test = df.iloc[-validation_months:].copy()
    return train, test


def _validate_model(model_func, df: pd.DataFrame, validation_months: int = 6, max_splits: int = 3) -> tuple[float, float]:
    """
    Valide le modèle avec plusieurs fenêtres de type rolling origin.

    Cela calcule les erreurs sur plusieurs blocs de validation successifs
    au lieu d'un seul holdout fixe.
    """
    n = len(df)
    if n < 6:
        return 0.0, 0.0

    validation_months = min(validation_months, max(1, n // 4))
    end = n - validation_months
    min_train = max(4, n - validation_months * (max_splits + 1))
    if min_train > end:
        min_train = max(4, end)

    train_ends = list(range(min_train, end + 1))
    if not train_ends:
        return 0.0, 0.0

    if len(train_ends) > max_splits:
        train_ends = train_ends[-max_splits:]

    mae_values = []
    mape_values = []

    for train_end in train_ends:
        train = df.iloc[:train_end].copy()
        test = df.iloc[train_end:train_end + validation_months].copy()
        if test.empty:
            continue

        try:
            forecast = model_func(train, horizon=len(test), include_history=False)
        except Exception as exc:
            logger.warning(f"Validation failed for {model_func.__name__} on split ending at {train_end}: {exc}")
            continue

        if forecast.empty:
            continue

        merged = test.merge(forecast[["ds", "yhat"]], on="ds", how="inner")
        if merged.empty:
            continue

        mae = float((merged["y"] - merged["yhat"]).abs().mean())
        non_zero = merged[merged["y"] != 0]
        mape = 0.0 if non_zero.empty else float(((non_zero["y"] - non_zero["yhat"]).abs() / non_zero["y"]).mean() * 100)

        mae_values.append(mae)
        mape_values.append(mape)

    if not mae_values:
        return 0.0, 0.0

    avg_mae = float(sum(mae_values) / len(mae_values))
    avg_mape = float(sum(mape_values) / len(mape_values))
    logger.info(
        f"{model_func.__name__} rolling-origin validation {len(mae_values)} splits - "
        f"MAE: {avg_mae:,.0f} | MAPE: {avg_mape:.1f}%"
    )
    return avg_mae, avg_mape


def _select_arima_order(y: pd.Series, max_p: int = 2, max_d: int = 1, max_q: int = 2) -> tuple[int, int, int]:
    from statsmodels.tsa.arima.model import ARIMA

    best_aic = float("inf")
    best_order = (1, 1, 1)

    for p in range(max_p + 1):
        for d in range(max_d + 1):
            for q in range(max_q + 1):
                try:
                    model = ARIMA(y, order=(p, d, q), enforce_stationarity=False, enforce_invertibility=False)
                    res = model.fit()
                    if res.aic < best_aic:
                        best_aic = res.aic
                        best_order = (p, d, q)
                except Exception:
                    continue

    return best_order


def _select_sarima_order(y: pd.Series) -> tuple[tuple[int, int, int], tuple[int, int, int, int]]:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    best_aic = float("inf")
    best_order = (1, 1, 1)
    best_seasonal = (1, 1, 1, 12)
    seasons = [12] if len(y) >= 24 else [3]

    for s in seasons:
        for p in range(2):
            for q in range(2):
                for P in range(2):
                    for Q in range(2):
                        try:
                            model = SARIMAX(
                                y,
                                order=(p, 1, q),
                                seasonal_order=(P, 1, Q, s),
                                enforce_stationarity=False,
                                enforce_invertibility=False,
                            )
                            res = model.fit(disp=False)
                            if res.aic < best_aic:
                                best_aic = res.aic
                                best_order = (p, 1, q)
                                best_seasonal = (P, 1, Q, s)
                        except Exception:
                            continue

    return best_order, best_seasonal


def _choose_prophet_seasonality(df: pd.DataFrame) -> str:
    if df["y"].mean() <= 0:
        return "additive"
    seasonal_strength = df.groupby(df["ds"].dt.month)["y"].mean().std() / df["y"].mean()
    return "multiplicative" if seasonal_strength >= 0.25 else "additive"


def _forecast_arima(df: pd.DataFrame, horizon: int, include_history: bool = True) -> pd.DataFrame:
    """
    Entraîne un modèle ARIMA (AutoRegressive Integrated Moving Average).

    ARIMA = modèle classique pour les séries temporelles non saisonnières.
    - AR (AutoRegressive): utilise les valeurs passées pour prédire l'avenir
    - I (Integrated): différencie la série pour la rendre stationnaire
    - MA (Moving Average): utilise les erreurs passées pour correction

    L'ordre ARIMA est choisi automatiquement à partir de l'historique via le critère AIC.
    Plan de secours: Si ARIMA échoue, utilise _forecast_trend_fallback (tendance linéaire)
    
    Args:
        df (pd.DataFrame): Données historiques avec colonnes ds, y
        horizon (int): Nombre de mois à prévoir (ex: 12 mois)
    
    Returns:
        pd.DataFrame: Prévisions avec intervales de confiance à 80%
    """
    logger.info(" Training ARIMA model...")
    df_ts = df.set_index("ds").copy()
    df_ts = df_ts.asfreq("MS")  # Fréquence mensuelle
    y = df_ts["y"].ffill().fillna(0)  # Remplir les valeurs manquantes
    
    try:
        from statsmodels.tsa.arima.model import ARIMA

        order = _select_arima_order(y)
        model = ARIMA(y, order=order, enforce_stationarity=False, enforce_invertibility=False)
        res = model.fit()

        if include_history:
            hist_pred = res.fittedvalues.fillna(y.iloc[0])
            hist_ci = res.get_prediction(start=y.index[0]).conf_int(alpha=0.20)
            hist_df = pd.DataFrame({
                "ds": y.index,
                "yhat": hist_pred.values,
                "yhat_lower": hist_ci.iloc[:, 0].values,
                "yhat_upper": hist_ci.iloc[:, 1].values,
                "is_historical": 1,
            })
        else:
            hist_df = pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical"])

        fc = res.get_forecast(steps=horizon)
        fc_mean = fc.predicted_mean
        fc_ci = fc.conf_int(alpha=0.20)
        future_dates = pd.date_range(start=y.index[-1] + pd.DateOffset(months=1), periods=horizon, freq="MS")
        future_df = pd.DataFrame({
            "ds": future_dates,
            "yhat": fc_mean.values,
            "yhat_lower": fc_ci.iloc[:, 0].values,
            "yhat_upper": fc_ci.iloc[:, 1].values,
            "is_historical": 0,
        })

        result = pd.concat([hist_df, future_df], ignore_index=True)
        result["yhat"] = result["yhat"].clip(lower=0)
        result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
        result["yhat_upper"] = result["yhat_upper"].clip(lower=0)
        result["model_name"] = "ARIMA"
        logger.info(f" ARIMA model finished successfully with order={order}.")
        return result
    except Exception as e:
        logger.error(f" ARIMA fitting failed: {e}. Using trend fallback.")
        return _forecast_trend_fallback(df, horizon, "ARIMA")

def _forecast_sarima(df: pd.DataFrame, horizon: int, include_history: bool = True) -> pd.DataFrame:
    """
    Entraîne un modèle SARIMA (Seasonal ARIMA).

    SARIMA = ARIMA + composante saisonnière.
    Parfait pour des données avec patterns répétitifs (ex: ventes plus hautes en décembre).

    L'ordre est sélectionné automatiquement sur la base de l'AIC.

    Args:
        df (pd.DataFrame): Données historiques avec colonnes ds, y
        horizon (int): Nombre de mois à prévoir
        include_history (bool): Si True, renvoie aussi les valeurs ajustées sur l'historique

    Returns:
        pd.DataFrame: Prévisions saisonnières avec intervales de confiance à 80%
    """
    logger.info(" Training SARIMA model...")
    df_ts = df.set_index("ds").copy()
    df_ts = df_ts.asfreq("MS")
    y = df_ts["y"].ffill().fillna(0)

    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        order, seasonal_order = _select_sarima_order(y)
        model = SARIMAX(
            y,
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        res = model.fit(disp=False)

        if include_history:
            hist_pred = res.fittedvalues.fillna(y.iloc[0])
            hist_ci = res.get_prediction(start=y.index[0]).conf_int(alpha=0.20)
            hist_df = pd.DataFrame({
                "ds": y.index,
                "yhat": hist_pred.values,
                "yhat_lower": hist_ci.iloc[:, 0].values,
                "yhat_upper": hist_ci.iloc[:, 1].values,
                "is_historical": 1,
            })
        else:
            hist_df = pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical"])

        fc = res.get_forecast(steps=horizon)
        fc_mean = fc.predicted_mean
        fc_ci = fc.conf_int(alpha=0.20)
        future_dates = pd.date_range(start=y.index[-1] + pd.DateOffset(months=1), periods=horizon, freq="MS")
        future_df = pd.DataFrame({
            "ds": future_dates,
            "yhat": fc_mean.values,
            "yhat_lower": fc_ci.iloc[:, 0].values,
            "yhat_upper": fc_ci.iloc[:, 1].values,
            "is_historical": 0,
        })

        result = pd.concat([hist_df, future_df], ignore_index=True)
        result["yhat"] = result["yhat"].clip(lower=0)
        result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
        result["yhat_upper"] = result["yhat_upper"].clip(lower=0)
        result["model_name"] = "SARIMA"
        logger.info(f" SARIMA model finished successfully with order={order} seasonal_order={seasonal_order}.")
        return result
    except Exception as e:
        logger.error(f" SARIMA fitting failed: {e}. Using seasonal fallback.")
        return _forecast_seasonal_fallback(df, horizon, "SARIMA")

def _forecast_prophet(df: pd.DataFrame, horizon: int, include_history: bool = True) -> pd.DataFrame:
    """
    Entraîne un modèle Prophet (développé par Facebook).

    Prophet = approche moderne pour les séries temporelles:
    - Gère automatiquement tendances, saisonnalités, jours fériés
    - Robuste aux données manquantes
    - Offre des intervales de confiance crédibles

    La configuration est choisie à partir des propriétés du CA historique.

    Args:
        df (pd.DataFrame): Données historiques avec colonnes ds, y
        horizon (int): Nombre de mois à prévoir
        include_history (bool): Si True, renvoie aussi les valeurs ajustées sur l'historique

    Returns:
        pd.DataFrame: Prévisions avec intervales de confiance à 80%
    """
    logger.info(" Training Prophet model...")
    try:
        from prophet import Prophet

        seasonality_mode = _choose_prophet_seasonality(df)
        yearly_seasonality = len(df) >= 12

        model = Prophet(
            yearly_seasonality=yearly_seasonality,
            weekly_seasonality=False,
            daily_seasonality=False,
            seasonality_mode=seasonality_mode,
            interval_width=0.80,
            changepoint_prior_scale=0.15,
        )

        if yearly_seasonality and len(df) >= 24:
            model.add_seasonality(name="ramadan_approx", period=354.37, fourier_order=3)

        model.fit(df)

        future = model.make_future_dataframe(periods=horizon, freq="MS")
        forecast = model.predict(future)
        last_hist = df["ds"].max()
        forecast["is_historical"] = (forecast["ds"] <= last_hist).astype(int)

        result = forecast[["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical"]].copy()
        result["yhat"] = result["yhat"].clip(lower=0)
        result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
        result["yhat_upper"] = result["yhat_upper"].clip(lower=0)
        result["model_name"] = "PROPHET"
        logger.info(f" Prophet model finished successfully with seasonality_mode={seasonality_mode}.")

        if not include_history:
            return result[result["is_historical"] == 0][["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical", "model_name"]].reset_index(drop=True)

        return result
    except Exception as e:
        logger.error(f" Prophet training failed: {e}. Using seasonal fallback.")
        return _forecast_seasonal_fallback(df, horizon, "PROPHET")

def _save_forecast(forecast: pd.DataFrame) -> None:
    """
    Sauvegarde les prévisions dans la base de données.
    
    Processus:
    1. Vérifier que le forecast n'est pas vide
    2. Vider la table existante (supprimer l'ancien forecast)
    3. Insérer toutes les lignes du nouveau forecast
    
    Args:
        forecast (pd.DataFrame): Dataframe avec colonnes:
            - ds, yhat, yhat_lower, yhat_upper, is_historical, model_name, mape, mae
    """
    if forecast.empty:
        logger.warning(f" Empty forecast, keeping existing {TABLE_NAME} data")
        return

    now_ts = datetime.now()
    
    # Supprimer les anciennes prévisions
    with DW_ENGINE.begin() as conn:
        conn.execute(text(f"DELETE FROM {TABLE_NAME}"))

    # Préparer les rows pour insertion en bulk
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
    
    # Insérer les données en bulk (plus rapide)
    sql = f"""
        INSERT INTO {TABLE_NAME}
            (run_date, model_name, ds, yhat, yhat_lower, yhat_upper, is_historical, mape, mae)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True  # Mode rapide pour SQL Server
        cursor.executemany(sql, rows)
        cursor.close()

    logger.info(f" {len(rows)} rows saved to {TABLE_NAME}")

def _evaluate(df_hist: pd.DataFrame, forecast: pd.DataFrame, validation_months: int = 6) -> tuple[float, float]:
    """
    Évalue la précision d'un modèle sur des mois de validation hors-échantillon.

    Args:
        df_hist (pd.DataFrame): Données historiques réelles
        forecast (pd.DataFrame): Prévisions du modèle (avec historic + futur lorsque disponible)
        validation_months (int): Nombre de mois retenus pour la validation

    Returns:
        tuple[float, float]: (mae, mape)
    """
    if len(df_hist) < 4 or forecast.empty:
        return 0.0, 0.0

    _, test = _train_test_split(df_hist, validation_months)
    if test.empty:
        return 0.0, 0.0

    hist_fc = forecast[(forecast["is_historical"] == 1) & (forecast["ds"].isin(test["ds"]))].copy()
    merged = test.merge(hist_fc[["ds", "yhat"]], on="ds", how="inner")

    if merged.empty:
        return 0.0, 0.0

    mae = float((merged["y"] - merged["yhat"]).abs().mean())
    non_zero = merged[merged["y"] != 0]
    mape = 0.0 if non_zero.empty else float(((non_zero["y"] - non_zero["yhat"]).abs() / non_zero["y"]).mean() * 100)

    model_name = forecast["model_name"].iloc[0] if "model_name" in forecast.columns else "UNKNOWN"
    logger.info(f" {model_name} holdout validation ({len(test)} months) - MAE: {mae:,.0f} | MAPE: {mape:.1f}%")
    return mae, mape

def run(horizon: int = 12) -> pd.DataFrame:
    """
    Fonction principale d'exécution du pipeline ML.
    
    Processus:
    1. Vérifier que la table existe (créer si nécessaire)
    2. Charger l'historique mensuel du CA
    3. Entraîner les 3 modèles en parallèle:
       - ARIMA
       - SARIMA
       - PROPHET
    4. Évaluer chaque modèle (MAE, MAPE)
    5. Combiner tous les résultats
    6. Sauvegarder dans la base de données
    
    Args:
        horizon (int): Nombre de mois à prévoir (défaut 12)
    
    Returns:
        pd.DataFrame: Tous les forecasts combinés (3 modèles x horizon mois)
    """
    # Créer la table si elle n'existe pas
    _ensure_table()
    
    # Charger l'historique
    df = _load_monthly_ca()
    if df.empty:
        logger.warning(" Forecast skipped because no CA history is available")
        return pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical", "model_name", "mae", "mape"])

    if len(df) < 12:
        logger.warning(" Less than 12 months of data — forecast may be unreliable")

    # Entraîner tous les 3 modèles!
    volatility = df["y"].pct_change().abs().dropna().mean() * 100
    _MAPE_FALLBACK_THRESHOLD = max(150.0, volatility * 2.5)
    logger.info(f"Using fallback MAPE threshold: {_MAPE_FALLBACK_THRESHOLD:.1f}%")

    arima_mae, arima_mape = _validate_model(_forecast_arima, df)
    arima_fc = _forecast_arima(df, horizon)
    if arima_mape >= _MAPE_FALLBACK_THRESHOLD:
        logger.warning(f" ARIMA holdout MAPE={arima_mape:.1f}% exceeds threshold. Replacing with trend fallback.")
        arima_fc = _forecast_trend_fallback(df, horizon, "ARIMA")
        arima_mae, arima_mape = _evaluate(df, arima_fc)
    arima_fc["mae"] = arima_mae
    arima_fc["mape"] = arima_mape

    sarima_mae, sarima_mape = _validate_model(_forecast_sarima, df)
    sarima_fc = _forecast_sarima(df, horizon)
    if sarima_mape >= _MAPE_FALLBACK_THRESHOLD:
        logger.warning(f" SARIMA holdout MAPE={sarima_mape:.1f}% exceeds threshold. Replacing with seasonal fallback.")
        sarima_fc = _forecast_seasonal_fallback(df, horizon, "SARIMA")
        sarima_mae, sarima_mape = _evaluate(df, sarima_fc)
    sarima_fc["mae"] = sarima_mae
    sarima_fc["mape"] = sarima_mape

    prophet_mae, prophet_mape = _validate_model(_forecast_prophet, df)
    prophet_fc = _forecast_prophet(df, horizon)
    prophet_fc["mae"] = prophet_mae
    prophet_fc["mape"] = prophet_mape
    
    # Combiner les résultats des 3 modèles
    combined_forecast = pd.concat([arima_fc, sarima_fc, prophet_fc], ignore_index=True)
    
    # Sauvegarder tous les forecasts dans la base!
    _save_forecast(combined_forecast)
    return combined_forecast
