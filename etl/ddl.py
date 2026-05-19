from __future__ import annotations

from sqlalchemy import text

from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)

ALL_DDL: list[tuple[str, str]] = [
    ("DIM_DATE", """
    CREATE TABLE DIM_DATE (
        id_date          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        date_val         DATE NOT NULL UNIQUE,
        jour             SMALLINT NOT NULL,
        mois             SMALLINT NOT NULL,
        trimestre        SMALLINT NOT NULL,
        semestre         SMALLINT NOT NULL,
        annee            SMALLINT NOT NULL,
        semaine          SMALLINT NOT NULL,
        jour_semaine     SMALLINT NOT NULL,
        est_weekend      SMALLINT NOT NULL DEFAULT 0,
        est_ferie        SMALLINT NOT NULL DEFAULT 0,
        exercice         SMALLINT NULL
    )"""),

    ("DIM_DOMAINE", """
    CREATE TABLE DIM_DOMAINE (
        id_domaine       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        DO_Domaine       SMALLINT NOT NULL UNIQUE,
        libelle_domaine  NVARCHAR(100) NOT NULL
    )"""),

    ("DIM_TYPE_DOC", """
    CREATE TABLE DIM_TYPE_DOC (
        id_type_doc      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        DO_Type          SMALLINT NOT NULL UNIQUE,
        libelle_type_doc NVARCHAR(100) NOT NULL
    )"""),

    ("DIM_MODE_REGLEMENT", """
    CREATE TABLE DIM_MODE_REGLEMENT (
        id_mode_reg      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        RT_Mode          SMALLINT NOT NULL UNIQUE,
        libelle_mode_reg NVARCHAR(100) NOT NULL
    )"""),

    ("DIM_ETAT_REGLEMENT", """
    CREATE TABLE DIM_ETAT_REGLEMENT (
        id_etat_reg      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        RT_Etat          SMALLINT NOT NULL UNIQUE,
        libelle_etat_reg NVARCHAR(100) NOT NULL
    )"""),

    ("DIM_ETAT_DOCREGL", """
    CREATE TABLE DIM_ETAT_DOCREGL (
        id_etat_docregl      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        DR_Regle             SMALLINT NOT NULL UNIQUE,
        libelle_etat_docregl NVARCHAR(100) NOT NULL
    )"""),

    ("DIM_TYPE_LIGNE", """
    CREATE TABLE DIM_TYPE_LIGNE (
        id_type_ligne      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        type_ligne         SMALLINT NOT NULL UNIQUE,
        libelle_type_ligne NVARCHAR(100) NOT NULL
    )"""),

    ("DIM_SENS_ECRITURE", """
    CREATE TABLE DIM_SENS_ECRITURE (
        id_sens            INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        EC_Sens            SMALLINT NOT NULL UNIQUE,
        libelle_sens       NVARCHAR(100) NOT NULL
    )"""),

    ("DIM_TYPE_TVA", """
    CREATE TABLE DIM_TYPE_TVA (
        id_type_tva        INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        type_tva           SMALLINT NOT NULL UNIQUE,
        libelle_type_tva   NVARCHAR(100) NOT NULL
    )"""),

    ("DIM_TYPE_MVT_CAISSE", """
    CREATE TABLE DIM_TYPE_MVT_CAISSE (
        id_type_mvt        INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        MC_TypeMvt         SMALLINT NOT NULL UNIQUE,
        libelle_type_mvt   NVARCHAR(100) NOT NULL
    )"""),

    ("DIM_BANQUE", """
    CREATE TABLE DIM_BANQUE (
        id_banque          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        EB_Abrege_code     BIGINT NOT NULL UNIQUE,
        EB_Banque          INT NULL,
        source             SMALLINT NOT NULL DEFAULT 1,
        row_hash           BINARY(32) NULL
    )"""),

    # --- DIMENSIONS DYNAMIQUES ---
    ("DIM_SEGMENT", """
    CREATE TABLE DIM_SEGMENT (
        id_segment         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        cbIndice           SMALLINT NOT NULL UNIQUE,
        cbIndice_code      BIGINT NOT NULL UNIQUE,
        CT_PrixTTC         SMALLINT NOT NULL DEFAULT 0,
        libelle_segment    NVARCHAR(100) NOT NULL,
        row_hash           BINARY(32) NULL
    )"""),

    ("DIM_COLLABORATEUR", """
    CREATE TABLE DIM_COLLABORATEUR (
        id_collab          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        CO_No              INT NOT NULL UNIQUE,
        CO_Fonction        INT NULL,
        CO_Sommeil         SMALLINT NOT NULL DEFAULT 0,
        row_hash           BINARY(32) NULL
    )"""),

    ("DIM_JOURNAL", """
    CREATE TABLE DIM_JOURNAL (
        id_journal         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        JO_Num_code        BIGINT NOT NULL UNIQUE,
        JO_Type            SMALLINT NULL,
        row_hash           BINARY(32) NULL
    )"""),

    ("DIM_FOURNISSEUR", """
    CREATE TABLE DIM_FOURNISSEUR (
        id_fournisseur     INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        CT_Num_code        BIGINT NOT NULL UNIQUE,
        CT_Sommeil         SMALLINT NOT NULL DEFAULT 0,
        CT_Encours         NUMERIC(18,4) NULL,
        CT_SvCA            NUMERIC(18,4) NULL,
        row_hash           BINARY(32) NULL
    )"""),

    ("DIM_FAMILLE", """
    CREATE TABLE DIM_FAMILLE (
        id_famille          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        FA_CodeFamille_code BIGINT NOT NULL UNIQUE,
        FA_Intitule         NVARCHAR(100) NULL,
        niveau_0_code       BIGINT NULL,
        niveau_1_code       BIGINT NULL,
        niveau_2_code       BIGINT NULL,
        row_hash            BINARY(32) NULL
    )"""),

    ("DIM_CLIENT", """
    CREATE TABLE DIM_CLIENT (
        id_client               INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        CT_Num_code             BIGINT NOT NULL UNIQUE,
        CT_Sommeil              SMALLINT NOT NULL DEFAULT 0,
        id_segment              INT NULL REFERENCES DIM_SEGMENT(id_segment) ON DELETE NO ACTION,
        id_collab               INT NULL REFERENCES DIM_COLLABORATEUR(id_collab) ON DELETE NO ACTION,
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
        CT_Intitule             NVARCHAR(100) NULL,
        CT_Ville                NVARCHAR(50) NULL,
        CT_CodeRegion           NVARCHAR(50) NULL,
        gouvernorat             NVARCHAR(50) NULL,
        row_hash                BINARY(32) NULL
    )"""),

    ("DIM_ARTICLE", """
    CREATE TABLE DIM_ARTICLE (
        id_article         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        AR_Ref_code        BIGINT NOT NULL UNIQUE,
        id_famille         INT NULL REFERENCES DIM_FAMILLE(id_famille) ON DELETE NO ACTION,
        id_fournisseur     INT NULL REFERENCES DIM_FOURNISSEUR(id_fournisseur) ON DELETE NO ACTION,
        FA_Intitule        NVARCHAR(100) NULL,
        AR_Sommeil         SMALLINT NOT NULL DEFAULT 0,
        AR_PrixAch         NUMERIC(18,4) NULL,
        AR_SuiviStock      SMALLINT NOT NULL DEFAULT 0,
        row_hash           BINARY(32) NULL
    )"""),

    ("DIM_DEPOT", """
    CREATE TABLE DIM_DEPOT (
        id_depot           INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        DE_No              INT NOT NULL UNIQUE,
        DE_Principal       SMALLINT NOT NULL DEFAULT 0,
        row_hash           BINARY(32) NULL
    )"""),

    ("DIM_CAISSE", """
    CREATE TABLE DIM_CAISSE (
        id_caisse          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        CA_Numero_code     BIGINT NOT NULL UNIQUE,
        CA_Type            SMALLINT NULL,
        id_journal         INT NULL REFERENCES DIM_JOURNAL(id_journal) ON DELETE NO ACTION,
        row_hash           BINARY(32) NULL
    )"""),

    # --- TABLES DE FAITS ---
    ("FAIT_LIGNES_VENTE", """
    CREATE TABLE FAIT_LIGNES_VENTE (
        id_ligne           INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        id_date            INT NULL REFERENCES DIM_DATE(id_date) ON DELETE NO ACTION,
        id_type_doc        INT NULL REFERENCES DIM_TYPE_DOC(id_type_doc) ON DELETE NO ACTION,
        id_domaine         INT NULL REFERENCES DIM_DOMAINE(id_domaine) ON DELETE NO ACTION,
        id_client          INT NULL REFERENCES DIM_CLIENT(id_client) ON DELETE NO ACTION,
        id_article         INT NULL REFERENCES DIM_ARTICLE(id_article) ON DELETE NO ACTION,
        DL_Qte             NUMERIC(18,4) NULL,
        DL_PrixUnitaire    NUMERIC(18,4) NULL,
        DL_Taxe1           NUMERIC(18,4) NULL,
        DL_MontantHT       NUMERIC(18,4) NULL,
        DL_MontantTTC      NUMERIC(18,4) NULL,
        DO_TxEscompte      NUMERIC(18,4) NULL,
        DO_TotalHT         NUMERIC(18,4) NULL,
        DO_TotalHTNet      NUMERIC(18,4) NULL,
        DO_TotalTTC        NUMERIC(18,4) NULL,
        DO_NetAPayer       NUMERIC(18,4) NULL,
        DO_MontantRegle    NUMERIC(18,4) NULL,
        DL_CMUP            NUMERIC(18,4) NULL,
        DL_PrixRU          NUMERIC(18,4) NULL,
        DO_Piece_hash      BIGINT NULL,
        source_hash        BINARY(32) NULL,
        date_extraction    DATE NOT NULL
    )"""),

    ("FAIT_REGLEMENTS", """
    CREATE TABLE FAIT_REGLEMENTS (
        id_reglement       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        id_date_paiement   INT NULL REFERENCES DIM_DATE(id_date) ON DELETE NO ACTION,
        id_date_echeance   INT NULL REFERENCES DIM_DATE(id_date) ON DELETE NO ACTION,
        id_client          INT NULL REFERENCES DIM_CLIENT(id_client) ON DELETE NO ACTION,
        id_fournisseur     INT NULL REFERENCES DIM_FOURNISSEUR(id_fournisseur) ON DELETE NO ACTION,
        id_banque          INT NULL REFERENCES DIM_BANQUE(id_banque) ON DELETE NO ACTION,
        id_mode_reg        INT NULL REFERENCES DIM_MODE_REGLEMENT(id_mode_reg) ON DELETE NO ACTION,
        id_etat_reg        INT NULL REFERENCES DIM_ETAT_REGLEMENT(id_etat_reg) ON DELETE NO ACTION,
        id_etat_docregl    INT NULL REFERENCES DIM_ETAT_DOCREGL(id_etat_docregl) ON DELETE NO ACTION,
        id_type_doc        INT NULL REFERENCES DIM_TYPE_DOC(id_type_doc) ON DELETE NO ACTION,
        RT_Montant         NUMERIC(18,4) NULL,
        DR_Montant         NUMERIC(18,4) NULL,
        RC_Montant         NUMERIC(18,4) NULL,
        RG_Montant         NUMERIC(18,4) NULL,
        LB_Agios           NUMERIC(18,4) NULL,
        LB_NbJour          SMALLINT NULL,
        LB_MontantReg      NUMERIC(18,4) NULL,
        BR_TotalReglement  NUMERIC(18,4) NULL,
        BR_Rapproch        SMALLINT NULL,
        BR_TauxAgios       NUMERIC(18,4) NULL,
        BR_TMM             NUMERIC(18,4) NULL,
        RT_NbJour          SMALLINT NULL,
        delai_reel_jours   INT NULL,
        ecart_delai        INT NULL,
        bucket_impaye      SMALLINT NULL,
        DR_Regle           SMALLINT NULL,
        DR_ModeReg         SMALLINT NULL,
        RT_Rapproche       SMALLINT NOT NULL DEFAULT 0,
        source_hash        BINARY(32) NULL,
        date_extraction    DATE NOT NULL,
        CONSTRAINT chk_regl_excl CHECK (
            (id_client IS NOT NULL AND id_fournisseur IS NULL) OR
            (id_fournisseur IS NOT NULL AND id_client IS NULL) OR
            (id_client IS NULL AND id_fournisseur IS NULL)
        )
    )"""),

    ("FAIT_ECRITURES", """
    CREATE TABLE FAIT_ECRITURES (
        id_ecriture        INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        id_date            INT NULL REFERENCES DIM_DATE(id_date) ON DELETE NO ACTION,
        id_type_ligne      INT NULL REFERENCES DIM_TYPE_LIGNE(id_type_ligne) ON DELETE NO ACTION,
        id_journal         INT NULL REFERENCES DIM_JOURNAL(id_journal) ON DELETE NO ACTION,
        id_banque          INT NULL REFERENCES DIM_BANQUE(id_banque) ON DELETE NO ACTION,
        id_client          INT NULL REFERENCES DIM_CLIENT(id_client) ON DELETE NO ACTION,
        id_fournisseur     INT NULL REFERENCES DIM_FOURNISSEUR(id_fournisseur) ON DELETE NO ACTION,
        id_article         INT NULL REFERENCES DIM_ARTICLE(id_article) ON DELETE NO ACTION,
        id_depot           INT NULL REFERENCES DIM_DEPOT(id_depot) ON DELETE NO ACTION,
        id_type_tva        INT NULL REFERENCES DIM_TYPE_TVA(id_type_tva) ON DELETE NO ACTION,
        id_type_mvt_caisse INT NULL REFERENCES DIM_TYPE_MVT_CAISSE(id_type_mvt) ON DELETE NO ACTION,
        id_sens_ecriture   INT NULL REFERENCES DIM_SENS_ECRITURE(id_sens) ON DELETE NO ACTION,
        id_caisse          INT NULL REFERENCES DIM_CAISSE(id_caisse) ON DELETE NO ACTION,
        EC_Intitule        NVARCHAR(100) NULL,
        EC_Sens            SMALLINT NULL,
        EC_Montant         NUMERIC(18,4) NULL,
        EC_TauxTVA         NUMERIC(18,4) NULL,
        EC_MontantTVA      NUMERIC(18,4) NULL,
        EC_MontantHT       NUMERIC(18,4) NULL,
        MC_Montant         NUMERIC(18,4) NULL,
        MC_Libelle         NVARCHAR(100) NULL,
        DL_CMUP            NUMERIC(18,4) NULL,
        CG_Num             INT NULL,
        TA_Taux01          NUMERIC(18,4) NULL,
        RT_Base01          NUMERIC(18,4) NULL,
        RT_Montant01       NUMERIC(18,4) NULL,
        AS_MontSto         NUMERIC(18,4) NULL,
        AS_QteSto          NUMERIC(18,4) NULL,
        AS_QteMini         NUMERIC(18,4) NULL,
        AS_QteRes          NUMERIC(18,4) NULL,
        qte_disponible     NUMERIC(18,4) NULL,
        ratio_tension      NUMERIC(18,4) NULL,
        en_rupture         SMALLINT NULL,
        qte_vendue_365j    NUMERIC(18,4) NULL,
        dsi_jours          NUMERIC(18,4) NULL,
        MC_Debit           NUMERIC(18,4) NULL,
        MC_Credit          NUMERIC(18,4) NULL,
        MC_Cloture         SMALLINT NULL,
        CA_Solde           NUMERIC(18,4) NULL,
        CA_SoldeEspece     NUMERIC(18,4) NULL,
        CA_SoldeCheque     NUMERIC(18,4) NULL,
        EC_No              INT NULL,
        source_hash        BINARY(32) NULL,
        date_extraction    DATE NOT NULL
    )"""),

    # --- TABLE D'AUDIT ---
    ("ETL_AUDIT", """
    CREATE TABLE ETL_AUDIT (
        run_id           INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        run_date         DATETIME NOT NULL DEFAULT GETUTCDATE(),
        mode             VARCHAR(10) NOT NULL,
        table_name       VARCHAR(100) NOT NULL,
        rows_inserted    INT NOT NULL DEFAULT 0,
        rows_updated     INT NOT NULL DEFAULT 0,
        duration_seconds INT NOT NULL DEFAULT 0,
        status           VARCHAR(20) NOT NULL,
        error_msg        NVARCHAR(500) NULL
    )"""),
]

