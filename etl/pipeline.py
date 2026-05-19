from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone, date
import pandas as pd
from sqlalchemy import text

from etl.config import DW_ENGINE, DIM_DATE_START, DIM_DATE_END, hash_key
from etl.utils.logger import get_logger
from etl import ddl, extract, transform, load

logger = get_logger(__name__)

# ==========================================
# 1. DICTIONNAIRES STATIQUES ET CARTOGRAPHIES
# ==========================================

SEGMENTS = {
    1: "DÉTAILLANTS",
    2: "GROSSISTES",
    3: "HORECA",
    4: "SEMI-GROS",
    5: "DISTRIBUTEUR",
}

MODES_REGLEMENT = {
    1: "Espèces",
    2: "Chèque",
    3: "Virement",
    4: "Traite",
    5: "LCR",
    7: "Carte",
    8: "Autre",
}

ETATS_REGLEMENT = {
    0: "En cours",
    1: "Soldé",
    2: "Payé",
}

ETATS_DOCREGL = {
    0: "Non réglé",
    1: "Réglé",
}

TYPES_LIGNE = {
    1: "Ecriture comptable",
    2: "TVA",
    3: "Mouvement caisse",
    4: "Stock snapshot",
}

SENS_ECRITURE = {
    0: "Débit",
    1: "Crédit",
}

TYPES_TVA = {
    1: "TVA collectée",
    2: "TVA déductible",
}

TYPES_MVT_CAISSE = {
    0: "Entrée",
    1: "Sortie",
    2: "Remise en banque chèques",
    3: "Remise en banque espèces",
    4: "Bordereau de carte bancaire",
    5: "Bon de caisse",
    6: "Escompte",
    7: "Règlement fournisseur",
}

TYPES_DOC = {
    1: "Devis",
    2: "Bon de commande",
    3: "Bon de livraison",
    4: "Bon de retour",
    5: "Bon d'avoir HT",
    6: "Facture",
    7: "Avoir",
    11: "Préparation de commande",
    12: "Bon de commande fournisseur",
    13: "Bon de réception",
    14: "Bon de retour fournisseur",
    15: "Bon d'avoir fournisseur HT",
    16: "Facture fournisseur",
    17: "Avoir fournisseur",
}

DOMAINES = {
    0: "Vente",
    1: "Achat",
    2: "Stock",
    3: "Interne",
}

GOUVERNORAT_MAPPING = {
    'TUNIS': 'Tunis', 'MONTPLAISIR': 'Tunis', 'LE BARDO': 'Tunis',
    'BARDO': 'Tunis', 'EZZAHROUNI': 'Tunis', 'OMRANE': 'Tunis',
    'AGBA': 'Tunis', 'ETTADHAMEN': 'Tunis', 'MARCHE CENTRAL': 'Tunis',
    'MALASINE': 'Tunis', 'LAKANIA': 'Tunis',
    'ARIANA': 'Ariana', 'RAOUED': 'Ariana', 'CITE ENNASR': 'Ariana',
    'KALAAT LANDLOUS': 'Ariana', 'LA SOUKRA': 'Ariana',
    'BEN AROUS': 'Ben Arous', 'EL MOUROUJ': 'Ben Arous',
    'RADES': 'Ben Arous', 'FOUCHANA': 'Ben Arous',
    'MANOUBA': 'Manouba', 'OUED ELLIL': 'Manouba',
    'BIZERTE': 'Bizerte', 'MENZEL BOURGUIBA': 'Bizerte',
    'NABEUL': 'Nabeul', 'HAMMAMET': 'Nabeul', 'KELIBIA': 'Nabeul',
    'SOUSSE': 'Sousse', 'MSAKEN': 'Sousse', 'AKOUDA': 'Sousse',
    'MONASTIR': 'Monastir', 'SKANES': 'Monastir', 'KSAR HELLAL': 'Monastir',
    'MAHDIA': 'Mahdia', 'EL JEM': 'Mahdia',
    'KAIROUAN': 'Kairouan', 'SBIKHA': 'Kairouan',
    'SFAX': 'Sfax', 'SAKIET EZZIT': 'Sfax', 'SAKIET EDDAIER': 'Sfax',
    'GABES': 'Gabès', 'EL HAMMA': 'Gabès',
    'MEDENINE': 'Médenine', 'ZARZIS': 'Médenine', 'BEN GARDANE': 'Médenine',
    'TATAOUINE': 'Tataouine',
    'GAFSA': 'Gafsa', 'METLAOUI': 'Gafsa',
    'KASSERINE': 'Kasserine', 'SBEITLA': 'Kasserine',
    'SIDI BOUZID': 'Sidi Bouzid',
    'BEJA': 'Béja', 'TESTOUR': 'Béja',
    'JENDOUBA': 'Jendouba', 'AIN DRAHAM': 'Jendouba',
    'KEF': 'Le Kef', 'DAHMANI': 'Le Kef',
    'SILIANA': 'Siliana', 'MAKTHAR': 'Siliana',
    'ZAGHOUAN': 'Zaghouan', 'ENFIDHA': 'Zaghouan',
    'TOZEUR': 'Tozeur', 'NEFTA': 'Tozeur',
    'KEBILI': 'Kébili',
    'HORS ZONE': 'Autre', 'DIVERS': 'Autre'
}

