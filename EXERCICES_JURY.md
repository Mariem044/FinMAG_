# 🎯 EXERCICES PRATIQUES & SCÉNARIOS JURY - FINMAG

## Objectif
Ce document contient des exercices que vous devez pouvoir réécrire instantanément pendant la soutenance si le jury demande.

---

## 1️⃣ EXERCICE: Réécris `_build_lookup()`

### Scenario Jury
> "Tu as une fonction qui crée des mappings pour tes dimensions. Réécris-moi `_build_lookup()` du zéro."

### Solution attendue

**Pseudo-code d'abord:**
```
1. Écrire requête: SELECT [surrogate_col], [natural_col] FROM [table_name]
2. Lire le résultat dans un DataFrame pandas
3. Si c'est DIM_DATE: convertir natural_col en date (pas datetime)
4. Créer dict en zippant natural_col values avec surrogate_col values
5. Retourner le dict
```

**Code complet:**
```python
def _build_lookup(table_name, natural_col, surrogate_col):
    """
    Construit un dictionnaire: natural_key → surrogate_key
    
    Args:
        table_name: Nom table (ex: "DIM_DATE")
        natural_col: Colonne clé métier (ex: "date_val")
        surrogate_col: Colonne ID technique (ex: "id_date")
    
    Returns:
        dict: {clé_métier: id_technique, ...}
    """
    # Étape 1: Requête SELECT
    query = f"SELECT [{surrogate_col}], [{natural_col}] FROM [{table_name}]"
    
    # Étape 2: Lire en DataFrame
    df = pd.read_sql(query, DW_ENGINE)
    
    # Étape 3: Convertir DIM_DATE (dates, pas datetimes)
    if table_name == "DIM_DATE" and not df.empty:
        df[natural_col] = pd.to_datetime(df[natural_col]).dt.date
    
    # Étape 4-5: Créer et retourner dict
    return dict(zip(df[natural_col], df[surrogate_col]))
```

### Usage
```python
lookups["DIM_DATE"] = _build_lookup("DIM_DATE", "date_val", "id_date")
# Résultat: {date(2024,1,1): 1, date(2024,1,2): 2, ...}

# Plus tard dans le code:
fact_df["id_date"] = fact_df["date_val"].map(lookups["DIM_DATE"])
```

---

## 2️⃣ EXERCICE: Réécris la fonction `_rows()`

### Scenario Jury
> "Comment tu requêtes la base de données dans ton API? Réécris le wrapper de requête SQL."

### Solution attendue

**Pseudo-code:**
```
1. Vérifier si ETL est en cours d'exécution (si verrou bloqué)
   → Si oui: retourner liste vide (éviter deadlock)
2. Ouvrir connexion à DW_ENGINE
3. Exécuter requête SQL avec paramètres
4. Récupérer TOUTES les lignes (fetchall)
5. Si erreur SQLAlchemy: logger + retourner []
6. Retourner les lignes
```

**Code complet:**
```python
def _rows(sql, params=None):
    """
    Exécute une requête SQL en lecture et retourne TOUTES les lignes.
    
    Args:
        sql: Requête SQL (peut contenir placeholders :param_name)
        params: Dict de paramètres (ex: {"year": 2024})
    
    Returns:
        list: Toutes les lignes retournées (vide si erreur ou ETL en cours)
    """
    # Étape 1: Vérifier si ETL bloque DB
    if _ETL_RUN_LOCK.locked():
        return []
    
    # Étape 2-4: Requête
    try:
        with DW_ENGINE.connect() as conn:
            result = conn.execute(text(sql), params or {})
            return result.fetchall()
    # Étape 5: Gestion erreur
    except SQLAlchemyError as exc:
        logging.error(f"Database query error in _rows: {exc}")
        return []
```

### Usage
```python
# Sans paramètres
rows = _rows("SELECT * FROM DIM_CLIENT")

# Avec paramètres
rows = _rows(
    "SELECT * FROM FAIT_LIGNES_VENTE WHERE annee = :year",
    {"year": 2024}
)

# Traiter résultats
for row in rows:
    print(row.client_id, row.nom_client)
```

