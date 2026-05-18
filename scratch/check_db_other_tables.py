import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from etl.config import DW_ENGINE
from sqlalchemy import text

with DW_ENGINE.connect() as conn:
    print("--- YEARS IN FAIT_ECRITURES ---")
    sql_ecr = """
        SELECT DISTINCT d.annee
        FROM FAIT_ECRITURES f
        JOIN DIM_DATE d ON f.id_date = d.id_date
        WHERE d.annee IS NOT NULL
        ORDER BY d.annee DESC
    """
    rows = conn.execute(text(sql_ecr)).fetchall()
    print("Years in FAIT_ECRITURES:", [r.annee for r in rows])
    
    print("\n--- YEARS IN FAIT_REGLEMENTS ---")
    sql_reg = """
        SELECT DISTINCT d.annee
        FROM FAIT_REGLEMENTS f
        JOIN DIM_DATE d ON f.id_date = d.id_date
        WHERE d.annee IS NOT NULL
        ORDER BY d.annee DESC
    """
    rows = conn.execute(text(sql_reg)).fetchall()
    print("Years in FAIT_REGLEMENTS:", [r.annee for r in rows])
