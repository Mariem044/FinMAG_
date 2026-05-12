import os

os.environ.setdefault("DW_CONN", "sqlite:///:memory:")
os.environ.setdefault("MAG_CONN", "sqlite:///:memory:")
os.environ.setdefault("GRT_CONN", "sqlite:///:memory:")

import pandas as pd

from etl.config import hash_key
from etl.transform import add_fact_ecritures_calcs, add_fact_reglements_calcs


def test_hash_key_basic():
    assert hash_key("ABC") == hash_key("abc")
    assert hash_key(None) is None
    assert hash_key("") is None


def test_hash_key_returns_positive_sql_int():
    value = hash_key("MAG-001")
    assert isinstance(value, int)
    assert 0 <= value <= 0x7FFFFFFF


def test_add_fact_reglements_calcs():
    df = pd.DataFrame(
        {
            "RT_Date": ["2024-03-15"],
            "DO_Date": ["2024-02-01"],
            "RT_NbJour": [30],
        }
    )

    result = add_fact_reglements_calcs(df)

    assert "delai_reel_jours" in result.columns
    assert "ecart_delai" in result.columns
    assert result["delai_reel_jours"].iloc[0] == 43
    assert result["ecart_delai"].iloc[0] == 13


def test_add_fact_ecritures_calcs():
    df = pd.DataFrame(
        {
            "AS_QteSto": [100],
            "AS_QteRes": [90],
            "AS_QteMini": [10],
        }
    )

    result = add_fact_ecritures_calcs(df)

    assert result["qte_disponible"].iloc[0] == 10
    assert result["en_rupture"].iloc[0] == 0
    assert result["alerte_tension"].iloc[0] == 1
