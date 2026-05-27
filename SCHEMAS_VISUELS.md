# 📊 SCHÉMAS VISUELS & DIAGRAMMES - FINMAG

Utilisez ces diagrammes pour visualiser et mémoriser l'architecture.

---

## 1. Flux de données complet

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FINMAG ARCHITECTURE COMPLÈTE                     │
└─────────────────────────────────────────────────────────────────────────┘

SOURCE DE DONNÉES (SQL Server)
  │
  ├── [MAG Database]     (Magasin/Stock/Achat)
  │   ├─ F_COMPTET       (Clients/Fournisseurs)
  │   ├─ F_ARTICLE       (Articles/Produits)
  │   ├─ P_CATTARIF      (Catégories tarifaires)
  │   └─ VENTES          (Lignes de vente)
  │
  ├── [GRT Database]     (Gestion Règlements)
  │   ├─ P_Ville         (Gouvernorats)
  │   ├─ P_ModeReglements (Modes de paiement)
  │   └─ REGLEMENTS      (Paiements clients)
  │
  └── [SAG Database]     (Comptabilité)
      └─ MOUVEMENTS_CAISSE

                        ↓↓↓ ETL PIPELINE ↓↓↓

┌──────────────────────────────────────────────────────────┐
│ EXTRACT                                                   │
│ ├─ read_sql(MAG_ENGINE, "SELECT ... FROM F_COMPTET") → df_client
│ ├─ read_sql(GRT_ENGINE, "SELECT ... FROM P_Ville") → df_ville
│ └─ read_sql(MAG_ENGINE, "SELECT ... FROM F_ARTICLE") → df_article
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│ TRANSFORM                                                 │
│ ├─ transform_dim_date(dates)       → colonnes calendrier
│ ├─ _clean_text_code("  Tunisia  ") → "TUNISIA"
│ ├─ _clean_bank_account("123-456")  → "123456"
│ └─ add_fact_reglements_calcs(df)   → délai_paiement, bucket
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│ LOAD                                                      │
│ ├─ _build_lookup("DIM_DATE", ...)  → {date: id_date}
│ ├─ DELETE FROM DIM_VILLE
│ ├─ INSERT INTO DIM_VILLE (df_ville)
│ └─ DELETE FROM FAIT_LIGNES_VENTE
│    INSERT INTO FAIT_LIGNES_VENTE (enriched_df)
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│ DATA WAREHOUSE (SQL Server - Lecture seule)              │
│                                                           │
│ DIMENSIONS:                                               │
│ ├─ DIM_DATE     (jour, mois, trimestre, annee, ...)    │
│ ├─ DIM_CLIENT   (id_client, nom, ville, segment, ...)  │
│ ├─ DIM_SEGMENT  (id_segment, libelle, prix)             │
│ ├─ DIM_VILLE    (id_ville, gouvernorat)                 │
│ ├─ DIM_ARTICLE  (id_article, designation, famille)     │
│ └─ ...autres dimensions...                               │
│                                                           │
│ FAITS:                                                    │
│ ├─ FAIT_LIGNES_VENTE (id_date, id_client, montant)      │
│ ├─ FAIT_REGLEMENTS   (id_date, id_client, delai_paiement)
│ ├─ FAIT_ENCOURS      (id_client, montant_encours)       │
│ └─ FAIT_MOUVEMENTS_CAISSE (...)                         │
│                                                           │
│ KPIs:                                                     │
│ ├─ ML_KPI05_CA_FORECAST (prévisions ARIMA/SARIMA/PROPHET)
│ └─ RAPPORT_* (rapports métier)                          │
│                                                           │
│ AUDIT:                                                    │
│ └─ ETL_AUDIT (run_id, table_name, status, nb_rows, ...) │
└──────────────────────────────────────────────────────────┘
        │              │                    │
        ↓              ↓                    ↓
   API Backend    ML Models          Frontend React
