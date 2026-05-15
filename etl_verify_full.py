import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy import text
from etl.config import DW_ENGINE, MAG_ENGINE, GRT_ENGINE

def q(engine, sql):
    with engine.connect() as c:
        return c.execute(text(sql)).fetchall()

def n(engine, sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()

print("\n=== SOURCE COUNTS ===")
print("MAG clients:", n(MAG_ENGINE, "SELECT COUNT(*) FROM F_COMPTET WHERE CT_Type=0"))
print("MAG articles:", n(MAG_ENGINE, "SELECT COUNT(*) FROM F_ARTICLE"))
print("MAG ventes:", n(MAG_ENGINE, "SELECT COUNT(*) FROM F_DOCLIGNE WHERE DO_Domaine=0 AND DO_Type IN(6,7)"))
print("MAG ecritures:", n(MAG_ENGINE, "SELECT COUNT(*) FROM F_ECRITUREC WHERE EC_Montant IS NOT NULL"))
print("GRT reglements:", n(GRT_ENGINE, "SELECT COUNT(*) FROM F_ReglementClient"))

print("\n=== DW COUNTS ===")
for t in ["DIM_CLIENT","DIM_ARTICLE","DIM_FAMILLE","FAIT_LIGNES_VENTE","FAIT_REGLEMENTS","FAIT_ECRITURES"]:
    print(f"{t}:", n(DW_ENGINE, f"SELECT COUNT(*) FROM {t}"))

print("\n=== LAST ETL RUN ===")
rows = q(DW_ENGINE, "SELECT TOP 3 run_id, run_date, status, duration_seconds, error_msg FROM ETL_AUDIT WHERE table_name='PIPELINE' ORDER BY run_date DESC")
for r in rows:
    print(f"  run_id={r.run_id} | {r.run_date} | {r.status} | {r.duration_seconds}s | {r.error_msg}")

print("\n=== DONE ===")
