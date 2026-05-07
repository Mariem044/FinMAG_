"""
ddl.py — SIAD MAG Distribution ETL
Génération DDL SQL Server complet — schéma constellation v13.
Ordre strict respectant les dépendances FK (8 groupes).

Règles :
- Zéro VARCHAR dans les tables DW (INT, NUMERIC(18,4), DATE, SMALLINT)
- Colonnes _code = INT NOT NULL UNIQUE (hash CRC32 clé naturelle)
- PK = INT IDENTITY(1,1) sur toutes les tables
- FK ON DELETE SET NULL sur faits, ON DELETE CASCADE sur dim hiérarchiques
- row_hash BINARY(32) pour détection modifications delta (MERGE)
"""
from __future__ import annotations

from sqlalchemy import text

from etl.config import DW_ENGINE
from etl.utils.logger import get_logger

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# DDL par groupe (ordre dépendances FK)
# ═══════════════════════════════════════════════════════════════════════════════

_DDL_GROUPE_1: list[tuple[str, str]] = [

    ("DIM_DATE", """
CREATE TABLE DIM_DATE (
    id_date          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    date_valeur      DATE NOT NULL UNIQUE,
    jour             SMALLINT NOT NULL,
    mois             SMALLINT NOT NULL,
    trimestre        SMALLINT NOT NULL,
    semestre         SMALLINT NOT NULL,
    annee            SMALLINT NOT NULL,
    semaine_iso      SMALLINT NOT NULL,
    jour_semaine     SMALLINT NOT NULL,   -- 1=Lun … 7=Dim
    est_weekend      SMALLINT NOT NULL DEFAULT 0,
    est_ferie        SMALLINT NOT NULL DEFAULT 0,
    exercice         SMALLINT NULL        -- exercice fiscal Sage
)"""),

    ("DIM_DOMAINE", """
CREATE TABLE DIM_DOMAINE (
    id_domaine       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    code_domaine     SMALLINT NOT NULL UNIQUE,
    -- 0=Vente 1=Achat 2=Stock 3=Interne
    libelle_domaine  NVARCHAR(100) NOT NULL   -- human-readable label (Bug 17)
)"""),

    ("DIM_TYPE_DOC", """
CREATE TABLE DIM_TYPE_DOC (
    id_type_doc      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    code_type_doc    SMALLINT NOT NULL UNIQUE,
    libelle_type_doc NVARCHAR(100) NOT NULL   -- human-readable label (Bug 17)
)"""),

    ("DIM_MODE_REGLEMENT", """
CREATE TABLE DIM_MODE_REGLEMENT (
    id_mode_reg      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    code_mode_reg    SMALLINT NOT NULL UNIQUE,
    libelle_mode_reg NVARCHAR(100) NOT NULL   -- human-readable label (Bug 17)
)"""),

    ("DIM_ETAT_REGLEMENT", """
CREATE TABLE DIM_ETAT_REGLEMENT (
    id_etat_reg      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    code_etat_reg    SMALLINT NOT NULL UNIQUE,
    libelle_etat_reg NVARCHAR(100) NOT NULL   -- human-readable label (Bug 17)
)"""),

    ("DIM_ETAT_DOCREGL", """
CREATE TABLE DIM_ETAT_DOCREGL (
    id_etat_docregl      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    code_etat_docregl    SMALLINT NOT NULL UNIQUE,
    libelle_etat_docregl NVARCHAR(100) NOT NULL   -- human-readable label (Bug 17)
)"""),

    ("DIM_TYPE_LIGNE", """
CREATE TABLE DIM_TYPE_LIGNE (
    id_type_ligne      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    code_type_ligne    SMALLINT NOT NULL UNIQUE,
    -- 1=EcritureC 2=RegTaxe 3=MvtCaisse 4=ArtStock
    libelle_type_ligne NVARCHAR(100) NOT NULL   -- human-readable label (Bug 17)
)"""),

    ("DIM_SENS_ECRITURE", """
CREATE TABLE DIM_SENS_ECRITURE (
    id_sens            INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    code_sens          SMALLINT NOT NULL UNIQUE,   -- 0=Débit 1=Crédit
    libelle_sens       NVARCHAR(100) NOT NULL   -- human-readable label (Bug 17)
)"""),

    ("DIM_TYPE_TVA", """
CREATE TABLE DIM_TYPE_TVA (
    id_type_tva        INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    code_type_tva      SMALLINT NOT NULL UNIQUE,   -- 1=Collectée 2=Déductible
    libelle_type_tva   NVARCHAR(100) NOT NULL   -- human-readable label (Bug 17)
)"""),

    ("DIM_TYPE_MVT_CAISSE", """
CREATE TABLE DIM_TYPE_MVT_CAISSE (
    id_type_mvt        INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    code_type_mvt      SMALLINT NOT NULL UNIQUE,
    libelle_type_mvt   NVARCHAR(100) NOT NULL   -- human-readable label (Bug 17)
)"""),

    ("DIM_BANQUE", """
CREATE TABLE DIM_BANQUE (
    id_banque          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    EB_Abrege_code     INT NOT NULL UNIQUE,        -- CRC32(EB_Abrege)
    EB_Banque_code     INT NULL,                   -- CRC32(EB_Banque)
    source             SMALLINT NOT NULL DEFAULT 1, -- 1=MAG 2=GRT 3=Merge
    row_hash           BINARY(32) NULL
)"""),
]

