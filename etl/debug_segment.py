import etl.load as L
import etl.extract as E
import etl.transform as T
import pandas as pd
from etl.config import DW_ENGINE, SEGMENTS

df_raw = E.extract_dim_segment()
df = (
    df_raw.copy()
    .assign(
        cbIndice_code=lambda d: d["cbIndice"].apply(T.hash_key),
        CT_PrixTTC=lambda d: pd.to_numeric(d["CT_PrixTTC"], errors="coerce").fillna(0).astype("Int16"),
        libelle_segment=lambda d: d["cbIndice"].map(
            lambda v: SEGMENTS.get(int(v), f"Segment {v}")
        ),
    )
)

df2 = L._prepare_for_load(df, "DIM_SEGMENT")
binary_cols = [c for c in df2.columns if c in L._BINARY_COLS]
df3 = L._hex_encode_binary_cols(df2, binary_cols) if binary_cols else df2

cols = list(df3.columns)
value_exprs = []
for c in cols:
    if c in binary_cols:
        value_exprs.append("CONVERT(VARBINARY(32), ?, 2)")
    else:
        value_exprs.append("?")

col_names = ", ".join([f"[{c}]" for c in cols])
values_sql = ", ".join(value_exprs)
sql = f"INSERT INTO [DIM_SEGMENT] ({col_names}) VALUES ({values_sql})"
print("SQL:", sql)
print()

rows = [tuple(L._to_python(v) for v in row) for row in df3.itertuples(index=False, name=None)]
print("All rows:")
for r in rows:
    for col, val in zip(cols, r):
        print(f"  {col}: type={type(val).__name__} len={len(str(val)) if val is not None else 'NULL'} repr={repr(val)}")
    print()