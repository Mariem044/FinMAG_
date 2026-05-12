from __future__ import annotations

import hashlib
import sys
import warnings
from datetime import datetime, date
from typing import Callable, Dict, List, Tuple, Optional

import pandas as pd
from sqlalchemy import text

warnings.filterwarnings(
    "ignore",
    message="The behavior of DataFrame concatenation with empty or all-NA entries",
    category=FutureWarning,
)

from etl.config import DW_ENGINE, SEGMENTS, DIM_DATE_START, DIM_DATE_END, FENETRE_RFM_JOURS
from etl.utils.logger import get_logger
from etl.utils.audit import (
    acquire_lock, start_run, end_run, release_lock,
    table_timer, get_last_run_info,
)
from etl import ddl, extract, transform, load

logger = get_logger(__name__)





KPI18_MIGRATION: list[tuple[str, str]] = [
    (
        "DIM_CLIENT.rfm_recence_jours",
        "IF COL_LENGTH('DIM_CLIENT','rfm_recence_jours') IS NULL "
        "ALTER TABLE [DIM_CLIENT] ADD rfm_recence_jours INT NULL",
    ),
    (
        "DIM_CLIENT.rfm_frequence",
        "IF COL_LENGTH('DIM_CLIENT','rfm_frequence') IS NULL "
        "ALTER TABLE [DIM_CLIENT] ADD rfm_frequence INT NULL",
    ),
    (
        "DIM_CLIENT.rfm_montant_12m",
        "IF COL_LENGTH('DIM_CLIENT','rfm_montant_12m') IS NULL "
        "ALTER TABLE [DIM_CLIENT] ADD rfm_montant_12m NUMERIC(18,4) NULL",
    ),
    (
        "DIM_CLIENT.rfm_score",
        "IF COL_LENGTH('DIM_CLIENT','rfm_score') IS NULL "
        "ALTER TABLE [DIM_CLIENT] ADD rfm_score VARCHAR(20) NULL",
    ),
    (
        "FAIT_REGLEMENTS.BR_TauxAgios",
        "IF COL_LENGTH('FAIT_REGLEMENTS','BR_TauxAgios') IS NULL "
        "ALTER TABLE [FAIT_REGLEMENTS] ADD BR_TauxAgios NUMERIC(18,4) NULL",
    ),
    (
        "FAIT_REGLEMENTS.BR_TMM",
        "IF COL_LENGTH('FAIT_REGLEMENTS','BR_TMM') IS NULL "
        "ALTER TABLE [FAIT_REGLEMENTS] ADD BR_TMM NUMERIC(18,4) NULL",
    ),
]


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

Step = Tuple[
    str,
    Callable[..., pd.DataFrame],
    Optional[Callable[[pd.DataFrame, Dict], pd.DataFrame]],
    Callable[[pd.DataFrame, str, str], None],
]






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
    date_lookup = lookups.get("DIM_DATE", {})
    id_val = date_lookup.get(today)
    if id_val is not None:
        return id_val
    if date_lookup:
        max_date = max(date_lookup.keys())
        id_val   = date_lookup[max_date]
        logger.warning(
            f"Today ({today}) not in DIM_DATE — fallback to {max_date} "
            f"(id_date={id_val}). Consider extending DIM_DATE_END."
        )
        return id_val
    logger.error("DIM_DATE lookup is empty — stock snapshot id_date will be NULL")
    return None






def _bucket_from_echeance(row) -> Optional[int]:
    if row.get("DR_Regle", 1) != 0:
        return None
    echeance = row.get("LB_EcheanceReg")
    if echeance is None or pd.isna(echeance):
        return None
    try:
        days_overdue = (date.today() - pd.Timestamp(echeance).date()).days
    except Exception:
        return None
    if days_overdue <= 0:
        return None
    if days_overdue <= 30:
        return 0
    if days_overdue <= 60:
        return 1
    if days_overdue <= 90:
        return 2
    return 3






