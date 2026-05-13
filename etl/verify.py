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

print("\n=== FAIT_REGLEMENTS DEDUP CHECK ===")
with DW_ENGINE.connect() as conn:
    r = conn.execute(text("""
        SELECT
            COUNT(*) AS total_rows,
            COUNT(DISTINCT RT_Num) AS distinct_rt_num,
            COUNT(*) - COUNT(DISTINCT RT_Num) AS duplicate_rows,
            SUM(CASE WHEN DR_Regle = 1 AND id_client IS NOT NULL THEN RT_Montant ELSE 0 END) AS encaissements_raw,
            SUM(CASE WHEN DR_Regle = 0 AND id_client IS NOT NULL THEN RT_Montant ELSE 0 END) AS impayes_raw
        FROM FAIT_REGLEMENTS
        WHERE RT_Num IS NOT NULL
    """)).fetchone()
print(f"  Total rows:       {r.total_rows}")
print(f"  Distinct RT_Num:  {r.distinct_rt_num}")
print(f"  Duplicate rows:   {r.duplicate_rows}  (should be 0 after fix)")
print(f"  Encaissements raw (no dedup): {r.encaissements_raw:,.0f}")
print(f"  Impayes raw (no dedup):       {r.impayes_raw:,.0f}")

print("\n=== FAIT_REGLEMENTS DEDUPED TOTALS ===")
with DW_ENGINE.connect() as conn:
    r = conn.execute(text("""
        WITH deduped AS (
            SELECT RT_Num,
                   MAX(RT_Montant) AS RT_Montant,
                   MAX(DR_Regle)   AS DR_Regle,
                   MAX(id_client)  AS id_client
            FROM FAIT_REGLEMENTS
            WHERE RT_Num IS NOT NULL AND id_client IS NOT NULL
            GROUP BY RT_Num
        )
        SELECT
            SUM(CASE WHEN DR_Regle = 1 THEN RT_Montant ELSE 0 END) AS encaissements,
            SUM(CASE WHEN DR_Regle = 0 THEN RT_Montant ELSE 0 END) AS impayes
        FROM deduped
    """)).fetchone()
print(f"  Encaissements (deduped): {r.encaissements:,.0f}")
print(f"  Impayes (deduped):       {r.impayes:,.0f}")

print("\n=== STOCK SNAPSHOT CHECK ===")
with DW_ENGINE.connect() as conn:
    r = conn.execute(text("""
        SELECT
            COUNT(*) AS total_stock_rows,
            SUM(CASE WHEN AS_QteSto IS NOT NULL AND AS_QteSto > 0 THEN 1 ELSE 0 END) AS rows_with_stock,
            SUM(CASE WHEN en_rupture = 1 THEN 1 ELSE 0 END) AS ruptures,
            SUM(CASE WHEN dsi_jours IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_dsi,
            SUM(CASE WHEN ratio_tension IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_tension
        FROM FAIT_ECRITURES fe
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
        WHERE tl.type_ligne = 4
    """)).fetchone()
print(f"  Stock rows total:    {r.total_stock_rows}")
print(f"  Rows with stock > 0: {r.rows_with_stock}  (should be > 0)")
print(f"  Ruptures:            {r.ruptures}")
print(f"  Rows with DSI:       {r.rows_with_dsi}")
print(f"  Rows with tension:   {r.rows_with_tension}")

print("\n=== MARGIN SANITY CHECK ===")
with DW_ENGINE.connect() as conn:
    r = conn.execute(text("""
        WITH latest AS (
            SELECT MAX(d.annee) AS latest_year
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
            JOIN DIM_DATE d ON d.id_date = f.id_date
            WHERE dom.DO_Domaine = 0
        )
        SELECT
            SUM(f.DL_MontantHT) AS ca_total,
            SUM(CASE WHEN a.AR_PrixAch IS NOT NULL AND a.AR_PrixAch > 0
                THEN f.DL_MontantHT ELSE 0 END) AS ca_avec_cout,
            SUM(CASE WHEN a.AR_PrixAch IS NOT NULL AND a.AR_PrixAch > 0
                THEN f.DL_MontantHT - (f.DL_Qte * a.AR_PrixAch)
                ELSE NULL END) AS marge_brute,
            COUNT(CASE WHEN a.AR_PrixAch IS NOT NULL AND a.AR_PrixAch > 0
                THEN 1 END) AS nb_lignes_avec_cout,
            COUNT(*) AS nb_lignes_total
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        JOIN DIM_DATE d ON d.id_date = f.id_date
        LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
        CROSS JOIN latest
        WHERE dom.DO_Domaine = 0 AND d.annee = latest.latest_year
    """)).fetchone()
ca = float(r.ca_total or 0)
ca_cout = float(r.ca_avec_cout or 0)
marge = float(r.marge_brute or 0)
pct_cout = (ca_cout / ca * 100) if ca else 0
marge_pct = (marge / ca_cout * 100) if ca_cout else 0
print(f"  CA total:              {ca:>15,.0f}")
print(f"  CA with cost data:     {ca_cout:>15,.0f}  ({pct_cout:.1f}% of CA has AR_PrixAch)")
print(f"  Marge brute:           {marge:>15,.0f}")
print(f"  Marge %% (on CA+cout): {marge_pct:>14.1f}%%  (expected 15-30%%)")
print(f"  Lines with cost:       {r.nb_lignes_avec_cout}/{r.nb_lignes_total}")

print("\n=== DONE ===\n")