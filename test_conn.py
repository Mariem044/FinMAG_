from sqlalchemy import create_engine, text

try:
    engine = create_engine(r"mssql+pyodbc://@.\SQLEXPRESS/DW_SIAD?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes")
    with engine.connect() as conn:
        print("Success:", conn.execute(text("SELECT 1")).scalar())
except Exception as e:
    print("Failed:", e)
