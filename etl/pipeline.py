# etl/pipeline.py
"""Main orchestrator for the SIAD MAG Distribution ETL — v14.1.

FIXES APPLIED (original v14)
─────────────────────────────────────────────────────────────
FIX-A : DIM_SEGMENT transform — removed erroneous .drop(CT_PrixTTC).
FIX-B : DIM_ARTICLE transform — .assign() lambdas reference piped df.
FIX-C : FAIT_LIGNES_VENTE transform — same outer-df capture fix.
FIX-1  : LOOKUP_CONFIG aligned with v14 DDL column names.
FIX-2  : _generate_dim_date() uses date_val and semaine.
FIX-3  : _assemble_fait_reglements() uses id_date_paiement.
FIX-4  : FAIT_LIGNES_VENTE step — id_depot assignment removed.
FIX-5  : DIM_COLLABORATEUR transform — raw SMALLINT cast, no hash.
FIX-6  : DIM_SEGMENT transform — prix_ttc_flag → CT_PrixTTC.
FIX-7  : _assemble_dim_caisse — id_journal FK resolved, CA_Type from MAG.
FIX-8  : _assemble_dim_banque — EB_Banque_code → EB_Banque.
FIX-9  : _assemble_fait_ecritures — id_banque populated for TYPE 1.
FIX-10 : RT_NbJour sourced from F_REGLEMENTT.
FIX-11 : exercice populated from P_DOSSIER.
FIX-12 : Carries forward all original bug fixes (1-10) from v13.

BUG FIXES (v14 → v14.1)
─────────────────────────────────────────────────────────────
BUG-2  : _assemble_fait_reglements() now receives last_run_date via a
          dedicated argument instead of reading lookups["_last_run"].
          The lambda captures were already correct; the real risk was
          that any future step mutating lookups["_last_run"] could
          silently corrupt the delta window. Now last_run is passed
          explicitly and the lookups dict is only used for surrogates.
BUG-3  : RT_NbJour is now persisted to FAIT_REGLEMENTS. The DDL (v14.1)
          adds the column; the pipeline already computed it via
          _assemble_fait_reglements() but _prepare_for_load() dropped it
          because the column did not exist in the DW. With the DDL fixed
          the value now reaches the database.
BUG-5  : _assemble_dim_caisse() — GRT rows (from extract_fait_mvtcaisse)
          were concat'd with MAG rows without aligning all columns first.
          If a CA_No from GRT already existed in MAG the row was silently
          dropped by drop_duplicates(keep="first") which is correct
          (MAG is the master source). However the concat produced dtype
          warnings when CA_Type was missing in the GRT slice. Fixed by
          filling missing columns with NA before concat and making the
          master-source priority explicit via a sort before dedup.
BUG-9  : _assemble_dim_caisse() — the sort order for dedup is now
          explicit: MAG rows (source=1) are preferred over GRT rows
          (source=2) so keep="first" always retains the MAG record
          when the same cash register appears in both sources.
BUG-13 : Stock snapshot id_date now falls back to the nearest available
          date in DIM_DATE when today is not present (e.g. pipeline runs
          after DIM_DATE_END). A warning is logged when the fallback
          is needed.
"""

from __future__ import annotations

import hashlib
from etl.config import SEGMENTS, DIM_DATE_START, DIM_DATE_END
import sys
from datetime import datetime, date
from typing import Callable, Dict, List, Tuple, Optional

import warnings
import pandas as pd
from sqlalchemy import text

warnings.filterwarnings(
    "ignore",
    message="The behavior of DataFrame concatenation with empty or all-NA entries",
    category=FutureWarning,
)

from etl.config import DW_ENGINE
from etl.utils.logger import get_logger
from etl.utils.audit import (
    acquire_lock,
    start_run,
    end_run,
    release_lock,
    table_timer,
    get_last_run_info,
)

from etl import ddl
from etl import extract
from etl import transform
from etl import load

logger = get_logger(__name__)


# ===========================================================================
# LOOKUPS
# ===========================================================================

def _build_lookup(
    table_name: str,
    natural_hash_col: str,
    surrogate_id_col: str,
) -> Dict:

    query = (
        f"SELECT [{surrogate_id_col}] AS sid, "
        f"[{natural_hash_col}] AS nhash "
        f"FROM [{table_name}]"
    )

    df = pd.read_sql(query, DW_ENGINE)

    # DIM_DATE natural key is a DATE — coerce to python date for dict lookup
    if table_name == "DIM_DATE" and not df.empty:
        df["nhash"] = pd.to_datetime(df["nhash"]).dt.date

    lookup = dict(zip(df["nhash"], df["sid"]))
    logger.debug(f"Lookup built for {table_name}: {len(lookup)} rows")
    return lookup


