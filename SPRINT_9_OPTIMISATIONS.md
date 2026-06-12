# Sprint 9+ — Optimisations pipeline (2026-06-12)

> **But** : diviser par ~50 la charge CPU/RAM du VPS (12 Go) en
> découplant entraînement / inférence, supprimer le bug baseline silencieux
> et matérialiser le training set H+1h pour rendre l'XGBoost opérationnel
> de bout en bout.

## 1. Découplage entraînement / inférence (gaspillage CPU éliminé)

### Avant (Sprint 8+)
- `dag_live_speed_retrain` tournait **toutes les 30 min** = **48 entraînements/jour**.
- Les données ne changeaient qu'une fois par jour → 47 entraînements
  strictement identiques, soit ~47× ~5 min = **~4h CPU gaspillées/jour**.

### Après (Sprint 9+)
| DAG | Fréquence | Durée | Rôle |
|-----|-----------|-------|------|
| `build_xgb_training_set` | 02h30 quotidien | ~1 min | Matérialise `gold.xgb_training_set` (self-join H+1h indexé) |
| `dag_daily_speed_train` | 03h00 quotidien | ~5-10 min | **Entraîne** XGBoost H+1h, sauvegarde disque + MLflow |
| `dag_inference_xgboost` | **toutes les 15 min** | ~10-30 s | **Inférence pure** : charge le modèle, prédit, INSERT gold.trafic_predictions |

**Gain** : 1 entraînement/jour au lieu de 48 → **−98 % du coût training**.
Le worker Airflow peut maintenant charger le modèle 1 fois (cache process)
et ne faire que de l'inférence.

## 2. Bug critique silencieux — fallback baseline (ÉTAT FIXÉ)

