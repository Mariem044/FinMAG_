from sqlalchemy import text
from etl.config import DW_ENGINE

with DW_ENGINE.begin() as conn:
    n = conn.execute(text(
        "UPDATE ETL_AUDIT "
        "SET status='ABORTED', "
        "error_msg='Manual reset', "
        "duration_seconds=DATEDIFF(SECOND, run_date, GETUTCDATE()) "
        "WHERE status='RUNNING' AND table_name='PIPELINE'"
    )).rowcount

print(f"Reset {n} stuck run(s).")