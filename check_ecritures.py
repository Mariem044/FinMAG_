"""
FinMAG Dashboard — Verification & Correction Script
====================================================
Run: python verify_and_fix.py
Checks every value shown in the dashboard screenshots and tells you
exactly what is wrong and how to fix it.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy import text
from etl.config import DW_ENGINE, MAG_ENGINE, GRT_ENGINE

def dw(sql, params=None):
    with DW_ENGINE.connect() as c:
        return c.execute(text(sql), params or {}).fetchone()

def dw_all(sql, params=None):
    with DW_ENGINE.connect() as c:
        return c.execute(text(sql), params or {}).fetchall()

def mag(sql, params=None):
    with DW_ENGINE.connect() as c:
        return c.execute(text(sql), params or {}).fetchone()

def src(engine, sql, params=None):
    with engine.connect() as c:
        return c.execute(text(sql), params or {}).fetchall()

def src1(engine, sql, params=None):
    with engine.connect() as c:
        return c.execute(text(sql), params or {}).fetchone()

OK   = "[OK]  "
BAD  = "[BAD] "
WARN = "[WARN]"
SEP  = "=" * 65

issues = []

def check(label, ok, found, expected="", fix=""):
    status = OK if ok else BAD
    print(f"  {status} {label}")
    if found:
        print(f"         Found:    {found}")
    if expected and not ok:
        print(f"         Expected: {expected}")
    if not ok:
        issues.append((label, fix))
        if fix:
            print(f"         FIX:      {fix}")

# ================================================================
print(f"\n{SEP}")
print("  1. MARGE BRUTE — dashboard shows 1.8% (0.0 MDT CA couverts)")
print(SEP)

r = dw("""
    SELECT
        COUNT(*) AS total_articles,
        SUM(CASE WHEN AR_PrixAch IS NOT NULL AND AR_PrixAch > 0 THEN 1 ELSE 0 END) AS with_prix,
        AVG(CASE WHEN AR_PrixAch > 0 THEN AR_PrixAch END) AS avg_prix
    FROM DIM_ARTICLE
""")
print(f"  DIM_ARTICLE: {r.with_prix}/{r.total_articles} have AR_PrixAch > 0  (avg={float(r.avg_prix or 0):.2f})")

r2 = dw("""
    SELECT COUNT(*) AS matched
    FROM FAIT_LIGNES_VENTE f
    JOIN DIM_ARTICLE a ON a.id_article = f.id_article
    WHERE a.AR_PrixAch IS NOT NULL AND a.AR_PrixAch > 0
""")
print(f"  FAIT_LIGNES_VENTE rows with valid AR_PrixAch: {r2.matched}")

r3 = dw("""
    SELECT
        SUM(f.DL_MontantHT) AS ca,
        SUM(CASE WHEN a.AR_PrixAch > 0 AND f.DL_Qte IS NOT NULL
            THEN f.DL_MontantHT - (f.DL_Qte * a.AR_PrixAch)
            ELSE NULL END) AS marge,
        SUM(CASE WHEN a.AR_PrixAch > 0 THEN f.DL_MontantHT ELSE 0 END) AS ca_avec_cout
    FROM FAIT_LIGNES_VENTE f
    JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
    LEFT JOIN DIM_ARTICLE a ON a.id_article = f.id_article
    WHERE dom.DO_Domaine = 0
""")
ca   = float(r3.ca or 0)
marge = float(r3.marge or 0)
ca_c  = float(r3.ca_avec_cout or 0)
pct   = marge / ca_c * 100 if ca_c else 0
cover = ca_c / ca * 100 if ca else 0

check("Marge brute computable",
      ca_c > 0 and pct > 0,
      f"Marge={marge:,.0f} DT  Taux={pct:.1f}%  Coverage={cover:.1f}%",
      "Marge > 0 DT, coverage > 60%",
      "AR_PrixAch exists but DL_Qte may be NULL or join fails — see below")

# Check if DL_Qte is the problem
r4 = dw("""
    SELECT
        SUM(CASE WHEN DL_Qte IS NULL THEN 1 ELSE 0 END) AS null_qte,
        SUM(CASE WHEN DL_Qte <= 0 THEN 1 ELSE 0 END) AS zero_qte,
        COUNT(*) AS total
    FROM FAIT_LIGNES_VENTE