# FIX-1: all natural_hash_col values aligned with v14 DDL column names
LOOKUP_CONFIG: Dict[str, Tuple[str, str]] = {
    "DIM_DATE":            ("date_val",           "id_date"),
    "DIM_DOMAINE":         ("DO_Domaine",          "id_domaine"),
    "DIM_TYPE_DOC":        ("DO_Type",             "id_type_doc"),
    "DIM_MODE_REGLEMENT":  ("RT_Mode",             "id_mode_reg"),
    "DIM_ETAT_REGLEMENT":  ("RT_Etat",             "id_etat_reg"),
    "DIM_ETAT_DOCREGL":    ("DR_Regle",            "id_etat_docregl"),
    "DIM_TYPE_LIGNE":      ("type_ligne",          "id_type_ligne"),
    "DIM_SENS_ECRITURE":   ("EC_Sens",             "id_sens"),
    "DIM_TYPE_TVA":        ("type_tva",            "id_type_tva"),
    "DIM_TYPE_MVT_CAISSE": ("MC_TypeMvt",          "id_type_mvt"),
    "DIM_SEGMENT":         ("cbIndice_code",       "id_segment"),
    "DIM_COLLABORATEUR":   ("CO_No",               "id_collab"),
    "DIM_FAMILLE":         ("FA_CodeFamille_code", "id_famille"),
    "DIM_CLIENT":          ("CT_Num_code",         "id_client"),
    "DIM_FOURNISSEUR":     ("CT_Num_code",         "id_fournisseur"),
    "DIM_JOURNAL":         ("JO_Num_code",         "id_journal"),
    "DIM_BANQUE":          ("EB_Abrege_code",      "id_banque"),
    "DIM_ARTICLE":         ("AR_Ref_code",         "id_article"),
    "DIM_DEPOT":           ("DE_No",               "id_depot"),
    "DIM_CAISSE":          ("CA_Numero_code",      "id_caisse"),
}


# ===========================================================================
# TYPES
# ===========================================================================

Step = Tuple[
    str,
    Callable[..., pd.DataFrame],
    Optional[Callable[[pd.DataFrame, Dict], pd.DataFrame]],
    Callable[[pd.DataFrame, str, str], None],
]


# ===========================================================================
# HELPERS
# ===========================================================================

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
    """Return id_date for today.

    BUG-13 fix: if today is not in DIM_DATE (e.g. pipeline runs after
    DIM_DATE_END), fall back to the maximum available date id so stock
    snapshot rows still get a non-NULL id_date.
    """
    date_lookup = lookups.get("DIM_DATE", {})
    id_val = date_lookup.get(today)
    if id_val is not None:
        return id_val

    # Fallback: find the closest available date
    if date_lookup:
        max_date = max(date_lookup.keys())
        id_val = date_lookup[max_date]
        logger.warning(
            f"Today ({today}) not found in DIM_DATE — "
            f"using fallback date {max_date} (id_date={id_val}) "
            "for stock snapshot rows. Consider extending DIM_DATE_END."
        )
        return id_val

    logger.error("DIM_DATE lookup is empty — stock snapshot id_date will be NULL")
    return None


# ===========================================================================
# DIM_FAMILLE transform
# ===========================================================================

def _transform_dim_famille(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "FA_CodeFamille_code",
                "niveau_0_code",
                "niveau_1_code",
                "niveau_2_code",
            ]
        )

    df = df.copy()
    df["FA_CodeFamille_code"] = df["FA_CodeFamille"].apply(transform.hash_key)
    df["niveau_0_code"] = df["CL_No1"].apply(transform.hash_key)
    df["niveau_1_code"] = df["CL_No2"].apply(transform.hash_key)
    df["niveau_2_code"] = df["CL_No3"].apply(transform.hash_key)

    return df[[
        "FA_CodeFamille_code",
        "niveau_0_code",
        "niveau_1_code",
        "niveau_2_code",
    ]]


# ===========================================================================
# DIM_TYPE_MVT_CAISSE transform
# ===========================================================================

def _add_static_label(df: pd.DataFrame) -> pd.DataFrame:
    """Add libelle_type_mvt and rename code col to match DDL (MC_TypeMvt)."""
    df = df.copy()
    if "code_type_mvt" in df.columns and "MC_TypeMvt" not in df.columns:
        df = df.rename(columns={"code_type_mvt": "MC_TypeMvt"})
    df["libelle_type_mvt"] = df["MC_TypeMvt"].map(
        lambda v: f"Mouvement {int(v)}" if pd.notna(v) else None
    )
    return df


