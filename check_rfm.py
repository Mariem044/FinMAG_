import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy import text
from etl.config import DW_ENGINE

with DW_ENGINE.connect() as c:
    rows = c.execute(text("""
        SELECT rfm_score, COUNT(*) AS nb
        FROM DIM_CLIENT
        GROUP BY rfm_score
        ORDER BY nb DESC
    """)).fetchall()
    for r in rows:
        print(f"  '{r.rfm_score}' : {r.nb} clients")
