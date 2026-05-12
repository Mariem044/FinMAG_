import os

os.environ.setdefault("DW_CONN", "sqlite:///:memory:")
os.environ.setdefault("MAG_CONN", "sqlite:///:memory:")
os.environ.setdefault("GRT_CONN", "sqlite:///:memory:")

import pandas as pd

from etl.load import _sha256_row, _to_python


def test_to_python_handles_nulls_and_scalars():
    assert _to_python(None) is None
    assert _to_python(pd.NA) is None
    assert _to_python(pd.Series([7], dtype="int64").iloc[0]) == 7


def test_sha256_row_is_stable_and_binary():
    row = pd.Series(["A", None, 10])

    first = _sha256_row(row)
    second = _sha256_row(row)

    assert first == second
    assert isinstance(first, bytes)
    assert len(first) == 32
