import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from etl.config import MAG_ENGINE
from sqlalchemy import text

with MAG_ENGINE.connect() as conn:
    print("--- TYPICAL CMUP VALUES FOR ANOMALOUS ARTICLES ---")
    
    # Check Marwa 1.5L (1002010211)
    sql_marwa = """
        SELECT DISTINCT TOP 10
            DL_CMUP,
            COUNT(*) as occurrences
        FROM F_DOCLIGNE
        WHERE AR_Ref = '1002010211'
        AND DL_CMUP IS NOT NULL
        AND DL_CMUP > 0
        AND DL_CMUP < 10.0 -- realistic range
        GROUP BY DL_CMUP
        ORDER BY occurrences DESC
    """
    rows = conn.execute(text(sql_marwa)).fetchall()
    print("Marwa 1.5L (1002010211) - Typical CMUP values:")
    for r in rows:
        print(f"  CMUP: {r.DL_CMUP:,.4f} DT | Occurrences: {r.occurrences}")
        
    # Check Safia 0.5L (1002010321)
    sql_safia = """
        SELECT DISTINCT TOP 10
            DL_CMUP,
            COUNT(*) as occurrences
        FROM F_DOCLIGNE
        WHERE AR_Ref = '1002010321'
        AND DL_CMUP IS NOT NULL
        AND DL_CMUP > 0
        AND DL_CMUP < 10.0 -- realistic range
        GROUP BY DL_CMUP
        ORDER BY occurrences DESC
    """
    rows = conn.execute(text(sql_safia)).fetchall()
    print("\nSafia 0.5L (1002010321) - Typical CMUP values:")
    for r in rows:
        print(f"  CMUP: {r.DL_CMUP:,.4f} DT | Occurrences: {r.occurrences}")
