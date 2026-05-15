import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy import text
from etl.config import DW_ENGINE

def n(engine, sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()

def r(engine, sql):
    with engine.connect() as c:
        return c.execute(text(sql)).fetchone()

print("\n=== STOCK QUALITY ===")
row = r(DW_ENGINE, """
    SELECT
        SUM(CASE WHEN dsi_jours IS NOT NULL THEN 1 ELSE 0 END) AS has_dsi,
        SUM(CASE WHEN en_rupture = 1 THEN 1 ELSE 0 END) AS ruptures,
        SUM(CASE WHEN ratio_tension > 0.8 THEN 1 ELSE 0 END) AS tension,
        COUNT(*) AS total
    FROM FAIT_ECRITURES fe
    JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
    WHERE tl.type_ligne = 4
""")
print(f"  Stock rows: {row.total}  DSI computed: {row.has_dsi}  Ruptures: {row.ruptures}  Tension alerts: {row.tension}")

print("\n=== RFM QUALITY ===")
row = r(DW_ENGINE, """
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN rfm_score IS NOT NULL THEN 1 ELSE 0 END) AS scored,
        SUM(CASE WHEN rfm_score='Champion' THEN 1 ELSE 0 END) AS champion,
        SUM(CASE WHEN rfm_score='Fidele' THEN 1 ELSE 0 END) AS fidele,
        SUM(CASE WHEN rfm_score='A risque' THEN 1 ELSE 0 END) AS a_risque,
        SUM(CASE WHEN rfm_score='Dormant' THEN 1 ELSE 0 END) AS dormant
    FROM DIM_CLIENT
""")
print(f"  Clients: {row.total}  Scored: {row.scored}  Champion: {row.champion}  Fidele: {row.fidele}  A risque: {row.a_risque}  Dormant: {row.dormant}")

print("\n=== MARGIN QUALITY ===")
row = r(DW_ENGINE, """
    WITH ly AS (SELECT MAX(d.annee) AS y FROM FAIT_LIGNES_VENTE f JOIN DIM_DATE d ON d.id_date=f.id_date)
    SELECT
        SUM(f.DL_MontantHT) AS ca,
        SUM(CASE WHEN a.AR_PrixAch>0 AND f.DL_Qte IS NOT NULL
            THEN f.DL_MontantHT-(f.DL_Qte*a.AR_PrixAch) ELSE NULL END) AS marge,
        SUM(CASE WHEN a.AR_PrixAch>0 THEN f.DL_MontantHT ELSE 0 END) AS ca_avec_cout,
        COUNT(CASE WHEN a.AR_PrixAch>0 THEN 1 END) AS lines_with_cost,
        COUNT(*) AS total_lines
    FROM FAIT_LIGNES_VENTE f
    JOIN DIM_DOMAINE dom ON dom.id_domaine=f.id_domaine
    JOIN DIM_DATE d ON d.id_date=f.id_date
    LEFT JOIN DIM_ARTICLE a ON a.id_article=f.id_article
    CROSS JOIN ly
    WHERE dom.DO_Domaine=0 AND d.annee=ly.y
""")
ca = float(row.ca or 0)
ca_c = float(row.ca_avec_cout or 0)
marge = float(row.marge or 0)
pct_cover = ca_c/ca*100 if ca else 0
marge_pct = marge/ca_c*100 if ca_c else 0
print(f"  CA: {ca:,.0f} DT")
print(f"  Marge brute: {marge:,.0f} DT ({marge_pct:.1f}% of covered CA)")
print(f"  Cost coverage: {row.lines_with_cost:,}/{row.total_lines:,} lines ({pct_cover:.1f}%)")

print("\n=== GOUVERNORAT COVERAGE ===")
row = r(DW_ENGINE, """
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN gouvernorat='Autre' OR gouvernorat IS NULL THEN 1 ELSE 0 END) AS unresolved
    FROM DIM_CLIENT
""")
pct = int(row.unresolved)/max(int(row.total),1)*100
print(f"  Unresolved gouvernorats: {row.unresolved}/{row.total} ({pct:.1f}%)")

print("\n=== IMPAYES SUMMARY ===")
row = r(DW_ENGINE, """
    WITH d AS (
        SELECT RT_Num, MAX(RT_Montant) AS m, MAX(DR_Regle) AS regle
        FROM FAIT_REGLEMENTS
        WHERE RT_Num IS NOT NULL AND id_client IS NOT NULL
        GROUP BY RT_Num
    )
    SELECT
        SUM(CASE WHEN regle=1 THEN m ELSE 0 END) AS enc,
        SUM(CASE WHEN regle=0 THEN m ELSE 0 END) AS imp
    FROM d
""")
enc = float(row.enc or 0); imp = float(row.imp or 0)
taux = enc/(enc+imp)*100 if (enc+imp) else 0
print(f"  Encaissements: {enc:,.0f} DT")
print(f"  Impayes: {imp:,.0f} DT")
print(f"  Taux recouvrement: {taux:.1f}%")

print("\n=== DONE ===")
