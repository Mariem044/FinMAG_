from sqlalchemy import text
from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)


def table_exists(table_name):
    """Retourne True si la table existe déjà dans la base de données."""
    sql = """
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = :tbl AND TABLE_TYPE = 'BASE TABLE'
    """
    with DW_ENGINE.connect() as conn:
        result = conn.execute(text(sql), {"tbl": table_name}).scalar()
    return result is not None and result > 0


def create_all_tables(drop_existing=False):
    """Crée toutes les tables du data warehouse."""
    logger.info("=== Création des tables du data warehouse ===")

    if drop_existing:
        _drop_all_tables()

    tables = {
        "DIM_DATE": """
            CREATE TABLE DIM_DATE (
                id_date      INT IDENTITY(1,1) PRIMARY KEY,
                date_val     DATE NOT NULL UNIQUE,
                jour         SMALLINT NOT NULL,
                mois         SMALLINT NOT NULL,
                trimestre    SMALLINT NOT NULL,
                semestre     SMALLINT NOT NULL,
                annee        SMALLINT NOT NULL,
                semaine      SMALLINT NOT NULL,
                jour_semaine SMALLINT NOT NULL,
                est_weekend  SMALLINT NOT NULL DEFAULT 0,
                est_ferie    SMALLINT NOT NULL DEFAULT 0,
                exercice     SMALLINT NULL
            )
        """,
        "DIM_TYPE_MVT_CAISSE": """
            CREATE TABLE DIM_TYPE_MVT_CAISSE (
                id_type_mvt INT IDENTITY(1,1) PRIMARY KEY,
                MC_TypeMvt  SMALLINT NOT NULL UNIQUE
            )
        """,
        "DIM_BANQUE": """
            CREATE TABLE DIM_BANQUE (
                id_banque      INT IDENTITY(1,1) PRIMARY KEY,
                EB_Abrege_code NVARCHAR(50) NOT NULL UNIQUE,
                EB_Banque      NVARCHAR(100) NULL,
                source         SMALLINT NOT NULL DEFAULT 1
            )
        """,
        "DIM_SEGMENT": """
            CREATE TABLE DIM_SEGMENT (
                id_segment      INT IDENTITY(1,1) PRIMARY KEY,
                cbIndice        SMALLINT NOT NULL UNIQUE,
                cbIndice_code   INT NOT NULL,
                CT_PrixTTC      SMALLINT NOT NULL DEFAULT 0,
                libelle_segment NVARCHAR(100) NULL
            )
        """,
        "DIM_COLLABORATEUR": """
            CREATE TABLE DIM_COLLABORATEUR (
                id_collab   INT IDENTITY(1,1) PRIMARY KEY,
                CO_No       INT NOT NULL UNIQUE,
                CO_Fonction INT NULL,
                CO_Sommeil  SMALLINT NOT NULL DEFAULT 0
            )
        """,
        "DIM_JOURNAL": """
            CREATE TABLE DIM_JOURNAL (
                id_journal   INT IDENTITY(1,1) PRIMARY KEY,
                JO_Num_code  NVARCHAR(50) NOT NULL UNIQUE,
                JO_Type      SMALLINT NULL
            )
        """,
        "DIM_FOURNISSEUR": """
            CREATE TABLE DIM_FOURNISSEUR (
                id_fournisseur INT IDENTITY(1,1) PRIMARY KEY,
                CT_Num_code    NVARCHAR(50) NOT NULL UNIQUE,
                CT_Intitule    NVARCHAR(100) NULL,
                CT_Sommeil     SMALLINT NOT NULL DEFAULT 0,
                CT_Encours     NUMERIC(18,4) NULL,
                CT_SvCA        NUMERIC(18,4) NULL
            )
        """,
        "DIM_FAMILLE": """
            CREATE TABLE DIM_FAMILLE (
                id_famille          INT IDENTITY(1,1) PRIMARY KEY,
                FA_CodeFamille_code NVARCHAR(50) NOT NULL UNIQUE,
                FA_Intitule         NVARCHAR(100) NULL,
                niveau_0_code       NVARCHAR(50) NULL,
                niveau_1_code       NVARCHAR(50) NULL,
                niveau_2_code       NVARCHAR(50) NULL,
                niveau_3_code       NVARCHAR(50) NULL
            )
        """,
        "DIM_CLIENT": """
            CREATE TABLE DIM_CLIENT (
                id_client               INT IDENTITY(1,1) PRIMARY KEY,
                CT_Num_code             NVARCHAR(50) NOT NULL UNIQUE,
                CT_Intitule             NVARCHAR(100) NULL,
                CT_Sommeil              SMALLINT NOT NULL DEFAULT 0,
                id_segment              INT NULL,
                id_collab               INT NULL,
                CT_Encours              NUMERIC(18,4) NULL,
                CT_SvCA                 NUMERIC(18,4) NULL,
                CT_SoldeActuel          NUMERIC(18,4) NULL,
                CT_Engagement           NUMERIC(18,4) NULL,
                CT_ChiffreAffaire       NUMERIC(18,4) NULL,
                CT_EchusUnMois          NUMERIC(18,4) NULL,
                CT_EchusDeuxMois        NUMERIC(18,4) NULL,
                CT_EchusTroisMois       NUMERIC(18,4) NULL,
                CT_EchusPlusTroisMois   NUMERIC(18,4) NULL,
                CT_MoyenneDelaiPayement NUMERIC(18,4) NULL,
                CT_MoyenneDelaiImpaye   NUMERIC(18,4) NULL,
                CT_Ville                NVARCHAR(50) NULL,
                CT_CodeRegion           NVARCHAR(50) NULL,
                gouvernorat             NVARCHAR(50) NULL,
                rfm_recence_jours       INT NULL,
                rfm_frequence           INT NULL,
                rfm_montant_12m         NUMERIC(18,4) NULL
            )
        """,
        "DIM_ARTICLE": """
            CREATE TABLE DIM_ARTICLE (
                id_article     INT IDENTITY(1,1) PRIMARY KEY,
                AR_Ref_code    NVARCHAR(50) NOT NULL UNIQUE,
                AR_Design      NVARCHAR(200) NULL,
                id_famille     INT NULL,
                id_fournisseur INT NULL,
                FA_Intitule    NVARCHAR(100) NULL,
                AR_Sommeil     SMALLINT NOT NULL DEFAULT 0,
                AR_PrixAch     NUMERIC(18,4) NULL,
                AR_SuiviStock  SMALLINT NOT NULL DEFAULT 0
            )
        """,
        "DIM_DEPOT": """
            CREATE TABLE DIM_DEPOT (
                id_depot     INT IDENTITY(1,1) PRIMARY KEY,
                DE_No        INT NOT NULL UNIQUE,
                DE_Intitule  NVARCHAR(100) NULL,
                DE_Principal SMALLINT NOT NULL DEFAULT 0
            )
        """,
        "DIM_CAISSE": """
            CREATE TABLE DIM_CAISSE (
                id_caisse      INT IDENTITY(1,1) PRIMARY KEY,
                CA_Numero_code NVARCHAR(50) NOT NULL UNIQUE,
                CA_Type        SMALLINT NULL,
                id_journal     INT NULL
            )
        """,
        "FAIT_LIGNES_VENTE": """
            CREATE TABLE FAIT_LIGNES_VENTE (
                id_ligne        INT IDENTITY(1,1) PRIMARY KEY,
                id_date         INT NULL,
                id_client       INT NULL,
                id_article      INT NULL,
                DO_Domaine      SMALLINT NULL,
                DO_Type         SMALLINT NULL,
                DL_Qte          NUMERIC(18,4) NULL,
                DL_PrixUnitaire NUMERIC(18,4) NULL,
                DL_Taxe1        NUMERIC(18,4) NULL,
                DL_MontantHT    NUMERIC(18,4) NULL,
                DL_MontantTTC   NUMERIC(18,4) NULL,
                DO_TxEscompte   NUMERIC(18,4) NULL,
                DO_TotalHT      NUMERIC(18,4) NULL,
                DO_TotalHTNet   NUMERIC(18,4) NULL,
                DO_TotalTTC     NUMERIC(18,4) NULL,
                DO_NetAPayer    NUMERIC(18,4) NULL,
                DO_MontantRegle NUMERIC(18,4) NULL,
                DL_CMUP         NUMERIC(18,4) NULL,
                DL_PrixRU       NUMERIC(18,4) NULL,
                DO_Piece_hash   BIGINT NULL,
                date_extraction DATE NOT NULL
            )
        """,
        "FAIT_REGLEMENTS": """
            CREATE TABLE FAIT_REGLEMENTS (
                id_reglement     INT IDENTITY(1,1) PRIMARY KEY,
                id_date_paiement INT NULL,
                id_date_echeance INT NULL,
                id_client        INT NULL,
                id_fournisseur   INT NULL,
                id_banque        INT NULL,
                RT_Mode          SMALLINT NULL,
                RT_Etat          SMALLINT NULL,
                DR_Regle         SMALLINT NULL,
                DO_Type          SMALLINT NULL,
                RT_Num           NVARCHAR(50) NULL,
                RT_Montant       NUMERIC(18,4) NULL,
                DR_Montant       NUMERIC(18,4) NULL,
                LB_Agios         NUMERIC(18,4) NULL,
                LB_NbJour        SMALLINT NULL,
                RT_NbJour        SMALLINT NULL,
                delai_reel_jours INT NULL,
                ecart_delai      INT NULL,
                bucket_impaye    SMALLINT NULL,
                DR_ModeReg       SMALLINT NULL,
                RT_Rapproche     SMALLINT NOT NULL DEFAULT 0,
                date_extraction  DATE NOT NULL
            )
        """,
        "FAIT_ECRITURES": """
            CREATE TABLE FAIT_ECRITURES (
                id_ecriture        INT IDENTITY(1,1) PRIMARY KEY,
                id_date            INT NULL,
                grain              SMALLINT NULL,
                id_journal         INT NULL,
                id_banque          INT NULL,
                id_client          INT NULL,
                id_fournisseur     INT NULL,
                id_article         INT NULL,
                id_depot           INT NULL,
                id_type_mvt_caisse INT NULL,
                id_caisse          INT NULL,
                EC_Sens            SMALLINT NULL,
                EC_Montant         NUMERIC(18,4) NULL,
                EC_TauxTVA         NUMERIC(18,4) NULL,
                CG_Num             INT NULL,
                RT_Base01          NUMERIC(18,4) NULL,
                RT_Montant01       NUMERIC(18,4) NULL,
                AS_MontSto         NUMERIC(18,4) NULL,
                AS_QteSto          NUMERIC(18,4) NULL,
                AS_QteMini         NUMERIC(18,4) NULL,
                AS_QteRes          NUMERIC(18,4) NULL,
                qte_disponible     NUMERIC(18,4) NULL,
                ratio_tension      NUMERIC(18,4) NULL,
                en_rupture         SMALLINT NULL,
                alerte_tension     SMALLINT NULL,
                qte_vendue_365j    NUMERIC(18,4) NULL,
                dsi_jours          NUMERIC(18,4) NULL,
                MC_Debit           NUMERIC(18,4) NULL,
                MC_Credit          NUMERIC(18,4) NULL,
                CA_SoldeEspece     NUMERIC(18,4) NULL,
                CA_SoldeCheque     NUMERIC(18,4) NULL,
                EC_No              INT NULL,
                date_extraction    DATE NOT NULL
            )
        """,
        "DIM_MODE_REGLEMENT": """
            CREATE TABLE DIM_MODE_REGLEMENT (
                id_mode_reg      INT IDENTITY(1,1) PRIMARY KEY,
                RT_Mode          SMALLINT NOT NULL UNIQUE,
                libelle_mode_reg NVARCHAR(50) NULL
            )
        """,
        "ETL_AUDIT": """
            CREATE TABLE ETL_AUDIT (
                run_id           INT IDENTITY(1,1) PRIMARY KEY,
                run_date         DATETIME NOT NULL DEFAULT GETUTCDATE(),
                mode             VARCHAR(10) NOT NULL,
                table_name       VARCHAR(100) NOT NULL,
                rows_inserted    INT NOT NULL DEFAULT 0,
                rows_updated     INT NOT NULL DEFAULT 0,
                duration_seconds INT NOT NULL DEFAULT 0,
                status           VARCHAR(20) NOT NULL,
                error_msg        NVARCHAR(500) NULL
            )
        """,
    }

    with DW_ENGINE.begin() as conn:
        for table_name, ddl_sql in tables.items():
            if (not drop_existing or table_name == "ETL_AUDIT") and table_exists(table_name):
                logger.info(f"  [SKIP] {table_name} existe déjà")
                continue
            try:
                conn.execute(text(ddl_sql.strip()))
                logger.info(f"  [OK] {table_name} créée")
            except Exception as e:
                logger.error(f"  [ERREUR] {table_name}: {e}")
                raise

    logger.info("=== Toutes les tables créées ===")


def _drop_all_tables():
    """Supprime toutes les tables dans le bon ordre pour éviter les erreurs de clé étrangère."""
    logger.warning("Suppression de toutes les tables existantes...")

    # Supprimer d'abord les faits, puis les dimensions
    drop_order = [
        "FAIT_ECRITURES", "FAIT_REGLEMENTS", "FAIT_LIGNES_VENTE",
        "DIM_CAISSE", "DIM_ARTICLE", "DIM_CLIENT", "DIM_DEPOT",
        "DIM_FAMILLE", "DIM_FOURNISSEUR", "DIM_JOURNAL", "DIM_COLLABORATEUR",
        "DIM_SEGMENT", "DIM_BANQUE", "DIM_TYPE_MVT_CAISSE",
        "DIM_MODE_REGLEMENT", "DIM_DATE",
    ]

    with DW_ENGINE.begin() as conn:
        for table_name in drop_order:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS [{table_name}]"))
                logger.info(f"  [DROP] {table_name}")
            except Exception as e:
                logger.warning(f"  [DROP WARN] {table_name}: {e}")