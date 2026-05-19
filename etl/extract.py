import pandas as pd
from sqlalchemy import text
from etl.config import MAG_ENGINE, GRT_ENGINE


def _read(engine, sql):
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


def extract_dim_segment():
    return _read(MAG_ENGINE, "SELECT cbIndice, CT_PrixTTC, CT_Intitule AS libelle_segment FROM P_CATTARIF WHERE cbIndice BETWEEN 1 AND 5 AND CT_Intitule IS NOT NULL AND CT_Intitule <> ''")

def extract_dim_collaborateur():
    return _read(MAG_ENGINE, "SELECT CO_No, CO_Fonction, CO_Sommeil FROM F_COLLABORATEUR")

def extract_dim_famille():
    return _read(MAG_ENGINE, "SELECT FA_CodeFamille, FA_Intitule, CL_No1, CL_No2, CL_No3, CL_No4 FROM F_FAMILLE WHERE FA_Type = 0")

def extract_dim_fournisseur():
    return _read(MAG_ENGINE, "SELECT CT_Num, CT_Sommeil, CT_Encours, CT_SvCA, CT_Intitule FROM F_COMPTET WHERE CT_Type = 1")

def extract_dim_article():
    sql = """
        SELECT a.AR_Ref, a.AR_Design, a.FA_CodeFamille, af.CT_Num AS CT_Num_fourn, a.AR_Sommeil, a.AR_PrixAch, a.AR_SuiviStock
        FROM F_ARTICLE a
        LEFT JOIN F_ARTFOURNISS af ON af.AR_Ref = a.AR_Ref AND af.AF_Principal = 1
    """
    return _read(MAG_ENGINE, sql)

def extract_dim_client_mag():
    return _read(MAG_ENGINE, "SELECT CT_Num, CT_Sommeil, N_CatTarif, CO_No, CT_Encours, CT_SvCA, CT_Ville, CT_CodeRegion, CT_Intitule FROM F_COMPTET WHERE CT_Type = 0")

def extract_dim_client_grt():
    # Vérifier si la colonne a une faute de frappe Sage (CT_EchustTroisMois)
    check_sql = "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'F_COMPTET' AND COLUMN_NAME = 'CT_EchustTroisMois'"
    with GRT_ENGINE.connect() as conn:
        result = conn.execute(text(check_sql)).scalar()
        has_typo = result is not None and result > 0

    col_3m = "CT_EchustTroisMois AS CT_EchusTroisMois" if has_typo else "CT_EchusTroisMois"
    sql = f"""
        SELECT CT_Num, CT_SoldeActuel, CT_Engagement, CT_ChiffreAffaire, CT_EchusUnMois, CT_EchusDeuxMois, {col_3m}, CT_EchusPlusTroisMois, CT_MoyenneDelaiPayement, CT_MoyenneDelaiImpaye
        FROM F_COMPTET
    """
    return _read(GRT_ENGINE, sql)

def extract_dim_depot():
    return _read(MAG_ENGINE, "SELECT DE_No, DE_Intitule, DE_Principal FROM F_DEPOT")

def extract_dim_journal():
    return _read(MAG_ENGINE, "SELECT JO_Num, JO_Type FROM F_JOURNAUX")

def extract_dim_banque_mag():
    return _read(MAG_ENGINE, "SELECT EB_Abrege, EB_Banque FROM F_EBANQUE")

def extract_dim_banque_grt():
    return pd.DataFrame(columns=["EB_Abrege", "EB_Banque"])

def extract_dim_caisse_mag():
    try:
        check_sql = "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'F_CAISSE' AND COLUMN_NAME = 'CA_Type'"
        with MAG_ENGINE.connect() as conn:
            result = conn.execute(text(check_sql)).scalar()
            has_ca_type = result is not None and result > 0
        col_type = "CA_Type" if has_ca_type else "NULL AS CA_Type"
        df = _read(MAG_ENGINE, f"SELECT CA_No, JO_Num, DE_No, CO_No, {col_type} FROM F_CAISSE")
        if not df.empty:
            return df
    except Exception:
        pass

    # Fallback to GRT_ENGINE F_Caisse
    sql_grt = """
        SELECT 
            CA_Numero AS CA_No, 
            CA_NumJournal AS JO_Num, 
            NULL AS DE_No, 
            NULL AS CO_No, 
            CA_Type 
        FROM F_Caisse
    """
    return _read(GRT_ENGINE, sql_grt)




def extract_fait_lignes_achat():
    sql = """
        SELECT dl.DO_Domaine, dl.DO_Type, dl.CT_Num, dl.DO_Piece, dl.DL_Ligne, dl.DO_Date, dl.AR_Ref, dl.DL_Qte, dl.DL_PrixUnitaire, dl.DL_Taxe1, dl.DL_MontantHT, dl.DL_MontantTTC, dl.DL_CMUP, dl.DL_PrixRU, de.DO_TxEscompte, de.DO_TotalHT, de.DO_TotalHTNet, de.DO_TotalTTC, de.DO_NetAPayer, de.DO_MontantRegle
        FROM F_DOCLIGNE dl
        INNER JOIN F_DOCENTETE de ON de.DO_Domaine = dl.DO_Domaine AND de.DO_Type = dl.DO_Type AND de.DO_Piece = dl.DO_Piece
        WHERE dl.DO_Domaine = 1 AND dl.DO_Type IN (16, 17) AND dl.DL_MontantHT IS NOT NULL
    """
    return _read(MAG_ENGINE, sql)