```

---

## 2. Pipeline ETL - Étapes détaillées

```
ÉTAPE 1: INITIALISATION
├─ load_dotenv()              (charger variables d'environnement)
├─ DW_ENGINE = create_engine(...) (connexion DW)
├─ logger = get_logger()      (setup logging)
└─ audit.start_run("full")    (marquer début dans ETL_AUDIT)
                ↓

ÉTAPE 2: CREATE TABLES (DDL)
├─ ddl.create_all_tables()
│  ├─ CREATE TABLE DIM_DATE    (si n'existe pas)
│  ├─ CREATE TABLE DIM_CLIENT
│  ├─ CREATE TABLE FAIT_LIGNES_VENTE
│  └─ ... créer toutes tables attendues
                ↓

ÉTAPE 3: CHARGER DIMENSIONS (Parents d'abord)
├─ A. DIM_DATE (Calendrier)
│  └─ pd.date_range(start, end, freq="D")
│     → transform_dim_date()
│     → load_dimension(df, "DIM_DATE")
│     → lookups["DIM_DATE"] = _build_lookup(...)
│
├─ B. Dimensions lookup (codes de référence)
│  ├─ DIM_SEGMENT (catégories tarifaires)
│  │  └─ extract_dim_segment() → transform → load → lookup
│  │
│  ├─ DIM_VILLE (gouvernorats)
│  │  └─ extract_dim_ville() → transform → load → lookup
│  │
│  ├─ DIM_CLIENT (clients consolidés)
│  │  ├─ extract_dim_client_mag()  (données MAG)
│  │  ├─ extract_dim_client_grt()  (données GRT)
│  │  ├─ merge sur clés naturelles
│  │  └─ load → lookup
│  │
│  └─ ... autres dimensions (SEGMENT, ARTICLE, FOURNISSEUR, etc)
│
                ↓

ÉTAPE 4: CHARGER FAITS (Enfants - utilisent lookups)
├─ Extraction données transactionnelles
│  ├─ extract_fact_lignes_vente()
│  ├─ extract_fact_reglements()
│  └─ extract_fact_encours()
│
├─ Transformation (enrichissement)
│  ├─ fact_df["id_date"] = fact_df["date_val"].map(lookups["DIM_DATE"])
│  ├─ fact_df["id_client"] = fact_df["CT_Num"].map(lookups["DIM_CLIENT"])
│  ├─ fact_df["id_segment"] = fact_df["segment"].map(lookups["DIM_SEGMENT"])
│  └─ add_fact_reglements_calcs()  (colonnes métier)
│
├─ Chargement
│  ├─ load_fact(df_ventes, "FAIT_LIGNES_VENTE")
│  ├─ load_fact(df_reglements, "FAIT_REGLEMENTS")
│  └─ load_fact(df_encours, "FAIT_ENCOURS")
│
                ↓

ÉTAPE 5: KPIs & POST-TRAITEMENT
├─ Calculs agrégés
│  ├─ SELECT SUM(montant) BY mois, segment → CA KPI
│  ├─ SELECT AVG(délai) BY client → délai paiement
│  └─ SELECT COUNT(*) BY ville → clients par région
│
├─ INSERT INTO tables rapports
│  └─ RAPPORT_CA, RAPPORT_ENCOURS, etc
│
                ↓

ÉTAPE 6: FINALISATION
├─ audit.complete_run(run_id, "SUCCESS")  (marquer fin)
├─ logger.info("ETL completed successfully")
└─ Exceptions → audit.complete_run(run_id, "ERROR", error_msg)
```

---

## 3. Modèles ML - Pipeline prévisions

```
┌────────────────────────────────────────────────────────┐
│     CHIFFRE D'AFFAIRES FORECAST (KPI-05)               │
└────────────────────────────────────────────────────────┘

INPUT: Historique mensuel du CA
──────────────────────────────────
SELECT
    DATEFROMPARTS(d.annee, d.mois, 1) AS ds,
    SUM(f.DL_MontantHT) AS y
FROM FAIT_LIGNES_VENTE f
JOIN DIM_DATE d ON ...
WHERE f.DO_Domaine = 0
GROUP BY d.annee, d.mois
HAVING COUNT(*) > 10

Résultat:
┌─────────────┬────────────┐
│ ds          │ y          │
├─────────────┼────────────┤
│ 2020-01-01  │ 150000.00  │
│ 2020-02-01  │ 175000.00  │
│ 2020-03-01  │ 165000.00  │
│ ...         │ ...        │
│ 2024-11-01  │ 210000.00  │
│ 2024-12-01  │ 225000.00  │
└─────────────┴────────────┘
(~60 observations mensuelles)

                    ↓

PROCESSUS: Entraîner 3 modèles en PARALLÈLE
─────────────────────────────────────────────

┌──────────────────┐
│  MODÈLE 1: ARIMA │
├──────────────────┤
│ Équation:        │
│ Yt = φ₁Yt₋₁ +    │
│      θ₁εt₋₁ + εt │
│                  │
│ Order: (p,d,q)   │
│ p: AR terms      │
│ d: differencing  │
│ q: MA terms      │
│                  │
│ Auto-ARIMA:      │
│ Grid search p,d,q
└──────────────────┘

┌──────────────────────┐
│ MODÈLE 2: SARIMA     │
├──────────────────────┤
│ Ajoute saisonnalité: │
│                      │
│ Order: (p,d,q)       │
│ Seasonal: (P,D,Q,m)  │
│ m = 12 (mois)        │
│                      │
│ Gère bonne les      │
│ patterns répétitifs  │
│ (ex: Noël = pic CA) │
└──────────────────────┘

┌──────────────────────┐
│ MODÈLE 3: PROPHET    │
├──────────────────────┤
│ Framework Facebook   │
│                      │
│ Composantes:         │
│ Y(t) = Trend +       │
│        Seasonality + │
│        Holidays +    │
│        Error         │
│                      │
│ Avantages:           │
│ - Robuste bruit      │
│ - Peu paramètres     │
│ - Support holidays   │
└──────────────────────┘

                    ↓

OUTPUT: Prévisions pour 12 mois suivants
──────────────────────────────────────────

Modèle | ds          | yhat      | yhat_lower | yhat_upper | is_hist
--------|-------------|-----------|------------|------------|--------
ARIMA   | 2025-01-01  | 235000    | 220000     | 250000     | 0
ARIMA   | 2025-02-01  | 240000    | 222000     | 258000     | 0
...     | ...         | ...       | ...        | ...        | ...
SARIMA  | 2025-01-01  | 238000    | 225000     | 251000     | 0
...     | ...         | ...       | ...        | ...        | ...
PROPHET | 2025-01-01  | 236500    | 223000     | 250000     | 0
...     | ...         | ...       | ...        | ...        | ...

Storage: ML_KPI05_CA_FORECAST table

                    ↓

FRONTEND AFFICHAGE
───────────────────
Chart avec:
- Axe X: Mois (2020-2025+)
- Axe Y: CA (TND)
- Courbe grise: Historique
- Ligne colorée: Prévisions (couleur = modèle)
- Zone ombragée: Intervale confiance [yhat_lower, yhat_upper]

Utilisateur peut:
- Sélectionner modèle (ARIMA, SARIMA, PROPHET)
- Voir valeurs exactes en hover
- Exporter prévisions CSV
```

---

## 4. Structure de données DW

```
┌──────────────────────────────────────────────────────────────┐
│                    DATA WAREHOUSE STAR SCHEMA                 │
└──────────────────────────────────────────────────────────────┘

                    FAIT_LIGNES_VENTE
                   (Table de faits)
                    ┌──────────┐
                    │ id_vente  │ PK
                    │ id_date   │ FK→DIM_DATE
                    │ id_client │ FK→DIM_CLIENT
                    │ id_article│ FK→DIM_ARTICLE
                    │ id_segment│ FK→DIM_SEGMENT
                    │ montant_HT│
                    │ qte       │
                    │ delai_reel│
                    │ est_paye  │
                    └──────────┘
                   ↙ ↓ ↓ ↓ ↓ ↘
    ┌────────────┐  ┌──────────┐  ┌───────────┐  ┌────────────┐  ┌──────────┐
    │ DIM_DATE   │  │ DIM_CLIENT│  │DIM_ARTICLE│  │DIM_SEGMENT │  │DIM_VILLE │
    ├────────────┤  ├──────────┤  ├───────────┤  ├────────────┤  ├──────────┤
    │ id_date[PK]│  │ id_client │  │ id_article│  │id_segment[P│  │id_ville  │
    │ date_val   │  │ CT_Num[FK]│  │ AR_Ref[FK]│  │ cbIndice   │  │ CbIndice │
    │ jour       │  │ nom       │  │ nom       │  │ libelle    │  │ nom      │
    │ mois       │  │ ville_id  │  │ famille_id│  │ prix       │  │ gouvern. │
    │ trimestre  │  │ segment_id│  │ prix_ach  │  │            │  │          │
    │ annee      │  │ fourniss. │  │ fourniss. │  │            │  │          │
    │ est_weekend│  │ categorie │  │ stock     │  │            │  │          │
    │ ...        │  │ ...       │  │ ...       │  │            │  │          │
    └────────────┘  └──────────┘  └───────────┘  └────────────┘  └──────────┘
```

**Concept: Star Schema**
- 1 table de faits au centre (FAIT_LIGNES_VENTE)
- N dimensions autour (DIM_*)
- Jointures radiales (étoile)
- Optimisé pour lectures analytiques (OLAP)

---

## 5. Cycle de vie requête API → Affichage Frontend

```
┌─ UTILISATEUR CLIQUE SUR TABLEAU ─────────────────────┐
│                                                        │
└────────────────────┬─────────────────────────────────┘
                     ↓

┌─ FRONTEND (React) ──────────────────────────────────┐
│                                                      │
│ 1. useFilters() hook → recupère filtres:            │
│    ├─ year: 2024                                    │
│    ├─ month: 3                                      │
│    ├─ segment: "Premium"                            │
│    └─ ville: "Tunis"                                │
│                                                      │
│ 2. useApiResource() → construit query string:       │
│    GET /api/kpi/ca?year=2024&month=3&...           │
│                                                      │
│ 3. Affiche loading spinner                          │
│                                                      │
└────────────┬────────────────────────────────────────┘
             ↓

┌─ BACKEND API (FastAPI) ─────────────────────────────┐
│                                                      │
│ @app.get("/api/kpi/ca")                            │
│ def get_ca(year: int, month: int, ...):            │
│                                                      │
│ 1. Parser paramètres                                │
│ 2. Construire requête SQL:                          │
│    WHERE annee = :year AND mois = :month            │
│    AND (segment = :segment OR segment IS NULL)      │
│    AND (ville = :ville OR ville IS NULL)            │
│                                                      │
│ 3. Appeler _rows(sql, params)                       │
│    ├─ Si ETL en cours → retourner []                │
│    ├─ Sinon exécuter requête                        │
│    ├─ Gérer erreurs (SQLAlchemyError)               │
│    └─ Retourner lignes SQL Server                   │
│                                                      │
│ 4. Transformer en JSON:                             │
│    {                                                 │
│      "ca": 1500000.00,                              │
│      "qte": 450,                                     │
│      "nb_clients": 23,                               │
│      "delai_paiement_moyen": 45.2                    │
│    }                                                 │
│                                                      │
│ 5. Retourner au frontend                            │
│                                                      │
└────────────┬────────────────────────────────────────┘
             ↓

┌─ DATA WAREHOUSE (SQL Server) ───────────────────────┐
│                                                      │
│ SELECT                                               │
│   SUM(f.DL_MontantHT) as ca,                        │
│   COUNT(DISTINCT f.id_client) as nb_clients         │
│ FROM FAIT_LIGNES_VENTE f                            │
│ JOIN DIM_DATE d ON f.id_date = d.id_date            │
│ JOIN DIM_CLIENT c ON f.id_client = c.id_client      │
│ WHERE d.annee = 2024                                │
│   AND d.mois = 3                                    │
│   AND c.id_segment = :segment_id                    │
│   AND c.id_ville = :ville_id                        │
│                                                      │
│ Résultat: 1 seule ligne (agrégée)                   │
│                                                      │
└────────────┬────────────────────────────────────────┘
             ↓

┌─ FRONTEND (React) - Affichage ──────────────────────┐
│                                                      │
│ Récoit JSON du backend                              │
│ Affiche dans KPICard:                               │
│                                                      │
│ ┌─ KPI CARD ─────────────────────────────┐         │
│ │                                         │         │
│ │  Chiffre d'Affaires                     │         │
│ │  1,500,000 TND                          │         │
│ │                                         │         │
│ │  ↑ +8% vs mois dernier                  │         │
│ │                                         │         │
│ │  Clients actifs: 23                     │         │
│ │  Délai paiement: 45.2j                  │         │
│ │                                         │         │
│ └─────────────────────────────────────────┘         │
│                                                      │
│ Utilisateur peut:                                   │
│ - Changer filtres                                   │
│ - Exporter données                                  │
│ - Voir détail dans tableau                          │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## 6. Thread Safety & Verrous

```
┌──────────────────────────────────────────────────────────┐
│           PROBLÈME: ETL vs API Concurrent               │
└──────────────────────────────────────────────────────────┘

SCÉNARIO 1: Pas de protection
─────────────────────────────

Thread 1 (API)          │ Thread 2 (ETL)
                        │
GET /api/data           │
  ├─ SELECT * FROM DIM  │ [Run] DELETE FROM DIM
  └─ Data partielles!   │      INSERT INTO DIM
                        │      [ETL commit]
        ↓               │        ↓
   Résultat corrompu!   │


SCÉNARIO 2: Avec verrous (notre approche)
──────────────────────────────────────────

_ETL_RUN_LOCK = threading.Lock()

Thread 1 (API)          │ Thread 2 (ETL)
                        │
GET /api/data           │
  ├─ if _ETL_RUN_LOCK.  │
  │     locked():       │
  │     return []       │ [Acq. verrou]
  │                     │ [Run] DELETE, INSERT
  │                     │ [Commit]
  │                     │ [Rel. verrou]
  └─ Requête safe!      │


VERROUS UTILISÉS:

1. _ETL_RUN_LOCK (etl/pipeline.py)
   ├─ Acquis au début du ETL
   ├─ Empêche API de requêter pendant ETL
   └─ Libéré à la fin du ETL

2. _ML_RUN_LOCK (ml/runner.py)
   ├─ Acquis avant d'entraîner modèles
   ├─ Empêche 2 ML runs simultanés
   └─ Libéré après entraînement


FLUX AVEC VERROUS:

ETL Background:
  try:
      _ETL_RUN_LOCK.acquire(blocking=False)
      run_pipeline()  # Safe, verrou tenu
      audit.complete_run("SUCCESS")
  except:
      audit.complete_run("ERROR", error)
  finally:
      _ETL_RUN_LOCK.release()

API Endpoint:
  def _rows(sql, params=None):
      if _ETL_RUN_LOCK.locked():
          return []  # Ne pas requêter si ETL actif
      try:
          with DW_ENGINE.connect() as conn:
              return conn.execute(text(sql), params).fetchall()
      except SQLAlchemyError:
          return []
```

---

## 7. Lookups & Enrichissement

```
┌────────────────────────────────────────────────────────┐
│          ENRICHISSEMENT AVEC LOOKUPS (JOINTURE)       │
└────────────────────────────────────────────────────────┘

ÉTAPE 1: Créer lookups (après charger dimensions)
──────────────────────────────────────────────────

lookups["DIM_DATE"] = _build_lookup("DIM_DATE", "date_val", "id_date")

Fonction:
  Query: SELECT id_date, date_val FROM DIM_DATE
  Dict: {
    date(2024,1,1): 1,
    date(2024,1,2): 2,
    date(2024,1,3): 3,
    ...
  }

lookups["DIM_CLIENT"] = _build_lookup("DIM_CLIENT", "CT_Num", "id_client")

  Query: SELECT id_client, CT_Num FROM DIM_CLIENT
  Dict: {
    "CT001": 10,
    "CT002": 11,
    "CT003": 12,
    ...
  }

...même pour SEGMENT, VILLE, etc


ÉTAPE 2: Enrichir faits avec IDs techniques
────────────────────────────────────────────

Données sources (brutes):
┌──────────┬────────────┬─────────────┐
│ date_val │ CT_Num     │ montant     │
├──────────┼────────────┼─────────────┤
│ 2024-1-1 │ CT001      │ 1000        │
│ 2024-1-1 │ CT002      │ 1500        │
│ 2024-1-2 │ CT001      │ 2000        │
└──────────┴────────────┴─────────────┘

Enrichissement:
  df["id_date"] = df["date_val"].map(lookups["DIM_DATE"])
  df["id_client"] = df["CT_Num"].map(lookups["DIM_CLIENT"])

Résultat (enrichi):
┌──────────┬────────────┬──────────┬────────────┬─────────────┐
│ date_val │ CT_Num     │ id_date  │ id_client  │ montant     │
├──────────┼────────────┼──────────┼────────────┼─────────────┤
│ 2024-1-1 │ CT001      │ 1        │ 10         │ 1000        │
│ 2024-1-1 │ CT002      │ 1        │ 11         │ 1500        │
│ 2024-1-2 │ CT001      │ 2        │ 10         │ 2000        │
└──────────┴────────────┴──────────┴────────────┴─────────────┘

ÉTAPE 3: Charger en DB avec IDs techniques
───────────────────────────────────────────

INSERT INTO FAIT_LIGNES_VENTE (id_date, id_client, montant)
VALUES (1, 10, 1000),
       (1, 11, 1500),
       (2, 10, 2000)

✅ AVANTAGES des IDs techniques (surrogate keys):
   - Économise espace (int au lieu de string date/code)
   - Élimine redondance (pas répéter date/nom dans chaque ligne)
   - Accélère jointures (int vs string)
   - Permet changements dimensions (renommer client sans toucher faits)
```

---

## 8. Logique filtre "Tous" vs filtré

```
┌──────────────────────────────────────────────────────┐
│         LOGIQUE FILTRE MÉTIER FINMAG                │
└──────────────────────────────────────────────────────┘

Valeurs "sans filtre":
NO_FILTER_VALUES = ("Tous", "Toutes", "")

Exemple requête:

  segment = "Tous"  (pas de filtre)
  ville = "Tunis"   (avec filtre)

SQL généré:
  SELECT ... FROM ...
  WHERE (segment IS NULL OR segment_id IN (SELECT id FROM DIM_SEGMENT))
    AND ville_id = 5  -- ID de Tunis

Alternative pattern:
  SELECT ... FROM ... WHERE 1=1
    (concat dynamique des conditions)


PSEUDO-CODE générique:

def build_where_clause(filters):
    conditions = []
    params = {}
    
    if filters.get("segment") not in NO_FILTER_VALUES:
        conditions.append("c.id_segment = :segment_id")
        params["segment_id"] = lookups["SEGMENT"].get(filters["segment"])
    
    if filters.get("ville") not in NO_FILTER_VALUES:
        conditions.append("c.id_ville = :ville_id")
        params["ville_id"] = lookups["VILLE"].get(filters["ville"])
    
    # ... ajouter autres filtres
    
    where = " AND ".join(conditions) if conditions else "1=1"
    return f"SELECT ... FROM ... WHERE {where}", params
```

---

## Mémo - Diagrammes à redessiner en soutenance

Si jury demande de dessiner:

1. **Star Schema** (étoile) - 1 fait au centre, N dimensions
2. **ETL Pipeline** (extract → transform → load)
3. **Thread Safety** (deux threads, un verrou)
4. **Forecast Models** (3 courbes: ARIMA, SARIMA, PROPHET)
5. **API Call Flow** (Frontend → API → DB → Frontend)

Tous ces schémas sont ci-dessus. Vous pouvez les redessiner en 2 min chacun.

---

## Bonus: Cheat Sheet SQL

```sql
-- Requête la plus courante: Agrégé par mois/segment
SELECT
    d.annee,
    d.mois,
    s.libelle as segment,
    COUNT(*) as nb_lignes,
    SUM(f.montant_HT) as ca_total,
    AVG(f.delai_reel) as delai_moyen
FROM FAIT_LIGNES_VENTE f
JOIN DIM_DATE d ON f.id_date = d.id_date
JOIN DIM_SEGMENT s ON f.id_segment = s.id_segment
WHERE d.annee >= 2023
GROUP BY d.annee, d.mois, s.libelle
ORDER BY d.annee DESC, d.mois DESC;

-- Vérifier intégrité
SELECT COUNT(*), COUNT(DISTINCT id_date) FROM FAIT_LIGNES_VENTE;
-- Si COUNT = COUNT DISTINCT → pas OK (doublons)

-- Vérifier performance
SELECT COUNT(*) FROM FACT_LIGNES_VENTE;
-- > 1M rows? Créer indexes:
CREATE INDEX idx_fact_id_date ON FACT_LIGNES_VENTE(id_date);
CREATE INDEX idx_fact_id_client ON FACT_LIGNES_VENTE(id_client);

-- Tester lookups
SELECT COUNT(DISTINCT CT_Num) as nb_clients_source
FROM FACT_LIGNES_VENTE;

SELECT COUNT(DISTINCT id_client) as nb_clients_loaded
FROM FACT_LIGNES_VENTE;
-- Devraient être égaux (sinon des CT_Num n'ont pas d'ID)
```

C'est tout! Vous avez maintenant:
- ✅ Guides complets de chaque composant
- ✅ Exercices pratiques à réécrire
- ✅ Schémas visuels à mémoriser/redessiner
- ✅ Questions-réponses courantes du jury

Bonne soutenance! 🚀
