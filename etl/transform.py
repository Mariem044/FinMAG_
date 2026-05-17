from __future__ import annotations

import sys
import os
from pathlib import Path

# Permet d'importer le module 'etl' lorsqu'on exécute le script directement depuis le dossier etl
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

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
    df["DO_Piece_hash"] = df["DO_Piece"].apply(hash_key).astype("Int64")
    return df


def add_fact_ecritures_calcs(df: pd.DataFrame) -> pd.DataFrame:
    # FIX 3: guard for empty DataFrame — ensure output columns exist without KeyError
    if df.empty:
        import logging
        logging.getLogger(__name__).debug(
            "add_fact_ecritures_calcs: received empty DataFrame, returning with null KPI columns"
        )
        for col in ["qte_disponible", "ratio_tension", "en_rupture"]:
            if col not in df.columns:
                df[col] = pd.NA
        return df

    df = df.copy()
    
    # Transtypage explicite pour supporter les entrées brutes (strings du CSV)
    for col in ["AS_QteSto", "AS_QteRes", "AS_QteMini"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["qte_disponible"] = df["AS_QteSto"] - df["AS_QteRes"]
    denominator = df["AS_QteSto"] - df["AS_QteRes"]
    df["ratio_tension"] = (df["AS_QteRes"] / denominator).where(
        (denominator > 0) & (df["AS_QteRes"] >= 0), other=None
    ).clip(lower=0, upper=1)
    df["en_rupture"] = (
        (df["AS_QteSto"] <= df["AS_QteMini"]) &
        df["AS_QteSto"].notna() &
        df["AS_QteMini"].notna()
    ).astype("Int16")
    return df


def add_fact_reglements_calcs(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["RT_Date"]   = pd.to_datetime(df.get("RT_Date"),   errors="coerce")
    df["DO_Date"]   = pd.to_datetime(df.get("DO_Date"),   errors="coerce")
    df["RT_NbJour"] = pd.to_numeric(df.get("RT_NbJour"),  errors="coerce")
    df["delai_reel_jours"] = (df["RT_Date"] - df["DO_Date"]).dt.days.astype("Int32")
    df["ecart_delai"]      = (df["delai_reel_jours"] - df["RT_NbJour"]).astype("Int32")
    return df


def transform_dim_date(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["annee"] = df["date"].dt.year.astype("Int16")
    df["mois"]  = df["date"].dt.month.astype("Int16")
    df["jour"]  = df["date"].dt.day.astype("Int16")
    df["semaine"] = df["date"].dt.isocalendar().week.astype("Int16")
    df["trimestre"] = df["date"].dt.quarter.astype("Int16")
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

    # NOTE: sales_lookup is keyed by AR_Ref hash, not id_article surrogate.
    # DSI is computed correctly via _compute_dsi_jours() SQL in pipeline.py.
    # This branch is intentionally left as a no-op to avoid incorrect mapping.
    if False:  # pragma: no cover
        pass

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


if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path

    # Ajout de la racine du projet au path pour les imports locaux
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    input_dir = Path(r"C:\Users\marie\Desktop\myProject\FINMAG\etl\TEMP")
    output_dir = Path(r"C:\Users\marie\Desktop\myProject\FINMAG\etl\TEMP-TRANSF")
    
    # Création du dossier cible s'il n'existe pas
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Dossier source : {input_dir}")
    print(f"Dossier destination : {output_dir}")
    print("-" * 50)
    
    def process_all_files():
        # Liste de tous les fichiers dans TEMP
        for file_path in input_dir.glob("*.csv"):
            filename = file_path.name
            out_path = output_dir / filename
            
            print(f"Traitement de {filename}...")
            try:
                # Lecture brute
                df = pd.read_csv(file_path, sep=";", dtype=str)
                
                # Routage des transformations spécifiques
                if filename == "fait_lignes_vente.csv":
                    df = add_fact_lignes_vente_calcs(df)
                    print(f" => Application des calculs de ventes (DO_Piece_hash)")
                    
                elif filename in ["fait_artstock.csv", "fait_ecriturec.csv"]:
                    df = add_fact_ecritures_calcs(df)
                    print(f" => Application des calculs de stocks (en_rupture, tension)")
                    
                elif filename in ["fait_reglements_clients.csv", "fait_reglements_fournisseurs.csv"]:
                    # Simulation de jointure doc_dates
                    doc_dates_path = input_dir / "docentete_dates.csv"
                    if doc_dates_path.exists():
                        doc_dates = pd.read_csv(doc_dates_path, sep=";", dtype=str)[["DO_Type", "DO_Piece", "DO_Date"]]
                        doc_dates = doc_dates.drop_duplicates(subset=["DO_Type", "DO_Piece"], keep="last")
                        df = df.merge(doc_dates, on=["DO_Type", "DO_Piece"], how="left")
                    else:
                        df["DO_Date"] = pd.NA
                    
                    df = add_fact_reglements_calcs(df)
                    df = add_fact_reglements_banking_fees(df)
                    print(f" => Application des calculs de règlements (délais, agios)")
                    
                else:
                    # Pass-through pour les dimensions et autres tables
                    print(f" => Pass-through (pas de règles de calcul complexes)")
                
                # Sauvegarde unifiée
                df.to_csv(out_path, sep=";", index=False, encoding="utf-8-sig")
                
            except Exception as e:
                print(f" => Erreur sur {filename} : {e}")

    # Lancement du traitement de tous les fichiers
    process_all_files()
    
    print("-" * 50)
    print("Test unitaire terminé ! Tous les fichiers sont dans TEMP-TRANSF.")