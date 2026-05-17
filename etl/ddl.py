from __future__ import annotations

from sqlalchemy import text

from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)


_DDL_GROUPE_1: list[tuple[str, str]] = [
    ("REF_SEGMENTS_MAPPING", """
CREATE TABLE REF_SEGMENTS_MAPPING (
    cbIndice         SMALLINT NOT NULL PRIMARY KEY,
    libelle_segment  NVARCHAR(100) NOT NULL
)"""),

    ("REF_TYPES_MVT_CAISSE_MAPPING", """
CREATE TABLE REF_TYPES_MVT_CAISSE_MAPPING (
    MC_TypeMvt       SMALLINT NOT NULL PRIMARY KEY,
    libelle_type_mvt NVARCHAR(100) NOT NULL
)"""),

    ("REF_MODES_REGLEMENT_MAPPING", """
CREATE TABLE REF_MODES_REGLEMENT_MAPPING (
    RT_Mode          SMALLINT NOT NULL PRIMARY KEY,
    libelle_mode_reg NVARCHAR(100) NOT NULL
)"""),

    ("REF_ETATS_REGLEMENT_MAPPING", """
CREATE TABLE REF_ETATS_REGLEMENT_MAPPING (
    RT_Etat          SMALLINT NOT NULL PRIMARY KEY,
    libelle_etat_reg NVARCHAR(100) NOT NULL
)"""),

    ("REF_ETATS_DOCREGL_MAPPING", """
CREATE TABLE REF_ETATS_DOCREGL_MAPPING (
    DR_Regle         SMALLINT NOT NULL PRIMARY KEY,
    libelle_etat_docregl NVARCHAR(100) NOT NULL
)"""),

    ("REF_TYPES_LIGNE_MAPPING", """
CREATE TABLE REF_TYPES_LIGNE_MAPPING (
    type_ligne       SMALLINT NOT NULL PRIMARY KEY,
    libelle_type_ligne NVARCHAR(100) NOT NULL
)"""),

    ("REF_SENS_ECRITURE_MAPPING", """
CREATE TABLE REF_SENS_ECRITURE_MAPPING (
    EC_Sens          SMALLINT NOT NULL PRIMARY KEY,
    libelle_sens     NVARCHAR(100) NOT NULL
)"""),

    ("REF_TYPES_TVA_MAPPING", """
CREATE TABLE REF_TYPES_TVA_MAPPING (
    type_tva         SMALLINT NOT NULL PRIMARY KEY,
    libelle_type_tva NVARCHAR(100) NOT NULL
)"""),

    ("REF_TYPES_DOC_MAPPING", """
CREATE TABLE REF_TYPES_DOC_MAPPING (
    DO_Type          SMALLINT NOT NULL PRIMARY KEY,
    libelle_type_doc NVARCHAR(100) NOT NULL
)"""),

    ("REF_DOMAINES_MAPPING", """
CREATE TABLE REF_DOMAINES_MAPPING (
    DO_Domaine       SMALLINT NOT NULL PRIMARY KEY,
    libelle_domaine  NVARCHAR(100) NOT NULL
)"""),

    ("ETL_LOOKUP_CONFIG", """
CREATE TABLE ETL_LOOKUP_CONFIG (
    table_name       VARCHAR(100) NOT NULL PRIMARY KEY,
    natural_col      VARCHAR(100) NOT NULL,
    surrogate_col    VARCHAR(100) NOT NULL
)"""),

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
]





_DDL_GROUPE_2: list[tuple[str, str]] = [






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
]





_DDL_GROUPE_3: list[tuple[str, str]] = [

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
]





