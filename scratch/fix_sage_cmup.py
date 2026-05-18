import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from etl.config import MAG_ENGINE
from sqlalchemy import text

with MAG_ENGINE.connect() as conn:
    trans = conn.begin()
    try:
        print("--- CORRECTING SAGE ERP SOURCE DB (F_DOCLIGNE) ---")
        
        # 1. Update Marwa 1.5L row
        print("Updating Marwa 1.5L row (cbMarq=298076)...")
        upd_marwa = """
            UPDATE F_DOCLIGNE
            SET DL_CMUP = 0.4828,
                cbModification = GETDATE()
            WHERE cbMarq = 298076
        """
        res_marwa = conn.execute(text(upd_marwa))
        print(f"Updated {res_marwa.rowcount} row.")
        
        # 2. Update Safia 0.5L rows
        safia_ids = (339915, 340591, 340884, 342682, 342789, 345464, 342786, 341197, 342348)
        print(f"Updating Safia 0.5L rows (cbMarq in {safia_ids})...")
        upd_safia = """
            UPDATE F_DOCLIGNE
            SET DL_CMUP = 3.9710,
                cbModification = GETDATE()
            WHERE cbMarq IN :ids
        """
        res_safia = conn.execute(text(upd_safia), {"ids": safia_ids})
        print(f"Updated {res_safia.rowcount} rows.")
        
        trans.commit()
        print("Transaction committed successfully!")
        
    except Exception as e:
        trans.rollback()
        print(f"Error during update, rolled back: {e}")
        raise e

with MAG_ENGINE.connect() as conn:
    print("\n--- VERIFYING SAVED CMUP VALUES IN SAGE ---")
    sql_check = """
        SELECT
            cbMarq,
            DO_Piece,
            AR_Ref,
            DL_Qte,
            DL_MontantHT,
            DL_CMUP,
            cbModification
        FROM F_DOCLIGNE
        WHERE cbMarq IN (298076, 339915, 340591, 340884, 342682, 342789, 345464, 342786, 341197, 342348)
    """
    rows = conn.execute(text(sql_check)).fetchall()
    for r in rows:
        print(f"cbMarq: {r.cbMarq} | Piece: {r.DO_Piece} | Article: {r.AR_Ref} | CMUP: {r.DL_CMUP:.4f} | ModDate: {r.cbModification}")
