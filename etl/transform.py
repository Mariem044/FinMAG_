from __future__ import annotations

from typing import Dict, Any, Optional

import pandas as pd


from etl.config import hash_key

__all__ = [
    "hash_key",
    "resolve_fk",
    "add_fact_lignes_vente_calcs",
    "add_fact_ecritures_calcs",
    "add_fact_reglements_calcs",
    "add_fact_reglements_bucket",
    "transform_dim_date",
    "transform_dim_client",
]



def resolve_fk(
    df: pd.DataFrame,
    source_col: str,
    lookup: Dict[Any, int],
    target_col: str,
    orphan_threshold: Optional[int] = None,
) -> pd.DataFrame:
    import logging
    df[target_col] = df[source_col].map(lookup)
    orphan_cnt = int(df[target_col].isna().sum())
    if orphan_cnt:
        logging.getLogger(__name__).warning(
            f"{orphan_cnt} orphan rows when resolving FK {source_col} → {target_col}"
        )
        if orphan_threshold is not None and orphan_cnt > orphan_threshold:
            raise ValueError(
                f"{orphan_cnt} orphan rows exceed threshold "
                f"({orphan_threshold}) resolving FK {source_col} → {target_col}"
            )
    return df



def add_fact_lignes_vente_calcs(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["DO_Piece_hash"] = df["DO_Piece"].apply(hash_key)
    return df


def add_fact_ecritures_calcs(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["qte_disponible"] = df["AS_QteSto"] - df["AS_QteRes"]
    denominator = df["AS_QteSto"] - df["AS_QteRes"]
    df["ratio_tension"] = (df["AS_QteRes"] / denominator).where(
        denominator > 0, other=None
    )
    df["en_rupture"] = (df["AS_QteSto"] <= df["AS_QteMini"]).astype("Int8")

    tension_flag = df["ratio_tension"].where(df["ratio_tension"].notna())
    df["alerte_tension"] = (
        (tension_flag > 0.8)
        .where(tension_flag.notna())
        .astype("Int8")
    )
    return df


def add_fact_reglements_calcs(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["RT_Date"]   = pd.to_datetime(df["RT_Date"],   errors="coerce")
    df["DO_Date"]   = pd.to_datetime(df["DO_Date"],   errors="coerce")
    df["RT_NbJour"] = pd.to_numeric(df["RT_NbJour"],  errors="coerce")
    df["delai_reel_jours"] = (df["RT_Date"] - df["DO_Date"]).dt.days
    df["ecart_delai"]      = df["delai_reel_jours"] - df["RT_NbJour"]
    return df


def add_fact_reglements_bucket(df: pd.DataFrame) -> pd.DataFrame:
    def _bucket(row) -> Optional[int]:
        if row.get("DR_Regle", 1) != 0:
            return None
        days = row.get("delai_reel_jours")
        if days is None or pd.isna(days):
            return None
        days = int(days)
        if days <= 30:
            return 0
        if days <= 60:
            return 1
        if days <= 90:
            return 2
        return 3

    df = df.copy()
    df["bucket_impaye"] = df.apply(_bucket, axis=1)
    return df



def transform_dim_date(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["annee"] = df["date"].dt.year.astype("Int16")
    df["mois"]  = df["date"].dt.month.astype("Int16")
    df["jour"]  = df["date"].dt.day.astype("Int16")
    return df


def transform_dim_client(
    df: pd.DataFrame,
    lookup_segment: Dict[int, int],
    lookup_collab:  Dict[int, int],
) -> pd.DataFrame:
    df = df.copy()
    df["CT_Num_code"]    = df["CT_Num"].apply(hash_key)
    df["_N_CatTarif_hash"] = df["N_CatTarif"].apply(hash_key)
    df = resolve_fk(df, "_N_CatTarif_hash", lookup_segment, "id_segment")
    df = df.drop(columns=["_N_CatTarif_hash"])
    df = resolve_fk(df, "CO_No", lookup_collab, "id_collab")
    return df