_DDL_GROUPE_4: list[tuple[str, str]] = [

    ("DIM_CLIENT", """
CREATE TABLE DIM_CLIENT (
    id_client               INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CT_Num_code             BIGINT NOT NULL UNIQUE,
    CT_Sommeil              SMALLINT NOT NULL DEFAULT 0,
    id_segment              INT NULL REFERENCES DIM_SEGMENT(id_segment)
                                ON DELETE NO ACTION,
    id_collab               INT NULL REFERENCES DIM_COLLABORATEUR(id_collab)
                                ON DELETE NO ACTION,
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
]





_DDL_GROUPE_5: list[tuple[str, str]] = [

    ("DIM_ARTICLE", """
CREATE TABLE DIM_ARTICLE (
    id_article         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    AR_Ref_code        BIGINT NOT NULL UNIQUE,
    id_famille         INT NULL REFERENCES DIM_FAMILLE(id_famille)
                           ON DELETE NO ACTION,
    id_fournisseur     INT NULL REFERENCES DIM_FOURNISSEUR(id_fournisseur)
                           ON DELETE NO ACTION,
    FA_Intitule        NVARCHAR(100) NULL,
    AR_Sommeil         SMALLINT NOT NULL DEFAULT 0,
    AR_PrixAch         NUMERIC(18,4) NULL,
    AR_SuiviStock      SMALLINT NOT NULL DEFAULT 0,
    row_hash           BINARY(32) NULL
)"""),
]





_DDL_GROUPE_6: list[tuple[str, str]] = [

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
    id_journal         INT NULL REFERENCES DIM_JOURNAL(id_journal)
                           ON DELETE NO ACTION,
    row_hash           BINARY(32) NULL
)"""),
]





