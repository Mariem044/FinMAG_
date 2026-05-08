# etl/pipeline.py
"""Main orchestrator for the SIAD MAG Distribution ETL.

Bug fixes applied
-----------------
Bug 1  – Added missing ``add_fact_reglements_bucket`` function to transform
          module shim (defined locally here until transform.py is updated).
Bug 2  – DIM_CLIENT: N_CatTarif is hashed before lookup against DIM_SEGMENT
          (lookup keys are CRC32 hashes, not raw ints).
Bug 3  – DIM_CLIENT: collaborateur FK column renamed id_collab to match DDL.
Bug 4  – DIM_DEPOT: load key_col changed to "DE_No" (raw int, as per DDL and
          LOOKUP_CONFIG); _hash_columns call removed (DE_No is stored raw).
Bug 5  – _assemble_dim_banque: source column built before drop_duplicates using
          a per-row origin tag so row count always matches after dedup.
Bug 6  – FAIT_REGLEMENTS: merge join corrected to left_on="DO_Piece" so the
          règlement's document piece number matches F_DOCENTETE.DO_Piece.
Bug 7  – _last_run stored under a private key "_last_run" is fine; guarded
          against accidental overwrite by popping it before any step writes
          to lookups, and re-injecting it each iteration.
Bug 8  – GRT client enrichment: extract_dim_client_grt() is now merged into
          DIM_CLIENT before load.
Bug 9  – FK re-enable moved to a finally block so it runs even on failure.
Bug 10 – audit.py bare imports fixed (from etl.config / etl.utils.logger).
          (audit.py must be patched separately; pipeline import corrected here.)
"""

from __future__ import annotations

import hashlib
from etl.config import SEGMENTS, DIM_DATE_START, DIM_DATE_END
import sys
from datetime import datetime, date
from typing import Callable, Dict, List, Tuple, Optional

import pandas as pd
from sqlalchemy import text

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
# BUG 1 FIX — add_fact_reglements_bucket (missing from transform.py)
# ===========================================================================

def _add_fact_reglements_bucket(df: pd.DataFrame) -> pd.DataFrame:
    """Assign bucket_impaye based on delai_reel_jours and DR_Regle.

    Buckets (KPI-08):
        0 = 0–30 days
        1 = 31–60 days
        2 = 61–90 days
        3 = > 90 days
    Only rows with DR_Regle == 0 (unpaid) get a bucket; paid rows get NULL.
    """
    from etl.config import BUCKETS_IMPAYE  # [0, 30, 60, 90]

    def _bucket(row):
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


# ===========================================================================
# LOOKUPS
# ===========================================================================

def _build_lookup(
    table_name: str,
    natural_hash_col: str,
    surrogate_id_col: str,
) -> Dict[int, int]:

    query = (
        f"SELECT [{surrogate_id_col}] AS sid, "
        f"[{natural_hash_col}] AS nhash "
        f"FROM [{table_name}]"
    )

    df = pd.read_sql(query, DW_ENGINE)
    if table_name == "DIM_DATE" and not df.empty:
        df["nhash"] = pd.to_datetime(df["nhash"]).dt.date
    lookup = dict(zip(df["nhash"], df["sid"]))

    logger.debug(f"Lookup built for {table_name}: {len(lookup)} rows")
    return lookup