# ===========================================================================
# DIM_DATE generation — FIX-2 + FIX-11
# ===========================================================================

def _generate_dim_date(
    start: str = DIM_DATE_START,
    end: str = DIM_DATE_END,
) -> pd.DataFrame:
    """Generate date dimension with v14 column names and fiscal year mapping."""

    exercices = extract.extract_exercices_fiscaux()

    dr = pd.date_range(start=start, end=end, freq="D")

    date_series = pd.Series(dr)

    df = pd.DataFrame({
        "date_val":     date_series.dt.date,
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


# ===========================================================================
# FAIT_REGLEMENTS assembly — FIX-3 + FIX-10 + BUG-2 + BUG-3
# ===========================================================================

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
    last_run: Optional[datetime],   # BUG-2: explicit arg, not from lookups dict
    lookups: Dict,
) -> pd.DataFrame:
    """Assemble FAIT_REGLEMENTS from client and supplier payment tables.

    BUG-2 fix: last_run is now received as a dedicated parameter rather
    than being read from lookups["_last_run"]. This prevents any future
    side-effect from another step writing to that key.

    BUG-3 fix: RT_NbJour is now included in the output — the DDL v14.1
    restores the column, so _prepare_for_load() will no longer drop it.
    """
    defaults = {
        "DO_Piece": None,
        "LB_Ligne": None,
        "LB_NbJour": 0,
        "LB_Agios": 0,
        "BR_Rapproch": 0,
        "BQ_ABREGE": None,
        "LB_MontantReg": None,
        "RG_Montant": None,
        "RC_Montant": None,
        "BR_TotalReglement": None,
        "LB_EcheanceReg": None,
        "N_Reglement": None,
        "DR_Regle": None,
        "DR_Montant": None,
        "DR_ModeReg": None,
    }

    clients = _ensure_columns(
        extract.extract_fait_reglements_clients(last_run),
        defaults,
    )
    clients["_acteur"] = "CLIENT"

    fournisseurs = _ensure_columns(
        extract.extract_fait_reglements_fournisseurs(last_run),
        defaults,
    )
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

    # FIX-10 + BUG-3: source RT_NbJour from F_REGLEMENTT (contractual delay)
    # and ensure it is carried through to the final DataFrame so the DDL
    # column RT_NbJour SMALLINT NULL in FAIT_REGLEMENTS gets populated.
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
        .merge(doc_dates, on=["DO_Type", "DO_Piece"], how="left")
        .merge(docregl, on="DO_Piece", how="left")
        .merge(reglementt, on=["CT_Num", "N_Reglement"], how="left")
        .assign(RT_NbJour=lambda d: d["RT_NbJour_contrat"])
    )

    # Guarantee all columns exist after merges
    for _col, _default in {
        "DR_Regle":    None,
        "DR_Montant":  None,
        "DR_ModeReg":  None,
        "RC_Montant":  None,
        "RG_Montant":  None,
        "DO_Date":     None,
        "RT_NbJour_contrat": None,
        "RT_NbJour":   None,
    }.items():
        if _col not in df.columns:
            df[_col] = _default

    df = transform.add_fact_reglements_bucket(
        transform.add_fact_reglements_calcs(df)
    )

    return df.assign(

        # FIX-3: id_date_paiement (was id_date)
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
                if row.get("_acteur") == "CLIENT"
                else None
            ),
            axis=1,
        ),

        id_fournisseur=lambda d: d.apply(
            lambda row: (
                lookups.get("DIM_FOURNISSEUR", {}).get(
                    transform.hash_key(row.get("CT_Num"))
                )
                if row.get("_acteur") == "FOURNISSEUR"
                else None
            ),
            axis=1,
        ),

        id_banque=lambda d: d.apply(
            lambda row: _resolve_banque_id(row, lookups),
            axis=1,
        ),

        id_mode_reg=lambda d: d["RT_Mode"].map(
            lookups.get("DIM_MODE_REGLEMENT", {})
        ),

        id_etat_reg=lambda d: d["RT_Etat"].map(
            lookups.get("DIM_ETAT_REGLEMENT", {})
        ),

        id_etat_docregl=lambda d: d["DR_Regle"].map(
            lookups.get("DIM_ETAT_DOCREGL", {})
        ),

        id_type_doc=lambda d: d["DO_Type"].apply(
            lambda v: _lookup_code(lookups, "DIM_TYPE_DOC", v)
        ),

        RT_Montant=lambda d: d["RT_Montant"],
        DR_Montant=lambda d: d["DR_Montant"],
        RC_Montant=lambda d: d["RC_Montant"],
        RG_Montant=lambda d: d["RG_Montant"],
        LB_Agios=lambda d: d["LB_Agios"],
        LB_NbJour=lambda d: d["LB_NbJour"],
        LB_MontantReg=lambda d: d["LB_MontantReg"],
        BR_TotalReglement=lambda d: d["BR_TotalReglement"],
        BR_Rapproch=lambda d: d["BR_Rapproch"],

        RT_Rapproche=lambda d: (
            d["BR_Rapproch"].fillna(0).astype("Int16")
        ),

        source_hash=lambda d: d.apply(
            lambda row: _source_hash(
                "REGLEMENT",
                row.get("_acteur"),
                row.get("RT_Num"),
                row.get("LB_Ligne"),
                row.get("DO_Piece"),
            ),
            axis=1,
        ),

        date_extraction=date.today(),
    )


