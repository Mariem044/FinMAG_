import os

os.environ.setdefault("DW_CONN", "sqlite:///:memory:")
os.environ.setdefault("MAG_CONN", "sqlite:///:memory:")
os.environ.setdefault("GRT_CONN", "sqlite:///:memory:")

from datetime import datetime

import pandas as pd
import pytest

from etl.extract import _delta_filter, _validate_columns


def test_delta_filter_without_last_run():
    clause, params = _delta_filter("cbModification", None)

    assert clause == ""
    assert params == {}


def test_delta_filter_with_last_run():
    last_run = datetime(2024, 1, 1, 8, 30)

    clause, params = _delta_filter("table_alias.cbModification", last_run)

    assert clause == " AND table_alias.cbModification >= :last_run"
    assert params == {"last_run": last_run}


def test_delta_filter_rejects_unsafe_column_name():
    with pytest.raises(ValueError):
        _delta_filter("cbModification; DROP TABLE X", None)


def test_validate_columns_reports_missing_columns():
    df = pd.DataFrame({"present": [1]})

    with pytest.raises(ValueError, match="missing columns"):
        _validate_columns(df, ["present", "missing"], "sample")