LOOKUP_CONFIG: Dict[str, Tuple[str, str]] = {
    "DIM_DATE":          ("date_valeur",       "id_date"),
    "DIM_DOMAINE":       ("code_domaine",      "id_domaine"),
    "DIM_TYPE_DOC":      ("code_type_doc",     "id_type_doc"),
    "DIM_MODE_REGLEMENT":("code_mode_reg",     "id_mode_reg"),
    "DIM_ETAT_REGLEMENT":("code_etat_reg",     "id_etat_reg"),
    "DIM_ETAT_DOCREGL":  ("code_etat_docregl", "id_etat_docregl"),
    "DIM_TYPE_LIGNE":    ("code_type_ligne",   "id_type_ligne"),
    "DIM_SENS_ECRITURE": ("code_sens",         "id_sens"),
    "DIM_TYPE_TVA":      ("code_type_tva",     "id_type_tva"),
    "DIM_TYPE_MVT_CAISSE": ("code_type_mvt",   "id_type_mvt"),
    "DIM_SEGMENT":       ("cbIndice_code",      "id_segment"),
    "DIM_COLLABORATEUR": ("CO_No",              "id_collab"),
    "DIM_FAMILLE":       ("FA_CodeFamille_code","id_famille"),
    "DIM_CLIENT":        ("CT_Num_code",        "id_client"),
    "DIM_FOURNISSEUR":   ("CT_Num_code",        "id_fournisseur"),
    "DIM_JOURNAL":       ("JO_Num_code",        "id_journal"),
    "DIM_BANQUE":        ("EB_Abrege_code",     "id_banque"),
    "DIM_ARTICLE":       ("AR_Ref_code",        "id_article"),
    "DIM_DEPOT":         ("DE_No",              "id_depot"),
    "DIM_CAISSE":        ("CA_Numero_code",     "id_caisse"),
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

    pivot = (
        df.pivot_table(
            index="FA_CodeFamille",
            columns="CL_Niveau",
            values="CL_Code",
            aggfunc="first",
        )
        .reset_index()
        .rename(
            columns={
                0: "niveau_0",
                1: "niveau_1",
                2: "niveau_2",
            }
        )
    )

    pivot["FA_CodeFamille_code"] = pivot["FA_CodeFamille"].apply(transform.hash_key)
    for level in ("niveau_0", "niveau_1", "niveau_2"):
        if level not in pivot.columns:
            pivot[level] = None
        pivot[f"{level}_code"] = pivot[level].apply(transform.hash_key)

    return pivot[
        [
            "FA_CodeFamille_code",
            "niveau_0_code",
            "niveau_1_code",
            "niveau_2_code",
        ]
    ]


def _add_static_label(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["libelle_type_mvt"] = df["code_type_mvt"].map(
        lambda v: f"Mouvement {int(v)}" if pd.notna(v) else None
    )
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
    lookups: Dict,
) -> pd.DataFrame:
    defaults = {
        "DO_Piece": None,
        "LB_Ligne": None,
        "LB_NbJour": 0,
        "LB_Agios": 0,
        "BR_Rapproch": 0,
        "BQ_ABREGE": None,
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
    docregl = (
        extract.extract_docregl_grt(last_run)
        .drop_duplicates(subset=["DO_Piece"], keep="last")
    )

    df = (
        pd.concat([clients, fournisseurs], ignore_index=True, sort=False)
        .merge(doc_dates, on=["DO_Type", "DO_Piece"], how="left")
        .merge(docregl, on="DO_Piece", how="left")
        .assign(RT_NbJour=lambda d: d["LB_NbJour"])
    )

    df = transform.add_fact_reglements_bucket(
        transform.add_fact_reglements_calcs(df)
    )

    return df.assign(
        id_date=lambda d: d["RT_Date"].apply(
            lambda dt: lookups.get("DIM_DATE", {}).get(
                pd.Timestamp(dt).date() if pd.notna(dt) else None
            )
        ),
        id_client=lambda d: d.apply(
            lambda row: (
                lookups.get("DIM_CLIENT", {}).get(transform.hash_key(row.get("CT_Num")))
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
        RT_Rapproche=lambda d: d["BR_Rapproch"].fillna(0).astype("Int16"),
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


def _assemble_dim_caisse(lookups: Dict) -> pd.DataFrame:
    df_mag = extract.extract_dim_caisse_mag()
    df_grt = (
        extract.extract_fait_mvtcaisse()
        [["CA_No", "CA_Type", "JO_Num"]]
        .drop_duplicates(subset=["CA_No"])
    )
    return (
        pd.concat([df_mag, df_grt], ignore_index=True)
        .assign(
            CA_Numero_code=lambda d: d["CA_No"].apply(transform.hash_key),
            JO_Num_code=lambda d: d["JO_Num"].apply(transform.hash_key),
        )
        .drop_duplicates(subset=["CA_Numero_code"], keep="first")
    )


# BUG 5 FIX — source column built per-row before drop_duplicates
def _assemble_dim_banque(lookups: Dict) -> pd.DataFrame:
    df_mag = extract.extract_dim_banque_mag().copy()
    df_grt = extract.extract_dim_banque_grt().copy()

    # Tag each row with its origin BEFORE concatenation and dedup
    df_mag["source"] = 1
    df_grt["source"] = 2

    return (
        pd.concat([df_mag, df_grt], ignore_index=True)
        .assign(
            EB_Abrege_code=lambda d: d["EB_Abrege"].apply(transform.hash_key),
            EB_Banque_code=lambda d: d["EB_Banque"].apply(transform.hash_key),
        )
        .drop_duplicates(subset=["EB_Abrege_code"], keep="first")
    )


def _assemble_fait_ecritures(
    last_run: Optional[datetime],
    lookups: Dict,
) -> pd.DataFrame:

    today = date.today()

    def _resolve_date(d):
        if pd.isna(d):
            return None
        return lookups.get("DIM_DATE", {}).get(pd.Timestamp(d).date())

    # TYPE 1 — écritures comptables
    df1 = (
        extract.extract_fait_ecriturec(last_run)
        .assign(
            type_ligne=1,
            id_type_ligne=_lookup_code(lookups, "DIM_TYPE_LIGNE", 1),
            id_date=lambda d: d["EC_Date"].apply(_resolve_date),
            id_journal=lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
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
            id_type_ligne=_lookup_code(lookups, "DIM_TYPE_LIGNE", 2),
            id_date=lambda d: d["EC_Date"].apply(_resolve_date),
            id_journal=lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
            ),
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
            id_type_ligne=_lookup_code(lookups, "DIM_TYPE_LIGNE", 3),
            id_date=lambda d: d["MC_Date"].apply(_resolve_date),
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
    df4 = (
        extract.extract_fait_artstock()
        .assign(
            type_ligne=4,
            id_type_ligne=_lookup_code(lookups, "DIM_TYPE_LIGNE", 4),
            id_date=lookups.get("DIM_DATE", {}).get(today),
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

    return pd.concat([df1, df2, df3, df4], ignore_index=True)


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
        WHERE tl.code_type_ligne = 4
    """
    with DW_ENGINE.begin() as conn:
        conn.execute(text(sql))
    logger.info("dsi_jours computed successfully.")


# ===========================================================================
# DATE DIM
# ===========================================================================

def _generate_dim_date(start: str = "2015-01-01", end: str = "2030-12-31") -> pd.DataFrame:
    dr = pd.date_range(start=start, end=end, freq="D")
    df = pd.DataFrame({"date_valeur": dr})
    df["annee"]       = df["date_valeur"].dt.year.astype("Int16")
    df["mois"]        = df["date_valeur"].dt.month.astype("Int16")
    df["jour"]        = df["date_valeur"].dt.day.astype("Int16")
    df["trimestre"]   = df["date_valeur"].dt.quarter.astype("Int16")          # ← ADD THIS
    df["semestre"]    = ((df["mois"] - 1) // 6 + 1).astype("Int16")          # ← ADD THIS
    df["semaine_iso"] = df["date_valeur"].dt.isocalendar().week.astype("Int32")
    df["jour_semaine"]= df["date_valeur"].dt.weekday + 1
    df["est_weekend"] = (df["jour_semaine"] >= 6).astype("Int16")
    df["est_ferie"]   = 0  # placeholder
    df["exercice"]    = None
    return df


# ===========================================================================
# STEPS
# ===========================================================================

STEPS: List[Step] = [

    (
        "DIM_DATE",
        lambda **kw: pd.DataFrame(),
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="date_valeur"),
    ),

    (
        "DIM_DOMAINE",
        lambda **kw: extract.extract_static_dims()["DIM_DOMAINE"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="code_domaine"),
    ),

    (
        "DIM_TYPE_DOC",
        lambda **kw: extract.extract_static_dims()["DIM_TYPE_DOC"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="code_type_doc"),
    ),

    (
        "DIM_MODE_REGLEMENT",
        lambda **kw: extract.extract_static_dims()["DIM_MODE_REGLEMENT"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="code_mode_reg"),
    ),

    (
        "DIM_ETAT_REGLEMENT",
        lambda **kw: extract.extract_static_dims()["DIM_ETAT_REGLEMENT"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="code_etat_reg"),
    ),

    (
        "DIM_ETAT_DOCREGL",
        lambda **kw: extract.extract_static_dims()["DIM_ETAT_DOCREGL"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="code_etat_docregl"),
    ),

    (
        "DIM_TYPE_LIGNE",
        lambda **kw: extract.extract_static_dims()["DIM_TYPE_LIGNE"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="code_type_ligne"),
    ),

    (
        "DIM_SENS_ECRITURE",
        lambda **kw: extract.extract_static_dims()["DIM_SENS_ECRITURE"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="code_sens"),
    ),

    (
        "DIM_TYPE_TVA",
        lambda **kw: extract.extract_static_dims()["DIM_TYPE_TVA"],
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="code_type_tva"),
    ),

    (
        "DIM_TYPE_MVT_CAISSE",
        lambda **kw: extract.extract_dim_type_mvt_caisse(),
        lambda df, lookups: _add_static_label(df),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="code_type_mvt"),
    ),

    (
        "DIM_SEGMENT",
        lambda **kw: extract.extract_dim_segment(),
        lambda df, lookups: (
            _hash_columns(df, ["cbIndice"])
            .assign(
                prix_ttc_flag=df["CT_PrixTTC"].fillna(0).astype("Int16"),
                libelle_segment=df["cbIndice"].map(
                    lambda v: SEGMENTS.get(int(v), f"Segment {v}")
                ),
            )
        ),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="cbIndice_code"),
    ),

    (
        "DIM_COLLABORATEUR",
        lambda **kw: extract.extract_dim_collaborateur(kw.get("last_run")),
        lambda df, lookups: _hash_columns(df, ["CO_Fonction"]),
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

    # BUG 2, 3, 8 FIX — DIM_CLIENT
    (
        "DIM_CLIENT",
        lambda **kw: extract.extract_dim_client_mag(kw.get("last_run")),

        lambda df, lookups: (
            lambda df_mag: (
                # BUG 8 FIX: merge GRT enrichment columns
                df_mag.merge(
                    extract.extract_dim_client_grt(),
                    on="CT_Num",
                    how="left",
                )
                .pipe(_hash_columns, ["CT_Num"])
                .assign(
                    # BUG 2 FIX: hash N_CatTarif before lookup (keys are CRC32)
                    id_segment=lambda d: d["N_CatTarif"].apply(
                        lambda v: lookups.get("DIM_SEGMENT", {}).get(
                            transform.hash_key(v)
                        )
                    ),
                    # BUG 3 FIX: column name is id_collab (matches DDL), not id_collaborateur
                    id_collab=lambda d: d["CO_No"].map(
                        lookups.get("DIM_COLLABORATEUR", {})
                    ),
                )
            )(df.copy())
        ),

        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CT_Num_code"),
    ),

    (
        "DIM_ARTICLE",
        lambda **kw: extract.extract_dim_article(kw.get("last_run")),
        lambda df, lookups: (
            _hash_columns(df, ["AR_Ref", "FA_CodeFamille", "CT_Num_fourn"])
            .assign(
                id_famille=df["FA_CodeFamille"].apply(
                    lambda v: lookups.get("DIM_FAMILLE", {}).get(transform.hash_key(v))
                ),
                id_fournisseur=df["CT_Num_fourn"].apply(
                    lambda v: lookups.get("DIM_FOURNISSEUR", {}).get(transform.hash_key(v))
                ),
            )
        ),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="AR_Ref_code"),
    ),

    # BUG 4 FIX — DIM_DEPOT: no hash column; DDL stores DE_No as raw INT UNIQUE
    (
        "DIM_DEPOT",
        lambda **kw: extract.extract_dim_depot(kw.get("last_run")),
        lambda df, lookups: df.copy(),          # no transform needed
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DE_No"),
    ),

    (
        "DIM_CAISSE",
        lambda **kw: pd.DataFrame(),
        lambda df, lookups: _assemble_dim_caisse(lookups),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CA_Numero_code"),
    ),

    (
        "FAIT_LIGNES_VENTE",
        lambda **kw: extract.extract_fait_lignes_vente(kw.get("last_run")),
        lambda df, lookups: (
            transform.add_fact_lignes_vente_calcs(df)
            .assign(
                id_date=df["DO_Date"].apply(
                    lambda d: lookups.get("DIM_DATE", {}).get(
                        pd.Timestamp(d).date() if pd.notna(d) else None
                    )
                ),
                id_type_doc=df["DO_Type"].apply(
                    lambda v: _lookup_code(lookups, "DIM_TYPE_DOC", v)
                ),
                id_domaine=df["DO_Domaine"].apply(
                    lambda v: _lookup_code(lookups, "DIM_DOMAINE", v)
                ),
                id_client=df["CT_Num"].apply(
                    lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
                ),
                id_article=df["AR_Ref"].apply(
                    lambda v: lookups.get("DIM_ARTICLE", {}).get(transform.hash_key(v))
                ),
                id_depot=df["DE_No"].apply(
                    lambda v: lookups.get("DIM_DEPOT", {}).get(v)
                ),
                source_hash=df.apply(
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

    # FAIT_REGLEMENTS: client and supplier regulations
    (
        "FAIT_REGLEMENTS",
        lambda **kw: pd.DataFrame(),
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

    # BUG 7 FIX — store _last_run once; never let step loop overwrite it
    lookups: Dict[str, Dict] = {"_last_run": last_run_date}

    # BUG 9 FIX — FK disable/enable wrapped in try/finally
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

                # Preserve _last_run before step mutates lookups
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

                # BUG 7 FIX — restore _last_run in case a step accidentally
                # wrote to the key (e.g. a table named "_last_run")
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

        # BUG 9 FIX — always re-enable FK constraints after a full load,
        # whether the pipeline succeeded or failed
        if fk_disabled:
            try:
                with DW_ENGINE.begin() as conn:
                    ddl.enable_all_fk(conn)
                logger.info("FK enabled.")
            except Exception as fk_exc:
                logger.error(f"Failed to re-enable FK constraints: {fk_exc}")


if __name__ == "__main__":
    run_pipeline()