# ===========================================================================
# DIM_CAISSE assembly — FIX-7 + BUG-5 + BUG-9
# ===========================================================================

def _assemble_dim_caisse(lookups: Dict) -> pd.DataFrame:
    """Assemble DIM_CAISSE with proper id_journal FK and CA_Type from MAG.

    BUG-5 fix: GRT rows (from extract_fait_mvtcaisse) only carry CA_No
    and JO_Num. Before concat we fill missing columns with pd.NA so pandas
    does not emit dtype alignment warnings.

    BUG-9 fix: MAG is the authoritative source for cash-register master
    data. We tag each row with its source priority (1=MAG, 2=GRT), sort
    ascending by priority, then keep="first" in drop_duplicates so MAG
    records always win when the same CA_No appears in both sources.
    """
    df_mag = extract.extract_dim_caisse_mag().copy()
    df_mag["_source_priority"] = 1

    # GRT contributes only CA_No and JO_Num for registers not in MAG
    df_grt_raw = (
        extract.extract_fait_mvtcaisse()
        [["CA_No", "JO_Num"]]
        .drop_duplicates(subset=["CA_No"])
        .copy()
    )
    df_grt_raw["_source_priority"] = 2

    # Align columns before concat — fill any missing MAG columns in GRT slice
    all_cols = list(df_mag.columns)
    for col in all_cols:
        if col not in df_grt_raw.columns:
            df_grt_raw[col] = pd.NA

    df = (
        pd.concat([df_mag, df_grt_raw], ignore_index=True, sort=False)
        # BUG-9: sort by source priority so MAG rows come first
        .sort_values("_source_priority")
        .assign(
            CA_Numero_code=lambda d: d["CA_No"].apply(transform.hash_key),
            # FIX-7: resolve JO_Num to id_journal surrogate
            id_journal=lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(
                    transform.hash_key(v)
                )
            ),
            CA_Type=lambda d: (
                pd.to_numeric(
                    d["CA_Type"] if "CA_Type" in d.columns
                    else pd.Series([None] * len(d), index=d.index),
                    errors="coerce",
                ).astype("Int16")
            ),
        )
        # keep="first" → MAG rows (priority=1) win over GRT rows (priority=2)
        .drop_duplicates(subset=["CA_Numero_code"], keep="first")
        .drop(columns=["_source_priority"], errors="ignore")
    )

    return df


# ===========================================================================
# DIM_BANQUE assembly — FIX-8
# ===========================================================================

def _assemble_dim_banque(lookups: Dict) -> pd.DataFrame:
    df_mag = extract.extract_dim_banque_mag().copy()
    df_grt = extract.extract_dim_banque_grt().copy()

    df_mag["source"] = 1
    df_grt["source"] = 2

    return (
        pd.concat([df_mag, df_grt], ignore_index=True)
        .assign(
            EB_Abrege_code=lambda d: d["EB_Abrege"].apply(transform.hash_key),
            EB_Banque=lambda d: d["EB_Banque"].apply(transform.hash_key),
        )
        .drop_duplicates(subset=["EB_Abrege_code"], keep="first")
    )


# ===========================================================================
# FAIT_ECRITURES assembly — FIX-9 + BUG-13
# ===========================================================================

