import sys
from sqlalchemy import text

sys.path.insert(0, r"c:\Users\marie\Desktop\myProject\FINMAG")

from etl.config import MAG_ENGINE, GRT_ENGINE

def search_database_schema(engine, db_name):
    print(f"\n===== SEARCHING SCHEMA OF SOURCE DB: {db_name} =====")
    with engine.connect() as conn:
        # Search table names
        sql_tables = """
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_NAME LIKE '%livr%' 
               OR TABLE_NAME LIKE '%chauff%' 
               OR TABLE_NAME LIKE '%transp%' 
               OR TABLE_NAME LIKE '%exped%'
        """
        tables = [r[0] for r in conn.execute(text(sql_tables)).fetchall()]
        print(f"Tables matching search terms: {tables}")
        
        # Search column names
        sql_cols = """
            SELECT TABLE_NAME, COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE COLUMN_NAME LIKE '%livr%' 
               OR COLUMN_NAME LIKE '%chauff%' 
               OR COLUMN_NAME LIKE '%transp%' 
               OR COLUMN_NAME LIKE '%exped%'
            ORDER BY TABLE_NAME, COLUMN_NAME
        """
        cols = conn.execute(text(sql_cols)).fetchall()
        print(f"Columns matching search terms: {len(cols)} columns found.")
        if len(cols) > 0:
            print("Sample matching columns (first 15):")
            for r in cols[:15]:
                print(f"  {r.TABLE_NAME}.{r.COLUMN_NAME}")

print("Searching MAG database...")
try:
    search_database_schema(MAG_ENGINE, "MAG_2020")
except Exception as e:
    print(f"Error searching MAG database: {e}")

print("\nSearching GRT database...")
try:
    search_database_schema(GRT_ENGINE, "GRT_MAG")
except Exception as e:
    print(f"Error searching GRT database: {e}")