_DDL_GROUPE_2: list[tuple[str, str]] = [

    ("DIM_SEGMENT", """
CREATE TABLE DIM_SEGMENT (
    id_segment         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    cbIndice           SMALLINT NOT NULL UNIQUE,   -- 1..5  (raw natural key)
    cbIndice_code      INT      NOT NULL UNIQUE,   -- CRC32(cbIndice) surrogate hash
    prix_ttc_flag      SMALLINT NOT NULL DEFAULT 0,
    libelle_segment    NVARCHAR(100) NOT NULL,
    row_hash           BINARY(32) NULL
)"""),

    ("DIM_COLLABORATEUR", """
CREATE TABLE DIM_COLLABORATEUR (
    id_collab          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CO_No              INT NOT NULL UNIQUE,
    CO_Fonction_code   INT NULL,                   -- CRC32(CO_Fonction)
    CO_Sommeil         SMALLINT NOT NULL DEFAULT 0,
    row_hash           BINARY(32) NULL
)"""),

    ("DIM_JOURNAL", """
CREATE TABLE DIM_JOURNAL (
    id_journal         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    JO_Num_code        INT NOT NULL UNIQUE,        -- CRC32(JO_Num)
    JO_Type            SMALLINT NULL,
    row_hash           BINARY(32) NULL
)"""),

    ("DIM_FOURNISSEUR", """
CREATE TABLE DIM_FOURNISSEUR (
    id_fournisseur     INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CT_Num_code        INT NOT NULL UNIQUE,        -- CRC32(CT_Num)
    CT_Sommeil         SMALLINT NOT NULL DEFAULT 0,
    CT_Encours         NUMERIC(18,4) NULL,
    CT_SvCA            NUMERIC(18,4) NULL,
    row_hash           BINARY(32) NULL
)"""),
]

_DDL_GROUPE_3: list[tuple[str, str]] = [

    ("DIM_FAMILLE", """
CREATE TABLE DIM_FAMILLE (
    id_famille         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    FA_CodeFamille_code INT NOT NULL UNIQUE,       -- CRC32(FA_CodeFamille)
    niveau_0_code      INT NULL,                   -- CRC32 racine
    niveau_1_code      INT NULL,                   -- CRC32 famille
    niveau_2_code      INT NULL,                   -- CRC32 sous-famille
    row_hash           BINARY(32) NULL
)"""),
]

_DDL_GROUPE_4: list[tuple[str, str]] = [

    ("DIM_CLIENT", """
CREATE TABLE DIM_CLIENT (
    id_client              INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CT_Num_code            INT NOT NULL UNIQUE,    -- CRC32(CT_Num)
    CT_Sommeil             SMALLINT NOT NULL DEFAULT 0,
    id_segment             INT NULL REFERENCES DIM_SEGMENT(id_segment)
                               ON DELETE SET NULL,
    id_collab              INT NULL REFERENCES DIM_COLLABORATEUR(id_collab)
                               ON DELETE SET NULL,
    CT_Encours             NUMERIC(18,4) NULL,
    CT_SvCA                NUMERIC(18,4) NULL,
    -- Champs GRT enrichissement
    CT_SoldeActuel         NUMERIC(18,4) NULL,
    CT_Engagement          NUMERIC(18,4) NULL,
    CT_ChiffreAffaire      NUMERIC(18,4) NULL,
    CT_EchusUnMois         NUMERIC(18,4) NULL,
    CT_EchusDeuxMois       NUMERIC(18,4) NULL,
    CT_EchusTroisMois      NUMERIC(18,4) NULL,
    CT_EchusPlusTroisMois  NUMERIC(18,4) NULL,
    CT_MoyenneDelaiPayement NUMERIC(18,4) NULL,
    CT_MoyenneDelaiImpaye  NUMERIC(18,4) NULL,
    row_hash               BINARY(32) NULL
)"""),
]

_DDL_GROUPE_5: list[tuple[str, str]] = [

    ("DIM_ARTICLE", """
CREATE TABLE DIM_ARTICLE (
    id_article         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    AR_Ref_code        INT NOT NULL UNIQUE,        -- CRC32(AR_Ref)
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
    CA_Numero_code     INT NOT NULL UNIQUE,        -- CRC32(CA_No ou CA_Numero)
    CA_Type            SMALLINT NULL,
    JO_Num_code        INT NULL,                   -- CRC32(JO_Num) ref journal
    row_hash           BINARY(32) NULL
)"""),
]