---

## 3️⃣ EXERCICE: Réécris `transform_dim_date()`

### Scenario Jury
> "Explique-moi comment tu construis une dimension calendrier. Je veux le code."

### Solution attendue

**Pseudo-code:**
```
ENTRÉE: DataFrame avec colonne 'date_val' (datetime)

SORTIES (colonnes à ajouter):
- jour: 1-31
- mois: 1-12
- trimestre: 1-4
- semestre: 1-2
- annee: 2018-2025
- semaine: 1-53 (ISO)
- jour_semaine: 0-6 (lundi=0)
- est_weekend: 0/1
- est_ferie: 0/1
- exercice: =annee

LOGIQUE:
1. Copier le DF (ne pas muter l'original)
2. Convertir date_val en datetime
3. Extraire jour, mois, année
4. Calculer trimestre = (mois-1)//3 + 1
5. Calculer semestre = 1 si mois <= 6 else 2
6. Extraire numéro semaine ISO
7. Extraire jour semaine (0=lundi, 6=dimanche)
8. Marquer weekend si jour_semaine >= 5
9. Initialiser est_ferie à 0
10. Copier année dans exercice
```

**Code complet:**
```python
def transform_dim_date(df):
    """
    Ajoute les colonnes calendrier à un DataFrame de dates.
    
    Args:
        df: DataFrame avec colonne 'date_val'
    
    Returns:
        DataFrame enrichi avec colonnes calendrier
    """
    # Étape 1: Copier (important!)
    df = df.copy()
    
    # Étape 2: Convertir en datetime
    df["date_val"] = pd.to_datetime(df["date_val"])
    
    # Étape 3-4: jour, mois, année, trimestre
    df["jour"] = df["date_val"].dt.day.astype("int16")
    df["mois"] = df["date_val"].dt.month.astype("int16")
    df["annee"] = df["date_val"].dt.year.astype("int16")
    df["trimestre"] = df["date_val"].dt.quarter.astype("int16")
    
    # Étape 5: Semestre
    df["semestre"] = df["mois"].apply(
        lambda m: 1 if m <= 6 else 2
    ).astype("int16")
    
    # Étape 6: Semaine ISO
    df["semaine"] = df["date_val"].dt.isocalendar().week.astype("int16")
    
    # Étape 7: Jour semaine
    df["jour_semaine"] = df["date_val"].dt.dayofweek.astype("int16")
    
    # Étape 8: Weekend (samedi=5, dimanche=6)
    df["est_weekend"] = df["jour_semaine"].apply(
        lambda d: 1 if d >= 5 else 0
    ).astype("int16")
    
    # Étape 9: Jour férié (à enrichir après)
    df["est_ferie"] = 0
    
    # Étape 10: Exercice
    df["exercice"] = df["annee"]
    
    return df
```

### Validation
```python
# Test
date_range = pd.date_range("2024-01-01", periods=5, freq="D")
df = pd.DataFrame({"date_val": date_range})
df_transformed = transform_dim_date(df)

# Vérifier
print(df_transformed[["date_val", "jour", "mois", "annee", "est_weekend"]])
```

---

## 4️⃣ EXERCICE: Écris le middleware de logging FastAPI

### Scenario Jury
> "Comment tu traces les requêtes HTTP? Montre-moi le middleware de logging."

### Solution attendue

**Pseudo-code:**
```
Pour chaque requête:
1. Noter le timestamp ISO
2. Extraire méthode HTTP et URL
3. Si REQUEST_LOG_FILE configuré:
   → Écrire dans fichier: "timestamp METHOD URL"
4. Sinon:
   → Loger en console
5. Appeler le next handler
6. Loger le status code de la réponse
7. Retourner la réponse
```

