"""
KPI-17 — Alerte dynamique de réapprovisionnement
=================================================
Calcule un stock de sécurité dynamique par article à partir de la
vitesse de consommation et de la variabilité des ventes mensuelles.
Classifie ensuite chaque article selon un niveau d'alerte.

Méthode : règles métier déterministes (pas de ML).
  - Stock de sécurité dynamique = conso_jour × lead_time × (1 + cv_conso)
  - ratio_tension fourni par l'ETL (FAIT_ECRITURES.ratio_tension)
  - Priorité dérivée directement de en_rupture + stock vs. stock_securite_dyn

Avantage par rapport à un modèle ML entraîné sur des labels règle-based :
  la logique est transparente, auditable en SSMS, et ne souffre pas du
  biais circulaire (train sur labels = reproduire la règle).

Résultats stockés dans ML_KPI17_REAPPRO_ALERT.

Usage :
    python -m ml.kpi17_reappro_alert
    python -m ml.kpi17_reappro_alert --lead-time 7
"""
from __future__ import annotations

import argparse
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import text

warnings.filterwarnings("ignore")

from config import DW_ENGINE
from utils.logger import get_logger

logger = get_logger(__name__)

# ── DDL ──────────────────────────────────────────────────────────────────────
_DDL = """
IF OBJECT_ID('ML_KPI17_REAPPRO_ALERT', 'U') IS NULL
CREATE TABLE ML_KPI17_REAPPRO_ALERT (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    run_date            DATE NOT NULL,
    id_article          INT  NOT NULL,
    AR_Ref_code         BIGINT NOT NULL,
    famille             NVARCHAR(100) NULL,
    stock_actuel        NUMERIC(18,4) NULL,
    stock_mini_statique NUMERIC(18,4) NULL,   -- seuil Sage d'origine (AS_QteMini)
    stock_securite_dyn  NUMERIC(18,4) NULL,   -- seuil dynamique : conso × lead_time × (1 + cv)
    conso_jour_moy      NUMERIC(18,4) NULL,   -- consommation journalière moyenne (12 mois)
    cv_conso            NUMERIC(18,4) NULL,   -- coefficient de variation mensuel
    score_urgence       NUMERIC(5,4)  NULL,   -- ratio_tension normalisé [0;1]
    priorite            VARCHAR(20)   NULL,   -- CRITIQUE / URGENT / ATTENTION / OK
    qte_a_commander     NUMERIC(18,4) NULL,   -- quantité suggérée à commander
    lead_time_jours     INT           NULL
)
"""


def _ensure_table() -> None:
    with DW_ENGINE.begin() as conn:
        conn.execute(text(_DDL))


# ── data loading ─────────────────────────────────────────────────────────────

def _load_stock() -> pd.DataFrame:
    """
    Charge le snapshot de stock depuis V_FAIT_STOCK_SNAPSHOT (vue sémantique
    sur FAIT_ECRITURES WHERE type_ligne = 4).
    """
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
    logger.info(f"[KPI-17] Stock snapshot : {len(df)} articles actifs")
    return df


def _load_monthly_sales() -> pd.DataFrame:
    """Ventes mensuelles par article sur les 12 derniers mois."""
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
        AND f.DL_Qte > 0
        GROUP BY f.id_article, d.annee, d.mois
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    logger.info(f"[KPI-17] Ventes mensuelles : {len(df)} lignes article×mois")
    return df


# ── dynamic safety stock ──────────────────────────────────────────────────────