# ==========================================
# 2. DEFINITION DES VUES ET INDEXES
# ==========================================

VIEWS: list[tuple[str, str]] = [
    ("V_FAIT_ECRITURES_COMPTA", """
    CREATE VIEW [V_FAIT_ECRITURES_COMPTA] AS
    SELECT
        fe.id_ecriture,
        fe.id_date,
        fe.id_journal,
        fe.id_client,
        fe.id_fournisseur,
        fe.EC_Intitule,
        fe.EC_Montant,
        fe.EC_Sens,
        fe.id_sens_ecriture,
        fe.source_hash,
        fe.date_extraction
    FROM FAIT_ECRITURES fe
    JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
    WHERE tl.type_ligne = 1;
    """),

    ("V_FAIT_TVA", """
    CREATE VIEW [V_FAIT_TVA] AS
    SELECT
        fe.id_ecriture,
        fe.id_date,
        fe.id_type_tva,
        fe.id_client,
        fe.id_fournisseur,
        fe.EC_TauxTVA,
        fe.EC_MontantTVA,
        fe.EC_MontantHT,
        fe.source_hash,
        fe.date_extraction
    FROM FAIT_ECRITURES fe
    JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
    WHERE tl.type_ligne = 2;
    """),

    ("V_FAIT_MVT_CAISSE", """
    CREATE VIEW [V_FAIT_MVT_CAISSE] AS
    SELECT
        fe.id_ecriture,
        fe.id_date,
        fe.id_caisse,
        fe.id_banque,
        fe.id_type_mvt_caisse,
        fe.MC_Montant,
        fe.MC_Libelle,
        fe.source_hash,
        fe.date_extraction
    FROM FAIT_ECRITURES fe
    JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
    WHERE tl.type_ligne = 3;
    """),

    ("V_FAIT_STOCK_SNAPSHOT", """
    CREATE VIEW [V_FAIT_STOCK_SNAPSHOT] AS
    SELECT
        fe.id_ecriture,
        fe.id_date,
        fe.id_article,
        fe.id_depot,
        fe.AS_QteSto,
        fe.AS_QteMini,
        fe.AS_QteRes,
        fe.AS_MontSto,
        fe.DL_CMUP,
        fe.en_rupture,
        fe.ratio_tension,
        fe.dsi_jours,
        fe.source_hash,
        fe.date_extraction
    FROM FAIT_ECRITURES fe
    JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
    WHERE tl.type_ligne = 4;
    """),
]

