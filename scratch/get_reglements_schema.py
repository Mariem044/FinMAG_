from etl.api.queries import _rows

sql = "SELECT TOP 1 * FROM FAIT_REGLEMENTS"
try:
    rows = _rows(sql)
    if rows:
        print("Columns in FAIT_REGLEMENTS:")
        for col in rows[0]._mapping.keys():
            print(f"  - {col}")
    else:
        print("FAIT_REGLEMENTS is empty!")
except Exception as e:
    print(f"Failed to query FAIT_REGLEMENTS: {e}")