def _compute_dynamic_safety_stock(
    stock_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    lead_time: int,
) -> pd.DataFrame:
    """
    Stock de sécurité dynamique = conso_jour_moy × lead_time × (1 + cv_conso)

    cv_conso : coefficient de variation de la consommation mensuelle.
    Un CV élevé indique une demande erratique → stock tampon plus grand.

    Pour les articles sans historique de vente, on conserve le seuil
    statique Sage (AS_QteMini) comme valeur par défaut.
    """
    if sales_df.empty:
        stock_df = stock_df.copy()
        stock_df["conso_jour_moy"] = 0.0
        stock_df["cv_conso"]       = 0.0
        stock_df["stock_securite_dyn"] = stock_df["stock_mini"].fillna(0)
        return stock_df

    agg = (
        sales_df.groupby("id_article")["qte_vendue"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .rename(columns={"mean": "conso_mois_moy", "std": "conso_mois_std", "count": "nb_mois"})
    )
    agg["conso_mois_std"]  = agg["conso_mois_std"].fillna(0)
    agg["cv_conso"]        = np.where(
        agg["conso_mois_moy"] > 0,
        agg["conso_mois_std"] / agg["conso_mois_moy"],
        0.0,
    )
    agg["conso_jour_moy"]  = agg["conso_mois_moy"] / 30.0

    df = stock_df.merge(agg[["id_article", "conso_jour_moy", "cv_conso"]], on="id_article", how="left")
    df["conso_jour_moy"] = df["conso_jour_moy"].fillna(0.0)
    df["cv_conso"]       = df["cv_conso"].fillna(0.0)

    # Dynamic safety stock formula
    df["stock_securite_dyn"] = (
        df["conso_jour_moy"] * lead_time * (1 + df["cv_conso"])
    ).clip(lower=0)

    # Fallback to static minimum when consumption data is absent
    mask_no_data = df["conso_jour_moy"] == 0
    df.loc[mask_no_data, "stock_securite_dyn"] = df.loc[mask_no_data, "stock_mini"].fillna(0)

    return df


# ── priority assignment ───────────────────────────────────────────────────────

def _assign_priority(df: pd.DataFrame) -> pd.DataFrame:
    """
    Règles métier déterministes pour l'assignation de priorité.

    CRITIQUE  : article déjà en rupture (en_rupture=1) OU stock < stock_securite_dyn
    URGENT    : ratio_tension >= 0.75
    ATTENTION : ratio_tension >= 0.50
    OK        : pas d'alerte

    score_urgence : ratio_tension normalisé [0;1] pour trier les alertes.
    """
    df = df.copy()

    # Normalise ratio_tension → score_urgence [0;1]
    df["ratio_tension"]  = pd.to_numeric(df.get("ratio_tension"), errors="coerce").fillna(0)
    df["score_urgence"]  = df["ratio_tension"].clip(0, 1)

    df["stock_actuel"]       = pd.to_numeric(df["stock_actuel"],       errors="coerce").fillna(0)
    df["stock_securite_dyn"] = pd.to_numeric(df["stock_securite_dyn"], errors="coerce").fillna(0)
    df["en_rupture"]         = pd.to_numeric(df.get("en_rupture", 0),  errors="coerce").fillna(0)

    def _priorite(row) -> str:
        if row["en_rupture"] == 1 or row["stock_actuel"] < row["stock_securite_dyn"]:
            return "CRITIQUE"
        rt = row["score_urgence"]
        if rt >= 0.75:
            return "URGENT"
        if rt >= 0.50:
            return "ATTENTION"
        return "OK"

    df["priorite"] = df.apply(_priorite, axis=1)
    return df


def _compute_order_quantity(df: pd.DataFrame, lead_time: int) -> pd.DataFrame:
    """
    Quantité à commander = max(0, stock_securite_dyn × 2 − stock_actuel)
    Couvre deux fois le stock de sécurité pour tenir compte des délais
    fournisseurs et de la variabilité de la demande.
    """
    df = df.copy()
    df["qte_a_commander"] = (
        df["stock_securite_dyn"] * 2 - df["stock_actuel"]
    ).clip(lower=0)
    df["lead_time_jours"] = lead_time
    return df


# ── save ──────────────────────────────────────────────────────────────────────

def _save(df: pd.DataFrame) -> None:
    today = datetime.now(timezone.utc).date()
    with DW_ENGINE.begin() as conn:
        conn.execute(
            text("DELETE FROM ML_KPI17_REAPPRO_ALERT WHERE run_date = :d"),
            {"d": today},
        )

    cols = [
        "id_article", "AR_Ref_code", "famille",
        "stock_actuel", "stock_mini", "stock_securite_dyn",
        "conso_jour_moy", "cv_conso", "score_urgence",
        "priorite", "qte_a_commander", "lead_time_jours",
    ]

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

    existing_cols = [c for c in cols if c in df.columns]
    rows = []
    for row in df[existing_cols].itertuples(index=False):
        rows.append((today,) + tuple(_v(v) for v in row))

    col_names = ", ".join(existing_cols)
    placeholders = ", ".join(["?"] * (len(existing_cols) + 1))
    sql = (
        f"INSERT INTO ML_KPI17_REAPPRO_ALERT "
        f"(run_date, {col_names}) "
        f"VALUES ({placeholders})"
    )
    with DW_ENGINE.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, rows)
        cursor.close()

    n_crit = (df["priorite"] == "CRITIQUE").sum()
    n_urg  = (df["priorite"] == "URGENT").sum()
    n_att  = (df["priorite"] == "ATTENTION").sum()
    logger.info(
        f"[KPI-17] {len(rows)} articles sauvegardés — "
        f"CRITIQUE: {n_crit} | URGENT: {n_urg} | ATTENTION: {n_att}"
    )


# ── main ──────────────────────────────────────────────────────────────────────

def run(lead_time: int = 7) -> pd.DataFrame:
    """
    Calcule les alertes de réapprovisionnement pour tous les articles actifs.

    Paramètre
    ---------
    lead_time : délai fournisseur en jours (utilisé pour le calcul du
                stock de sécurité dynamique). Valeur par défaut : 7 jours.
    """
    _ensure_table()

    stock_df = _load_stock()
    sales_df = _load_monthly_sales()

    if stock_df.empty:
        logger.warning("[KPI-17] Aucun article en stock — rien à calculer.")
        return pd.DataFrame()

    df = _compute_dynamic_safety_stock(stock_df, sales_df, lead_time)
    df = _assign_priority(df)
    df = _compute_order_quantity(df, lead_time)
    _save(df)
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KPI-17 Alerte Réapprovisionnement")
    parser.add_argument("--lead-time", type=int, default=7,
                        help="Délai fournisseur en jours (défaut: 7)")
    args = parser.parse_args()
    result = run(lead_time=args.lead_time)

    if not result.empty:
        summary = result.groupby("priorite").size().sort_index()
        print("\n=== KPI-17 RÉAPPROVISIONNEMENT ===")
        print(summary.to_string())
        print(f"\nTop 10 CRITIQUE/URGENT :")
        print(
            result[result["priorite"].isin(["CRITIQUE", "URGENT"])]
            [["AR_Ref_code", "famille", "stock_actuel", "stock_securite_dyn",
              "score_urgence", "qte_a_commander", "priorite"]]
            .sort_values("score_urgence", ascending=False)
            .head(10)
            .to_string(index=False)
        )