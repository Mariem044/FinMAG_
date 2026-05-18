from __future__ import annotations

import hashlib
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

warnings.filterwarnings(
    "ignore",
    message="The behavior of DataFrame concatenation with empty or all-NA entries",
    category=FutureWarning,
)

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl.config import (
    DW_ENGINE,
    DIM_DATE_START,
    DIM_DATE_END,
    AUDIT_TABLE_NAME,
    JO_TYPE_TO_TVA_MAPPING,
    RT_ETAT_SOLDE,
)
from etl.utils.logger import get_logger
from etl.utils.audit import (
    start_run, end_run, release_lock,
    table_timer, get_last_run_info,
)

from etl import ddl, extract, transform, load

logger = get_logger(__name__)


@dataclass
class PipelineStep:
    """
    Describes one ETL step in the pipeline.

    Attributes
    ----------
    table_name   : target DW table name
    extract_fn   : callable(**kw) -> DataFrame drawn from source systems
    transform_fn : optional callable(DataFrame, lookups) -> DataFrame
    load_fn      : callable(DataFrame, table_name, mode) -> None
    description  : plain-language description of what this step computes
                   (shown in log output and useful for professor review)
    """
    table_name:   str
    extract_fn:   Callable
    transform_fn: Optional[Callable]
    load_fn:      Callable
    description:  str


# KPI18_MIGRATION has been moved to ddl.py (_MIGRATIONS list).
# It runs as part of ddl.apply_schema_migrations() and is no longer
# managed here to avoid duplication.

def _compute_thresholds() -> dict:
    sql = """
        SELECT
            (SELECT AVG(cycle) FROM (
                SELECT DATEDIFF(DAY, MIN(d.date_val), MAX(d.date_val)) AS cycle
                FROM FAIT_LIGNES_VENTE v
                JOIN DIM_DATE d ON d.id_date = v.id_date
                JOIN DIM_DOMAINE dom ON dom.id_domaine = v.id_domaine
                WHERE dom.DO_Domaine = 0
                GROUP BY v.id_client
                HAVING COUNT(DISTINCT d.date_val) > 1
            ) cycles) AS avg_purchase_cycle,

            (SELECT TOP 1 delai_reel_jours FROM (
                SELECT delai_reel_jours,
                       NTILE(10) OVER (ORDER BY delai_reel_jours) AS tile
                FROM FAIT_REGLEMENTS WHERE delai_reel_jours > 0 AND DR_Regle = 0
            ) t WHERE tile = 5 ORDER BY delai_reel_jours DESC) AS p50_delay,

            (SELECT AVG(CAST(ratio AS FLOAT)) FROM (
                SELECT CAST(AS_QteRes AS FLOAT) / NULLIF(AS_QteSto, 0) AS ratio
                FROM FAIT_ECRITURES fe
                JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
                WHERE tl.type_ligne = 4
                AND AS_QteRes IS NOT NULL AND AS_QteSto > 0
            ) r) AS avg_tension_ratio
        FROM (SELECT 1 AS x) dummy
    """
    with DW_ENGINE.connect() as conn:
        row = conn.execute(text(sql)).fetchone()

    avg_cycle  = int(row.avg_purchase_cycle) if row.avg_purchase_cycle else 365
    p50_delay  = int(row.p50_delay)          if row.p50_delay          else 5
    avg_tension = float(row.avg_tension_ratio) if row.avg_tension_ratio else 0.2

    return {
        "fenetre_dsi":          avg_cycle,
        "buckets_impaye":       [0, p50_delay, p50_delay * 6, p50_delay * 18],
        "seuil_tension_stock":  avg_tension * 2.5,
    }

