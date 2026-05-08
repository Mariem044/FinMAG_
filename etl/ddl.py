"""
ddl.py — SIAD MAG Distribution ETL
Génération DDL SQL Server complet — schéma constellation v14.
Ordre strict respectant les dépendances FK (8 groupes).

FIXES APPLIED
─────────────────────────────────────────────────────────────
FIX-1  : DIM_DATE        — date_valeur → date_val
FIX-2  : DIM_DATE        — semaine_iso → semaine
FIX-3  : DIM_DATE        — trimestre, semestre added (v13 carry-over)
FIX-4  : DIM_SEGMENT     — prix_ttc_flag → CT_PrixTTC
FIX-5  : DIM_COLLABORATEUR — CO_Fonction raw SMALLINT restored
           (was incorrectly hashed as CO_Fonction_code INT)
FIX-6  : DIM_BANQUE      — EB_Banque_code → EB_Banque
FIX-7  : DIM_CAISSE      — JO_Num_code → id_journal FK
FIX-8  : Codification dims — aligned with Sage source column names
           DIM_DOMAINE      : code_domaine → DO_Domaine
           DIM_TYPE_DOC     : code_type_doc → DO_Type
           DIM_MODE_REGLEMENT: code_mode_reg → RT_Mode
           DIM_ETAT_REGLEMENT: code_etat_reg → RT_Etat
           DIM_ETAT_DOCREGL : code_etat_docregl → DR_Regle
           DIM_TYPE_LIGNE   : code_type_ligne → type_ligne
           DIM_SENS_ECRITURE: code_sens → EC_Sens
           DIM_TYPE_TVA     : code_type_tva → type_tva
           DIM_TYPE_MVT_CAISSE: code_type_mvt → MC_TypeMvt
FIX-9  : FAIT_LIGNES_VENTE — id_depot removed
FIX-10 : FAIT_ECRITURES   — id_banque added
FIX-11 : FAIT_REGLEMENTS  — id_date → id_date_paiement
FIX-12 : FAIT_REGLEMENTS  — chk_regl_excl constraint restored
FIX-13 : FAIT_ECRITURES   — all stock/caisse/TVA columns restored
FIX-14 : ETL_AUDIT        — restored (was missing in v14 draft)
FIX-15 : disable_all_fk / enable_all_fk restored
FIX-16 : _apply_schema_migrations(conn) internal form restored
FIX-17 : _INDEX_MIGRATIONS wired into apply_schema_migrations()
FIX-18 : Full _MIGRATIONS list covering all renamed/added columns
"""

from __future__ import annotations

from sqlalchemy import text

from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 1 — no outgoing FK
# ═══════════════════════════════════════════════════════════════════════════════