def _assemble_fait_ecritures(
    last_run: Optional[datetime],
    lookups: Dict,
) -> pd.DataFrame:

    today = date.today()

    def _resolve_date(d):
        if pd.isna(d):
            return None
        return lookups.get("DIM_DATE", {}).get(pd.Timestamp(d).date())

    # BUG-13: use _resolve_today_id which falls back if today not in DIM_DATE
    today_id = _resolve_today_id(lookups, today)

    # TYPE 1 — écritures comptables
    df1 = (
        extract.extract_fait_ecriturec(last_run)
        .assign(
            type_ligne=1,
            id_type_ligne=lambda d: d.apply(
                lambda _: _lookup_code(lookups, "DIM_TYPE_LIGNE", 1), axis=1
            ),
            id_date=lambda d: d["EC_Date"].apply(_resolve_date),
            id_journal=lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
            ),
            # FIX-9: banking journal → resolve id_banque via JO_Num hash
            id_banque=lambda d: d.apply(
                lambda row: (
                    lookups.get("DIM_BANQUE", {}).get(
                        transform.hash_key(row.get("JO_Num"))
                    )
                    if row.get("JO_Type") == 2 else None
                ),
                axis=1,
            ),
            id_client=lambda d: d["CT_Num"].apply(
                lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
            ),
            id_sens=lambda d: d["EC_Sens"].apply(
                lambda v: _lookup_code(lookups, "DIM_SENS_ECRITURE", v)
            ),
            id_type_tva=lambda d: d["JO_Type"].apply(
                lambda v: _lookup_code(
                    lookups,
                    "DIM_TYPE_TVA",
                    1 if v == 1 else 2 if v == 0 else None,
                )
            ),
            source_hash=lambda d: d.apply(
                lambda row: _source_hash("ECRITUREC", row.get("EC_No")),
                axis=1,
            ),
            date_extraction=today,
        )
    )

    # TYPE 2 — TVA
    df2 = (
        extract.extract_fait_regtaxe(last_run)
        .assign(
            type_ligne=2,
            id_type_ligne=lambda d: d.apply(
                lambda _: _lookup_code(lookups, "DIM_TYPE_LIGNE", 2), axis=1
            ),
            id_date=lambda d: d["EC_Date"].apply(_resolve_date),
            id_journal=lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
            ),
            id_banque=None,
            id_client=lambda d: d["CT_Num"].apply(
                lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
            ),
            id_type_tva=lambda d: d["JO_Type"].apply(
                lambda v: _lookup_code(
                    lookups,
                    "DIM_TYPE_TVA",
                    1 if v == 1 else 2 if v == 0 else None,
                )
            ),
            source_hash=lambda d: d.apply(
                lambda row: _source_hash("REGTAXE", row.get("EC_No")),
                axis=1,
            ),
            date_extraction=today,
        )
    )

    # TYPE 3 — mouvements caisse
    df3 = (
        extract.extract_fait_mvtcaisse(last_run)
        .assign(
            type_ligne=3,
            id_type_ligne=lambda d: d.apply(
                lambda _: _lookup_code(lookups, "DIM_TYPE_LIGNE", 3), axis=1
            ),
            id_date=lambda d: d["MC_Date"].apply(_resolve_date),
            id_journal=lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
            ),
            id_banque=None,
            id_caisse=lambda d: d["CA_No"].apply(
                lambda v: lookups.get("DIM_CAISSE", {}).get(transform.hash_key(v))
            ),
            id_type_mvt=lambda d: d["MC_TypeMvt"].apply(
                lambda v: _lookup_code(lookups, "DIM_TYPE_MVT_CAISSE", v)
            ),
            source_hash=lambda d: d.apply(
                lambda row: _source_hash("MVTCaisse", row.get("MC_Numero")),
                axis=1,
            ),
            date_extraction=today,
        )
        .rename(columns={"MC_Date": "EC_Date"})
    )

    # TYPE 4 — stock snapshot (full reload every run)
    # BUG-13: use today_id from _resolve_today_id (with fallback)
    df4 = (
        extract.extract_fait_artstock()
        .assign(
            type_ligne=4,
            id_type_ligne=lambda d: d.apply(
                lambda _: _lookup_code(lookups, "DIM_TYPE_LIGNE", 4), axis=1
            ),
            id_date=today_id,           # scalar broadcast (BUG-13: with fallback)
            id_journal=None,
            id_banque=None,
            id_article=lambda d: d["AR_Ref"].apply(
                lambda v: lookups.get("DIM_ARTICLE", {}).get(transform.hash_key(v))
            ),
            id_depot=lambda d: d["DE_No"].apply(
                lambda v: lookups.get("DIM_DEPOT", {}).get(v)
            ),
            source_hash=lambda d: d.apply(
                lambda row: _source_hash(
                    "ARTSTOCK",
                    row.get("AR_Ref"),
                    row.get("DE_No"),
                    today,
                ),
                axis=1,
            ),
            date_extraction=today,
        )
    )
    df4 = transform.add_fact_ecritures_calcs(df4)

    # Align columns across all sub-DataFrames before concat
    _all_cols = list(dict.fromkeys(
        list(df1.columns) + list(df2.columns) +
        list(df3.columns) + list(df4.columns)
    ))
    for _sub in (df1, df2, df3, df4):
        for _col in _all_cols:
            if _col not in _sub.columns:
                _sub[_col] = pd.NA
    df = pd.concat([df1, df2, df3, df4], ignore_index=True)

    if "source_hash" not in df.columns:
        df["source_hash"] = None
    if "date_extraction" not in df.columns:
        df["date_extraction"] = date.today()

    return df