def _safe_int16(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    return s.astype(object).where(s.notna(), other=None).astype("Int16")


def _build_lookup(table_name: str, natural_hash_col: str, surrogate_id_col: str) -> Dict:
    query = (
        f"SELECT [{surrogate_id_col}] AS sid, [{natural_hash_col}] AS nhash "
        f"FROM [{table_name}]"
    )
    df = pd.read_sql(query, DW_ENGINE)
    if table_name == "DIM_DATE" and not df.empty:
        df["nhash"] = pd.to_datetime(df["nhash"]).dt.date
    lookup = dict(zip(df["nhash"], df["sid"]))
    logger.debug(f"Lookup built for {table_name}: {len(lookup)} rows")
    return lookup


def _get_lookup_config() -> Dict[str, Tuple[str, str]]:
    sql = "SELECT table_name, natural_col, surrogate_col FROM ETL_LOOKUP_CONFIG"
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    return {
        row["table_name"]: (row["natural_col"], row["surrogate_col"])
        for _, row in df.iterrows()
    }

# PipelineStep is defined at the top of this module as a @dataclass.


def _hash_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    df = df.copy()
    for col in cols:
        df[f"{col}_code"] = df[col].apply(transform.hash_key)
    return df


def _source_hash(*values) -> bytes:
    parts = ["<NULL>" if pd.isna(v) else str(v).strip() for v in values]
    return hashlib.sha256("|".join(parts).encode("utf-8")).digest()


def _ensure_columns(df: pd.DataFrame, defaults: Dict) -> pd.DataFrame:
    df = df.copy()
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default
    return df


def _lookup_code(lookups: Dict, table_name: str, value):
    if pd.isna(value):
        return None
    return lookups.get(table_name, {}).get(value)


def _resolve_today_id(lookups: Dict, today: date) -> Optional[int]:
    if not lookups.get("DIM_DATE"):
        lookups["DIM_DATE"] = _build_lookup("DIM_DATE", "date_val", "id_date")
    date_lookup = lookups.get("DIM_DATE", {})
    id_val = date_lookup.get(today)
    if id_val is not None:
        return id_val
    date_lookup_keys = [k for k in date_lookup.keys() if k is not None]
    if date_lookup_keys:
        max_date = max(date_lookup_keys)
        if max_date >= today:
            id_val = date_lookup[max_date]
            logger.warning(
                f"Today ({today}) not in DIM_DATE — fallback to {max_date} "
                f"(id_date={id_val}). Consider extending DIM_DATE_END."
            )
            return id_val
    logger.warning(
        f"Today ({today}) beyond DIM_DATE range — stock snapshot id_date will be NULL"
    )
    return None


_PIPELINE_THRESHOLDS: list[int] = []

def _bucket_from_echeance(row) -> Optional[int]:
    if row.get("DR_Regle", 1) != 0:
        return None
    echeance = row.get("LB_EcheanceReg")
    if echeance is None or pd.isna(echeance):
        return None
    try:
        today = datetime.now(timezone.utc).date()
        days_overdue = (today - pd.Timestamp(echeance).date()).days
    except Exception:
        return None
    if days_overdue <= 0:
        return None
    seuils = _PIPELINE_THRESHOLDS[1:]
    for i, seuil in enumerate(seuils):
        if days_overdue <= seuil:
            return i
    return len(seuils)


def _transform_dim_famille(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[
            "FA_CodeFamille_code", "FA_Intitule",
            "niveau_0_code", "niveau_1_code", "niveau_2_code",
        ])
    df = df.copy()
    df["FA_CodeFamille_code"] = df["FA_CodeFamille"].apply(transform.hash_key)
    df["FA_Intitule"]         = df["FA_Intitule"].fillna("").astype(str).str.strip().str[:100]
    df["niveau_0_code"]       = df["CL_No1"].apply(transform.hash_key)
    df["niveau_1_code"]       = df["CL_No2"].apply(transform.hash_key)
    df["niveau_2_code"]       = df["CL_No3"].apply(transform.hash_key)
    return df[[
        "FA_CodeFamille_code", "FA_Intitule",
        "niveau_0_code", "niveau_1_code", "niveau_2_code",
    ]]


def _transform_dim_segment(df: pd.DataFrame) -> pd.DataFrame:
    df = _hash_columns(df, ["cbIndice"])
    df["CT_PrixTTC"] = pd.to_numeric(df["CT_PrixTTC"], errors="coerce").fillna(0).astype("Int16")
    
    try:
        sql = "SELECT cbIndice, libelle_segment FROM REF_SEGMENTS_MAPPING"
        with DW_ENGINE.connect() as conn:
            ref_df = pd.read_sql(text(sql), conn)
        ref_map = dict(zip(ref_df["cbIndice"], ref_df["libelle_segment"]))
    except Exception as exc:
        logger.warning(f"REF_SEGMENTS_MAPPING not available: {exc}")
        ref_map = {}

    df["libelle_segment"] = (
        df["cbIndice"]
        .map(lambda v: ref_map.get(int(v), f"Segment {v}"))
        .str[:100]
    )
    return df


def _add_static_label(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "code_type_mvt" in df.columns and "MC_TypeMvt" not in df.columns:
        df = df.rename(columns={"code_type_mvt": "MC_TypeMvt"})
    df["MC_TypeMvt"] = pd.to_numeric(df["MC_TypeMvt"], errors="coerce").astype("Int16")
    
    try:
        sql = "SELECT MC_TypeMvt, libelle_type_mvt FROM REF_TYPES_MVT_CAISSE_MAPPING"
        with DW_ENGINE.connect() as conn:
            ref_df = pd.read_sql(text(sql), conn)
        ref_map = dict(zip(ref_df["MC_TypeMvt"], ref_df["libelle_type_mvt"]))
    except Exception as exc:
        logger.warning(f"REF_TYPES_MVT_CAISSE_MAPPING not available: {exc}")
        ref_map = {}

    df["libelle_type_mvt"] = df["MC_TypeMvt"].map(
        lambda v: ref_map.get(int(v), f"Type caisse {int(v)}") if pd.notna(v) else None
    )
    return df


def _resolve_gouvernorat_sql(df: pd.DataFrame) -> pd.Series:
    """
    Resolve gouvernorat labels for all clients via a SQL JOIN on
    REF_GOUVERNORAT_MAPPING instead of the 400-line Python dict.

    Falls back to 'Autre' for unmatched codes. The reference table is
    populated once during schema migration (migrations/005_ref_gouvernorat.sql)
    and maintained by the DBA/analyst in SSMS.
    """
    if "CT_CodeRegion" not in df.columns:
        return pd.Series("Autre", index=df.index)

    # Build a temporary mapping from the DW reference table
    try:
        gov_sql = """
            SELECT CT_CodeRegion, gouvernorat
            FROM REF_GOUVERNORAT_MAPPING
        """
        with DW_ENGINE.connect() as conn:
            gov_df = pd.read_sql(text(gov_sql), conn)
        gov_map = dict(zip(
            gov_df["CT_CodeRegion"].str.strip().str.upper(),
            gov_df["gouvernorat"],
        ))
    except Exception as exc:
        logger.warning(
            f"[DIM_CLIENT] REF_GOUVERNORAT_MAPPING not available ({exc}); "
            "run migrations/005_ref_gouvernorat.sql in SSMS first. "
            "Defaulting all gouvernorat to 'Autre'."
        )
        return pd.Series("Autre", index=df.index)

    return (
        df["CT_CodeRegion"]
        .fillna("")
        .str.strip()
        .str.upper()
        .map(gov_map)
        .fillna("Autre")
    )


# ── kept for reference only — business logic is now in REF_GOUVERNORAT_MAPPING





@lru_cache(maxsize=1)
def _famille_label_lookup() -> Dict:
    df = extract.extract_dim_famille()
    if df.empty or "FA_CodeFamille" not in df.columns:
        return {}
    return {
        int(transform.hash_key(v)): lbl
        for v, lbl in zip(
            df["FA_CodeFamille"],
            df["FA_Intitule"].fillna("").astype(str).str.strip().str[:100],
        )
        if v is not None and transform.hash_key(v) is not None
    }


def _generate_dim_date(
    start: str = DIM_DATE_START,
    end:   str = DIM_DATE_END,
) -> pd.DataFrame:
    exercices = extract.extract_exercices_fiscaux()
    dr = pd.date_range(start=start, end=end, freq="D")

    df = pd.DataFrame({
        "date_val":     pd.Series(dr).dt.date,
        "annee":        dr.year.astype("int16"),
        "mois":         dr.month.astype("int16"),
        "jour":         dr.day.astype("int16"),
        "trimestre":    dr.quarter.astype("int16"),
        "semestre":     ((dr.month - 1) // 6 + 1).astype("int16"),
        "semaine":      dr.isocalendar().week.values.astype("int32"),
        "jour_semaine": (dr.weekday + 1).astype("int16"),
        "est_weekend":  (dr.weekday >= 5).astype("int16"),
        "est_ferie":    0,
    })

    def _get_exercice(d) -> Optional[int]:
        for i, (debut, fin) in enumerate(exercices, 1):
            if debut <= d <= fin:
                return i
        return None

    df["exercice"] = df["date_val"].apply(_get_exercice)
    return df


def _resolve_banque_id(row: pd.Series, lookups: Dict):
    banque_lookup = lookups.get("DIM_BANQUE", {})
    for col in ("BQ_ABREGE", "BQ_Num"):
        value = row.get(col)
        if pd.notna(value):
            resolved = banque_lookup.get(transform.hash_key(str(value)))
            if resolved is not None:
                return resolved
    return None


def _assemble_fait_reglements(
    last_run: Optional[datetime],
    lookups:  Dict,
) -> pd.DataFrame:
    defaults = {
        "DO_Piece":          None,
        "LB_Ligne":          None,
        "LB_NbJour":         0,
        "LB_Agios":          0,
        "BR_Rapproch":       0,
        "BR_TauxAgios":      None,
        "BR_TMM":            None,
        "BQ_ABREGE":         None,
        "LB_MontantReg":     None,
        "RG_Montant":        None,
        "RC_Montant":        None,
        "BR_TotalReglement": None,
        "LB_EcheanceReg":    None,
        "N_Reglement":       None,
        "DR_Regle":          None,
        "DR_Montant":        None,
        "DR_ModeReg":        None,
    }

    clients      = _ensure_columns(extract.extract_fait_reglements_clients(last_run), defaults)
    clients["_acteur"] = "CLIENT"

    fournisseurs = _ensure_columns(extract.extract_fait_reglements_fournisseurs(last_run), defaults)
    fournisseurs["_acteur"] = "FOURNISSEUR"

    doc_dates = (
        extract.extract_docentete_dates()[["DO_Type", "DO_Piece", "DO_Date"]]
        .drop_duplicates(subset=["DO_Type", "DO_Piece"], keep="last")
    )

    _docregl_raw = extract.extract_docregl_grt(last_run)
    if _docregl_raw.empty or "DO_Piece" not in _docregl_raw.columns:
        docregl = pd.DataFrame(columns=["DO_Piece", "DR_Montant", "DR_Regle", "DR_ModeReg"])
    else:
        docregl = _docregl_raw.drop_duplicates(subset=["DO_Piece"], keep="last")

    _reglementt_raw = extract.extract_reglementt()
    if _reglementt_raw.empty or "CT_Num" not in _reglementt_raw.columns:
        reglementt = pd.DataFrame(columns=["CT_Num", "N_Reglement", "RT_NbJour_contrat"])
    else:
        reglementt = (
            _reglementt_raw[["CT_Num", "N_Reglement", "RT_NbJour"]]
            .rename(columns={"RT_NbJour": "RT_NbJour_contrat"})
        )

    df = (
        pd.concat([clients, fournisseurs], ignore_index=True, sort=False)
        .merge(doc_dates,    on=["DO_Type", "DO_Piece"], how="left")
        .merge(docregl,      on="DO_Piece",              how="left")
        .assign(N_Reglement=lambda d: pd.to_numeric(d["N_Reglement"], errors="coerce"))
        .merge(reglementt,   on=["CT_Num", "N_Reglement"], how="left")
        .assign(RT_NbJour=lambda d: d["RT_NbJour_contrat"])
    )

    # Derive DR_Regle from RT_Etat when docregl join yields NULL
    if "RT_Etat" in df.columns:
        df["DR_Regle"] = df.apply(
            lambda row: (1 if row.get("RT_Etat") == 2 else 0)
            if pd.isna(row.get("DR_Regle")) else row.get("DR_Regle"),
            axis=1,
        )

    for _col, _default in {
        "DR_Regle":          None,
        "DR_Montant":        None,
        "DR_ModeReg":        None,
        "RT_Rapproche":      None,
        "BR_Rapproch":       None,
        "RC_Montant":        None,
        "RG_Montant":        None,
        "DO_Date":           None,
        "RT_NbJour_contrat": None,
        "RT_NbJour":         None,
    }.items():
        if _col not in df.columns:
            df[_col] = _default

    df = transform.add_fact_reglements_calcs(df)
    df["bucket_impaye"] = df.apply(_bucket_from_echeance, axis=1)
    df = transform.add_fact_reglements_banking_fees(df)

    rapproche = (
        pd.to_numeric(df["RT_Rapproche"], errors="coerce")
        .combine_first(pd.to_numeric(df["BR_Rapproch"], errors="coerce"))
        .combine_first(
            pd.to_numeric(df.get("DR_Regle", pd.Series(dtype=float)), errors="coerce")
            .apply(lambda v: 1 if v == 1 else None)
        )
        .fillna(0)
        .clip(lower=0, upper=1)
    )

    return df.assign(
        id_date_paiement=lambda d: d["RT_Date"].apply(
            lambda dt: lookups.get("DIM_DATE", {}).get(
                pd.Timestamp(dt).date() if pd.notna(dt) else None
            )
        ),
        id_date_echeance=lambda d: d["LB_EcheanceReg"].apply(
            lambda dt: lookups.get("DIM_DATE", {}).get(
                pd.Timestamp(dt).date() if pd.notna(dt) else None
            )
        ),
        id_client=lambda d: d.apply(
            lambda row: (
                lookups.get("DIM_CLIENT", {}).get(
                    transform.hash_key(row.get("CT_Num"))
                )
                if row.get("_acteur") == "CLIENT" else None
            ),
            axis=1,
        ),
        id_fournisseur=lambda d: d.apply(
            lambda row: (
                lookups.get("DIM_FOURNISSEUR", {}).get(
                    transform.hash_key(row.get("CT_Num"))
                )
                if row.get("_acteur") == "FOURNISSEUR" else None
            ),
            axis=1,
        ),
        id_banque=lambda d: d.apply(
            lambda row: _resolve_banque_id(row, lookups), axis=1
        ),
        id_mode_reg=lambda d:     d["RT_Mode"].map(lookups.get("DIM_MODE_REGLEMENT", {})),
        id_etat_reg=lambda d:     d["RT_Etat"].map(lookups.get("DIM_ETAT_REGLEMENT", {})),
        id_etat_docregl=lambda d: d["DR_Regle"].map(lookups.get("DIM_ETAT_DOCREGL", {})),
        id_type_doc=lambda d: d["DO_Type"].apply(
            lambda v: _lookup_code(lookups, "DIM_TYPE_DOC", v)
        ),
        BR_Rapproch=lambda d: pd.to_numeric(d["BR_Rapproch"], errors="coerce").astype("Int16"),
        RT_Rapproche=rapproche.astype("Int16"),
        RT_Num=lambda d: d["RT_Num"].astype(str).where(d["RT_Num"].notna(), other=None),
        source_hash=lambda d: d.apply(
            lambda row: _source_hash(
                "REGLEMENT",
                row.get("_acteur"),
                row.get("CT_Num"),
                row.get("RT_Num"),
                row.get("LB_Ligne"),
                row.get("DO_Piece"),
            ),
            axis=1,
        ),
        date_extraction=datetime.now(timezone.utc).date(),
    ).drop_duplicates(subset=["source_hash"], keep="last")


def _assemble_dim_caisse(lookups: Dict) -> pd.DataFrame:
    df_mag = extract.extract_dim_caisse_mag().copy()
    df_mag["_source_priority"] = 1

    df_grt_raw = (
        extract.extract_fait_mvtcaisse(last_run=None)
        [["CA_No", "JO_Num"]]
        .drop_duplicates(subset=["CA_No"])
        .copy()
    )
    df_grt_raw["_source_priority"] = 2

    all_cols = list(df_mag.columns)
    for col in all_cols:
        if col not in df_grt_raw.columns:
            df_grt_raw[col] = pd.NA

    df = (
        pd.concat([df_mag, df_grt_raw], ignore_index=True, sort=False)
        .sort_values("_source_priority")
        .assign(
            CA_Numero_code=lambda d: d["CA_No"].apply(transform.hash_key),
            id_journal=lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
            ),
            CA_Type=lambda d: (
                pd.to_numeric(
                    d["CA_Type"] if "CA_Type" in d.columns
                    else pd.Series([None] * len(d), index=d.index),
                    errors="coerce",
                )
                .pipe(lambda s: s.astype(object).where(s.notna(), other=None))
                .astype("Int16")
            ),
        )
        .drop_duplicates(subset=["CA_Numero_code"], keep="first")
        .drop(columns=["_source_priority"], errors="ignore")
    )
    return df


def _assemble_dim_banque(lookups: Dict) -> pd.DataFrame:
    df_mag = extract.extract_dim_banque_mag().copy()
    df_grt = extract.extract_dim_banque_grt().copy()

    df_mag["source"] = 1
    df_grt["source"] = 2

    return (
        pd.concat([df_mag, df_grt], ignore_index=True)
        .assign(
            EB_Abrege_code=lambda d: d["EB_Abrege"].apply(transform.hash_key),
            EB_Banque=lambda d: pd.to_numeric(d["EB_Banque"], errors="coerce").astype("Int64"),
        )
        .drop_duplicates(subset=["EB_Abrege_code"], keep="first")
    )


# ---------------------------------------------------------------------------
# FIX 1: _normalize_ecriturec — explicit float64 cast + whitespace stripping
# This prevents Decimal/object columns from becoming NaN/0 after to_numeric.
# ---------------------------------------------------------------------------
def _normalize_ecriturec(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    df = _ensure_columns(df, {
        "JO_Num": None,
        "EC_No": None,
        "EC_Date": None,
        "CG_Num": None,
        "CT_Num": None,
        "EC_Sens": None,
        "EC_Montant": None,
        "JO_Type": None,
    })
    if df.empty:
        logger.warning("FAIT_ECRITURES: %s extraction returned 0 rows", source_name)
    df["EC_No"] = pd.to_numeric(df["EC_No"], errors="coerce").astype("Int64")
    df["EC_Date"] = pd.to_datetime(df["EC_Date"], errors="coerce")
    df["CG_Num"] = pd.to_numeric(df["CG_Num"], errors="coerce").astype("Int64")
    df["EC_Sens"] = pd.to_numeric(df["EC_Sens"], errors="coerce").astype("Int16")

    # FIX: strip formatting characters (spaces, non-breaking spaces, commas)
    # before numeric conversion — Sage sometimes returns amounts as formatted strings
    ec_montant_raw = df["EC_Montant"]
    if ec_montant_raw.dtype == object:
        ec_montant_raw = (
            ec_montant_raw
            .astype(str)
            .str.replace(r"[\s\u00a0\xa0,]", "", regex=True)
            .replace("None", pd.NA)
            .replace("nan", pd.NA)
        )
    df["EC_Montant"] = pd.to_numeric(ec_montant_raw, errors="coerce").astype("float64")

    return df


def _assemble_fait_ecritures(
    last_run: Optional[datetime],
    lookups:  Dict,
) -> pd.DataFrame:
    today    = datetime.now(timezone.utc).date()
    today_id = _resolve_today_id(lookups, today)

    def _resolve_date(d):
        if pd.isna(d):
            return None
        try:
            return lookups.get("DIM_DATE", {}).get(pd.Timestamp(d).date())
        except Exception:
            return None
    df1 = (
        _normalize_ecriturec(extract.extract_fait_ecriturec(last_run), "F_ECRITUREC")
        .assign(
            type_ligne   =1,
            id_type_ligne=lambda d: d.apply(lambda _: _lookup_code(lookups, "DIM_TYPE_LIGNE", 1), axis=1),
            id_date      =lambda d: d["EC_Date"].apply(_resolve_date),
            id_journal   =lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
            ),
            id_banque=pd.NA,
            id_client=lambda d: d["CT_Num"].apply(
                lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
            ),
            id_sens_ecriture=lambda d: d["EC_Sens"].apply(
                lambda v: lookups["DIM_SENS_ECRITURE"].get(v)
            ),
            id_type_tva=lambda d: d["JO_Type"].apply(
                lambda v: _lookup_code(
                    lookups, "DIM_TYPE_TVA",
                    JO_TYPE_TO_TVA_MAPPING.get(v),
                )
            ),
            source_hash=lambda d: d.apply(
                lambda row: _source_hash(
                    "ECRITUREC", row.get("JO_Num"), row.get("EC_No"),
                    row.get("EC_Date"), row.get("CG_Num"), row.get("CT_Num"),
                    row.get("EC_Sens"), row.get("EC_Montant"),
                ),
                axis=1,
            ),
            date_extraction=today,
        )
    )


    df2 = (
        _normalize_ecriturec(extract.extract_fait_regtaxe(last_run), "F_REGTAXE")
        .assign(
            type_ligne   =2,
            id_type_ligne=lambda d: d.apply(lambda _: _lookup_code(lookups, "DIM_TYPE_LIGNE", 2), axis=1),
            id_date      =lambda d: d["EC_Date"].apply(_resolve_date),
            id_journal   =lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
            ),
            id_banque    =None,
            id_client=lambda d: d["CT_Num"].apply(
                lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
            ),
            id_type_tva=lambda d: d["JO_Type"].apply(
                lambda v: _lookup_code(
                    lookups, "DIM_TYPE_TVA",
                    JO_TYPE_TO_TVA_MAPPING.get(v),
                )
            ),
            source_hash=lambda d: d.apply(
                lambda row: _source_hash(
                    "REGTAXE", row.get("JO_Num"), row.get("EC_No"),
                    row.get("EC_Date"), row.get("TA_Taux01"),
                    row.get("RT_Base01"), row.get("RT_Montant01"),
                ),
                axis=1,
            ),
            date_extraction=today,
        )
    )

    df3 = (
        extract.extract_fait_mvtcaisse(last_run)
        .assign(
            type_ligne   =3,
            id_type_ligne=lambda d: d.apply(lambda _: _lookup_code(lookups, "DIM_TYPE_LIGNE", 3), axis=1),
            id_date      =lambda d: d["MC_Date"].apply(_resolve_date),
            id_journal   =lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
            ),
            id_banque    =None,
            id_caisse=lambda d: d["CA_No"].apply(
                lambda v: lookups.get("DIM_CAISSE", {}).get(transform.hash_key(v))
            ),
            id_type_mvt_caisse=lambda d: d["MC_TypeMvt"].apply(
                lambda v: lookups["DIM_TYPE_MVT_CAISSE"].get(v)
            ),
            source_hash=lambda d: d.apply(
                lambda row: _source_hash(
                    "MVTCaisse", row.get("CA_No"), row.get("MC_Numero"),
                    row.get("MC_Date"), row.get("MC_TypeMvt"),
                    row.get("MC_Debit"), row.get("MC_Credit"),
                ),
                axis=1,
            ),
            date_extraction=today,
        )
        .rename(columns={"MC_Date": "EC_Date"})
    )

    # ---------------------------------------------------------------------------
    # FIX 3: artstock — ensure typed empty df + explicit numeric casts so
    # add_fact_ecritures_calcs never KeyErrors on an empty/untyped DataFrame.
    # ---------------------------------------------------------------------------
    artstock = extract.extract_fait_artstock()
    if artstock.empty:
        logger.warning(
            "FAIT_ECRITURES: F_ARTSTOCK returned 0 rows — "
            "check that F_ARTSTOCK is accessible on MAG_ENGINE and "
            "that AR_SuiviStock>0 articles exist. Stock KPIs will be empty."
        )
        artstock = pd.DataFrame(columns=[
            "AR_Ref", "DE_No", "AS_MontSto", "AS_QteSto", "AS_QteMini", "AS_QteRes",
        ])

    df4 = (
        artstock
        .assign(
            # Explicit numeric coercion before calcs — avoids silent 0s from object dtype
            AS_QteSto  =lambda d: pd.to_numeric(d["AS_QteSto"],  errors="coerce"),
            AS_QteRes  =lambda d: pd.to_numeric(d["AS_QteRes"],  errors="coerce"),
            AS_QteMini =lambda d: pd.to_numeric(d["AS_QteMini"], errors="coerce"),
            AS_MontSto =lambda d: pd.to_numeric(d["AS_MontSto"], errors="coerce"),
            type_ligne   =4,
            id_type_ligne=lambda d: d.apply(lambda _: _lookup_code(lookups, "DIM_TYPE_LIGNE", 4), axis=1),
            id_date      =today_id,
            id_journal   =None,
            id_banque    =None,
            id_client    =None,
            id_sens_ecriture =None,
            id_type_mvt_caisse =None,
            id_type_tva  =None,
            id_caisse    =None,
            id_article   =lambda d: d["AR_Ref"].apply(
                lambda v: lookups.get("DIM_ARTICLE", {}).get(transform.hash_key(str(v).strip())) if pd.notna(v) else None
            ),
            id_depot=lambda d: d["DE_No"].apply(
                lambda v: lookups.get("DIM_DEPOT", {}).get(int(v)) if pd.notna(v) else None
            ),
            source_hash=lambda d: d.apply(
                lambda row: _source_hash("ARTSTOCK", row.get("AR_Ref"), row.get("DE_No")),
                axis=1,
            ),
            date_extraction=today,
        )
    )
    # df4 = transform.add_fact_ecritures_calcs(df4) # Moved to SQL post-load

    _all_cols = list(dict.fromkeys(
        list(df1.columns) + list(df2.columns) +
        list(df3.columns) + list(df4.columns)
    ))
    for _sub in (df1, df2, df3, df4):
        for _col in _all_cols:
            if _col not in _sub.columns:
                _sub[_col] = None

    df = pd.concat([df1, df2, df3, df4], ignore_index=True)

    if "source_hash" not in df.columns:
        df["source_hash"] = None
    if "date_extraction" not in df.columns:
        df["date_extraction"] = datetime.now(timezone.utc).date()

    before = len(df)
    df = df.drop_duplicates(subset=["source_hash"], keep="last")
    if len(df) != before:
        logger.warning(f"FAIT_ECRITURES: dropped {before - len(df)} duplicate source_hash rows")

    numeric_cols = [
        "EC_Montant", "TA_Taux01", "RT_Base01", "RT_Montant01", 
        "AS_MontSto", "AS_QteSto", "AS_QteMini", "AS_QteRes", 
        "qte_disponible", "ratio_tension", "MC_Debit", "MC_Credit", 
        "MC_Cloture", "CA_Solde", "CA_SoldeEspece", "CA_SoldeCheque"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.replace({pd.NA: None})

    return df


def _compute_dsi_jours(thresholds: dict) -> None:
    sql = """
        UPDATE fe
        SET
            fe.qte_vendue_365j = sub.qte_vendue,
            fe.dsi_jours = CASE
                WHEN sub.qte_vendue > 0
                THEN fe.AS_QteSto / (sub.qte_vendue / CAST(:fenetre AS FLOAT))
                ELSE NULL
            END
        FROM FAIT_ECRITURES fe
        INNER JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
        INNER JOIN (
            SELECT flv.id_article, SUM(flv.DL_Qte) AS qte_vendue
            FROM FAIT_LIGNES_VENTE flv
            JOIN DIM_DATE d ON d.id_date = flv.id_date
            JOIN DIM_DOMAINE dom ON dom.id_domaine = flv.id_domaine
            WHERE d.date_val >= DATEADD(DAY, -:fenetre, CAST(GETDATE() AS DATE))
              AND dom.DO_Domaine = 0
            GROUP BY flv.id_article
        ) sub ON sub.id_article = fe.id_article
        WHERE tl.type_ligne = 4
    """
    with DW_ENGINE.begin() as conn:
        conn.execute(text("SET NOCOUNT OFF"))
        result = conn.execute(text(sql), {"fenetre": thresholds["fenetre_dsi"]})
        rowcount = result.rowcount if result.rowcount >= 0 else "unknown"
        logger.info(f"dsi_jours computed: {rowcount} stock rows updated (window={thresholds['fenetre_dsi']} days).")


def _compute_stock_kpis() -> None:
    sql = """
        UPDATE fe
        SET
            fe.qte_disponible = fe.AS_QteSto - fe.AS_QteRes,
            fe.ratio_tension = CASE 
                WHEN (fe.AS_QteSto - fe.AS_QteRes) > 0 AND fe.AS_QteRes >= 0 
                THEN CASE 
                    WHEN CAST(fe.AS_QteRes AS FLOAT) / (fe.AS_QteSto - fe.AS_QteRes) > 1 THEN 1.0
                    WHEN CAST(fe.AS_QteRes AS FLOAT) / (fe.AS_QteSto - fe.AS_QteRes) < 0 THEN 0.0
                    ELSE CAST(fe.AS_QteRes AS FLOAT) / (fe.AS_QteSto - fe.AS_QteRes)
                END
                ELSE NULL 
            END,
            fe.en_rupture = CASE 
                WHEN fe.AS_QteSto <= fe.AS_QteMini 
                     AND fe.AS_QteSto IS NOT NULL 
                     AND fe.AS_QteMini IS NOT NULL 
                THEN 1 
                ELSE 0 
            END
        FROM FAIT_ECRITURES fe
        INNER JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
        WHERE tl.type_ligne = 4
    """
    with DW_ENGINE.begin() as conn:
        conn.execute(text("SET NOCOUNT OFF"))
        result = conn.execute(text(sql))
        rowcount = result.rowcount if result.rowcount >= 0 else "unknown"
        logger.info(f"Stock KPIs computed: {rowcount} rows updated.")




def _load_dim_date(df: pd.DataFrame, table: str, mode: str) -> None:
    # Force pandas to use DATETIME in SQL instead of VARCHAR(MAX) for python date objects
    if "date_val" in df.columns:
        df["date_val"] = pd.to_datetime(df["date_val"])
        
    if mode == "full":
        load.load_dimension(df, table, "full", key_col="date_val")
    else:
        load.load_dimension(df, table, "delta", key_col="date_val")


def _build_lignes_vente_transform(last_run_date):
    def _transform(df_vente: pd.DataFrame, lookups: Dict) -> pd.DataFrame:
        df_raw = df_vente

        return (
            transform.add_fact_lignes_vente_calcs(df_raw)
            .assign(
                id_date=lambda d: d["DO_Date"].apply(
                    lambda dt: lookups.get("DIM_DATE", {}).get(
                        pd.Timestamp(dt).date() if pd.notna(dt) else None
                    )
                ),
                id_type_doc=lambda d: d["DO_Type"].apply(
                    lambda v: _lookup_code(lookups, "DIM_TYPE_DOC", v)
                ),
                id_domaine=lambda d: d["DO_Domaine"].apply(
                    lambda v: _lookup_code(lookups, "DIM_DOMAINE", v)
                ),
                id_client=lambda d: d["CT_Num"].apply(
                    lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
                ),
                id_article=lambda d: d["AR_Ref"].apply(
                    lambda v: lookups.get("DIM_ARTICLE", {}).get(transform.hash_key(v))
                ),
                source_hash=lambda d: d.apply(
                    lambda row: _source_hash(
                        "DOCLIGNE", row.get("DO_Domaine"), row.get("DO_Type"),
                        row.get("DO_Piece"), row.get("DL_Ligne"), row.get("AR_Ref")
                    ),
                    axis=1,
                ),
                date_extraction=datetime.now(timezone.utc).date(),
        )
    )
    return _transform

STEPS: List[PipelineStep] = [
    PipelineStep(
        table_name="DIM_DATE",
        extract_fn=lambda **kw: pd.DataFrame(),
        transform_fn=None,
        load_fn=lambda df, tbl, mode: _load_dim_date(df, tbl, mode),
        description="Génère la dimension calendaire de DIM_DATE_START à DIM_DATE_END.",
    ),
    PipelineStep(
        table_name="DIM_DOMAINE",
        extract_fn=lambda **kw: extract.extract_static_dims()["DIM_DOMAINE"],
        transform_fn=None,
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DO_Domaine"),
        description="Charge les domaines Sage (Vente=0, Achat=1, Stock=2, Interne=3).",
    ),
    PipelineStep(
        table_name="DIM_TYPE_DOC",
        extract_fn=lambda **kw: extract.extract_static_dims()["DIM_TYPE_DOC"],
        transform_fn=None,
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DO_Type"),
        description="Charge les types de document Sage (Facture, BL, Avoir, …).",
    ),
    PipelineStep(
        table_name="DIM_MODE_REGLEMENT",
        extract_fn=lambda **kw: extract.extract_static_dims()["DIM_MODE_REGLEMENT"],
        transform_fn=None,
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="RT_Mode"),
        description="Modes de règlement : Espèces, Chèque, Virement, Traite, …",
    ),
    PipelineStep(
        table_name="DIM_ETAT_REGLEMENT",
        extract_fn=lambda **kw: extract.extract_static_dims()["DIM_ETAT_REGLEMENT"],
        transform_fn=None,
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="RT_Etat"),
        description="États de règlement Sage (En cours, Soldé, Payé).",
    ),
    PipelineStep(
        table_name="DIM_ETAT_DOCREGL",
        extract_fn=lambda **kw: extract.extract_static_dims()["DIM_ETAT_DOCREGL"],
        transform_fn=None,
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DR_Regle"),
        description="État de règlement du document (Non réglé=0, Réglé=1).",
    ),
    PipelineStep(
        table_name="DIM_TYPE_LIGNE",
        extract_fn=lambda **kw: extract.extract_static_dims()["DIM_TYPE_LIGNE"],
        transform_fn=None,
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="type_ligne"),
        description="Types de ligne FAIT_ECRITURES (1=Compta, 2=TVA, 3=Caisse, 4=Stock).",
    ),
    PipelineStep(
        table_name="DIM_SENS_ECRITURE",
        extract_fn=lambda **kw: extract.extract_static_dims()["DIM_SENS_ECRITURE"],
        transform_fn=None,
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="EC_Sens"),
        description="Sens de l'écriture comptable (Débit=0, Crédit=1).",
    ),
    PipelineStep(
        table_name="DIM_TYPE_TVA",
        extract_fn=lambda **kw: extract.extract_static_dims()["DIM_TYPE_TVA"],
        transform_fn=None,
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="type_tva"),
        description="Types de TVA (collectée=1, déductible=2).",
    ),
    PipelineStep(
        table_name="DIM_TYPE_MVT_CAISSE",
        extract_fn=lambda **kw: extract.extract_dim_type_mvt_caisse(),
        transform_fn=lambda df, lookups: _add_static_label(df),
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="MC_TypeMvt"),
        description="Types de mouvement caisse Sage (entrées, sorties, remises, …).",
    ),
    PipelineStep(
        table_name="DIM_SEGMENT",
        extract_fn=lambda **kw: extract.extract_dim_segment(),
        transform_fn=lambda df, lookups: _transform_dim_segment(df),
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="cbIndice_code"),
        description="Segments clients Sage (Détaillants, Grossistes, HORECA, Semi-gros, Distributeur).",
    ),
    PipelineStep(
        table_name="DIM_COLLABORATEUR",
        extract_fn=lambda **kw: extract.extract_dim_collaborateur(kw.get("last_run")),
        transform_fn=lambda df, lookups: df.assign(
            CO_Fonction=lambda d: (
                pd.to_numeric(d["CO_Fonction"], errors="coerce")
                .pipe(lambda s: s.astype(object).where(s.notna(), other=None))
                .astype("Int32")
            )
        ),
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CO_No"),
        description="Collaborateurs (commerciaux) issus de F_COLLABORATEUR.",
    ),
    PipelineStep(
        table_name="DIM_JOURNAL",
        extract_fn=lambda **kw: extract.extract_dim_journal(kw.get("last_run")),
        transform_fn=lambda df, lookups: _hash_columns(df, ["JO_Num"]),
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="JO_Num_code"),
        description="Journaux comptables Sage (ventes, achats, banque, caisse, OD).",
    ),
    PipelineStep(
        table_name="DIM_FOURNISSEUR",
        extract_fn=lambda **kw: extract.extract_dim_fournisseur(kw.get("last_run")),
        transform_fn=lambda df, lookups: _hash_columns(df, ["CT_Num"]),
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CT_Num_code"),
        description="Fournisseurs issus du plan comptable tiers Sage (CT_Type=1).",
    ),
    PipelineStep(
        table_name="DIM_BANQUE",
        extract_fn=lambda **kw: pd.DataFrame(),
        transform_fn=lambda df, lookups: _assemble_dim_banque(lookups),
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="EB_Abrege_code"),
        description="Comptes bancaires consolidés depuis MAG_ENGINE et GRT_ENGINE.",
    ),
    PipelineStep(
        table_name="DIM_FAMILLE",
        extract_fn=lambda **kw: extract.extract_dim_famille(),
        transform_fn=lambda df, lookups: _transform_dim_famille(df),
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="FA_CodeFamille_code"),
        description="Familles d'articles Sage sur 3 niveaux hiérarchiques.",
    ),
    PipelineStep(
        table_name="DIM_CLIENT",
        extract_fn=lambda **kw: extract.extract_dim_client_mag(kw.get("last_run")),
        transform_fn=lambda df, lookups: (
            df.copy()
            .merge(extract.extract_dim_client_grt(), on="CT_Num", how="left")
            .pipe(_hash_columns, ["CT_Num"])
            .assign(
                id_segment=lambda d: d["N_CatTarif"].apply(
                    lambda v: lookups.get("DIM_SEGMENT", {}).get(
                        transform.hash_key(int(v))
                        if v is not None and str(v).strip().isdigit()
                        else transform.hash_key(v)
                    )
                ),
                id_collab=lambda d: d["CO_No"].map(lookups.get("DIM_COLLABORATEUR", {})),
                CT_Intitule=lambda d: d["CT_Intitule"].str.strip().str[:100] if "CT_Intitule" in d.columns else None,
                CT_Ville=lambda d: d["CT_Ville"].str.strip().str[:50] if "CT_Ville" in d.columns else None,
                CT_CodeRegion=lambda d: d["CT_CodeRegion"].str.strip().str[:50] if "CT_CodeRegion" in d.columns else None,
            )
            .assign(gouvernorat=lambda d: _resolve_gouvernorat_sql(d))
            .drop_duplicates(subset=["CT_Num_code"], keep="last")
        ),
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CT_Num_code"),
        description="Clients consolidés MAG+GRT. Gouvernorat résolu via REF_GOUVERNORAT_MAPPING.",
    ),
    PipelineStep(
        table_name="DIM_ARTICLE",
        extract_fn=lambda **kw: extract.extract_dim_article(kw.get("last_run")),
        transform_fn=lambda df, lookups: (
            _hash_columns(df, ["AR_Ref", "FA_CodeFamille", "CT_Num_fourn"])
            .assign(
                id_famille=lambda d: d["FA_CodeFamille"].apply(
                    lambda v: lookups.get("DIM_FAMILLE", {}).get(transform.hash_key(v))
                ),
                FA_Intitule=lambda d: d["FA_CodeFamille"].apply(
                    lambda v: (
                        _famille_label_lookup().get(int(transform.hash_key(v)))
                        if v is not None and pd.notna(v) and transform.hash_key(v) is not None
                        else None
                    )
                ),
                id_fournisseur=lambda d: d["CT_Num_fourn"].apply(
                    lambda v: lookups.get("DIM_FOURNISSEUR", {}).get(transform.hash_key(v))
                ),
            )
        ),
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="AR_Ref_code"),
        description="Articles/produits depuis F_ARTICLE. Liés aux familles et fournisseurs.",
    ),
    PipelineStep(
        table_name="DIM_DEPOT",
        extract_fn=lambda **kw: extract.extract_dim_depot(kw.get("last_run")),
        transform_fn=lambda df, lookups: df.copy(),
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DE_No"),
        description="Dépôts de stockage issus de F_DEPOT.",
    ),
    PipelineStep(
        table_name="DIM_CAISSE",
        extract_fn=lambda **kw: pd.DataFrame(),
        transform_fn=lambda df, lookups: _assemble_dim_caisse(lookups),
        load_fn=lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CA_Numero_code"),
        description="Caisses consolidées depuis MAG_ENGINE et GRT_ENGINE (F_MVTCAISSE).",
    ),
    PipelineStep(
        table_name="FAIT_LIGNES_VENTE",
        extract_fn=lambda **kw: pd.concat([
            extract.extract_fait_lignes_vente(kw.get("last_run")),
            extract.extract_fait_lignes_achat(kw.get("last_run")),
        ], ignore_index=True),
        transform_fn=None,
        load_fn=lambda df, tbl, mode: load.load_fact(df, tbl, mode),
        description="Lignes de documents vente + achat (DO_Domaine=0/1). Grain = une ligne de document.",
    ),
    PipelineStep(
        table_name="FAIT_REGLEMENTS",
        extract_fn=lambda **kw: pd.DataFrame(),
        transform_fn=None,
        load_fn=lambda df, tbl, mode: load.load_fact(df, tbl, mode),
        description="Règlements clients et fournisseurs consolidés depuis MAG et GRT. Grain = un règlement.",
    ),
    PipelineStep(
        table_name="FAIT_ECRITURES",
        extract_fn=lambda **kw: pd.DataFrame(),
        transform_fn=None,
        load_fn=lambda df, tbl, mode: load.load_fact(df, tbl, mode),
        description="Écritures multi-grain : compta (1), TVA (2), mouvements caisse (3), stock snapshot (4).",
    ),
]


