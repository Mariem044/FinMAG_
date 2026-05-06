# etl/pipeline.py
"""Main orchestrator for the SIAD MAG Distribution ETL.
It determines the run mode (full load vs. incremental delta),
creates the DW schema if missing, extracts → transforms → loads
all dimension tables (respecting FK order) followed by fact tables,
and records everything in the ETL_AUDIT table.

Bug fixes applied
-----------------
Bug  9  – Step type alias: mismatched Optional bracket corrected.
Bug 10  – Lookup building: replaced fragile column‑inference with an explicit
           LOOKUP_CONFIG dict per table.
Bug 11  – FAIT_LIGNES_VENTE transform: removed references to N_CatTarif and
           CO_No which are not present in extract_fait_lignes_vente output.
Bug 12  – _generate_dim_date: semaine_iso cast changed Int16→Int32 to avoid
           silent overflow for week 53 (UInt32 source dtype).
Bug 13  – STEPS now includes DIM_FOURNISSEUR, DIM_JOURNAL, DIM_BANQUE,
           FAIT_REGLEMENTS, and FAIT_ECRITURES.
Bug 19  – disable_all_fk called before dimension loads in full mode;
           enable_all_fk called once after all loads complete.
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, date
from typing import Callable, Dict, List, Tuple, Optional

import pandas as pd

from etl.config import DW_ENGINE, CHUNK_SIZE
from etl.utils.logger import get_logger
from etl.utils.audit import (
    acquire_lock,
    start_run,
    end_run,
    table_timer,
    get_last_run_info,
)
from etl import ddl
from etl import extract
from etl import transform
from etl import load

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helper – build lookup dicts (natural_hash → surrogate_id) after dim loaded
# ---------------------------------------------------------------------------
def _build_lookup(
    table_name: str, natural_hash_col: str, surrogate_id_col: str
) -> Dict[int, int]:
    """Return {natural_hash: surrogate_id} for a dimension already in DW."""
    query = (
        f"SELECT [{surrogate_id_col}] AS sid, [{natural_hash_col}] AS nhash "
        f"FROM [{table_name}]"
    )
    df = pd.read_sql(query, DW_ENGINE)
    lookup = dict(zip(df["nhash"], df["sid"]))
    logger.debug(f"Lookup built for {table_name}: {len(lookup)} rows (hash→id)")
    return lookup


# ---------------------------------------------------------------------------
# Explicit per-table lookup configuration
# (table_name) -> (natural_hash_col_in_DW, surrogate_pk_col_in_DW)
# Residual-issue-2 fix: column names must exactly match what is written to the
# DW.  _hash_columns(df, ["cbIndice"]) produces "cbIndice_code", not "cb_indice".
# ---------------------------------------------------------------------------
LOOKUP_CONFIG: Dict[str, Tuple[str, str]] = {
    "DIM_DATE":          ("date_valeur",          "id_date"),
    # _hash_columns(["cbIndice"]) → cbIndice_code stored in DW
    "DIM_SEGMENT":       ("cbIndice_code",         "id_segment"),
    # CO_No is stored as a raw integer (not hashed) in DIM_COLLABORATEUR
    "DIM_COLLABORATEUR": ("CO_No",                 "id_collab"),
    "DIM_FAMILLE":       ("FA_CodeFamille_code",   "id_famille"),
    "DIM_CLIENT":        ("CT_Num_code",            "id_client"),
    "DIM_FOURNISSEUR":   ("CT_Num_code",            "id_fournisseur"),
    "DIM_JOURNAL":       ("JO_Num_code",            "id_journal"),
    "DIM_BANQUE":        ("EB_Abrege_code",         "id_banque"),
    "DIM_ARTICLE":       ("AR_Ref_code",            "id_article"),
    # DE_No is stored as a raw integer in DIM_DEPOT (not hashed)
    "DIM_DEPOT":         ("DE_No",                  "id_depot"),
    "DIM_CAISSE":        ("CA_Numero_code",          "id_caisse"),
}

# ---------------------------------------------------------------------------
# Step type alias  (Bug 9 fix: closed Optional bracket before 3rd element)
# ---------------------------------------------------------------------------
Step = Tuple[
    str,                                                        # DW table name
    Callable[..., pd.DataFrame],                                # extract fn
    Optional[Callable[[pd.DataFrame, Dict], pd.DataFrame]],    # transform fn
    Callable[[pd.DataFrame, str, str], None],                   # load fn
]


def _hash_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Apply ``transform.hash_key`` on each column; result column = <col>_code.

    Residual-issue-3 fix: works on a copy so the original DataFrame (and any
    lambda closures that captured it) is not mutated in-place.
    """
    df = df.copy()
    for col in cols:
        df[f"{col}_code"] = df[col].apply(transform.hash_key)
    return df