_DDL_GROUPE_1: list[tuple[str, str]] = [

    # FIX-1/2/3: date_val, semaine, trimestre, semestre
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

    # FIX-8: DO_Domaine replaces code_domaine
    ("DIM_DOMAINE", """
CREATE TABLE DIM_DOMAINE (
    id_domaine       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    DO_Domaine       SMALLINT NOT NULL UNIQUE,
    libelle_domaine  NVARCHAR(100) NOT NULL
)"""),

    # FIX-8: DO_Type replaces code_type_doc
    ("DIM_TYPE_DOC", """
CREATE TABLE DIM_TYPE_DOC (
    id_type_doc      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    DO_Type          SMALLINT NOT NULL UNIQUE,
    libelle_type_doc NVARCHAR(100) NOT NULL
)"""),

    # FIX-8: RT_Mode replaces code_mode_reg
    ("DIM_MODE_REGLEMENT", """
CREATE TABLE DIM_MODE_REGLEMENT (
    id_mode_reg      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    RT_Mode          SMALLINT NOT NULL UNIQUE,
    libelle_mode_reg NVARCHAR(100) NOT NULL
)"""),

    # FIX-8: RT_Etat replaces code_etat_reg
    ("DIM_ETAT_REGLEMENT", """
CREATE TABLE DIM_ETAT_REGLEMENT (
    id_etat_reg      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    RT_Etat          SMALLINT NOT NULL UNIQUE,
    libelle_etat_reg NVARCHAR(100) NOT NULL
)"""),

    # FIX-8: DR_Regle replaces code_etat_docregl
    ("DIM_ETAT_DOCREGL", """
CREATE TABLE DIM_ETAT_DOCREGL (
    id_etat_docregl      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    DR_Regle             SMALLINT NOT NULL UNIQUE,
    libelle_etat_docregl NVARCHAR(100) NOT NULL
)"""),

    # FIX-8: type_ligne replaces code_type_ligne
    ("DIM_TYPE_LIGNE", """
CREATE TABLE DIM_TYPE_LIGNE (
    id_type_ligne      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    type_ligne         SMALLINT NOT NULL UNIQUE,
    libelle_type_ligne NVARCHAR(100) NOT NULL
)"""),

    # FIX-8: EC_Sens replaces code_sens
    ("DIM_SENS_ECRITURE", """
CREATE TABLE DIM_SENS_ECRITURE (
    id_sens            INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    EC_Sens            SMALLINT NOT NULL UNIQUE,
    libelle_sens       NVARCHAR(100) NOT NULL
)"""),

    # FIX-8: type_tva replaces code_type_tva
    ("DIM_TYPE_TVA", """
CREATE TABLE DIM_TYPE_TVA (
    id_type_tva        INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    type_tva           SMALLINT NOT NULL UNIQUE,
    libelle_type_tva   NVARCHAR(100) NOT NULL
)"""),

    # FIX-8: MC_TypeMvt replaces code_type_mvt
    ("DIM_TYPE_MVT_CAISSE", """
CREATE TABLE DIM_TYPE_MVT_CAISSE (
    id_type_mvt        INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    MC_TypeMvt         SMALLINT NOT NULL UNIQUE,
    libelle_type_mvt   NVARCHAR(100) NOT NULL
)"""),

    # FIX-6: EB_Banque_code → EB_Banque; source column (v13 carry-over)
    ("DIM_BANQUE", """
CREATE TABLE DIM_BANQUE (
    id_banque          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    EB_Abrege_code     INT NOT NULL UNIQUE,
    EB_Banque          INT NULL,
    source             SMALLINT NOT NULL DEFAULT 1,
    row_hash           BINARY(32) NULL
)"""),
]

# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 2
# ═══════════════════════════════════════════════════════════════════════════════