**Code complet:**
```python
@app.middleware("http")
async def log_requests(request, call_next):
    """
    Middleware qui log chaque requête HTTP.
    """
    # Étape 1-2: Timestamp et URL
    url = str(request.url)
    timestamp = datetime.now().isoformat()
    
    # Étape 3-4: Écrire ou loger
    if REQUEST_LOG_FILE:
        try:
            log_path = os.path.abspath(REQUEST_LOG_FILE)
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} {request.method} {url}\n")
        except OSError as exc:
            logger.warning(
                "Could not write request log to %s: %s",
                REQUEST_LOG_FILE,
                exc
            )
    else:
        logger.info("Incoming request: %s %s", request.method, url)
    
    # Étape 5: Appeler next
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled error while processing request %s %s",
            request.method,
            url
        )
        raise
    
    # Étape 6: Loger response
    logger.info(
        "Request completed: %s %s %s",
        request.method,
        url,
        response.status_code
    )
    
    # Étape 7: Retourner
    return response
```

---

## 5️⃣ EXERCICE: Réécris `load_dimension()`

### Scenario Jury
> "Explique comment tu charges les données du DataFrame vers la base. Code complet."

### Solution attendue

**Pseudo-code:**
```
ENTRÉE: DataFrame + nom table cible

ÉTAPES:
1. Si DataFrame vide → quit early (rien à charger)
2. Récupérer liste colonnes qui existent en DB
3. Filtrer DataFrame pour garder que les colonnes valides
4. Si ETL_ALLOW_TABLE_DELETE=true:
   → Exécuter DELETE FROM table
5. Sinon:
   → Log warning (APPEND mode, données anciennes restent)
6. INSERT les nouvelles données avec .to_sql()
7. Loger nombre de lignes chargées
```

**Code complet:**
```python
def load_dimension(df, table):
    """
    Charge une dimension dans le Data Warehouse.
    
    Args:
        df: DataFrame à charger
        table: Nom de la table cible
    """
    # Étape 1: Vérifier pas vide
    if df.empty:
        logger.info(f"[{table}] DataFrame vide, rien à charger.")
        return
    
    # Étape 2-3: Valider colonnes
    target_cols = get_table_columns(table)
    valid_cols = [c for c in df.columns if c in target_cols]
    df_clean = df[valid_cols].copy()
    
    # Étape 4-5: DELETE ou APPEND
    if ALLOW_TABLE_DELETE:
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"DELETE FROM [{table}]"))
    else:
        logger.warning(
            "[%s] ETL_ALLOW_TABLE_DELETE disabled; "
            "%s rows will be appended",
            table,
            len(df_clean),
        )
    
    # Étape 6: INSERT
    df_clean.to_sql(table, DW_ENGINE, if_exists="append", index=False)
    
    # Étape 7: Loger
    logger.info(f"[{table}] {len(df_clean)} lignes chargées.")
```

---

## 6️⃣ EXERCICE: Explique & réécris le fallback ML

### Scenario Jury
> "Que fais-tu si ARIMA échoue? Comment tu garantis une prévision?"

### Solution attendue

**Explication:**
> "J'utilise un fallback basé sur décomposition saisonnière simple. C'est plus robuste que les modèles statistiques complexes si les données sont bruitées ou peu nombreuses."

**Pseudo-code du fallback:**
```
ENTRÉE: df (historique), horizon (nb mois à prévoir)

ÉTAPES:

1. FIT TENDANCE LINÉAIRE:
   - t = indices (0, 1, 2, ...)
   - Polyfit degré 1: y = alpha*t + beta
   - trend = alpha*t + beta

2. CALCULER SAISONNALITÉ:
   - seasonal_ratios = y / trend (pour chaque mois)
   - Grouper par mois, moyenner les ratios
   - Remplir mois manquants avec 1.0
   - Normaliser (moyenne ratios = 1.0)

3. GÉNÉRER PRÉVISIONS:
   - Créer dates futures (horizon mois)
   - Pour chaque mois futur:
     yhat = trend_future * seasonal_ratio[month]

4. INTERVALES DE CONFIANCE:
   - Calculer résidus = y_réel - y_trend*seasonality
   - std_err = écart type des résidus
   - yhat_lower = yhat - 1.28 * std_err  (80% CI)
   - yhat_upper = yhat + 1.28 * std_err

5. POST-TRAITEMENT:
   - Clipper valeurs >= 0 (pas de CA négatif!)
   - Retourner avec colonnes: ds, yhat, yhat_lower, yhat_upper, is_historical
```

