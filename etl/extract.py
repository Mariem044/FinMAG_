from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pandas as pd
from sqlalchemy import text

from etl.config import MAG_ENGINE, GRT_ENGINE, DIM_DATE_START, DIM_DATE_END
from etl.utils.logger import get_logger

logger = get_logger(__name__)

import os as _os
_QUERY_TIMEOUT: int = int(_os.environ["ETL_QUERY_TIMEOUT"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read(engine, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            text(sql),
            conn.execution_options(timeout=_QUERY_TIMEOUT),
            params=params or {},
        )
    logger.debug(f"Extracted {len(df)} rows — {sql[:80].strip()}...")
    return df


def _delta_filter(col: str, last_run: Optional[datetime]) -> tuple[str, dict]:
    import re as _re
    if not _re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", col):
        raise ValueError(f"Unsafe column name: {col!r}")
    if last_run is None:
        return "", {}
    # cbModification is unreliable in Sage — fall back to date-based filter
    # using the document/entry date column instead
    date_col = col
    if col.endswith("cbModification"):
        # derive the date column from the table alias
        prefix = col.split(".")[0] + "." if "." in col else ""
        date_col_map = {
            "dl.cbModification":  "dl.DO_Date",
            "a.cbModification":   "a.cbModification",  # articles: no reliable date col, keep as-is
            "cbModification":     "cbModification",
            "ec.cbModification":  "ec.EC_Date",
            "rt.cbModification":  "ec.EC_Date",
        }
        date_col = date_col_map.get(col, col)
        logger.debug(f"_delta_filter: remapped {col!r} → {date_col!r}")
    return f" AND {date_col} >= :last_run", {"last_run": last_run}


def _validate_columns(df: pd.DataFrame, required_cols: list[str], source_name: str) -> None:
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{source_name} missing columns: {missing}")


def _column_exists(engine, table: str, column: str) -> bool:
    sql = (
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = :tbl AND COLUMN_NAME = :col"
    )
    with engine.connect() as conn:
        return conn.execute(text(sql), {"tbl": table, "col": column}).scalar() > 0


def _table_exists(engine, table: str) -> bool:
    sql = (
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_NAME = :tbl AND TABLE_TYPE = 'BASE TABLE'"
    )
    with engine.connect() as conn:
        return conn.execute(text(sql), {"tbl": table}).scalar() > 0


# ---------------------------------------------------------------------------
# Dimension extracts
# ---------------------------------------------------------------------------

def extract_exercices_fiscaux() -> list[tuple[date, date]]:
    sql = """
        SELECT
            D_DebutExo01, D_FinExo01,
            D_DebutExo02, D_FinExo02,
            D_DebutExo03, D_FinExo03,
            D_DebutExo04, D_FinExo04,
            D_DebutExo05, D_FinExo05
        FROM P_DOSSIER
    """
    try:
        df = _read(MAG_ENGINE, sql)
        exos = []
        for i in range(1, 6):
            debut = df.iloc[0].get(f"D_DebutExo0{i}")
            fin   = df.iloc[0].get(f"D_FinExo0{i}")
            if pd.notna(debut) and pd.notna(fin):
                exos.append((pd.Timestamp(debut).date(), pd.Timestamp(fin).date()))
        logger.info(f"Fiscal years loaded: {len(exos)}")
        return exos
    except Exception as exc:
        logger.warning(f"Cannot read P_DOSSIER: {exc}")
        return []


def extract_dim_segment() -> pd.DataFrame:
    sql = """
        SELECT cbIndice, CT_PrixTTC
        FROM P_CATTARIF
        WHERE cbIndice BETWEEN 1 AND 5
    """
    return _read(MAG_ENGINE, sql)


def extract_dim_collaborateur(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_clause, params = _delta_filter("cbModification", last_run)
    sql = f"""
        SELECT CO_No, CO_Fonction, CO_Sommeil
        FROM F_COLLABORATEUR
        WHERE 1=1 {delta_clause}
    """
    return _read(MAG_ENGINE, sql, params)


def extract_dim_famille() -> pd.DataFrame:
    """
    Extract product families including FA_Intitule label.
    This label is propagated to DIM_FAMILLE and DIM_ARTICLE so the UI
    never shows raw hash codes.
    """
    sql = """
        SELECT FA_CodeFamille, FA_Intitule, CL_No1, CL_No2, CL_No3, CL_No4
        FROM F_FAMILLE
        WHERE FA_Type = 0
    """
    df = _read(MAG_ENGINE, sql)
    # Ensure FA_Intitule is never None/NaN — fall back to code string so UI
    # always has a human-readable label even for unconfigured families.
    if "FA_Intitule" in df.columns:
        df["FA_Intitule"] = (
            df["FA_Intitule"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str[:100]
        )
        missing = df["FA_Intitule"] == ""
        if missing.any():
            df.loc[missing, "FA_Intitule"] = (
                "Famille " + df.loc[missing, "FA_CodeFamille"].astype(str)
            )
    logger.info(f"F_FAMILLE extracted: {len(df)} rows")
    return df


def extract_dim_fournisseur(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_clause, params = _delta_filter("cbModification", last_run)
    sql = f"""
        SELECT CT_Num, CT_Sommeil, CT_Encours, CT_SvCA
        FROM F_COMPTET
        WHERE CT_Type = 1 {delta_clause}
    """
    return _read(MAG_ENGINE, sql, params)


def extract_dim_article(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_clause, params = _delta_filter("a.cbModification", last_run)
    sql = f"""
        SELECT
            a.AR_Ref,
            a.FA_CodeFamille,
            af.CT_Num AS CT_Num_fourn,
            a.AR_Sommeil,
            a.AR_PrixAch,
            a.AR_SuiviStock
        FROM F_ARTICLE a
        LEFT JOIN F_ARTFOURNISS af
            ON af.AR_Ref = a.AR_Ref AND af.AF_Principal = 1
        WHERE 1=1 {delta_clause}
    """
    return _read(MAG_ENGINE, sql, params)


def extract_dim_client_mag(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_clause, params = _delta_filter("cbModification", last_run)
    sql = f"""
        SELECT CT_Num, CT_Sommeil, N_CatTarif, CO_No, CT_Encours, CT_SvCA,
               CT_Ville, CT_CodeRegion, CT_Intitule
        FROM F_COMPTET
        WHERE CT_Type = 0 {delta_clause}
    """
    return _read(MAG_ENGINE, sql, params)


def extract_dim_client_grt() -> pd.DataFrame:
    if _column_exists(GRT_ENGINE, "F_COMPTET", "CT_EchustTroisMois"):
        echust_col = "CT_EchustTroisMois AS CT_EchusTroisMois"
        logger.debug("GRT F_COMPTET: using CT_EchustTroisMois (Sage typo variant)")
    elif _column_exists(GRT_ENGINE, "F_COMPTET", "CT_EchusTroisMois"):
        echust_col = "CT_EchusTroisMois"
        logger.debug("GRT F_COMPTET: using CT_EchusTroisMois (standard spelling)")
    else:
        echust_col = "NULL AS CT_EchusTroisMois"
        logger.warning(
            "GRT F_COMPTET: neither CT_EchustTroisMois nor CT_EchusTroisMois "
            "found — defaulting to NULL"
        )

    sql = f"""
        SELECT
            CT_NUM AS CT_Num,
            CT_SoldeActuel,
            CT_Engagement,
            CT_ChiffreAffaire,
            CT_EchusUnMois,
            CT_EchusDeuxMois,
            {echust_col},
            CT_EchusPlusTroisMois,
            CT_MoyenneDelaiPayement,
            CT_MoyenneDelaiImpaye
        FROM F_COMPTET
    """
    df = _read(GRT_ENGINE, sql)
    _validate_columns(df, ["CT_Num", "CT_EchusTroisMois"], "extract_dim_client_grt")
    return df


def extract_dim_depot(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_clause, params = _delta_filter("cbModification", last_run)
    sql = f"""
        SELECT DE_No, DE_Principal
        FROM F_DEPOT
        WHERE 1=1 {delta_clause}
    """
    return _read(MAG_ENGINE, sql, params)


def extract_dim_journal(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_clause, params = _delta_filter("cbModification", last_run)
    sql = f"""
        SELECT JO_Num, JO_Type
        FROM F_JOURNAUX
        WHERE 1=1 {delta_clause}
    """
    return _read(MAG_ENGINE, sql, params)


def extract_dim_banque_mag() -> pd.DataFrame:
    sql = """
        SELECT EB_Abrege, EB_Banque
        FROM F_EBANQUE
    """
    return _read(MAG_ENGINE, sql)


def extract_dim_banque_grt() -> pd.DataFrame:
    return pd.DataFrame(columns=["EB_Abrege", "EB_Banque"])


def extract_dim_caisse_mag() -> pd.DataFrame:
    check_sql = (
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = 'F_CAISSE' AND COLUMN_NAME = 'CA_Type'"
    )
    with MAG_ENGINE.connect() as conn:
        has_ca_type = conn.execute(text(check_sql)).scalar() > 0

    if has_ca_type:
        sql = "SELECT CA_No, JO_Num, DE_No, CO_No, CA_Type FROM F_CAISSE"
    else:
        logger.warning("F_CAISSE.CA_Type not found in MAG — defaulting to NULL")
        sql = "SELECT CA_No, JO_Num, DE_No, CO_No, NULL AS CA_Type FROM F_CAISSE"

    return _read(MAG_ENGINE, sql)


# ---------------------------------------------------------------------------
# Fact extracts — purchases / sales
# ---------------------------------------------------------------------------

def extract_fait_lignes_achat(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_clause, params = _delta_filter("dl.cbModification", last_run)
    sql = f"""
        SELECT
            dl.DO_Domaine,
            dl.DO_Type,
            dl.CT_Num,
            dl.DO_Piece,
            dl.DL_Ligne,
            dl.DO_Date,
            dl.AR_Ref,
            dl.DL_Qte,
            dl.DL_PrixUnitaire,
            dl.DL_Taxe1,
            dl.DL_MontantHT,
            dl.DL_MontantTTC,
            dl.DL_CMUP,
            dl.DL_PrixRU,
            de.DO_TxEscompte,
            de.DO_TotalHT,
            de.DO_TotalHTNet,
            de.DO_TotalTTC,
            de.DO_NetAPayer,
            de.DO_MontantRegle
        FROM F_DOCLIGNE dl
        INNER JOIN F_DOCENTETE de
            ON  de.DO_Domaine = dl.DO_Domaine
            AND de.DO_Type    = dl.DO_Type
            AND de.DO_Piece   = dl.DO_Piece
        WHERE dl.DO_Domaine = 1
          AND dl.DO_Type IN (16, 17)
          AND dl.DL_MontantHT IS NOT NULL
          {delta_clause}
    """
    return _read(MAG_ENGINE, sql, params)


def extract_fait_lignes_vente(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_clause, params = _delta_filter("dl.cbModification", last_run)
    sql = f"""
        SELECT
            dl.DO_Domaine,
            dl.DO_Type,
            dl.CT_Num,
            dl.DO_Piece,
            dl.DL_Ligne,
            dl.DO_Date,
            dl.AR_Ref,
            dl.DL_Qte,
            dl.DL_PrixUnitaire,
            dl.DL_Taxe1,
            dl.DL_MontantHT,
            dl.DL_MontantTTC,
            dl.DL_CMUP,
            dl.DL_PrixRU,
            de.DO_TxEscompte,
            de.DO_TotalHT,
            de.DO_TotalHTNet,
            de.DO_TotalTTC,
            de.DO_NetAPayer,
            de.DO_MontantRegle
        FROM F_DOCLIGNE dl
        INNER JOIN F_DOCENTETE de
            ON  de.DO_Domaine = dl.DO_Domaine
            AND de.DO_Type    = dl.DO_Type
            AND de.DO_Piece   = dl.DO_Piece
        WHERE dl.DO_Domaine = 0
          AND dl.DO_Type IN (6, 7)
          AND dl.DL_MontantHT IS NOT NULL
          {delta_clause}
    """
    return _read(MAG_ENGINE, sql, params)


def extract_fait_ecriturec(last_run: Optional[datetime] = None) -> pd.DataFrame:
    """
    Extract accounting entries from F_ECRITUREC.
    Only rows with a non-NULL EC_Montant are fetched so the pipeline never
    loads zero-amount phantom rows.
    """
    delta_clause, params = _delta_filter("ec.cbModification", last_run)
    sql = f"""
        SELECT
            ec.JO_Num,
            ec.EC_No,
            ec.EC_Date,
            ec.CG_Num,
            ec.CT_Num,
            ec.EC_Sens,
            ec.EC_Montant,
            j.JO_Type
        FROM F_ECRITUREC ec
        INNER JOIN F_JOURNAUX j ON j.JO_Num = ec.JO_Num
        WHERE ec.EC_Montant IS NOT NULL
          AND ec.EC_Montant <> 0
          {delta_clause}
    """
    df = _read(MAG_ENGINE, sql, params)
    logger.info(f"F_ECRITUREC extracted: {len(df)} rows")
    if df.empty:
        logger.warning(
            "F_ECRITUREC returned 0 rows — FAIT_ECRITURES type_ligne=1 will be empty. "
            "Check MAG_ENGINE connectivity and that EC_Montant IS NOT NULL rows exist."
        )
    return df


def extract_fait_regtaxe(last_run: Optional[datetime] = None) -> pd.DataFrame:
    """
    Extract VAT lines from F_REGTAXE.
    Only rows with a non-NULL RT_Montant01 are fetched.
    """
    delta_clause, params = _delta_filter("rt.cbModification", last_run)
    sql = f"""
        SELECT
            rt.EC_No,
            rt.TA_Taux01,
            rt.RT_Base01,
            rt.RT_Montant01,
            ec.JO_Num,
            ec.EC_Date,
            ec.CT_Num,
            j.JO_Type
        FROM F_REGTAXE rt
        INNER JOIN F_ECRITUREC ec ON ec.EC_No = rt.EC_No
        INNER JOIN F_JOURNAUX  j  ON j.JO_Num = ec.JO_Num
        WHERE rt.RT_Montant01 IS NOT NULL
          {delta_clause}
    """
    df = _read(MAG_ENGINE, sql, params)
    logger.info(f"F_REGTAXE extracted: {len(df)} rows")
    return df


def extract_fait_artstock() -> pd.DataFrame:
    """
    Extract the current stock snapshot from F_ARTSTOCK (one row per
    article × depot).  Includes a table-existence guard and a non-zero
    sanity check so any infrastructure problem surfaces immediately in
    the ETL log rather than silently producing all-zero stock values.
    """
    if not _table_exists(MAG_ENGINE, "F_ARTSTOCK"):
        logger.error(
            "F_ARTSTOCK does not exist on MAG_ENGINE — stock snapshot will be empty. "
            "Verify database connectivity and schema."
        )
        return pd.DataFrame(
            columns=["AR_Ref", "DE_No", "AS_MontSto", "AS_QteSto", "AS_QteMini", "AS_QteRes"]
        )

    sql = """
        SELECT
            s.AR_Ref,
            s.DE_No,
            s.AS_MontSto,
            s.AS_QteSto,
            s.AS_QteMini,
            s.AS_QteRes
        FROM F_ARTSTOCK s
        INNER JOIN F_ARTICLE a ON a.AR_Ref = s.AR_Ref
        WHERE s.AS_QteSto IS NOT NULL
    """
    try:
        df = _read(MAG_ENGINE, sql)
        logger.info(f"F_ARTSTOCK extracted: {len(df)} rows")
        non_zero = (pd.to_numeric(df["AS_QteSto"], errors="coerce").fillna(0) > 0).sum()
        logger.info(f"F_ARTSTOCK sanity: {non_zero}/{len(df)} rows have AS_QteSto > 0")
        if df.empty:
            logger.warning(
                "F_ARTSTOCK returned 0 rows — all stock values will be NULL. "
                "Verify that F_ARTSTOCK contains data on MAG_ENGINE."
            )
        elif non_zero == 0:
            logger.warning(
                "F_ARTSTOCK: every AS_QteSto is 0 or NULL. "
                "Inventory module will show zero stock everywhere — "
                "check if Sage stock management (AR_SuiviStock) is enabled."
            )
        else:
            logger.info(
                f"F_ARTSTOCK sample:\n"
                + df[["AR_Ref", "DE_No", "AS_QteSto", "AS_QteMini", "AS_MontSto"]]
                .head(5)
                .to_string(index=False)
            )
        return df
    except Exception as exc:
        logger.error(f"F_ARTSTOCK extraction failed: {exc}")
        return pd.DataFrame(
            columns=["AR_Ref", "DE_No", "AS_MontSto", "AS_QteSto", "AS_QteMini", "AS_QteRes"]
        )


def extract_reglementt() -> pd.DataFrame:
    sql = """
        SELECT CT_Num, N_Reglement, RT_NbJour
        FROM F_REGLEMENTT
    """
    return _read(MAG_ENGINE, sql)


def extract_docentete_dates() -> pd.DataFrame:
    sql = """
        SELECT DO_Domaine, DO_Type, DO_Piece, DO_Date
        FROM F_DOCENTETE
    """
    return _read(MAG_ENGINE, sql)


# ---------------------------------------------------------------------------
# Fact extracts — payments / cash
# ---------------------------------------------------------------------------

def extract_fait_reglech() -> pd.DataFrame:
    sql = """
        SELECT DO_Piece, SUM(RC_Montant) AS RC_Montant
        FROM F_REGLECH
        GROUP BY DO_Piece
    """
    try:
        df = _read(GRT_ENGINE, sql)
        logger.info(f"F_REGLECH extracted: {len(df)} rows")
        return df
    except Exception as exc:
        logger.warning(f"F_REGLECH not available — RC_Montant will be NULL: {exc}")
        return pd.DataFrame(columns=["DO_Piece", "RC_Montant"])


def extract_fait_reglements_clients(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_where = f"AND RT_Date >= :last_run" if last_run is not None else ""
    params = {"last_run": last_run} if last_run is not None else {}
    sql = f"""
        SELECT
            rc.RT_Num,
            rc.CT_Num,
            rc.DO_Type,
            rc.DO_Piece,
            rc.RT_Date,
            rc.RT_Mode,
            rc.RT_Montant,
            rc.RT_Etat,
            rc.BQ_Num,
            rc.BQ_ABREGE,
            rc.RT_Rapproche,
            rc.RT_Echeance AS LB_EcheanceReg,
            NULL AS LB_Ligne,
            NULL AS BR_Num,
            NULL AS LB_MontantReg,
            NULL AS LB_NbJour,
            NULL AS LB_Agios,
            NULL AS BR_TotalReglement,
            NULL AS BR_Rapproch,
            NULL AS BR_TauxAgios,
            NULL AS BR_TMM
        FROM F_ReglementClient rc
        WHERE rc.RT_Montant IS NOT NULL
        {delta_where}
    """
    df = _read(GRT_ENGINE, sql, params)
    _validate_columns(df, ["RT_Num", "RT_Date", "LB_EcheanceReg"], "extract_fait_reglements_clients")
    return df


def extract_fait_reglements_fournisseurs(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_where = f"AND RT_Date >= :last_run" if last_run is not None else ""
    params = {"last_run": last_run} if last_run is not None else {}
    sql = f"""
        SELECT RT_Num, CT_Num, DO_Type, DO_Piece, RT_Date,
            RT_Mode, RT_Montant, RT_Etat, BQ_Num
        FROM F_ReglementFournisseur
        WHERE 1=1 {delta_where}
    """
    return _read(GRT_ENGINE, sql, params)


def extract_docregl_grt(last_run: Optional[datetime] = None) -> pd.DataFrame:
    sql = """
        SELECT DO_Piece, DR_Montant, DR_EtatRegle AS DR_Regle, DR_ModeReg
        FROM F_DOCREGL
    """
    return _read(GRT_ENGINE, sql)


def extract_fait_mvtcaisse(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_clause, params = _delta_filter("mc.MC_Date", last_run)
    sql = f"""
        SELECT
            mc.MC_Numero,
            mc.MC_Date,
            mc.MC_TypeMvt,
            mc.MC_Debit,
            mc.MC_Credit,
            mc.MC_Cloture,
            c.CA_Numero   AS CA_No,
            c.CA_Type,
            c.CA_Solde,
            c.CA_SoldeEspece,
            c.CA_SoldeCheque,
            c.CA_NumJournal AS JO_Num
        FROM F_MvtCaisse mc
        INNER JOIN F_Caisse c ON c.CA_Numero = mc.CA_Numero
        WHERE 1=1 {delta_clause}
    """
    return _read(GRT_ENGINE, sql, params)


def extract_dim_type_mvt_caisse() -> pd.DataFrame:
    sql = """
        SELECT DISTINCT MC_TypeMvt AS code_type_mvt
        FROM F_MvtCaisse
        WHERE MC_TypeMvt IS NOT NULL
    """
    return _read(GRT_ENGINE, sql)


# ---------------------------------------------------------------------------
# Static dimension maps
# ---------------------------------------------------------------------------

def extract_static_dims() -> dict[str, pd.DataFrame]:
    from etl.config import (
        MODES_REGLEMENT, ETATS_REGLEMENT, ETATS_DOCREGL,
        TYPES_LIGNE, SENS_ECRITURE, TYPES_TVA, DOMAINES, TYPES_DOC,
    )

    def _df(d: dict, code_col: str, lib_col: str) -> pd.DataFrame:
        return pd.DataFrame([(k, v) for k, v in d.items()], columns=[code_col, lib_col])

    return {
        "DIM_DOMAINE":         _df(DOMAINES,          "DO_Domaine",    "libelle_domaine"),
        "DIM_TYPE_DOC":        _df(TYPES_DOC,          "DO_Type",       "libelle_type_doc"),
        "DIM_MODE_REGLEMENT":  _df(MODES_REGLEMENT,    "RT_Mode",       "libelle_mode_reg"),
        "DIM_ETAT_REGLEMENT":  _df(ETATS_REGLEMENT,    "RT_Etat",       "libelle_etat_reg"),
        "DIM_ETAT_DOCREGL":    _df(ETATS_DOCREGL,      "DR_Regle",      "libelle_etat_docregl"),
        "DIM_TYPE_LIGNE":      _df(TYPES_LIGNE,        "type_ligne",    "libelle_type_ligne"),
        "DIM_SENS_ECRITURE":   _df(SENS_ECRITURE,      "EC_Sens",       "libelle_sens"),
        "DIM_TYPE_TVA":        _df(TYPES_TVA,          "type_tva",      "libelle_type_tva"),
    }


def extract_rfm_data(fenetre_jours: int = 365) -> pd.DataFrame:
    """Extract RFM raw data (Recency, Frequency, Monetary) for clients over past N days."""
    sql = f"""
        SELECT
            dl.CT_Num,
            MAX(dl.DO_Date) AS last_purchase_date,
            COUNT(DISTINCT dl.DO_Piece) AS frequency,
            SUM(dl.DL_MontantHT) AS montant_12m
        FROM F_DOCLIGNE dl
        WHERE dl.DO_Domaine = 0
          AND dl.DO_Type IN (6, 7)
          AND dl.DL_MontantHT IS NOT NULL
          AND dl.DO_Date >= DATEADD(DAY, -{fenetre_jours}, CAST(GETDATE() AS DATE))
        GROUP BY dl.CT_Num
    """
    try:
        df = _read(MAG_ENGINE, sql)
        logger.info(f"RFM data extracted: {len(df)} clients")
        return df
    except Exception as exc:
        logger.warning(f"RFM extraction failed: {exc}")
        return pd.DataFrame(columns=["CT_Num", "last_purchase_date", "frequency", "montant_12m"])


def extract_sales_history_365d() -> pd.DataFrame:
    """Extract 365-day rolling sales quantities by article for DSI calculation."""
    sql = """
        SELECT
            dl.AR_Ref,
            SUM(dl.DL_Qte) AS qte_vendue_365j
        FROM F_DOCLIGNE dl
        WHERE dl.DO_Domaine = 0
          AND dl.DO_Type IN (6, 7)
          AND dl.DO_Date >= DATEADD(DAY, -365, CAST(GETDATE() AS DATE))
          AND dl.DL_Qte IS NOT NULL
        GROUP BY dl.AR_Ref
    """
    try:
        df = _read(MAG_ENGINE, sql)
        logger.info(f"Sales history (365d) extracted: {len(df)} rows")
        return df
    except Exception as exc:
        logger.warning(f"Sales history extraction failed: {exc}")
        return pd.DataFrame(columns=["AR_Ref", "qte_vendue_365j"])