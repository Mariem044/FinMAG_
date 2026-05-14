import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy import text
from etl.config import DW_ENGINE

with DW_ENGINE.connect() as conn:
    print("en_rupture distribution:")
    rows = conn.execute(text("""
        SELECT en_rupture, COUNT(*) as cnt 
        FROM FAIT_ECRITURES 
        WHERE id_type_ligne = 84
        GROUP BY en_rupture
    """)).fetchall()
    for r in rows: print(f"  en_rupture={r[0]} | count={r[1]}")

    print("\nratio_tension distribution:")
    rows = conn.execute(text("""
        SELECT 
            SUM(CASE WHEN ratio_tension IS NULL THEN 1 ELSE 0 END) as null_cnt,
            SUM(CASE WHEN ratio_tension > 0.8 THEN 1 ELSE 0 END) as high_cnt,
            SUM(CASE WHEN ratio_tension <= 0.8 THEN 1 ELSE 0 END) as low_cnt,
            MIN(AS_QteSto) as min_sto,
            MAX(AS_QteSto) as max_sto,
            MIN(AS_QteMini) as min_mini,
            MAX(AS_QteMini) as max_mini
        FROM FAIT_ECRITURES
        WHERE id_type_ligne = 84
    """)).fetchone()
    print(f"  null ratio={r[0]} | high>{0.8}={rows[1]} | low={rows[2]}")
    print(f"  QteSto: {rows[3]} to {rows[4]}")
    print(f"  QteMini: {rows[5]} to {rows[6]}")