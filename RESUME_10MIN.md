# ⚡ RÉSUMÉ 10 MIN PRE-SOUTENANCE - FINMAG

Lisez ceci 10 minutes avant votre présentation. Format ultra-condensé.

---

## 🎯 Message Principal en 30 secondes

**FINMAG c'est:**
- Pipeline ETL (Extract-Transform-Load) qui consolide données de 3 sources SQL
- Dashboard React affichant KPIs métier en temps réel
- 3 modèles ML (ARIMA, SARIMA, PROPHET) pour prévoir le Chiffre d'Affaires
- Architecture robuste avec gestion d'erreurs, logging d'audit, thread-safety

**Technos**: Python (FastAPI, pandas, SQLAlchemy) + React/TypeScript + SQL Server

---

## 🏗️ Architecture en 1 page

```
Sources (MAG, GRT, SAG)
         ↓
    ETL EXTRACT    (lire SQL brutes)
         ↓
    ETL TRANSFORM  (normaliser, enrichir)
         ↓
    ETL LOAD       (INSERT en DW)
         ↓
   DATA WAREHOUSE  (Dimensions + Faits)
    ↙       ↙       ↙
  API    ML(3 modèles)  Frontend
  ↓         ↓            ↓
  JSON  Prévisions    Dashboard visuel
```

---

## 📋 Les 5 fichiers clés à connaître

| Fichier | Rôle | Ligne clé |
|---------|------|-----------|
| `etl/pipeline.py` | Orchestre ETL complet | `run_pipeline()` lance tout |
| `etl/extract.py` | Lit données sources | `_read(engine, sql)` wrapper |
| `etl/transform.py` | Normalise données | `transform_dim_date()` exemple |
| `dashboard/backend/api/queries.py` | API endpoints | `_rows(sql)` requête DB |
| `dashboard/backend/ml/ca_forecast.py` | 3 modèles prévisions | `_load_monthly_ca()` charge données |

---

## ✅ 3 concepts à expliquer facilement

### 1. Lookups (natural_key → surrogate_key)
```python
lookups["DIM_DATE"] = _build_lookup("DIM_DATE", "date_val", "id_date")
# Résultat: {date(2024,1,1): 1, date(2024,1,2): 2, ...}

# Usage:
fact_df["id_date"] = fact_df["date_val"].map(lookups["DIM_DATE"])
```
**À dire**: "J'associe chaque date métier à un ID technique pour économiser espace et accélérer jointures."

### 2. Thread Safety
```python
_ETL_RUN_LOCK = threading.Lock()

# API vérifie
if _ETL_RUN_LOCK.locked():
    return []  # ETL en cours, ne requête pas
```
**À dire**: "Je protège l'ETL avec un verrou pour éviter que l'API requête une table en cours de modification."

### 3. ML Fallback
```python
try:
    return _forecast_arima(df, 12)
except Exception:
    return _forecast_seasonal_fallback(df, 12, "ARIMA")
```
**À dire**: "Si ARIMA échoue, j'utilise décomposition saisonnière simple comme fallback pour garantir une prévision."

---

## 🎤 Réponses clés du jury

**Q: "Explique l'ETL"**
> Extraction des 3 sources → Normalisation (cleaning, lookups) → Insertion en DW → Calcul KPIs

**Q: "Pourquoi 3 modèles ML?"**
> Robustesse: ARIMA simple, SARIMA + saisonalité, PROPHET robuste. Chacun a des points forts.

**Q: "Comment tu gères les erreurs?"**
> Try/except + logging + fallback graceful (ex: seasonal decomposition si ARIMA échoue)

**Q: "Thread safety?"**
> Verrous (locks) pour éviter races entre ETL et API. API vérifie si ETL bloqué avant requêter.

**Q: "Pourquoi lookups?"**
> Économiser espace (int vs string), accélérer jointures, permettre changements dimensions.