**Code complet (résumé):**
```python
def _forecast_seasonal_fallback(df, horizon, model_name):
    """Prévision par décomposition saisonnière (fallback)."""
    
    # Étape 1: Tendance linéaire
    t = np.arange(len(df))
    y = df["y"].values.astype(float)
    alpha, beta = np.polyfit(t, y, 1) if len(df) >= 2 else (0.0, float(y[0]))
    trend = alpha * t + beta
    
    # Étape 2: Saisonnalité
    trend_safe = np.where(trend <= 0, 1e-5, trend)
    seasonal_ratios = y / trend_safe
    
    df_temp = df.copy()
    df_temp["ratio"] = seasonal_ratios
    df_temp["month"] = df_temp["ds"].dt.month
    
    # Moyenner par mois
    monthly_seasonality = df_temp.groupby("month")["ratio"].mean().to_dict()
    
    # Remplir mois manquants
    for m in range(1, 13):
        if m not in monthly_seasonality:
            monthly_seasonality[m] = 1.0
    
    # Normaliser
    mean_ratio = np.mean(list(monthly_seasonality.values()))
    if mean_ratio > 0:
        for m in monthly_seasonality:
            monthly_seasonality[m] /= mean_ratio
    
    # Étape 3: Générer prévisions futures
    last_ds = df["ds"].max()
    future_dates = [last_ds + pd.DateOffset(months=i) for i in range(1, horizon + 1)]
    future_df = pd.DataFrame({"ds": future_dates})
    
    full_df = pd.concat([df, future_df], ignore_index=True)
    full_df["t"] = np.arange(len(full_df))
    full_df["month"] = full_df["ds"].dt.month
    
    pred_trend = alpha * full_df["t"].values + beta
    full_df["yhat"] = pred_trend * full_df["month"].map(monthly_seasonality)
    
    # Étape 4: Intervales confiance
    residuals = y - (trend * df_temp["month"].map(monthly_seasonality))
    std_err = np.std(residuals) if len(residuals) > 1 else 0.1 * np.mean(y)
    
    full_df["yhat_lower"] = full_df["yhat"] - 1.28 * std_err
    full_df["yhat_upper"] = full_df["yhat"] + 1.28 * std_err
    
    # Marquer historique vs prévision
    full_df["is_historical"] = (full_df["ds"] <= df["ds"].max()).astype(int)
    
    # Étape 5: Post-traitement
    result = full_df[["ds", "yhat", "yhat_lower", "yhat_upper", "is_historical"]].copy()
    result["yhat"] = result["yhat"].clip(lower=0)
    result["yhat_lower"] = result["yhat_lower"].clip(lower=0)
    result["yhat_upper"] = result["yhat_upper"].clip(lower=0)
    result["model_name"] = model_name
    
    return result
```

---

## 7️⃣ EXERCICE: Architecture ETL - Dessine & explique

### Scenario Jury
> "Dessine-moi l'architecture complète du pipeline ETL. Quelles sont les étapes?"

### Solution attendue

