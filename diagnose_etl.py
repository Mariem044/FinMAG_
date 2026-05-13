"""
ETL Diagnostic Script
Run this from your project root: python diagnose_etl.py
It tests every extraction and reports row counts + sample data.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

# ── 1. Engine connectivity ────────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 1 — Engine connectivity")
print("="*60)

try:
    from etl.config import MAG_ENGINE, GRT_ENGINE, DW_ENGINE
    print("✅ Config imported OK")
except Exception as e:
    print(f"❌ Config import FAILED: {e}")
    sys.exit(1)

for name, engine in [("MAG", MAG_ENGINE), ("GRT", GRT_ENGINE), ("DW", DW_ENGINE)]:
    try:
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        print(f"✅ {name}_ENGINE connected OK")
    except Exception as e:
        print(f"❌ {name}_ENGINE FAILED: {e}")


# ── 2. Table existence on MAG ─────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 2 — Key tables exist on MAG_ENGINE")
print("="*60)

MAG_TABLES = [
    "F_DOCLIGNE", "F_DOCENTETE", "F_ECRITUREC", "F_REGTAXE",
    "F_ARTSTOCK", "F_ARTICLE", "F_COMPTET", "F_FAMILLE",
    "F_COLLABORATEUR", "F_DEPOT", "F_JOURNAUX", "F_EBANQUE",
    "F_CAISSE", "P_DOSSIER", "P_CATTARIF",
]

from sqlalchemy import text

for tbl in MAG_TABLES:
    try:
        with MAG_ENGINE.connect() as conn:
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM {tbl}")
            ).scalar()
        status = "✅" if count > 0 else "⚠️ EMPTY"
        print(f"  {status}  {tbl:<30} {count:>10} rows")
    except Exception as e:
        print(f"  ❌  {tbl:<30} ERROR: {e}")


# ── 3. Table existence on GRT ─────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 3 — Key tables exist on GRT_ENGINE")
print("="*60)

GRT_TABLES = [
    "F_COMPTET", "F_ReglementClient", "F_ReglementFournisseur",
    "F_DOCREGL", "F_MvtCaisse", "F_Caisse",
    "F_LigneBordereauRemise", "F_BordereauRemise", "F_REGLECH",
]

for tbl in GRT_TABLES:
    try:
        with GRT_ENGINE.connect() as conn:
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM {tbl}")
            ).scalar()
        status = "✅" if count > 0 else "⚠️ EMPTY"
        print(f"  {status}  {tbl:<35} {count:>10} rows")
    except Exception as e:
        print(f"  ❌  {tbl:<35} ERROR: {e}")


# ── 4. Extract function tests ─────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 4 — Extract functions (row counts + sample)")
print("="*60)

from etl import extract

EXTRACTIONS = [
    ("extract_fait_ecriturec",          lambda: extract.extract_fait_ecriturec()),
    ("extract_fait_regtaxe",            lambda: extract.extract_fait_regtaxe()),
    ("extract_fait_artstock",           lambda: extract.extract_fait_artstock()),
    ("extract_fait_lignes_vente",       lambda: extract.extract_fait_lignes_vente()),
    ("extract_fait_lignes_achat",       lambda: extract.extract_fait_lignes_achat()),
    ("extract_dim_article",             lambda: extract.extract_dim_article()),
    ("extract_dim_famille",             lambda: extract.extract_dim_famille()),
    ("extract_dim_client_mag",          lambda: extract.extract_dim_client_mag()),
    ("extract_dim_client_grt",          lambda: extract.extract_dim_client_grt()),
    ("extract_dim_fournisseur",         lambda: extract.extract_dim_fournisseur()),
    ("extract_dim_collaborateur",       lambda: extract.extract_dim_collaborateur()),
    ("extract_dim_journal",             lambda: extract.extract_dim_journal()),
    ("extract_dim_depot",               lambda: extract.extract_dim_depot()),
    ("extract_dim_banque_mag",          lambda: extract.extract_dim_banque_mag()),
    ("extract_dim_caisse_mag",          lambda: extract.extract_dim_caisse_mag()),
    ("extract_dim_segment",             lambda: extract.extract_dim_segment()),
    ("extract_exercices_fiscaux",       lambda: pd.DataFrame(extract.extract_exercices_fiscaux())),
    ("extract_fait_reglements_clients", lambda: extract.extract_fait_reglements_clients()),
    ("extract_fait_reglements_fourn",   lambda: extract.extract_fait_reglements_fournisseurs()),
    ("extract_fait_mvtcaisse",          lambda: extract.extract_fait_mvtcaisse()),
    ("extract_docregl_grt",             lambda: extract.extract_docregl_grt()),
    ("extract_reglementt",              lambda: extract.extract_reglementt()),
    ("extract_docentete_dates",         lambda: extract.extract_docentete_dates()),
    ("extract_fait_reglech",            lambda: extract.extract_fait_reglech()),
]

CRITICAL_COLS = {
    "extract_fait_ecriturec":    ["EC_No", "EC_Date", "EC_Montant", "CG_Num", "CT_Num"],
    "extract_fait_artstock":     ["AR_Ref", "DE_No", "AS_QteSto", "AS_MontSto"],
    "extract_fait_lignes_vente": ["DO_Piece", "DL_MontantHT", "AR_Ref", "CT_Num"],
    "extract_dim_famille":       ["FA_CodeFamille", "FA_Intitule"],
}

for name, fn in EXTRACTIONS:
    try:
        df = fn()
        n = len(df)
        status = "✅" if n > 0 else "⚠️  EMPTY"
        print(f"\n  {status}  {name}  →  {n} rows")
        print(f"         columns: {list(df.columns)}")

        # Check critical columns
        if name in CRITICAL_COLS:
            for col in CRITICAL_COLS[name]:
                if col not in df.columns:
                    print(f"         ❌  MISSING COLUMN: {col}")
                elif n > 0:
                    nulls = df[col].isna().sum()
                    zeros = (df[col] == 0).sum() if df[col].dtype != object else 0
                    print(f"         col {col:<20} nulls={nulls}  zeros={zeros}  "
                          f"sample={df[col].dropna().iloc[0] if nulls < n else 'ALL NULL'}")

        # Show first row for critical tables
        if n > 0 and name in ("extract_fait_ecriturec", "extract_fait_artstock"):
            print(f"         first row:\n{df.iloc[0].to_dict()}")

    except Exception as e:
        print(f"\n  ❌  {name}  →  EXCEPTION: {e}")


# ── 5. DW tables row counts ───────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 5 — DW tables row counts (after last ETL run)")
print("="*60)

DW_TABLES = [
    "DIM_DATE", "DIM_CLIENT", "DIM_ARTICLE", "DIM_FAMILLE",
    "DIM_SEGMENT", "DIM_COLLABORATEUR", "DIM_JOURNAL",
    "DIM_FOURNISSEUR", "DIM_DEPOT", "DIM_CAISSE", "DIM_BANQUE",
    "FAIT_LIGNES_VENTE", "FAIT_REGLEMENTS", "FAIT_ECRITURES", "ETL_AUDIT",
]

for tbl in DW_TABLES:
    try:
        with DW_ENGINE.connect() as conn:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
        status = "✅" if count > 0 else "⚠️ EMPTY"
        print(f"  {status}  {tbl:<30} {count:>10} rows")
    except Exception as e:
        print(f"  ❌  {tbl:<30} ERROR: {e}")


# ── 6. FAIT_ECRITURES spot-check ──────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 6 — FAIT_ECRITURES spot-check (EC_Montant, EC_No, id_date)")
print("="*60)

try:
    with DW_ENGINE.connect() as conn:
        rows = conn.execute(text("""
            SELECT TOP 5
                id_ecriture, EC_No, EC_Montant,
                id_date, id_type_ligne, date_extraction
            FROM FAIT_ECRITURES
            ORDER BY id_ecriture DESC
        """)).fetchall()
    if not rows:
        print("  ⚠️  FAIT_ECRITURES is empty")
    for r in rows:
        print(f"  id={r.id_ecriture}  EC_No={r.EC_No}  "
              f"EC_Montant={r.EC_Montant}  id_date={r.id_date}  "
              f"type_ligne={r.id_type_ligne}  extracted={r.date_extraction}")
except Exception as e:
    print(f"  ❌ {e}")

# ── 6b. FAIT_ECRITURES montant distribution ───────────────────────────────────
try:
    with DW_ENGINE.connect() as conn:
        agg = conn.execute(text("""
            SELECT
                id_type_ligne,
                COUNT(*) AS nb,
                SUM(CASE WHEN EC_Montant IS NULL THEN 1 ELSE 0 END) AS nulls,
                SUM(CASE WHEN EC_Montant = 0    THEN 1 ELSE 0 END) AS zeros,
                AVG(ABS(EC_Montant)) AS avg_abs_montant
            FROM FAIT_ECRITURES
            GROUP BY id_type_ligne
        """)).fetchall()
    print("\n  EC_Montant distribution by type_ligne:")
    for r in agg:
        print(f"    type_ligne={r.id_type_ligne}  nb={r.nb}  "
              f"nulls={r.nulls}  zeros={r.zeros}  avg_abs={r.avg_abs_montant}")
except Exception as e:
    print(f"  ❌ {e}")


# ── 7. DIM_FAMILLE / DIM_ARTICLE label check ──────────────────────────────────
print("\n" + "="*60)
print("STEP 7 — FA_Intitule populated in DIM_FAMILLE and DIM_ARTICLE")
print("="*60)

for tbl, col in [("DIM_FAMILLE", "FA_Intitule"), ("DIM_ARTICLE", "FA_Intitule")]:
    try:
        with DW_ENGINE.connect() as conn:
            r = conn.execute(text(f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN {col} IS NULL OR {col} = '' THEN 1 ELSE 0 END) AS empty,
                    MAX({col}) AS sample
                FROM {tbl}
            """)).fetchone()
        print(f"  {tbl}.{col}: total={r.total}  empty={r.empty}  sample={r.sample!r}")
    except Exception as e:
        print(f"  ❌ {tbl}: {e}")


# ── 8. ETL_AUDIT last runs ────────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 8 — ETL_AUDIT last 5 pipeline runs")
print("="*60)

try:
    with DW_ENGINE.connect() as conn:
        runs = conn.execute(text("""
            SELECT TOP 5 run_id, run_date, mode, status,
                         duration_seconds, error_msg
            FROM ETL_AUDIT
            WHERE table_name = 'PIPELINE'
            ORDER BY run_date DESC
        """)).fetchall()
    for r in runs:
        print(f"  run_id={r.run_id}  {r.run_date}  mode={r.mode}  "
              f"status={r.status}  dur={r.duration_seconds}s  "
              f"error={r.error_msg or 'none'}")
except Exception as e:
    print(f"  ❌ {e}")

print("\n" + "="*60)
print("DIAGNOSTIC COMPLETE — share this output to pinpoint the bugs")
print("="*60 + "\n")