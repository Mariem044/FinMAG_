import sys
import os
from sqlalchemy import text

sys.path.append(os.path.abspath("."))
from etl.config import DW_ENGINE

with DW_ENGINE.connect() as conn:
    print("Available years in FAIT_ECRITURES (type_ligne = 4):")
    res = conn.execute(text("""
        SELECT d.annee, COUNT(*) AS cnt
        FROM FAIT_ECRITURES e
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = e.id_type_ligne AND tl.type_ligne = 4
        LEFT JOIN DIM_DATE d ON d.id_date = e.id_date
        GROUP BY d.annee
        ORDER BY d.annee
    """)).fetchall()
    for row in res:
        print(f"  Year: {row[0]}, Count: {row[1]}")
