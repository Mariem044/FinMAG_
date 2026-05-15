"""
Run from project root: python diag_region2.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from etl.config import DW_ENGINE, MAG_ENGINE
from sqlalchemy import text

def q(engine, sql, params=None):
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchall()

print("\n" + "="*60)
print("STEP 1: CT_CodeRegion distinct values (MAG)")
print("="*60)
for r in q(MAG_ENGINE, """
    SELECT CT_CodeRegion, COUNT(*) as nb
    FROM F_COMPTET WHERE CT_Type = 0
    AND CT_CodeRegion IS NOT NULL AND CT_CodeRegion <> ''
    GROUP BY CT_CodeRegion ORDER BY nb DESC
"""):
    print(dict(r._mapping))

print("\n" + "="*60)
print("STEP 2: DIGID_CA_CLIENT_PAR_REGION view — columns + sample")
print("="*60)
try:
    for r in q(MAG_ENGINE, """
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'DIGID_CA_CLIENT_PAR_REGION_AVEC_CATEGORIE_TARIFAIRE'
        ORDER BY ORDINAL_POSITION
    """):
        print(r[0])
    print("--- Sample rows ---")
    for r in q(MAG_ENGINE, """
        SELECT TOP 10 * FROM DIGID_CA_CLIENT_PAR_REGION_AVEC_CATEGORIE_TARIFAIRE
    """):
        print(dict(r._mapping))
except Exception as e:
    print(f"Error: {e}")

print("\n" + "="*60)
print("STEP 3: CT_Ville + CT_CodeRegion sample for clients (MAG)")
print("="*60)
for r in q(MAG_ENGINE, """
    SELECT TOP 20 CT_Num, CT_Intitule, CT_Ville, CT_CodeRegion
    FROM F_COMPTET WHERE CT_Type = 0
    AND CT_Ville IS NOT NULL AND CT_Ville <> ''
    ORDER BY CT_Num
"""):
    print(dict(r._mapping))

print("\nDONE")