**Diagramme à dessiner:**
```
    ┌─────────────────────────────────────────────┐
    │   SOURCES DE DONNÉES                        │
    │  ├─ MAG (Magasin/Stock)                    │
    │  ├─ GRT (Gestion Règlements)               │
    │  └─ SAG (Comptabilité/Stock/Achats)        │
    └─────────────────────┬───────────────────────┘
                          ↓
    ┌─────────────────────────────────────────────┐
    │   1. EXTRACT (etl/extract.py)               │
    │   Lire données brutes via SQL               │
    │   → DataFrames pandas                       │
    └─────────────────────┬───────────────────────┘
                          ↓
    ┌─────────────────────────────────────────────┐
    │   2. TRANSFORM (etl/transform.py)           │
    │   Normaliser, enrichir, calculer            │
    │   → DataFrames transformés                  │
    └─────────────────────┬───────────────────────┘
                          ↓
    ┌─────────────────────────────────────────────┐
    │   3. LOAD (etl/load.py)                     │
    │   INSERT dans Data Warehouse                │
    │   → DELETE (full) ou APPEND (incremental)   │
    └─────────────────────┬───────────────────────┘
                          ↓
    ┌─────────────────────────────────────────────┐
    │   4. KPI & POST-TRAITEMENT (pipeline.py)    │
    │   Calculer métriques métier                 │
    │   → Tables KPI (ML_KPI*, RAPPORT_*)         │
    └─────────────────────┬───────────────────────┘
                          ↓
    ┌─────────────────────────────────────────────┐
    │   DATA WAREHOUSE                            │
    │  ├─ Dimensions (DIM_CLIENT, DIM_DATE, ...)  │
    │  ├─ Faits (FAIT_LIGNES_VENTE, ...)          │
    │  ├─ KPIs (ML_KPI05_CA_FORECAST)             │
    │  └─ Audit (ETL_AUDIT)                       │
    └─────────────────────┬───────────────────────┘
                          ↓
    ┌─────────────────────────────────────────────┐
    │   CONSOMMATEURS                             │
    │  ├─ API/Backend (requêtes KPI)              │
    │  ├─ ML/Models (prévisions)                  │
    │  └─ Frontend (Dashboard React)              │
    └─────────────────────────────────────────────┘
```

**Explication à donner:**

1. **EXTRACT**: Récupère données brutes des 3 sources SQL
2. **TRANSFORM**: Normalise, crée lookups, enrichit données
3. **LOAD**: Insère dans tables DW
4. **KPI**: Calcule métriques métier complexes
5. **Résultat**: Data Warehouse propre, documenté, auditalisé

**Ordonancement:**
- Dimensions en premier (parents)
- Faits ensuite (enfants, utilisent lookups dimensions)
- KPIs et rapports derniers

---

## 8️⃣ EXERCICE: Approche problème - "ETL en erreur"

### Scenario Jury
> "L'ETL a planté avec erreur 'Duplicate key' sur DIM_DATE. Qu'est-ce que tu vérifies?"

### Réponse attendue

**Checklist diagnostic:**

1. **Vérifier données source:**
   ```sql
   SELECT COUNT(*), COUNT(DISTINCT date_val)
   FROM (SELECT DATEFROMPARTS(annee, mois, 1) AS date_val FROM ...) src
   ```
   → Si COUNT < COUNT DISTINCT → doublon dans source

2. **Vérifier transform:**
   ```python
   df_date_src = extract_dim_date()  # Mock source
   df_date_transformed = transform_dim_date(df_date_src)
   assert df_date_transformed["date_val"].is_unique, "Doublons après transform!"
   ```

3. **Vérifier state de la table DIM_DATE:**
   ```sql
   SELECT COUNT(*), COUNT(DISTINCT date_val) FROM DIM_DATE
   ```

4. **Solution possible:**
   ```python
   # Si doublons dans source:
   df = df.drop_duplicates(subset=["date_val"])
   
   # Si table existante:
   ALLOW_TABLE_DELETE=true  # Force full reload
   ```

5. **Vérifier logs:**
   ```bash
   tail -f etl_run.log
   ```

---

## 9️⃣ EXERCICE: Performance - "Le pipeline est lent"

### Scenario Jury
> "L'ETL prend 2 heures maintenant. Qu'est-ce que tu optimises en priorité?"

### Réponse attendue

**À vérifier (par ordre):**

1. **Index manquants:**
   ```sql
   -- Vérifier indexes sur clés de jointure
   SELECT * FROM FAIT_LIGNES_VENTE WHERE id_date = ? (doit être rapide)
   
   -- Créer si manquant
   CREATE INDEX idx_fact_id_date ON FAIT_LIGNES_VENTE(id_date)
   ```

