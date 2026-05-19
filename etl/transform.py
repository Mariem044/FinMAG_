import pandas as pd
from etl.config import hash_key

def resolve_fk(df: pd.DataFrame, source_col: str, lookup: dict, target_col: str) -> pd.DataFrame:
    """Associe une clef metier (ex: CT_Num) a sa clef technique de l'entrepot (id_client) via un dictionnaire de correspondance."""
    df = df.copy()
    df[target_col] = df[source_col].map(lookup)
    return df

def transform_dim_date(df: pd.DataFrame) -> pd.DataFrame:
    """Genere les attributs calendaires (jour, mois, annee, etc.) a partir d'une liste de dates."""
    df = df.copy()
    df["date_val"] = pd.to_datetime(df["date_val"])
    df["jour"] = df["date_val"].dt.day.astype("int16")
    df["mois"] = df["date_val"].dt.month.astype("int16")
    df["trimestre"] = df["date_val"].dt.quarter.astype("int16")
    df["semestre"] = df["date_val"].apply(lambda m: 1 if m <= 6 else 2).astype("int16")
    df["annee"] = df["date_val"].dt.year.astype("int16")
    df["semaine"] = df["date_val"].dt.isocalendar().week.astype("int16")
    df["jour_semaine"] = df["date_val"].dt.dayofweek.astype("int16")
    df["est_weekend"] = df["jour_semaine"].apply(lambda d: 1 if d >= 5 else 0).astype("int16")
    df["est_ferie"] = 0 # Par defaut 0 pour simplifier
    df["exercice"] = df["annee"]
    return df

def transform_dim_client(df: pd.DataFrame, segment_lookup: dict, collab_lookup: dict) -> pd.DataFrame:
    """Transforme les clients en appliquant les hashages et en resolvant les cles etrangeres."""
    df = df.copy()
    df["CT_Num_code"] = df["CT_Num"].apply(hash_key)
    
    # Resolutions simples des relations vers le segment et le collaborateur
    df["id_segment"] = df["N_CatTarif"].apply(hash_key).map(segment_lookup)
    df["id_collab"] = df["CO_No"].map(collab_lookup)
    return df

def add_fact_lignes_vente_calcs(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule le hash de la piece pour l'analyse croisee."""
    df = df.copy()
    df["DO_Piece_hash"] = df["DO_Piece"].apply(hash_key)
    return df

def add_fact_reglements_calcs(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule les delais reels de paiement en jours et les ecarts par rapport au delai contractuel."""
    df = df.copy()
    df["RT_Date"] = pd.to_datetime(df["RT_Date"], errors="coerce")
    df["DO_Date"] = pd.to_datetime(df["DO_Date"], errors="coerce")
    df["RT_NbJour"] = pd.to_numeric(df["RT_NbJour"], errors="coerce").fillna(0)
    
    df["delai_reel_jours"] = (df["RT_Date"] - df["DO_Date"]).dt.days
    df["ecart_delai"] = df["delai_reel_jours"] - df["RT_NbJour"]
    return df

def add_fact_ecritures_calcs(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule les ratios de stock, quantites disponibles et alertes ruptures."""
    if df.empty:
        return df
    df = df.copy()
    
    # Conversion des colonnes de stock en numerique
    for col in ["AS_QteSto", "AS_QteRes", "AS_QteMini"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["qte_disponible"] = df["AS_QteSto"] - df["AS_QteRes"]
    
    # Tension = Reserve / (Total - Reserve), borne entre 0 et 1
    denominateur = df["AS_QteSto"] - df["AS_QteRes"]
    df["ratio_tension"] = (df["AS_QteRes"] / denominateur).where(denominateur > 0, 0).clip(0, 1)
    
    # Rupture = Stock Actuel <= Stock Minimum
    df["en_rupture"] = (df["AS_QteSto"] <= df["AS_QteMini"]).astype("int16")
    return df