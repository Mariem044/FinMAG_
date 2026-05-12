import json
import logging
import os
import re
import threading
import unicodedata
from typing import List

from google import genai
from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from etl.config import DW_ENGINE
from etl import pipeline

app = FastAPI(title="FinMAG API")
_ETL_RUN_LOCK = threading.Lock()
_ETL_LAST_ERROR = None
_startup_logger = logging.getLogger("api.startup")

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

allowed_origins = [
    origin.strip()
    for origin in os.getenv("API_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
] or DEFAULT_ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
if _GEMINI_API_KEY:
    _GEMINI_CLIENT = genai.Client(api_key=_GEMINI_API_KEY)
    _LLM_READY = True
    _startup_logger.info("Gemini LLM ready.")
else:
    _GEMINI_CLIENT = None
    _LLM_READY = False
    _startup_logger.warning(
        "GEMINI_API_KEY not set - LLM assistant disabled. "
        "Add it to etl/.env to enable."
    )

_SYSTEM_PROMPT = (
    "Tu es FinMAG, assistant IA financier de MAG Distribution, avec un ton de CFO. "
    "Reponds toujours en francais, de facon directe, sobre et utile. "
    "Limite chaque reponse a 4-5 lignes maximum. "
    "N'analyse les donnees financieres que lorsqu'elles sont fournies dans le message utilisateur. "
    "Pour un message casual ou non financier, reponds naturellement en 1-2 lignes, sans mentionner les donnees. "
    "Ne repete pas les memes alertes, warnings ou anomalies si l'utilisateur ne les demande pas. "
    "Ne fais pas de longue synthese automatique. "
    "Utilise le **gras uniquement pour les chiffres cles**, jamais pour des phrases entieres."
)

MONTHS = ["Jan", "Fev", "Mar", "Avr", "Mai", "Jun", "Jul", "Aou", "Sep", "Oct", "Nov", "Dec"]


def _rows(sql, params=None):
    with DW_ENGINE.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchall()


def _row(sql, params=None):
    with DW_ENGINE.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchone()


def _num(value, default=0.0):
    return float(value) if value is not None else default


def _int(value, default=0):
    return int(value) if value is not None else default


def _date_str(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")


def _run_etl_background():
    global _ETL_LAST_ERROR
    try:
        pipeline.run_pipeline()
        _ETL_LAST_ERROR = None
    except Exception as exc:
        _ETL_LAST_ERROR = str(exc)
    finally:
        _ETL_RUN_LOCK.release()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/etl/status")
def get_etl_status():
    try:
        last_run = _row(
            """
            SELECT TOP 1 run_id, run_date, status, duration_seconds, error_msg
            FROM ETL_AUDIT
            WHERE table_name = 'PIPELINE'
            ORDER BY run_date DESC
            """
        )
        counts = _rows(
            """
            SELECT 'clients' AS name, COUNT(*) AS value FROM DIM_CLIENT
            UNION ALL SELECT 'articles', COUNT(*) FROM DIM_ARTICLE
            UNION ALL SELECT 'ventes', COUNT(*) FROM FAIT_LIGNES_VENTE
            UNION ALL SELECT 'reglements', COUNT(*) FROM FAIT_REGLEMENTS
            UNION ALL SELECT 'ecritures', COUNT(*) FROM FAIT_ECRITURES
            """
        )
    except Exception as exc:
        return {
            "running": _ETL_RUN_LOCK.locked(),
            "lastError": str(exc),
            "lastRun": None,
            "counts": {},
        }
    return {
        "running": _ETL_RUN_LOCK.locked(),
        "lastError": _ETL_LAST_ERROR,
        "lastRun": None if not last_run else {
            "runId": _int(last_run.run_id),
            "date": _date_str(last_run.run_date),
            "status": last_run.status,
            "durationSeconds": _int(last_run.duration_seconds),
            "error": last_run.error_msg,
        },
        "counts": {r.name: _int(r.value) for r in counts},
    }


@app.post("/api/etl/run")
def run_etl(background_tasks: BackgroundTasks):
    if not _ETL_RUN_LOCK.acquire(blocking=False):
        return {"started": False, "running": True}
    background_tasks.add_task(_run_etl_background)
    return {"started": True, "running": True}


@app.get("/api/dashboard/kpis")
def get_dashboard_kpis():

    sql = """
        WITH latest AS (
            SELECT COALESCE(MAX(d.annee), YEAR(GETDATE())) AS latest_year
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
            WHERE dom.DO_Domaine = 0
        )
        SELECT
            SUM(f.DL_MontantHT) AS ca_total,
            COUNT(DISTINCT f.DO_Piece_hash) AS nb_commandes,
            COUNT(DISTINCT f.id_client) AS nb_clients_actifs,
            SUM(f.DL_MontantHT - (f.DL_Qte * COALESCE(a.AR_PrixAch, 0))) AS marge_brute
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
        CROSS JOIN latest
        WHERE dom.DO_Domaine = 0
          AND d.annee = latest.latest_year
    """
    row = _row(sql)
    ca_total = _num(row.ca_total)
    marge_brute = _num(row.marge_brute)
    try:
        taux_recouvrement = get_tresorerie_summary()["taux_recouvrement"]
    except Exception:
        taux_recouvrement = 0.0
    return {
        "ca_total": ca_total,
        "nb_commandes": _int(row.nb_commandes),
        "nb_clients_actifs": _int(row.nb_clients_actifs),
        "taux_recouvrement": taux_recouvrement,
        "marge_brute_pct": (marge_brute / ca_total * 100) if ca_total else 0,
    }


@app.get("/api/ventes/ca-by-month")
def get_ca_by_month():
    sql = """
        WITH latest AS (
            SELECT COALESCE(MAX(d.annee), YEAR(GETDATE())) AS latest_year
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
            WHERE dom.DO_Domaine = 0
        ),
        monthly AS (
            SELECT d.annee, d.mois, SUM(f.DL_MontantHT) AS ca
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            JOIN DIM_DATE d ON d.id_date = f.id_date
            CROSS JOIN latest
            WHERE dom.DO_Domaine = 0
              AND d.annee IN (latest.latest_year, latest.latest_year - 1)
            GROUP BY d.annee, d.mois
        )
        SELECT cur.mois AS month_num,
               cur.ca,
               cur.ca * 1.05 AS objectif,
               COALESCE(prev.ca, 0) AS caN1
        FROM monthly cur
        CROSS JOIN latest
        LEFT JOIN monthly prev
          ON prev.annee = latest.latest_year - 1
         AND prev.mois = cur.mois
        WHERE cur.annee = latest.latest_year
        ORDER BY cur.mois
    """
    return [
        {
            "month": MONTHS[r.month_num - 1],
            "ca": _num(r.ca),
            "objectif": _num(r.objectif),
            "caN1": _num(r.caN1),
        }
        for r in _rows(sql)
    ]


@app.get("/api/ventes/top-familles")
def get_top_familles():
    sql = """
        SELECT TOP 8
            COALESCE(
                CONVERT(VARCHAR(30), fa.FA_CodeFamille_code),
                'Sans famille'
            ) AS name,
            SUM(f.DL_MontantHT) AS ca
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_ARTICLE a  ON a.id_article  = f.id_article
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
        WHERE dom.DO_Domaine = 0
        GROUP BY fa.FA_CodeFamille_code
        ORDER BY ca DESC
    """
    return [
        {"name": f"Famille {r.name}", "ca": _num(r.ca)}
        for r in _rows(sql)
    ]


@app.get("/api/ventes/ca-by-region")
def get_ca_by_region():
    sql = """
        SELECT TOP 12
            COALESCE(s.libelle_segment, 'Sans segment') AS name,
            SUM(f.DL_MontantHT)          AS ca,
            COUNT(DISTINCT f.id_client)  AS clients,
            COUNT(DISTINCT f.DO_Piece_hash) AS commandes
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_CLIENT  c ON c.id_client  = f.id_client
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE dom.DO_Domaine = 0
        GROUP BY s.libelle_segment
        ORDER BY ca DESC
    """
    return [
        {
            "name": r.name,
            "ca": _num(r.ca),
            "clients": _int(r.clients),
            "commandes": _int(r.commandes),
        }
        for r in _rows(sql)
    ]


@app.get("/api/tresorerie/summary")
def get_tresorerie_summary():
    sql = """
        SELECT
            SUM(CASE WHEN DR_Regle = 1 THEN RT_Montant ELSE 0 END) AS encaissements,
            SUM(CASE WHEN DR_Regle = 0 THEN RT_Montant ELSE 0 END) AS impayes,
            AVG(CAST(delai_reel_jours AS FLOAT)) AS delai_moyen
        FROM FAIT_REGLEMENTS
    """
    row = _row(sql)
    encaissements = _num(row.encaissements)
    impayes = _num(row.impayes)
    total = encaissements + impayes
    return {
        "encaissements": encaissements,
        "impayes": impayes,
        "delai_moyen": round(_num(row.delai_moyen)),
        "taux_recouvrement": (encaissements / total * 100) if total else 0,
    }


@app.get("/api/tresorerie/impayes")
def get_impayes():
    sql = """
        SELECT TOP 30
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
    return [
        {
            "client": f"Client {r.CT_Num_code}",
            "code": str(r.CT_Num_code),
            "montant": _num(r.montant_impaye),
            "montantImpaye": _num(r.montant_impaye),
            "anciennete": _int(r.anciennete),
            "region": "DW",
            "representant": "",
            "dateEcheance": "",
            "statut": (
                "Critique" if _int(r.anciennete) > 90
                else "Urgent" if _int(r.anciennete) > 60
                else "Attention"
            ),
        }
        for r in _rows(sql)
    ]


@app.get("/api/tresorerie/encaissements-by-mode")
def get_encaissements_by_mode():
    sql = """
        SELECT
            COALESCE(m.libelle_mode_reg, CONCAT('Mode ', r.DR_ModeReg)) AS mode,
            SUM(CASE WHEN r.id_client IS NOT NULL THEN r.RT_Montant ELSE 0 END) AS mag,
            SUM(CASE WHEN r.id_fournisseur IS NOT NULL THEN r.RT_Montant ELSE 0 END) AS grt,
            AVG(CASE WHEN r.RT_Rapproche = 1 THEN 100.0 ELSE 0.0 END) AS rapprochement
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_MODE_REGLEMENT m ON m.id_mode_reg = r.id_mode_reg
        WHERE r.DR_Regle = 1
        GROUP BY m.libelle_mode_reg, r.DR_ModeReg
        ORDER BY
            SUM(CASE WHEN r.id_client IS NOT NULL THEN r.RT_Montant ELSE 0 END)
          + SUM(CASE WHEN r.id_fournisseur IS NOT NULL THEN r.RT_Montant ELSE 0 END)
          DESC
    """
    return [
        {
            "mode": r.mode,
            "mag": _num(r.mag),
            "grt": _num(r.grt),
            "rapprochement": round(_num(r.rapprochement)),
        }
        for r in _rows(sql)
    ]


@app.get("/api/tresorerie/aging")
def get_aging():

    sql = """
        SELECT TOP 8
            COALESCE(CONVERT(VARCHAR(30), c.CT_Num_code), 'Client') AS client,
            SUM(CASE WHEN r.bucket_impaye = 0 THEN r.RT_Montant ELSE 0 END) AS b0,
            SUM(CASE WHEN r.bucket_impaye = 1 THEN r.RT_Montant ELSE 0 END) AS b1,
            SUM(CASE WHEN r.bucket_impaye = 2 THEN r.RT_Montant ELSE 0 END) AS b2,
            SUM(CASE WHEN r.bucket_impaye = 3 THEN r.RT_Montant ELSE 0 END) AS b3
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
        WHERE r.DR_Regle = 0
        GROUP BY c.CT_Num_code
        ORDER BY b3 DESC
    """
    return [
        {
            "client": f"Client {r.client}",
            "0-30j": _num(r.b0),
            "31-60j": _num(r.b1),
            "61-90j": _num(r.b2),
            ">90j": _num(r.b3),
        }
        for r in _rows(sql)
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
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = f.id_type_ligne
        JOIN DIM_ARTICLE a ON a.id_article = f.id_article
        WHERE tl.type_ligne = 4
          AND f.en_rupture = 1
          AND f.AS_QteSto IS NOT NULL
          AND f.ratio_tension IS NOT NULL
        ORDER BY f.ratio_tension DESC
    """
    alerts = []
    for r in _rows(sql):
        stock = _num(r.AS_QteSto)
        seuil = _num(r.AS_QteMini)
        ratio = _num(r.ratio_tension)
        alerts.append({
            "article": f"ART-{r.AR_Ref_code}",
            "designation": f"Article {r.AR_Ref_code}",
            "stockActuel": stock,
            "seuil": seuil,
            "dateRupture": "",
            "famille": "DW",
            "fournisseur": "",
            "priorite": (
                "CRITIQUE" if stock <= seuil
                else "URGENT" if ratio >= 0.8
                else "ATTENTION"
            ),
            "ratioTension": ratio,
        })
    return alerts


@app.get("/api/produits/articles")
def get_articles():
    sql = """
        WITH sales AS (
            SELECT
                id_article,
                COALESCE(SUM(DL_Qte), 0) AS qte_vendue,
                COALESCE(SUM(DL_MontantHT), 0) AS ca
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            WHERE dom.DO_Domaine = 0
            GROUP BY id_article
        ),
        stock AS (
            SELECT
                e.id_article,
                MAX(e.AS_QteSto) AS stock,
                MAX(e.dsi_jours) AS dsi_jours
            FROM FAIT_ECRITURES e
            JOIN DIM_TYPE_LIGNE tl
              ON tl.id_type_ligne = e.id_type_ligne
             AND tl.type_ligne = 4
            GROUP BY e.id_article
        )
        SELECT TOP 100
            a.AR_Ref_code,
            a.id_famille,
            a.AR_PrixAch,
            COALESCE(sales.qte_vendue, 0) AS qte_vendue,
            COALESCE(sales.ca, 0) AS ca,
            stock.stock,
            stock.dsi_jours
        FROM DIM_ARTICLE a
        LEFT JOIN sales ON sales.id_article = a.id_article
        LEFT JOIN stock ON stock.id_article = a.id_article
        ORDER BY ca DESC
    """
    return [
        {
            "code": f"ART-{r.AR_Ref_code}",
            "designation": f"Article {r.AR_Ref_code}",
            "famille": f"Famille {r.id_famille or 'N/A'}",
            "qteVendue": _num(r.qte_vendue),
            "ca": _num(r.ca),
            "prixMoyen": _num(r.AR_PrixAch),
            "marge": 0,
            "stock": _num(r.stock),
            "dsi": _num(r.dsi_jours),
        }
        for r in _rows(sql)
    ]


@app.get("/api/acteurs/clients")
def get_clients():
    sql = """
        SELECT TOP 100
            c.CT_Num_code,
            COALESCE(s.libelle_segment, 'Sans segment') AS segment,
            SUM(v.DL_MontantHT) AS ca_total,
            COUNT(DISTINCT v.DO_Piece_hash) AS nb_commandes,
            FORMAT(MAX(d.date_val), 'yyyy-MM-dd') AS derniere_commande,
            c.CT_SoldeActuel AS solde_impaye,
            c.CT_Sommeil AS sommeil
        FROM DIM_CLIENT c
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        LEFT JOIN FAIT_LIGNES_VENTE v ON v.id_client = c.id_client
        LEFT JOIN DIM_DOMAINE dom ON dom.id_domaine = v.id_domaine AND dom.DO_Domaine = 0
        LEFT JOIN DIM_DATE d ON d.id_date = v.id_date
        GROUP BY c.CT_Num_code, s.libelle_segment, c.CT_SoldeActuel, c.CT_Sommeil
        ORDER BY ca_total DESC
    """
    return [
        {
            "code": str(r.CT_Num_code),
            "nom": f"Client {r.CT_Num_code}",
            "region": "DW",
            "caTotal": _num(r.ca_total),
            "nbCommandes": _int(r.nb_commandes),
            "derniereCommande": r.derniere_commande or "",
            "soldeImpaye": _num(r.solde_impaye),
            "segment": r.segment,
            "actif": _int(r.sommeil) == 0,
            "nouveau": False,
        }
        for r in _rows(sql)
    ]


@app.get("/api/acteurs/rfm")
def get_acteurs_rfm():
    sql = """
        SELECT TOP 200
            c.CT_Num_code,
            COALESCE(s.libelle_segment, 'Sans segment') AS segment,
            c.rfm_recence_jours,
            c.rfm_frequence,
            c.rfm_montant_12m
        FROM DIM_CLIENT c
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE c.rfm_montant_12m IS NOT NULL
           OR c.rfm_frequence   IS NOT NULL
        ORDER BY c.rfm_montant_12m DESC
    """
    return [
        {
            "code": str(r.CT_Num_code),
            "name": f"Client {r.CT_Num_code}",
            "segment": r.segment,
            "frequence": _int(r.rfm_frequence),
            "recence": _int(r.rfm_recence_jours, 999),
            "montant": _num(r.rfm_montant_12m),
        }
        for r in _rows(sql)
    ]


@app.get("/api/acteurs/aging")
def get_acteurs_aging():
    sql = """
        SELECT TOP 30
            COALESCE(CONVERT(VARCHAR(30), c.CT_Num_code), 'Client') AS client,
            SUM(CASE WHEN r.bucket_impaye = 0 THEN r.RT_Montant ELSE 0 END) AS b0,
            SUM(CASE WHEN r.bucket_impaye = 1 THEN r.RT_Montant ELSE 0 END) AS b1,
            SUM(CASE WHEN r.bucket_impaye = 2 THEN r.RT_Montant ELSE 0 END) AS b2,
            SUM(CASE WHEN r.bucket_impaye = 3 THEN r.RT_Montant ELSE 0 END) AS b3
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
        WHERE r.DR_Regle = 0
        GROUP BY c.CT_Num_code
        ORDER BY b3 DESC
    """
    return [
        {
            "clientCode": str(r.client),
            "client": f"C{r.client}",
            "0-30j": _num(r.b0),
            "31-60j": _num(r.b1),
            "61-90j": _num(r.b2),
            ">90j": _num(r.b3),
        }
        for r in _rows(sql)
    ]


@app.get("/api/acteurs/fournisseurs")
def get_acteurs_fournisseurs():
    sql = """
        SELECT TOP 100
            f.CT_Num_code,
            f.CT_Encours,
            COUNT(a.id_article) AS nb_articles
        FROM DIM_FOURNISSEUR f
        LEFT JOIN DIM_ARTICLE a ON a.id_fournisseur = f.id_fournisseur
        GROUP BY f.CT_Num_code, f.CT_Encours
        ORDER BY nb_articles DESC, f.CT_Encours DESC
    """
    return [
        {
            "code": str(r.CT_Num_code),
            "nom": f"Fournisseur {r.CT_Num_code}",
            "encours": _num(r.CT_Encours),
            "nbArticles": _int(r.nb_articles),
        }
        for r in _rows(sql)
    ]


@app.get("/api/acteurs/fournisseur-concentration")
def get_fournisseur_concentration():
    sql = """
        WITH achats AS (
            SELECT
                a.id_fournisseur,
                SUM(f.DL_MontantHT) AS montant_achat
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            JOIN DIM_ARTICLE a   ON a.id_article   = f.id_article
            WHERE dom.DO_Domaine = 1
            GROUP BY a.id_fournisseur
        ),
        total AS (
            SELECT SUM(montant_achat) AS total_achats FROM achats
        )
        SELECT TOP 20
            COALESCE(CONVERT(VARCHAR(30), f.CT_Num_code), 'Sans fournisseur') AS fournisseur,
            COUNT(a.id_article) AS nb_articles,
            COALESCE(ach.montant_achat, 0) AS montant_achat,
            CASE
                WHEN total.total_achats > 0
                THEN POWER(ach.montant_achat / total.total_achats, 2)
                ELSE 0
            END AS hhi_contribution
        FROM DIM_ARTICLE a
        LEFT JOIN DIM_FOURNISSEUR f ON f.id_fournisseur = a.id_fournisseur
        LEFT JOIN achats ach         ON ach.id_fournisseur = a.id_fournisseur
        CROSS JOIN total
        GROUP BY f.CT_Num_code, ach.montant_achat, total.total_achats
        ORDER BY montant_achat DESC
    """
    return [
        {
            "fournisseur": f"Fournisseur {r.fournisseur}",
            "nbArticles": _int(r.nb_articles),
            "montantAchat": _num(r.montant_achat),
            "hhi": round(_num(r.hhi_contribution), 4),
            "risqueConcentration": _num(r.hhi_contribution) > 0.25,
        }
        for r in _rows(sql)
    ]


@app.get("/api/banque/rapprochement")
def get_banque_rapprochement():
    sql = """
        SELECT
            d.mois AS month_num,
            AVG(CASE WHEN r.RT_Rapproche = 1 THEN 100.0 ELSE 0.0 END) AS taux,
            SUM(CASE WHEN r.RT_Rapproche = 0 THEN 1 ELSE 0 END) AS non_rapproches
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_DATE d ON d.id_date = r.id_date_paiement
        WHERE d.mois IS NOT NULL
        GROUP BY d.mois
        ORDER BY d.mois
    """
    return [
        {
            "month": MONTHS[r.month_num - 1],
            "taux": round(_num(r.taux)),
            "nonRapproches": _int(r.non_rapproches),
        }
        for r in _rows(sql)
    ]


@app.get("/api/caisse/caisses")
def get_caisses():
    sql = """
        SELECT TOP 20
            c.CA_Numero_code,
            MAX(e.CA_SoldeEspece) AS especes,
            MAX(e.CA_SoldeCheque) AS cheques
        FROM DIM_CAISSE c
        LEFT JOIN FAIT_ECRITURES e ON e.id_caisse = c.id_caisse
        GROUP BY c.CA_Numero_code
        ORDER BY c.CA_Numero_code
    """
    return [
        {
            "id": f"CA-{r.CA_Numero_code}",
            "nom": f"Caisse {r.CA_Numero_code}",
            "especes": _num(r.especes),
            "cheques": _num(r.cheques),
            "seuilMin": 20000,
            "depot": "DW",
        }
        for r in _rows(sql)
    ]


@app.get("/api/caisse/flux-daily")
def get_caisse_flux_daily():
    sql = """
        SELECT TOP 30
            d.date_val,
            SUM(e.MC_Credit) AS credit,
            SUM(e.MC_Debit)  AS debit
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        WHERE e.MC_Credit IS NOT NULL OR e.MC_Debit IS NOT NULL
        GROUP BY d.date_val
        ORDER BY d.date_val DESC
    """
    rows = list(reversed(_rows(sql)))
    cumul = 0.0
    data = []
    for i, r in enumerate(rows):
        credit = _num(r.credit)
        debit  = _num(r.debit)
        net    = credit - debit
        cumul += net
        data.append({
            "day": f"J-{len(rows) - i}",
            "credit": credit,
            "debit": -debit,
            "net": net,
            "cumul": cumul,
        })
    return data


@app.get("/api/caisse/mouvements-by-type")
def get_caisse_mouvements_by_type():
    sql = """
        SELECT TOP 10
            COALESCE(tm.libelle_type_mvt, CONCAT('Mouvement ', tm.MC_TypeMvt)) AS name,
            SUM(ABS(COALESCE(e.MC_Credit, 0)) + ABS(COALESCE(e.MC_Debit, 0))) AS value
        FROM FAIT_ECRITURES e
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = e.id_type_ligne
        LEFT JOIN DIM_TYPE_MVT_CAISSE tm ON tm.id_type_mvt = e.id_type_mvt
        WHERE tl.type_ligne = 3
        GROUP BY tm.libelle_type_mvt, tm.MC_TypeMvt
        ORDER BY SUM(ABS(COALESCE(e.MC_Credit, 0)) + ABS(COALESCE(e.MC_Debit, 0))) DESC
    """
    return [{"name": r.name, "value": _num(r.value)} for r in _rows(sql)]


@app.get("/api/fiscalite/kpis")
def get_fiscalite_kpis():
    row = _row(
        """
        SELECT
            COUNT(*) AS nb_ecritures,
            SUM(CASE WHEN t.type_tva = 1 THEN e.RT_Montant01 ELSE 0 END) AS tva_collectee,
            SUM(CASE WHEN t.type_tva = 2 THEN e.RT_Montant01 ELSE 0 END) AS tva_deductible,
            SUM(CASE WHEN ABS(COALESCE(e.EC_Montant, 0)) > 30000 THEN 1 ELSE 0 END) AS anomalies
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_TYPE_TVA t ON t.id_type_tva = e.id_type_tva
        """
    )
    debit_credit = _row(
        """
        SELECT
            SUM(CASE WHEN s.EC_Sens = 0 THEN ABS(e.EC_Montant) ELSE 0 END) AS debit,
            SUM(CASE WHEN s.EC_Sens = 1 THEN ABS(e.EC_Montant) ELSE 0 END) AS credit
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_SENS_ECRITURE s ON s.id_sens = e.id_sens
        """
    )
    debit = _num(debit_credit.debit)
    credit = _num(debit_credit.credit)
    total = max(debit, credit)
    return {
        "nb_ecritures": _int(row.nb_ecritures),
        "tva_collectee": _num(row.tva_collectee),
        "tva_deductible": _num(row.tva_deductible),
        "anomalies": _int(row.anomalies),
        "equilibre_pct": (min(debit, credit) / total * 100) if total else 100,
    }


@app.get("/api/fiscalite/journaux")
def get_fiscalite_journaux():
    sql = """
        SELECT TOP 10
            COALESCE(CONVERT(VARCHAR(30), j.JO_Num_code), 'Sans journal') AS journal,
            SUM(CASE WHEN s.EC_Sens = 0 THEN ABS(e.EC_Montant) ELSE 0 END) AS debit,
            SUM(CASE WHEN s.EC_Sens = 1 THEN ABS(e.EC_Montant) ELSE 0 END) AS credit
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_JOURNAL j ON j.id_journal = e.id_journal
        LEFT JOIN DIM_SENS_ECRITURE s ON s.id_sens = e.id_sens
        GROUP BY j.JO_Num_code
        ORDER BY
            SUM(CASE WHEN s.EC_Sens = 0 THEN ABS(e.EC_Montant) ELSE 0 END)
          + SUM(CASE WHEN s.EC_Sens = 1 THEN ABS(e.EC_Montant) ELSE 0 END)
          DESC
    """
    return [{"journal": f"Journal {r.journal}", "debit": _num(r.debit), "credit": _num(r.credit)} for r in _rows(sql)]


@app.get("/api/fiscalite/tva-by-month")
def get_fiscalite_tva_by_month():
    sql = """
        SELECT
            d.mois AS month_num,
            SUM(CASE WHEN t.type_tva = 1 THEN e.RT_Montant01 ELSE 0 END) AS collectee,
            SUM(CASE WHEN t.type_tva = 2 THEN e.RT_Montant01 ELSE 0 END) AS deductible
        FROM FAIT_ECRITURES e
        JOIN DIM_DATE d ON d.id_date = e.id_date
        LEFT JOIN DIM_TYPE_TVA t ON t.id_type_tva = e.id_type_tva
        WHERE e.RT_Montant01 IS NOT NULL
        GROUP BY d.mois
        ORDER BY d.mois
    """
    return [
        {
            "month": MONTHS[r.month_num - 1],
            "collectee": _num(r.collectee),
            "deductible": _num(r.deductible),
            "soldeNet": _num(r.collectee) - _num(r.deductible),
        }
        for r in _rows(sql)
    ]


@app.get("/api/fiscalite/anomalies")
def get_fiscalite_anomalies():
    sql = """
        SELECT TOP 100
            d.date_val,
            COALESCE(CONVERT(VARCHAR(30), j.JO_Num_code), 'Journal') AS journal,
            ABS(COALESCE(e.EC_Montant, 0)) AS montant,
            CASE
                WHEN ABS(COALESCE(e.EC_Montant, 0)) >= 100000 THEN 0.95
                WHEN ABS(COALESCE(e.EC_Montant, 0)) >= 50000 THEN 0.85
                WHEN ABS(COALESCE(e.EC_Montant, 0)) >= 30000 THEN 0.70
                ELSE 0.25
            END AS score
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        LEFT JOIN DIM_JOURNAL j ON j.id_journal = e.id_journal
        WHERE e.EC_Montant IS NOT NULL
        ORDER BY montant DESC
    """
    return [
        {
            "date": _date_str(r.date_val),
            "score": _num(r.score),
            "montant": _num(r.montant),
            "journal": r.journal,
            "anomalie": _num(r.score) >= 0.8,
        }
        for r in _rows(sql)
    ]


@app.get("/api/fiscalite/balance-by-month")
def get_fiscalite_balance_by_month():
    sql = """
        SELECT
            d.mois AS month_num,
            SUM(CASE WHEN s.EC_Sens = 0 THEN ABS(e.EC_Montant) ELSE 0 END) AS debit,
            SUM(CASE WHEN s.EC_Sens = 1 THEN ABS(e.EC_Montant) ELSE 0 END) AS credit
        FROM FAIT_ECRITURES e
        JOIN DIM_DATE d ON d.id_date = e.id_date
        LEFT JOIN DIM_SENS_ECRITURE s ON s.id_sens = e.id_sens
        GROUP BY d.mois
        ORDER BY d.mois
    """
    return [
        {
            "month": MONTHS[r.month_num - 1],
            "debit": _num(r.debit),
            "credit": _num(r.credit),
            "ecart": _num(r.debit) - _num(r.credit),
        }
        for r in _rows(sql)
    ]


@app.get("/api/fiscalite/ecritures")
def get_fiscalite_ecritures():
    sql = """
        SELECT TOP 100
            d.date_val,
            e.EC_No,
            COALESCE(CONVERT(VARCHAR(30), j.JO_Num_code), 'Journal') AS journal,
            e.CG_Num,
            e.EC_Montant,
            s.EC_Sens
        FROM FAIT_ECRITURES e
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        LEFT JOIN DIM_JOURNAL j ON j.id_journal = e.id_journal
        LEFT JOIN DIM_SENS_ECRITURE s ON s.id_sens = e.id_sens
        ORDER BY d.date_val DESC, e.id_ecriture DESC
    """
    rows = []
    for r in _rows(sql):
        montant = _num(r.EC_Montant)
        is_debit = _int(r.EC_Sens) == 0
        rows.append({
            "date": _date_str(r.date_val),
            "numPiece": f"EC-{r.EC_No or ''}",
            "journal": r.journal,
            "compte": str(r.CG_Num or ""),
            "libelle": f"Ecriture {r.EC_No or ''}",
            "debit": montant if is_debit else 0,
            "credit": 0 if is_debit else montant,
            "solde": montant if is_debit else -montant,
        })
    return rows


@app.get("/api/notifications")
def get_notifications():
    try:
        stock = get_stock_alerts()[:6]
    except Exception:
        stock = []
    try:
        impayes = get_impayes()[:6]
    except Exception:
        impayes = []
    items = []
    for a in stock:
        items.append({
            "id": f"stock-{a['article']}",
            "type": "stock",
            "severity": "critical" if a["priorite"] == "CRITIQUE" else "warning",
            "title": a["designation"],
            "message": f"Stock critique - {a['stockActuel']:.0f} unites restantes",
            "meta": a["famille"],
            "time": "DW",
        })
    for i in impayes:
        items.append({
            "id": f"pay-{i['code']}-{i['anciennete']}",
            "type": "payment",
            "severity": "critical" if i["anciennete"] > 90 else "warning",
            "title": i["client"],
            "message": f"Impaye {i['anciennete']}j - {i['montantImpaye']:.0f} DT",
            "meta": i["region"],
            "time": i["dateEcheance"] or "DW",
        })
    return items


@app.get("/api/search")
def search(q: str = ""):
    needle = f"%{q.strip()}%"
    if not q.strip():
        return {"clients": [], "articles": [], "ecritures": [], "fournisseurs": []}
    clients = _rows(
        "SELECT TOP 5 CT_Num_code, CT_SoldeActuel FROM DIM_CLIENT "
        "WHERE CONVERT(VARCHAR(30), CT_Num_code) LIKE :q ORDER BY CT_Num_code",
        {"q": needle},
    )
    articles = _rows(
        "SELECT TOP 5 AR_Ref_code, id_famille FROM DIM_ARTICLE "
        "WHERE CONVERT(VARCHAR(30), AR_Ref_code) LIKE :q ORDER BY AR_Ref_code",
        {"q": needle},
    )
    ecritures = _rows(
        "SELECT TOP 5 EC_No, CG_Num, EC_Montant FROM FAIT_ECRITURES "
        "WHERE CONVERT(VARCHAR(30), EC_No) LIKE :q OR CONVERT(VARCHAR(30), CG_Num) LIKE :q "
        "ORDER BY id_ecriture DESC",
        {"q": needle},
    )
    fournisseurs = _rows(
        "SELECT TOP 5 CT_Num_code, CT_Encours FROM DIM_FOURNISSEUR "
        "WHERE CONVERT(VARCHAR(30), CT_Num_code) LIKE :q ORDER BY CT_Num_code",
        {"q": needle},
    )
    return {
        "clients": [{"label": f"Client {r.CT_Num_code}", "subtitle": f"Solde {round(_num(r.CT_SoldeActuel))} DT", "to": "/acteurs"} for r in clients],
        "articles": [{"label": f"Article {r.AR_Ref_code}", "subtitle": f"Famille {r.id_famille or 'N/A'}", "to": "/produits"} for r in articles],
        "ecritures": [{"label": f"Ecriture {r.EC_No or ''}", "subtitle": f"Compte {r.CG_Num or ''} - {round(_num(r.EC_Montant))} DT", "to": "/fiscalite"} for r in ecritures],
        "fournisseurs": [{"label": f"Fournisseur {r.CT_Num_code}", "subtitle": f"Encours {round(_num(r.CT_Encours))} DT", "to": "/acteurs"} for r in fournisseurs],
    }


@app.get("/api/assistant/summary")
def get_assistant_summary():
    result = {
        "kpis": {}, "tresorerie": {}, "articles": [],
        "clients": [], "impayes": [], "stockAlerts": [],
    }
    with DW_ENGINE.connect() as conn:
        def _q(sql, params=None):
            return conn.execute(text(sql), params or {}).fetchall()
        def _qone(sql, params=None):
            return conn.execute(text(sql), params or {}).fetchone()

        try:
            kpi_row = _qone("""
                WITH latest AS (
                    SELECT COALESCE(MAX(d.annee), YEAR(GETDATE())) AS latest_year
                    FROM FAIT_LIGNES_VENTE f
                    JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
                    LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
                    WHERE dom.DO_Domaine = 0
                )
                SELECT SUM(f.DL_MontantHT) AS ca_total,
                       COUNT(DISTINCT f.DO_Piece_hash) AS nb_commandes,
                       COUNT(DISTINCT f.id_client) AS nb_clients_actifs,
                       SUM(f.DL_MontantHT - (f.DL_Qte * COALESCE(a.AR_PrixAch,0))) AS marge_brute
                FROM FAIT_LIGNES_VENTE f
                JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
                LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
                LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
                CROSS JOIN latest
                WHERE dom.DO_Domaine = 0 AND d.annee = latest.latest_year
            """)
            ca = _num(kpi_row.ca_total)
            result["kpis"] = {
                "ca_total": ca,
                "nb_commandes": _int(kpi_row.nb_commandes),
                "nb_clients_actifs": _int(kpi_row.nb_clients_actifs),
                "marge_brute_pct": (_num(kpi_row.marge_brute) / ca * 100) if ca else 0,
                "taux_recouvrement": 0,
            }
        except Exception:
            pass

        try:
            tr = _qone("""
                SELECT SUM(CASE WHEN DR_Regle=1 THEN RT_Montant ELSE 0 END) AS enc,
                       SUM(CASE WHEN DR_Regle=0 THEN RT_Montant ELSE 0 END) AS imp,
                       AVG(CAST(delai_reel_jours AS FLOAT)) AS delai
                FROM FAIT_REGLEMENTS
            """)
            enc = _num(tr.enc); imp = _num(tr.imp); tot = enc + imp
            result["tresorerie"] = {
                "encaissements": enc, "impayes": imp,
                "delai_moyen": round(_num(tr.delai)),
                "taux_recouvrement": (enc / tot * 100) if tot else 0,
            }
            result["kpis"]["taux_recouvrement"] = result["tresorerie"]["taux_recouvrement"]
        except Exception:
            pass

        try:
            result["articles"] = [
                {"code": f"ART-{r.AR_Ref_code}", "ca": _num(r.ca),
                 "stock": _num(r.stock), "dsi": _num(r.dsi_jours)}
                for r in _q("""
                    WITH sales AS (
                        SELECT id_article, COALESCE(SUM(DL_MontantHT),0) AS ca
                        FROM FAIT_LIGNES_VENTE f
                        JOIN DIM_DOMAINE dom ON dom.id_domaine=f.id_domaine
                        WHERE dom.DO_Domaine=0 GROUP BY id_article
                    ),
                    stock AS (
                        SELECT e.id_article, MAX(e.AS_QteSto) AS stock, MAX(e.dsi_jours) AS dsi_jours
                        FROM FAIT_ECRITURES e
                        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne=e.id_type_ligne AND tl.type_ligne=4
                        GROUP BY e.id_article
                    )
                    SELECT TOP 20 a.AR_Ref_code, COALESCE(sales.ca,0) AS ca,
                           stock.stock, stock.dsi_jours
                    FROM DIM_ARTICLE a
                    LEFT JOIN sales ON sales.id_article=a.id_article
                    LEFT JOIN stock ON stock.id_article=a.id_article
                    ORDER BY ca DESC
                """)
            ]
        except Exception:
            pass

        try:
            result["clients"] = [
                {"code": str(r.CT_Num_code), "rfm_recence": _int(r.rfm_recence_jours, 999),
                 "rfm_frequence": _int(r.rfm_frequence), "rfm_montant": _num(r.rfm_montant_12m),
                 "soldeImpaye": _num(r.solde_impaye)}
                for r in _q("""
                    SELECT TOP 20 c.CT_Num_code, c.rfm_recence_jours, c.rfm_frequence,
                           c.rfm_montant_12m, c.CT_SoldeActuel AS solde_impaye
                    FROM DIM_CLIENT c
                    ORDER BY c.rfm_montant_12m DESC
                """)
            ]
        except Exception:
            pass

        try:
            result["impayes"] = [
                {"client": f"Client {r.CT_Num_code}", "montant": _num(r.montant_impaye),
                 "anciennete": _int(r.anciennete)}
                for r in _q("""
                    SELECT TOP 20 c.CT_Num_code, SUM(r.RT_Montant) AS montant_impaye,
                           MAX(r.delai_reel_jours) AS anciennete
                    FROM FAIT_REGLEMENTS r JOIN DIM_CLIENT c ON c.id_client=r.id_client
                    WHERE r.DR_Regle=0 GROUP BY c.CT_Num_code
                    HAVING SUM(r.RT_Montant)>0 ORDER BY montant_impaye DESC
                """)
            ]
        except Exception:
            pass

        try:
            result["stockAlerts"] = [
                {"article": f"ART-{r.AR_Ref_code}", "stockActuel": _num(r.AS_QteSto),
                 "seuil": _num(r.AS_QteMini), "ratioTension": _num(r.ratio_tension)}
                for r in _q("""
                    SELECT TOP 20 a.AR_Ref_code, f.AS_QteSto, f.AS_QteMini, f.ratio_tension
                    FROM FAIT_ECRITURES f
                    JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne=f.id_type_ligne
                    JOIN DIM_ARTICLE a ON a.id_article=f.id_article
                    WHERE tl.type_ligne=4 AND f.en_rupture=1
                      AND f.AS_QteSto IS NOT NULL AND f.ratio_tension IS NOT NULL
                    ORDER BY f.ratio_tension DESC
                """)
            ]
        except Exception:
            pass

    return result




class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]

_FINANCIAL_KEYWORDS = {
    "ca", "chiffre", "client", "clients", "stock", "stocks", "impaye", "impayes",
    "tresorerie", "marge", "vente", "ventes", "article", "articles", "kpi",
    "analyse", "analyser", "donnee", "donnees", "rapport",
}
_CASUAL_CA_PHRASES = {"ca va", "comment ca va", "ca marche", "ca roule"}


def _normalize_intent_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _asks_financial_question(text: str) -> bool:
    normalized = _normalize_intent_text(text)
    compact = " ".join(normalized.split())
    if any(phrase in compact for phrase in _CASUAL_CA_PHRASES):
        compact = re.sub(r"ca (va|marche|roule)|comment ca va", "", compact)
    words = set(re.findall(r"[a-z0-9]+", compact))
    if words & _FINANCIAL_KEYWORDS:
        return True
    return "chiffre d affaires" in compact or "data warehouse" in compact


def _build_dw_context() -> str:
    ctx: dict = {}
    try:
        summary = get_assistant_summary()
        ctx["kpis"]          = summary.get("kpis", {})
        ctx["tresorerie"]    = summary.get("tresorerie", {})
        ctx["top_articles"]  = summary.get("articles", [])[:10]
        ctx["top_clients"]   = summary.get("clients", [])[:10]
        ctx["impayes"]       = summary.get("impayes", [])[:10]
        ctx["alertes_stock"] = summary.get("stockAlerts", [])[:10]
    except Exception as exc:
        ctx["error"] = str(exc)
    return json.dumps(ctx, ensure_ascii=False, default=str)


def _gemini_history(messages: List[ChatMessage]) -> list:
    return [
        genai.types.Content(
            role="user" if msg.role == "user" else "model",
            parts=[genai.types.Part(text=msg.content)],
        )
        for msg in messages[:-1]
    ]


@app.get("/api/assistant/status")
def get_assistant_status():
    return {"llm_ready": _LLM_READY, "model": _GEMINI_MODEL if _LLM_READY else None}


@app.post("/api/assistant/chat")
def assistant_chat(req: ChatRequest):
    if not _LLM_READY or _GEMINI_CLIENT is None:
        def _no_key():
            yield "data: Ajoutez GEMINI_API_KEY dans etl/.env pour activer l'IA.\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_no_key(), media_type="text/event-stream")

    if not req.messages:
        return StreamingResponse(iter(["data: [DONE]\n\n"]), media_type="text/event-stream")

    current_user_text = req.messages[-1].content
    is_financial_question = _asks_financial_question(current_user_text)

    if is_financial_question:
        dw_ctx = _build_dw_context()
        prompt = (
            "[DONNEES LIVE DU DATA WAREHOUSE - MAG Distribution]\n"
            + dw_ctx
            + "\n\n[QUESTION UTILISATEUR]\n"
            + current_user_text
        )
        contents = _gemini_history(req.messages) + [
            genai.types.Content(role="user", parts=[genai.types.Part(text=prompt)])
        ]
    else:
        contents = [
            genai.types.Content(role="user", parts=[genai.types.Part(text=current_user_text)])
        ]

    def _stream():
        try:
            response = _GEMINI_CLIENT.models.generate_content_stream(
                model=_GEMINI_MODEL,
                contents=contents,
                config=genai.types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
            )
            for chunk in response:
                text_chunk = chunk.text if chunk.text else ""
                if text_chunk:
                    for line in text_chunk.splitlines(keepends=True):
                        yield f"data: {line}"
                    if not text_chunk.endswith("\n"):
                        yield "\n"
                    yield "\n"
        except Exception as exc:
            yield f"data: Erreur LLM : {exc}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