2. **Requêtes lentes:**
   ```python
   # Ajouter LIMIT avant transformation
   df = pd.read_sql(sql, DW_ENGINE, chunksize=10000)  # Loader par chunks
   ```

3. **Transformations inefficaces:**
   ```python
   # ❌ Lent: Apply sur chaque ligne
   df["trimestre"] = df["mois"].apply(lambda m: (m-1)//3 + 1)
   
   # ✅ Rapide: Vectorisé
   df["trimestre"] = (df["mois"] - 1) // 3 + 1
   ```

4. **Lookups inefficaces:**
   ```python
   # ❌ Lent: Boucle + lookup dict pour chaque ligne
   for idx, row in df.iterrows():
       df.at[idx, "id_date"] = lookups["DIM_DATE"].get(row["date_val"])
   
   # ✅ Rapide: Vectorisé avec .map()
   df["id_date"] = df["date_val"].map(lookups["DIM_DATE"])
   ```

5. **Paralléliser si possible:**
   ```python
   # Traiter dimensions en parallèle
   from concurrent.futures import ThreadPoolExecutor
   
   with ThreadPoolExecutor(max_workers=4) as executor:
       futures = [
           executor.submit(extract.extract_dim_date),
           executor.submit(extract.extract_dim_client),
           executor.submit(extract.extract_dim_segment),
       ]
       df_date, df_client, df_segment = [f.result() for f in futures]
   ```

---

## 🔟 EXERCICE: Tester ton code - Écris un test unitaire

### Scenario Jury
> "Montre-moi comment tu testes _build_lookup(). Code complet."

### Solution attendue

```python
import pytest
import pandas as pd
from etl.config import DW_ENGINE
from etl.pipeline import _build_lookup

class TestBuildLookup:
    """Tests pour _build_lookup()"""
    
    def test_build_lookup_basic(self):
        """Vérifier que lookup crée dict correct"""
        # SETUP: Insérer données test
        df_test = pd.DataFrame({
            "id_date": [1, 2, 3],
            "date_val": ["2024-01-01", "2024-01-02", "2024-01-03"]
        })
        df_test.to_sql("DIM_DATE_TEST", DW_ENGINE, if_exists="replace", index=False)
        
        # EXECUTE
        lookup = _build_lookup("DIM_DATE_TEST", "date_val", "id_date")
        
        # ASSERT
        assert isinstance(lookup, dict)
        assert len(lookup) == 3
        assert lookup[pd.to_datetime("2024-01-01").date()] == 1
        assert lookup[pd.to_datetime("2024-01-02").date()] == 2
        
        # CLEANUP
        DW_ENGINE.execute(text("DROP TABLE DIM_DATE_TEST"))
    
    def test_build_lookup_date_conversion(self):
        """Vérifier que DIM_DATE convertit en date (pas datetime)"""
        # ... setup ...
        lookup = _build_lookup("DIM_DATE", "date_val", "id_date")
        
        # Vérifier clés sont des date, pas datetime
        for key in lookup.keys():
            assert isinstance(key, datetime.date)
            assert not isinstance(key, datetime.datetime)
    
    def test_build_lookup_empty_table(self):
        """Vérifier que tableau vide retourne dict vide"""
        # ... setup avec table vide ...
        lookup = _build_lookup("DIM_EMPTY", "col1", "col2")
        assert lookup == {}

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**À exécuter:**
```bash
pytest tests/test_pipeline.py::TestBuildLookup -v
```

---

## 1️⃣1️⃣ QUESTIONS-RÉPONSES JURY COURANTES

### Q1: "Pourquoi 3 modèles ML?"
**Réponse:**
> "Ensemble voting pour robustesse. ARIMA/SARIMA sont sensibles aux paramètres (p,d,q). PROPHET est plus adaptable mais peut surfiage. En prenant les 3, on améliore la confiance. Et si tous échouent, le fallback (décomposition saisonnière) garantit une prévision."

### Q2: "Qu'est-ce qui peut casser ton application?"
**Réponse:**
> "1) Base de données inaccessible (timeout, mauvais credentials)
> 2) ETL qui prend trop long et bloque les requêtes API (d'où les verrous)
> 3) Données manquantes ou malformées (d'où validation)
> 4) Modèles ML qui échouent (d'où fallback)
> 5) Frontend vs Backend mismatch (d'où CORS)"

### Q3: "Comment tu gères la sécurité?"
**Réponse:**
> "1) Credentials en variables d'environnement (jamais hardcoded)
> 2) CORS restreint en production (env CORS_ALLOW_ORIGINS)
> 3) Connexions SQLAlchemy avec connection pooling
> 4) Logs d'audit pour traçabilité
> 5) Erreurs loggées sans exposer détails sensibles"

### Q4: "Comment tu sais que l'ETL a réussi?"
**Réponse:**
> "Audit table ETL_AUDIT:
> - Chaque run génère un run_id
> - On trace: table_name, nblignes, durée, status (RUNNING→SUCCESS/ERROR)
> - Status query en fin: SELECT MAX(run_date) WHERE status='SUCCESS'"

### Q5: "Peux-tu supporter 1M de lignes?"
**Réponse:**
> "Oui, avec optimisations:
> 1) Chunked loading: pd.read_sql(..., chunksize=100000)
> 2) Indexes sur clés de jointure
> 3) Vectorization pandas (pas de .apply() sur chaque ligne)
> 4) Parallélisation extraction dimensions
> 5) Incremental loads (delta) plutôt que full"

---

## 1️⃣2️⃣ FEUILLE PENSE-BÊTE RAPIDE

### Commandes clés
```bash
# Lancer ETL
python -m etl.pipeline

