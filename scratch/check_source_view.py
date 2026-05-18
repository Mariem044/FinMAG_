import sys
from sqlalchemy import text

sys.path.insert(0, r"c:\Users\marie\Desktop\myProject\FINMAG")

from etl.config import MAG_ENGINE

with MAG_ENGINE.connect() as conn:
    print("----- O2S_VW_LISTE_DES_LIVREURS SCHEMAS -----")
    sql_cols = """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'O2S_VW_LISTE_DES_LIVREURS'
    """
    for r in conn.execute(text(sql_cols)).fetchall():
        print(f"  {r.COLUMN_NAME}: {r.DATA_TYPE}")
        
    print("\n----- O2S_VW_LISTE_DES_LIVREURS DATA SAMPLE -----")
    try:
        sql_data = "SELECT TOP 10 * FROM O2S_VW_LISTE_DES_LIVREURS"
        rows = conn.execute(text(sql_data)).fetchall()
        print(f"Total rows retrieved: {len(rows)}")
        for r in rows:
            print(dict(r._mapping))
    except Exception as e:
        print(f"Error querying view: {e}")
