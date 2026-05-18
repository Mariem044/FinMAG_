import time
import sys
import os

# Add parent directory to PYTHONPATH
sys.path.append(os.path.abspath("."))

from etl.api.queries import _rows, _row, _build_dynamic_filters

# Build the filters for Tunis Nord
filt_sql, filt_params = _build_dynamic_filters(
    year=None, quarter=None, month=None, region=None, famille=None,
    segment=None, depot="Tunis Nord", source=None,
    aliases={"date": "d", "client": "c", "segment": "s"}
)

print(f"Generated filt_sql: {filt_sql}")
print(f"Generated filt_params: {filt_params}")

sql = f"""
    WITH deduped AS (
        SELECT
            r.RT_Num,
            MAX(r.RT_Montant)         AS RT_Montant,
            MAX(r.DR_Regle)           AS DR_Regle,
            MAX(r.delai_reel_jours)   AS delai_reel_jours
        FROM FAIT_REGLEMENTS r
        LEFT JOIN DIM_DATE d ON d.id_date = r.id_date_paiement
        LEFT JOIN DIM_CLIENT c ON c.id_client = r.id_client
        LEFT JOIN DIM_SEGMENT s ON s.id_segment = c.id_segment
        WHERE r.RT_Num IS NOT NULL AND r.id_client IS NOT NULL
        {filt_sql}
        GROUP BY r.RT_Num
    )
    SELECT
        SUM(CASE WHEN DR_Regle = 1 THEN RT_Montant ELSE 0 END) AS encaissements,
        SUM(CASE WHEN DR_Regle = 0 THEN RT_Montant ELSE 0 END) AS impayes,
        AVG(CAST(delai_reel_jours AS FLOAT)) AS delai_moyen
    FROM deduped
"""

print("Executing SQL on database...")
start_time = time.time()
try:
    row = _row(sql, filt_params)
    elapsed = time.time() - start_time
    print(f"  [SUCCESS] Query executed in {elapsed:.2f} seconds.")
    print(f"  Result: encaissements={row.encaissements}, impayes={row.impayes}, delai_moyen={row.delai_moyen}")
except Exception as e:
    print(f"  [ERROR] Query failed: {e}")