def extract_fait_lignes_vente():
    sql = """
        SELECT dl.DO_Domaine, dl.DO_Type, dl.CT_Num, dl.DO_Piece, dl.DL_Ligne, dl.DO_Date, dl.AR_Ref, dl.DL_Qte, dl.DL_PrixUnitaire, dl.DL_Taxe1, dl.DL_MontantHT, dl.DL_MontantTTC, dl.DL_CMUP, dl.DL_PrixRU, de.DO_TxEscompte, de.DO_TotalHT, de.DO_TotalHTNet, de.DO_TotalTTC, de.DO_NetAPayer, de.DO_MontantRegle
        FROM F_DOCLIGNE dl
        INNER JOIN F_DOCENTETE de ON de.DO_Domaine = dl.DO_Domaine AND de.DO_Type = dl.DO_Type AND de.DO_Piece = dl.DO_Piece
        WHERE dl.DO_Domaine = 0 AND dl.DO_Type IN (6, 7) AND dl.DL_MontantHT IS NOT NULL
    """
    return _read(MAG_ENGINE, sql)

def extract_fait_ecriturec():
    sql = """
        SELECT ec.JO_Num, ec.EC_No, ec.EC_Date, ec.CG_Num, ec.CT_Num, ec.EC_Sens, ec.EC_Montant, j.JO_Type
        FROM F_ECRITUREC ec
        INNER JOIN F_JOURNAUX j ON j.JO_Num = ec.JO_Num
        WHERE ec.EC_Montant IS NOT NULL AND ec.EC_Montant <> 0
    """
    return _read(MAG_ENGINE, sql)

def extract_fait_regtaxe():
    sql = """
        SELECT rt.EC_No, rt.TA_Taux01, rt.RT_Base01, rt.RT_Montant01, ec.JO_Num, ec.EC_Date, ec.CT_Num, j.JO_Type
        FROM F_REGTAXE rt
        INNER JOIN F_ECRITUREC ec ON ec.EC_No = rt.EC_No
        INNER JOIN F_JOURNAUX  j  ON j.JO_Num = ec.JO_Num
        WHERE rt.RT_Montant01 IS NOT NULL
    """
    return _read(MAG_ENGINE, sql)

def extract_fait_artstock():
    sql = """
        SELECT s.AR_Ref, s.DE_No, s.AS_MontSto, s.AS_QteSto, s.AS_QteMini, s.AS_QteRes
        FROM F_ARTSTOCK s
        INNER JOIN F_ARTICLE a ON a.AR_Ref = s.AR_Ref
        WHERE s.AS_QteSto IS NOT NULL
    """
    return _read(MAG_ENGINE, sql)

def extract_reglementt():
    return _read(MAG_ENGINE, "SELECT CT_Num, N_Reglement, RT_NbJour FROM F_REGLEMENTT")

def extract_docentete_dates():
    return _read(MAG_ENGINE, "SELECT DO_Domaine, DO_Type, DO_Piece, DO_Date FROM F_DOCENTETE")

def extract_fait_reglements_clients():
    sql = """
        SELECT rc.RT_Num, rc.CT_Num, rc.DO_Type, rc.DO_Piece, rc.RT_Date, rc.RT_Mode, rc.RT_Montant, rc.RT_Etat, rc.BQ_Num, rc.BQ_ABREGE, rc.RT_Rapproche, rc.RT_Echeance AS LB_EcheanceReg, lb.LB_Ligne, br.BR_Num, lb.LB_MontantReg, lb.LB_NbJour, lb.LB_Agios, br.BR_TotalReglement, br.BR_Rapproch, NULL AS BR_TauxAgios, NULL AS BR_TMM
        FROM F_ReglementClient rc
        LEFT JOIN F_LigneBordereauRemise lb ON lb.RT_Num = rc.RT_Num
        LEFT JOIN F_BordereauRemise br ON br.BR_Num = lb.BR_Num
        WHERE rc.RT_Montant IS NOT NULL
    """
    return _read(GRT_ENGINE, sql)

def extract_fait_reglements_fournisseurs():
    return _read(GRT_ENGINE, "SELECT RT_Num, CT_Num, DO_Type, DO_Piece, RT_Date, RT_Mode, RT_Montant, RT_Etat, BQ_Num FROM F_ReglementFournisseur WHERE RT_Montant IS NOT NULL")

def extract_docregl_grt():
    return _read(GRT_ENGINE, "SELECT DO_Piece, DR_Montant, DR_ModeReg FROM F_DOCREGL")

def extract_docregl_mag():
    return _read(MAG_ENGINE, "SELECT DO_Piece, N_Reglement, DR_Regle FROM F_DOCREGL")

def extract_fait_mvtcaisse():
    sql = """
        SELECT mc.MC_Numero, mc.MC_Date, mc.MC_TypeMvt, mc.MC_Debit, mc.MC_Credit, mc.MC_Cloture, c.CA_Numero AS CA_No, c.CA_Type, c.CA_Solde, c.CA_SoldeEspece, c.CA_SoldeCheque, c.CA_NumJournal AS JO_Num
        FROM F_MvtCaisse mc
        INNER JOIN F_Caisse c ON c.CA_Numero = mc.CA_Numero
    """
    return _read(GRT_ENGINE, sql)

def extract_dim_type_mvt_caisse():
    sql = """
        SELECT mc.MC_TypeMvt AS code_type_mvt, MAX(mc.MC_IntituleTypeMvt) AS intitule_type_mvt
        FROM F_MvtCaisse mc
        WHERE mc.MC_TypeMvt IS NOT NULL
        GROUP BY mc.MC_TypeMvt
    """
    return _read(GRT_ENGINE, sql)