# Lancer API
cd dashboard && uvicorn backend.api.queries:app --reload

# Lancer frontend
cd dashboard/frontend && npm run dev

# Lancer ML
python -c "from dashboard.backend.ml import runner; runner.run_all_background()"

# Voir logs
tail -100f etl_run.log

# Vérifier DB connexion
python -c "from etl.config import DW_ENGINE; print(DW_ENGINE.execute('SELECT 1'))"
```

### Imports critiques
```python
# Configuration
from etl.config import DW_ENGINE, MAG_ENGINE, GRT_ENGINE, get_required_env

# Logging
from etl.utils.logger import get_logger
logger = get_logger(__name__)

# Audit
from etl.utils.audit import start_run, complete_run

# Pandas & SQL
import pandas as pd
from sqlalchemy import text

# ML
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from prophet import Prophet
```

### Variables d'environnement critiques
```bash
# Base de données
DW_CONNECTION_STRING=mssql+pyodbc://...
MAG_CONNECTION_STRING=mssql+pyodbc://...
GRT_CONNECTION_STRING=mssql+pyodbc://...

# Logging
ETL_LOG_LEVEL=INFO
ETL_LOG_FILE=etl_run.log
REQUEST_LOG_FILE=request_log.txt

# ETL
ETL_ALLOW_TABLE_DELETE=true
ETL_DROP_EXISTING=false

# API
APP_ENV=production
CORS_ALLOW_ORIGINS=https://dashboard.com,https://app.com

# ML
ML_FORECAST_HORIZON=12  # Mois à prévoir
```

---

## Conclusion

Vous êtes maintenant prêt(e) pour la soutenance!

✅ Vous pouvez réécrire n'importe quel bloc
✅ Vous avez des réponses aux questions courantes
✅ Vous comprenez l'architecture complète
✅ Vous savez déboguer les problèmes

**Conseil final**: Pendant la soutenance, si une question vous bloque:
1. Respirez profondément
2. Dessinez un pseudo-code sur le tableau
3. Demandez une clarification si nécessaire
4. Écrivez le code étape par étape (pas tout d'un coup)

Bonne chance! 🚀
