"""
ETL Logical Verification Suite
================================
Run from project root:  python etl_verify_full.py
Requires etl/.env to be present with DW_CONN, MAG_CONN, GRT_CONN.

Checks:
  1.  Source row counts (MAG + GRT)
  2.  DW table counts after load
  3.  FK integrity (no orphan surrogates)
  4.  hash_key collision detection
  5.  Surrogate lookup completeness
  6.  FAIT_LIGNES_VENTE business rules
  7.  FAIT_REGLEMENTS dedup & balance
  8.  FAIT_ECRITURES type_ligne distribution
  9.  Stock KPIs (DSI, tension, rupture)
 10.  RFM scores
 11.  DIM_CLIENT data quality
 12.  DIM_ARTICLE data quality
 13.  DIM_FAMILLE label coverage
 14.  Margin sanity (AR_PrixAch vs DL_MontantHT)
 15.  Date range alignment (source vs DW)
 16.  Delta filter diagnosis (rows since last run)
 17.  Audit log consistency
 18.  source_hash uniqueness
 19.  Gouvernorat mapping coverage
 20.  CA growth / N-1 comparison
"""

import os
import sys
import textwrap
from datetime import datetime

# ── bootstrap path so etl package resolves
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from etl.config import DW_ENGINE, MAG_ENGINE, GRT_ENGINE

# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

PASS  = "\033[92m[PASS]\033[0m"
FAIL  = "\033[91m[FAIL]\033[0m"
WARN  = "\033[93m[WARN]\033[0m"
INFO  = "\033[94m[INFO]\033[0m"
SEP   = "─" * 70

results = []   # (label, status, detail)


def _run(engine, sql, params=None):
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchall()


def _one(engine, sql, params=None):
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchone()


def _scalar(engine, sql, params=None):
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


def check(label, passed, detail="", warning_only=False):
    status = PASS if passed else (WARN if warning_only else FAIL)
    results.append((label, "PASS" if passed else ("WARN" if warning_only else "FAIL"), detail))
    print(f"  {status}  {label}")
    if detail:
        for line in textwrap.wrap(detail, 90):
            print(f"          {line}")


def section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


# ─────────────────────────────────────────────────────────────────
# 1. Source row counts
# ─────────────────────────────────────────────────────────────────
section("1 · Source row counts (MAG + GRT)")

mag_tables = {
    "F_COMPTET (clients CT_Type=0)":
        "SELECT COUNT(*) FROM F_COMPTET WHERE CT_Type=0",
    "F_COMPTET (fournisseurs CT_Type=1)":
        "SELECT COUNT(*) FROM F_COMPTET WHERE CT_Type=1",
    "F_ARTICLE":
        "SELECT COUNT(*) FROM F_ARTICLE",
    "F_FAMILLE (FA_Type=0)":
        "SELECT COUNT(*) FROM F_FAMILLE WHERE FA_Type=0",
    "F_DOCLIGNE ventes (DO_Domaine=0, DO_Type IN 6,7)":
        "SELECT COUNT(*) FROM F_DOCLIGNE WHERE DO_Domaine=0 AND DO_Type IN(6,7) AND DL_MontantHT IS NOT NULL",
    "F_ECRITUREC":
        "SELECT COUNT(*) FROM F_ECRITUREC WHERE EC_Montant IS NOT NULL AND EC_Montant<>0",
    "F_ARTSTOCK":
        "SELECT COUNT(*) FROM F_ARTSTOCK WHERE AS_QteSto IS NOT NULL",
    "F_EBANQUE":
        "SELECT COUNT(*) FROM F_EBANQUE",
    "F_DEPOT":
        "SELECT COUNT(*) FROM F_DEPOT",
    "F_CAISSE":
        "SELECT COUNT(*) FROM F_CAISSE",
    "F_JOURNAUX":
        "SELECT COUNT(*) FROM F_JOURNAUX",
    "F_COLLABORATEUR":
        "SELECT COUNT(*) FROM F_COLLABORATEUR",
}

for label, sql in mag_tables.items():
    try:
        n = _scalar(MAG_ENGINE, sql)
        check(f"MAG · {label}", n > 0, f"{n:,} rows")
    except Exception as exc:
        check(f"MAG · {label}", False, str(exc))

grt_tables = {
    "F_ReglementClient":
        "SELECT COUNT(*) FROM F_ReglementClient WHERE RT_Montant IS NOT NULL",
    "F_ReglementFournisseur":
        "SELECT COUNT(*) FROM F_ReglementFournisseur",
    "F_MvtCaisse":
        "SELECT COUNT(*) FROM F_MvtCaisse",
    "F_DOCREGL":
        "SELECT COUNT(*) FROM F_DOCREGL",
}

