import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pandas as pd
from etl import pipeline
from etl import load

original_load_fact = load.load_fact

def mock_load_fact(df, tbl, mode):
    if tbl == "FAIT_ECRITURES":
        print(f"\n--- DTYPES for {tbl} ---")
        for col, dtype in df.dtypes.items():
            print(f"{col}: {dtype} (sample: {df[col].iloc[0] if not df.empty else 'empty'})")
        sys.exit(0)
    else:
        original_load_fact(df, tbl, mode)

load.load_fact = mock_load_fact

if __name__ == "__main__":
    pipeline.run_pipeline(force_full=False)