""")
check("DL_Qte populated",
      int(r4.null_qte) / max(int(r4.total), 1) < 0.05,
      f"NULL={r4.null_qte}  Zero/neg={r4.zero_qte}  Total={r4.total}",
      "< 5% NULL",
      "DL_Qte is not being extracted from F_DOCLIGNE — check extract.py")

# Check if the issue is DL_MontantHT < DL_Qte * AR_PrixAch (avoirs)
r5 = dw("""
    SELECT
        COUNT(*) AS negative_marge_lines,
        SUM(CASE WHEN f.DL_MontantHT < (f.DL_Qte * a.AR_PrixAch) THEN 1 ELSE 0 END) AS loss_lines
    FROM FAIT_LIGNES_VENTE f
    JOIN DIM_ARTICLE a ON a.id_article = f.id_article
    WHERE a.AR_PrixAch > 0 AND f.DL_Qte IS NOT NULL
""")
print(f"  Lines where sale price < cost (avoirs or data issue): {r5.loss_lines}")

# ================================================================
print(f"\n{SEP}")
print("  2. CA N-1 COMPARISON — dashboard shows 442.7% growth (impossible)")
print(SEP)

rows = dw_all("""
    SELECT d.annee, SUM(f.DL_MontantHT) AS ca, COUNT(*) AS nb_lignes
    FROM FAIT_LIGNES_VENTE f
    JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
    JOIN DIM_DATE d ON d.id_date = f.id_date
    WHERE dom.DO_Domaine = 0
    GROUP BY d.annee
    ORDER BY d.annee DESC
""")
print("  CA by year:")
for r in rows:
    print(f"    {r.annee}: {float(r.ca or 0):>15,.0f} DT  ({r.nb_lignes:,} lignes)")

if len(rows) >= 2:
    ca_n  = float(rows[0].ca or 0)
    ca_n1 = float(rows[1].ca or 0)
    growth = (ca_n - ca_n1) / ca_n1 * 100 if ca_n1 else 0
    check("CA growth plausible (-50% to +100%)",
          -50 < growth < 100,
          f"Growth = {growth:+.1f}%  ({rows[0].annee}: {ca_n:,.0f}  vs  {rows[1].annee}: {ca_n1:,.0f})",
          "Between -50% and +100%",
          "Year N has partial data (only Feb 2026) vs full year N-1 — filter dashboard to same months")

# Check months available per year
month_rows = dw_all("""
    SELECT d.annee, COUNT(DISTINCT d.mois) AS nb_mois, MIN(d.mois) AS first_month, MAX(d.mois) AS last_month
    FROM FAIT_LIGNES_VENTE f
    JOIN DIM_DATE d ON d.id_date = f.id_date
    JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
    WHERE dom.DO_Domaine = 0
    GROUP BY d.annee ORDER BY d.annee DESC
""")
print("  Months with data per year:")
for r in month_rows:
    print(f"    {r.annee}: {r.nb_mois} months (mois {r.first_month}..{r.last_month})")

# ================================================================
print(f"\n{SEP}")
print("  3. STOCK DUPLICATES — same article appears twice in alerts")
print(SEP)

dup_stock = dw_all("""
    SELECT a.AR_Ref_code, COUNT(*) AS nb, SUM(fe.AS_QteSto) AS total_stock
    FROM FAIT_ECRITURES fe
    JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
    JOIN DIM_ARTICLE a ON a.id_article = fe.id_article
    WHERE tl.type_ligne = 4
    GROUP BY a.AR_Ref_code
    HAVING COUNT(*) > 1
    ORDER BY nb DESC