def run_pipeline(force_full: bool = False) -> None:
    """
    Orchestrate the full ETL pipeline:
      1. Determine load mode (full vs delta) from ETL_AUDIT.
      2. Apply DDL migrations (CREATE tables, ALTER columns, CREATE views).
      3. For each PipelineStep: extract → transform → load → build lookup.
      4. Compute derived KPIs in SQL (DSI, RFM scores).
      5. Mark the audit row SUCCESS or ERROR.

    Concurrency protection is handled entirely by sp_getapplock inside
    start_run() — no application-level lock is needed here.
    """
    if force_full:
        last_run_date, mode = None, "full"
        logger.info("Force full load requested via --full flag.")
    else:
        last_run_date, mode = get_last_run_info()
    logger.info(f"Mode: {mode.upper()}")

    ddl.create_all_tables(drop_existing=False)
    ddl.apply_schema_migrations()

    thresholds = _compute_thresholds()
    global _PIPELINE_THRESHOLDS
    _PIPELINE_THRESHOLDS = thresholds["buckets_impaye"]
    logger.info(f"Thresholds computed from DW: {thresholds}")

    run_id      = start_run(mode)
    fk_disabled = False

    lookups: Dict = {}

    _transform_lignes_vente = _build_lignes_vente_transform(last_run_date)
    _transform_reglements   = lambda df, lk: _assemble_fait_reglements(last_run_date, lk)
    _transform_ecritures    = lambda df, lk: _assemble_fait_ecritures(last_run_date, lk)

    _RUNTIME_TRANSFORMS: Dict[str, Callable] = {
        "FAIT_LIGNES_VENTE": _transform_lignes_vente,
        "FAIT_REGLEMENTS":   _transform_reglements,
        "FAIT_ECRITURES":    _transform_ecritures,
    }

    try:
        if mode == "full":
            with DW_ENGINE.begin() as conn:
                ddl.disable_all_fk(conn)
            fk_disabled = True
            logger.info("FK constraints disabled for full load.")

        for step in STEPS:
            table_name   = step.table_name
            extract_fn   = step.extract_fn
            _transform_fn = step.transform_fn
            load_fn      = step.load_fn

            with table_timer(run_id, table_name) as ctx:
                logger.info(f"--- [{table_name}] {step.description} ---")

                transform_fn = _RUNTIME_TRANSFORMS.get(table_name, _transform_fn)

                df_raw = extract_fn(last_run=last_run_date)
                n_extracted = len(df_raw)

                if table_name == "DIM_DATE":
                    df = _generate_dim_date()
                elif transform_fn is not None:
                    df = transform_fn(df_raw, lookups)
                else:
                    df = df_raw

                n_loaded = len(df)
                load_fn(df, table_name, mode)

                lookup_config_map = _get_lookup_config()
                if table_name in lookup_config_map:
                    nat_col, surr_col = lookup_config_map[table_name]
                    lookups[table_name] = _build_lookup(table_name, nat_col, surr_col)

                ctx["rows_inserted"] = n_loaded
                ctx["rows_updated"]  = 0

                # Volume log — visible in ETL log and useful for profiling
                orphaned = max(0, n_extracted - n_loaded)
                logger.info(
                    f"[{table_name}] extracted={n_extracted} "
                    f"loaded={n_loaded} orphaned={orphaned}"
                )

        logger.info("--- Computing dsi_jours (stock coverage indicator) ---")
        _compute_dsi_jours(thresholds)

        logger.info("--- Computing Stock KPIs (Python to SQL) ---")
        _compute_stock_kpis()



        end_run(run_id, "SUCCESS")

    except Exception as exc:
        logger.exception("ETL pipeline failed")
        end_run(run_id, "ERROR", error_msg=str(exc))
        raise

    finally:
        release_lock(run_id)
        if fk_disabled:
            try:
                with DW_ENGINE.begin() as conn:
                    ddl.enable_all_fk(conn)
                logger.info("FK constraints re-enabled.")
            except Exception as fk_exc:
                logger.error(f"Failed to re-enable FK constraints: {fk_exc}")


if __name__ == "__main__":
    run_pipeline(force_full="--full" in sys.argv)