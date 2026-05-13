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
    "add_fact_reglements_banking_fees",
    "add_fact_ecritures_dsi",
    "transform_dim_date",
    "transform_dim_client",
    "transform_dim_client_rfm",
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
    # FIX 3: guard for empty DataFrame — ensure output columns exist without KeyError
    if df.empty:
        import logging
        logging.getLogger(__name__).debug(
            "add_fact_ecritures_calcs: received empty DataFrame, returning with null KPI columns"
        )
        for col in ["qte_disponible", "ratio_tension", "en_rupture", "alerte_tension"]:
            if col not in df.columns:
                df[col] = pd.NA
        return df

    df = df.copy()
    df["qte_disponible"] = df["AS_QteSto"] - df["AS_QteRes"]
    denominator = df["AS_QteSto"] - df["AS_QteRes"]
    df["ratio_tension"] = (df["AS_QteRes"] / denominator).where(
        (denominator > 0) & (df["AS_QteRes"] >= 0), other=None
    ).clip(lower=0, upper=1)
    df["en_rupture"] = (
        (df["AS_QteSto"] <= df["AS_QteMini"]) &
        df["AS_QteSto"].notna() &
        df["AS_QteMini"].notna()
    ).astype("Int8")

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


def transform_dim_client_rfm(
    client_df: pd.DataFrame,
    rfm_data: pd.DataFrame,
) -> pd.DataFrame:
    """Enrich DIM_CLIENT with RFM calculations."""
    df = client_df.copy()

    if rfm_data.empty:
        df["rfm_recence_jours"] = None
        df["rfm_frequence"] = None
        df["rfm_montant_12m"] = None
        df["rfm_score"] = None
        return df

    rfm_data = rfm_data.copy()
    rfm_data["CT_Num_hash"] = rfm_data["CT_Num"].apply(hash_key)
    rfm_lookup = dict(zip(
        rfm_data["CT_Num_hash"],
        rfm_data[["last_purchase_date", "frequency", "montant_12m"]].values
    ))

    df["_CT_Num_hash"] = df["CT_Num"].apply(hash_key)
    df[["last_purchase_date", "rfm_frequence", "rfm_montant_12m"]] = (
        df["_CT_Num_hash"]
        .apply(lambda h: pd.Series(rfm_lookup.get(h, (None, None, None))))
        .set_axis(["last_purchase_date", "rfm_frequence", "rfm_montant_12m"], axis=1)
    )

    df["last_purchase_date"] = pd.to_datetime(df["last_purchase_date"], errors="coerce")
    df["rfm_recence_jours"] = (
        (pd.Timestamp.now().normalize() - df["last_purchase_date"]).dt.days
    ).astype("Int32")

    def _rfm_score(row) -> Optional[str]:
        if pd.isna(row["rfm_recence_jours"]) or pd.isna(row["rfm_frequence"]):
            return None
        if row["rfm_recence_jours"] <= 30 and row["rfm_frequence"] >= 4:
            return "Champion"
        elif row["rfm_recence_jours"] <= 60 and row["rfm_frequence"] >= 3:
            return "Fidèle"
        elif row["rfm_recence_jours"] <= 90:
            return "À risque"
        else:
            return "Dormant"

    df["rfm_score"] = df.apply(_rfm_score, axis=1)
    df = df.drop(columns=["_CT_Num_hash", "last_purchase_date"])

    return df


def add_fact_reglements_banking_fees(df: pd.DataFrame) -> pd.DataFrame:
    """Add banking fees calculations to FAIT_REGLEMENTS."""
    df = df.copy()

    if "BR_TauxAgios" not in df.columns:
        df["BR_TauxAgios"] = None
    if "BR_TMM" not in df.columns:
        df["BR_TMM"] = None

    df["BR_TauxAgios"] = pd.to_numeric(df["BR_TauxAgios"], errors="coerce").fillna(0)
    df["BR_TMM"] = pd.to_numeric(df["BR_TMM"], errors="coerce").fillna(0)

    return df


def add_fact_ecritures_dsi(
    ecritures_df: pd.DataFrame,
    sales_365d: pd.DataFrame,
) -> pd.DataFrame:
    """Add DSI (Days Sales of Inventory) calculations to FAIT_ECRITURES."""
    df = ecritures_df.copy()

    if "id_type_ligne" not in df.columns:
        return df

    stock_mask = df["id_type_ligne"] == 4

    if sales_365d.empty:
        df.loc[stock_mask, "qte_vendue_365j"] = None
        df.loc[stock_mask, "dsi_jours"] = None
        return df

    sales_365d_copy = sales_365d.copy()
    sales_365d_copy["AR_Ref_hash"] = sales_365d_copy["AR_Ref"].apply(hash_key)
    sales_lookup = dict(zip(sales_365d_copy["AR_Ref_hash"], sales_365d_copy["qte_vendue_365j"]))

    if "id_article" in df.columns:
        df.loc[stock_mask, "qte_vendue_365j"] = (
            df.loc[stock_mask, "id_article"]
            .map(lambda x: sales_lookup.get(x) if pd.notna(x) else None)
        )

    df["dsi_jours"] = None
    if "AS_QteSto" in df.columns and "qte_vendue_365j" in df.columns:
        valid_mask = (
            stock_mask &
            df["AS_QteSto"].notna() &
            df["qte_vendue_365j"].notna() &
            (df["qte_vendue_365j"] > 0)
        )
        df.loc[valid_mask, "dsi_jours"] = (
            df.loc[valid_mask, "AS_QteSto"] / (df.loc[valid_mask, "qte_vendue_365j"] / 365)
        ).astype("float64")

    return df