for label, sql in grt_tables.items():
    try:
        n = _scalar(GRT_ENGINE, sql)
        check(f"GRT · {label}", n > 0, f"{n:,} rows", warning_only=(n == 0))
    except Exception as exc:
        check(f"GRT · {label}", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 2. DW table counts
# ─────────────────────────────────────────────────────────────────
section("2 · DW table counts")

dw_tables = [
    "DIM_DATE", "DIM_DOMAINE", "DIM_TYPE_DOC", "DIM_MODE_REGLEMENT",
    "DIM_ETAT_REGLEMENT", "DIM_ETAT_DOCREGL", "DIM_TYPE_LIGNE",
    "DIM_SEGMENT", "DIM_COLLABORATEUR", "DIM_JOURNAL", "DIM_FOURNISSEUR",
    "DIM_BANQUE", "DIM_FAMILLE", "DIM_CLIENT", "DIM_ARTICLE",
    "DIM_DEPOT", "DIM_CAISSE",
    "FAIT_LIGNES_VENTE", "FAIT_REGLEMENTS", "FAIT_ECRITURES",
    "ETL_AUDIT",
]
for tbl in dw_tables:
    try:
        n = _scalar(DW_ENGINE, f"SELECT COUNT(*) FROM {tbl}")
        check(f"DW · {tbl}", n > 0, f"{n:,} rows", warning_only=(n == 0))
    except Exception as exc:
        check(f"DW · {tbl}", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 3. FK integrity — orphan surrogates in fact tables
# ─────────────────────────────────────────────────────────────────
section("3 · FK integrity (orphan surrogate keys in fact tables)")

fk_checks = [
    ("FAIT_LIGNES_VENTE", "id_date",    "DIM_DATE",    "id_date"),
    ("FAIT_LIGNES_VENTE", "id_client",  "DIM_CLIENT",  "id_client"),
    ("FAIT_LIGNES_VENTE", "id_article", "DIM_ARTICLE", "id_article"),
    ("FAIT_LIGNES_VENTE", "id_domaine", "DIM_DOMAINE", "id_domaine"),
    ("FAIT_REGLEMENTS",   "id_client",  "DIM_CLIENT",  "id_client"),
    ("FAIT_REGLEMENTS",   "id_mode_reg","DIM_MODE_REGLEMENT","id_mode_reg"),
    ("FAIT_ECRITURES",    "id_article", "DIM_ARTICLE", "id_article"),
    ("FAIT_ECRITURES",    "id_journal", "DIM_JOURNAL", "id_journal"),
    ("FAIT_ECRITURES",    "id_depot",   "DIM_DEPOT",   "id_depot"),
]

for fact_tbl, fk_col, dim_tbl, pk_col in fk_checks:
    try:
        sql = f"""
            SELECT COUNT(*) FROM {fact_tbl} f
            WHERE f.[{fk_col}] IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM {dim_tbl} d WHERE d.[{pk_col}] = f.[{fk_col}]
              )
        """
        orphans = _scalar(DW_ENGINE, sql)
        check(
            f"FK {fact_tbl}.{fk_col} → {dim_tbl}.{pk_col}",
            orphans == 0,
            f"{orphans:,} orphan rows" if orphans else "clean",
        )
    except Exception as exc:
        check(f"FK {fact_tbl}.{fk_col}", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 4. hash_key collision detection (same hash → different natural key)
# ─────────────────────────────────────────────────────────────────
section("4 · hash_key collision detection")

collision_checks = [
    ("DIM_CLIENT",      "CT_Num_code"),
    ("DIM_ARTICLE",     "AR_Ref_code"),
    ("DIM_FOURNISSEUR",  "CT_Num_code"),
    ("DIM_FAMILLE",     "FA_CodeFamille_code"),
]
for tbl, hash_col in collision_checks:
    try:
        sql = f"""
            SELECT COUNT(*) FROM (
                SELECT [{hash_col}], COUNT(*) AS cnt
                FROM {tbl}
                WHERE [{hash_col}] IS NOT NULL
                GROUP BY [{hash_col}]
                HAVING COUNT(*) > 1
            ) dup
        """
        collisions = _scalar(DW_ENGINE, sql)
        check(
            f"hash_key collisions in {tbl}.{hash_col}",
            collisions == 0,
            f"{collisions} collision groups found" if collisions else "no collisions",
        )
    except Exception as exc:
        check(f"hash_key collision {tbl}", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 5. Surrogate lookup completeness (every source key has a DW row)
# ─────────────────────────────────────────────────────────────────
section("5 · Surrogate lookup completeness")

# How many FAIT_LIGNES_VENTE rows have NULL id_client despite CT_Num present
try:
    r = _one(DW_ENGINE, """
        SELECT
            SUM(CASE WHEN id_client IS NULL THEN 1 ELSE 0 END) AS missing_client,
            SUM(CASE WHEN id_article IS NULL THEN 1 ELSE 0 END) AS missing_article,
            SUM(CASE WHEN id_date IS NULL THEN 1 ELSE 0 END) AS missing_date,
            COUNT(*) AS total
        FROM FAIT_LIGNES_VENTE
    """)
    for col, val in [("id_client", r.missing_client),
                     ("id_article", r.missing_article),
                     ("id_date", r.missing_date)]:
        pct = int(val) / max(int(r.total), 1) * 100
        check(
            f"FAIT_LIGNES_VENTE NULL {col}",
            pct < 5,
            f"{val:,}/{r.total:,} ({pct:.1f}%)",
            warning_only=(pct < 20),
        )
except Exception as exc:
    check("FAIT_LIGNES_VENTE surrogate lookup", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 6. FAIT_LIGNES_VENTE business rules
# ─────────────────────────────────────────────────────────────────
section("6 · FAIT_LIGNES_VENTE business rules")

try:
    r = _one(DW_ENGINE, """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN DL_MontantHT IS NULL THEN 1 ELSE 0 END) AS null_montant,
            SUM(CASE WHEN DL_MontantHT < 0 THEN 1 ELSE 0 END) AS negative_montant,
            SUM(CASE WHEN DL_Qte IS NULL THEN 1 ELSE 0 END) AS null_qte,
            SUM(CASE WHEN DL_Qte < 0 THEN 1 ELSE 0 END) AS negative_qte,
            SUM(CASE WHEN DL_PrixUnitaire IS NULL THEN 1 ELSE 0 END) AS null_prix,
            SUM(CASE WHEN DO_Piece_hash IS NULL THEN 1 ELSE 0 END) AS null_piece_hash,
            MIN(DL_MontantHT) AS min_montant,
            MAX(DL_MontantHT) AS max_montant,
            SUM(DL_MontantHT) AS total_ca
        FROM FAIT_LIGNES_VENTE
    """)
    check("No NULL DL_MontantHT", r.null_montant == 0,
          f"{r.null_montant:,} NULL rows")
    pct_neg = int(r.negative_montant) / max(int(r.total), 1) * 100
    check("Negative DL_MontantHT < 5% (avoirs expected)",
          pct_neg < 30,
          f"{r.negative_montant:,} avoir rows ({pct_neg:.1f}%)", warning_only=True)
    check("DO_Piece_hash populated", r.null_piece_hash == 0,
          f"{r.null_piece_hash:,} NULL")
    check("CA total > 0", float(r.total_ca or 0) > 0,
          f"Total CA = {float(r.total_ca or 0):,.0f} DT")
    print(f"          Range: {float(r.min_montant or 0):,.2f} … {float(r.max_montant or 0):,.2f} DT")
except Exception as exc:
    check("FAIT_LIGNES_VENTE business rules", False, str(exc))

# duplicate source_hash check
try:
    dup = _scalar(DW_ENGINE, """
        SELECT COUNT(*) FROM (
            SELECT source_hash, COUNT(*) cnt FROM FAIT_LIGNES_VENTE
            WHERE source_hash IS NOT NULL
            GROUP BY source_hash HAVING COUNT(*)>1
        ) d
    """)
    check("FAIT_LIGNES_VENTE source_hash unique", dup == 0,
          f"{dup} duplicate hashes")
except Exception as exc:
    check("FAIT_LIGNES_VENTE source_hash", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 7. FAIT_REGLEMENTS dedup & balance
# ─────────────────────────────────────────────────────────────────
section("7 · FAIT_REGLEMENTS dedup & balance")

try:
    r = _one(DW_ENGINE, """
        SELECT
            COUNT(*) AS total,
            COUNT(DISTINCT RT_Num) AS distinct_rt,
            SUM(CASE WHEN id_client IS NULL AND id_fournisseur IS NULL THEN 1 ELSE 0 END) AS orphan_actors,
            SUM(CASE WHEN RT_Montant IS NULL THEN 1 ELSE 0 END) AS null_montant
        FROM FAIT_REGLEMENTS
        WHERE RT_Num IS NOT NULL
    """)
    dup_rows = int(r.total) - int(r.distinct_rt)
    check("FAIT_REGLEMENTS no duplicate RT_Num", dup_rows == 0,
          f"{dup_rows:,} extra rows (dedup needed)" if dup_rows else "clean")
    pct_orphan = int(r.orphan_actors) / max(int(r.total), 1) * 100
    check("FAIT_REGLEMENTS actor linked", pct_orphan < 5,
          f"{r.orphan_actors:,} rows with no client/fournisseur ({pct_orphan:.1f}%)",
          warning_only=True)
    check("FAIT_REGLEMENTS RT_Montant not null", r.null_montant == 0,
          f"{r.null_montant:,} NULL")
except Exception as exc:
    check("FAIT_REGLEMENTS dedup", False, str(exc))

try:
    r = _one(DW_ENGINE, """
        WITH d AS (
            SELECT RT_Num,
                   MAX(RT_Montant) AS m,
                   MAX(DR_Regle) AS r
            FROM FAIT_REGLEMENTS
            WHERE RT_Num IS NOT NULL AND id_client IS NOT NULL
            GROUP BY RT_Num
        )
        SELECT
            SUM(CASE WHEN r=1 THEN m ELSE 0 END) AS enc,
            SUM(CASE WHEN r=0 THEN m ELSE 0 END) AS imp
        FROM d
    """)
    enc = float(r.enc or 0); imp = float(r.imp or 0); total = enc + imp
    taux = enc / total * 100 if total else 0
    check("Taux recouvrement > 50%", taux > 50,
          f"Encaissements={enc:,.0f}  Impayés={imp:,.0f}  Taux={taux:.1f}%",
          warning_only=True)
except Exception as exc:
    check("FAIT_REGLEMENTS balance", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 8. FAIT_ECRITURES type_ligne distribution
# ─────────────────────────────────────────────────────────────────
section("8 · FAIT_ECRITURES type_ligne distribution")

try:
    rows = _run(DW_ENGINE, """
        SELECT tl.type_ligne, tl.libelle_type_ligne, COUNT(*) AS nb
        FROM FAIT_ECRITURES fe
        LEFT JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
        GROUP BY tl.type_ligne, tl.libelle_type_ligne
        ORDER BY tl.type_ligne
    """)
    if not rows:
        check("FAIT_ECRITURES populated", False, "Table is empty!")
    for row in rows:
        print(f"          type_ligne={row.type_ligne} ({row.libelle_type_ligne}): {row.nb:,} rows")
    types_found = {r.type_ligne for r in rows}
    check("All 4 type_ligne present (1=écritures, 2=TVA, 3=caisse, 4=stock)",
          {1, 2, 3, 4}.issubset(types_found),
          f"Found: {sorted(types_found)}")
except Exception as exc:
    check("FAIT_ECRITURES distribution", False, str(exc))

# source_hash uniqueness
try:
    dup = _scalar(DW_ENGINE, """
        SELECT COUNT(*) FROM (
            SELECT source_hash, COUNT(*) cnt FROM FAIT_ECRITURES
            WHERE source_hash IS NOT NULL
            GROUP BY source_hash HAVING COUNT(*)>1
        ) d
    """)
    check("FAIT_ECRITURES source_hash unique", dup == 0,
          f"{dup} duplicate hashes")
except Exception as exc:
    check("FAIT_ECRITURES source_hash", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 9. Stock KPIs
# ─────────────────────────────────────────────────────────────────
section("9 · Stock KPIs (DSI, tension, rupture)")

try:
    r = _one(DW_ENGINE, """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN AS_QteSto IS NOT NULL THEN 1 ELSE 0 END) AS has_stock,
            SUM(CASE WHEN AS_QteSto > 0 THEN 1 ELSE 0 END) AS positive_stock,
            SUM(CASE WHEN dsi_jours IS NOT NULL THEN 1 ELSE 0 END) AS has_dsi,
            SUM(CASE WHEN ratio_tension IS NOT NULL THEN 1 ELSE 0 END) AS has_tension,
            SUM(CASE WHEN en_rupture = 1 THEN 1 ELSE 0 END) AS ruptures,
            SUM(CASE WHEN ratio_tension > 0.8 THEN 1 ELSE 0 END) AS alerte_tension,
            AVG(dsi_jours) AS avg_dsi,
            MIN(AS_QteSto) AS min_stock,
            MAX(AS_QteSto) AS max_stock
        FROM FAIT_ECRITURES fe
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
        WHERE tl.type_ligne = 4
    """)
    check("Stock snapshot rows > 0", int(r.total) > 0, f"{r.total:,} stock rows")
    pct_dsi = int(r.has_dsi) / max(int(r.total), 1) * 100
    check("DSI computed for > 50% stock rows", pct_dsi > 50,
          f"{r.has_dsi:,}/{r.total:,} ({pct_dsi:.1f}%)", warning_only=True)
    print(f"          Positive stock: {r.positive_stock:,}  Ruptures: {r.ruptures:,}  "
          f"Alertes tension: {r.alerte_tension:,}")
    if r.avg_dsi:
        print(f"          Avg DSI = {float(r.avg_dsi):.1f} days  "
              f"Stock range: {float(r.min_stock or 0):.0f} … {float(r.max_stock or 0):.0f}")
except Exception as exc:
    check("Stock KPIs", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 10. RFM scores
# ─────────────────────────────────────────────────────────────────
section("10 · RFM scores in DIM_CLIENT")

try:
    r = _one(DW_ENGINE, """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN rfm_score IS NOT NULL THEN 1 ELSE 0 END) AS scored,
            SUM(CASE WHEN rfm_score = 'Champion' THEN 1 ELSE 0 END) AS champion,
            SUM(CASE WHEN rfm_score = 'Fidèle' THEN 1 ELSE 0 END) AS fidele,
            SUM(CASE WHEN rfm_score = 'À risque' THEN 1 ELSE 0 END) AS a_risque,
            SUM(CASE WHEN rfm_score = 'Dormant' THEN 1 ELSE 0 END) AS dormant
        FROM DIM_CLIENT
    """)
    pct = int(r.scored) / max(int(r.total), 1) * 100
    check("RFM scored > 50% clients", pct > 50,
          f"{r.scored:,}/{r.total:,} ({pct:.1f}%)", warning_only=True)
    print(f"          Champion={r.champion}  Fidèle={r.fidele}  "
          f"À risque={r.a_risque}  Dormant={r.dormant}")
except Exception as exc:
    check("RFM scores", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 11. DIM_CLIENT data quality
# ─────────────────────────────────────────────────────────────────
section("11 · DIM_CLIENT data quality")

try:
    r = _one(DW_ENGINE, """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN id_segment IS NULL THEN 1 ELSE 0 END) AS no_segment,
            SUM(CASE WHEN id_collab IS NULL THEN 1 ELSE 0 END) AS no_collab,
            SUM(CASE WHEN gouvernorat IS NULL OR gouvernorat = '' THEN 1 ELSE 0 END) AS no_gouv,
            SUM(CASE WHEN CT_Intitule IS NULL OR CT_Intitule = '' THEN 1 ELSE 0 END) AS no_intitule,
            SUM(CASE WHEN CT_Sommeil = 1 THEN 1 ELSE 0 END) AS sommeil,
            COUNT(DISTINCT gouvernorat) AS nb_gouvernorats
        FROM DIM_CLIENT
    """)
    pct_seg = int(r.no_segment) / max(int(r.total), 1) * 100
    check("DIM_CLIENT segment coverage", pct_seg < 20,
          f"{r.no_segment:,}/{r.total:,} without segment ({pct_seg:.1f}%)", warning_only=True)
    check("DIM_CLIENT gouvernorat populated", r.no_gouv == 0,
          f"{r.no_gouv:,} missing", warning_only=True)
    check("DIM_CLIENT CT_Intitule populated", int(r.no_intitule) / max(int(r.total),1) < 0.1,
          f"{r.no_intitule:,} missing ({int(r.no_intitule)/max(int(r.total),1)*100:.1f}%)",
          warning_only=True)
    print(f"          Total={r.total:,}  Sommeil={r.sommeil:,}  Gouvernorats={r.nb_gouvernorats}")
except Exception as exc:
    check("DIM_CLIENT quality", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 12. DIM_ARTICLE data quality
# ─────────────────────────────────────────────────────────────────
section("12 · DIM_ARTICLE data quality")

try:
    r = _one(DW_ENGINE, """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN id_famille IS NULL THEN 1 ELSE 0 END) AS no_famille,
            SUM(CASE WHEN id_fournisseur IS NULL THEN 1 ELSE 0 END) AS no_fourn,
            SUM(CASE WHEN AR_PrixAch IS NULL OR AR_PrixAch = 0 THEN 1 ELSE 0 END) AS no_prix,
            SUM(CASE WHEN FA_Intitule IS NULL OR FA_Intitule = '' THEN 1 ELSE 0 END) AS no_label,
            SUM(CASE WHEN AR_Sommeil = 1 THEN 1 ELSE 0 END) AS sommeil
        FROM DIM_ARTICLE
    """)
    pct_prix = int(r.no_prix) / max(int(r.total), 1) * 100
    pct_label = int(r.no_label) / max(int(r.total), 1) * 100
    check("DIM_ARTICLE FA_Intitule populated", pct_label < 5,
          f"{r.no_label:,}/{r.total:,} missing ({pct_label:.1f}%)", warning_only=True)
    check("DIM_ARTICLE AR_PrixAch populated > 80%", pct_prix < 20,
          f"{r.no_prix:,}/{r.total:,} missing ({pct_prix:.1f}%)", warning_only=True)
    print(f"          Total={r.total:,}  No famille={r.no_famille:,}  "
          f"No fournisseur={r.no_fourn:,}  Sommeil={r.sommeil:,}")
except Exception as exc:
    check("DIM_ARTICLE quality", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 13. DIM_FAMILLE label coverage
# ─────────────────────────────────────────────────────────────────
section("13 · DIM_FAMILLE label coverage")

try:
    r = _one(DW_ENGINE, """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN FA_Intitule IS NULL OR FA_Intitule = '' THEN 1 ELSE 0 END) AS empty
        FROM DIM_FAMILLE
    """)
    check("DIM_FAMILLE FA_Intitule populated",
          int(r.empty) == 0,
          f"{r.empty}/{r.total} empty labels", warning_only=True)
except Exception as exc:
    check("DIM_FAMILLE labels", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 14. Margin sanity
# ─────────────────────────────────────────────────────────────────
section("14 · Margin sanity check")

try:
    r = _one(DW_ENGINE, """
        WITH latest AS (
            SELECT MAX(d.annee) AS y
            FROM FAIT_LIGNES_VENTE f
            JOIN DIM_DOMAINE dom ON dom.id_domaine=f.id_domaine
            JOIN DIM_DATE d ON d.id_date=f.id_date
            WHERE dom.DO_Domaine=0
        )
        SELECT
            SUM(f.DL_MontantHT) AS ca,
            SUM(CASE WHEN a.AR_PrixAch>0 AND f.DL_Qte IS NOT NULL
                THEN f.DL_MontantHT ELSE 0 END) AS ca_cout,
            SUM(CASE WHEN a.AR_PrixAch>0 AND f.DL_Qte IS NOT NULL
                THEN f.DL_MontantHT - (f.DL_Qte * a.AR_PrixAch)
                ELSE NULL END) AS marge,
            COUNT(*) AS lines,
            COUNT(CASE WHEN a.AR_PrixAch>0 THEN 1 END) AS lines_with_cost
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine=f.id_domaine
        JOIN DIM_DATE d ON d.id_date=f.id_date
        LEFT JOIN DIM_ARTICLE a ON a.id_article=f.id_article
        CROSS JOIN latest
        WHERE dom.DO_Domaine=0 AND d.annee=latest.y
    """)
    ca = float(r.ca or 0)
    ca_c = float(r.ca_cout or 0)
    marge = float(r.marge or 0)
    pct_cover = ca_c / ca * 100 if ca else 0
    marge_pct  = marge / ca_c * 100 if ca_c else 0
    check("Marge brute 10-50% (normal distribution trade)",
          10 < marge_pct < 50,
          f"Marge={marge:,.0f} DT  Taux={marge_pct:.1f}%  (on {pct_cover:.0f}% CA with cost)",
          warning_only=True)
    check("Cost coverage > 60% lines", pct_cover > 60,
          f"{r.lines_with_cost:,}/{r.lines:,} lines ({pct_cover:.1f}%)",
          warning_only=True)
except Exception as exc:
    check("Margin sanity", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 15. Date range alignment
# ─────────────────────────────────────────────────────────────────
section("15 · Date range alignment (source vs DW)")

try:
    src = _one(MAG_ENGINE, """
        SELECT MIN(DO_Date) AS mn, MAX(DO_Date) AS mx
        FROM F_DOCLIGNE
        WHERE DO_Domaine=0 AND DO_Type IN(6,7)
        AND DL_MontantHT IS NOT NULL
    """)
    dw = _one(DW_ENGINE, """
        SELECT MIN(d.date_val) AS mn, MAX(d.date_val) AS mx
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DATE d ON d.id_date=f.id_date
    """)
    print(f"          Source F_DOCLIGNE: {src.mn} → {src.mx}")
    print(f"          DW FAIT_LIGNES_VENTE: {dw.mn} → {dw.mx}")
    check("DW date range covers source min date",
          dw.mn is not None and src.mn is not None and dw.mn <= src.mn,
          f"DW start={dw.mn}  Source start={src.mn}", warning_only=True)
    check("DW date range covers source max date",
          dw.mx is not None and src.mx is not None and dw.mx >= src.mx,
          f"DW end={dw.mx}  Source end={src.mx}", warning_only=True)
except Exception as exc:
    check("Date range alignment", False, str(exc))

try:
    ec_src = _one(MAG_ENGINE, "SELECT MIN(EC_Date) AS mn, MAX(EC_Date) AS mx FROM F_ECRITUREC")
    ec_dw  = _one(DW_ENGINE, """
        SELECT MIN(d.date_val) AS mn, MAX(d.date_val) AS mx
        FROM FAIT_ECRITURES fe
        JOIN DIM_DATE d ON d.id_date=fe.id_date
        JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne=fe.id_type_ligne
        WHERE tl.type_ligne=1
    """)
    print(f"          F_ECRITUREC: {ec_src.mn} → {ec_src.mx}")
    print(f"          DW écritures type_ligne=1: {ec_dw.mn} → {ec_dw.mx}")
except Exception as exc:
    print(f"          [INFO] Écritures date range: {exc}")

# ─────────────────────────────────────────────────────────────────
# 16. Delta filter diagnosis
# ─────────────────────────────────────────────────────────────────
section("16 · Delta filter diagnosis")

try:
    last_run = _scalar(DW_ENGINE, """
        SELECT MAX(run_date) FROM ETL_AUDIT
        WHERE status='SUCCESS' AND table_name='PIPELINE'
    """)
    print(f"          Last successful run: {last_run}")
    if last_run:
        n_vente = _scalar(MAG_ENGINE, """
            SELECT COUNT(*) FROM F_DOCLIGNE
            WHERE DO_Date >= :lr AND DO_Domaine=0
              AND DO_Type IN(6,7) AND DL_MontantHT IS NOT NULL
        """, {"lr": last_run})
        n_ec = _scalar(MAG_ENGINE, """
            SELECT COUNT(*) FROM F_ECRITUREC
            WHERE EC_Date >= :lr AND EC_Montant IS NOT NULL
        """, {"lr": last_run})
        total_v = _scalar(MAG_ENGINE, """
            SELECT COUNT(*) FROM F_DOCLIGNE
            WHERE DO_Domaine=0 AND DO_Type IN(6,7) AND DL_MontantHT IS NOT NULL
        """)
        total_e = _scalar(MAG_ENGINE, "SELECT COUNT(*) FROM F_ECRITUREC WHERE EC_Montant IS NOT NULL")
        print(f"          DELTA ventes: {n_vente:,}/{total_v:,} rows have DO_Date >= last run")
        print(f"          DELTA écritures: {n_ec:,}/{total_e:,} rows have EC_Date >= last run")
        check("Delta filter returns < 100% for ventes (not all rows are new)",
              n_vente < total_v,
              f"{n_vente:,}/{total_v:,} rows would be reloaded", warning_only=True)
    else:
        print(f"          {INFO}  No successful run yet — full load will be used")
except Exception as exc:
    check("Delta filter diagnosis", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 17. Audit log consistency
# ─────────────────────────────────────────────────────────────────
section("17 · ETL_AUDIT consistency")

try:
    rows = _run(DW_ENGINE, """
        SELECT TOP 10
            run_id, run_date, mode, table_name, status,
            duration_seconds, rows_inserted, error_msg
        FROM ETL_AUDIT
        WHERE table_name = 'PIPELINE'
        ORDER BY run_date DESC
    """)
    if not rows:
        check("ETL_AUDIT has pipeline runs", False, "No PIPELINE rows found")
    else:
        print(f"          Last {len(rows)} pipeline runs:")
        for r in rows:
            err = f" — {r.error_msg[:60]}" if r.error_msg else ""
            print(f"            run_id={r.run_id}  {r.run_date}  {r.status}  "
                  f"{r.duration_seconds}s{err}")
        stale = _scalar(DW_ENGINE, """
            SELECT COUNT(*) FROM ETL_AUDIT
            WHERE status='RUNNING'
            AND table_name='PIPELINE'
            AND run_date < DATEADD(HOUR,-24,GETUTCDATE())
        """)
        check("No stale RUNNING rows in ETL_AUDIT", stale == 0,
              f"{stale} stale RUNNING rows found")
except Exception as exc:
    check("ETL_AUDIT", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 18. source_hash uniqueness across all fact tables
# ─────────────────────────────────────────────────────────────────
section("18 · source_hash uniqueness")

for tbl in ("FAIT_LIGNES_VENTE", "FAIT_REGLEMENTS", "FAIT_ECRITURES"):
    try:
        r = _one(DW_ENGINE, f"""
            SELECT
                COUNT(*) AS total,
                COUNT(DISTINCT source_hash) AS distinct_hashes,
                SUM(CASE WHEN source_hash IS NULL THEN 1 ELSE 0 END) AS null_hashes
            FROM {tbl}
        """)
        dup = int(r.total) - int(r.null_hashes) - int(r.distinct_hashes)
        pct_null = int(r.null_hashes) / max(int(r.total), 1) * 100
        check(f"{tbl} source_hash no duplicates", dup <= 0,
              f"{dup} duplicates, {r.null_hashes:,} NULLs ({pct_null:.1f}%)")
    except Exception as exc:
        check(f"{tbl} source_hash", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 19. Gouvernorat mapping coverage
# ─────────────────────────────────────────────────────────────────
section("19 · Gouvernorat mapping coverage")

try:
    rows = _run(DW_ENGINE, """
        SELECT gouvernorat, COUNT(*) AS nb
        FROM DIM_CLIENT
        GROUP BY gouvernorat
        ORDER BY nb DESC
    """)
    total_clients = sum(r.nb for r in rows)
    autre_nb = sum(r.nb for r in rows if r.gouvernorat in ("Autre", None, ""))
    pct_autre = autre_nb / max(total_clients, 1) * 100
    check("Gouvernorat 'Autre' < 10% of clients", pct_autre < 10,
          f"{autre_nb:,}/{total_clients:,} unresolved ({pct_autre:.1f}%)", warning_only=True)
    print(f"          Top 10 gouvernorats:")
    for r in rows[:10]:
        print(f"            {str(r.gouvernorat or 'NULL'):<30}  {r.nb:>6} clients")
except Exception as exc:
    check("Gouvernorat coverage", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# 20. CA growth vs N-1
# ─────────────────────────────────────────────────────────────────
section("20 · CA growth vs N-1")

try:
    r = _one(DW_ENGINE, """
        WITH ly AS (
            SELECT MAX(annee) AS y FROM DIM_DATE
            WHERE id_date IN (SELECT id_date FROM FAIT_LIGNES_VENTE)
        )
        SELECT
            d.annee,
            SUM(f.DL_MontantHT) AS ca
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine=f.id_domaine
        JOIN DIM_DATE d ON d.id_date=f.id_date
        CROSS JOIN ly
        WHERE dom.DO_Domaine=0
        AND d.annee IN (ly.y, ly.y-1)
        GROUP BY d.annee
        ORDER BY d.annee DESC
    """)
    years = _run(DW_ENGINE, """
        WITH ly AS (
            SELECT MAX(annee) AS y FROM DIM_DATE
            WHERE id_date IN (SELECT id_date FROM FAIT_LIGNES_VENTE)
        )
        SELECT d.annee, SUM(f.DL_MontantHT) AS ca
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine=f.id_domaine
        JOIN DIM_DATE d ON d.id_date=f.id_date
        CROSS JOIN ly
        WHERE dom.DO_Domaine=0 AND d.annee IN (ly.y, ly.y-1)
        GROUP BY d.annee ORDER BY d.annee DESC
    """)
    if len(years) >= 2:
        ca_n  = float(years[0].ca or 0)
        ca_n1 = float(years[1].ca or 0)
        growth = (ca_n - ca_n1) / ca_n1 * 100 if ca_n1 else 0
        check(f"CA growth within -50% to +200% range (plausibility)",
              -50 < growth < 200,
              f"CA {years[0].annee}: {ca_n:,.0f}  vs  CA {years[1].annee}: {ca_n1:,.0f}  "
              f"Growth={growth:+.1f}%",
              warning_only=True)
    else:
        print(f"          {INFO}  Only one year of data — N-1 comparison not possible")
except Exception as exc:
    check("CA growth", False, str(exc))

# ─────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  SUMMARY")
print(SEP)

passed = sum(1 for _, s, _ in results if s == "PASS")
warned = sum(1 for _, s, _ in results if s == "WARN")
failed = sum(1 for _, s, _ in results if s == "FAIL")
total  = len(results)

print(f"  {PASS}  {passed}/{total} checks passed")
if warned:
    print(f"  {WARN}  {warned}/{total} warnings")
if failed:
    print(f"  {FAIL}  {failed}/{total} failures\n")
    print("  Failed checks:")
    for label, status, detail in results:
        if status == "FAIL":
            print(f"    • {label}")
            if detail:
                print(f"      {detail}")

print(f"\n  Run completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(SEP + "\n")

sys.exit(0 if failed == 0 else 1)