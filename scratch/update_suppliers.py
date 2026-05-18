import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
from etl import extract, load, pipeline

print("Starting custom update for DIM_FOURNISSEUR...")

# 1. Extract
df = extract.extract_dim_fournisseur()
print(f"Extracted {len(df)} suppliers.")

# 2. Transform
df = pipeline._hash_columns(df, ["CT_Num"])

# 3. Load
load.load_dimension(df, "DIM_FOURNISSEUR", "delta", key_col="CT_Num_code")
print("Updated DIM_FOURNISSEUR with names.")
