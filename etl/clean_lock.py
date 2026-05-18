from etl.config import DW_ENGINE
from sqlalchemy import text

def clean_lock():
    print("Nettoyage du verrou ETL...")
    with DW_ENGINE.connect() as conn:
        result = conn.execute(text("""
            UPDATE ETL_AUDIT 
            SET status = 'ABORTED', error_msg = 'Stopped by user' 
            WHERE status = 'RUNNING' AND table_name = 'PIPELINE'
        """))
        conn.commit()
        print(f"Verrou nettoyé. Lignes affectées : {result.rowcount}")

if __name__ == "__main__":
    clean_lock()