""")
check("No duplicate articles in stock snapshot",
      len(dup_stock) == 0,
      f"{len(dup_stock)} articles appear multiple times (multiple depots)",
      "Each article appears once",
      "Normal if multi-depot — dashboard should SUM or filter by depot, not show raw rows")

if dup_stock:
    print("  Top duplicated articles (likely multiple depots):")
    for r in dup_stock[:5]:
        print(f"    ART-{r.AR_Ref_code}: {r.nb} rows  total_stock={float(r.total_stock or 0):.0f}")

# ================================================================
print(f"\n{SEP}")
print("  4. RFM SCORES — all Dormant, Champion=0 Fidele=0")
print(SEP)

rfm_dist = dw_all("""
    SELECT rfm_score, COUNT(*) AS nb,
           AVG(CAST(rfm_recence_jours AS FLOAT)) AS avg_recence,
           AVG(CAST(rfm_frequence AS FLOAT)) AS avg_freq
    FROM DIM_CLIENT
    WHERE rfm_score IS NOT NULL
    GROUP BY rfm_score ORDER BY nb DESC
""")
print("  RFM distribution:")
for r in rfm_dist:
    print(f"    '{r.rfm_score}': {r.nb} clients  avg_recence={float(r.avg_recence or 0):.0f}j  avg_freq={float(r.avg_freq or 0):.1f}")

rfm_raw = dw("""
    SELECT
        MIN(rfm_recence_jours) AS min_rec,
        MAX(rfm_recence_jours) AS max_rec,
        MIN(rfm_frequence) AS min_freq,
        MAX(rfm_frequence) AS max_freq,
        AVG(CAST(rfm_recence_jours AS FLOAT)) AS avg_rec,
        AVG(CAST(rfm_frequence AS FLOAT)) AS avg_freq,
        SUM(CASE WHEN rfm_recence_jours <= 30 AND rfm_frequence >= 4 THEN 1 ELSE 0 END) AS should_be_champion,
        SUM(CASE WHEN rfm_recence_jours <= 60 AND rfm_frequence >= 3 THEN 1 ELSE 0 END) AS should_be_fidele,
        SUM(CASE WHEN rfm_recence_jours <= 90 THEN 1 ELSE 0 END) AS should_be_a_risque
    FROM DIM_CLIENT
    WHERE rfm_recence_jours IS NOT NULL
""")
print(f"\n  Recence range: {rfm_raw.min_rec}j .. {rfm_raw.max_rec}j  (avg={float(rfm_raw.avg_rec or 0):.0f}j)")
print(f"  Frequence range: {rfm_raw.min_freq} .. {rfm_raw.max_freq}  (avg={float(rfm_raw.avg_freq or 0):.1f})")
print(f"  Clients who SHOULD be Champion (rec<=30, freq>=4): {rfm_raw.should_be_champion}")
print(f"  Clients who SHOULD be Fidele   (rec<=60, freq>=3): {rfm_raw.should_be_fidele}")
print(f"  Clients who SHOULD be A risque (rec<=90):          {rfm_raw.should_be_a_risque}")

check("RFM thresholds produce non-zero Champion/Fidele",
      int(rfm_raw.should_be_champion or 0) > 0 or int(rfm_raw.should_be_fidele or 0) > 0,
      f"Champion={rfm_raw.should_be_champion}  Fidele={rfm_raw.should_be_fidele}",
      "> 0 in each category",
      "Thresholds too strict for your data — avg freq is low. Adjust in pipeline.py _compute_rfm_scores()")

# Suggest better thresholds based on actual data
freq_dist = dw_all("""
    SELECT rfm_frequence, COUNT(*) AS nb
    FROM DIM_CLIENT
    WHERE rfm_frequence IS NOT NULL
    GROUP BY rfm_frequence
    ORDER BY rfm_frequence DESC
""")
print("\n  Frequence distribution (to calibrate thresholds):")
for r in freq_dist[:10]:
    print(f"    freq={r.rfm_frequence}: {r.nb} clients")

# ================================================================
print(f"\n{SEP}")
print("  5. AGIOS = 0 DT — rapprochement bancaire shows 0 agios")
print(SEP)

agios = dw("""
    SELECT
        SUM(LB_Agios) AS total_agios,
        COUNT(CASE WHEN LB_Agios IS NOT NULL AND LB_Agios > 0 THEN 1 END) AS rows_with_agios,
        COUNT(*) AS total
    FROM FAIT_REGLEMENTS
