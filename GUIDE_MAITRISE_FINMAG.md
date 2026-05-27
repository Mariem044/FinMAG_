# 📘 GUIDE COMPLET DE MAÎTRISE - PROJET FINMAG

## Table des matières
1. [Architecture Globale](#architecture-globale)
2. [Configuration Centralisée](#configuration-centralisée)
3. [Pipeline ETL](#pipeline-etl)
4. [Backend API](#backend-api)
5. [Modèles ML](#modèles-ml)
6. [Frontend React](#frontend-react)
7. [Patterns et Bonnes Pratiques](#patterns-et-bonnes-pratiques)

---

## Architecture Globale

### Vision d'ensemble
```
┌─────────────────────────────────────────────────────────┐
│                    FINMAG Dashboard                       │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Frontend (React + Vite)      Backend API (FastAPI)     │
│  ├─ Components              ├─ Endpoints (queries.py)   │
│  ├─ Hooks (useAuth)         ├─ Configuration (config.py)│
│  ├─ Stores (Zustand)        └─ Utils (logger, audit)    │
│  └─ Router (TanStack)                                    │
│                                                           │
│  ┌──────────────────────────────────────────────┐       │
│  │          ETL Pipeline                         │       │
│  │  ├─ Extract (extraction.py)                  │       │
│  │  ├─ Transform (transformation.py)            │       │
│  │  └─ Load (chargement.py)                     │       │
│  └──────────────────────────────────────────────┘       │
│                                                           │
│  ┌──────────────────────────────────────────────┐       │
│  │          ML Models                            │       │
│  │  ├─ CA Forecast (ARIMA, SARIMA, PROPHET)    │       │
│  │  └─ Runner (orchestrateur ML)                │       │
│  └──────────────────────────────────────────────┘       │
│                                                           │
│  ┌──────────────────────────────────────────────┐       │
│  │     Data Warehouse (SQL Server)              │       │
│  │  ├─ Dimensions (DIM_DATE, DIM_CLIENT, etc) │       │
│  │  ├─ Facts (FAIT_LIGNES_VENTE, etc)         │       │
│  │  └─ ML Results (ML_KPI05_CA_FORECAST)      │       │
│  └──────────────────────────────────────────────┘       │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### Flux de données
```
Sources Métier (MAG, GRT, SAG)
         ↓
    ETL EXTRACT
         ↓
    ETL TRANSFORM
         ↓
    ETL LOAD
         ↓
  Data Warehouse
    ↙        ↘
API/Backend    ML Models
    ↘        ↙
   Frontend React
```

---

## Configuration Centralisée

### Fichier: `dashboard/backend/config.py`

**Rôle**: Centraliser les configurations, les connexions BD et les utilitaires partagés.

#### Variables d'environnement requises:
```python
# Connexions bases de données
DW_CONNECTION_STRING      # Data Warehouse (lecture des KPIs)
MAG_CONNECTION_STRING     # Source MAG (Magasin/Stock)
GRT_CONNECTION_STRING     # Source GRT (Gestion des règlements)

# Configuration runtime
APP_ENV                   # "production" ou "development"
CORS_ALLOW_ORIGINS        # Origins CORS autorisées
ETL_AUDIT_TABLE           # Table d'audit ETL
ETL_LOG_FILE              # Fichier de logs ETL
ETL_LOG_LEVEL             # Niveau de logs (DEBUG, INFO, WARNING, ERROR)
```

#### Fonctions clés:

```python
def get_required_env(name: str) -> str:
    """
    OBJECTIF: Lire une variable d'environnement obligatoire
    COMPORTEMENT:
      - Si elle existe → la retourner
      - Si elle n'existe pas → lever RuntimeError
    USAGE: Éviter de créer des variables None qui causent des erreurs plus tard
    """
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
```

#### Moteurs SQLAlchemy:
```python
DW_ENGINE    # Connexion au Data Warehouse (lecture seule)
MAG_ENGINE   # Connexion à la source MAG
GRT_ENGINE   # Connexion à la source GRT
```

**⚠️ Important**: Ces moteurs utilisent `QueuePool` avec des paramètres d'optimisation:
- Pool size adapté aux connexions simultanées
- Echo désactivé en production (logs des requêtes SQL)
- Timeouts configurés

---

## Pipeline ETL

### Vue d'ensemble du pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ 1. INITIALISATION                                            │
│    ├─ Charger variables d'environnement                     │
│    ├─ Créer/Valider tables (DDL)                           │
│    └─ Démarrer enregistrement d'audit                       │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. DIMENSIONS (Données de référence)                        │
│                                                              │
│    A. DIM_DATE (Calendrier)                                │
│       - Générer plage de dates (ex: 2018-2025)            │
│       - Ajouter colonnes: jour, mois, trimestre, année    │
│       - Marquer jours fériés                               │
│                                                              │
│    B. Dimensions lookup (codes de référence)              │
│       - DIM_SEGMENT: Catégories tarifaires                │
│       - DIM_VILLE: Gouvernorats (régions)                 │
│       - DIM_MODE_REGLEMENT: Modalités de paiement         │
│       - DIM_COLLABORATEUR: Équipe commerciale             │
│       - DIM_FAMILLE: Catégories de produits               │
│       - DIM_FOURNISSEUR: Tiers fournisseurs               │
│       - DIM_ARTICLE: Catalogue produits                   │
│       - DIM_CLIENT: Clients (données consolidées)         │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. FAITS (Données transactionnelles)                        │
│                                                              │
│    - FAIT_LIGNES_VENTE: Lignes de commandes/ventes        │
│    - FAIT_REGLEMENTS: Paiements clients                    │
│    - FAIT_ENCOURS: Encours clients                         │
│    - FAIT_MOUVEMENTS_CAISSE: Mouvements de caisse          │
│                                                              │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. CALCULS KPI & POST-TRAITEMENT                           │
│                                                              │
│    - Dériver KPIs (CA, Encours, Délai paiement)          │
│    - Consolider métriques                                   │
│                                                              │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. AUDIT & FINALISATION                                     │
│                                                              │
│    - Enregistrer nblignes insérées/mises à jour            │
│    - Enregistrer durée d'exécution                         │
│    - Marquer comme SUCCESS ou ERROR                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Fichiers du Pipeline ETL

#### 1. `etl/extract.py` - EXTRACTION

**Rôle**: Lire les données depuis les sources (MAG, GRT)

```python
# Pattern: Une fonction par table source

def extract_dim_segment():
    """Extraire catégories tarifaires depuis MAG"""
    return _read(
        MAG_ENGINE,
        """
        SELECT cbIndice, CT_PrixTTC, CT_Intitule AS libelle_segment
        FROM P_CATTARIF
        WHERE cbIndice BETWEEN 1 AND 5
    )

def extract_dim_ville():
    """Extraire gouvernorats depuis GRT"""
    return _read(
        GRT_ENGINE,
        "SELECT CbIndice, VI_Designation, VI_Code FROM P_Ville"
    )

def extract_dim_client_mag():
    """Extraire clients depuis MAG (magasin/stock)"""
    return _read(
        MAG_ENGINE,
        """
        SELECT CT_Num, CT_Sommeil, CT_Intitule, CT_Ville
        FROM F_COMPTET WHERE CT_Type = 0
    )
```

**⚠️ Abstraction `_read(engine, sql)`**:
```python
def _read(engine, sql):
    """
    PATTERN: Wrappeur pour exécuter SQL et retourner DataFrame
    AVANTAGES:
      - Gestion d'erreur centralisée
      - Utilisation consistent des engines
      - Facilite les mocks en tests
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)
```

#### 2. `etl/transform.py` - TRANSFORMATION

**Rôle**: Normaliser et enrichir les données extraites

```python
def transform_dim_date(df):
    """
    OBJECTIF: Ajouter colonnes calendrier à un DataFrame de dates
    
    COLONNES AJOUTÉES:
    - jour (1-31): Jour du mois
    - mois (1-12): Numéro du mois
    - trimestre (1-4): Trimestre de l'année
    - semestre (1-2): 1er ou 2ème semestre
    - annee (2018-2025): Année
    - semaine (1-53): Semaine ISO
    - jour_semaine (0-6): Lundi=0, Dimanche=6
    - est_weekend (0,1): Flag si samedi ou dimanche
    - est_ferie (0,1): Flag si jour férié (enrichi après)
    - exercice: Même que année
    
    PSEUDO-CODE:
    1. Convertir colonne 'date_val' en datetime
    2. Extraire jour, mois, année du datetime
    3. Calculer trimestre = (mois-1) // 3 + 1
    4. Calculer semestre = 1 si mois <= 6 else 2
    5. Extraire numéro de semaine ISO
    6. Extraire jour de la semaine (0=lundi)
    7. Marquer si weekend (jour_semaine >= 5)
    8. Initialiser est_ferie à 0 (enrichi après)
    """
    df = df.copy()
    df["date_val"] = pd.to_datetime(df["date_val"])
    df["jour"] = df["date_val"].dt.day.astype("int16")
    df["mois"] = df["date_val"].dt.month.astype("int16")
    df["trimestre"] = df["date_val"].dt.quarter.astype("int16")
    df["semestre"] = df["mois"].apply(lambda m: 1 if m <= 6 else 2).astype("int16")
    df["annee"] = df["date_val"].dt.year.astype("int16")
    df["semaine"] = df["date_val"].dt.isocalendar().week.astype("int16")
    df["jour_semaine"] = df["date_val"].dt.dayofweek.astype("int16")
    df["est_weekend"] = df["jour_semaine"].apply(lambda d: 1 if d >= 5 else 0).astype("int16")
    df["est_ferie"] = 0
    df["exercice"] = df["annee"]
    return df

def add_fact_reglements_calcs(df):
    """
    OBJECTIF: Calculer délai de paiement et bucket impayés
    
    COLONNES AJOUTÉES:
    - delai_reel_jours: Date paiement - Date document initial
    - ecart_delai: delai_reel - délai contrat (RT_NbJour)
    - bucket_impaye: Classe d'ancienneté si impayé
      * 0: 0-30 jours
      * 1: 31-60 jours
      * 2: 61-90 jours
      * 3: >90 jours
    
    PSEUDO-CODE:
    1. Convertir RT_Date (date paiement) en datetime
    2. Convertir DO_Date (date document) en datetime
    3. delai_reel_jours = RT_Date - DO_Date (en jours)
    4. ecart_delai = delai_reel_jours - RT_NbJour
    5. Si impayé: Calculer bucket basé sur jours de retard
    """
    df = df.copy()
    df["RT_Date"] = pd.to_datetime(df["RT_Date"], errors="coerce")
    df["DO_Date"] = pd.to_datetime(df["DO_Date"], errors="coerce")
    df["RT_NbJour"] = pd.to_numeric(df["RT_NbJour"], errors="coerce").fillna(0)
    df["delai_reel_jours"] = (df["RT_Date"] - df["DO_Date"]).dt.days
    df["ecart_delai"] = df["delai_reel_jours"] - df["RT_NbJour"]
    return df
```

#### 3. `etl/load.py` - CHARGEMENT

**Rôle**: Charger les données transformées dans le Data Warehouse

```python
def load_dimension(df, table):
    """
    OBJECTIF: Charger une dimension (effacer & insérer)
    
    COMPORTEMENT:
    1. Si DataFrame est vide → Quitter (rien à charger)
    2. Filtrer colonnes DataFrame pour garder seulement celles qui existent en DB
    3. Si ETL_ALLOW_TABLE_DELETE=true:
       - DELETE FROM table  (vider la table)
       - INSERT les nouvelles données (full load)
    4. Sinon:
       - APPEND les données (incremental, legacy)
    5. Loger le nombre de lignes chargées
    
    PSEUDO-CODE:
    1. target_cols = get_table_columns(table) → Liste colonnes DB
    2. valid_cols = [c for c in df.columns if c in target_cols]
    3. df_clean = df[valid_cols]
    4. Si ALLOW_TABLE_DELETE: DELETE FROM table
    5. df_clean.to_sql(table, if_exists="append")
    6. logger.info(f"[{table}] {len(df_clean)} lignes chargées")
    """
    if df.empty:
        logger.info(f"[{table}] DataFrame vide, rien à charger.")
        return

    target_cols = get_table_columns(table)
    valid_cols = [c for c in df.columns if c in target_cols]
    df_clean = df[valid_cols].copy()

    if ALLOW_TABLE_DELETE:
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"DELETE FROM [{table}]"))

    df_clean.to_sql(table, DW_ENGINE, if_exists="append", index=False)
    logger.info(f"[{table}] {len(df_clean)} lignes chargées.")

def load_fact(df, table):
    """
    OBJECTIF: Charger une table de faits (même logique que dimension)
    """
    load_dimension(df, table)
```

#### 4. `etl/pipeline.py` - ORCHESTRATEUR

**Rôle**: Coordonner extract, transform, load

```python
def run_pipeline():
    """
    OBJECTIF: Exécuter ETL complet : EXTRACT → TRANSFORM → LOAD
    
    ÉTAPES:
    1. Initialiser audit (start_run)
    2. Créer/valider tables (ddl.create_all_tables)
    3. Charger DIMENSIONS (DIM_DATE, DIM_SEGMENT, DIM_VILLE, etc)
    4. Charger FAITS (FAIT_LIGNES_VENTE, FAIT_REGLEMENTS, etc)
    5. Calculer KPIs et post-traitement
    6. Finaliser audit (success/error)
    
    PSEUDO-CODE:
    try:
        ensure_dw_database_exists()
        run_id = audit.start_run("full")  # Début audit
        
        # Créer tables
        ddl.create_all_tables(drop_existing=False)
        
        # Charger dimensions
        df_date = transform.transform_dim_date(date_range)
        load.load_dimension(df_date, "DIM_DATE")
        lookups["DIM_DATE"] = _build_lookup("DIM_DATE", "date_val", "id_date")
        
        # ... charger autres dimensions
        
        # Charger faits
        df_ventes = extract_faits_ventes()
        df_ventes = enrich_with_lookups(df_ventes, lookups)
        load.load_fact(df_ventes, "FAIT_LIGNES_VENTE")
        
        # Calculer KPIs
        calculate_kpis()
        
        audit.complete_run(run_id, "SUCCESS")
        
    except Exception as exc:
        audit.complete_run(run_id, "ERROR", str(exc))
        raise
    """
    logger.info("=== ETL PIPELINE STARTED ===")
    # ... implémentation
```

#### 5. Fonctions utilitaires

```python
def _build_lookup(table_name, natural_col, surrogate_col):
    """
    OBJECTIF: Créer table de correspondance natural_key → surrogate_key
    
    EXEMPLE:
    Table DIM_DATE:
    ┌────────────────┬──────────┐
    │ date_val       │ id_date  │
    ├────────────────┼──────────┤
    │ 2024-01-15     │ 15       │
    │ 2024-01-16     │ 16       │
    └────────────────┴──────────┘
    
    Lookup retourné:
    {
        date(2024, 1, 15): 15,
        date(2024, 1, 16): 16,
    }
    
    USAGE: Enrichir faits avec IDs dimensions
    fact_row["id_date"] = lookups["DIM_DATE"][fact_row["date_val"]]
    
    PSEUDO-CODE:
    1. SELECT [surrogate_col], [natural_col] FROM [table]
    2. Si DIM_DATE: Convertir natural_col en date
    3. Retourner dict(zip(natural_col, surrogate_col))
    """
    query = f"SELECT [{surrogate_col}], [{natural_col}] FROM [{table_name}]"
    df = pd.read_sql(query, DW_ENGINE)
    if table_name == "DIM_DATE" and not df.empty:
        df[natural_col] = pd.to_datetime(df[natural_col]).dt.date
    return dict(zip(df[natural_col], df[surrogate_col]))

def _clean_text_code(value):
    """
    OBJECTIF: Normaliser code texte pour matching
    
    TRANSFORMATIONS:
    - Convertir en majuscules (case-insensitive matching)
    - Trim espaces avant/après
    - Retourner None si vide
    
    EXEMPLES:
    "  tunisia  " → "TUNISIA"
    "code_client" → "CODE_CLIENT"
    None → None
    
    PSEUDO-CODE:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text.upper() if text else None
    """
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text.upper() if text else None

def _clean_bank_account(value):
    """
    OBJECTIF: Extraire chiffres du numéro de compte bancaire
    
    EXEMPLES:
    "1234-5678-90" → "1234567890"
    "12 34 56 78" → "12345678"
    None → None
    
    PSEUDO-CODE:
    if pd.isna(value):
        return None
    digits = re.sub(r"\D+", "", str(value))  # Garder que digits
    return digits or None
    """
    if pd.isna(value):
        return None
    digits = re.sub(r"\D+", "", str(value))
    return digits or None
```

---

## Backend API

### Fichier: `dashboard/backend/api/queries.py`

**Rôle**: Exposer endpoints REST pour le frontend

#### Initialisation FastAPI

```python
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FinMAG API")

# CORS Configuration
cors_origins = ["*"] if DEV_MODE else [...]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### Middleware de Logging

```python
@app.middleware("http")
async def log_requests(request, call_next):
    """
    OBJECTIF: Logger chaque requête HTTP
    
    INFORMATIONS LOGGÉES:
    - Timestamp ISO
    - Méthode HTTP (GET, POST, etc)
    - URL complète
    - Status code de la réponse
    
    PSEUDO-CODE:
    1. Enregistrer timestamp et URL
    2. Si REQUEST_LOG_FILE: Écrire dans fichier
    3. Sinon: Loger en console
    4. Appeler le prochain handler (call_next)
    5. Loger le status code retourné
    6. Retourner la réponse
    """
    url = str(request.url)
    timestamp = datetime.now().isoformat()
    
    if REQUEST_LOG_FILE:
        # Écrire dans fichier
        with open(REQUEST_LOG_FILE, "a") as f:
            f.write(f"{timestamp} {request.method} {url}\n")
    
    response = await call_next(request)
    logger.info(f"Request completed: {request.method} {url} {response.status_code}")
    return response
```

#### Fonctions de Base de Données

```python
def _rows(sql, params=None):
    """
    OBJECTIF: Exécuter requête SQL et retourner TOUTES les lignes
    
    COMPORTEMENT:
    - Utilise DW_ENGINE (Data Warehouse, lecture seule)
    - Gère les erreurs SQLAlchemy
    - Retourne [] si ETL en cours (évite locks)
    
    PSEUDO-CODE:
    if _ETL_RUN_LOCK.locked():
        return []  # ETL en cours, éviter deadlock
    
    try:
        with DW_ENGINE.connect() as conn:
            result = conn.execute(text(sql), params or {})
            return result.fetchall()
    except SQLAlchemyError as exc:
        logging.error(f"Database error: {exc}")
        return []
    """
    if _ETL_RUN_LOCK.locked():
        return []
    try:
        with DW_ENGINE.connect() as conn:
            return conn.execute(text(sql), params or {}).fetchall()
    except SQLAlchemyError as exc:
        logging.error(f"Database query error: {exc}")
        return []

def _row(sql, params=None):
    """
    OBJECTIF: Exécuter requête SQL et retourner UNE SEULE ligne
    Même logique que _rows() mais avec .fetchone()
    """
    if _ETL_RUN_LOCK.locked():
        return None
    try:
        with DW_ENGINE.connect() as conn:
            return conn.execute(text(sql), params or {}).fetchone()
    except SQLAlchemyError as exc:
        logging.error(f"Database query error: {exc}")
        return None
```

#### Constants et Mappings

```python
MONTHS = ["Jan", "Fev", "Mar", "Avr", "Mai", "Jun", "Jul", "Aou", "Sep", "Oct", "Nov", "Dec"]
NO_FILTER_VALUES = ("Tous", "Toutes", "")  # Valeurs considérées comme "pas de filtre"
QUARTER_MAP = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
```

#### Patterns de requêtes

```python
# Pattern 1: Lire toutes les lignes
rows = _rows("SELECT * FROM DIM_CLIENT")
for row in rows:
    print(row.client_id, row.nom)

# Pattern 2: Lire une seule ligne
row = _row("SELECT * FROM DIM_CLIENT WHERE id_client = ?", [5])
if row:
    print(row.nom)

# Pattern 3: Requête avec paramètres
rows = _rows(
    "SELECT * FROM FAIT_LIGNES_VENTE WHERE annee = :year AND mois = :month",
    {"year": 2024, "month": 1}
)
```

---

## Modèles ML

### Fichier: `dashboard/backend/ml/ca_forecast.py`

**Rôle**: Prévoir le Chiffre d'Affaires (CA) mensuel avec 3 modèles

#### Architecture des modèles

```
┌──────────────────────────────────────────────┐
│      CA_FORECAST (3 modèles en parallèle)   │
├──────────────────────────────────────────────┤
│                                              │
│  1. ARIMA                                    │
│     └─ AutoRegressive Integrated Moving Avg │
│        (séries temporelles simples)          │
│                                              │
│  2. SARIMA                                   │
│     └─ Seasonal ARIMA                       │
│        (ajoute saisonnalité)                │
│                                              │
│  3. PROPHET (Facebook)                       │
│     └─ Gère tendances, saisonnalité,        │
│        jours fériés                         │
│                                              │
└──────────────────────────────────────────────┘
         ↓
    Ensemble des 3 prévisions
    + Intervalles de confiance (yhat_lower, yhat_upper)
```

#### Données d'entrée

```sql
SELECT
    DATEFROMPARTS(d.annee, d.mois, 1) AS ds,
    SUM(f.DL_MontantHT) AS y
FROM FAIT_LIGNES_VENTE f
JOIN DIM_DATE d ON d.id_date = f.id_date
WHERE f.DO_Domaine = 0
GROUP BY d.annee, d.mois
HAVING COUNT(*) > 10  -- Filtre bruit mineurs (< 10 lignes/mois)
ORDER BY ds
```

**Résultat attendu**:
```
ds            | y
──────────────┼─────────────
2020-01-01    | 150000
2020-02-01    | 175000
2020-03-01    | 160000
...
```

#### Pipeline de prévision

```python
def _load_monthly_ca() -> pd.DataFrame:
    """
    OBJECTIF: Charger historique mensuel du CA
    
    PSEUDO-CODE:
    1. Requête SQL pour agréger CA par mois
    2. Convertir ds en datetime, y en float
    3. Nettoyer valeurs manquantes (dropna)
    4. Trier par date
    5. Retourner DataFrame avec colonnes ds, y
    """
    sql = """
        SELECT
            DATEFROMPARTS(d.annee, d.mois, 1) AS ds,
            SUM(f.DL_MontantHT) AS y
        FROM FAIT_LIGNES_VENTE f
        JOIN DIM_DATE d ON d.id_date = f.id_date
        WHERE f.DO_Domaine = 0
        GROUP BY d.annee, d.mois
        HAVING COUNT(*) > 10
        ORDER BY ds
    """
    with DW_ENGINE.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    df = df.dropna().sort_values("ds").reset_index(drop=True)
    
    if df.empty:
        logger.warning("No monthly CA observations found")
        return df
    
    logger.info(f"Loaded {len(df)} monthly observations ({df['ds'].min().date()} -> {df['ds'].max().date()})")
    return df
```

#### Modèle ARIMA

```python
def _forecast_arima(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """
    OBJECTIF: Prévision avec ARIMA (AutoRegressive Integrated Moving Average)
    
    PARAMÈTRES:
    - p: nombre de termes autorégressifs
    - d: degré de différenciation (rendre stationnaire)
    - q: nombre de termes de moyenne mobile
    
    PROCESSUS:
    1. Ajuster modèle ARIMA aux données historiques
    2. Générer prévisions sur horizon mois
    3. Calculer intervales de confiance (80%, 95%)
    4. Retourner DataFrame avec yhat, yhat_lower, yhat_upper
    
    PSEUDO-CODE:
    try:
        model = ARIMA(df['y'], order=(p, d, q))
        fitted = model.fit()
        forecast = fitted.get_forecast(steps=horizon)
        forecast_df = forecast.conf_int(alpha=0.2)  # 80% CI
        return format_output(forecast_df, 'ARIMA')
    except Exception:
        # Fallback si ARIMA échoue
        return _forecast_seasonal_fallback(df, horizon, 'ARIMA')
    """
    # ... implémentation
```

#### Modèle SARIMA

```python
def _forecast_sarima(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """
    OBJECTIF: Prévision avec SARIMA (Seasonal ARIMA)
    
    Ajoute composante saisonnière:
    - P: AR saisonnier
    - D: Différenciation saisonnière
    - Q: MA saisonnier
    - m: Période saisonnière (12 mois pour données annuelles)
    
    PROCESSUS:
    1. Ajuster SARIMA avec paramètres (p,d,q)x(P,D,Q,12)
    2. Générer prévisions
    3. Retourner avec intervales de confiance
    
    PSEUDO-CODE:
    try:
        model = SARIMAX(df['y'], order=(p,d,q), seasonal_order=(P,D,Q,12))
        fitted = model.fit()
        forecast = fitted.get_forecast(steps=horizon)
        return format_output(forecast, 'SARIMA')
    except Exception:
        return _forecast_seasonal_fallback(df, horizon, 'SARIMA')
    """
    # ... implémentation
```

#### Modèle PROPHET

```python
def _forecast_prophet(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """
    OBJECTIF: Prévision avec PROPHET (Framework Facebook)
    
    AVANTAGES:
    - Robuste au bruit et données manquantes
    - Gère saisonnalités multiples
    - Support jours fériés
    - Généralement moins d'ajustement paramètres requis
    
    FORMAT PROPHET:
    - ds: timestamp
    - y: valeur à prévoir
    
    PROCESSUS:
    1. Préparer df au format PROPHET (colonnes ds, y)
    2. Créer modèle Prophet
    3. Fit sur données historiques
    4. Générer future dataframe (horizon mois)
    5. Prédire sur future
    6. Retourner avec yhat, yhat_lower, yhat_upper
    
    PSEUDO-CODE:
    try:
        model = Prophet(interval_width=0.80)
        model.fit(df[['ds', 'y']])
        future = model.make_future_dataframe(periods=horizon, freq='MS')
        forecast = model.predict(future)
        return extract_columns(forecast, 'PROPHET')
    except Exception:
        return _forecast_seasonal_fallback(df, horizon, 'PROPHET')
    """
    # ... implémentation
```

#### Plan de secours (Fallback)

```python
def _forecast_seasonal_fallback(df: pd.DataFrame, horizon: int, model_name: str) -> pd.DataFrame:
    """
    OBJECTIF: Prévision par décomposition saisonnière si ARIMA/SARIMA/PROPHET échouent
    
    APPROCHE SIMPLE:
    1. Ajuster tendance linéaire (y = a*t + b)
    2. Calculer ratios saisonniers par mois
    3. Appliquer tendance + saisonnalité pour avenir
    4. Ajouter intervales de confiance basés résidus
    
    PSEUDO-CODE:
    1. Fit ligne y = alpha*t + beta
    2. trend = alpha*t + beta pour chaque mois
    3. seasonal_ratios = y / trend (pour chaque observation)
    4. monthly_seasonality = moyenne ratios par mois
    5. Normaliser monthly_seasonality (moyenne = 1.0)
    6. Générer dates futures
    7. future_yhat = future_trend * monthly_seasonality[month]
    8. std_err = std(résidus historiques)
    9. yhat_lower = yhat - 1.28 * std_err  (80% CI)
    10. yhat_upper = yhat + 1.28 * std_err
    11. Clipper valeurs >= 0 (pas de CA négatif!)
    
    EXEMPLE:
    Historique: Jan 100, Feb 120, Mar 100, ...
    Trend: 100, 101, 102, ...
    Seasonal ratios: 1.0, 1.19, 0.98, ...
    Moyenne par mois: Jan→1.0, Feb→1.15, Mar→1.05, ...
    
    Prévision Jan+12: trend[Jan+12] * 1.0 = ...
    """
    logger.info(f"Running Seasonal Decomposition Fallback for {model_name}...")
    n_obs = len(df)
    t = np.arange(n_obs)
    y = df["y"].values.astype(float)
    
    # Tendance linéaire
    if n_obs >= 2:
        alpha, beta = np.polyfit(t, y, 1)
    else:
        alpha, beta = 0.0, float(y[0]) if n_obs > 0 else 0.0
    
    trend = alpha * t + beta
    trend_safe = np.where(trend <= 0, 1e-5, trend)
    seasonal_ratios = y / trend_safe
    
    # Saisonnalité par mois
    df_temp = df.copy()
    df_temp["ratio"] = seasonal_ratios
    df_temp["month"] = df_temp["ds"].dt.month
    monthly_seasonality = df_temp.groupby("month")["ratio"].mean().to_dict()
    
    # Remplir mois manquants
    for m in range(1, 13):
        if m not in monthly_seasonality:
            monthly_seasonality[m] = 1.0
    
    # Normaliser (moyenne = 1.0)
    mean_ratio = np.mean(list(monthly_seasonality.values()))
    if mean_ratio > 0:
        for m in monthly_seasonality:
            monthly_seasonality[m] /= mean_ratio
    
    # Générer prévisions futures
    last_ds = df["ds"].max()
    future_dates = [last_ds + pd.DateOffset(months=i) for i in range(1, horizon + 1)]
    future_df = pd.DataFrame({"ds": future_dates})
    future_df["y"] = np.nan
    
    full_df = pd.concat([df, future_df], ignore_index=True)
    full_df["t"] = np.arange(len(full_df))
    full_df["month"] = full_df["ds"].dt.month
    
    pred_trend = alpha * full_df["t"].values + beta
    full_df["yhat"] = pred_trend * full_df["month"].map(monthly_seasonality)
    
    # Intervales de confiance
    residuals = y - (trend * df_temp["month"].map(monthly_seasonality))
    std_err = np.std(residuals) if len(residuals) > 1 else 0.1 * np.mean(y) if len(y) > 0 else 1.0
    
    full_df["yhat_lower"] = full_df["yhat"] - 1.28 * std_err
    full_df["yhat_upper"] = full_df["yhat"] + 1.28 * std_err
    full_df["is_historical"] = (full_df["ds"] <= df["ds"].max()).astype(int)
    
    result = full_df[["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical"]].copy()
    result["yhat"] = result["yhat"].clip(lower=0)
    result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
    result["yhat_upper"] = result["yhat_upper"].clip(lower=0)
    result["model_name"] = model_name
    return result
```

#### Table de résultats

```sql
CREATE TABLE ML_KPI05_CA_FORECAST (
    id INT IDENTITY(1,1) PRIMARY KEY,
    run_date DATETIME NOT NULL,            -- Quand forecast généré
    model_name VARCHAR(20) NOT NULL,       -- ARIMA, SARIMA ou PROPHET
    ds DATE NOT NULL,                      -- Date prévision
    yhat NUMERIC(18,4) NOT NULL,           -- CA prévu
    yhat_lower NUMERIC(18,4) NOT NULL,     -- Borne basse intervale confiance
    yhat_upper NUMERIC(18,4) NOT NULL,     -- Borne haute intervale confiance
    is_historical SMALLINT NOT NULL,       -- 1=historique, 0=prévision
    mape NUMERIC(10,4) NULL,               -- Mean Absolute Percentage Error
    mae NUMERIC(18,4) NULL                 -- Mean Absolute Error
)
```

### Fichier: `dashboard/backend/ml/runner.py`

**Rôle**: Orchestrer exécution des modèles ML

```python
_ML_RUN_LOCK = threading.Lock()      # Verrou pour exécutions séquentielles
_ML_IS_RUNNING = False                # Flag d'exécution
_ML_LAST_ERROR = None                 # Message d'erreur du dernier run

def is_running():
    """
    OBJECTIF: Vérifier si un ML pipeline est en cours
    
    RETOURNE True SI:
    - _ML_IS_RUNNING = True, OU
    - Verrou est bloqué (thread en cours)
    
    USAGE: Frontend utilise pour afficher spinner/loading
    """
    global _ML_IS_RUNNING
    return _ML_IS_RUNNING or _ML_RUN_LOCK.locked()

def run_all(only=None, skip=None):
    """
    OBJECTIF: Exécuter tous les modèles ML en synchrone (bloquant)
    
    PARAMÈTRES:
    - only: Liste KPI à exécuter (ex: ["05"] pour juste CA forecast)
    - skip: Liste KPI à ignorer
    
    RETOURNE:
    {"05": "OK"} ou {"05": "ERROR: message"}
    
    PSEUDO-CODE:
    modules = {"05": ca_forecast}  # Modules ML disponibles
    
    if only:
        modules = {k: v for k, v in modules.items() if k in only}
    if skip:
        modules = {k: v for k, v in modules.items() if k not in skip}
    
    results = {}
    for kpi_id, mod in modules.items():
        try:
            logger.info(f"Running ML KPI-{kpi_id}...")
            mod.run()  # Lance l'entraînement
            results[kpi_id] = "OK"
        except Exception as exc:
            logger.error(f"Error running KPI-{kpi_id}: {exc}")
            results[kpi_id] = f"ERROR: {exc}"
    return results
    """
    # ... implémentation

def run_all_background():
    """
    OBJECTIF: Lancer ML pipeline en arrière-plan (async)
    
    COMPORTEMENT:
    1. Essayer d'acquérir verrou sans bloquer
    2. Si on peut pas = un autre pipeline est déjà en cours → retourner False
    3. Si on peut = Créer thread daemon qui exécute run_all()
    4. Retourner True pour indiquer succès
    
    PSEUDO-CODE:
    if not _ML_RUN_LOCK.acquire(blocking=False):
        return False  # Pipeline déjà en cours
    
    def _run():
        global _ML_IS_RUNNING, _ML_LAST_ERROR
        _ML_IS_RUNNING = True
        try:
            run_all()
            _ML_LAST_ERROR = None
        except Exception as exc:
            logger.error(f"Background ML error: {exc}")
            _ML_LAST_ERROR = str(exc)
        finally:
            _ML_IS_RUNNING = False
            _ML_RUN_LOCK.release()
    
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return True
    """
    # ... implémentation
```

---

## Frontend React

### Fichier: `dashboard/frontend/src/main.jsx`

**Rôle**: Point d'entrée de l'application React

```javascript
import { createRoot } from "react-dom/client";
import { RouterProvider } from "@tanstack/react-router";
import { getRouter } from "./router";
import "./styles.css";

const router = getRouter();
const root = document.getElementById("root");

if (!root) {
  throw new Error("Root element not found");
}

createRoot(root).render(<RouterProvider router={router} />);
```

**Composants clés**:
- `createRoot`: Initialise racine React (remplace ReactDOM.render)
- `RouterProvider`: Fournit routing contextuel
- Styles CSS globaux chargés

### Fichier: `dashboard/frontend/src/router.jsx`

**Rôle**: Configuration du routeur TanStack Router

```javascript
export const getRouter = () => {
  const router = createRouter({
    routeTree,                        // Arbre de routes généré
    context: {},                      // Context global partagé entre routes
    scrollRestoration: true,          // Restaurer scroll position
    defaultPreloadStaleTime: 0,       // Preload agressif
    defaultErrorComponent: DefaultErrorComponent,  // Component erreur personnalisé
  });
  return router;
};
```

**Routes principales** (dans `src/routes/`):
- `__root.jsx`: Layout racine
- `login.jsx`: Authentification
- `index.jsx`: Accueil
- `dashboard/` (group): Pages dashboard
  - `comptabilite.jsx`: Module comptabilité
  - `finance.jsx`: Module finance
  - `predictions.jsx`: Module prédictions ML
  - `parametres.jsx`: Paramètres
- `ProtectedRoute.jsx`: HOC pour routes authentifiées

### Structure des composants

```
src/components/
├── auth/
│   └── ProtectedRoute.jsx      // Wrapper pour routes privées
├── dashboard/
│   ├── Header.jsx              // En-tête page
│   ├── Sidebar.jsx             // Menu latéral
│   ├── DashboardLayout.jsx      // Layout principal
│   ├── KPICard.jsx              // Carte KPI (métrique)
│   ├── ChartCard.jsx            // Carte graphique
│   ├── FiltersBar.jsx           // Barre filtres
│   └── CustomTooltip.jsx        // Infobulle personnalisée
└── ...
```

### Hooks personnalisés

```javascript
// src/hooks/useApiResource.js
/**
 * OBJECTIF: Requête HTTP avec gestion cache et état
 * UTILISÉ POUR: GET données depuis API backend
 * 
 * RETURNS: { data, isLoading, error, refetch }
 */

// src/store/useAuth.js
/**
 * OBJECTIF: Gestion authentification utilisateur
 * STATE: { user, isAuthenticated, login(), logout() }
 * STOCKAGE: localStorage pour persistance
 */

// src/store/useFilters.js
/**
 * OBJECTIF: Gestion filtres dashboard (année, mois, segment, etc)
 * STATE: { filters, setFilters, resetFilters }
 * SYNC: Synchronisé avec URL query params
 */

// src/store/useTheme.js
/**
 * OBJECTIF: Gestion thème (clair/sombre)
 * STATE: { theme, toggleTheme }
 * STOCKAGE: localStorage
 */

// src/store/useSidebar.js
/**
 * OBJECTIF: Gestion état sidebar (ouvert/fermé)
 * STATE: { isOpen, toggle }
 */

// src/store/useParametres.js
/**
 * OBJECTIF: Gestion paramètres configuration
 * STATE: { params, updateParam }
 */
```

### Stack Technologique Frontend

```json
{
  "@tanstack/react-router": "^1.168.0",     // Routeur
  "@tanstack/react-query": "^5.83.0",       // Gestion données/cache
  "@tanstack/react-table": "^8.21.3",       // Tableau avancé
  "@radix-ui/react-*": "Composants UI sans style",
  "@tailwindcss/vite": "^4.2.1",            // CSS utility-first
  "recharts": "Graphiques/charts"           // (inféré depuis ChartCard)
}
```

### Pages principales

#### Page: `src/routes/login.jsx`
```
Formulaire authentification
  ├─ Champ email
  ├─ Champ password
  ├─ Bouton submit
  └─ Lien registration (optionnel)

FLOW:
1. Utilisateur entre credentials
2. Appel POST /api/login
3. Stocker token JWT en localStorage
4. Rediriger vers dashboard

PROTECTION: ProtectedRoute.jsx
```

#### Page: `src/routes/dashboard/finance.jsx`
```
Dashboard Finance
  ├─ Header (breadcrumb, titre)
  ├─ FiltersBar (année, mois, segment)
  ├─ KPI Cards
  │  ├─ CA (Chiffre d'Affaires)
  │  ├─ Encours
  │  ├─ Délai paiement moyen
  │  └─ Clients actifs
  └─ Charts
     ├─ CA par mois (LineChart)
     ├─ CA par segment (BarChart)
     └─ Distribution encours (PieChart)

DATA SOURCE:
- /api/kpi/ca?year=2024&month=1&segment=...
- /api/kpi/encours?...
- /api/charts/ca-trend?...
```

#### Page: `src/routes/dashboard/predictions.jsx`
```
Prédictions ML - CA Forecast
  ├─ Header
  ├─ Bouton "Lancer Prédiction"
  ├─ Status (Loading, Success, Error)
  ├─ Selector Modèle (ARIMA, SARIMA, PROPHET)
  └─ ChartCard
     ├─ Historique CA (courbe grise)
     ├─ Prévision (ligne colorée par modèle)
     └─ Intervales de confiance (zone ombragée)

API CALLS:
- POST /api/ml/run → Lancer prédictions en arrière-plan
- GET /api/ml/status → Vérifier si en cours
- GET /api/ml/forecast?model=PROPHET → Récupérer résultats
```

---

## Patterns et Bonnes Pratiques

### 1. Pattern: Database Abstraction

**Problème**: Éviter coupler requêtes SQL au reste du code

**Solution**: Wrapper les appels DB
```python
# ❌ À ÉVITER
def get_clients(year):
    with engine.connect() as conn:
        return conn.execute(text(...)).fetchall()

# ✅ À FAIRE
def _rows(sql, params=None):
    """Abstraction centralisée"""
    with DW_ENGINE.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchall()

def get_clients(year):
    return _rows("SELECT * FROM DIM_CLIENT WHERE year = :year", {"year": year})
```

### 2. Pattern: Error Handling

**Chaque fonction doit gérer ses erreurs**:
```python
def _rows(sql, params=None):
    try:
        with DW_ENGINE.connect() as conn:
            return conn.execute(text(sql), params or {}).fetchall()
    except SQLAlchemyError as exc:
        logging.error(f"Database error: {exc}")
        return []  # Retourner valeur safe au lieu de lever
```

### 3. Pattern: Logging

**Format standard**: `[MODULE] message`
```python
logger.info(f"[DIM_DATE] Loaded {len(df)} rows")
logger.warning(f"[ETL] No data found for {table_name}")
logger.error(f"[API] Database connection failed: {exc}")
```

### 4. Pattern: Data Transformation

**Toujours copier le DataFrame**:
```python
def transform_dim_date(df):
    df = df.copy()  # ← Important! Éviter mutations
    df["jour"] = df["date_val"].dt.day
    return df
```

### 5. Pattern: Lookup Tables

**Créer mapping natural_key → surrogate_key**:
```python
lookups["DIM_DATE"] = _build_lookup("DIM_DATE", "date_val", "id_date")
# Résultat: {date(2024,1,1): 1, date(2024,1,2): 2, ...}

# Utiliser pour enrichissement
fact_df["id_date"] = fact_df["date_val"].map(lookups["DIM_DATE"])
```

### 6. Pattern: Thread Safety

**Utiliser verrous pour opérations longues**:
```python
_ETL_RUN_LOCK = threading.Lock()

def run_etl_background():
    if not _ETL_RUN_LOCK.acquire(blocking=False):
        return False  # Déjà en cours
    
    try:
        # Opération longue
        run_pipeline()
    finally:
        _ETL_RUN_LOCK.release()
```

### 7. Pattern: Fallback Graceful

**Toujours avoir plan B si composant échoue**:
```python
def _forecast_with_fallback(df, horizon):
    try:
        return _forecast_prophet(df, horizon)
    except Exception:
        logger.warning("PROPHET failed, using fallback")
        return _forecast_seasonal_fallback(df, horizon, "PROPHET_FALLBACK")
```

### 8. Pattern: Configuration Externe

**Tous les paramètres en variables d'environnement**:
```python
# ✅ À FAIRE
ETL_LOG_LEVEL = os.getenv("ETL_LOG_LEVEL", "INFO")

# ❌ À ÉVITER
ETL_LOG_LEVEL = "INFO"  # Hardcoded, inflexible
```

---

## Checklist Maîtrise pour Soutenance

### Concepts clés à mémoriser

**ETL**:
- [ ] 3 étapes: Extract, Transform, Load
- [ ] Dimensions vs Faits
- [ ] Lookups (natural_key → surrogate_key)
- [ ] Pipeline complet en `pipeline.py`

**Modèles ML**:
- [ ] 3 modèles: ARIMA, SARIMA, PROPHET
- [ ] Données d'entrée: CA mensuel historique
- [ ] Sorties: yhat (prévision), yhat_lower, yhat_upper (intervales)
- [ ] Fallback si modèle échoue

**Backend API**:
- [ ] FastAPI + CORS
- [ ] Middleware logging
- [ ] Fonctions `_rows()` et `_row()` pour DB
- [ ] Endpoints pour frontend

**Frontend**:
- [ ] React + TanStack Router
- [ ] Hooks personnalisés (useAuth, useFilters, etc)
- [ ] Zustand pour state management
- [ ] Radix UI + Tailwind CSS

### Questions possibles du jury

1. **"Explique-moi le pipeline ETL"**
   → Décrire Extract → Transform → Load avec exemples

2. **"Pourquoi 3 modèles ML?"**
   → Ensemble voting pour robustesse. ARIMA simple, SARIMA + saisonalité, PROPHET robuste

3. **"Comment gères-tu les erreurs?"**
   → Try/except, logging, fallback graceful (ici: seasonal decomposition)

4. **"Réécris la fonction _build_lookup()"**
   → SELECT surrogate_col, natural_col FROM table; zip() en dict

5. **"Explique le middleware logging"**
   → Intercepte chaque requête HTTP, log timestamp + méthode + URL + status

6. **"Comment fait le frontend pour afficher les prédictions?"**
   → GET /api/ml/forecast → afficher avec recharts, zones de confiance ombragées

---

## Ressources Rapides

### Imports courants
```python
# Backend
from fastapi import FastAPI
from sqlalchemy import text, create_engine
import pandas as pd
import logging

# ETL
from etl.config import DW_ENGINE, MAG_ENGINE, GRT_ENGINE
from etl.utils.logger import get_logger
from etl import extract, transform, load

# ML
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from prophet import Prophet
```

### Commandes utiles
```bash
# Lancer ETL
python -m etl.pipeline

# Lancer API
uvicorn dashboard.backend.api.queries:app --reload

# Lancer Frontend (dev)
npm run dev

# Lancer prédictions ML
python -m dashboard.backend.ml.runner

# Logs
tail -f etl_run.log
```

---

## Conclusion

Vous maîtrisez maintenant:
✅ Architecture globale du projet FINMAG
✅ Pipeline ETL complet (Extract → Transform → Load)
✅ Modèles ML (ARIMA, SARIMA, PROPHET)
✅ Backend API (FastAPI, DB abstraction)
✅ Frontend React (Router, Hooks, Components)
✅ Patterns et bonnes pratiques
✅ Comment réécrire n'importe quel bloc de code

**Conseil pour la soutenance**: 
- Parlez lentement en expliquant chaque étape
- Utilisez des diagrammes/pseudo-code pour illustrer
- Montrez les fichiers et pointed du doigt les sections pertinentes
- Si jury demande bloc: Pseudo-code d'abord, puis code détaillé
