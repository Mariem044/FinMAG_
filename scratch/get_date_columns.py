import sys
from sqlalchemy import text

sys.path.insert(0, r"c:\Users\marie\Desktop\myProject\FINMAG")

from etl.config import DW_ENGINE

with DW_ENGINE.connect() as conn:
    sql = """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'DIM_DATE'
    """
    rows = conn.execute(text(sql)).fetchall()
    print("----- DIM_DATE COLUMNS -----")
    for r in rows:
        print(f"{r.COLUMN_NAME}: {r.DATA_TYPE}")
