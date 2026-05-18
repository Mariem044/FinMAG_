import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from etl.config import MAG_ENGINE
from sqlalchemy import text

with MAG_ENGINE.connect() as conn:
    print("--- CORRECTING SAGE ERP SOURCE DB BYPASSING TRIGGERS ---")
    try:
        # 1. Disable triggers
        print("Disabling triggers on F_DOCLIGNE...")
        conn.execute(text("DISABLE TRIGGER ALL ON F_DOCLIGNE"))
        print("Triggers disabled successfully.")
        
        # 2. Run updates
        print("Updating Marwa 1.5L row (cbMarq=298076)...")
        upd_marwa = """
            UPDATE F_DOCLIGNE
            SET DL_CMUP = 0.4828,
                cbModification = GETDATE()
            WHERE cbMarq = 298076
        """
        res_marwa = conn.execute(text(upd_marwa))
        print("Updated Marwa row.")
        
        print("Updating Safia 0.5L rows (cbMarq in 339915, 340591, etc.)...")
        upd_safia = """
            UPDATE F_DOCLIGNE
            SET DL_CMUP = 3.9710,
                cbModification = GETDATE()
            WHERE cbMarq IN (339915, 340591, 340884, 342682, 342789, 345464, 342786, 341197, 342348)
        """
        res_safia = conn.execute(text(upd_safia))
        print("Updated Safia rows.")
        
        # Commit the transaction
        conn.commit()
        print("Updates committed successfully.")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        # Rollback in case of error
        try:
            conn.rollback()
            print("Transaction rolled back.")
        except Exception:
            pass
        raise e
        
    finally:
        # 3. Always re-enable triggers
        print("Re-enabling triggers on F_DOCLIGNE...")
        conn.execute(text("ENABLE TRIGGER ALL ON F_DOCLIGNE"))
        conn.commit()
        print("Triggers re-enabled successfully.")

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