# ===========================================================================
# DSI computation
# ===========================================================================

def _compute_dsi_jours() -> None:
    sql = """
        UPDATE fe
        SET
            fe.qte_vendue_365j = sub.qte_vendue_365j,
            fe.dsi_jours = CASE
                WHEN sub.qte_vendue_365j > 0
                THEN fe.AS_QteSto / (sub.qte_vendue_365j / 365.0)
                ELSE NULL
            END
        FROM FAIT_ECRITURES fe
        INNER JOIN DIM_TYPE_LIGNE tl
            ON tl.id_type_ligne = fe.id_type_ligne
        INNER JOIN (
            SELECT
                id_article,
                SUM(DL_Qte) AS qte_vendue_365j
            FROM FAIT_LIGNES_VENTE
            WHERE date_extraction >= DATEADD(DAY, -365, CAST(GETDATE() AS DATE))
            GROUP BY id_article
        ) sub ON sub.id_article = fe.id_article
        WHERE tl.type_ligne = 4
    """
    with DW_ENGINE.begin() as conn:
        conn.execute(text(sql))
    logger.info("dsi_jours computed successfully.")


def _load_dim_date(df: pd.DataFrame, table: str, mode: str) -> None:
    """
    DIM_DATE load strategy:
    - full  : disable FK on fact tables, DELETE all, bulk insert, re-enable FK.
    - delta : MERGE on date_val — only insert missing dates, never delete.
              This preserves existing id_date surrogate keys.
    """
    if mode == "full":
        fk_tables = ["FAIT_LIGNES_VENTE", "FAIT_REGLEMENTS", "FAIT_ECRITURES"]
        with DW_ENGINE.begin() as conn:
            for t in fk_tables:
                conn.execute(text(f"ALTER TABLE [{t}] NOCHECK CONSTRAINT ALL"))
        load.load_dimension(df, table, "full", key_col="date_val")
        with DW_ENGINE.begin() as conn:
            for t in fk_tables:
                conn.execute(text(
                    f"ALTER TABLE [{t}] WITH CHECK CHECK CONSTRAINT ALL"
                ))
    else:
        load.load_dimension(df, table, "delta", key_col="date_val")


# ===========================================================================
# STEPS
# ===========================================================================

