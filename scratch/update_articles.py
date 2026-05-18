import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
from etl import extract, load, pipeline

print("Starting custom update for DIM_ARTICLE...")

# 1. Extract
df = extract.extract_dim_article()
print(f"Extracted {len(df)} articles.")

# 2. Transform
# Build lookups for DIM_FAMILLE and DIM_FOURNISSEUR first since the step uses map
lookups = {
    "DIM_FAMILLE": pipeline._build_lookup("DIM_FAMILLE", "FA_CodeFamille_code", "id_famille"),
    "DIM_FOURNISSEUR": pipeline._build_lookup("DIM_FOURNISSEUR", "CT_Num_code", "id_fournisseur"),
}
print("Built family and supplier lookups.")

# Replicate the transform step
df = pipeline._hash_columns(df, ["AR_Ref", "FA_CodeFamille", "CT_Num_fourn"])
df = df.assign(
    id_famille=lambda d: d["FA_CodeFamille"].apply(
        lambda v: lookups.get("DIM_FAMILLE", {}).get(pipeline.transform.hash_key(v))
    ),
    FA_Intitule=lambda d: d["FA_CodeFamille"].apply(
        lambda v: (
            pipeline._famille_label_lookup().get(int(pipeline.transform.hash_key(v)))
            if v is not None and pd.notna(v) and pipeline.transform.hash_key(v) is not None
            else None
        )
    ),
    id_fournisseur=lambda d: d["CT_Num_fourn"].apply(
        lambda v: lookups.get("DIM_FOURNISSEUR", {}).get(pipeline.transform.hash_key(v))
    ),
    AR_Design=lambda d: d["AR_Design"].str.strip().str[:100] if "AR_Design" in d.columns else None,
)

# 3. Load
load.load_dimension(df, "DIM_ARTICLE", "delta", key_col="AR_Ref_code")
print("Updated DIM_ARTICLE with designations and refs.")
