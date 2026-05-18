import sys
import os

# Add parent directory to PYTHONPATH
sys.path.append(os.path.abspath("."))

from etl.api.queries import _row, _rows

# 1. Get average rows count globally
avg_row = _row("""
    SELECT AVG(CAST(row_cnt AS FLOAT)) AS avg_rows
    FROM (
        SELECT d.annee, d.mois, COUNT(*) AS row_cnt
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DATE d ON d.id_date = f.id_date
        GROUP BY d.annee, d.mois
    ) counts
""")
print(f"Global average rows per month (avg_rows): {avg_row.avg_rows}")
threshold = avg_row.avg_rows * 0.5
print(f"Threshold (avg_rows * 0.5): {threshold}")

# 2. Get monthly row counts with default/empty filters (year=2024)
print("\nMonthly row counts for 2024 (unfiltered):")
rows_unfilt = _rows("""
    SELECT d.annee, d.mois, COUNT(*) AS row_cnt
    FROM FAIT_LIGNES_VENTE f
    JOIN DIM_DATE d ON d.id_date = f.id_date
    WHERE d.annee = 2024
    GROUP BY d.annee, d.mois
    ORDER BY d.mois
""")
for r in rows_unfilt:
    print(f"  Month {r.mois}: row_cnt={r.row_cnt} (Passed threshold? {r.row_cnt >= threshold})")

# 3. Simulate with a specific depot or segment that the user might have selected
# Wait, let's see if there is any active filter in the user's view (like GRT_MAG or a segment)
print("\nMonthly row counts for 2024 with a filter (e.g. segment='DÉTAILLANTS' or similar):")
rows_filt = _rows("""
    SELECT d.annee, d.mois, COUNT(*) AS row_cnt
    FROM FAIT_LIGNES_VENTE f
    JOIN DIM_DATE d ON d.id_date = f.id_date
    LEFT JOIN DIM_CLIENT c ON c.id_client = f.id_client
    LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
    WHERE d.annee = 2024 AND s.libelle_segment = 'DETAILLANTS'
    GROUP BY d.annee, d.mois
    ORDER BY d.mois
""")
for r in rows_filt:
    print(f"  Month {r.mois}: row_cnt={r.row_cnt} (Passed threshold? {r.row_cnt >= threshold})")