INDEXES: list[tuple[str, str]] = [
    ("idx_flv_date", "FAIT_LIGNES_VENTE(id_date)"),
    ("idx_flv_client", "FAIT_LIGNES_VENTE(id_client)"),
    ("idx_flv_article", "FAIT_LIGNES_VENTE(id_article)"),
    ("idx_flv_domaine", "FAIT_LIGNES_VENTE(id_domaine)"),
    ("idx_fr_fournisseur", "FAIT_REGLEMENTS(id_fournisseur)"),
    ("idx_fr_date_pai", "FAIT_REGLEMENTS(id_date_paiement)"),
    ("idx_fr_date_ech", "FAIT_REGLEMENTS(id_date_echeance)"),
]

# Order de suppression strict base sur les cles etrangeres
TABLES_DROP_ORDER: list[str] = [
    # 1. Tables de faits (qui pointent vers les dimensions parentes)
    "FAIT_ECRITURES",
    "FAIT_REGLEMENTS",
    "FAIT_LIGNES_VENTE",
    # 2. Dimensions avec cles etrangeres references
    "DIM_CAISSE",
    "DIM_ARTICLE",
    "DIM_CLIENT",
    # 3. Dimensions parentes et tables indépendantes
    "DIM_DEPOT",
    "DIM_FAMILLE",
    "DIM_FOURNISSEUR",
    "DIM_JOURNAL",
    "DIM_COLLABORATEUR",
    "DIM_SEGMENT",
    "DIM_BANQUE",
    "DIM_TYPE_MVT_CAISSE",
    "DIM_TYPE_TVA",
    "DIM_SENS_ECRITURE",
    "DIM_TYPE_LIGNE",
    "DIM_ETAT_DOCREGL",
    "DIM_ETAT_REGLEMENT",
    "DIM_MODE_REGLEMENT",
    "DIM_TYPE_DOC",
    "DIM_DOMAINE",
    "DIM_DATE",
    "ETL_AUDIT"
]