# ==========================================
# 2. ASSISTANCE ET RESOLUTIONS DE CLES
# ==========================================

def _build_lookup(table_name: str, natural_col: str, surrogate_col: str) -> dict:
    """Helper simple pour charger la correspondance entre clef metier et clef technique."""
    query = f"SELECT [{surrogate_col}], [{natural_col}] FROM [{table_name}]"
    df = pd.read_sql(query, DW_ENGINE)
    if table_name == "DIM_DATE" and not df.empty:
        df[natural_col] = pd.to_datetime(df[natural_col]).dt.date
    return dict(zip(df[natural_col], df[surrogate_col]))

def _source_hash(*values) -> bytes:
    """Genere une clef unique de type hash binaire a partir de valeurs."""
    parts = ["<NULL>" if pd.isna(v) else str(v).strip() for v in values]
    return hashlib.sha256("|".join(parts).encode("utf-8")).digest()

def _resolve_gouvernorat(region: str) -> str:
    """Map une region brute vers son gouvernorat en Tunisie."""
    if pd.isna(region) or not str(region).strip():
        return "Autre"
    return GOUVERNORAT_MAPPING.get(str(region).strip().upper(), "Autre")

# ==========================================
# 3. PIPELINE GENERAL (SEQUENTIEL & LINEAIRE)
# ==========================================

