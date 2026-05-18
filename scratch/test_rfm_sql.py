import sys
from sqlalchemy import text

sys.path.insert(0, r"c:\Users\marie\Desktop\myProject\FINMAG")

from etl.config import DW_ENGINE

with DW_ENGINE.connect() as conn:
    sql = """
        WITH latest_date AS (
            SELECT MAX(d.date_val) AS max_dt
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DATE d ON d.id_date = f.id_date
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            WHERE dom.DO_Domaine = 0
        ),
        client_stats AS (
            SELECT
                f.id_client,
                COUNT(DISTINCT CONCAT(f.DO_Piece_hash, '-', COALESCE(f.id_type_doc, 0))) AS freq,
                SUM(f.DL_MontantHT) AS mont,
                MAX(d.date_val) AS last_purchase_dt
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DATE d ON d.id_date = f.id_date
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            WHERE dom.DO_Domaine = 0
            GROUP BY f.id_client
        )
        SELECT TOP 10
            c.id_client,
            c.CT_Num_code,
            c.CT_Intitule,
            DATEDIFF(day, cs.last_purchase_dt, ld.max_dt) AS rfm_recence_jours,
            cs.freq AS rfm_frequence,
            cs.mont AS rfm_montant_12m
        FROM DIM_CLIENT c
        JOIN client_stats cs ON cs.id_client = c.id_client
        CROSS JOIN latest_date ld
        ORDER BY cs.mont DESC
    """
    rows = conn.execute(text(sql)).fetchall()
    print("----- DYNAMIC RFM QUERY TEST -----")
    for r in rows:
        print(dict(r._mapping))