_DDL_GROUPE_2: list[tuple[str, str]] = [

    # FIX-4: prix_ttc_flag → CT_PrixTTC
    ("DIM_SEGMENT", """
CREATE TABLE DIM_SEGMENT (
    id_segment         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    cbIndice           SMALLINT NOT NULL UNIQUE,
    cbIndice_code      INT NOT NULL UNIQUE,
    CT_PrixTTC         SMALLINT NOT NULL DEFAULT 0,
    libelle_segment    NVARCHAR(100) NOT NULL,
    row_hash           BINARY(32) NULL
)"""),

    # FIX-5: CO_Fonction raw SMALLINT (not hashed)
    ("DIM_COLLABORATEUR", """
CREATE TABLE DIM_COLLABORATEUR (
    id_collab          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CO_No              INT NOT NULL UNIQUE,
    CO_Fonction        SMALLINT NULL,
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

# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 3
# ═══════════════════════════════════════════════════════════════════════════════

_DDL_GROUPE_3: list[tuple[str, str]] = [

    ("DIM_FAMILLE", """
CREATE TABLE DIM_FAMILLE (
    id_famille          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    FA_CodeFamille_code INT NOT NULL UNIQUE,
    niveau_0_code       INT NULL,
    niveau_1_code       INT NULL,
    niveau_2_code       INT NULL,
    row_hash            BINARY(32) NULL
)"""),
]

# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 4
# ═══════════════════════════════════════════════════════════════════════════════

_DDL_GROUPE_4: list[tuple[str, str]] = [

    ("DIM_CLIENT", """
CREATE TABLE DIM_CLIENT (
    id_client               INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CT_Num_code             INT NOT NULL UNIQUE,
    CT_Sommeil              SMALLINT NOT NULL DEFAULT 0,
    id_segment              INT NULL REFERENCES DIM_SEGMENT(id_segment)
                                ON DELETE SET NULL,
    id_collab               INT NULL REFERENCES DIM_COLLABORATEUR(id_collab)
                                ON DELETE SET NULL,
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
    row_hash                BINARY(32) NULL
)"""),
]

# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 5
# ═══════════════════════════════════════════════════════════════════════════════

_DDL_GROUPE_5: list[tuple[str, str]] = [

    ("DIM_ARTICLE", """
CREATE TABLE DIM_ARTICLE (
    id_article         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    AR_Ref_code        INT NOT NULL UNIQUE,
    id_famille         INT NULL REFERENCES DIM_FAMILLE(id_famille)
                           ON DELETE SET NULL,
    id_fournisseur     INT NULL REFERENCES DIM_FOURNISSEUR(id_fournisseur)
                           ON DELETE SET NULL,
    AR_Sommeil         SMALLINT NOT NULL DEFAULT 0,
    AR_PrixAch         NUMERIC(18,4) NULL,
    AR_SuiviStock      SMALLINT NOT NULL DEFAULT 0,
    row_hash           BINARY(32) NULL
)"""),
]

# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 6
# ═══════════════════════════════════════════════════════════════════════════════

_DDL_GROUPE_6: list[tuple[str, str]] = [

    ("DIM_DEPOT", """
CREATE TABLE DIM_DEPOT (
    id_depot           INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    DE_No              INT NOT NULL UNIQUE,
    DE_Principal       SMALLINT NOT NULL DEFAULT 0,
    row_hash           BINARY(32) NULL
)"""),

    # FIX-7: JO_Num_code → id_journal FK; CA_Type nullable
    ("DIM_CAISSE", """
CREATE TABLE DIM_CAISSE (
    id_caisse          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CA_Numero_code     INT NOT NULL UNIQUE,
    CA_Type            SMALLINT NULL,
    id_journal         INT NULL REFERENCES DIM_JOURNAL(id_journal)
                           ON DELETE SET NULL,
    row_hash           BINARY(32) NULL
)"""),
]

# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 7 — Facts
# ═══════════════════════════════════════════════════════════════════════════════

_DDL_GROUPE_7: list[tuple[str, str]] = [

    # FIX-9: id_depot removed
    ("FAIT_LIGNES_VENTE", """
CREATE TABLE FAIT_LIGNES_VENTE (
    id_ligne           INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    id_date            INT NULL REFERENCES DIM_DATE(id_date)
                           ON DELETE SET NULL,
    id_type_doc        INT NULL REFERENCES DIM_TYPE_DOC(id_type_doc)
                           ON DELETE SET NULL,
    id_domaine         INT NULL REFERENCES DIM_DOMAINE(id_domaine)
                           ON DELETE SET NULL,
    id_client          INT NULL REFERENCES DIM_CLIENT(id_client)
                           ON DELETE SET NULL,
    id_article         INT NULL REFERENCES DIM_ARTICLE(id_article)
                           ON DELETE SET NULL,
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
    DO_Piece_hash      INT NULL,
    source_hash        BINARY(32) NULL,
    date_extraction    DATE NOT NULL
)"""),

    # FIX-11/12: id_date_paiement + chk_regl_excl
    ("FAIT_REGLEMENTS", """
CREATE TABLE FAIT_REGLEMENTS (
    id_regl            INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    id_date_paiement   INT NULL REFERENCES DIM_DATE(id_date)
                           ON DELETE SET NULL,
    id_date_echeance   INT NULL REFERENCES DIM_DATE(id_date)
                           ON DELETE SET NULL,
    id_client          INT NULL REFERENCES DIM_CLIENT(id_client)
                           ON DELETE SET NULL,
    id_fournisseur     INT NULL REFERENCES DIM_FOURNISSEUR(id_fournisseur)
                           ON DELETE SET NULL,
    id_banque          INT NULL REFERENCES DIM_BANQUE(id_banque)
                           ON DELETE SET NULL,
    id_mode_reg        INT NULL REFERENCES DIM_MODE_REGLEMENT(id_mode_reg)
                           ON DELETE SET NULL,
    id_etat_reg        INT NULL REFERENCES DIM_ETAT_REGLEMENT(id_etat_reg)
                           ON DELETE SET NULL,
    id_etat_docregl    INT NULL REFERENCES DIM_ETAT_DOCREGL(id_etat_docregl)
                           ON DELETE SET NULL,
    id_type_doc        INT NULL REFERENCES DIM_TYPE_DOC(id_type_doc)
                           ON DELETE SET NULL,
    RT_Montant         NUMERIC(18,4) NULL,
    DR_Montant         NUMERIC(18,4) NULL,
    RC_Montant         NUMERIC(18,4) NULL,
    RG_Montant         NUMERIC(18,4) NULL,
    LB_Agios           NUMERIC(18,4) NULL,
    LB_NbJour          SMALLINT NULL,
    LB_MontantReg      NUMERIC(18,4) NULL,
    BR_TotalReglement  NUMERIC(18,4) NULL,
    BR_Rapproch        SMALLINT NULL,
    delai_reel_jours   SMALLINT NULL,
    ecart_delai        SMALLINT NULL,
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

    # FIX-10/13: id_banque added; all stock/caisse/TVA columns restored
    ("FAIT_ECRITURES", """
CREATE TABLE FAIT_ECRITURES (
    id_ecriture        INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    id_date            INT NULL REFERENCES DIM_DATE(id_date)
                           ON DELETE SET NULL,
    id_type_ligne      INT NULL REFERENCES DIM_TYPE_LIGNE(id_type_ligne)
                           ON DELETE SET NULL,
    id_journal         INT NULL REFERENCES DIM_JOURNAL(id_journal)
                           ON DELETE SET NULL,
    id_banque          INT NULL REFERENCES DIM_BANQUE(id_banque)
                           ON DELETE SET NULL,
    id_client          INT NULL REFERENCES DIM_CLIENT(id_client)
                           ON DELETE SET NULL,
    id_fournisseur     INT NULL REFERENCES DIM_FOURNISSEUR(id_fournisseur)
                           ON DELETE SET NULL,
    id_article         INT NULL REFERENCES DIM_ARTICLE(id_article)
                           ON DELETE SET NULL,
    id_depot           INT NULL REFERENCES DIM_DEPOT(id_depot)
                           ON DELETE SET NULL,
    id_type_tva        INT NULL REFERENCES DIM_TYPE_TVA(id_type_tva)
                           ON DELETE SET NULL,
    id_type_mvt        INT NULL REFERENCES DIM_TYPE_MVT_CAISSE(id_type_mvt)
                           ON DELETE SET NULL,
    id_sens            INT NULL REFERENCES DIM_SENS_ECRITURE(id_sens)
                           ON DELETE SET NULL,
    id_caisse          INT NULL REFERENCES DIM_CAISSE(id_caisse)
                           ON DELETE SET NULL,
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

# ═══════════════════════════════════════════════════════════════════════════════
# GROUP 8
# ═══════════════════════════════════════════════════════════════════════════════

_DDL_GROUPE_8: list[tuple[str, str]] = [

    # FIX-14: restored
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

# ── All groups in dependency order ───────────────────────────────────────────

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

# ═══════════════════════════════════════════════════════════════════════════════
# Additive migrations — safe to re-run every pipeline start
# ═══════════════════════════════════════════════════════════════════════════════

_MIGRATIONS: list[tuple[str, str]] = [

    # ── DIM_DATE ─────────────────────────────────────────────────────────────
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
    # date_val / semaine cannot be added as simple ALTER if the old column
    # still exists — guard with rename-then-add pattern using dynamic SQL.
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

    # ── DIM_SEGMENT ──────────────────────────────────────────────────────────
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

    # ── DIM_COLLABORATEUR ────────────────────────────────────────────────────
    # Rename hashed CO_Fonction_code back to raw CO_Fonction if needed
    (
        "DIM_COLLABORATEUR.CO_Fonction",
        "IF COL_LENGTH('DIM_COLLABORATEUR','CO_Fonction') IS NULL AND "
        "COL_LENGTH('DIM_COLLABORATEUR','CO_Fonction_code') IS NOT NULL "
        "EXEC sp_rename 'DIM_COLLABORATEUR.CO_Fonction_code', 'CO_Fonction', 'COLUMN'",
    ),
    (
        "DIM_COLLABORATEUR.CO_Fonction_add",
        "IF COL_LENGTH('DIM_COLLABORATEUR','CO_Fonction') IS NULL "
        "ALTER TABLE [DIM_COLLABORATEUR] ADD CO_Fonction SMALLINT NULL",
    ),

    # ── DIM_BANQUE ───────────────────────────────────────────────────────────
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

    # ── DIM_CAISSE ───────────────────────────────────────────────────────────
    (
        "DIM_CAISSE.id_journal",
        "IF COL_LENGTH('DIM_CAISSE','id_journal') IS NULL "
        "ALTER TABLE [DIM_CAISSE] ADD id_journal INT NULL "
        "REFERENCES DIM_JOURNAL(id_journal)",
    ),

    # ── Codification dims — rename generic code_* to Sage names ─────────────
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

    # ── FAIT_REGLEMENTS ──────────────────────────────────────────────────────
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

    # ── FAIT_ECRITURES ───────────────────────────────────────────────────────
    (
        "FAIT_ECRITURES.id_banque",
        "IF COL_LENGTH('FAIT_ECRITURES','id_banque') IS NULL "
        "ALTER TABLE [FAIT_ECRITURES] ADD id_banque INT NULL "
        "REFERENCES DIM_BANQUE(id_banque)",
    ),
    (
        "FAIT_ECRITURES.CG_Num",
        "IF COL_LENGTH('FAIT_ECRITURES','CG_Num') IS NULL "
        "ALTER TABLE [FAIT_ECRITURES] ADD CG_Num INT NULL",
    ),

    # ── source_hash columns ──────────────────────────────────────────────────
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
]

# ── Unique indexes on source_hash ────────────────────────────────────────────

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
    for t in ("FAIT_LIGNES_VENTE", "FAIT_REGLEMENTS", "FAIT_ECRITURES")
]

# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

_DROP_IF_EXISTS = (
    "IF OBJECT_ID(N'[dbo].[{name}]', N'U') IS NOT NULL "
    "DROP TABLE [{name}]"
)


def table_exists(table_name: str) -> bool:
    """Return True when *table_name* exists in the DW."""
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
    """
    Create all DW tables in FK-dependency order.

    drop_existing=True  → DROP TABLE IF EXISTS before each CREATE.
    drop_existing=False → skip tables that already exist.
    """
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


def _apply_schema_migrations(conn) -> None:
    """
    Apply all additive/rename migrations using an existing *conn*.
    Called internally by apply_schema_migrations() and by pipeline.py
    after create_all_tables().  Safe to re-run at every pipeline start.
    """
    for label, sql in _MIGRATIONS:
        try:
            conn.execute(text(sql))
            logger.info(f"  [MIGRATION OK]   {label}")
        except Exception as exc:
            logger.warning(f"  [MIGRATION WARN] {label}: {exc}")

    for label, sql in _INDEX_MIGRATIONS:
        try:
            conn.execute(text(sql))
            logger.info(f"  [INDEX OK]       {label}")
        except Exception as exc:
            logger.warning(f"  [INDEX WARN]     {label}: {exc}")


def apply_schema_migrations() -> None:
    """Public entry-point: open a transaction and run all migrations."""
    with DW_ENGINE.begin() as conn:
        _apply_schema_migrations(conn)


def disable_all_fk(conn) -> None:
    """Disable all FK constraints on every DW table (full-load helper)."""
    for table_name, _ in ALL_DDL:
        try:
            conn.execute(
                text(f"ALTER TABLE [{table_name}] NOCHECK CONSTRAINT ALL")
            )
        except Exception:
            pass


def enable_all_fk(conn) -> None:
    """Re-enable and validate all FK constraints (full-load helper)."""
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
    """DROP all tables in reverse FK order."""
    reversed_tables = [name for name, _ in reversed(ALL_DDL)]
    logger.warning("DDL : DROP ALL TABLES")

    with DW_ENGINE.begin() as conn:
        # Disable constraints first so DROP order doesn't matter
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


# ── Standalone entry-point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    drop = "--drop" in sys.argv
    create_all_tables(drop_existing=drop)
    apply_schema_migrations()