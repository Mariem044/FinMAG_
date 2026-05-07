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

from etl.config import SEGMENTS
import sys
import traceback
from datetime import datetime, date
from typing import Callable, Dict, List, Tuple, Optional

import pandas as pd
from sqlalchemy import text

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
    lookup = dict(zip(df["nhash"], df["sid"]))

    logger.debug(f"Lookup built for {table_name}: {len(lookup)} rows")
    return lookup


LOOKUP_CONFIG: Dict[str, Tuple[str, str]] = {
    "DIM_DATE":          ("date_valeur",       "id_date"),
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
            id_date=lambda d: d["EC_Date"].apply(_resolve_date),
            id_journal=lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
            ),
            id_client=lambda d: d["CT_Num"].apply(
                lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
            ),
            date_extraction=today,
        )
    )

    # TYPE 2 — TVA
    df2 = (
        extract.extract_fait_regtaxe(last_run)
        .assign(
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
    )

    # TYPE 3 — mouvements caisse
    df3 = (
        extract.extract_fait_mvtcaisse(last_run)
        .assign(
            type_ligne=3,
            id_date=lambda d: d["MC_Date"].apply(_resolve_date),
            id_caisse=lambda d: d["CA_No"].apply(
                lambda v: lookups.get("DIM_CAISSE", {}).get(transform.hash_key(v))
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
            id_date=lookups.get("DIM_DATE", {}).get(today),
            id_article=lambda d: d["AR_Ref"].apply(
                lambda v: lookups.get("DIM_ARTICLE", {}).get(transform.hash_key(v))
            ),
            id_depot=lambda d: d["DE_No"].apply(
                lambda v: lookups.get("DIM_DEPOT", {}).get(v)
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
        INNER JOIN (
            SELECT
                id_article,
                SUM(DL_Qte) AS qte_vendue_365j
            FROM FAIT_LIGNES_VENTE
            WHERE date_extraction >= DATEADD(DAY, -365, CAST(GETDATE() AS DATE))
            GROUP BY id_article
        ) sub ON sub.id_article = fe.id_article
        WHERE fe.type_ligne = 4
    """
    with DW_ENGINE.begin() as conn:
        conn.execute(text(sql))
    logger.info("dsi_jours computed successfully.")


# ===========================================================================
# DATE DIM
# ===========================================================================

def _generate_dim_date(
    start: str = "2015-01-01",
    end: str = "2030-12-31",
) -> pd.DataFrame:

    dr = pd.date_range(start=start, end=end, freq="D")
    df = pd.DataFrame({"date_valeur": dr})
    df["annee"]      = df["date_valeur"].dt.year.astype("Int16")
    df["mois"]       = df["date_valeur"].dt.month.astype("Int16")
    df["jour"]       = df["date_valeur"].dt.day.astype("Int16")
    df["semaine_iso"]= df["date_valeur"].dt.isocalendar().week.astype("Int32")
    df["jour_semaine"]= df["date_valeur"].dt.weekday + 1
    df["est_weekend"]= (df["jour_semaine"] >= 6).astype("Int16")
    df["exercice"]   = None
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
        lambda df, lookups: _hash_columns(df, ["FA_CodeFamille", "CL_Code"]),
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
                id_famille=df["FA_CodeFamille"].map(
                    lookups.get("DIM_FAMILLE", {})
                ),
                id_fournisseur=df["CT_Num_fourn"].map(
                    lookups.get("DIM_FOURNISSEUR", {})
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
                id_client=df["CT_Num"].apply(
                    lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
                ),
                id_article=df["AR_Ref"].apply(
                    lambda v: lookups.get("DIM_ARTICLE", {}).get(transform.hash_key(v))
                ),
                id_depot=df["DE_No"].apply(
                    lambda v: lookups.get("DIM_DEPOT", {}).get(v)
                ),
                date_extraction=date.today(),
            )
        ),
        lambda df, tbl, mode: load.load_fact(df, tbl, mode),
    ),

    # BUG 1, 6 FIX — FAIT_REGLEMENTS
    (
        "FAIT_REGLEMENTS",
        lambda **kw: extract.extract_fait_reglements_clients(kw.get("last_run")),

        lambda df, lookups: (
            # BUG 1 FIX: use locally defined _add_fact_reglements_bucket
            # BUG 6 FIX: join on DO_Piece (document key), not RT_Num (règlement key)
            _add_fact_reglements_bucket(
                transform.add_fact_reglements_calcs(
                    df.merge(
                        extract.extract_docentete_dates()[["DO_Piece", "DO_Date"]],
                        on="DO_Piece",
                        how="left",
                    )
                    .rename(columns={"LB_NbJour": "RT_NbJour"})
                )
            )
            .assign(
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
                RT_Rapproche=lambda d: (
                    d["BR_Rapproch"].fillna(0).astype("Int16")
                    if "BR_Rapproch" in d.columns else 0
                ),
                date_extraction=date.today(),
            )
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

    run_id = start_run(mode)

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

    except Exception as exc:
        logger.exception("ETL pipeline failed")
        end_run(run_id, "ERROR", error_msg=str(exc))
        raise

    finally:
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