# ==========================================
# 3. FONCTIONS UTILITAIRES
# ==========================================

def table_exists(table_name: str) -> bool:
    """Verifie si une table existe dans la base de donnees."""
    query = """
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_NAME = :tbl AND TABLE_TYPE = 'BASE TABLE'
    """
    with DW_ENGINE.connect() as conn:
        result = conn.execute(text(query), {"tbl": table_name}).scalar()
    return result > 0


def disable_all_fk(conn) -> None:
    """Desactive temporairement les contraintes de cle etrangere pour le chargement initial."""
    for table_name, _ in ALL_DDL:
        try:
            conn.execute(text(f"ALTER TABLE [{table_name}] NOCHECK CONSTRAINT ALL"))
        except Exception:
            pass


def enable_all_fk(conn) -> None:
    """Reactive les contraintes de cle etrangere apres le chargement."""
    for table_name, _ in ALL_DDL:
        try:
            conn.execute(text(f"ALTER TABLE [{table_name}] WITH CHECK CHECK CONSTRAINT ALL"))
        except Exception as exc:
            logger.warning(f"FK check [{table_name}]: {exc}")


def _drop_all_tables() -> None:
    """Supprime proprement les vues et toutes les tables dans l'ordre strict des dependances."""
    logger.warning("DDL : Suppression de toutes les vues et tables...")
    
    with DW_ENGINE.begin() as conn:
        # 1. Supprimer les vues d'abord
        for view_name, _ in VIEWS:
            try:
                conn.execute(text(f"IF OBJECT_ID('{view_name}', 'V') IS NOT NULL DROP VIEW [{view_name}]"))
                logger.info(f"  [DROP VIEW] {view_name}")
            except Exception as exc:
                logger.warning(f"  [DROP VIEW WARN] {view_name}: {exc}")

        # 2. Supprimer les tables dans l'ordre strict des dependances (pour eviter les erreurs FK)
        for table_name in TABLES_DROP_ORDER:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS [{table_name}]"))
                logger.info(f"  [DROP] {table_name}")
            except Exception as exc:
                logger.warning(f"  [DROP WARN] {table_name}: {exc}")


