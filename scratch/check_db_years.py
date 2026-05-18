import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from etl.config import DW_ENGINE
from sqlalchemy import text

with DW_ENGINE.connect() as conn:
    print("--- YEARS IN DIM_DATE ---")
    sql_dim_date = "SELECT DISTINCT annee FROM DIM_DATE WHERE annee IS NOT NULL ORDER BY annee DESC"
    rows = conn.execute(text(sql_dim_date)).fetchall()
    print("Years in DIM_DATE:", [r.annee for r in rows])
    
    print("\n--- YEARS IN FAIT_LIGNES_VENTE (SALES) ---")
    sql_sales = """
        SELECT DISTINCT d.annee
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DATE d ON f.id_date = d.id_date
        WHERE d.annee IS NOT NULL
        ORDER BY d.annee DESC
    """
    rows = conn.execute(text(sql_sales)).fetchall()
    print("Years in FAIT_LIGNES_VENTE:", [r.annee for r in rows])