""")
check("LB_Agios has data",
      float(agios.total_agios or 0) > 0,
      f"Total agios={float(agios.total_agios or 0):,.0f}  rows_with_agios={agios.rows_with_agios}/{agios.total}",
      "> 0",
      "LB_Agios not populated in GRT source — check F_LigneBordereauRemise table")

# Check source
try:
    src_agios = src1(GRT_ENGINE, """
        SELECT COUNT(*) AS nb, SUM(LB_Agios) AS total
        FROM F_LigneBordereauRemise
        WHERE LB_Agios IS NOT NULL AND LB_Agios > 0
    """)
    print(f"  GRT F_LigneBordereauRemise: {src_agios.nb} rows with LB_Agios, total={float(src_agios.total or 0):,.0f}")
except Exception as e:
    print(f"  GRT F_LigneBordereauRemise: not accessible — {e}")

# ================================================================
print(f"\n{SEP}")
print("  6. FOURNISSEUR VALEUR REF = '—' — CT_SvCA missing")
print(SEP)

svca = dw("""
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN CT_SvCA IS NOT NULL AND CT_SvCA > 0 THEN 1 ELSE 0 END) AS has_svca,
        SUM(CT_SvCA) AS total_svca
    FROM DIM_FOURNISSEUR
""")
check("DIM_FOURNISSEUR CT_SvCA populated",
      int(svca.has_svca) > 0,
      f"{svca.has_svca}/{svca.total} fournisseurs have CT_SvCA  total={float(svca.total_svca or 0):,.0f}",
      "> 0",
      "CT_SvCA is populated from MAG F_COMPTET — verify it's not 0 in source")

try:
    src_svca = src1(MAG_ENGINE, """
        SELECT COUNT(*) AS nb, SUM(CT_SvCA) AS total
        FROM F_COMPTET
        WHERE CT_Type = 1 AND CT_SvCA IS NOT NULL AND CT_SvCA > 0
    """)
    print(f"  MAG F_COMPTET fournisseurs with CT_SvCA > 0: {src_svca.nb}  total={float(src_svca.total or 0):,.0f}")
except Exception as e:
    print(f"  MAG CT_SvCA check failed: {e}")

# ================================================================
print(f"\n{SEP}")
print("  7. GOUVERNORAT 23% 'Autre' — 983/4211 clients unmapped")
print(SEP)

unmapped = dw_all("""
    SELECT TOP 20
        CT_CodeRegion,
        COUNT(*) AS nb
    FROM DIM_CLIENT
    WHERE gouvernorat = 'Autre'
    AND CT_CodeRegion IS NOT NULL
    AND CT_CodeRegion != ''
    GROUP BY CT_CodeRegion
    ORDER BY nb DESC
""")
check("Gouvernorat unresolved < 5%",
      False,
      "23.3% unresolved (983/4211)",
      "< 5%",
      "Add missing CT_CodeRegion values to _normalize_gouvernorat() in pipeline.py")

print("  Top unresolved CT_CodeRegion values to add to mapping:")
for r in unmapped:
    print(f"    '{r.CT_CodeRegion}': {r.nb} clients")

# ================================================================
print(f"\n{SEP}")
print("  8. TAUX RAPPROCHEMENT BANCAIRE — shows 97% (check Float=0j)")
print(SEP)

banque = dw("""
    SELECT
        AVG(CASE WHEN RT_Rapproche=1 OR DR_Regle=1 THEN 100.0 ELSE 0 END) AS taux,
        AVG(CAST(NULLIF(LB_NbJour, 0) AS FLOAT)) AS float_moyen,
        COUNT(CASE WHEN LB_NbJour > 0 THEN 1 END) AS has_float
    FROM FAIT_REGLEMENTS
    WHERE RT_Montant IS NOT NULL