def create_all_tables(drop_existing: bool = False) -> None:
    """Cree toutes les tables du schema de l'entrepot de donnees."""
    logger.info("=== DDL : debut creation schema DW ===")

    if drop_existing:
        _drop_all_tables()

    with DW_ENGINE.begin() as conn:
        for table_name, ddl_sql in ALL_DDL:
            if not drop_existing and table_exists(table_name):
                logger.info(f"  [SKIP] {table_name} - deja existante")
                continue
            try:
                conn.execute(text(ddl_sql.strip()))
                logger.info(f"  [OK]   {table_name} creee")
            except Exception as exc:
                logger.error(f"  [ERR]  {table_name} : {exc}")
                raise

    logger.info("=== DDL : schema DW cree avec succes ===")


def apply_schema_migrations() -> None:
    """Applique les vues et indexes de performance sur la base de donnees."""
    logger.info("=== DDL : application des migrations (vues & indexes) ===")
    
    with DW_ENGINE.begin() as conn:
        # 1. Creation/Remplacement des Vues
        for view_name, create_sql in VIEWS:
            try:
                conn.execute(text(f"IF OBJECT_ID('{view_name}', 'V') IS NOT NULL DROP VIEW [{view_name}]"))
                conn.execute(text(create_sql.strip()))
                logger.info(f"  [VIEW OK]   {view_name} creee")
            except Exception as exc:
                logger.warning(f"  [VIEW WARN] {view_name}: {exc}")

        # 2. Creation des indexes de performance
        for idx_name, columns in INDEXES:
            try:
                tbl = columns.split('(')[0]
                check_sql = f"""
                    IF NOT EXISTS (
                        SELECT * FROM sys.indexes 
                        WHERE name = '{idx_name}' AND object_id = OBJECT_ID('{tbl}')
                    )
                    BEGIN
                        CREATE INDEX {idx_name} ON {columns};
                    END
                """
                conn.execute(text(check_sql))
                logger.info(f"  [INDEX OK]  {idx_name} sur {columns}")
            except Exception as exc:
                logger.warning(f"  [INDEX WARN] {idx_name}: {exc}")

    logger.info("=== DDL : migrations terminees ===")


if __name__ == "__main__":
    import sys

    # Si l'argument --drop est passe, on recree la base proprement de zero
    drop = "--drop" in sys.argv
    create_all_tables(drop_existing=drop)
    apply_schema_migrations()
