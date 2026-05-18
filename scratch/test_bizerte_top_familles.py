from etl.api.queries import _rows

sql = """
    SELECT 
        COALESCE(NULLIF(fa.FA_Intitule, ''), 'Sans famille') AS name,
        SUM(f.DL_MontantHT) AS ca
    FROM FAIT_LIGNES_VENTE f
    JOIN DIM_DOMAINE dom ON dom.id_domaine = f.id_domaine
    LEFT JOIN DIM_DATE d ON d.id_date = f.id_date
    LEFT JOIN DIM_CLIENT c ON c.id_client = f.id_client
    LEFT JOIN DIM_ARTICLE a  ON a.id_article  = f.id_article
    LEFT JOIN DIM_FAMILLE fa ON fa.id_famille = a.id_famille
    WHERE dom.DO_Domaine = 0
    AND d.annee = 2026
    AND c.gouvernorat = 'Bizerte'
    GROUP BY fa.FA_Intitule
    ORDER BY ca DESC
"""

rows = _rows(sql)
print("Top families in 2026 for Bizerte:")
for r in rows[:5]:
    print(f"  - {r.name}: {r.ca:,.2f} DT")
