import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy import text
from etl.config import MAG_ENGINE

with MAG_ENGINE.connect() as conn:

    print("=== F_ARTICLE price columns ===")
    rows = conn.execute(text("""
        SELECT TOP 5 
            AR_Ref,
            AR_PrixAch,
            AR_PrixVen,
            AR_PrixTTC,
            AR_Coef
        FROM F_ARTICLE
        WHERE AR_PrixAch > 0 OR AR_Coef > 0
    """)).fetchall()
    for r in rows:
        print(f"  Ref={r[0]} | PrixAch={r[1]} | PrixVen={r[2]} | PrixTTC={r[3]} | Coef={r[4]}")

    print("\n=== AR_Coef distribution ===")
    row = conn.execute(text("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN AR_Coef > 0 THEN 1 ELSE 0 END) as has_coef,
            SUM(CASE WHEN AR_PrixAch > 0 THEN 1 ELSE 0 END) as has_prix_ach,
            SUM(CASE WHEN AR_PrixVen > 0 THEN 1 ELSE 0 END) as has_prix_ven
        FROM F_ARTICLE
    """)).fetchone()
    print(f"  Total: {row[0]} | Has Coef: {row[1]} | Has PrixAch: {row[2]} | Has PrixVen: {row[3]}")

    print("\n=== F_ARTPRIX — alternate price table ===")
    try:
        rows = conn.execute(text("""
            SELECT TOP 5 * FROM F_ARTPRIX
        """)).fetchall()
        for r in rows:
            print(f"  {r}")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n=== F_DOCLIGNE cost columns ===")
    rows = conn.execute(text("""
        SELECT TOP 5
            DO_Piece,
            DL_MontantHT,
            DL_PrixRU,
            DL_CMUP,
            DL_Qte
        FROM F_DOCLIGNE
        WHERE DO_Domaine = 0
        AND DO_Type IN (6,7)
        AND DL_PrixRU > 0
    """)).fetchall()
    for r in rows:
        print(f"  Piece={r[0]} | MontantHT={r[1]} | PrixRU={r[2]} | CMUP={r[3]} | Qte={r[4]}")

    print("\n=== DL_CMUP availability ===")
    row = conn.execute(text("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN DL_CMUP > 0 THEN 1 ELSE 0 END) as has_cmup,
            SUM(CASE WHEN DL_PrixRU > 0 THEN 1 ELSE 0 END) as has_prixru
        FROM F_DOCLIGNE
        WHERE DO_Domaine = 0 AND DO_Type IN (6,7)
    """)).fetchone()
    print(f"  Total vente lines: {row[0]} | Has CMUP: {row[1]} | Has PrixRU: {row[2]}")