**Q: "Qu'est-ce qui peut casser?"**
> 1) DB inaccessible 2) ETL qui prend trop long 3) Données malformées 4) ML échoue (d'où fallback)

---

## 🔍 Si jury demande du code

**Fonction 1: `_build_lookup()`** - Créer mapping
```python
def _build_lookup(table_name, natural_col, surrogate_col):
    query = f"SELECT [{surrogate_col}], [{natural_col}] FROM [{table_name}]"
    df = pd.read_sql(query, DW_ENGINE)
    if table_name == "DIM_DATE" and not df.empty:
        df[natural_col] = pd.to_datetime(df[natural_col]).dt.date
    return dict(zip(df[natural_col], df[surrogate_col]))
```

**Fonction 2: `_rows()`** - Requête DB safe
```python
def _rows(sql, params=None):
    if _ETL_RUN_LOCK.locked():
        return []  # ETL en cours
    try:
        with DW_ENGINE.connect() as conn:
            return conn.execute(text(sql), params or {}).fetchall()
    except SQLAlchemyError as exc:
        logging.error(f"Database error: {exc}")
        return []
```

**Fonction 3: `load_dimension()`** - Charger table
```python
def load_dimension(df, table):
    if df.empty:
        return
    target_cols = get_table_columns(table)
    valid_cols = [c for c in df.columns if c in target_cols]
    df_clean = df[valid_cols].copy()
    
    if ALLOW_TABLE_DELETE:
        with DW_ENGINE.begin() as conn:
            conn.execute(text(f"DELETE FROM [{table}]"))
    
    df_clean.to_sql(table, DW_ENGINE, if_exists="append", index=False)
    logger.info(f"[{table}] {len(df_clean)} lignes chargées.")
```

---

## 📊 Schémas à redessiner en 1 min

### Star Schema
```
FAIT_LIGNES_VENTE
      ↙ ↓ ↓ ↓ ↓ ↘
DIM_DATE, CLIENT, SEGMENT, ARTICLE, VILLE
```

### ETL Steps
```
EXTRACT → TRANSFORM → LOAD → KPI
```

### ML Ensemble
```
ARIMA ↓
SARIMA ├→ Ensemble → Prévisions
PROPHET ↑
```

---

## 🚀 Commandes rapides

```bash
# Lancer ETL
python -m etl.pipeline

# Lancer API
cd dashboard && uvicorn backend.api.queries:app --reload

# Vérifier DB
python -c "from etl.config import DW_ENGINE; print(DW_ENGINE.execute('SELECT 1'))"

# Voir logs
tail -50f etl_run.log
```

---

## 💪 Derniers conseils

1. **Parlez lentement** - Expliquez chaque mot, n'allez pas trop vite
2. **Utilisez les documents** - Pointez du doigt les fichiers pendant présentation
3. **Pseudo-code d'abord** - Si jury demande code, donnez pseudo-code avant code réel
4. **Diagrammes** - Dessinez schémas pour illustrer (ex: star schema)
5. **Admettez si vous ne savez pas** - "Je vais vérifier" c'est mieux que inventer
6. **Montrez les logs** - Quand vous lancez ETL, montrez les logs qui prouvent ça marche
7. **Questions du jury** - Posez des questions si vous comprenez pas bien

---

## ✨ Points forts de votre projet

✅ Robustesse: Fallbacks graceful, error handling partout
✅ Performance: Vectorization pandas, indexes, chunked loading
✅ Maintenabilité: Code organisé, logging, configuration externe
✅ Scalabilité: Thread-safe, peut supporter 1M+ rows
✅ Documentation: Docstrings clairs, commentaires utiles
✅ Audit trail: ETL_AUDIT table trace tout

---

## 🎯 Dernier check (5 min avant)

- [ ] Je peux expliquer le flux complet (sources → ETL → DW → API → Frontend)
- [ ] Je peux réécris une fonction (lookup, rows, load)
- [ ] Je comprends pourquoi 3 modèles ML
- [ ] Je sais ce que c'est les lookups
- [ ] Je sais ce que c'est thread-safe
- [ ] Je peux dessiner star schema
- [ ] Je peux expliquer fallback ML
- [ ] Je peux dire 3 points clés du projet

Si oui partout ✅ → Vous êtes prêt!

---

## Ressources rapides

**Guide complet**: Voir GUIDE_MAITRISE_FINMAG.md
**Exercices pratiques**: Voir EXERCICES_JURY.md
**Schémas détaillés**: Voir SCHEMAS_VISUELS.md

Bonne chance! 🚀

*Rappel: Si jury coupe le code, c'est pas grave. Dites: "Je peux le terminer, c'est juste un..." et expliquez logique.*
