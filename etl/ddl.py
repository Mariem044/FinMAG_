from __future__ import annotations

from sqlalchemy import text

from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)





_DDL_GROUPE_1: list[tuple[str, str]] = [

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
    EB_Abrege_code     INT NOT NULL UNIQUE,
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
    cbIndice_code      INT NOT NULL UNIQUE,
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
    JO_Num_code        INT NOT NULL UNIQUE,
    JO_Type            SMALLINT NULL,
    row_hash           BINARY(32) NULL
)"""),

    ("DIM_FOURNISSEUR", """
CREATE TABLE DIM_FOURNISSEUR (
    id_fournisseur     INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CT_Num_code        INT NOT NULL UNIQUE,
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
    FA_CodeFamille_code INT NOT NULL UNIQUE,
    FA_Intitule         NVARCHAR(100) NULL,
    niveau_0_code       INT NULL,
    niveau_1_code       INT NULL,
    niveau_2_code       INT NULL,
    row_hash            BINARY(32) NULL
)"""),
]





_DDL_GROUPE_4: list[tuple[str, str]] = [

    ("DIM_CLIENT", """
CREATE TABLE DIM_CLIENT (
    id_client               INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CT_Num_code             INT NOT NULL UNIQUE,
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
    rfm_recence_jours       INT NULL,
    rfm_frequence           INT NULL,
    rfm_montant_12m         NUMERIC(18,4) NULL,
    rfm_score               VARCHAR(20) NULL,
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
    AR_Ref_code        INT NOT NULL UNIQUE,
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
    CA_Numero_code     INT NOT NULL UNIQUE,
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
    DO_Piece_hash      INT NULL,
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
    id_type_mvt        INT NULL REFERENCES DIM_TYPE_MVT_CAISSE(id_type_mvt)
                           ON DELETE NO ACTION,
    id_sens            INT NULL REFERENCES DIM_SENS_ECRITURE(id_sens)
                           ON DELETE NO ACTION,
    id_caisse          INT NULL REFERENCES DIM_CAISSE(id_caisse)
                           ON DELETE NO ACTION,
    EC_Montant         NUMERIC(18,4) NULL,
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
    alerte_tension     SMALLINT NULL,
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





_MIGRATIONS: list[tuple[str, str]] = [


    (
        "DIM_DATE.trimestre",
        "IF COL_LENGTH('DIM_DATE','trimestre') IS NULL "
        "ALTER TABLE [DIM_DATE] ADD trimestre SMALLINT NOT NULL DEFAULT 0",
    ),
    (
        "DIM_DATE.semestre",
        "IF COL_LENGTH('DIM_DATE','semestre') IS NULL "
        "ALTER TABLE [DIM_DATE] ADD semestre SMALLINT NOT NULL DEFAULT 0",
    ),
    (
        "DIM_DATE.date_val",
        "IF COL_LENGTH('DIM_DATE','date_val') IS NULL AND "
        "COL_LENGTH('DIM_DATE','date_valeur') IS NOT NULL "
        "EXEC sp_rename 'DIM_DATE.date_valeur', 'date_val', 'COLUMN'",
    ),
    (
        "DIM_DATE.semaine",
        "IF COL_LENGTH('DIM_DATE','semaine') IS NULL AND "
        "COL_LENGTH('DIM_DATE','semaine_iso') IS NOT NULL "
        "EXEC sp_rename 'DIM_DATE.semaine_iso', 'semaine', 'COLUMN'",
    ),


    (
        "DIM_SEGMENT.cbIndice_code",
        "IF COL_LENGTH('DIM_SEGMENT','cbIndice_code') IS NULL "
        "ALTER TABLE [DIM_SEGMENT] ADD cbIndice_code INT NULL",
    ),
    (
        "DIM_SEGMENT.CT_PrixTTC",
        "IF COL_LENGTH('DIM_SEGMENT','CT_PrixTTC') IS NULL AND "
        "COL_LENGTH('DIM_SEGMENT','prix_ttc_flag') IS NOT NULL "
        "EXEC sp_rename 'DIM_SEGMENT.prix_ttc_flag', 'CT_PrixTTC', 'COLUMN'",
    ),
    (
        "DIM_SEGMENT.CT_PrixTTC_add",
        "IF COL_LENGTH('DIM_SEGMENT','CT_PrixTTC') IS NULL "
        "ALTER TABLE [DIM_SEGMENT] ADD CT_PrixTTC SMALLINT NOT NULL DEFAULT 0",
    ),
    (
        "DIM_SEGMENT.libelle_segment",
        "IF COL_LENGTH('DIM_SEGMENT','libelle_segment') IS NULL "
        "ALTER TABLE [DIM_SEGMENT] ADD libelle_segment NVARCHAR(100) NULL",
    ),
    (
        "DIM_SEGMENT.libelle_segment_widen",
        "IF EXISTS ("
        "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='DIM_SEGMENT' AND COLUMN_NAME='libelle_segment' "
        "AND CHARACTER_MAXIMUM_LENGTH < 100"
        ") "
        "ALTER TABLE [DIM_SEGMENT] ALTER COLUMN libelle_segment NVARCHAR(100) NULL",
    ),



    (
        "DIM_COLLABORATEUR.CO_Fonction_rename",
        "IF COL_LENGTH('DIM_COLLABORATEUR','CO_Fonction') IS NULL AND "
        "COL_LENGTH('DIM_COLLABORATEUR','CO_Fonction_code') IS NOT NULL "
        "EXEC sp_rename 'DIM_COLLABORATEUR.CO_Fonction_code', 'CO_Fonction', 'COLUMN'",
    ),
    (
        "DIM_COLLABORATEUR.CO_Fonction_add",
        "IF COL_LENGTH('DIM_COLLABORATEUR','CO_Fonction') IS NULL "
        "ALTER TABLE [DIM_COLLABORATEUR] ADD CO_Fonction INT NULL",
    ),
    (
        "DIM_COLLABORATEUR.CO_Fonction_widen_to_int",
        "IF EXISTS ("
        "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='DIM_COLLABORATEUR' AND COLUMN_NAME='CO_Fonction' "
        "AND DATA_TYPE='smallint'"
        ") "
        "ALTER TABLE [DIM_COLLABORATEUR] ALTER COLUMN CO_Fonction INT NULL",
    ),


    (
        "DIM_BANQUE.EB_Banque",
        "IF COL_LENGTH('DIM_BANQUE','EB_Banque') IS NULL AND "
        "COL_LENGTH('DIM_BANQUE','EB_Banque_code') IS NOT NULL "
        "EXEC sp_rename 'DIM_BANQUE.EB_Banque_code', 'EB_Banque', 'COLUMN'",
    ),
    (
        "DIM_BANQUE.EB_Banque_add",
        "IF COL_LENGTH('DIM_BANQUE','EB_Banque') IS NULL "
        "ALTER TABLE [DIM_BANQUE] ADD EB_Banque INT NULL",
    ),
    (
        "DIM_BANQUE.source",
        "IF COL_LENGTH('DIM_BANQUE','source') IS NULL "
        "ALTER TABLE [DIM_BANQUE] ADD source SMALLINT NOT NULL DEFAULT 1",
    ),

    (
        "DIM_FAMILLE.FA_Intitule",
        "IF COL_LENGTH('DIM_FAMILLE','FA_Intitule') IS NULL "
        "ALTER TABLE [DIM_FAMILLE] ADD FA_Intitule NVARCHAR(100) NULL",
    ),
    (
        "DIM_ARTICLE.FA_Intitule",
        "IF COL_LENGTH('DIM_ARTICLE','FA_Intitule') IS NULL "
        "ALTER TABLE [DIM_ARTICLE] ADD FA_Intitule NVARCHAR(100) NULL",
    ),


    (
        "DIM_CAISSE.id_journal",
        "IF COL_LENGTH('DIM_CAISSE','id_journal') IS NULL "
        "ALTER TABLE [DIM_CAISSE] ADD id_journal INT NULL "
        "REFERENCES DIM_JOURNAL(id_journal)",
    ),

    (
        "DIM_CAISSE.CA_Type_nullable",
        "IF EXISTS ("
        "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='DIM_CAISSE' AND COLUMN_NAME='CA_Type' "
        "AND IS_NULLABLE='NO'"
        ") "
        "ALTER TABLE [DIM_CAISSE] ALTER COLUMN CA_Type SMALLINT NULL",
    ),


    (
        "DIM_DOMAINE.DO_Domaine",
        "IF COL_LENGTH('DIM_DOMAINE','DO_Domaine') IS NULL AND "
        "COL_LENGTH('DIM_DOMAINE','code_domaine') IS NOT NULL "
        "EXEC sp_rename 'DIM_DOMAINE.code_domaine', 'DO_Domaine', 'COLUMN'",
    ),
    (
        "DIM_TYPE_DOC.DO_Type",
        "IF COL_LENGTH('DIM_TYPE_DOC','DO_Type') IS NULL AND "
        "COL_LENGTH('DIM_TYPE_DOC','code_type_doc') IS NOT NULL "
        "EXEC sp_rename 'DIM_TYPE_DOC.code_type_doc', 'DO_Type', 'COLUMN'",
    ),
    (
        "DIM_MODE_REGLEMENT.RT_Mode",
        "IF COL_LENGTH('DIM_MODE_REGLEMENT','RT_Mode') IS NULL AND "
        "COL_LENGTH('DIM_MODE_REGLEMENT','code_mode_reg') IS NOT NULL "
        "EXEC sp_rename 'DIM_MODE_REGLEMENT.code_mode_reg', 'RT_Mode', 'COLUMN'",
    ),
    (
        "DIM_ETAT_REGLEMENT.RT_Etat",
        "IF COL_LENGTH('DIM_ETAT_REGLEMENT','RT_Etat') IS NULL AND "
        "COL_LENGTH('DIM_ETAT_REGLEMENT','code_etat_reg') IS NOT NULL "
        "EXEC sp_rename 'DIM_ETAT_REGLEMENT.code_etat_reg', 'RT_Etat', 'COLUMN'",
    ),
    (
        "DIM_ETAT_DOCREGL.DR_Regle",
        "IF COL_LENGTH('DIM_ETAT_DOCREGL','DR_Regle') IS NULL AND "
        "COL_LENGTH('DIM_ETAT_DOCREGL','code_etat_docregl') IS NOT NULL "
        "EXEC sp_rename 'DIM_ETAT_DOCREGL.code_etat_docregl', 'DR_Regle', 'COLUMN'",
    ),
    (
        "DIM_TYPE_LIGNE.type_ligne",
        "IF COL_LENGTH('DIM_TYPE_LIGNE','type_ligne') IS NULL AND "
        "COL_LENGTH('DIM_TYPE_LIGNE','code_type_ligne') IS NOT NULL "
        "EXEC sp_rename 'DIM_TYPE_LIGNE.code_type_ligne', 'type_ligne', 'COLUMN'",
    ),
    (
        "DIM_SENS_ECRITURE.EC_Sens",
        "IF COL_LENGTH('DIM_SENS_ECRITURE','EC_Sens') IS NULL AND "
        "COL_LENGTH('DIM_SENS_ECRITURE','code_sens') IS NOT NULL "
        "EXEC sp_rename 'DIM_SENS_ECRITURE.code_sens', 'EC_Sens', 'COLUMN'",
    ),
    (
        "DIM_TYPE_TVA.type_tva",
        "IF COL_LENGTH('DIM_TYPE_TVA','type_tva') IS NULL AND "
        "COL_LENGTH('DIM_TYPE_TVA','code_type_tva') IS NOT NULL "
        "EXEC sp_rename 'DIM_TYPE_TVA.code_type_tva', 'type_tva', 'COLUMN'",
    ),
    (
        "DIM_TYPE_MVT_CAISSE.MC_TypeMvt",
        "IF COL_LENGTH('DIM_TYPE_MVT_CAISSE','MC_TypeMvt') IS NULL AND "
        "COL_LENGTH('DIM_TYPE_MVT_CAISSE','code_type_mvt') IS NOT NULL "
        "EXEC sp_rename 'DIM_TYPE_MVT_CAISSE.code_type_mvt', 'MC_TypeMvt', 'COLUMN'",
    ),


    (
        "FAIT_REGLEMENTS.id_date_paiement",
        "IF COL_LENGTH('FAIT_REGLEMENTS','id_date_paiement') IS NULL AND "
        "COL_LENGTH('FAIT_REGLEMENTS','id_date') IS NOT NULL "
        "EXEC sp_rename 'FAIT_REGLEMENTS.id_date', 'id_date_paiement', 'COLUMN'",
    ),
    (
        "FAIT_REGLEMENTS.id_date_echeance",
        "IF COL_LENGTH('FAIT_REGLEMENTS','id_date_echeance') IS NULL "
        "ALTER TABLE [FAIT_REGLEMENTS] ADD id_date_echeance INT NULL "
        "REFERENCES DIM_DATE(id_date)",
    ),
    (
        "FAIT_REGLEMENTS.id_type_doc",
        "IF COL_LENGTH('FAIT_REGLEMENTS','id_type_doc') IS NULL "
        "ALTER TABLE [FAIT_REGLEMENTS] ADD id_type_doc INT NULL "
        "REFERENCES DIM_TYPE_DOC(id_type_doc)",
    ),
    (
        "FAIT_REGLEMENTS.RG_Montant",
        "IF COL_LENGTH('FAIT_REGLEMENTS','RG_Montant') IS NULL "
        "ALTER TABLE [FAIT_REGLEMENTS] ADD RG_Montant NUMERIC(18,4) NULL",
    ),
    (
        "FAIT_REGLEMENTS.LB_MontantReg",
        "IF COL_LENGTH('FAIT_REGLEMENTS','LB_MontantReg') IS NULL "
        "ALTER TABLE [FAIT_REGLEMENTS] ADD LB_MontantReg NUMERIC(18,4) NULL",
    ),
    (
        "FAIT_REGLEMENTS.BR_TotalReglement",
        "IF COL_LENGTH('FAIT_REGLEMENTS','BR_TotalReglement') IS NULL "
        "ALTER TABLE [FAIT_REGLEMENTS] ADD BR_TotalReglement NUMERIC(18,4) NULL",
    ),
    (
        "FAIT_REGLEMENTS.BR_Rapproch",
        "IF COL_LENGTH('FAIT_REGLEMENTS','BR_Rapproch') IS NULL "
        "ALTER TABLE [FAIT_REGLEMENTS] ADD BR_Rapproch SMALLINT NULL",
    ),
    (
        "FAIT_REGLEMENTS.RT_NbJour",
        "IF COL_LENGTH('FAIT_REGLEMENTS','RT_NbJour') IS NULL "
        "ALTER TABLE [FAIT_REGLEMENTS] ADD RT_NbJour SMALLINT NULL",
    ),
    (
        "FAIT_REGLEMENTS.delai_reel_jours_int",
        "IF EXISTS ("
        "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='FAIT_REGLEMENTS' AND COLUMN_NAME='delai_reel_jours' "
        "AND DATA_TYPE='smallint'"
        ") "
        "ALTER TABLE [FAIT_REGLEMENTS] ALTER COLUMN delai_reel_jours INT NULL",
    ),
    (
        "FAIT_REGLEMENTS.ecart_delai_int",
        "IF EXISTS ("
        "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='FAIT_REGLEMENTS' AND COLUMN_NAME='ecart_delai' "
        "AND DATA_TYPE='smallint'"
        ") "
        "ALTER TABLE [FAIT_REGLEMENTS] ALTER COLUMN ecart_delai INT NULL",
    ),

    (
        "FAIT_REGLEMENTS.id_mode_reg_nullable",
        "IF EXISTS ("
        "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='FAIT_REGLEMENTS' AND COLUMN_NAME='id_mode_reg' "
        "AND IS_NULLABLE='NO'"
        ") "
        "ALTER TABLE [FAIT_REGLEMENTS] ALTER COLUMN id_mode_reg INT NULL",
    ),
    (
        "FAIT_REGLEMENTS.id_reglement_rename",
        """
IF COL_LENGTH('FAIT_REGLEMENTS','id_regl') IS NOT NULL
AND COL_LENGTH('FAIT_REGLEMENTS','id_reglement') IS NULL
BEGIN
    DECLARE @pk_name NVARCHAR(256);
    SELECT @pk_name = kc.name
    FROM sys.key_constraints kc
    JOIN sys.tables t ON t.object_id = kc.parent_object_id
    WHERE t.name = 'FAIT_REGLEMENTS'
      AND kc.type = 'PK';

    IF @pk_name IS NOT NULL
    BEGIN
        DECLARE @drop_sql NVARCHAR(512) =
            N'ALTER TABLE [FAIT_REGLEMENTS] DROP CONSTRAINT [' + @pk_name + N']';
        EXEC sp_executesql @drop_sql;
    END;

    EXEC sp_rename 'FAIT_REGLEMENTS.id_regl', 'id_reglement', 'COLUMN';

    ALTER TABLE [FAIT_REGLEMENTS]
        ADD CONSTRAINT [PK_FAIT_REGLEMENTS] PRIMARY KEY (id_reglement);
END
""",
    ),


    (
        "FAIT_ECRITURES.id_banque",
        "IF COL_LENGTH('FAIT_ECRITURES','id_banque') IS NULL "
        "ALTER TABLE [FAIT_ECRITURES] ADD id_banque INT NULL "
        "REFERENCES DIM_BANQUE(id_banque)",
    ),
    (
        "FAIT_ECRITURES.id_fournisseur",
        "IF COL_LENGTH('FAIT_ECRITURES','id_fournisseur') IS NULL "
        "ALTER TABLE [FAIT_ECRITURES] ADD id_fournisseur INT NULL "
        "REFERENCES DIM_FOURNISSEUR(id_fournisseur)",
    ),
    (
        "FAIT_ECRITURES.CG_Num",
        "IF COL_LENGTH('FAIT_ECRITURES','CG_Num') IS NULL "
        "ALTER TABLE [FAIT_ECRITURES] ADD CG_Num INT NULL",
    ),
    (
        "FAIT_ECRITURES.alerte_tension",
        "IF COL_LENGTH('FAIT_ECRITURES','alerte_tension') IS NULL "
        "ALTER TABLE [FAIT_ECRITURES] ADD alerte_tension SMALLINT NULL",
    ),


    (
        "DIM_CLIENT.CT_Intitule",
        "IF COL_LENGTH('DIM_CLIENT','CT_Intitule') IS NULL "
        "ALTER TABLE [DIM_CLIENT] ADD CT_Intitule NVARCHAR(100) NULL",
    ),
    (
        "DIM_CLIENT.CT_Ville",
        "IF COL_LENGTH('DIM_CLIENT','CT_Ville') IS NULL "
        "ALTER TABLE [DIM_CLIENT] ADD CT_Ville NVARCHAR(50) NULL",
    ),
    (
        "DIM_CLIENT.CT_CodeRegion",
        "IF COL_LENGTH('DIM_CLIENT','CT_CodeRegion') IS NULL "
        "ALTER TABLE [DIM_CLIENT] ADD CT_CodeRegion NVARCHAR(50) NULL",
    ),
    (
        "DIM_CLIENT.gouvernorat",
        "IF COL_LENGTH('DIM_CLIENT','gouvernorat') IS NULL "
        "ALTER TABLE [DIM_CLIENT] ADD gouvernorat NVARCHAR(50) NULL",
    ),
    (
        "FAIT_LIGNES_VENTE.source_hash",
        "IF COL_LENGTH('FAIT_LIGNES_VENTE','source_hash') IS NULL "
        "ALTER TABLE [FAIT_LIGNES_VENTE] ADD source_hash BINARY(32) NULL",
    ),
    (
        "FAIT_REGLEMENTS.source_hash",
        "IF COL_LENGTH('FAIT_REGLEMENTS','source_hash') IS NULL "
        "ALTER TABLE [FAIT_REGLEMENTS] ADD source_hash BINARY(32) NULL",
    ),
    (
        "FAIT_ECRITURES.source_hash",
        "IF COL_LENGTH('FAIT_ECRITURES','source_hash') IS NULL "
        "ALTER TABLE [FAIT_ECRITURES] ADD source_hash BINARY(32) NULL",
    ),


    (
        "DIM_SEGMENT.cbIndice_unique",
        "IF NOT EXISTS ("
        "SELECT 1 FROM sys.indexes "
        "WHERE name='UQ_DIM_SEGMENT_cbIndice' "
        "AND object_id=OBJECT_ID('DIM_SEGMENT')"
        ") "
        "ALTER TABLE [DIM_SEGMENT] ADD CONSTRAINT [UQ_DIM_SEGMENT_cbIndice] "
        "UNIQUE (cbIndice)",
    ),
    (
        "FAIT_REGLEMENTS.RT_Num",
        "IF COL_LENGTH('FAIT_REGLEMENTS','RT_Num') IS NULL "
        "ALTER TABLE [FAIT_REGLEMENTS] ADD RT_Num NVARCHAR(50) NULL",
    ),
    (
        "FAIT_REGLEMENTS.RT_Num_type",
        "IF EXISTS ("
        "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='FAIT_REGLEMENTS' AND COLUMN_NAME='RT_Num' "
        "AND DATA_TYPE='int'"
        ") "
        "ALTER TABLE [FAIT_REGLEMENTS] ALTER COLUMN RT_Num NVARCHAR(50) NULL",
    ),
]



_INDEX_MIGRATIONS: list[tuple[str, str]] = [
    (
        f"UX_{t}_source_hash",
        f"IF NOT EXISTS ("
        f"SELECT 1 FROM sys.indexes "
        f"WHERE name = 'UX_{t}_source_hash' "
        f"AND object_id = OBJECT_ID('{t}')"
        f") "
        f"CREATE UNIQUE INDEX [UX_{t}_source_hash] "
        f"ON [{t}]([source_hash]) WHERE [source_hash] IS NOT NULL",
    )
    for t in ("FAIT_LIGNES_VENTE", "FAIT_ECRITURES")
] + [
    (
        "FAIT_LIGNES_VENTE.DL_CMUP",
        "IF COL_LENGTH('FAIT_LIGNES_VENTE','DL_CMUP') IS NULL "
        "ALTER TABLE [FAIT_LIGNES_VENTE] ADD DL_CMUP NUMERIC(18,4) NULL",
    ),
    (
        "FAIT_LIGNES_VENTE.DL_PrixRU",
        "IF COL_LENGTH('FAIT_LIGNES_VENTE','DL_PrixRU') IS NULL "
        "ALTER TABLE [FAIT_LIGNES_VENTE] ADD DL_PrixRU NUMERIC(18,4) NULL",
    ),
    (
        "DROP_UX_FAIT_REGLEMENTS_source_hash",
        "IF EXISTS ("
        "SELECT 1 FROM sys.indexes "
        "WHERE name = 'UX_FAIT_REGLEMENTS_source_hash' "
        "AND object_id = OBJECT_ID('FAIT_REGLEMENTS')"
        ") "
        "DROP INDEX [UX_FAIT_REGLEMENTS_source_hash] ON [FAIT_REGLEMENTS]",
    ),
]





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
_KPI18_MIGRATIONS: list[tuple[str, str]] = [
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

# ── BIGINT surrogate key migrations ──────────────────────────────────────────
# ETL_HASH_BYTES is now 8, producing values up to 2^63-1 which overflows INT.
# These ALTER COLUMN statements upgrade the affected columns to BIGINT.
# The migration is idempotent: IF COL_LENGTH guards prevent double-execution
# errors, but SSMS may still show a warning for existing data — that is safe.
_BIGINT_MIGRATIONS: list[tuple[str, str]] = [
    (
        "DIM_CLIENT.CT_Num_code → BIGINT",
        "IF EXISTS ("
        "  SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "  WHERE TABLE_NAME='DIM_CLIENT' AND COLUMN_NAME='CT_Num_code' AND DATA_TYPE='int'"
        ") ALTER TABLE [DIM_CLIENT] ALTER COLUMN CT_Num_code BIGINT NOT NULL",
    ),
    (
        "DIM_FOURNISSEUR.CT_Num_code → BIGINT",
        "IF EXISTS ("
        "  SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "  WHERE TABLE_NAME='DIM_FOURNISSEUR' AND COLUMN_NAME='CT_Num_code' AND DATA_TYPE='int'"
        ") ALTER TABLE [DIM_FOURNISSEUR] ALTER COLUMN CT_Num_code BIGINT NOT NULL",
    ),
    (
        "DIM_ARTICLE.AR_Ref_code → BIGINT",
        "IF EXISTS ("
        "  SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "  WHERE TABLE_NAME='DIM_ARTICLE' AND COLUMN_NAME='AR_Ref_code' AND DATA_TYPE='int'"
        ") ALTER TABLE [DIM_ARTICLE] ALTER COLUMN AR_Ref_code BIGINT NOT NULL",
    ),
    (
        "DIM_JOURNAL.JO_Num_code → BIGINT",
        "IF EXISTS ("
        "  SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "  WHERE TABLE_NAME='DIM_JOURNAL' AND COLUMN_NAME='JO_Num_code' AND DATA_TYPE='int'"
        ") ALTER TABLE [DIM_JOURNAL] ALTER COLUMN JO_Num_code BIGINT NOT NULL",
    ),
    (
        "DIM_BANQUE.EB_Abrege_code → BIGINT",
        "IF EXISTS ("
        "  SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "  WHERE TABLE_NAME='DIM_BANQUE' AND COLUMN_NAME='EB_Abrege_code' AND DATA_TYPE='int'"
        ") ALTER TABLE [DIM_BANQUE] ALTER COLUMN EB_Abrege_code BIGINT NOT NULL",
    ),
    (
        "DIM_FAMILLE.FA_CodeFamille_code → BIGINT",
        "IF EXISTS ("
        "  SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "  WHERE TABLE_NAME='DIM_FAMILLE' AND COLUMN_NAME='FA_CodeFamille_code' AND DATA_TYPE='int'"
        ") ALTER TABLE [DIM_FAMILLE] ALTER COLUMN FA_CodeFamille_code BIGINT NOT NULL",
    ),
    (
        "DIM_CAISSE.CA_Numero_code → BIGINT",
        "IF EXISTS ("
        "  SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "  WHERE TABLE_NAME='DIM_CAISSE' AND COLUMN_NAME='CA_Numero_code' AND DATA_TYPE='int'"
        ") ALTER TABLE [DIM_CAISSE] ALTER COLUMN CA_Numero_code BIGINT NOT NULL",
    ),
    (
        "FAIT_LIGNES_VENTE.DO_Piece_hash → BIGINT",
        "IF EXISTS ("
        "  SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "  WHERE TABLE_NAME='FAIT_LIGNES_VENTE' AND COLUMN_NAME='DO_Piece_hash' AND DATA_TYPE='int'"
        ") ALTER TABLE [FAIT_LIGNES_VENTE] ALTER COLUMN DO_Piece_hash BIGINT NULL",
    ),
    (
        "FAIT_ECRITURES.DO_Piece_hash → BIGINT",
        "IF EXISTS ("
        "  SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
        "  WHERE TABLE_NAME='FAIT_ECRITURES' AND COLUMN_NAME='DO_Piece_hash' AND DATA_TYPE='int'"
        ") ALTER TABLE [FAIT_ECRITURES] ALTER COLUMN DO_Piece_hash BIGINT NULL",
    ),
]

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
