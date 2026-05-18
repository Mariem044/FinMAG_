import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from etl.config import DW_ENGINE
from sqlalchemy import text

with DW_ENGINE.connect() as conn:
    print("--- TOP 10 LARGEST DISCREPANCIES (LOSS-MAKING LINES) ---")
    sql = """
        SELECT TOP 10
            f.DO_Piece_hash,
            a.AR_Ref,
            a.AR_Design,
            f.DL_Qte,
            f.DL_MontantHT,
            f.DL_CMUP,
            (f.DL_Qte * f.DL_CMUP) AS total_cost,
            f.DL_MontantHT - (f.DL_Qte * f.DL_CMUP) AS margin
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_ARTICLE a ON a.id_article = f.id_article
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        WHERE dom.DO_Domaine = 0
        AND d.annee = 2024
        AND f.DL_MontantHT < (f.DL_Qte * f.DL_CMUP)
        ORDER BY margin ASC
    """
    rows = conn.execute(text(sql)).fetchall()
    for i, r in enumerate(rows, 1):
        print(f"{i}. Piece Hash: {r.DO_Piece_hash}")
        print(f"   Article: {r.AR_Ref} - {r.AR_Design}")
        print(f"   Qte Sold: {r.DL_Qte:,.2f} | Montant HT: {r.DL_MontantHT:,.2f} DT")
        print(f"   Unit Cost (CMUP): {r.DL_CMUP:,.2f} DT | Total Cost: {r.total_cost:,.2f} DT")
        print(f"   Row Loss: {r.margin:,.2f} DT")
        print("-" * 50)
