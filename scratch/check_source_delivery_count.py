import sys
from sqlalchemy import text

sys.path.insert(0, r"c:\Users\marie\Desktop\myProject\FINMAG")

from etl.config import MAG_ENGINE

with MAG_ENGINE.connect() as conn:
    sql = """
        SELECT 
            LIVREUR, 
            COUNT(*) AS nb_livraisons,
            SUM(DO_NetAPayer) AS volume_livre
        FROM O2S_VW_PREPARATION_LIVRAISON
        WHERE LIVREUR IS NOT NULL AND LIVREUR <> ''
        GROUP BY LIVREUR
        ORDER BY volume_livre DESC
    """
    rows = conn.execute(text(sql)).fetchall()
    print("----- MAG_2020 DELIVERY STATS BY DRIVER -----")
    for r in rows:
        print(f"Livreur: {r.LIVREUR} | Deliveries: {r.nb_livraisons} | Volume: {r.volume_livre:,.2f} TND")