""")
check("Float bancaire (LB_NbJour) has data",
      int(banque.has_float or 0) > 0,
      f"Float moyen={float(banque.float_moyen or 0):.1f}j  rows with float={banque.has_float}",
      "> 0 rows",
      "LB_NbJour not populated — check F_LigneBordereauRemise in GRT source")

# ================================================================
print(f"\n{SEP}")
print("  9. CLIENTS ACTIFS = 360 on dashboard vs 4211 in DIM_CLIENT")
print(SEP)

active = dw("""
    SELECT
        COUNT(DISTINCT f.id_client) AS active_clients_in_sales,
        (SELECT COUNT(*) FROM DIM_CLIENT WHERE CT_Sommeil = 0) AS non_sommeil
    FROM FAIT_LIGNES_VENTE f
    JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
    JOIN DIM_DATE d ON d.id_date = f.id_date
    WHERE dom.DO_Domaine = 0
    AND d.annee = (SELECT MAX(annee) FROM DIM_DATE WHERE id_date IN
        (SELECT id_date FROM FAIT_LIGNES_VENTE))
""")
print(f"  Clients who bought in latest year: {active.active_clients_in_sales}")
print(f"  Clients with CT_Sommeil=0:         {active.non_sommeil}")
check("Active clients count reasonable",
      int(active.active_clients_in_sales or 0) >= 300,
      f"{active.active_clients_in_sales} clients actifs in latest year",
      ">= 300",
      "Normal — only clients who actually purchased appear as 'actifs'")

# ================================================================
print(f"\n{SEP}")
print("  10. DELAI MOYEN REGLEMENT = 10j — verify against source")
print(SEP)

delai = dw("""
    WITH d AS (
        SELECT RT_Num, MAX(delai_reel_jours) AS delai
        FROM FAIT_REGLEMENTS
        WHERE RT_Num IS NOT NULL AND id_client IS NOT NULL
        AND delai_reel_jours IS NOT NULL AND delai_reel_jours > 0
        GROUP BY RT_Num
    )
    SELECT
        AVG(CAST(delai AS FLOAT)) AS avg_delai,
        MIN(delai) AS min_delai,
        MAX(delai) AS max_delai,
        COUNT(*) AS nb
    FROM d
""")
check("Delai moyen between 1 and 90 days",
      1 < float(delai.avg_delai or 0) < 90,
      f"Avg={float(delai.avg_delai or 0):.1f}j  Min={delai.min_delai}  Max={delai.max_delai}  N={delai.nb}",
      "1-90 days", "")

# ================================================================
print(f"\n{SEP}")
print("  SUMMARY OF ISSUES FOUND")
print(SEP)

if not issues:
    print("  All checks passed!")
else:
    print(f"  {len(issues)} issue(s) to fix:\n")
    for i, (label, fix) in enumerate(issues, 1):
        print(f"  {i}. {label}")
        if fix:
            print(f"     → {fix}")

print(f"\n{SEP}")
print("  RECOMMENDED FIXES (run in order)")
print(SEP)
print("""
  FIX 1 — RFM thresholds (pipeline.py line ~_compute_rfm_scores):
    Look at the frequence distribution printed above.
    If most clients have freq=1-2, change the SQL thresholds:
      Champion:  rec <= 30  AND freq >= 2   (was 4)
      Fidele:    rec <= 60  AND freq >= 2   (was 3)
      A risque:  rec <= 180                 (was 90)
    Then rerun: python -c "from etl.pipeline import _compute_rfm_scores; _compute_rfm_scores()"

  FIX 2 — Gouvernorat mapping (pipeline.py _normalize_gouvernorat):
    Take the list of unresolved CT_CodeRegion printed above
    and add each one to the correct gouvernorat bucket in the mapping dict.
    Then rerun ETL delta: python -m etl.pipeline

  FIX 3 — Marge brute (if DL_Qte is the problem):
    In extract.py extract_fait_lignes_vente(), verify dl.DL_Qte
    is included in the SELECT. It is in the code — so the issue
    may be that AR_PrixAch in Sage is 0 for most articles.
    Check: how many articles have AR_PrixAch > 0 in MAG (printed above).

  FIX 4 — CA N-1 442% growth:
    This is a display bug in the dashboard frontend, not an ETL bug.
    Year 2026 has only 2 months of data vs full 2025.
    Fix the frontend to compare same period (Jan-Feb 2025 vs Jan-Feb 2026).

  FIX 5 — Stock duplicates in alerts table:
    Normal behavior — one article per depot.
    Fix the API query in queries.py get_stock_alerts() to add:
      GROUP BY a.AR_Ref_code  (aggregate across depots)
    or add a WHERE clause to filter to the main depot only.
""")