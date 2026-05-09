# api/main.py
"""
FinMAG API — v14.2
Fixes applied vs v14.1:
  FIX-DEPOT   : get_ca_by_region() — removed f.id_depot JOIN on FAIT_LIGNES_VENTE;
                id_depot was dropped from that table in schema v11 (FIX-9/BUG-10).
                Sales are now grouped by DIM_CLIENT.id_segment as a meaningful proxy,
                or by a direct client-count breakdown when no depot is available.
  FIX-FAMILLE : get_top_familles() — joined DIM_FAMILLE → FA_CodeFamille_code and
                DIM_ARTICLE to surface the famille surrogate; label falls back to
                the code when no intitule is stored (DIM_FAMILLE has no libelle col).
  FIX-REGION  : get_ca_by_region() now groups by segment label instead of a
                non-existent depot FK, giving meaningful data without a schema change.
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from etl.config import DW_ENGINE

app = FastAPI(title="FinMAG API")

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


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/dashboard/kpis")
def get_dashboard_kpis():
    sql = """
        WITH latest AS (
            SELECT COALESCE(MAX(d.annee), YEAR(GETDATE())) AS latest_year
            FROM FAIT_LIGNES_VENTE f
            LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        )
        SELECT
            SUM(f.DL_MontantHT) AS ca_total,
            COUNT(DISTINCT f.DO_Piece_hash) AS nb_commandes,
            COUNT(DISTINCT f.id_client) AS nb_clients_actifs,
            SUM(f.DL_MontantHT - (f.DL_Qte * COALESCE(a.AR_PrixAch, 0))) AS marge_brute
        FROM FAIT_LIGNES_VENTE f
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
        CROSS JOIN latest
        WHERE d.annee = latest.latest_year
    """
    row = _row(sql)
    ca_total = _num(row.ca_total)
    marge_brute = _num(row.marge_brute)
    return {
        "ca_total": ca_total,
        "nb_commandes": _int(row.nb_commandes),
        "nb_clients_actifs": _int(row.nb_clients_actifs),
        "taux_recouvrement": get_tresorerie_summary()["taux_recouvrement"],
        "marge_brute_pct": (marge_brute / ca_total * 100) if ca_total else 0,
    }


@app.get("/api/ventes/ca-by-month")
def get_ca_by_month():
    sql = """
        WITH latest AS (
            SELECT COALESCE(MAX(d.annee), YEAR(GETDATE())) AS latest_year
            FROM FAIT_LIGNES_VENTE f
            LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        ),
        monthly AS (
            SELECT d.annee, d.mois, SUM(f.DL_MontantHT) AS ca
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DATE d ON d.id_date = f.id_date
            CROSS JOIN latest
            WHERE d.annee IN (latest.latest_year, latest.latest_year - 1)
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
    # FIX-FAMILLE: join through DIM_ARTICLE to reach DIM_FAMILLE.
    # DIM_FAMILLE has no libelle column (only FA_CodeFamille_code) so we fall
    # back to the surrogate id as a label. Extend this query if you add a
    # libelle_famille column to DIM_FAMILLE in a future migration.
    sql = """
        SELECT TOP 8
            COALESCE(
                CONVERT(VARCHAR(30), fa.FA_CodeFamille_code),
                'Sans famille'
            ) AS name,
            SUM(f.DL_MontantHT) AS ca
        FROM FAIT_LIGNES_VENTE f
        LEFT JOIN DIM_ARTICLE a  ON a.id_article  = f.id_article
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
        GROUP BY fa.FA_CodeFamille_code
        ORDER BY ca DESC
    """
    return [
        {"name": f"Famille {r.name}", "ca": _num(r.ca)}
        for r in _rows(sql)
    ]


@app.get("/api/ventes/ca-by-region")
def get_ca_by_region():
    # FIX-DEPOT: FAIT_LIGNES_VENTE no longer has id_depot (removed in schema
    # v11, FIX-9/BUG-10). Grouping by client segment is the closest meaningful
    # breakdown available without a depot FK on the fact table.
    sql = """
        SELECT TOP 12
            COALESCE(s.libelle_segment, 'Sans segment') AS name,
            SUM(f.DL_MontantHT)          AS ca,
            COUNT(DISTINCT f.id_client)  AS clients,
            COUNT(DISTINCT f.DO_Piece_hash) AS commandes
        FROM FAIT_LIGNES_VENTE f
        LEFT JOIN DIM_CLIENT  c ON c.id_client  = f.id_client
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
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
        ORDER BY mag + grt DESC
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
    # tl.type_ligne is correct since v14 DDL rename (FIX-2 already applied in v14.1)
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
        SELECT TOP 100
            a.AR_Ref_code,
            a.id_famille,
            a.AR_PrixAch,
            COALESCE(SUM(v.DL_Qte), 0) AS qte_vendue,
            COALESCE(SUM(v.DL_MontantHT), 0) AS ca,
            MAX(e.AS_QteSto) AS stock,
            MAX(e.dsi_jours) AS dsi_jours
        FROM DIM_ARTICLE a
        LEFT JOIN FAIT_LIGNES_VENTE v ON v.id_article = a.id_article
        LEFT JOIN FAIT_ECRITURES e ON e.id_article = a.id_article
        LEFT JOIN DIM_TYPE_LIGNE tl
            ON tl.id_type_ligne = e.id_type_ligne
            AND tl.type_ligne = 4
        GROUP BY a.AR_Ref_code, a.id_famille, a.AR_PrixAch
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
    # BUG-11 fix: FORMAT() returns ISO-8601 'YYYY-MM-DD' directly from SQL Server.
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


@app.get("/api/banque/rapprochement")
def get_banque_rapprochement():
    # FIX-1: id_date_paiement (renamed from id_date in v14 DDL)
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
        ORDER BY debit + credit DESC
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
    stock = get_stock_alerts()[:6]
    impayes = get_impayes()[:6]
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
        """
        SELECT TOP 5 CT_Num_code, CT_SoldeActuel
        FROM DIM_CLIENT
        WHERE CONVERT(VARCHAR(30), CT_Num_code) LIKE :q
        ORDER BY CT_Num_code
        """,
        {"q": needle},
    )
    articles = _rows(
        """
        SELECT TOP 5 AR_Ref_code, id_famille
        FROM DIM_ARTICLE
        WHERE CONVERT(VARCHAR(30), AR_Ref_code) LIKE :q
        ORDER BY AR_Ref_code
        """,
        {"q": needle},
    )
    ecritures = _rows(
        """
        SELECT TOP 5 EC_No, CG_Num, EC_Montant
        FROM FAIT_ECRITURES
        WHERE CONVERT(VARCHAR(30), EC_No) LIKE :q OR CONVERT(VARCHAR(30), CG_Num) LIKE :q
        ORDER BY id_ecriture DESC
        """,
        {"q": needle},
    )
    fournisseurs = _rows(
        """
        SELECT TOP 5 CT_Num_code, CT_Encours
        FROM DIM_FOURNISSEUR
        WHERE CONVERT(VARCHAR(30), CT_Num_code) LIKE :q
        ORDER BY CT_Num_code
        """,
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
    return {
        "kpis": get_dashboard_kpis(),
        "tresorerie": get_tresorerie_summary(),
        "articles": get_articles()[:20],
        "clients": get_clients()[:20],
        "impayes": get_impayes()[:20],
        "stockAlerts": get_stock_alerts()[:20],
    }