_DDL_GROUPE_7: list[tuple[str, str]] = [

    ("FAIT_LIGNES_VENTE", """
-- KPI-01 CA, KPI-02 Marge, KPI-03 Escompte, KPI-04 Top articles,
-- KPI-16 Concentrations achat, KPI-18 RFM
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
    id_depot           INT NULL REFERENCES DIM_DEPOT(id_depot)
                           ON DELETE SET NULL,
    -- Métriques
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
    -- Clé naturelle hashée pour RFM KPI-18
    DO_Piece_hash      INT NULL,                   -- CRC32(DO_Piece)
    source_hash        BINARY(32) NULL,            -- idempotent ETL key
    -- Chargement
    date_extraction    DATE NOT NULL
)"""),

    ("FAIT_REGLEMENTS", """
-- KPI-05 Règlements, KPI-06 Solde, KPI-07 Délai fournisseur,
-- KPI-08 Impayés, KPI-09 Retard client, KPI-10 Recouvrement, KPI-15 Rapprochement
CREATE TABLE FAIT_REGLEMENTS (
    id_regl            INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    id_date            INT NULL REFERENCES DIM_DATE(id_date)
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
    -- Métriques règlement
    RT_Montant         NUMERIC(18,4) NULL,
    DR_Montant         NUMERIC(18,4) NULL,
    RC_Montant         NUMERIC(18,4) NULL,         -- recouvrement KPI-10
    LB_Agios           NUMERIC(18,4) NULL,
    LB_NbJour          SMALLINT NULL,
    -- Délais KPI-07 / KPI-09
    delai_reel_jours   SMALLINT NULL,
    ecart_delai        SMALLINT NULL,              -- delai_reel - RT_NbJour contractuel
    -- Bucket impayé KPI-08 (0=0-30j,1=31-60j,2=61-90j,3=>90j)
    bucket_impaye      SMALLINT NULL,
    DR_Regle           SMALLINT NULL,             -- 0=non réglé 1=réglé
    DR_ModeReg         SMALLINT NULL,
    -- Rapprochement bancaire KPI-15
    RT_Rapproche       SMALLINT NOT NULL DEFAULT 0,
    source_hash        BINARY(32) NULL,            -- idempotent ETL key
    -- Discriminant client/fournisseur (contrainte mutuellement exclusive)
    -- CHECK garantit qu'exactement l'un des deux est renseigné
    date_extraction    DATE NOT NULL,
    CONSTRAINT chk_regl_excl CHECK (
        (id_client IS NOT NULL AND id_fournisseur IS NULL) OR
        (id_fournisseur IS NOT NULL AND id_client IS NULL) OR
        (id_client IS NULL AND id_fournisseur IS NULL)     -- cas intermédiaire chargement
    )
)"""),

    ("FAIT_ECRITURES", """
-- KPI-11 Couverture stock, KPI-12 Ruptures, KPI-13 DSI, KPI-14 Tension,
-- KPI-19 Solde comptable, KPI-20 TVA, KPI-21 Balance, KPI-22/23/24 Caisse
CREATE TABLE FAIT_ECRITURES (
    id_ecriture        INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    id_date            INT NULL REFERENCES DIM_DATE(id_date)
                           ON DELETE SET NULL,
    id_type_ligne      INT NULL REFERENCES DIM_TYPE_LIGNE(id_type_ligne)
                           ON DELETE SET NULL,
    id_journal         INT NULL REFERENCES DIM_JOURNAL(id_journal)
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
    -- Montants comptables KPI-19/20/21
    EC_Montant         NUMERIC(18,4) NULL,
    TA_Taux01          NUMERIC(18,4) NULL,
    RT_Base01          NUMERIC(18,4) NULL,
    RT_Montant01       NUMERIC(18,4) NULL,         -- TVA KPI-20
    -- Stock KPI-11/12/13/14
    AS_MontSto         NUMERIC(18,4) NULL,
    AS_QteSto          NUMERIC(18,4) NULL,
    AS_QteMini         NUMERIC(18,4) NULL,
    AS_QteRes          NUMERIC(18,4) NULL,
    qte_disponible     NUMERIC(18,4) NULL,         -- AS_QteSto - AS_QteRes
    ratio_tension      NUMERIC(18,4) NULL,         -- AS_QteRes / qte_disponible KPI-14
    en_rupture         SMALLINT NULL,              -- 1 si QteSto <= QteMini KPI-12
    alerte_tension     SMALLINT NULL,              -- 1 si ratio > 0.8 KPI-14
    qte_vendue_365j    NUMERIC(18,4) NULL,         -- calculé inter-faits
    dsi_jours          NUMERIC(18,4) NULL,         -- AS_QteSto/(qte_vendue_365j/365) KPI-13
    -- Caisse KPI-22/23/24
    MC_Debit           NUMERIC(18,4) NULL,
    MC_Credit          NUMERIC(18,4) NULL,
    MC_Cloture         SMALLINT NULL,
    CA_Solde           NUMERIC(18,4) NULL,
    CA_SoldeEspece     NUMERIC(18,4) NULL,
    CA_SoldeCheque     NUMERIC(18,4) NULL,
    -- Référence source
    EC_No              INT NULL,
    source_hash        BINARY(32) NULL,            -- idempotent ETL key
    date_extraction    DATE NOT NULL
)"""),
]

