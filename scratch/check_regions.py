import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from etl.config import DW_ENGINE
from sqlalchemy import text

with DW_ENGINE.connect() as conn:
    print("--- VERIFY REGIONAL SALES FOR 2024 ---")
    region_sql = """
        SELECT 
            COALESCE(NULLIF(c.gouvernorat, ''), 'Autre') AS name,
            SUM(f.DL_MontantHT) AS ca
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_CLIENT  c ON c.id_client  = f.id_client
        LEFT JOIN DIM_DATE    d ON d.id_date    = f.id_date
        WHERE dom.DO_Domaine = 0
        AND d.annee = 2024
        GROUP BY COALESCE(NULLIF(c.gouvernorat, ''), 'Autre')
        HAVING SUM(f.DL_MontantHT) > 0
        ORDER BY ca DESC
    """
    regions = conn.execute(text(region_sql)).fetchall()
    total_ca = float(sum(r.ca for r in regions))
    print(f"Total CA for Regions query: {total_ca:,.2f} DT")
    
    cumulative_pct = 0.0
    for r in regions:
        val = float(r.ca)
        pct = (val / total_ca * 100) if total_ca else 0.0
        cumulative_pct += pct
        print(f"Region: {r.name:20} | CA: {val:14,.2f} DT | Percentage: {pct:.2f}% (rounded: {round(pct):.0f}%)")
    print(f"Sum of exact percentages: {cumulative_pct:.2f}%")
    
    print("\n--- VERIFY TOP FAMILIES BY CA FOR 2024 ---")
    family_sql = """
        SELECT 
            COALESCE(NULLIF(fa.FA_Intitule, ''), 'Sans famille') AS name,
            SUM(f.DL_MontantHT) AS ca
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        LEFT JOIN DIM_ARTICLE a  ON a.id_article  = f.id_article
        LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
        WHERE dom.DO_Domaine = 0
        AND d.annee = 2024
        GROUP BY fa.FA_Intitule
        ORDER BY ca DESC
    """
    families = conn.execute(text(family_sql)).fetchall()
    total_fam_ca = float(sum(f.ca for f in families))
    print(f"Total CA for Families query: {total_fam_ca:,.2f} DT")
    for i, f in enumerate(families[:10], 1):
        val = float(f.ca)
        pct = (val / total_fam_ca * 100) if total_fam_ca else 0.0
        print(f"{i}. Family: {f.name:25} | CA: {val:14,.2f} DT | Percentage: {pct:.2f}%")

    print("\n--- VERIFY MONTHLY EVOLUTION FOR 2024 ---")
    monthly_sql = """
        SELECT 
            d.mois,
            SUM(f.DL_MontantHT) AS ca
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
        LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
        WHERE dom.DO_Domaine = 0
        AND d.annee = 2024
        GROUP BY d.mois
        ORDER BY d.mois
    """
    months = conn.execute(text(monthly_sql)).fetchall()
    months_map = ["Jan", "Fev", "Mar", "Avr", "Mai", "Jun", "Jul", "Aou", "Sep", "Oct", "Nov", "Dec"]
    monthly_total = 0.0
    for r in months:
        val = float(r.ca)
        monthly_total += val
        print(f"Month: {months_map[r.mois-1]:4} | CA: {val:14,.2f} DT")
    print(f"Sum of monthly CA: {monthly_total:,.2f} DT")
