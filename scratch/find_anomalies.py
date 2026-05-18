import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from etl.config import MAG_ENGINE
from sqlalchemy import text

with MAG_ENGINE.connect() as conn:
    print("--- SCANNING FOR ALL CMUP ANOMALIES IN SAGE (F_DOCLIGNE) ---")
    sql = """
        SELECT
            cbMarq,
            DO_Piece,
            AR_Ref,
            DL_Qte,
            DL_MontantHT,
            DL_CMUP,
            cbModification
        FROM F_DOCLIGNE
        WHERE AR_Ref IN ('1002010211', '1002010321')
        AND DL_CMUP > 10.0
        ORDER BY AR_Ref, DL_CMUP DESC
    """
    rows = conn.execute(text(sql)).fetchall()
    print(f"Found {len(rows)} anomalous records:")
    for i, r in enumerate(rows, 1):
        print(f"{i}. cbMarq: {r.cbMarq} | DO_Piece: {r.DO_Piece} | AR_Ref: {r.AR_Ref}")
        print(f"   Qte: {r.DL_Qte:,.2f} | Montant HT: {r.DL_MontantHT:,.2f} DT | CMUP: {r.DL_CMUP:,.4f} DT")
        print(f"   cbModification: {r.cbModification}")
        print("-" * 50)
