"""
Quick verification + delta filter diagnosis
Run from project root: python verify.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from etl.config import DW_ENGINE, MAG_ENGINE

print("\n=== DW TABLE COUNTS ===")
tables = [
    "DIM_ARTICLE", "DIM_FAMILLE", "DIM_CLIENT",
    "FAIT_LIGNES_VENTE", "FAIT_REGLEMENTS", "FAIT_ECRITURES",
]
with DW_ENGINE.connect() as conn:
    for tbl in tables:
        n = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
        print(f"  {tbl:<30} {n:>10} rows")

print("\n=== FA_Intitule in DIM_ARTICLE ===")
with DW_ENGINE.connect() as conn:
    r = conn.execute(text("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN FA_Intitule IS NULL OR FA_Intitule = '' THEN 1 ELSE 0 END) AS empty
        FROM DIM_ARTICLE
    """)).fetchone()
print(f"  Populated: {r.total - r.empty}/{r.total}")

print("\n=== FAIT_ECRITURES breakdown by type_ligne ===")
with DW_ENGINE.connect() as conn:
    rows = conn.execute(text("""
        SELECT tl.type_ligne, tl.libelle_type_ligne, COUNT(*) AS nb
        FROM FAIT_ECRITURES fe
        LEFT JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
        GROUP BY tl.type_ligne, tl.libelle_type_ligne
        ORDER BY tl.type_ligne
    """)).fetchall()
for r in rows:
    print(f"  type_ligne={r.type_ligne} ({r.libelle_type_ligne}): {r.nb} rows")

print("\n=== DELTA FILTER DIAGNOSIS ===")
print("Last successful run date:")
with DW_ENGINE.connect() as conn:
    last = conn.execute(text("""
        SELECT MAX(run_date) FROM ETL_AUDIT
        WHERE status = 'SUCCESS' AND table_name = 'PIPELINE'
    """)).scalar()
print(f"  {last}")

print("\nF_ECRITUREC rows that WOULD be picked by delta filter:")
with MAG_ENGINE.connect() as conn:
    n = conn.execute(text("""
        SELECT COUNT(*) FROM F_ECRITUREC
        WHERE EC_Date >= :last_run
    """), {"last_run": last}).scalar()
    total = conn.execute(text("SELECT COUNT(*) FROM F_ECRITUREC")).scalar()
print(f"  {n}/{total} rows have EC_Date >= last run")

print("\nF_DOCLIGNE rows that WOULD be picked by delta filter:")
with MAG_ENGINE.connect() as conn:
    n = conn.execute(text("""
        SELECT COUNT(*) FROM F_DOCLIGNE dl
        WHERE dl.DO_Date >= :last_run
        AND dl.DO_Domaine = 0 AND dl.DO_Type IN (6,7)
        AND dl.DL_MontantHT IS NOT NULL
    """), {"last_run": last}).scalar()
    total = conn.execute(text("""
        SELECT COUNT(*) FROM F_DOCLIGNE
        WHERE DO_Domaine=0 AND DO_Type IN (6,7) AND DL_MontantHT IS NOT NULL
    """)).scalar()
print(f"  {n}/{total} vente rows have DO_Date >= last run")

print("\n=== RFM scores in DIM_CLIENT ===")
with DW_ENGINE.connect() as conn:
    r = conn.execute(text("""
        SELECT
            SUM(CASE WHEN rfm_score IS NOT NULL THEN 1 ELSE 0 END) AS scored,
            SUM(CASE WHEN rfm_montant_12m IS NOT NULL THEN 1 ELSE 0 END) AS has_montant,
            COUNT(*) AS total
        FROM DIM_CLIENT
    """)).fetchone()
print(f"  RFM scored: {r.scored}/{r.total}, has montant: {r.has_montant}/{r.total}")

print("\n=== DSI in FAIT_ECRITURES ===")
with DW_ENGINE.connect() as conn:
    r = conn.execute(text("""
        SELECT
            SUM(CASE WHEN dsi_jours IS NOT NULL THEN 1 ELSE 0 END) AS has_dsi,
            SUM(CASE WHEN qte_vendue_365j IS NOT NULL THEN 1 ELSE 0 END) AS has_qte,
            COUNT(*) AS total
        FROM FAIT_ECRITURES fe
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
        WHERE tl.type_ligne = 4
    """)).fetchone()
print(f"  DSI computed: {r.has_dsi}/{r.total} stock rows, qte_vendue: {r.has_qte}/{r.total}")

print("\n=== SAGE DATE RANGES ===")
with MAG_ENGINE.connect() as conn:
    r = conn.execute(text("""
        SELECT 
            MIN(DO_Date) AS min_date,
            MAX(DO_Date) AS max_date,
            COUNT(*) AS total
        FROM F_DOCLIGNE
        WHERE DO_Domaine=0 AND DO_Type IN (6,7)
        AND DL_MontantHT IS NOT NULL
    """)).fetchone()
print(f"  F_DOCLIGNE ventes: {r.min_date} → {r.max_date} ({r.total} rows)")

with MAG_ENGINE.connect() as conn:
    r = conn.execute(text("""
        SELECT MIN(EC_Date) AS min_date, MAX(EC_Date) AS max_date
        FROM F_ECRITUREC
    """)).fetchone()
print(f"  F_ECRITUREC:       {r.min_date} → {r.max_date}")

with MAG_ENGINE.connect() as conn:
    r = conn.execute(text("""
        SELECT MIN(cbModification) AS min_mod, MAX(cbModification) AS max_mod
        FROM F_DOCLIGNE
        WHERE DO_Domaine=0 AND DO_Type IN (6,7)
    """)).fetchone()
print(f"  F_DOCLIGNE cbModification: {r.min_mod} → {r.max_mod}")

print("\n=== DONE ===\n")