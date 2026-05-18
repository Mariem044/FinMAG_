from etl.api.queries import _rows

# List segments
segments = _rows("SELECT DISTINCT libelle_segment FROM DIM_SEGMENT")
print("Segments in DIM_SEGMENT:")
for s in segments:
    print(f"  - '{s.libelle_segment}'")

# List active segments in sales for 2026
active_segments = _rows("""
    SELECT DISTINCT s.libelle_segment, COUNT(*) as count
    FROM FAIT_LIGNES_VENTE f
    JOIN DIM_DATE d ON d.id_date = f.id_date
    JOIN DIM_CLIENT c ON c.id_client = f.id_client
    JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
    WHERE d.annee = 2026
    GROUP BY s.libelle_segment
""")
print("Active segments in sales for 2026:")
for s in active_segments:
    print(f"  - '{s.libelle_segment}': {s.count}")