# ---------------------------------------------------------------------------
# STEPS – FK dependency order matches ddl.ALL_DDL grouping.
# Bug 13: DIM_FOURNISSEUR, DIM_JOURNAL, DIM_BANQUE, FAIT_REGLEMENTS,
#         FAIT_ECRITURES added.
# Bug  8: load_dimension calls now pass explicit key_col for delta mode.
# ---------------------------------------------------------------------------
STEPS: List[Step] = [
    # ── Groupe 1 – no outgoing FK ──────────────────────────────────────────
    (
        "DIM_DATE",
        lambda **kw: pd.DataFrame(),   # generated programmatically below
        None,
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="date_valeur"),
    ),
    # ── Groupe 2 ───────────────────────────────────────────────────────────
    (
        "DIM_SEGMENT",
        lambda **kw: extract.extract_dim_segment(),
        lambda df, lookups: _hash_columns(df, ["cbIndice"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="cbIndice_code"),
    ),
    (
        "DIM_COLLABORATEUR",
        lambda **kw: extract.extract_dim_collaborateur(kw.get("last_run")),
        lambda df, lookups: _hash_columns(df, ["CO_No"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CO_No_code"),
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
        lambda **kw: extract.extract_dim_banque_mag(),
        lambda df, lookups: _hash_columns(df, ["EB_Abrege", "EB_Banque"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="EB_Abrege_code"),
    ),
    # ── Groupe 3 ───────────────────────────────────────────────────────────
    (
        "DIM_FAMILLE",
        lambda **kw: extract.extract_dim_famille(),
        lambda df, lookups: _hash_columns(df, ["FA_CodeFamille", "CL_Code"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="FA_CodeFamille_code"),
    ),
    # ── Groupe 4 ───────────────────────────────────────────────────────────
    (
        "DIM_CLIENT",
        lambda **kw: extract.extract_dim_client_mag(kw.get("last_run")),
        lambda df, lookups: (
            _hash_columns(df, ["CT_Num"])
            .assign(
                id_segment=df["N_CatTarif"].map(lookups.get("DIM_SEGMENT", {})),
                id_collaborateur=df["CO_No"].map(lookups.get("DIM_COLLABORATEUR", {})),
            )
        ),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CT_Num_code"),
    ),
    # ── Groupe 5 ───────────────────────────────────────────────────────────
    (
        "DIM_ARTICLE",
        lambda **kw: extract.extract_dim_article(kw.get("last_run")),
        lambda df, lookups: (
            _hash_columns(df, ["AR_Ref", "FA_CodeFamille", "CT_Num_fourn"])
            .assign(
                id_famille=df["FA_CodeFamille"].map(lookups.get("DIM_FAMILLE", {})),
                id_fournisseur=df["CT_Num_fourn"].map(lookups.get("DIM_FOURNISSEUR", {})),
            )
        ),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="AR_Ref_code"),
    ),
    # ── Groupe 6 ───────────────────────────────────────────────────────────
    (
        "DIM_DEPOT",
        lambda **kw: extract.extract_dim_depot(kw.get("last_run")),
        lambda df, lookups: _hash_columns(df, ["DE_No"]),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DE_No_code"),
    ),
    (
        "DIM_CAISSE",
        lambda **kw: extract.extract_dim_caisse_mag(),
        # CA_No column is hashed and stored as CA_Numero_code to match DDL
        lambda df, lookups: df.assign(
            CA_Numero_code=df["CA_No"].apply(transform.hash_key),
            JO_Num_code=df["JO_Num"].apply(transform.hash_key),
        ),
        lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CA_Numero_code"),
    ),
    # ── Groupe 7 – Facts ───────────────────────────────────────────────────
    (
        "FAIT_LIGNES_VENTE",
        lambda **kw: extract.extract_fait_lignes_vente(kw.get("last_run")),
        # Bug 11 fix: removed id_segment/id_collab — those columns (N_CatTarif,
        # CO_No) belong to DIM_CLIENT extract, not to the fact line extract.
        lambda df, lookups: (
            transform.add_fact_lignes_vente_calcs(df)
            .assign(
                id_date=df["DO_Date"].apply(
                    lambda d: lookups.get("DIM_DATE", {}).get(
                        pd.Timestamp(d).date() if pd.notna(d) else None
                    )
                ),
                id_client=df["CT_Num"].apply(
                    lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
                ),
                id_article=df["AR_Ref"].apply(
                    lambda v: lookups.get("DIM_ARTICLE", {}).get(transform.hash_key(v))
                ),
                id_depot=df["DE_No"].apply(
                    lambda v: lookups.get("DIM_DEPOT", {}).get(transform.hash_key(v))
                ),
                date_extraction=date.today(),
            )
        ),
        lambda df, tbl, mode: load.load_fact(df, tbl, mode),
    ),
    (
        "FAIT_REGLEMENTS",
        lambda **kw: extract.extract_fait_reglements_clients(kw.get("last_run")),
        # Residual-issue-5 fix: join F_DOCENTETE dates so delai_reel_jours
        # and ecart_delai (KPI-07/09) can actually be computed.
        # LB_NbJour from the bordereau serves as the contractual delay term.
        lambda df, lookups: (
            transform.add_fact_reglements_calcs(
                df.merge(
                    extract.extract_docentete_dates()[["DO_Piece", "DO_Date"]],
                    left_on="RT_Num",
                    right_on="DO_Piece",
                    how="left",
                ).rename(columns={"LB_NbJour": "RT_NbJour"})
            ).assign(
                id_date=lambda d: d["RT_Date"].apply(
                    lambda dt: lookups.get("DIM_DATE", {}).get(
                        pd.Timestamp(dt).date() if pd.notna(dt) else None
                    )
                ),
                id_client=lambda d: d["CT_Num"].apply(
                    lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
                ),
                id_banque=lambda d: d["BQ_Num"].apply(
                    lambda v: lookups.get("DIM_BANQUE", {}).get(
                        transform.hash_key(str(v))
                    ) if pd.notna(v) else None
                ),
                id_mode_reg=lambda d: d["RT_Mode"].map(
                    lookups.get("DIM_MODE_REGLEMENT", {})
                ),
                id_etat_reg=lambda d: d["RT_Etat"].map(
                    lookups.get("DIM_ETAT_REGLEMENT", {})
                ),
                date_extraction=date.today(),
            )
        ),
        lambda df, tbl, mode: load.load_fact(df, tbl, mode),
    ),
    # Residual-issue-4 fix: FAIT_ECRITURES now assembles all four type_ligne
    # sources via _assemble_fait_ecritures (see helper below STEPS).
    # extract_fn returns an empty DataFrame; transform_fn does the real work.
    (
        "FAIT_ECRITURES",
        lambda **kw: pd.DataFrame(),
        lambda df, lookups: _assemble_fait_ecritures(
            lookups.get("_last_run"),  # sentinel key set in run_pipeline loop
            lookups,
        ),
        lambda df, tbl, mode: load.load_fact(df, tbl, mode),
    ),
]

# ---------------------------------------------------------------------------
# Helper – assemble all four FAIT_ECRITURES source types
# (Residual issue 4: previously only type_ligne=1 was loaded)
# ---------------------------------------------------------------------------
def _assemble_fait_ecritures(
    last_run: Optional[datetime],
    lookups: Dict,
) -> pd.DataFrame:
    """Union F_ECRITUREC (type 1), F_REGTAXE (type 2), F_ARTSTOCK (type 4),
    F_MVTCAISSE (type 3) into a single FAIT_ECRITURES DataFrame.
    Columns not applicable to a given type are left as NaN.
    """
    today = date.today()

    def _resolve_date(d):
        if pd.isna(d):
            return None
        return lookups.get("DIM_DATE", {}).get(pd.Timestamp(d).date())

    # ── Type 1: comptable ────────────────────────────────────────────────────
    df1 = extract.extract_fait_ecriturec(last_run).assign(
        type_ligne=1,
        id_date=lambda d: d["EC_Date"].apply(_resolve_date),
        id_journal=lambda d: d["JO_Num"].apply(
            lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
        ),
        id_client=lambda d: d["CT_Num"].apply(
            lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
        ),
        date_extraction=today,
    )

    # ── Type 2: TVA ──────────────────────────────────────────────────────────
    df2 = extract.extract_fait_regtaxe(last_run).assign(
        type_ligne=2,
        id_date=lambda d: d["EC_Date"].apply(_resolve_date),
        id_journal=lambda d: d["JO_Num"].apply(
            lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
        ),
        id_client=lambda d: d["CT_Num"].apply(
            lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
        ),
        date_extraction=today,
    )

    # ── Type 3: mouvement caisse ─────────────────────────────────────────────
    df3 = extract.extract_fait_mvtcaisse(last_run).assign(
        type_ligne=3,
        id_date=lambda d: d["MC_Date"].apply(_resolve_date),
        id_caisse=lambda d: d["CA_No"].apply(
            lambda v: lookups.get("DIM_CAISSE", {}).get(transform.hash_key(v))
        ),
        date_extraction=today,
    ).rename(columns={"MC_Date": "EC_Date"})

    # ── Type 4: stock snapshot (always full reload) ──────────────────────────
    df4 = extract.extract_fait_artstock().assign(
        type_ligne=4,
        id_date=today,          # snapshot date
        id_article=lambda d: d["AR_Ref"].apply(
            lambda v: lookups.get("DIM_ARTICLE", {}).get(transform.hash_key(v))
        ),
        id_depot=lambda d: d["DE_No"].apply(
            lambda v: lookups.get("DIM_DEPOT", {}).get(v)
        ),
        date_extraction=today,
    )
    # Apply stock KPI calculations (vectorised, no apply-scalar bug)
    df4 = transform.add_fact_ecritures_calcs(df4)

    # Union all four — pd.concat aligns on column names, fills missing with NaN
    return pd.concat([df1, df2, df3, df4], ignore_index=True)


# ---------------------------------------------------------------------------
# Helper – generate DIM_DATE rows programmatically (2015‑01‑01 → 2030‑12‑31)
# ---------------------------------------------------------------------------
def _generate_dim_date(start: str = "2015-01-01", end: str = "2030-12-31") -> pd.DataFrame:
    dr = pd.date_range(start=start, end=end, freq="D")
    df = pd.DataFrame({"date_valeur": dr})
    df["annee"] = df["date_valeur"].dt.year.astype("Int16")
    df["mois"] = df["date_valeur"].dt.month.astype("Int16")
    df["jour"] = df["date_valeur"].dt.day.astype("Int16")
    # Bug 12 fix: source dtype is UInt32; cast to Int32 to avoid silent overflow
    # for ISO week 53 (which exceeds Int16 max of 32 767 when accumulated).
    df["semaine_iso"] = df["date_valeur"].dt.isocalendar().week.astype("Int32")
    df["jour_semaine"] = df["date_valeur"].dt.weekday + 1   # 1=Mon … 7=Sun
    df["est_weekend"] = (df["jour_semaine"] >= 6).astype("Int16")
    df["exercice"] = None
    return df


# ---------------------------------------------------------------------------
# Main orchestration function
# ---------------------------------------------------------------------------
def run_pipeline() -> None:
    if not acquire_lock():
        logger.error("Another ETL run is active – aborting.")
        sys.exit(1)

    last_run_date, mode = get_last_run_info()
    logger.info(f"Mode détecté : {mode.upper()}")

    ddl.create_all_tables(drop_existing=False)

    run_id = start_run(mode)
    lookups: Dict[str, Dict] = {}
    # Store last_run_date as a sentinel so _assemble_fait_ecritures can use it
    # via the shared lookups dict without changing the Step function signatures.
    lookups["_last_run"] = last_run_date

    # Bug 19 fix: disable all FK constraints before any load in full mode so
    # that dimension loads cannot cause FK violations caught only later.
    if mode == "full":
        with DW_ENGINE.begin() as conn:
            ddl.disable_all_fk(conn)
            logger.info("Full mode: FK constraints disabled for load sequence.")

    try:
        for table_name, extract_fn, transform_fn, load_fn in STEPS:
            with table_timer(run_id, table_name) as ctx:
                logger.info(f"--- Processing {table_name} ({mode}) ---")

                # 1️⃣ Extraction
                df_raw = extract_fn(last_run=last_run_date)

                # Special case: DIM_DATE is generated programmatically.
                if table_name == "DIM_DATE":
                    df = _generate_dim_date()
                elif transform_fn is not None:
                    # 2️⃣ Transformation
                    df = transform_fn(df_raw, lookups)
                else:
                    df = df_raw

                # 3️⃣ Load
                load_fn(df, table_name, mode)

                # 4️⃣ Build lookup for downstream FK resolution (Bug 10 fix).
                if table_name in LOOKUP_CONFIG:
                    natural_hash_col, surrogate_id_col = LOOKUP_CONFIG[table_name]
                    lookups[table_name] = _build_lookup(
                        table_name, natural_hash_col, surrogate_id_col
                    )

                ctx["rows_inserted"] = len(df)
                ctx["rows_updated"] = 0

        # Bug 19 fix: re-enable and validate FK constraints after all loads.
        if mode == "full":
            with DW_ENGINE.begin() as conn:
                ddl.enable_all_fk(conn)
                logger.info("Full mode: FK constraints re-enabled and validated.")

        end_run(run_id, "SUCCESS")

    except Exception as exc:
        tb = traceback.format_exc()
        logger.exception("ETL pipeline failed")
        end_run(run_id, "ERROR", error_msg=str(exc))
        raise


if __name__ == "__main__":
    run_pipeline()
