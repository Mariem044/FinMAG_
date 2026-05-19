from sqlalchemy import text
from etl.config import DW_ENGINE

with DW_ENGINE.connect() as conn:
    rows = conn.execute(text("SELECT * FROM DIM_BANQUE")).fetchall()
    for r in rows:
        print(dict(r._mapping))