def run_pipeline(force_full: bool = False) -> None:
    """Execute le pipeline ETL de maniere purement sequentielle et lisible."""
    logger.info("=== ETL : DEBUT DE LA PIPELINE SEQUENTIELLE ===")
    
    # 1. Recreer la base de donnees si besoin (on s'assure qu'elle existe)
    ddl.create_all_tables(drop_existing=False)

    # 2. Desactiver temporairement les cles etrangeres pour charger sans blocages
    with DW_ENGINE.begin() as conn:
        ddl.disable_all_fk(conn)
    logger.info("FK : Contraintes de cles etrangeres desactivees.")

    lookups = {}

    try:
        # -------------------------------------------------------------------
        # ETAPE A : CHARGEMENT DES DIMENSIONS STATIQUES
        # -------------------------------------------------------------------
        
        # A1. DIM_DATE
        logger.info("--- [DIM_DATE] Generation des dates ---")
        exos = extract.extract_exercices_fiscaux()
        dr = pd.date_range(start=DIM_DATE_START, end=DIM_DATE_END, freq="D")
        
        df_date = pd.DataFrame({
            "date_val": dr.date,
            "jour": dr.day.astype("int16"),
            "mois": dr.month.astype("int16"),
            "trimestre": dr.quarter.astype("int16"),
            "semestre": ((dr.month - 1) // 6 + 1).astype("int16"),
            "annee": dr.year.astype("int16"),
            "semaine": dr.isocalendar().week.astype("int16"),
            "jour_semaine": (dr.weekday + 1).astype("int16"),
            "est_weekend": (dr.weekday >= 5).astype("int16"),
            "est_ferie": 0,
            "exercice": None
        })
        
        def get_exo(d) -> int | None:
            for i, (debut, fin) in enumerate(exos, 1):
                if debut <= d <= fin:
                    return i
            return None
        df_date["exercice"] = df_date["date_val"].apply(get_exo)
        
        # Cast en datetime pour eviter les problemes to_sql
        df_date["date_val"] = pd.to_datetime(df_date["date_val"])
        load.load_dimension(df_date, "DIM_DATE")
        lookups["DIM_DATE"] = _build_lookup("DIM_DATE", "date_val", "id_date")

        # A2. DIM_DOMAINE
        df_dom = pd.DataFrame([{"DO_Domaine": k, "libelle_domaine": v} for k, v in DOMAINES.items()])
        load.load_dimension(df_dom, "DIM_DOMAINE")
        lookups["DIM_DOMAINE"] = _build_lookup("DIM_DOMAINE", "DO_Domaine", "id_domaine")

        # A3. DIM_TYPE_DOC
        df_tdoc = pd.DataFrame([{"DO_Type": k, "libelle_type_doc": v} for k, v in TYPES_DOC.items()])
        load.load_dimension(df_tdoc, "DIM_TYPE_DOC")
        lookups["DIM_TYPE_DOC"] = _build_lookup("DIM_TYPE_DOC", "DO_Type", "id_type_doc")

        # A4. DIM_MODE_REGLEMENT
        df_mreg = pd.DataFrame([{"RT_Mode": k, "libelle_mode_reg": v} for k, v in MODES_REGLEMENT.items()])
        load.load_dimension(df_mreg, "DIM_MODE_REGLEMENT")
        lookups["DIM_MODE_REGLEMENT"] = _build_lookup("DIM_MODE_REGLEMENT", "RT_Mode", "id_mode_reg")

        # A5. DIM_ETAT_REGLEMENT
        df_ereg = pd.DataFrame([{"RT_Etat": k, "libelle_etat_reg": v} for k, v in ETATS_REGLEMENT.items()])
        load.load_dimension(df_ereg, "DIM_ETAT_REGLEMENT")
        lookups["DIM_ETAT_REGLEMENT"] = _build_lookup("DIM_ETAT_REGLEMENT", "RT_Etat", "id_etat_reg")

        # A6. DIM_ETAT_DOCREGL
        df_edoc = pd.DataFrame([{"DR_Regle": k, "libelle_etat_docregl": v} for k, v in ETATS_DOCREGL.items()])
        load.load_dimension(df_edoc, "DIM_ETAT_DOCREGL")
        lookups["DIM_ETAT_DOCREGL"] = _build_lookup("DIM_ETAT_DOCREGL", "DR_Regle", "id_etat_docregl")

        # A7. DIM_TYPE_LIGNE
        df_tlign = pd.DataFrame([{"type_ligne": k, "libelle_type_ligne": v} for k, v in TYPES_LIGNE.items()])
        load.load_dimension(df_tlign, "DIM_TYPE_LIGNE")
        lookups["DIM_TYPE_LIGNE"] = _build_lookup("DIM_TYPE_LIGNE", "type_ligne", "id_type_ligne")

        # A8. DIM_SENS_ECRITURE
        df_sens = pd.DataFrame([{"EC_Sens": k, "libelle_sens": v} for k, v in SENS_ECRITURE.items()])
        load.load_dimension(df_sens, "DIM_SENS_ECRITURE")
        lookups["DIM_SENS_ECRITURE"] = _build_lookup("DIM_SENS_ECRITURE", "EC_Sens", "id_sens")

        # A9. DIM_TYPE_TVA
        df_ttva = pd.DataFrame([{"type_tva": k, "libelle_type_tva": v} for k, v in TYPES_TVA.items()])
        load.load_dimension(df_ttva, "DIM_TYPE_TVA")
        lookups["DIM_TYPE_TVA"] = _build_lookup("DIM_TYPE_TVA", "type_tva", "id_type_tva")

        # -------------------------------------------------------------------
        # ETAPE B : CHARGEMENT DES DIMENSIONS DYNAMIQUES
        # -------------------------------------------------------------------

        # B1. DIM_TYPE_MVT_CAISSE
        logger.info("--- [DIM_TYPE_MVT_CAISSE] Extraction ---")
        df_mvt = extract.extract_dim_type_mvt_caisse()
        df_mvt = df_mvt.rename(columns={"code_type_mvt": "MC_TypeMvt"})
        df_mvt["libelle_type_mvt"] = df_mvt["MC_TypeMvt"].apply(lambda v: TYPES_MVT_CAISSE.get(int(v), f"Type caisse {int(v)}") if pd.notna(v) else None)
        df_mvt = df_mvt.drop_duplicates(subset=["MC_TypeMvt"], keep="first")
        load.load_dimension(df_mvt, "DIM_TYPE_MVT_CAISSE")
        lookups["DIM_TYPE_MVT_CAISSE"] = _build_lookup("DIM_TYPE_MVT_CAISSE", "MC_TypeMvt", "id_type_mvt")

        # B2. DIM_SEGMENT
        logger.info("--- [DIM_SEGMENT] Extraction ---")
        df_seg = extract.extract_dim_segment()
        df_seg["cbIndice_code"] = df_seg["cbIndice"].apply(hash_key)
        df_seg["libelle_segment"] = df_seg["cbIndice"].map(lambda v: SEGMENTS.get(int(v), f"Segment {v}"))
        df_seg = df_seg.drop_duplicates(subset=["cbIndice_code"], keep="first")
        load.load_dimension(df_seg, "DIM_SEGMENT")
        lookups["DIM_SEGMENT"] = _build_lookup("DIM_SEGMENT", "cbIndice_code", "id_segment")

        # B3. DIM_COLLABORATEUR
        logger.info("--- [DIM_COLLABORATEUR] Extraction ---")
        df_collab = extract.extract_dim_collaborateur()
        df_collab["CO_Fonction"] = pd.to_numeric(df_collab["CO_Fonction"], errors="coerce")
        df_collab = df_collab.drop_duplicates(subset=["CO_No"], keep="first")
        load.load_dimension(df_collab, "DIM_COLLABORATEUR")
        lookups["DIM_COLLABORATEUR"] = _build_lookup("DIM_COLLABORATEUR", "CO_No", "id_collab")

        # B4. DIM_JOURNAL
        logger.info("--- [DIM_JOURNAL] Extraction ---")
        df_jour = extract.extract_dim_journal()
        df_jour["JO_Num_code"] = df_jour["JO_Num"].apply(hash_key)
        df_jour = df_jour.drop_duplicates(subset=["JO_Num_code"], keep="first")
        load.load_dimension(df_jour, "DIM_JOURNAL")
        lookups["DIM_JOURNAL"] = _build_lookup("DIM_JOURNAL", "JO_Num_code", "id_journal")

        # B5. DIM_FOURNISSEUR
        logger.info("--- [DIM_FOURNISSEUR] Extraction ---")
        df_fourn = extract.extract_dim_fournisseur()
        df_fourn["CT_Num_code"] = df_fourn["CT_Num"].apply(hash_key)
        df_fourn = df_fourn.drop_duplicates(subset=["CT_Num_code"], keep="first")
        load.load_dimension(df_fourn, "DIM_FOURNISSEUR")
        lookups["DIM_FOURNISSEUR"] = _build_lookup("DIM_FOURNISSEUR", "CT_Num_code", "id_fournisseur")

        # B6. DIM_BANQUE
        logger.info("--- [DIM_BANQUE] Extraction ---")
        df_bq_mag = extract.extract_dim_banque_mag()
        df_bq_mag["source"] = 1
        df_bq_grt = extract.extract_dim_banque_grt()
        df_bq_grt["source"] = 2
        df_bq = pd.concat([df_bq_mag, df_bq_grt], ignore_index=True)
        df_bq["EB_Abrege_code"] = df_bq["EB_Abrege"].apply(hash_key)
        df_bq = df_bq.drop_duplicates(subset=["EB_Abrege_code"], keep="first")
        load.load_dimension(df_bq, "DIM_BANQUE")
        lookups["DIM_BANQUE"] = _build_lookup("DIM_BANQUE", "EB_Abrege_code", "id_banque")

        # B7. DIM_FAMILLE
        logger.info("--- [DIM_FAMILLE] Extraction ---")
        df_fam = extract.extract_dim_famille()
        df_fam["FA_CodeFamille_code"] = df_fam["FA_CodeFamille"].apply(hash_key)
        df_fam["niveau_0_code"] = df_fam["CL_No1"].apply(hash_key)
        df_fam["niveau_1_code"] = df_fam["CL_No2"].apply(hash_key)
        df_fam["niveau_2_code"] = df_fam["CL_No3"].apply(hash_key)
        df_fam = df_fam.drop_duplicates(subset=["FA_CodeFamille_code"], keep="first")
        load.load_dimension(df_fam, "DIM_FAMILLE")
        lookups["DIM_FAMILLE"] = _build_lookup("DIM_FAMILLE", "FA_CodeFamille_code", "id_famille")

        # Creation rapide d'une table de correspondance pour libelle famille
        fam_labels = dict(zip(df_fam["FA_CodeFamille_code"], df_fam["FA_Intitule"]))

        # B8. DIM_CLIENT
        logger.info("--- [DIM_CLIENT] Extraction MAG + GRT ---")
        df_cli_mag = extract.extract_dim_client_mag()
        df_cli_grt = extract.extract_dim_client_grt()
        df_cli = pd.merge(df_cli_mag, df_cli_grt, on="CT_Num", how="left")
        df_cli["CT_Num_code"] = df_cli["CT_Num"].apply(hash_key)
        df_cli["id_segment"] = df_cli["N_CatTarif"].apply(hash_key).map(lookups["DIM_SEGMENT"])
        df_cli["id_collab"] = df_cli["CO_No"].map(lookups["DIM_COLLABORATEUR"])
        df_cli["gouvernorat"] = df_cli["CT_CodeRegion"].apply(_resolve_gouvernorat)
        df_cli = df_cli.drop_duplicates(subset=["CT_Num_code"], keep="first")
        load.load_dimension(df_cli, "DIM_CLIENT")
        lookups["DIM_CLIENT"] = _build_lookup("DIM_CLIENT", "CT_Num_code", "id_client")

        # B9. DIM_ARTICLE
        logger.info("--- [DIM_ARTICLE] Extraction ---")
        df_art = extract.extract_dim_article()
        df_art["AR_Ref_code"] = df_art["AR_Ref"].apply(hash_key)
        df_art["id_famille"] = df_art["FA_CodeFamille"].apply(hash_key).map(lookups["DIM_FAMILLE"])
        df_art["id_fournisseur"] = df_art["CT_Num_fourn"].apply(hash_key).map(lookups["DIM_FOURNISSEUR"])
        df_art["FA_Intitule"] = df_art["FA_CodeFamille"].apply(hash_key).map(fam_labels)
        df_art = df_art.drop_duplicates(subset=["AR_Ref_code"], keep="first")
        load.load_dimension(df_art, "DIM_ARTICLE")
        lookups["DIM_ARTICLE"] = _build_lookup("DIM_ARTICLE", "AR_Ref_code", "id_article")

        # B10. DIM_DEPOT
        logger.info("--- [DIM_DEPOT] Extraction ---")
        df_dep = extract.extract_dim_depot()
        df_dep = df_dep.drop_duplicates(subset=["DE_No"], keep="first")
        load.load_dimension(df_dep, "DIM_DEPOT")
        lookups["DIM_DEPOT"] = _build_lookup("DIM_DEPOT", "DE_No", "id_depot")

        # B11. DIM_CAISSE
        logger.info("--- [DIM_CAISSE] Extraction ---")
        df_caisse = extract.extract_dim_caisse_mag()
        df_caisse["CA_Numero_code"] = df_caisse["CA_No"].apply(hash_key)
        df_caisse["id_journal"] = df_caisse["JO_Num"].apply(hash_key).map(lookups["DIM_JOURNAL"])
        df_caisse = df_caisse.drop_duplicates(subset=["CA_Numero_code"], keep="first")
        load.load_dimension(df_caisse, "DIM_CAISSE")
        lookups["DIM_CAISSE"] = _build_lookup("DIM_CAISSE", "CA_Numero_code", "id_caisse")

        # -------------------------------------------------------------------
        # ETAPE C : CHARGEMENT DES TABLES DE FAITS
        # -------------------------------------------------------------------

        # C1. FAIT_LIGNES_VENTE (Ventes + Achats)
        logger.info("--- [FAIT_LIGNES_VENTE] Extraction Ventes + Achats ---")
        df_vente = extract.extract_fait_lignes_vente()
        df_achat = extract.extract_fait_lignes_achat()
        df_flv = pd.concat([df_vente, df_achat], ignore_index=True)
        
        df_flv["DO_Piece_hash"] = df_flv["DO_Piece"].apply(hash_key)
        df_flv["id_date"] = pd.to_datetime(df_flv["DO_Date"]).dt.date.map(lookups["DIM_DATE"])
        df_flv["id_type_doc"] = df_flv["DO_Type"].map(lookups["DIM_TYPE_DOC"])
        df_flv["id_domaine"] = df_flv["DO_Domaine"].map(lookups["DIM_DOMAINE"])
        df_flv["id_client"] = df_flv["CT_Num"].apply(hash_key).map(lookups["DIM_CLIENT"])
        df_flv["id_article"] = df_flv["AR_Ref"].apply(hash_key).map(lookups["DIM_ARTICLE"])
        
        df_flv["source_hash"] = df_flv.apply(
            lambda r: _source_hash("DOCLIGNE", r.get("DO_Domaine"), r.get("DO_Type"), r.get("DO_Piece"), r.get("DL_Ligne"), r.get("AR_Ref")), axis=1
        )
        df_flv["date_extraction"] = datetime.now(timezone.utc).date()
        load.load_fact(df_flv, "FAIT_LIGNES_VENTE")

        # C2. FAIT_REGLEMENTS
        logger.info("--- [FAIT_REGLEMENTS] Ingestion consolidée ---")
        df_rc = extract.extract_fait_reglements_clients()
        df_rc["_acteur"] = "CLIENT"
        df_rf = extract.extract_fait_reglements_fournisseurs()
        df_rf["_acteur"] = "FOURNISSEUR"
        
        df_doc_dates = extract.extract_docentete_dates()[["DO_Type", "DO_Piece", "DO_Date"]].drop_duplicates(subset=["DO_Type", "DO_Piece"], keep="last")
        df_docregl = extract.extract_docregl_grt().drop_duplicates(subset=["DO_Piece"], keep="last")
        df_regt = extract.extract_reglementt().rename(columns={"RT_NbJour": "RT_NbJour_contrat"})
        df_regt["N_Reglement"] = pd.to_numeric(df_regt["N_Reglement"], errors="coerce")

        df_reg = pd.concat([df_rc, df_rf], ignore_index=True)
        df_reg = pd.merge(df_reg, df_doc_dates, on=["DO_Type", "DO_Piece"], how="left")
        df_reg = pd.merge(df_reg, df_docregl, on="DO_Piece", how="left")
        df_reg["N_Reglement"] = pd.to_numeric(df_reg.get("N_Reglement"), errors="coerce")
        df_reg = pd.merge(df_reg, df_regt, on=["CT_Num", "N_Reglement"], how="left")
        
        df_reg["RT_NbJour"] = df_reg["RT_NbJour_contrat"]
        df_reg = transform.add_fact_reglements_calcs(df_reg)
        
        df_reg["id_date_paiement"] = pd.to_datetime(df_reg["RT_Date"]).dt.date.map(lookups["DIM_DATE"])
        df_reg["id_date_echeance"] = pd.to_datetime(df_reg["LB_EcheanceReg"]).dt.date.map(lookups["DIM_DATE"])
        
        df_reg["id_client"] = df_reg.apply(lambda r: lookups["DIM_CLIENT"].get(hash_key(r["CT_Num"])) if r["_acteur"] == "CLIENT" else None, axis=1)
        df_reg["id_fournisseur"] = df_reg.apply(lambda r: lookups["DIM_FOURNISSEUR"].get(hash_key(r["CT_Num"])) if r["_acteur"] == "FOURNISSEUR" else None, axis=1)
        df_reg["id_banque"] = df_reg["BQ_ABREGE"].apply(hash_key).map(lookups["DIM_BANQUE"])
        df_reg["id_mode_reg"] = df_reg["RT_Mode"].map(lookups["DIM_MODE_REGLEMENT"])
        df_reg["id_etat_reg"] = df_reg["RT_Etat"].map(lookups["DIM_ETAT_REGLEMENT"])
        df_reg["id_etat_docregl"] = df_reg["DR_Regle"].map(lookups["DIM_ETAT_DOCREGL"])
        df_reg["id_type_doc"] = df_reg["DO_Type"].map(lookups["DIM_TYPE_DOC"])
        
        df_reg["source_hash"] = df_reg.apply(
            lambda r: _source_hash("REGLEMENT", r.get("_acteur"), r.get("CT_Num"), r.get("RT_Num"), r.get("LB_Ligne"), r.get("DO_Piece")), axis=1
        )
        df_reg["date_extraction"] = datetime.now(timezone.utc).date()
        load.load_fact(df_reg, "FAIT_REGLEMENTS")

        # C3. FAIT_ECRITURES (Multi-grain: Compta=1, TVA=2, Caisse=3, Stock=4)
        logger.info("--- [FAIT_ECRITURES] Assemblage multi-grain ---")
        
        # Grain 1: Compta
        df_ecr = extract.extract_fait_ecriturec()
        df_g1 = pd.DataFrame({
            "id_date": pd.to_datetime(df_ecr["EC_Date"]).dt.date.map(lookups["DIM_DATE"]),
            "id_type_ligne": lookups["DIM_TYPE_LIGNE"].get(1),
            "id_journal": df_ecr["JO_Num"].apply(hash_key).map(lookups["DIM_JOURNAL"]),
            "id_client": df_ecr["CT_Num"].apply(hash_key).map(lookups["DIM_CLIENT"]),
            "id_sens_ecriture": df_ecr["EC_Sens"].map(lookups["DIM_SENS_ECRITURE"]),
            "id_type_tva": df_ecr["JO_Type"].map({1:1, 0:2}).map(lookups["DIM_TYPE_TVA"]),
            "EC_Intitule": "Ecriture " + df_ecr["JO_Num"].astype(str),
            "EC_Sens": df_ecr["EC_Sens"],
            "EC_Montant": pd.to_numeric(df_ecr["EC_Montant"], errors="coerce"),
            "source_hash": df_ecr.apply(lambda r: _source_hash("ECRITUREC", r.get("JO_Num"), r.get("EC_No"), r.get("EC_Date"), r.get("CG_Num"), r.get("CT_Num")), axis=1),
            "date_extraction": datetime.now(timezone.utc).date()
        })
        
        # Grain 2: TVA
        df_tva = extract.extract_fait_regtaxe()
        df_g2 = pd.DataFrame({
            "id_date": pd.to_datetime(df_tva["EC_Date"]).dt.date.map(lookups["DIM_DATE"]),
            "id_type_ligne": lookups["DIM_TYPE_LIGNE"].get(2),
            "id_journal": df_tva["JO_Num"].apply(hash_key).map(lookups["DIM_JOURNAL"]),
            "id_client": df_tva["CT_Num"].apply(hash_key).map(lookups["DIM_CLIENT"]),
            "id_type_tva": df_tva["JO_Type"].map({1:1, 0:2}).map(lookups["DIM_TYPE_TVA"]),
            "EC_TauxTVA": pd.to_numeric(df_tva["TA_Taux01"], errors="coerce"),
            "EC_MontantTVA": pd.to_numeric(df_tva["RT_Montant01"], errors="coerce"),
            "EC_MontantHT": pd.to_numeric(df_tva["RT_Base01"], errors="coerce"),
            "source_hash": df_tva.apply(lambda r: _source_hash("REGTAXE", r.get("JO_Num"), r.get("EC_No"), r.get("EC_Date"), r.get("TA_Taux01")), axis=1),
            "date_extraction": datetime.now(timezone.utc).date()
        })
        
        # Grain 3: Mouvement de Caisse
        df_mc = extract.extract_fait_mvtcaisse()
        df_g3 = pd.DataFrame({
            "id_date": pd.to_datetime(df_mc["MC_Date"]).dt.date.map(lookups["DIM_DATE"]),
            "id_type_ligne": lookups["DIM_TYPE_LIGNE"].get(3),
            "id_journal": df_mc["JO_Num"].apply(hash_key).map(lookups["DIM_JOURNAL"]),
            "id_caisse": df_mc["CA_No"].apply(hash_key).map(lookups["DIM_CAISSE"]),
            "id_type_mvt_caisse": df_mc["MC_TypeMvt"].map(lookups["DIM_TYPE_MVT_CAISSE"]),
            "MC_Debit": pd.to_numeric(df_mc["MC_Debit"], errors="coerce"),
            "MC_Credit": pd.to_numeric(df_mc["MC_Credit"], errors="coerce"),
            "MC_Montant": pd.to_numeric(df_mc["MC_Debit"], errors="coerce").fillna(0) - pd.to_numeric(df_mc["MC_Credit"], errors="coerce").fillna(0),
            "MC_Libelle": "Mouvement Caisse " + df_mc["MC_Numero"].astype(str),
            "source_hash": df_mc.apply(lambda r: _source_hash("MVTCaisse", r.get("CA_No"), r.get("MC_Numero"), r.get("MC_Date"), r.get("MC_TypeMvt")), axis=1),
            "date_extraction": datetime.now(timezone.utc).date()
        })
        
        # Grain 4: Stock Snapshot (Aujourd'hui)
        df_stk = extract.extract_fait_artstock()
        today_date = datetime.now(timezone.utc).date()
        today_id = lookups["DIM_DATE"].get(today_date)
        
        df_g4 = pd.DataFrame({
            "id_date": today_id,
            "id_type_ligne": lookups["DIM_TYPE_LIGNE"].get(4),
            "id_article": df_stk["AR_Ref"].apply(hash_key).map(lookups["DIM_ARTICLE"]),
            "id_depot": df_stk["DE_No"].map(lookups["DIM_DEPOT"]),
            "AS_QteSto": pd.to_numeric(df_stk["AS_QteSto"], errors="coerce"),
            "AS_QteRes": pd.to_numeric(df_stk["AS_QteRes"], errors="coerce"),
            "AS_QteMini": pd.to_numeric(df_stk["AS_QteMini"], errors="coerce"),
            "AS_MontSto": pd.to_numeric(df_stk["AS_MontSto"], errors="coerce"),
            "source_hash": df_stk.apply(lambda r: _source_hash("ARTSTOCK", r.get("AR_Ref"), r.get("DE_No")), axis=1),
            "date_extraction": today_date
        })

        # Concatenation propre et chargement des faits multi-grain
        df_fe = pd.concat([df_g1, df_g2, df_g3, df_g4], ignore_index=True)
        load.load_fact(df_fe, "FAIT_ECRITURES")

        # -------------------------------------------------------------------
        # ETAPE D : CALCUL DES METRIQUES POST-LOAD (EN SQL SIMPLE)
        # -------------------------------------------------------------------
        logger.info("--- Calcul des KPIs de Stock et DSI en SQL ---")
        
        # D1. DSI (Stock coverage)
        dsi_sql = """
            UPDATE fe
            SET fe.qte_vendue_365j = sub.qte_vendue,
                fe.dsi_jours = CASE WHEN sub.qte_vendue > 0 THEN fe.AS_QteSto / (sub.qte_vendue / 365.0) ELSE NULL END
            FROM FAIT_ECRITURES fe
            INNER JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
            INNER JOIN (
                SELECT flv.id_article, SUM(flv.DL_Qte) AS qte_vendue
                FROM FAIT_LIGNES_VENTE flv
                JOIN DIM_DATE d ON d.id_date = flv.id_date
                JOIN DIM_DOMAINE dom ON dom.id_domaine = flv.id_domaine
                WHERE d.date_val >= DATEADD(DAY, -365, CAST(GETDATE() AS DATE)) AND dom.DO_Domaine = 0
                GROUP BY flv.id_article
            ) sub ON sub.id_article = fe.id_article
            WHERE tl.type_ligne = 4
        """
        
        # D2. Stock alert metrics
        kpi_sql = """
            UPDATE fe
            SET fe.qte_disponible = fe.AS_QteSto - fe.AS_QteRes,
                fe.ratio_tension = CASE 
                    WHEN (fe.AS_QteSto - fe.AS_QteRes) > 0 AND fe.AS_QteRes >= 0 
                    THEN CASE 
                        WHEN CAST(fe.AS_QteRes AS FLOAT) / (fe.AS_QteSto - fe.AS_QteRes) > 1 THEN 1.0
                        WHEN CAST(fe.AS_QteRes AS FLOAT) / (fe.AS_QteSto - fe.AS_QteRes) < 0 THEN 0.0
                        ELSE CAST(fe.AS_QteRes AS FLOAT) / (fe.AS_QteSto - fe.AS_QteRes)
                    END
                    ELSE NULL 
                END,
                fe.en_rupture = CASE WHEN fe.AS_QteSto <= fe.AS_QteMini THEN 1 ELSE 0 END
            FROM FAIT_ECRITURES fe
            INNER JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
            WHERE tl.type_ligne = 4
        """
        
        with DW_ENGINE.begin() as conn:
            conn.execute(text(dsi_sql))
            conn.execute(text(kpi_sql))
        logger.info("  [KPI SUCCESS] DSI et alertes ruptures de stocks mis a jour.")

        # D3. Ajouter une ligne de log dans ETL_AUDIT
        audit_sql = """
            INSERT INTO ETL_AUDIT (run_date, mode, table_name, rows_inserted, status)
            VALUES (GETUTCDATE(), 'full', 'ALL', :rows, 'SUCCESS')
        """
        with DW_ENGINE.begin() as conn:
            conn.execute(text(audit_sql), {"rows": len(df_fe)})
        
        logger.info("=== ETL : PIPELINE TERMINEE AVEC SUCCES ===")

    except Exception as exc:
        logger.exception("!!! ERREUR LORS DE L'EXECUTION DU PIPELINE !!!")
        with DW_ENGINE.begin() as conn:
            conn.execute(text("INSERT INTO ETL_AUDIT (run_date, mode, table_name, status, error_msg) VALUES (GETUTCDATE(), 'full', 'ALL', 'ERROR', :msg)"), {"msg": str(exc)[:500]})
        raise

    finally:
        # 4. Reactiver systematiquement les cles etrangeres pour preserver l'integrite
        try:
            with DW_ENGINE.begin() as conn:
                ddl.enable_all_fk(conn)
            logger.info("FK : Contraintes de cles etrangeres reactivees.")
        except Exception as fk_exc:
            logger.error(f"FK : Erreur lors de la reactivation : {fk_exc}")

        # 5. Appliquer les migrations DDL (recreation des vues & indexes pour le frontend)
        ddl.apply_schema_migrations()

if __name__ == "__main__":
    run_pipeline()