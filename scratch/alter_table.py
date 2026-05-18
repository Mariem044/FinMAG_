import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from etl.config import DW_ENGINE
from sqlalchemy import text

with DW_ENGINE.begin() as conn:
    conn.execute(text("ALTER TABLE DIM_FOURNISSEUR ADD CT_Intitule NVARCHAR(100) NULL;"))
    print("Column CT_Intitule added to DIM_FOURNISSEUR.")
