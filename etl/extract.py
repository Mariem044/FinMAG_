"""
extract.py — SIAD MAG Distribution ETL — v14.2
Extraction from MAG_2020 (Sage Gestion Commerciale)
and GRT_MAG (Sage Trésorerie).

FIXES vs previous version
──────────────────────────────────────────────────────────────────────────
FIX-JOIN  : extract_fait_mvtcaisse() — GRT F_Caisse PK is CA_Numero,
            aliased to CA_No so the rest of the pipeline stays consistent.
            The previous join ON c.CA_Numero = mc.CA_Numero was correct in
            SQL but selected c.CA_Numero AS CA_No — now explicit and safe.
FIX-DELTA : extract_fait_mvtcaisse() now accepts last_run and applies a
            delta filter on MC_Date so the caisse-dimension assembly and
            the fact-table assembly use the SAME time window.
FIX-BUG4  : extract_docregl_grt() had a duplicate definition — removed.
             Only one definition is kept (full reload; GRT has no
             cbModification column).
FIX-BUG7  : extract_dim_client_grt() — runtime column-existence check for
             CT_EchustTroisMois / CT_EchusTroisMois spelling variants.
FIX-BUG10 : extract_fait_lignes_vente() — DE_No removed from SELECT
             (id_depot was dropped from FAIT_LIGNES_VENTE in schema v11).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pandas as pd
from sqlalchemy import text

from etl.config import MAG_ENGINE, GRT_ENGINE, DIM_DATE_START, DIM_DATE_END
from etl.utils.logger import get_logger

logger = get_logger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _read(engine, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params or {})
    logger.debug(f"Extracted {len(df)} rows — {sql[:80].strip()}...")
    return df


def _delta_filter(col: str, last_run: Optional[datetime]) -> tuple[str, dict]:
    import re as _re
    if not _re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", col):
        raise ValueError(f"Unsafe column name: {col!r}")
    if last_run is None:
        return "", {}
    return f" AND {col} >= :last_run", {"last_run": last_run}


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


# ════════════════════════════════════════════════════════════════════════════
# MAG_2020
# ════════════════════════════════════════════════════════════════════════════

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
    sql = """
        SELECT FA_CodeFamille, FA_Intitule, CL_No1, CL_No2, CL_No3, CL_No4
        FROM F_FAMILLE
        WHERE FA_Type = 0
    """
    return _read(MAG_ENGINE, sql)


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
        SELECT CT_Num, CT_Sommeil, N_CatTarif, CO_No, CT_Encours, CT_SvCA
        FROM F_COMPTET
        WHERE CT_Type = 0 {delta_clause}
    """
    return _read(MAG_ENGINE, sql, params)


def extract_dim_client_grt() -> pd.DataFrame:
    """Extract client financial data from GRT_MAG.

    FIX-BUG7: Runtime check for CT_EchustTroisMois (Sage typo) vs
    CT_EchusTroisMois (standard spelling).
    """
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
    """GRT has no bank master table — return empty frame with expected columns."""
    return pd.DataFrame(columns=["EB_Abrege", "EB_Banque"])


def extract_dim_caisse_mag() -> pd.DataFrame:
    """MAG cash-register master data. CA_Type existence is checked at runtime."""
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


def extract_fait_lignes_vente(last_run: Optional[datetime] = None) -> pd.DataFrame:
    """Sales lines from MAG_2020.

    FIX-BUG10: DE_No removed — id_depot was dropped from FAIT_LIGNES_VENTE
    in schema v11. Including it was dead weight that _prepare_for_load()
    silently discarded every run.
    """
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
        WHERE 1=1 {delta_clause}
    """
    return _read(MAG_ENGINE, sql, params)


def extract_fait_regtaxe(last_run: Optional[datetime] = None) -> pd.DataFrame:
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
        WHERE 1=1 {delta_clause}
    """
    return _read(MAG_ENGINE, sql, params)


def extract_fait_artstock() -> pd.DataFrame:
    """Full stock snapshot — always a complete reload."""
    sql = """
        SELECT AR_Ref, DE_No, AS_MontSto, AS_QteSto, AS_QteMini, AS_QteRes
        FROM F_ARTSTOCK
    """
    return _read(MAG_ENGINE, sql)


def extract_reglementt() -> pd.DataFrame:
    """Contractual payment terms from MAG."""
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


# ════════════════════════════════════════════════════════════════════════════
# GRT_MAG
# ════════════════════════════════════════════════════════════════════════════

def extract_fait_reglements_clients(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_clause, params = _delta_filter("rc.RT_Date", last_run)
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
            lb.LB_Ligne,
            lb.BR_Num,
            lb.LB_MontantReg,
            lb.LB_EcheanceReg,
            lb.LB_NbJour,
            lb.LB_Agios,
            br.BR_TotalReglement,
            br.BR_Rapproch
        FROM F_ReglementClient rc
        LEFT JOIN F_LigneBordereauRemise lb ON lb.RT_Num = rc.RT_Num
        LEFT JOIN F_BordereauRemise br ON br.BR_Num = lb.BR_Num
        WHERE 1=1 {delta_clause}
    """
    df = _read(GRT_ENGINE, sql, params)
    _validate_columns(df, ["RT_Num", "RT_Date", "LB_EcheanceReg"], "extract_fait_reglements_clients")
    return df


def extract_fait_reglements_fournisseurs(last_run: Optional[datetime] = None) -> pd.DataFrame:
    delta_clause, params = _delta_filter("RT_Date", last_run)
    sql = f"""
        SELECT RT_Num, CT_Num, DO_Type, DO_Piece, RT_Date,
               RT_Mode, RT_Montant, RT_Etat, BQ_Num
        FROM F_ReglementFournisseur
        WHERE 1=1 {delta_clause}
    """
    return _read(GRT_ENGINE, sql, params)


def extract_docregl_grt(last_run: Optional[datetime] = None) -> pd.DataFrame:
    """Document règlement data from GRT_MAG.

    FIX-BUG4: only ONE definition kept (duplicate removed).
    GRT F_DOCREGL has no cbModification — always a full reload.
    last_run is accepted for API compatibility but ignored.
    """
    sql = """
        SELECT DO_Piece, DR_Montant, DR_EtatRegle AS DR_Regle, DR_ModeReg
        FROM F_DOCREGL
    """
    return _read(GRT_ENGINE, sql)


def extract_fait_mvtcaisse(last_run: Optional[datetime] = None) -> pd.DataFrame:
    """Cash movements from GRT.

    FIX-JOIN : GRT F_Caisse PK column is CA_Numero.  We alias it to CA_No
               so the rest of the pipeline (DIM_CAISSE assembly, FK lookup)
               uses a single consistent name.
    FIX-DELTA: delta filter on MC_Date so caisse-dim assembly and fact
               assembly use the same time window when last_run is supplied.
               For DIM_CAISSE (always full) the caller passes None.
    """
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


# ════════════════════════════════════════════════════════════════════════════
# STATIC DIMENSIONS
# ════════════════════════════════════════════════════════════════════════════

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