def _transform_dim_famille(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[
            "FA_CodeFamille_code", "niveau_0_code", "niveau_1_code", "niveau_2_code",
        ])
    df = df.copy()
    df["FA_CodeFamille_code"] = df["FA_CodeFamille"].apply(transform.hash_key)
    df["niveau_0_code"]       = df["CL_No1"].apply(transform.hash_key)
    df["niveau_1_code"]       = df["CL_No2"].apply(transform.hash_key)
    df["niveau_2_code"]       = df["CL_No3"].apply(transform.hash_key)
    return df[["FA_CodeFamille_code", "niveau_0_code", "niveau_1_code", "niveau_2_code"]]






def _add_static_label(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "code_type_mvt" in df.columns and "MC_TypeMvt" not in df.columns:
        df = df.rename(columns={"code_type_mvt": "MC_TypeMvt"})
    df["libelle_type_mvt"] = df["MC_TypeMvt"].map(
        lambda v: f"Mouvement {int(v)}" if pd.notna(v) else None
    )
    return df






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






def _assemble_fait_ecritures(
    last_run: Optional[datetime],
    lookups:  Dict,
) -> pd.DataFrame:
    today    = date.today()
    today_id = _resolve_today_id(lookups, today)

    def _resolve_date(d):
        if pd.isna(d):
            return None
        return lookups.get("DIM_DATE", {}).get(pd.Timestamp(d).date())

    df1 = (
        extract.extract_fait_ecriturec(last_run)
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
            id_sens=lambda d: d["EC_Sens"].apply(
                lambda v: _lookup_code(lookups, "DIM_SENS_ECRITURE", v)
            ),
            id_type_tva=lambda d: d["JO_Type"].apply(
                lambda v: _lookup_code(
                    lookups, "DIM_TYPE_TVA",
                    1 if v == 1 else 2 if v == 0 else None,
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
        extract.extract_fait_regtaxe(last_run)
        .assign(
            type_ligne   =2,
            id_type_ligne=lambda d: d.apply(lambda _: _lookup_code(lookups, "DIM_TYPE_LIGNE", 2), axis=1),
            id_date      =lambda d: d["EC_Date"].apply(_resolve_date),
            id_journal   =lambda d: d["JO_Num"].apply(
                lambda v: lookups.get("DIM_JOURNAL", {}).get(transform.hash_key(v))
            ),
            id_banque    =pd.NA,
            id_client=lambda d: d["CT_Num"].apply(
                lambda v: lookups.get("DIM_CLIENT", {}).get(transform.hash_key(v))
            ),
            id_type_tva=lambda d: d["JO_Type"].apply(
                lambda v: _lookup_code(
                    lookups, "DIM_TYPE_TVA",
                    1 if v == 1 else 2 if v == 0 else None,
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
            id_banque    =pd.NA,
            id_caisse=lambda d: d["CA_No"].apply(
                lambda v: lookups.get("DIM_CAISSE", {}).get(transform.hash_key(v))
            ),
            id_type_mvt=lambda d: d["MC_TypeMvt"].apply(
                lambda v: _lookup_code(lookups, "DIM_TYPE_MVT_CAISSE", v)
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

    df4 = (
        extract.extract_fait_artstock()
        .assign(
            type_ligne   =4,
            id_type_ligne=lambda d: d.apply(lambda _: _lookup_code(lookups, "DIM_TYPE_LIGNE", 4), axis=1),
            id_date      =today_id,
            id_journal   =pd.NA,
            id_banque    =pd.NA,
            id_client    =pd.NA,
            id_sens      =pd.NA,
            id_type_tva  =pd.NA,
            id_type_mvt  =pd.NA,
            id_caisse    =pd.NA,
            id_article   =lambda d: d["AR_Ref"].apply(
                lambda v: lookups.get("DIM_ARTICLE", {}).get(transform.hash_key(v))
            ),
            id_depot=lambda d: d["DE_No"].apply(
                lambda v: lookups.get("DIM_DEPOT", {}).get(v)
            ),
            source_hash=lambda d: d.apply(
                lambda row: _source_hash("ARTSTOCK", row.get("AR_Ref"), row.get("DE_No")),
                axis=1,
            ),
            date_extraction=today,
        )
    )
    df4 = transform.add_fact_ecritures_calcs(df4)

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

    before = len(df)
    df = df.drop_duplicates(subset=["source_hash"], keep="last")
    if len(df) != before:
        logger.warning(f"FAIT_ECRITURES: dropped {before - len(df)} duplicate source_hash rows")

    return df






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
        INNER JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
        INNER JOIN (
            SELECT flv.id_article, SUM(flv.DL_Qte) AS qte_vendue_365j
            FROM FAIT_LIGNES_VENTE flv
            JOIN DIM_DATE d ON d.id_date = flv.id_date
            JOIN DIM_DOMAINE dom ON dom.id_domaine = flv.id_domaine
            WHERE d.date_val >= DATEADD(DAY, -365, CAST(GETDATE() AS DATE))
              AND dom.DO_Domaine = 0
            GROUP BY flv.id_article
        ) sub ON sub.id_article = fe.id_article
        WHERE tl.type_ligne = 4
    """
    with DW_ENGINE.begin() as conn:
        conn.execute(text(sql))
    logger.info("dsi_jours computed successfully.")


def _compute_rfm_scores() -> None:
    sql = f"""
        UPDATE c
        SET
            c.rfm_recence_jours  = rfm.recence_jours,
            c.rfm_frequence      = rfm.frequence,
            c.rfm_montant_12m    = rfm.montant_12m,
            c.rfm_score          = CASE
                WHEN rfm.recence_jours <= 30 AND rfm.frequence >= 4 THEN 'Champion'
                WHEN rfm.recence_jours <= 60 AND rfm.frequence >= 3 THEN 'Fidèle'
                WHEN rfm.recence_jours <= 90 THEN 'À risque'
                ELSE 'Dormant'
            END
        FROM DIM_CLIENT c
        INNER JOIN (
            SELECT
                v.id_client,
                DATEDIFF(DAY, MAX(d.date_val), CAST(GETDATE() AS DATE)) AS recence_jours,
                COUNT(DISTINCT v.DO_Piece_hash)                          AS frequence,
                SUM(v.DL_MontantHT)                                      AS montant_12m
            FROM FAIT_LIGNES_VENTE v
            JOIN DIM_DATE d   ON d.id_date   = v.id_date
            JOIN DIM_DOMAINE dom ON dom.id_domaine = v.id_domaine
            WHERE d.date_val >= DATEADD(DAY, -{FENETRE_RFM_JOURS}, CAST(GETDATE() AS DATE))
              AND dom.DO_Domaine = 0
            GROUP BY v.id_client
        ) rfm ON rfm.id_client = c.id_client
    """
    with DW_ENGINE.begin() as conn:
        conn.execute(text(sql))
    logger.info(f"RFM scores computed (window={FENETRE_RFM_JOURS} days).")


def _load_dim_date(df: pd.DataFrame, table: str, mode: str) -> None:
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
                        row.get("DO_Piece"), row.get("DL_Ligne"), row.get("AR_Ref"),
                    ),
                    axis=1,
                ),
                date_extraction=date.today(),
            )
        )
    return _transform


STEPS: List[Step] = [

    ("DIM_DATE",
     lambda **kw: pd.DataFrame(),
     None,
     lambda df, tbl, mode: _load_dim_date(df, tbl, mode)),

    ("DIM_DOMAINE",
     lambda **kw: extract.extract_static_dims()["DIM_DOMAINE"],
     None,
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DO_Domaine")),

    ("DIM_TYPE_DOC",
     lambda **kw: extract.extract_static_dims()["DIM_TYPE_DOC"],
     None,
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DO_Type")),

    ("DIM_MODE_REGLEMENT",
     lambda **kw: extract.extract_static_dims()["DIM_MODE_REGLEMENT"],
     None,
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="RT_Mode")),

    ("DIM_ETAT_REGLEMENT",
     lambda **kw: extract.extract_static_dims()["DIM_ETAT_REGLEMENT"],
     None,
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="RT_Etat")),

    ("DIM_ETAT_DOCREGL",
     lambda **kw: extract.extract_static_dims()["DIM_ETAT_DOCREGL"],
     None,
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DR_Regle")),

    ("DIM_TYPE_LIGNE",
     lambda **kw: extract.extract_static_dims()["DIM_TYPE_LIGNE"],
     None,
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="type_ligne")),

    ("DIM_SENS_ECRITURE",
     lambda **kw: extract.extract_static_dims()["DIM_SENS_ECRITURE"],
     None,
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="EC_Sens")),

    ("DIM_TYPE_TVA",
     lambda **kw: extract.extract_static_dims()["DIM_TYPE_TVA"],
     None,
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="type_tva")),

    ("DIM_TYPE_MVT_CAISSE",
     lambda **kw: extract.extract_dim_type_mvt_caisse(),
     lambda df, lookups: _add_static_label(df),
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="MC_TypeMvt")),

    ("DIM_SEGMENT",
     lambda **kw: extract.extract_dim_segment(),
     lambda df, lookups: (
         _hash_columns(df, ["cbIndice"])
         .assign(
             CT_PrixTTC=lambda d: pd.to_numeric(
                 d["CT_PrixTTC"], errors="coerce"
             ).fillna(0).astype("Int16"),
             libelle_segment=lambda d: (
                 d["cbIndice"]
                 .map(lambda v: SEGMENTS.get(int(v), f"Segment {v}"))
                 .str[:100]
             ),
         )
     ),
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="cbIndice_code")),

    ("DIM_COLLABORATEUR",
     lambda **kw: extract.extract_dim_collaborateur(kw.get("last_run")),
     lambda df, lookups: df.assign(
         CO_Fonction=lambda d: (
             pd.to_numeric(d["CO_Fonction"], errors="coerce")
             .pipe(lambda s: s.astype(object).where(s.notna(), other=None))
             .astype("Int32")
         )
     ),
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CO_No")),

    ("DIM_JOURNAL",
     lambda **kw: extract.extract_dim_journal(kw.get("last_run")),
     lambda df, lookups: _hash_columns(df, ["JO_Num"]),
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="JO_Num_code")),

    ("DIM_FOURNISSEUR",
     lambda **kw: extract.extract_dim_fournisseur(kw.get("last_run")),
     lambda df, lookups: _hash_columns(df, ["CT_Num"]),
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CT_Num_code")),

    ("DIM_BANQUE",
     lambda **kw: pd.DataFrame(),
     lambda df, lookups: _assemble_dim_banque(lookups),
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="EB_Abrege_code")),

    ("DIM_FAMILLE",
     lambda **kw: extract.extract_dim_famille(),
     lambda df, lookups: _transform_dim_famille(df),
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="FA_CodeFamille_code")),

    ("DIM_CLIENT",
     lambda **kw: extract.extract_dim_client_mag(kw.get("last_run")),
     lambda df, lookups: (
         df.copy()
         .merge(extract.extract_dim_client_grt(), on="CT_Num", how="left")
         .pipe(_hash_columns, ["CT_Num"])
         .assign(
             id_segment=lambda d: d["N_CatTarif"].apply(
                 lambda v: lookups.get("DIM_SEGMENT", {}).get(transform.hash_key(v))
             ),
             id_collab=lambda d: d["CO_No"].map(lookups.get("DIM_COLLABORATEUR", {})),
         )
         .drop_duplicates(subset=["CT_Num_code"], keep="last")
     ),
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CT_Num_code")),

    ("DIM_ARTICLE",
     lambda **kw: extract.extract_dim_article(kw.get("last_run")),
     lambda df, lookups: (
         _hash_columns(df, ["AR_Ref", "FA_CodeFamille", "CT_Num_fourn"])
         .assign(
             id_famille=lambda d: d["FA_CodeFamille"].apply(
                 lambda v: lookups.get("DIM_FAMILLE", {}).get(transform.hash_key(v))
             ),
             id_fournisseur=lambda d: d["CT_Num_fourn"].apply(
                 lambda v: lookups.get("DIM_FOURNISSEUR", {}).get(transform.hash_key(v))
             ),
         )
     ),
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="AR_Ref_code")),

    ("DIM_DEPOT",
     lambda **kw: extract.extract_dim_depot(kw.get("last_run")),
     lambda df, lookups: df.copy(),
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="DE_No")),

    ("DIM_CAISSE",
     lambda **kw: pd.DataFrame(),
     lambda df, lookups: _assemble_dim_caisse(lookups),
     lambda df, tbl, mode: load.load_dimension(df, tbl, mode, key_col="CA_Numero_code")),



    ("FAIT_LIGNES_VENTE",
     lambda **kw: extract.extract_fait_lignes_vente(kw.get("last_run")),
     None,
     lambda df, tbl, mode: load.load_fact(df, tbl, mode)),

    ("FAIT_REGLEMENTS",
     lambda **kw: pd.DataFrame(),
     None,
     lambda df, tbl, mode: load.load_fact(df, tbl, mode)),

    ("FAIT_ECRITURES",
     lambda **kw: pd.DataFrame(),
     None,
     lambda df, tbl, mode: load.load_fact(df, tbl, mode)),
]






def run_pipeline() -> None:

    if not acquire_lock():
        logger.error("Another ETL run is active.")
        sys.exit(1)

    last_run_date, mode = get_last_run_info()
    logger.info(f"Mode: {mode.upper()}")

    ddl.create_all_tables(drop_existing=False)
    ddl.apply_schema_migrations()


    with DW_ENGINE.begin() as conn:
        for label, sql in KPI18_MIGRATION:
            try:
                conn.execute(text(sql))
                logger.info(f"  [MIGRATION OK] {label}")
            except Exception as exc:
                logger.warning(f"  [MIGRATION WARN] {label}: {exc}")

    run_id = start_run(mode)
    run_finished = False
    fk_disabled  = False

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

        for (table_name, extract_fn, _transform_fn, load_fn) in STEPS:
            with table_timer(run_id, table_name) as ctx:
                logger.info(f"--- Processing {table_name} ---")

                transform_fn = _RUNTIME_TRANSFORMS.get(table_name, _transform_fn)

                df_raw = extract_fn(last_run=last_run_date)

                if table_name == "DIM_DATE":
                    df = _generate_dim_date()
                elif transform_fn is not None:
                    df = transform_fn(df_raw, lookups)
                else:
                    df = df_raw

                load_fn(df, table_name, mode)

                if table_name in LOOKUP_CONFIG:
                    nat_col, surr_col = LOOKUP_CONFIG[table_name]
                    lookups[table_name] = _build_lookup(table_name, nat_col, surr_col)

                ctx["rows_inserted"] = len(df)
                ctx["rows_updated"]  = 0

        logger.info("--- Computing dsi_jours ---")
        _compute_dsi_jours()

        logger.info("--- Computing RFM scores (KPI-18) ---")
        _compute_rfm_scores()

        end_run(run_id, "SUCCESS")
        run_finished = True

    except Exception as exc:
        logger.exception("ETL pipeline failed")
        end_run(run_id, "ERROR", error_msg=str(exc))
        run_finished = True
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
    run_pipeline()

