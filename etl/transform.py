"""Transformations de préparation des données pour les dimensions et faits ETL.

Ce module contient des fonctions pures (pandas) qui normalisent les
DataFrames extraits avant leur chargement. Elles ne doivent pas
effectuer d'opérations côté base de données.
"""

import pandas as pd

#quels sont les transform pandas? 
#ce sont les transformations spécifiques à notre domaine métier 
def transform_dim_date(df):
    """Ajoute les colonnes calendrier à un DataFrame de dates."""
    df = df.copy()
    #what is int16 ? c'est un type de données entier sur 16 bits, utilisé pour économiser de la mémoire lorsque les valeurs sont dans une plage limitée (ex: jours, mois, années)
    df["date_val"]    = pd.to_datetime(df["date_val"])
    df["jour"]        = df["date_val"].dt.day.astype("int16")
    df["mois"]        = df["date_val"].dt.month.astype("int16")
    df["trimestre"]   = df["date_val"].dt.quarter.astype("int16")
    df["semestre"]    = df["mois"].apply(lambda m: 1 if m <= 6 else 2).astype("int16")
    df["annee"]       = df["date_val"].dt.year.astype("int16")
    df["semaine"]     = df["date_val"].dt.isocalendar().week.astype("int16")
    df["jour_semaine"]= df["date_val"].dt.dayofweek.astype("int16")
    df["est_weekend"] = df["jour_semaine"].apply(lambda d: 1 if d >= 5 else 0).astype("int16")
    df["est_ferie"]   = 0
    df["exercice"]    = df["annee"]
    return df



def add_fact_reglements_calcs(df):
    """Calcule le délai de paiement réel en jours et le bucket impayé.

    - `delai_reel_jours` : différence en jours entre date de paiement et date
        initiale du document
    - `ecart_delai` : écart entre `delai_reel_jours` et `RT_NbJour` (contrat)
    - `bucket_impaye` : découpage en classes d'ancienneté des impayés
        (0: 0-30j, 1:31-60j, 2:61-90j, 3:>90j)
    """
    df = df.copy()
    df["RT_Date"]         = pd.to_datetime(df["RT_Date"], errors="coerce")
    df["DO_Date"]         = pd.to_datetime(df["DO_Date"], errors="coerce")
    df["RT_NbJour"]       = pd.to_numeric(df["RT_NbJour"], errors="coerce").fillna(0)
    df["delai_reel_jours"]= (df["RT_Date"] - df["DO_Date"]).dt.days
    df["ecart_delai"]     = df["delai_reel_jours"] - df["RT_NbJour"]
    
    if "LB_EcheanceReg" in df.columns:
        echeance = pd.to_datetime(df["LB_EcheanceReg"], errors="coerce")
        today = pd.Timestamp.now()
        days_overdue = (today - echeance).dt.days
        bucket = pd.cut(
            days_overdue,
            bins=[-float("inf"), 30, 60, 90, float("inf")],
            labels=[0, 1, 2, 3]
        )
        df["bucket_impaye"] = bucket
    else:
        df["bucket_impaye"] = None
        
    return df