_DDL_GROUPE_7: list[tuple[str, str]] = [

    ("FAIT_LIGNES_VENTE", """
CREATE TABLE FAIT_LIGNES_VENTE (
    id_ligne           INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    id_date            INT NULL REFERENCES DIM_DATE(id_date)
                           ON DELETE NO ACTION,
    id_type_doc        INT NULL REFERENCES DIM_TYPE_DOC(id_type_doc)
                           ON DELETE NO ACTION,
    id_domaine         INT NULL REFERENCES DIM_DOMAINE(id_domaine)
                           ON DELETE NO ACTION,
    id_client          INT NULL REFERENCES DIM_CLIENT(id_client)
                           ON DELETE NO ACTION,
    id_article         INT NULL REFERENCES DIM_ARTICLE(id_article)
                           ON DELETE NO ACTION,
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
    id_date_paiement   INT NULL REFERENCES DIM_DATE(id_date)
                           ON DELETE NO ACTION,
    id_date_echeance   INT NULL REFERENCES DIM_DATE(id_date)
                           ON DELETE NO ACTION,
    id_client          INT NULL REFERENCES DIM_CLIENT(id_client)
                           ON DELETE NO ACTION,
    id_fournisseur     INT NULL REFERENCES DIM_FOURNISSEUR(id_fournisseur)
                           ON DELETE NO ACTION,
    id_banque          INT NULL REFERENCES DIM_BANQUE(id_banque)
                           ON DELETE NO ACTION,
    id_mode_reg        INT NULL REFERENCES DIM_MODE_REGLEMENT(id_mode_reg)
                           ON DELETE NO ACTION,
    id_etat_reg        INT NULL REFERENCES DIM_ETAT_REGLEMENT(id_etat_reg)
                           ON DELETE NO ACTION,
    id_etat_docregl    INT NULL REFERENCES DIM_ETAT_DOCREGL(id_etat_docregl)
                           ON DELETE NO ACTION,
    id_type_doc        INT NULL REFERENCES DIM_TYPE_DOC(id_type_doc)
                           ON DELETE NO ACTION,
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
    id_date            INT NULL REFERENCES DIM_DATE(id_date)
                           ON DELETE NO ACTION,
    id_type_ligne      INT NULL REFERENCES DIM_TYPE_LIGNE(id_type_ligne)
                           ON DELETE NO ACTION,
    id_journal         INT NULL REFERENCES DIM_JOURNAL(id_journal)
                           ON DELETE NO ACTION,
    id_banque          INT NULL REFERENCES DIM_BANQUE(id_banque)
                           ON DELETE NO ACTION,
    id_client          INT NULL REFERENCES DIM_CLIENT(id_client)
                           ON DELETE NO ACTION,
    id_fournisseur     INT NULL REFERENCES DIM_FOURNISSEUR(id_fournisseur)
                           ON DELETE NO ACTION,
    id_article         INT NULL REFERENCES DIM_ARTICLE(id_article)
                           ON DELETE NO ACTION,
    id_depot           INT NULL REFERENCES DIM_DEPOT(id_depot)
                           ON DELETE NO ACTION,
    id_type_tva        INT NULL REFERENCES DIM_TYPE_TVA(id_type_tva)
                           ON DELETE NO ACTION,
    id_type_mvt_caisse INT NULL REFERENCES DIM_TYPE_MVT_CAISSE(id_type_mvt)
                           ON DELETE NO ACTION,
    id_sens_ecriture   INT NULL REFERENCES DIM_SENS_ECRITURE(id_sens)
                           ON DELETE NO ACTION,
    id_caisse          INT NULL REFERENCES DIM_CAISSE(id_caisse)
                           ON DELETE NO ACTION,
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
]





_DDL_GROUPE_8: list[tuple[str, str]] = [

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



ALL_DDL: list[tuple[str, str]] = (
    _DDL_GROUPE_1
    + _DDL_GROUPE_2
    + _DDL_GROUPE_3
    + _DDL_GROUPE_4
    + _DDL_GROUPE_5
    + _DDL_GROUPE_6
    + _DDL_GROUPE_7
    + _DDL_GROUPE_8
)





_MIGRATIONS: list[tuple[str, str]] = []

_INDEX_MIGRATIONS: list[tuple[str, str]] = []





_DROP_IF_EXISTS = (
    "IF OBJECT_ID(N'[dbo].[{name}]', N'U') IS NOT NULL "
    "DROP TABLE [{name}]"
)


def table_exists(table_name: str) -> bool:
    with DW_ENGINE.connect() as conn:
        result = conn.execute(
            text(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_NAME = :tbl AND TABLE_TYPE = 'BASE TABLE'"
            ),
            {"tbl": table_name},
        ).scalar()
    return result > 0


def create_all_tables(drop_existing: bool = False) -> None:
    logger.info("=== DDL : début création schéma DW ===")

    if drop_existing:
        _drop_all_tables()

    with DW_ENGINE.begin() as conn:
        for table_name, ddl_sql in ALL_DDL:
            if not drop_existing and table_exists(table_name):
                logger.info(f"  [SKIP] {table_name} — déjà existante")
                continue
            try:
                conn.execute(text(ddl_sql.strip()))
                logger.info(f"  [OK]   {table_name} créée")
            except Exception as exc:
                logger.error(f"  [ERR]  {table_name} : {exc}")
                raise

    logger.info("=== DDL : schéma DW créé avec succès ===")



# ── KPI18 / RFM column migrations ────────────────────────────────────────────
# Previously managed in pipeline.py; moved here so all DDL changes are in one
# place and version-controlled alongside the table definitions.
_KPI18_MIGRATIONS: list[tuple[str, str]] = []

_BIGINT_MIGRATIONS: list[tuple[str, str]] = []

# ── Semantic views on FAIT_ECRITURES ─────────────────────────────────────────
# The constellation schema keeps FAIT_ECRITURES as one physical table
# (grain controlled by type_ligne). These views expose each semantic fact
# domain separately so analysts and professors can query them naturally in SSMS.
_VIEW_MIGRATIONS: list[tuple[str, str]] = [
    (
        "V_FAIT_ECRITURES_COMPTA",
        """
IF OBJECT_ID('V_FAIT_ECRITURES_COMPTA', 'V') IS NOT NULL
    DROP VIEW [V_FAIT_ECRITURES_COMPTA];
""",
    ),
    (
        "V_FAIT_ECRITURES_COMPTA (CREATE)",
        """
CREATE VIEW [V_FAIT_ECRITURES_COMPTA] AS
-- Écritures comptables pures (type_ligne = 1).
-- Chaque ligne correspond à une écriture dans un journal Sage
-- avec son sens (débit/crédit), le montant HT et le compte général.
SELECT
    fe.id_ecriture,
    fe.id_date,
    fe.id_journal,
    fe.id_client,
    fe.id_fournisseur,
    fe.DO_Piece_hash,
    fe.EC_Intitule,
    fe.EC_Montant,
    fe.EC_Sens,
    fe.id_sens_ecriture,
    fe.source_hash,
    fe.date_extraction
FROM FAIT_ECRITURES fe
JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
WHERE tl.type_ligne = 1;
""",
    ),
    (
        "V_FAIT_TVA",
        """
IF OBJECT_ID('V_FAIT_TVA', 'V') IS NOT NULL
    DROP VIEW [V_FAIT_TVA];
""",
    ),
    (
        "V_FAIT_TVA (CREATE)",
        """
CREATE VIEW [V_FAIT_TVA] AS
-- Lignes de TVA (type_ligne = 2).
-- Permet de calculer le taux de TVA effectif, la TVA collectée
-- et la TVA déductible séparément pour les déclarations fiscales.
SELECT
    fe.id_ecriture,
    fe.id_date,
    fe.id_type_tva,
    fe.id_client,
    fe.id_fournisseur,
    fe.DO_Piece_hash,
    fe.EC_TauxTVA,
    fe.EC_MontantTVA,
    fe.EC_MontantHT,
    fe.source_hash,
    fe.date_extraction
FROM FAIT_ECRITURES fe
JOIN DIM_TYPE_LIGNE tl ON tl.id_type_ligne = fe.id_type_ligne
WHERE tl.type_ligne = 2;
""",
    ),
    (
        "V_FAIT_MVT_CAISSE",
        """
IF OBJECT_ID('V_FAIT_MVT_CAISSE', 'V') IS NOT NULL
    DROP VIEW [V_FAIT_MVT_CAISSE];
""",
    ),
    (
        "V_FAIT_MVT_CAISSE (CREATE)",
        """
CREATE VIEW [V_FAIT_MVT_CAISSE] AS
-- Mouvements de caisse et bancaires (type_ligne = 3).
-- Chaque ligne est un mouvement physique d'espèces ou de chèque
-- dans une caisse ou un compte bancaire Sage.
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
""",
    ),
    (
        "V_FAIT_STOCK_SNAPSHOT",
        """
IF OBJECT_ID('V_FAIT_STOCK_SNAPSHOT', 'V') IS NOT NULL
    DROP VIEW [V_FAIT_STOCK_SNAPSHOT];
""",
    ),
    (
        "V_FAIT_STOCK_SNAPSHOT (CREATE)",
        """
CREATE VIEW [V_FAIT_STOCK_SNAPSHOT] AS
-- Snapshot de stock par article et dépôt (type_ligne = 4).
-- Une ligne par article : stock physique, stock minimum, valeur CMUP,
-- indicateurs de tension et de rupture calculés lors de l'ETL.
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
""",
    ),
    (
        "DIM_CLIENT.drop_rfm_cols",
        "IF COL_LENGTH('DIM_CLIENT','rfm_score') IS NOT NULL "
        "ALTER TABLE [DIM_CLIENT] DROP COLUMN rfm_score, rfm_recence_jours, rfm_frequence, rfm_montant_12m",
    ),
    (
        "FAIT_ECRITURES.drop_alerte_tension",
        "IF COL_LENGTH('FAIT_ECRITURES','alerte_tension') IS NOT NULL "
        "ALTER TABLE [FAIT_ECRITURES] DROP COLUMN alerte_tension",
    ),
    (
        "FAIT_ECRITURES.drop_do_piece_hash",
        "IF COL_LENGTH('FAIT_ECRITURES','DO_Piece_hash') IS NOT NULL "
        "ALTER TABLE [FAIT_ECRITURES] DROP COLUMN DO_Piece_hash",
    ),
]

# ── REF_GOUVERNORAT_MAPPING reference table ───────────────────────────────────
# Replaces the 400-line Python dict _normalize_gouvernorat() in pipeline.py.
# Maintained directly in SSMS by the analyst — no Python code change needed
# to add or correct a gouvernorat mapping.
_REF_GOUVERNORAT_SQL = """
IF OBJECT_ID('REF_GOUVERNORAT_MAPPING', 'U') IS NULL
BEGIN
    CREATE TABLE REF_GOUVERNORAT_MAPPING (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        CT_CodeRegion   NVARCHAR(100) NOT NULL,
        gouvernorat     NVARCHAR(50)  NOT NULL,
        CONSTRAINT UQ_REF_GOUVERNORAT_CodeRegion UNIQUE (CT_CodeRegion)
    );

    INSERT INTO REF_GOUVERNORAT_MAPPING (CT_CodeRegion, gouvernorat) VALUES
    ('TUNIS','Tunis'),('MONTPLAISIR','Tunis'),('LE BARDO','Tunis'),
    ('BARDO','Tunis'),('EZZAHROUNI','Tunis'),('OMRANE','Tunis'),
    ('AGBA','Tunis'),('ETTADHAMEN','Tunis'),('MARCHE CENTRAL','Tunis'),
    ('MALASINE','Tunis'),('LAKANIA','Tunis'),
    ('ARIANA','Ariana'),('RAOUED','Ariana'),('CITE ENNASR','Ariana'),
    ('KALAAT LANDLOUS','Ariana'),('LA SOUKRA','Ariana'),
    ('BEN AROUS','Ben Arous'),('EL MOUROUJ','Ben Arous'),
    ('RADES','Ben Arous'),('FOUCHANA','Ben Arous'),
    ('MANOUBA','Manouba'),('OUED ELLIL','Manouba'),
    ('BIZERTE','Bizerte'),('MENZEL BOURGUIBA','Bizerte'),
    ('NABEUL','Nabeul'),('HAMMAMET','Nabeul'),('KELIBIA','Nabeul'),
    ('SOUSSE','Sousse'),('MSAKEN','Sousse'),('AKOUDA','Sousse'),
    ('MONASTIR','Monastir'),('SKANES','Monastir'),('KSAR HELLAL','Monastir'),
    ('MAHDIA','Mahdia'),('EL JEM','Mahdia'),
    ('KAIROUAN','Kairouan'),('SBIKHA','Kairouan'),
    ('SFAX','Sfax'),('SAKIET EZZIT','Sfax'),('SAKIET EDDAIER','Sfax'),
    ('GABES','Gabès'),('EL HAMMA','Gabès'),
    ('MEDENINE','Médenine'),('ZARZIS','Médenine'),('BEN GARDANE','Médenine'),
    ('TATAOUINE','Tataouine'),
    ('GAFSA','Gafsa'),('METLAOUI','Gafsa'),
    ('KASSERINE','Kasserine'),('SBEITLA','Kasserine'),
    ('SIDI BOUZID','Sidi Bouzid'),
    ('BEJA','Béja'),('TESTOUR','Béja'),
    ('JENDOUBA','Jendouba'),('AIN DRAHAM','Jendouba'),
    ('KEF','Le Kef'),('DAHMANI','Le Kef'),
    ('SILIANA','Siliana'),('MAKTHAR','Siliana'),
    ('ZAGHOUAN','Zaghouan'),('ENFIDHA','Zaghouan'),
    ('TOZEUR','Tozeur'),('NEFTA','Tozeur'),
    ('KEBILI','Kébili'),
    ('hors zone','Autre'),('HORS ZONE','Autre'),('DIVERS','Autre');
END
"""


_REF_DICTIONARY_SQL = """
    -- 1. Populate REF_SEGMENTS_MAPPING
    IF NOT EXISTS (SELECT 1 FROM REF_SEGMENTS_MAPPING)
    BEGIN
        INSERT INTO REF_SEGMENTS_MAPPING (cbIndice, libelle_segment) VALUES
        (1, 'DÉTAILLANTS'), (2, 'GROSSISTES'), (3, 'HORECA'), (4, 'SEMI-GROS'), (5, 'DISTRIBUTEUR')
    END

    -- 2. Populate REF_TYPES_MVT_CAISSE_MAPPING
    IF NOT EXISTS (SELECT 1 FROM REF_TYPES_MVT_CAISSE_MAPPING)
    BEGIN
        INSERT INTO REF_TYPES_MVT_CAISSE_MAPPING (MC_TypeMvt, libelle_type_mvt) VALUES
        (0, 'Entrée'), (1, 'Sortie'), (2, 'Remise en banque chèques'), 
        (3, 'Remise en banque espèces'), (4, 'Bordereau de carte bancaire'), 
        (5, 'Bon de caisse'), (6, 'Escompte'), (7, 'Règlement fournisseur')
    END

    -- 3. Populate ETL_LOOKUP_CONFIG
    IF NOT EXISTS (SELECT 1 FROM ETL_LOOKUP_CONFIG)
    BEGIN
        INSERT INTO ETL_LOOKUP_CONFIG (table_name, natural_col, surrogate_col) VALUES
        ('DIM_DATE', 'date_val', 'id_date'),
        ('DIM_DOMAINE', 'DO_Domaine', 'id_domaine'),
        ('DIM_TYPE_DOC', 'DO_Type', 'id_type_doc'),
        ('DIM_MODE_REGLEMENT', 'RT_Mode', 'id_mode_reg'),
        ('DIM_ETAT_REGLEMENT', 'RT_Etat', 'id_etat_reg'),
        ('DIM_ETAT_DOCREGL', 'DR_Regle', 'id_etat_docregl'),
        ('DIM_TYPE_LIGNE', 'type_ligne', 'id_type_ligne'),
        ('DIM_SENS_ECRITURE', 'EC_Sens', 'id_sens_ecriture'),
        ('DIM_TYPE_TVA', 'type_tva', 'id_type_tva'),
        ('DIM_TYPE_MVT_CAISSE', 'MC_TypeMvt', 'id_type_mvt_caisse'),
        ('DIM_SEGMENT', 'cbIndice_code', 'id_segment'),
        ('DIM_COLLABORATEUR', 'CO_No', 'id_collab'),
        ('DIM_FAMILLE', 'FA_CodeFamille_code', 'id_famille'),
        ('DIM_CLIENT', 'CT_Num_code', 'id_client'),
        ('DIM_FOURNISSEUR', 'CT_Num_code', 'id_fournisseur'),
        ('DIM_JOURNAL', 'JO_Num_code', 'id_journal'),
        ('DIM_BANQUE', 'EB_Abrege_code', 'id_banque'),
        ('DIM_ARTICLE', 'AR_Ref_code', 'id_article'),
        ('DIM_DEPOT', 'DE_No', 'id_depot'),
        ('DIM_CAISSE', 'CA_Numero_code', 'id_caisse')
    END

    -- 4. Populate REF_MODES_REGLEMENT_MAPPING
    IF NOT EXISTS (SELECT 1 FROM REF_MODES_REGLEMENT_MAPPING)
    BEGIN
        INSERT INTO REF_MODES_REGLEMENT_MAPPING (RT_Mode, libelle_mode_reg) VALUES
        (1, 'Espèces'), (2, 'Chèque'), (3, 'Virement'), (4, 'Traite'), 
        (5, 'LCR'), (7, 'Carte'), (8, 'Autre')
    END

    -- 5. Populate REF_ETATS_REGLEMENT_MAPPING
    IF NOT EXISTS (SELECT 1 FROM REF_ETATS_REGLEMENT_MAPPING)
    BEGIN
        INSERT INTO REF_ETATS_REGLEMENT_MAPPING (RT_Etat, libelle_etat_reg) VALUES
        (0, 'En cours'), (1, 'Soldé'), (2, 'Payé')
    END

    -- 6. Populate REF_ETATS_DOCREGL_MAPPING
    IF NOT EXISTS (SELECT 1 FROM REF_ETATS_DOCREGL_MAPPING)
    BEGIN
        INSERT INTO REF_ETATS_DOCREGL_MAPPING (DR_Regle, libelle_etat_docregl) VALUES
        (0, 'Non réglé'), (1, 'Réglé')
    END

    -- 7. Populate REF_TYPES_LIGNE_MAPPING
    IF NOT EXISTS (SELECT 1 FROM REF_TYPES_LIGNE_MAPPING)
    BEGIN
        INSERT INTO REF_TYPES_LIGNE_MAPPING (type_ligne, libelle_type_ligne) VALUES
        (1, 'Ecriture comptable'), (2, 'TVA'), (3, 'Mouvement caisse'), (4, 'Stock snapshot')
    END

    -- 8. Populate REF_SENS_ECRITURE_MAPPING
    IF NOT EXISTS (SELECT 1 FROM REF_SENS_ECRITURE_MAPPING)
    BEGIN
        INSERT INTO REF_SENS_ECRITURE_MAPPING (EC_Sens, libelle_sens) VALUES
        (0, 'Débit'), (1, 'Crédit')
    END

    -- 9. Populate REF_TYPES_TVA_MAPPING
    IF NOT EXISTS (SELECT 1 FROM REF_TYPES_TVA_MAPPING)
    BEGIN
        INSERT INTO REF_TYPES_TVA_MAPPING (type_tva, libelle_type_tva) VALUES
        (1, 'TVA collectée'), (2, 'TVA déductible')
    END

    -- 10. Populate REF_TYPES_DOC_MAPPING
    IF NOT EXISTS (SELECT 1 FROM REF_TYPES_DOC_MAPPING)
    BEGIN
        INSERT INTO REF_TYPES_DOC_MAPPING (DO_Type, libelle_type_doc) VALUES
        (1, 'Devis'), (2, 'Bon de commande'), (3, 'Bon de livraison'), (4, 'Bon de retour'),
        (5, 'Bon d''avoir HT'), (6, 'Facture'), (7, 'Avoir'), (11, 'Préparation de commande'),
        (12, 'Bon de commande fournisseur'), (13, 'Bon de réception'), (14, 'Bon de retour fournisseur'),
        (15, 'Bon d''avoir fournisseur HT'), (16, 'Facture fournisseur'), (17, 'Avoir fournisseur')
    END

    -- 11. Populate REF_DOMAINES_MAPPING
    IF NOT EXISTS (SELECT 1 FROM REF_DOMAINES_MAPPING)
    BEGIN
        INSERT INTO REF_DOMAINES_MAPPING (DO_Domaine, libelle_domaine) VALUES
        (0, 'Vente'), (1, 'Achat'), (2, 'Stock'), (3, 'Interne')
    END
"""

def _apply_schema_migrations(conn) -> None:
    # 1. Standard column migrations (ADD COLUMN, ALTER COLUMN type changes)
    for label, sql in _MIGRATIONS:
        try:
            conn.execute(text(sql))
            logger.info(f"  [MIGRATION OK]   {label}")
        except Exception as exc:
            logger.warning(f"  [MIGRATION WARN] {label}: {exc}")

    # 2. Index migrations
    for label, sql in _INDEX_MIGRATIONS:
        try:
            conn.execute(text(sql))
            logger.info(f"  [INDEX OK]       {label}")
        except Exception as exc:
            logger.warning(f"  [INDEX WARN]     {label}: {exc}")

    # 3. KPI18 / RFM column additions (previously scattered in pipeline.py)
    for label, sql in _KPI18_MIGRATIONS:
        try:
            conn.execute(text(sql))
            logger.info(f"  [KPI18 OK]       {label}")
        except Exception as exc:
            logger.warning(f"  [KPI18 WARN]     {label}: {exc}")

    # 4. BIGINT surrogate key upgrades (hash is now 8 bytes → values up to 2^63-1)
    for label, sql in _BIGINT_MIGRATIONS:
        try:
            conn.execute(text(sql))
            logger.info(f"  [BIGINT OK]      {label}")
        except Exception as exc:
            logger.warning(f"  [BIGINT WARN]    {label}: {exc}")

    # 5. Semantic views on FAIT_ECRITURES
    for label, sql in _VIEW_MIGRATIONS:
        try:
            conn.execute(text(sql.strip()))
            logger.info(f"  [VIEW OK]        {label}")
        except Exception as exc:
            logger.warning(f"  [VIEW WARN]      {label}: {exc}")

    # 6. REF_GOUVERNORAT_MAPPING reference table (replaces Python dict)
    try:
        conn.execute(text(_REF_GOUVERNORAT_SQL.strip()))
        logger.info("  [REF OK]         REF_GOUVERNORAT_MAPPING")
    except Exception as exc:
        logger.warning(f"  [REF WARN]       REF_GOUVERNORAT_MAPPING: {exc}")

    # 7. REF Data for segments, caisse and lookup config
    try:
        conn.execute(text(_REF_DICTIONARY_SQL.strip()))
        logger.info("  [REF OK]         REF_DICTIONARY_SQL (Segments, Caisse, Config)")
    except Exception as exc:
        logger.warning(f"  [REF WARN]       REF_DICTIONARY_SQL: {exc}")

    # 8. Performance Indexes for Fact Tables
    indexes = [
        ("idx_flv_date", "FAIT_LIGNES_VENTE(id_date)"),
        ("idx_flv_client", "FAIT_LIGNES_VENTE(id_client)"),
        ("idx_flv_article", "FAIT_LIGNES_VENTE(id_article)"),
        ("idx_flv_domaine", "FAIT_LIGNES_VENTE(id_domaine)"),
        ("idx_fr_fournisseur", "FAIT_REGLEMENTS(id_fournisseur)"),
        ("idx_fr_date_pai", "FAIT_REGLEMENTS(id_date_paiement)"),
        ("idx_fr_date_ech", "FAIT_REGLEMENTS(id_date_echeance)"),
    ]
    for idx_name, columns in indexes:
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
            logger.info(f"  [INDEX OK]       {idx_name} sur {columns}")
        except Exception as exc:
            logger.warning(f"  [INDEX WARN]     {idx_name}: {exc}")


def apply_schema_migrations() -> None:
    logger.info("=== DDL : application des migrations de schéma ===")
    with DW_ENGINE.begin() as conn:
        _apply_schema_migrations(conn)
    logger.info("=== DDL : migrations terminées ===")



def disable_all_fk(conn) -> None:
    for table_name, _ in ALL_DDL:
        try:
            conn.execute(
                text(f"ALTER TABLE [{table_name}] NOCHECK CONSTRAINT ALL")
            )
        except Exception:
            pass


def enable_all_fk(conn) -> None:
    for table_name, _ in ALL_DDL:
        try:
            conn.execute(
                text(
                    f"ALTER TABLE [{table_name}] "
                    "WITH CHECK CHECK CONSTRAINT ALL"
                )
            )
        except Exception as exc:
            logger.warning(f"FK check [{table_name}]: {exc}")


def _drop_all_tables() -> None:
    reversed_tables = [name for name, _ in reversed(ALL_DDL)]
    logger.warning("DDL : DROP ALL TABLES")

    with DW_ENGINE.begin() as conn:
        for table_name in reversed_tables:
            try:
                conn.execute(
                    text(
                        f"IF OBJECT_ID(N'[{table_name}]', N'U') IS NOT NULL "
                        f"ALTER TABLE [{table_name}] NOCHECK CONSTRAINT ALL"
                    )
                )
            except Exception:
                pass

        for table_name in reversed_tables:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS [{table_name}]"))
                logger.info(f"  [DROP] {table_name}")
            except Exception as exc:
                logger.warning(f"  [DROP WARN] {table_name}: {exc}")


if __name__ == "__main__":
    import sys

    drop = "--drop" in sys.argv
    create_all_tables(drop_existing=drop)
    apply_schema_migrations()
