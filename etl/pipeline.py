from datetime import datetime, timezone
import pandas as pd
from sqlalchemy import text

from etl.config import DW_ENGINE, DIM_DATE_START, DIM_DATE_END
from etl.utils.logger import get_logger
from etl.utils import audit
from etl import ddl, extract, transform, load


logger = get_logger(__name__)


def _build_lookup(table_name, natural_col, surrogate_col):
    """Charge un dictionnaire {cle_naturelle: id_surrogate} depuis le data warehouse."""
    query = f"SELECT [{surrogate_col}], [{natural_col}] FROM [{table_name}]"
    df = pd.read_sql(query, DW_ENGINE)
    if table_name == "DIM_DATE" and not df.empty:
        df[natural_col] = pd.to_datetime(df[natural_col]).dt.date
    return dict(zip(df[natural_col], df[surrogate_col]))


def run_pipeline():
    logger.info("=== ETL PIPELINE STARTED ===")

    run_id = audit.start_run("full")

    ddl.create_all_tables(drop_existing=True)  # Recrée les tables avec le nouveau schéma

    today = datetime.now(timezone.utc).date()
    lookups = {}


    try:
        # --------------------------------------------------
        # STEP A: DIM_DATE
        # --------------------------------------------------
        logger.info("[DIM_DATE] Génération de la plage de dates...")
        date_range = pd.date_range(start=DIM_DATE_START, end=DIM_DATE_END, freq="D")
        df_date = pd.DataFrame({"date_val": date_range})
        df_date = transform.transform_dim_date(df_date)
        load.load_dimension(df_date, "DIM_DATE")
        lookups["DIM_DATE"] = _build_lookup("DIM_DATE", "date_val", "id_date")

        # --------------------------------------------------
        # STEP B: DIMENSIONS DYNAMIQUES
        # --------------------------------------------------

        # B1. DIM_TYPE_MVT_CAISSE
        logger.info("[DIM_TYPE_MVT_CAISSE] Extraction...")
        df_mvt = extract.extract_dim_type_mvt_caisse()
        df_mvt = df_mvt.rename(columns={"code_type_mvt": "MC_TypeMvt"})
        df_mvt = df_mvt.drop_duplicates(subset=["MC_TypeMvt"])
        load.load_dimension(df_mvt, "DIM_TYPE_MVT_CAISSE")
        lookups["DIM_TYPE_MVT_CAISSE"] = _build_lookup("DIM_TYPE_MVT_CAISSE", "MC_TypeMvt", "id_type_mvt")

        # B2. DIM_SEGMENT
        logger.info("[DIM_SEGMENT] Extraction...")
        df_seg = extract.extract_dim_segment()
        df_seg["libelle_segment"] = df_seg["cbIndice"].map({
            1: "DÉTAILLANTS", 2: "SEMI-GROS", 3: "HORECA", 4: "GROSSISTES", 5: "DISTRIBUTEUR"
        })
        df_seg["cbIndice_code"] = df_seg["cbIndice"].astype(int)
        df_seg = df_seg.drop_duplicates(subset=["cbIndice"])
        load.load_dimension(df_seg, "DIM_SEGMENT")
        lookups["DIM_SEGMENT"] = _build_lookup("DIM_SEGMENT", "cbIndice", "id_segment")

        # B3. DIM_COLLABORATEUR
        logger.info("[DIM_COLLABORATEUR] Extraction...")
        df_collab = extract.extract_dim_collaborateur()
        df_collab["CO_Fonction"] = pd.to_numeric(df_collab["CO_Fonction"], errors="coerce")
        df_collab = df_collab.drop_duplicates(subset=["CO_No"])
        load.load_dimension(df_collab, "DIM_COLLABORATEUR")
        lookups["DIM_COLLABORATEUR"] = _build_lookup("DIM_COLLABORATEUR", "CO_No", "id_collab")

        # B4. DIM_JOURNAL
        logger.info("[DIM_JOURNAL] Extraction...")
        df_jour = extract.extract_dim_journal()
        df_jour = df_jour.rename(columns={"JO_Num": "JO_Num_code"})
        df_jour = df_jour.drop_duplicates(subset=["JO_Num_code"])
        load.load_dimension(df_jour, "DIM_JOURNAL")
        lookups["DIM_JOURNAL"] = _build_lookup("DIM_JOURNAL", "JO_Num_code", "id_journal")

        # B5. DIM_FOURNISSEUR
        logger.info("[DIM_FOURNISSEUR] Extraction...")
        df_fourn = extract.extract_dim_fournisseur()
        df_fourn = df_fourn.rename(columns={"CT_Num": "CT_Num_code"})
        df_fourn = df_fourn.drop_duplicates(subset=["CT_Num_code"])
        load.load_dimension(df_fourn, "DIM_FOURNISSEUR")
        lookups["DIM_FOURNISSEUR"] = _build_lookup("DIM_FOURNISSEUR", "CT_Num_code", "id_fournisseur")

        # B6. DIM_BANQUE
        logger.info("[DIM_BANQUE] Extraction...")
        df_bq_mag = extract.extract_dim_banque_mag()
        df_bq_mag["source"] = 1
        df_bq_grt = extract.extract_dim_banque_grt()
        df_bq_grt["source"] = 2
        df_bq = pd.concat([df_bq_mag, df_bq_grt], ignore_index=True)
        df_bq = df_bq.rename(columns={"EB_Abrege": "EB_Abrege_code"})
        df_bq = df_bq.drop_duplicates(subset=["EB_Abrege_code"])
        load.load_dimension(df_bq, "DIM_BANQUE")
        lookups["DIM_BANQUE"] = _build_lookup("DIM_BANQUE", "EB_Abrege_code", "id_banque")

        # B7. DIM_FAMILLE
        logger.info("[DIM_FAMILLE] Extraction...")
        df_fam = extract.extract_dim_famille()
        df_fam = df_fam.rename(columns={
            "FA_CodeFamille": "FA_CodeFamille_code",
            "CL_No1": "niveau_0_code",
            "CL_No2": "niveau_1_code",
            "CL_No3": "niveau_2_code",
        })
        df_fam = df_fam.drop_duplicates(subset=["FA_CodeFamille_code"])
        load.load_dimension(df_fam, "DIM_FAMILLE")
        lookups["DIM_FAMILLE"] = _build_lookup("DIM_FAMILLE", "FA_CodeFamille_code", "id_famille")
        fam_labels = dict(zip(df_fam["FA_CodeFamille_code"], df_fam["FA_Intitule"]))

        # B8. DIM_CLIENT
        logger.info("[DIM_CLIENT] Extraction depuis MAG + GRT...")
        df_cli_mag = extract.extract_dim_client_mag()
        df_cli_grt = extract.extract_dim_client_grt()
        df_cli = pd.merge(df_cli_mag, df_cli_grt, on="CT_Num", how="left")
        df_cli = df_cli.rename(columns={"CT_Num": "CT_Num_code"})
        df_cli["id_segment"] = df_cli["N_CatTarif"].map(lookups["DIM_SEGMENT"])
        df_cli["id_collab"] = df_cli["CO_No"].map(lookups["DIM_COLLABORATEUR"])
        df_cli = df_cli.drop_duplicates(subset=["CT_Num_code"])
        load.load_dimension(df_cli, "DIM_CLIENT")
        lookups["DIM_CLIENT"] = _build_lookup("DIM_CLIENT", "CT_Num_code", "id_client")

        # B9. DIM_ARTICLE
        logger.info("[DIM_ARTICLE] Extraction...")
        df_art = extract.extract_dim_article()
        df_art = df_art.rename(columns={"AR_Ref": "AR_Ref_code", "CT_Num_fourn": "CT_Num_fourn_raw"})
        df_art["id_famille"] = df_art["FA_CodeFamille"].map(lookups["DIM_FAMILLE"])
        df_art["id_fournisseur"] = df_art["CT_Num_fourn_raw"].map(lookups["DIM_FOURNISSEUR"])
        df_art["FA_Intitule"] = df_art["FA_CodeFamille"].map(fam_labels)
        df_art = df_art.drop_duplicates(subset=["AR_Ref_code"])
        load.load_dimension(df_art, "DIM_ARTICLE")
        lookups["DIM_ARTICLE"] = _build_lookup("DIM_ARTICLE", "AR_Ref_code", "id_article")

        # B10. DIM_DEPOT
        logger.info("[DIM_DEPOT] Extraction...")
        df_dep = extract.extract_dim_depot()
        df_dep = df_dep.drop_duplicates(subset=["DE_No"])
        load.load_dimension(df_dep, "DIM_DEPOT")
        lookups["DIM_DEPOT"] = _build_lookup("DIM_DEPOT", "DE_No", "id_depot")

        # B11. DIM_CAISSE
        logger.info("[DIM_CAISSE] Extraction...")
        df_caisse = extract.extract_dim_caisse_mag()
        df_caisse = df_caisse.rename(columns={"CA_No": "CA_Numero_code"})
        df_caisse["id_journal"] = df_caisse["JO_Num"].map(lookups["DIM_JOURNAL"])
        df_caisse = df_caisse.drop_duplicates(subset=["CA_Numero_code"])
        load.load_dimension(df_caisse, "DIM_CAISSE")
        lookups["DIM_CAISSE"] = _build_lookup("DIM_CAISSE", "CA_Numero_code", "id_caisse")

        # --------------------------------------------------
        # STEP C: TABLES DE FAITS
        # --------------------------------------------------

        # C1. FAIT_LIGNES_VENTE
        logger.info("[FAIT_LIGNES_VENTE] Extraction ventes + achats...")
        df_vente = extract.extract_fait_lignes_vente()
        df_achat = extract.extract_fait_lignes_achat()
        df_flv = pd.concat([df_vente, df_achat], ignore_index=True)
        df_flv["DO_Piece_hash"] = df_flv["DO_Piece"].apply(
            lambda v: abs(hash(str(v))) if pd.notna(v) else None
        )
        df_flv["id_date"]    = pd.to_datetime(df_flv["DO_Date"]).dt.date.map(lookups["DIM_DATE"])
        df_flv["id_client"]  = df_flv["CT_Num"].map(lookups["DIM_CLIENT"])
        df_flv["id_article"] = df_flv["AR_Ref"].map(lookups["DIM_ARTICLE"])
        df_flv["date_extraction"] = today
        load.load_fact(df_flv, "FAIT_LIGNES_VENTE")

        # C2. FAIT_REGLEMENTS
        logger.info("[FAIT_REGLEMENTS] Extraction règlements...")
        df_rc = extract.extract_fait_reglements_clients()
        df_rc["_acteur"] = "CLIENT"
        df_rf = extract.extract_fait_reglements_fournisseurs()
        df_rf["_acteur"] = "FOURNISSEUR"
        df_doc_dates = extract.extract_docentete_dates()[["DO_Type", "DO_Piece", "DO_Date"]].drop_duplicates(subset=["DO_Type", "DO_Piece"])
        df_docregl = extract.extract_docregl_grt().drop_duplicates(subset=["DO_Piece"])
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
        df_reg["id_client"] = df_reg.apply(
            lambda r: lookups["DIM_CLIENT"].get(r["CT_Num"]) if r["_acteur"] == "CLIENT" else None, axis=1
        )
        df_reg["id_fournisseur"] = df_reg.apply(
            lambda r: lookups["DIM_FOURNISSEUR"].get(r["CT_Num"]) if r["_acteur"] == "FOURNISSEUR" else None, axis=1
        )
        df_reg["id_banque"] = df_reg["BQ_ABREGE"].map(lookups["DIM_BANQUE"])
        df_reg["date_extraction"] = today
        df_reg["RT_Rapproche"] = pd.to_numeric(df_reg.get("RT_Rapproche"), errors="coerce").fillna(0).astype("int16")
        load.load_fact(df_reg, "FAIT_REGLEMENTS")

        # C3. FAIT_ECRITURES (4 grains)
        logger.info("[FAIT_ECRITURES] Construction de la table de faits multi-grain...")

        # Grain 1 : Écritures comptables
        df_ecr = extract.extract_fait_ecriturec()
        df_g1 = pd.DataFrame({
            "id_date":    pd.to_datetime(df_ecr["EC_Date"]).dt.date.map(lookups["DIM_DATE"]),
            "grain":      1,
            "id_journal": df_ecr["JO_Num"].map(lookups["DIM_JOURNAL"]),
            "id_client":  df_ecr["CT_Num"].map(lookups["DIM_CLIENT"]),
            "EC_Sens":    df_ecr["EC_Sens"],
            "EC_Montant": pd.to_numeric(df_ecr["EC_Montant"], errors="coerce"),
            "EC_No":      df_ecr["EC_No"],
            "CG_Num":     df_ecr["CG_Num"],
            "date_extraction": today,
        })

        # Grain 2 : TVA
        df_tva = extract.extract_fait_regtaxe()
        df_g2 = pd.DataFrame({
            "id_date":      pd.to_datetime(df_tva["EC_Date"]).dt.date.map(lookups["DIM_DATE"]),
            "grain":        2,
            "id_journal":   df_tva["JO_Num"].map(lookups["DIM_JOURNAL"]),
            "id_client":    df_tva["CT_Num"].map(lookups["DIM_CLIENT"]),
            "EC_TauxTVA":   pd.to_numeric(df_tva["TA_Taux01"], errors="coerce"),
            "RT_Montant01": pd.to_numeric(df_tva["RT_Montant01"], errors="coerce"),
            "RT_Base01":    pd.to_numeric(df_tva["RT_Base01"], errors="coerce"),
            "EC_No":        df_tva["EC_No"],
            "date_extraction": today,
        })

        # Grain 3 : Mouvements caisse
        df_mc = extract.extract_fait_mvtcaisse()
        df_g3 = pd.DataFrame({
            "id_date":          pd.to_datetime(df_mc["MC_Date"]).dt.date.map(lookups["DIM_DATE"]),
            "grain":            3,
            "id_journal":       df_mc["JO_Num"].map(lookups["DIM_JOURNAL"]),
            "id_caisse":        df_mc["CA_No"].map(lookups["DIM_CAISSE"]),
            "id_type_mvt_caisse": df_mc["MC_TypeMvt"].map(lookups["DIM_TYPE_MVT_CAISSE"]),
            "MC_Debit":         pd.to_numeric(df_mc["MC_Debit"], errors="coerce"),
            "MC_Credit":        pd.to_numeric(df_mc["MC_Credit"], errors="coerce"),
            "CA_SoldeEspece":   pd.to_numeric(df_mc["CA_SoldeEspece"], errors="coerce"),
            "CA_SoldeCheque":   pd.to_numeric(df_mc["CA_SoldeCheque"], errors="coerce"),
            "date_extraction":  today,
        })

        # Grain 4 : Stock snapshot
        df_stk = extract.extract_fait_artstock()
        today_id = lookups["DIM_DATE"].get(today)
        df_g4 = pd.DataFrame({
            "id_date":    today_id,
            "grain":      4,
            "id_article": df_stk["AR_Ref"].map(lookups["DIM_ARTICLE"]),
            "id_depot":   df_stk["DE_No"].map(lookups["DIM_DEPOT"]),
            "AS_QteSto":  pd.to_numeric(df_stk["AS_QteSto"], errors="coerce"),
            "AS_QteRes":  pd.to_numeric(df_stk["AS_QteRes"], errors="coerce"),
            "AS_QteMini": pd.to_numeric(df_stk["AS_QteMini"], errors="coerce"),
            "AS_MontSto": pd.to_numeric(df_stk["AS_MontSto"], errors="coerce"),
            "date_extraction": today,
        })

        df_fe = pd.concat([df_g1, df_g2, df_g3, df_g4], ignore_index=True)
        load.load_fact(df_fe, "FAIT_ECRITURES")

        # --------------------------------------------------
        # STEP D: CALCULS POST-CHARGEMENT (KPIs stock)
        # --------------------------------------------------
        logger.info("[POST-LOAD] Calcul des KPIs stock...")

        dsi_sql = """
            UPDATE fe
            SET
                fe.qte_vendue_365j = sub.qte_vendue,
                fe.dsi_jours = CASE
                    WHEN sub.qte_vendue > 0
                    THEN fe.AS_QteSto / (sub.qte_vendue / 365.0)
                    ELSE NULL
                END
            FROM FAIT_ECRITURES fe
            JOIN (
                SELECT flv.id_article, SUM(flv.DL_Qte) AS qte_vendue
                FROM FAIT_LIGNES_VENTE flv
                JOIN DIM_DATE d ON d.id_date = flv.id_date
                WHERE d.date_val >= DATEADD(DAY, -365, CAST(GETDATE() AS DATE))
                AND flv.DO_Domaine = 0
                GROUP BY flv.id_article
            ) sub ON sub.id_article = fe.id_article
            WHERE fe.grain = 4
        """

        kpi_sql = """
            UPDATE FAIT_ECRITURES
            SET
                qte_disponible = AS_QteSto - AS_QteRes,
                ratio_tension = CASE
                    WHEN (AS_QteSto - AS_QteRes) > 0
                    THEN CAST(AS_QteRes AS FLOAT) / (AS_QteSto - AS_QteRes)
                    ELSE NULL
                END,
                en_rupture = CASE WHEN AS_QteSto <= AS_QteMini THEN 1 ELSE 0 END
            WHERE grain = 4
        """

        with DW_ENGINE.begin() as conn:
            conn.execute(text(dsi_sql))
            conn.execute(text(kpi_sql))

        logger.info("=== ETL PIPELINE COMPLETED SUCCESSFULLY ===")
        audit.end_run(run_id, "SUCCESS")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        audit.end_run(run_id, "FAILED", error_msg=str(e))
        raise



if __name__ == "__main__":
    run_pipeline()