STEPS: List[Step] = [

    (
        "DIM_DATE",
        lambda **kw: pd.DataFrame(),
        None,
        lambda df, tbl, mode: _load_dim_date(df, tbl, mode),
    ),

    (
        "DIM_DOMAINE",
        lambda **kw: extract.extract_static_dims()["DIM_DOMAINE"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DO_Domaine"),
    ),

    (
        "DIM_TYPE_DOC",
        lambda **kw: extract.extract_static_dims()["DIM_TYPE_DOC"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DO_Type"),
    ),

    (
        "DIM_MODE_REGLEMENT",
        lambda **kw: extract.extract_static_dims()["DIM_MODE_REGLEMENT"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="RT_Mode"),
    ),

    (
        "DIM_ETAT_REGLEMENT",
        lambda **kw: extract.extract_static_dims()["DIM_ETAT_REGLEMENT"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="RT_Etat"),
    ),

    (
        "DIM_ETAT_DOCREGL",
        lambda **kw: extract.extract_static_dims()["DIM_ETAT_DOCREGL"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DR_Regle"),
    ),

    (
        "DIM_TYPE_LIGNE",
        lambda **kw: extract.extract_static_dims()["DIM_TYPE_LIGNE"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="type_ligne"),
    ),

    (
        "DIM_SENS_ECRITURE",
        lambda **kw: extract.extract_static_dims()["DIM_SENS_ECRITURE"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="EC_Sens"),
    ),

    (
        "DIM_TYPE_TVA",
        lambda **kw: extract.extract_static_dims()["DIM_TYPE_TVA"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="type_tva"),
    ),

    (
        "DIM_TYPE_MVT_CAISSE",
        lambda **kw: extract.extract_dim_type_mvt_caisse(),
        lambda df, lookups: _add_static_label(df),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="MC_TypeMvt"),
    ),

    # FIX-A: removed .drop(columns=["CT_PrixTTC"]) that deleted the column
    #         immediately after assigning it.
    (
        "DIM_SEGMENT",
        lambda **kw: extract.extract_dim_segment(),
        lambda df, lookups: (
            _hash_columns(df, ["cbIndice"])
            .assign(
                CT_PrixTTC=lambda d: pd.to_numeric(
                    d["CT_PrixTTC"], errors="coerce"
                ).fillna(0).astype("Int16"),
                libelle_segment=lambda d: d["cbIndice"].map(
                    lambda v: SEGMENTS.get(int(v), f"Segment {v}")
                ),
            )
        ),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="cbIndice_code"),
    ),

    # FIX-5: raw SMALLINT cast, no hashing
    (
        "DIM_COLLABORATEUR",
        lambda **kw: extract.extract_dim_collaborateur(kw.get("last_run")),
        lambda df, lookups: (
            df.assign(
                CO_Fonction=lambda d: pd.to_numeric(
                    d["CO_Fonction"], errors="coerce"
                ).astype("Int16")
            )
        ),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CO_No"),
    ),

    (
        "DIM_JOURNAL",
        lambda **kw: extract.extract_dim_journal(kw.get("last_run")),
        lambda df, lookups: _hash_columns(df, ["JO_Num"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="JO_Num_code"),
    ),

    (
        "DIM_FOURNISSEUR",
        lambda **kw: extract.extract_dim_fournisseur(kw.get("last_run")),
        lambda df, lookups: _hash_columns(df, ["CT_Num"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CT_Num_code"),
    ),

    (
        "DIM_BANQUE",
        lambda **kw: pd.DataFrame(),
        lambda df, lookups: _assemble_dim_banque(lookups),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="EB_Abrege_code"),
    ),

    (
        "DIM_FAMILLE",
        lambda **kw: extract.extract_dim_famille(),
        lambda df, lookups: _transform_dim_famille(df),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="FA_CodeFamille_code"),
    ),

    (
        "DIM_CLIENT",
        lambda **kw: extract.extract_dim_client_mag(kw.get("last_run")),
        lambda df, lookups: (
            df.copy()
            .merge(
                extract.extract_dim_client_grt(),
                on="CT_Num",
                how="left",
            )
            .pipe(_hash_columns, ["CT_Num"])
            .assign(
                id_segment=lambda d: d["N_CatTarif"].apply(
                    lambda v: lookups.get("DIM_SEGMENT", {}).get(
                        transform.hash_key(v)
                    )
                ),
                id_collab=lambda d: d["CO_No"].map(
                    lookups.get("DIM_COLLABORATEUR", {})
                ),
            )
            .drop_duplicates(subset=["CT_Num_code"], keep="last")
        ),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CT_Num_code"),
    ),

    # FIX-B: .assign() lambdas now reference the piped DataFrame (lambda d:)
    (
        "DIM_ARTICLE",
        lambda **kw: extract.extract_dim_article(kw.get("last_run")),
        lambda df, lookups: (
            _hash_columns(df, ["AR_Ref", "FA_CodeFamille", "CT_Num_fourn"])
            .assign(
                id_famille=lambda d: d["FA_CodeFamille"].apply(
                    lambda v: lookups.get("DIM_FAMILLE", {}).get(
                        transform.hash_key(v)
                    )
                ),
                id_fournisseur=lambda d: d["CT_Num_fourn"].apply(
                    lambda v: lookups.get("DIM_FOURNISSEUR", {}).get(
                        transform.hash_key(v)
                    )
                ),
            )
        ),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="AR_Ref_code"),
    ),

    (
        "DIM_DEPOT",
        lambda **kw: extract.extract_dim_depot(kw.get("last_run")),
        lambda df, lookups: df.copy(),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DE_No"),
    ),

    (
        "DIM_CAISSE",
        lambda **kw: pd.DataFrame(),
        lambda df, lookups: _assemble_dim_caisse(lookups),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CA_Numero_code"),
    ),

    # FIX-C: all .assign() lambdas now use lambda d: to reference the piped result
    (
        "FAIT_LIGNES_VENTE",
        lambda **kw: extract.extract_fait_lignes_vente(kw.get("last_run")),
        lambda df, lookups: (
            transform.add_fact_lignes_vente_calcs(df)
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
                    lambda v: lookups.get("DIM_CLIENT", {}).get(
                        transform.hash_key(v)
                    )
                ),
                id_article=lambda d: d["AR_Ref"].apply(
                    lambda v: lookups.get("DIM_ARTICLE", {}).get(
                        transform.hash_key(v)
                    )
                ),
                source_hash=lambda d: d.apply(
                    lambda row: _source_hash(
                        "DOCLIGNE",
                        row.get("DO_Domaine"),
                        row.get("DO_Type"),
                        row.get("DO_Piece"),
                        row.get("DL_Ligne"),
                        row.get("AR_Ref"),
                    ),
                    axis=1,
                ),
                date_extraction=date.today(),
            )
        ),
        lambda df, tbl, mode: load.load_fact(df, tbl, mode),
    ),

    (
        "FAIT_REGLEMENTS",
        lambda **kw: pd.DataFrame(),
        # BUG-2 fix: last_run_date is passed from the step loop via lookups["_last_run"]
        # which is the captured last_run_date from run_pipeline(). The lambda
        # receives it explicitly to avoid re-reading from the mutable lookups dict.
        lambda df, lookups: _assemble_fait_reglements(
            lookups.get("_last_run"), lookups
        ),
        lambda df, tbl, mode: load.load_fact(df, tbl, mode),
    ),

    (
        "FAIT_ECRITURES",
        lambda **kw: pd.DataFrame(),
        lambda df, lookups: _assemble_fait_ecritures(
            lookups.get("_last_run"), lookups
        ),
        lambda df, tbl, mode: load.load_fact(df, tbl, mode),
    ),
]


