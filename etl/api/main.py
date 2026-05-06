# api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import pandas as pd

from etl.config import DW_ENGINE

app = FastAPI(title="FinMAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/dashboard/kpis")
def get_dashboard_kpis():
    sql = """
        SELECT
            SUM(DL_MontantHT)                              AS ca_total,
            COUNT(DISTINCT DO_Piece_hash)                  AS nb_commandes,
            COUNT(DISTINCT id_client)                      AS nb_clients_actifs
        FROM FAIT_LIGNES_VENTE
        WHERE YEAR(date_extraction) = YEAR(GETDATE())
    """
    with DW_ENGINE.connect() as conn:
        row = conn.execute(text(sql)).fetchone()
    return {
        "ca_total":        float(row.ca_total or 0),
        "nb_commandes":    int(row.nb_commandes or 0),
        "nb_clients_actifs": int(row.nb_clients_actifs or 0),
    }

@app.get("/api/ventes/ca-by-month")
def get_ca_by_month():
    sql = """
        SELECT
            d.mois AS month_num,
            SUM(f.DL_MontantHT) AS ca,
            SUM(f.DL_MontantHT) * 1.05 AS objectif   -- replace with real targets
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DATE d ON d.id_date = f.id_date
        WHERE d.annee = YEAR(GETDATE())
        GROUP BY d.mois
        ORDER BY d.mois
    """
    with DW_ENGINE.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    months = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]
    return [
        {"month": months[r.month_num - 1], "ca": float(r.ca), "objectif": float(r.objectif)}
        for r in rows
    ]

@app.get("/api/tresorerie/impayes")
def get_impayes():
    sql = """
        SELECT
            c.CT_Num_code,
            SUM(r.RT_Montant) AS montant_impaye,
            MAX(r.delai_reel_jours) AS anciennete
        FROM FAIT_REGLEMENTS r
        JOIN DIM_CLIENT c ON c.id_client = r.id_client
        WHERE r.DR_Regle = 0
        GROUP BY c.CT_Num_code
        HAVING SUM(r.RT_Montant) > 0
        ORDER BY montant_impaye DESC
    """
    with DW_ENGINE.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [
        {"code": str(r.CT_Num_code), "montant": float(r.montant_impaye), "anciennete": int(r.anciennete or 0)}
        for r in rows
    ]

@app.get("/api/produits/stock-alerts")
def get_stock_alerts():
    sql = """
        SELECT TOP 20
            a.AR_Ref_code,
            f.AS_QteSto,
            f.AS_QteMini,
            f.en_rupture,
            f.ratio_tension
        FROM FAIT_ECRITURES f
        JOIN DIM_ARTICLE a ON a.id_article = f.id_article
        WHERE f.type_ligne = 4
          AND f.en_rupture = 1
        ORDER BY f.ratio_tension DESC
    """
    with DW_ENGINE.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [dict(r._mapping) for r in rows]