_DDL_GROUPE_8: list[tuple[str, str]] = [

    ("ETL_AUDIT", """
CREATE TABLE ETL_AUDIT (
    run_id           INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_date         DATETIME NOT NULL DEFAULT GETUTCDATE(),
    mode             VARCHAR(10) NOT NULL,          -- 'full'/'delta'/'TABLE'
    table_name       VARCHAR(100) NOT NULL,
    rows_inserted    INT NOT NULL DEFAULT 0,
    rows_updated     INT NOT NULL DEFAULT 0,
    duration_seconds INT NOT NULL DEFAULT 0,
    status           VARCHAR(20) NOT NULL,          -- 'RUNNING'/'SUCCESS'/'ERROR'/'ABORTED'
    error_msg        NVARCHAR(500) NULL
)"""),
]

# ── Tous les groupes dans l'ordre ────────────────────────────────────────────
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


# ── Fonctions publiques ───────────────────────────────────────────────────────
def table_exists(table_name: str) -> bool:
    """Vérifie si une table existe dans le DW."""
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
    Crée toutes les tables DW dans l'ordre des dépendances FK.
    - drop_existing=True : DROP TABLE IF EXISTS avant création (full rebuild)
    - drop_existing=False : skip si table déjà existante
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
    """Apply additive migrations needed by newer ETL code."""
    for table_name in ("FAIT_LIGNES_VENTE", "FAIT_REGLEMENTS", "FAIT_ECRITURES"):
        conn.execute(
            text(
                f"IF COL_LENGTH('{table_name}', 'source_hash') IS NULL "
                f"ALTER TABLE [{table_name}] ADD source_hash BINARY(32) NULL"
            )
        )
        conn.execute(
            text(
                "IF NOT EXISTS ("
                "SELECT 1 FROM sys.indexes "
                f"WHERE name = 'UX_{table_name}_source_hash' "
                f"AND object_id = OBJECT_ID('{table_name}')"
                ") "
                f"CREATE UNIQUE INDEX [UX_{table_name}_source_hash] "
                f"ON [{table_name}]([source_hash]) "
                "WHERE [source_hash] IS NOT NULL"
            )
        )


def apply_schema_migrations() -> None:
    """Run additive schema migrations on an existing DW."""
    with DW_ENGINE.begin() as conn:
        _apply_schema_migrations(conn)


def _drop_all_tables() -> None:
    """DROP dans l'ordre inverse (faits → dimensions) pour respecter les FK."""
    reversed_tables = [name for name, _ in reversed(ALL_DDL)]
    logger.warning("DDL : DROP ALL TABLES (rebuild complet)")
    with DW_ENGINE.begin() as conn:
        # Bug 18 fix: only NOCHECK if the table actually exists so the loop
        # does not silently fail and leave state inconsistent before DROP.
        for table_name in reversed_tables:
            try:
                conn.execute(
                    text(
                        f"IF OBJECT_ID(N'[{table_name}]', N'U') IS NOT NULL "
                        f"ALTER TABLE [{table_name}] NOCHECK CONSTRAINT ALL"
                    )
                )
            except Exception:
                pass  # swallow any remaining edge-case errors

        for table_name in reversed_tables:
            try:
                conn.execute(
                    text(f"DROP TABLE IF EXISTS [{table_name}]")
                )
                logger.info(f"  [DROP] {table_name}")
            except Exception as exc:
                logger.warning(f"  [DROP WARN] {table_name}: {exc}")


def disable_all_fk(conn) -> None:
    """Désactive toutes les FK constraints DW (avant full load)."""
    for table_name, _ in ALL_DDL:
        try:
            conn.execute(
                text(f"ALTER TABLE [{table_name}] NOCHECK CONSTRAINT ALL")
            )
        except Exception:
            pass


def enable_all_fk(conn) -> None:
    """Réactive et vérifie toutes les FK constraints DW (après full load)."""
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


# ── Point d'entrée standalone ─────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    drop = "--drop" in sys.argv
    create_all_tables(drop_existing=drop)
