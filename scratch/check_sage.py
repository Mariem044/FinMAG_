import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from etl.config import MAG_ENGINE
from sqlalchemy import text

with MAG_ENGINE.connect() as conn:
    print("--- SAGE SOURCE DATABASE (F_DOCLIGNE) CHECK ---")
    sql = """
        SELECT TOP 5
            DO_Piece,
            AR_Ref,
            DL_Qte,
            DL_MontantHT,
            DL_CMUP,
            cbModification
        FROM F_DOCLIGNE
        WHERE DO_Domaine = 0
        AND AR_Ref = '1002010211'
        AND DL_CMUP > 1000
    """
    rows = conn.execute(text(sql)).fetchall()
    if not rows:
        print("No anomalous rows found in Sage itself for article 1002010211 with CMUP > 1000!")
    for i, r in enumerate(rows, 1):
        print(f"{i}. DO_Piece: {r.DO_Piece} | AR_Ref: {r.AR_Ref}")
        print(f"   Qte: {r.DL_Qte} | Montant HT: {r.DL_MontantHT} | CMUP: {r.DL_CMUP}")
        print(f"   cbModification: {r.cbModification}")