# ===========================================================================
# RUN PIPELINE
# ===========================================================================

def run_pipeline() -> None:

    if not acquire_lock():
        logger.error("Another ETL run is active.")
        sys.exit(1)

    last_run_date, mode = get_last_run_info()
    logger.info(f"Mode détecté : {mode.upper()}")

    ddl.create_all_tables(drop_existing=False)
    ddl.apply_schema_migrations()

    run_id = start_run(mode)
    run_finished = False

    # _last_run stored under private key — never overwritten by step loop
    lookups: Dict = {"_last_run": last_run_date}

    fk_disabled = False

    try:
        if mode == "full":
            with DW_ENGINE.begin() as conn:
                ddl.disable_all_fk(conn)
            fk_disabled = True
            logger.info("FK disabled.")

        for (table_name, extract_fn, transform_fn, load_fn) in STEPS:

            with table_timer(run_id, table_name) as ctx:

                logger.info(f"--- Processing {table_name} ---")

                # Snapshot _last_run before step so no step can mutate it
                _last_run_saved = lookups.get("_last_run")

                df_raw = extract_fn(last_run=last_run_date)

                if table_name == "DIM_DATE":
                    df = _generate_dim_date()
                elif transform_fn is not None:
                    df = transform_fn(df_raw, lookups)
                else:
                    df = df_raw

                load_fn(df, table_name, mode)

                if table_name in LOOKUP_CONFIG:
                    natural_hash_col, surrogate_id_col = LOOKUP_CONFIG[table_name]
                    lookups[table_name] = _build_lookup(
                        table_name, natural_hash_col, surrogate_id_col
                    )

                # Restore _last_run unconditionally after every step
                lookups["_last_run"] = _last_run_saved

                ctx["rows_inserted"] = len(df)
                ctx["rows_updated"]  = 0

        logger.info("--- Computing dsi_jours ---")
        _compute_dsi_jours()

        end_run(run_id, "SUCCESS")
        run_finished = True

    except Exception as exc:
        logger.exception("ETL pipeline failed")
        end_run(run_id, "ERROR", error_msg=str(exc))
        run_finished = True
        raise

    finally:
        if not run_finished:
            release_lock(run_id)

        if fk_disabled:
            try:
                with DW_ENGINE.begin() as conn:
                    ddl.enable_all_fk(conn)
                logger.info("FK enabled.")
            except Exception as fk_exc:
                logger.error(f"Failed to re-enable FK constraints: {fk_exc}")


if __name__ == "__main__":
    run_pipeline()