### Symptôme
Le widget "Carte du trafic" insérait des "prédictions" = **30.0 km/h constant**
(la valeur de fallback du `XGBoostSpeedModel.predict()` quand le modèle
n'est pas entraîné). Le dashboard mentait à l'utilisateur en affichant
"Lyon à 30 km/h moyen" alors qu'aucun modèle n'était actif.

### Cause (3 couches)
1. `src/models/xgboost_speed.py:240` retournait `predicted_speed_kmh=30.0`
   si `self.models[60]` n'était pas chargé.
2. `dag_live_speed_retrain.py` entraînait toutes les 30 min, mais
   `train_one()` filait l'erreur `gold.xgb_training_set n'existe pas`
   (la table n'avait jamais été créée).
3. Le DAG catchait l'exception en best-effort et insérait quand même
   la baseline dans `gold.trafic_predictions` → **l'utilisateur voyait
   des données, mais c'était du fake**.

### Fix (Sprint 9+)
- `gold.xgb_training_set` créée par `scripts/sql/create_xgb_training_set.sql`
  (schéma v0.3.1, 11 features alignées sur `gold.traffic_features_live`).
- `build_xgb_training_set` (DAG Airflow) la peuple chaque nuit via
  self-join H+1h indexé (Index Only Scan en 19s sur 444k iterations).
- `XGBoostSpeedModel._load_training_data()` lit directement cette table
  (plus de `LEAD() OVER (...)` sur 2.4M rows).
- `dag_inference_xgboost` charge le modèle entraîné et fait une vraie
  prédiction XGBoost — **plus aucun fallback baseline**.

## 3. RAM worker Airflow

État du VPS (12 Go total) :
- postgres : ~1-2 Go
- redis : 256 Mo
- streamlit : 1 Go
- api : 768 Mo
- mlflow : 768 Mo
- **airflow-worker : 6 Go** (déjà en place dans `docker-compose.yml`)

Pas de changement nécessaire côté worker : la séparation training/inf
garantit qu'on n'a plus de pic de RAM (l'entraînement nocturne ne
concurrence plus l'inférence temps réel).

## 4. Performance de la query SQL d'entraînement

### EXPLAIN ANALYZE (single query CTE pré-filtrée, 2 jours de lookback)
```
->  Index Only Scan using idx_gold_traffic_channel_computed
    on traffic_features_live traffic_features_live_1
    (cost=0.56..2.01 rows=35 width=16)
    (actual time=0.101..0.107 rows=1 loops=444405)
    Index Cond: ((channel_id = traffic_features_live.channel_id)
                 AND (computed_at >= ...)
                 AND (computed_at <  ...))
Execution Time: 18880.732 ms   (~19s)
```

### Run réel DAG `build_xgb_training_set`
- Durée totale : **54.5s** (INSERT + stats)
- Rows insérées : **358 695** sur **1088 channels**
- Target : moyenne 23.3 km/h, std 18.0 (cohérent trafic urbain)

## 5. Index créé

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gold_traffic_channel_computed
  ON gold.traffic_features_live USING btree (channel_id, computed_at)
  INCLUDE (speed_kmh, lag_1, lag_2, lag_3, rolling_mean_3);
```

**Covering index** : `(channel_id, computed_at)` + colonnes features en
INCLUDE → Index Only Scan, pas de Heap Fetch.

## 6. Fix carte trafic "H+30min" → "H+1h" (Sprint 8+ UI cohérence)

`dashboard/components/widgets/pro_tcl/gnn_map.py:222` — le default
de `render_traffic_map_compact(horizon_minutes=...)` est passé de 30 à
60 (alignement sur la politique focus H+1h). Le caption "pas de
prédictions H+30min" utilise maintenant la bonne valeur.

`dashboard/pages/Usager_1_Mon_Trajet.py:163` — titre de section
mis à jour : "🗺️ Carte du trafic — H+1h" au lieu de "H+30min".

## 7. Smoke test à reproduire

```bash
# 1. Vérifier que les 3 DAGs s'importent
docker compose exec airflow-scheduler python -c "
import sys; sys.path.insert(0, '/opt/airflow')
for dag_id in ['dag_daily_speed_train', 'dag_inference_xgboost', 'build_xgb_training_set']:
    __import__('dags.ml.' + dag_id)
    print(f'OK {dag_id}')"

# 2. Trigger manuel build_xgb_training_set
docker compose exec airflow-scheduler airflow dags trigger build_xgb_training_set
# Attendre ~1 min puis vérifier :
docker compose exec postgres psql -U lyonflow -d lyonflow -c "
  SELECT count(*), count(DISTINCT channel_id) FROM gold.xgb_training_set;"

# 3. Trigger manuel dag_daily_speed_train (entraîne le modèle)
docker compose exec airflow-scheduler airflow dags trigger dag_daily_speed_train
# Attendre ~10 min puis vérifier :
ls -la /opt/lyonflow/data/models/xgb_speed_h60.pkl

# 4. Trigger manuel dag_inference_xgboost (prédit)
docker compose exec airflow-scheduler airflow dags trigger dag_inference_xgboost
# Vérifier que les nouvelles prédictions ont model_version != 0.0.0 :
docker compose exec postgres psql -U lyonflow -d lyonflow -c "
  SELECT model_version, count(*) FROM gold.trafic_predictions
  WHERE calculated_at > NOW() - INTERVAL '15 min'
  GROUP BY model_version;"
```

## 8. Fix rendu carte itinéraire voiture (Sprint 9+)

### Symptôme
Le widget "Mon trajet" (Usager_1) affichait 8 points dispersés (Steph,
Rue de l'Université, Avenue Berthelot) au lieu d'une polyligne le long
des rues, avec certains points dans le Rhône.

### Cause
- Les nœuds H3 sont au **centre de cellule hexagonale** (`cell_to_geo`),
  pas sur la rue exacte. Ils peuvent tomber dans le Rhône, sur un toit,
  ou perpendiculairement à la rue.
- 1 `folium.PolyLine` par segment = 8 traits courts non reliés.
- Aucune géométrie LineString en base (`geometry_columns` ne retourne
  que 3 tables POINT : `gold.channels_ref`, `silver.trafic_boucles_clean`
  ×2). Pas de réseau routier OSM stocké.

### Fix Sprint 9+ (progressive)
- `dashboard/components/widgets/usager/itinerary.py` : 1 polyligne
  **continue** reliant tous les nœuds du chemin (`dash_array="6 4"`
  pour signaler que c'est une approximation H3) + cercles H3 + segments
  colorés par vitesse.
- Sprint 10+ : snap-to-roads via Overpass API
  (`https://overpass-api.de/api/interpreter`) pour projeter chaque
  nœud H3 sur la rue la plus proche dans un rayon 20m. Requiert
  ~150ms par nœud, ~2s pour 8 nœuds. Cached 1h.
- Sprint 11+ (ou AWS/GCP) : OSRM local (`osrm-backend` Docker image,
  ~500 Mo RAM) pour un vrai routage routier avec snap-to-roads
  intégré. Hors scope VPS 12 Go.

## 9. Drift PSI (à intégrer Sprint 9+ suite)

`src/monitoring/psi.py` créé — module de calcul PSI (Population Stability
Index) sans dépendance Evidently. À intégrer dans
`build_xgb_training_set` pour persister un rapport dans
`gold.model_drift_reports` (table déjà existante, schéma v0.3.1).
