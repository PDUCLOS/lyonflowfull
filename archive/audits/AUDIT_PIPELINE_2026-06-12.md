# Audit complet LyonFlowFull — Pipeline, Mocks, Widgets

**Date** : 2026-06-12
**Branche** : `vps` (production)
**Scope** : 142 fichiers Python, 50+ widgets, 8 collecteurs, 9 DAGs, 3 modeles ML
**Methode** : scan exhaustif `grep` + lecture code + validation DDL (`deploy/init-db.sql`)

---

## Table des matieres

1. [Synthese executive](#1-synthese-executive)
2. [Audit Zero Mock — Etat reel](#2-audit-zero-mock--etat-reel)
3. [Pipeline complet Bronze → Gold → ML → Dashboard](#3-pipeline-complet-bronze--gold--ml--dashboard)
4. [Audit widget par widget](#4-audit-widget-par-widget)
5. [Problemes critiques (CRASH runtime)](#5-problemes-critiques-crash-runtime)
6. [Problemes de qualite des donnees (silencieux)](#6-problemes-de-qualite-des-donnees-silencieux)
7. [Code mort a nettoyer](#7-code-mort-a-nettoyer)
8. [Plan de correction priorise](#8-plan-de-correction-priorise)

---

## 1. Synthese executive

| Indicateur | Valeur |
|------------|--------|
| Fichiers Python | 142 |
| Tests | 150 verts / 9 skip / 7 deselected |
| Widgets total | 50+ (15 usager + 16 elu + 20 pro_tcl) |
| Widgets 100% donnees reelles | **29** |
| Widgets partiellement fabriques | **7** |
| Widgets hardcodes (pas de DB) | **5** |
| Widgets renderers purs (OK) | **9+** |
| Mocks en production (TRUE MOCK) | **7 instances** |
| Code mort (demo_mode) | **6 blocs** |
| Labels trompeurs | **4 fichiers** |
| Queries SQL cassees (crash silencieux) | **5 fonctions** |
| Schema mismatches confirmes | **3 critiques** |

### Verdict

Le Sprint 8 "Zero Mock" a supprime le systeme de mock (repertoire `src/data/mock/`, flag `LYONFLOW_DEMO_MODE`). **Mais 7 vrais mocks subsistent dans le code de production**, dont 3 critiques. Le pipeline Medallion fonctionne Bronze→Silver→Gold, mais les modeles ML ne s'entrainent pas reellement (colonnes renommees non propagees). Les predictions sont en mode **baseline** (derniere vitesse observee = prediction).

---

## 2. Audit Zero Mock — Etat reel

### 2.1 Contexte structurant

```python
# src/data/data_loader.py:86
def _is_demo_mode():
    return False  # Toujours False depuis Sprint 8

# src/data/data_loader.py:99
def _maybe_force_mock():
    return False  # Toujours False
```

Le repertoire `src/data/mock/` est **supprime**. Les mocks test restent dans `tests/fixtures/mock_data/` (normal).

### 2.2 TRUE MOCK — Atteignables en production

#### CRITIQUE-1 : Bottlenecks avec ROI/cout fabriques

| | |
|---|---|
| **Fichier** | `src/data/data_loader.py:624-639` |
| **Impact** | 8 chemins de production (5 widgets Elu + 3 pages) |
| **Probleme** | `load_bottlenecks_top()` lit les vrais bottlenecks depuis `gold.infrastructure_bottlenecks` mais **fabrique 6 champs** : `lines_impacted=["C3","C13"]`, `voyageurs_jour=5000+i*1000`, `gain_min=5+i`, `cout_M_euros=2.5-i*0.15`, `roi_mois=18+i*3`, `delai_mois=6+i*2` |
| **Consequence** | Des elus voient des chiffres de ROI et de cout totalement inventes |

#### CRITIQUE-2 : Graphe mock en fallback silencieux

| | |
|---|---|
| **Fichier** | `src/routing/graph.py:79-81, 200-265` |
| **Impact** | Tout le routage (itineraires Usager + Elu) |
| **Probleme** | Si `_build_graph_from_db()` leve une exception, `except Exception` tombe sur `_build_mock_graph()` — 12 segments hardcodes avec noms fictifs (`MOCK_C3_*`) et vitesses inventees |
| **Consequence** | Le routage peut tourner sur un faux graphe sans signal d'erreur |

#### CRITIQUE-3 : GNN entraine sur donnees synthetiques en fallback

| | |
|---|---|
| **Fichier** | `dags/ml/retrain_gnn.py:152-153` |
| **Impact** | Modele GNN deploye en production |
| **Probleme** | Si chargement DB echoue, fallback sur `STGCNDataset.synthetic()` — donnees aleatoires. Un modele entraine sur du bruit serait pousse dans MLflow |
| **Consequence** | Masque par DAG paused, mais dangereux si reactive |

#### MOYEN-1 : Coordonnees GPS par hash

| | |
|---|---|
| **Fichier** | `src/data/data_loader.py:122-144` |
| **Impact** | Carte trafic usager |
| **Probleme** | `_approx_lonlat_from_channel_id()` genere des pseudo-coords par hash du `channel_id` car les vrais lat/lon sont NULL (dette schema `properties_twgid` vs `channel_id`) |

#### MOYEN-2 : Confiance hardcodee

| | |
|---|---|
| **Fichier** | `src/routing/pathfinder.py:163` |
| **Impact** | Score de confiance des itineraires |
| **Probleme** | `_compute_confidence()` retourne `0.85` en dur, quelle que soit la fraicheur des donnees |

#### MOYEN-3 : Matrice spatiale sans H3

| | |
|---|---|
| **Fichier** | `dags/transforms/build_spatial_mapping.py:71-74` |
| **Impact** | Topologie du GNN |
| **Probleme** | `matrix_i/j` calcule via `node_idx % 40 / node_idx // 40` au lieu de `h3.cell_to_local_ij()` |

#### FAIBLE-1 : Metriques Accueil hardcodees

| | |
|---|---|
| **Fichier** | `dashboard/Accueil.py:157, 163` |
| **Impact** | Page d'accueil decorative |
| **Probleme** | `"Capteurs trafic", "1 100"` et `"Predictions/jour", "~26k"` sont des constantes |

### 2.3 Code mort (derriere `_is_demo_mode()=False`)

Jamais execute en prod mais encombre le code :

| Fichier | Lignes | Description |
|---------|--------|-------------|
| `src/data/data_loader.py` | 961-1039 | `_FALLBACK_MOCK_MODELS` (7 entrees MLflow) |
| `dashboard/components/widgets/pro_tcl/model_monitoring.py` | 20-92 | `MOCK_MODELS` (7 modeles) |
| `dashboard/components/widgets/pro_tcl/pipeline_management.py` | 209-249 | 6 health check hardcodes |
| `src/routing/pathfinder_multimodal.py` | 276-281, 539-549 | Itineraires vides `source="demo"` |
| `src/ml/mlflow_integration.py` | 318, 326, 382 | Return `[]` au lieu de `DashboardDataError` |
| `src/data/db_query.py` | 78-82 | `_with_fallback()` — zero appelant |

### 2.4 Labels trompeurs (documentation mensongere)

| Fichier | Ligne | Message actuel | Devrait etre |
|---------|-------|---------------|-------------|
| `dashboard/components/data_status.py` | 32 | "chiffres fictifs (mocks)" | "donnees indisponibles" |
| `src/data/db_query.py` | 51-53 | "basculeront sur les donnees mock" | "afficheront une erreur" |
| `src/data/airflow_client.py` | 7 | "fallback MOCK_DAGS preserve" | Supprimer, le code leve `DashboardDataError` |
| `dashboard/components/data_cache.py` | toutes | Parametre `force_mock: bool = False` | Supprimer le parametre mort |

---

## 3. Pipeline complet Bronze → Gold → ML → Dashboard

### 3.1 Bronze — Ingestion (8 sources)

```
API Source            Collecteur                    Table Bronze              Frequence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Grand Lyon WFS        trafic_grandlyon.py           bronze.trafic_boucles     */5 min
SIRI 2.0              tcl_siri_lite.py              bronze.tcl_vehicles       */5 min
GBFS 3.0              velov.py                      bronze.velov              */5 min
Open-Meteo forecast   meteo.py                      bronze.meteo              */1h
Open-Meteo AQ         air_quality.py                bronze.air_quality        */1h
Grand Lyon WFS        chantiers.py                  bronze.chantiers          1x/jour
data.education.gouv   calendrier_scolaire.py        bronze.calendrier_sc.     1x/mois
calendrier.api.gouv   jours_feries.py               bronze.jours_feries       1x/mois
```

**Pattern commun** : `DataCollector` (Template Method) → `fetch_raw()` → `validate()` → `_save_raw()`. Tenacity retry 3x exponentiel. Skip INSERT si n_records=0.

> **[B-1] DEAD-END** : `bronze.air_quality` est ingere mais **n'a AUCUN transform Silver**. Donnees stockees, jamais utilisees.

### 3.2 Silver — Nettoyage (5 transforms)

```
Bronze Source              Transform                     Table Silver                 Statut
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
bronze.trafic_boucles      Parse GeoJSON, midpoint,      silver.trafic_boucles_clean   OK
                           deduplicate, geom 4326+2154
bronze.velov               Merge status+info by station  silver.velov_clean            OK
bronze.tcl_vehicles        Parse SIRI, extract delay     silver.tcl_vehicles_clean     OK
bronze.meteo               Parse hourly forecast         silver.meteo_hourly           ⚠️ [S-1]
bronze.chantiers           Filtre actifs, parse dates    silver.chantiers_actifs        OK
bronze.air_quality         —                             —                             ❌ Pas de transform
```

> **[S-1] SCHEMA DIVERGE** : `_transform_meteo` ecrit `temperature_c, rain_mm` mais le DDL init-db.sql a `temperature_2m, precipitation`. Le code en aval (`silver_to_gold`) lit `temperature_c, rain_mm` → schema probablement ALTER-e post-dump, mais divergence non reconciliee.

### 3.3 Gold — Feature Engineering (5 transforms)

#### gold.traffic_features_live (31 colonnes)

```
Input:  silver.trafic_boucles_clean (fenetre 2h)
        + LATERAL JOIN silver.meteo_hourly
        + LEFT JOIN gold.dim_spatial_grid_mapping  ← ⚠️ JOIN CASSE [G-1]
        + fonctions PL/pgSQL _is_vacances(), _is_ferie()

Calculs:
  - LAG(speed_kmh, 1/2/3) → lag_1, lag_2, lag_3
  - AVG(speed_kmh) OVER (3 preceding) → rolling_mean_3
  - speed_kmh - LAG(...,1) → delta_1
  - sin(2π * hour/24) → sin_hour, cos_hour
  - sin(2π * dow/7) → sin_dow, cos_dow
  - md5(channel_id) → channel_hash

Output: channel_id, computed_at, speed_kmh, vitesse_limite_kmh,
        lag_1..3, delta_1, rolling_mean_3, sin_hour, cos_hour,
        sin_dow, cos_dow, hour_of_day, day_of_week, is_weekend,
        temperature_2m, precipitation, is_vacances, is_ferie,
        lat(NULL), lon(NULL), channel_hash
```

> **[G-1] JOIN CASSE** : `dim_spatial_grid_mapping.properties_twgid` stocke des entiers ("537"), `traffic_features_live.channel_id` stocke "LYO00xxx". Le JOIN `ON properties_twgid = channel_id` ne match **jamais**. Consequence : `lat` et `lon` sont **toujours NULL**.

#### gold.velov_features

```
Input:  silver.velov_clean (fenetre 2h)
        + LATERAL JOIN silver.meteo_hourly

Calculs:
  - DENSE_RANK() → station_id_encoded
  - LAG bikes 1/2/3
  - AVG rolling_mean_3h
  - hour_sin, hour_cos
  - is_vacances, is_ferie

⚠️ [G-2] Colonnes INSERT (bikes_lag_1..3, rolling_mean_3h) ≠
          DDL migration (lag_30min, lag_60min, rolling_mean_1h)
```

#### gold.bus_delay_segments

```
Input:  silver.tcl_vehicles_clean (7 jours)
Calculs: AVG/P90 delay_seconds GROUP BY line_ref, hour, date, weather
Statut: OK
```

#### gold.tcl_vehicle_realtime

```
Input:  silver.tcl_vehicles_clean
Calcul: DISTINCT ON (journey_ref) ORDER BY measurement_time DESC
Statut: OK
```

#### gold.infrastructure_bottlenecks

```
Input:  gold.bus_delay_segments × gold.traffic_features_live
Calcul: CROSS JOIN par heure, diagnostic :
  - bus lent + trafic lent = "infra" (bottleneck infrastructure)
  - bus lent + trafic OK = "operations" (probleme operationnel)
  - trafic lent + bus OK = "bus_lane_ok" (voie dediee fonctionne)
  - sinon = "ok"

⚠️ [G-3] lat/lon synthetiques : HASHTEXT(segment_id) % 1000 / 10000.0 + 45.75
```

### 3.4 ML — Modeles (3 modeles, etat reel)

#### XGBoost Speed (H+1h)

```
Fichier:   src/models/xgboost_speed.py
Schedule:  */30 min (dag_live_speed_retrain)
Features:  speed_kmh, lag_h1, rolling_mean_h1, sin_hour, cos_hour,
           temperature_2m, precipitation, is_vacances, is_ferie

❌ [M-1] CRASH SYSTEMATIQUE — lag_h1 et rolling_mean_h1 N'EXISTENT PAS
   dans gold.traffic_features_live (noms reels: lag_1, rolling_mean_3).
   Le training echoue silencieusement → le DAG bascule en BASELINE :
   derniere vitesse observee propagee comme "prediction".

Ecriture:  gold.trafic_predictions (horizon_h=1 uniquement)
           model_version="baseline_v0.3.1", lat=NULL, lon=NULL
```

#### XGBoost Velov (H+30min, H+1h)

```
Fichier:   src/models/xgboost_velov.py
Schedule:  hourly :50 (retrain_xgboost)
Features:  station_id_encoded, bikes_lag_1..3, rolling_mean_3h,
           hour_sin, hour_cos, temperature_c, rain_mm, is_vacances, is_ferie

❌ [M-2] DOUBLE PROBLEME :
   (a) Colonnes potentiellement renommees (meme [G-2])
   (b) Target = bikes_available ACTUEL (pas de LEAD) → le modele
       apprend a predire le present, pas le futur
```

#### ST-GRU-GNN (spatial, daily 03h)

```
Fichier:   training/stgcn/model.py + dataset.py
Schedule:  daily 03h (retrain_gnn) — DAG PAUSED

❌ [M-3] dataset.py SELECTe node_idx, hour_sin, day_sin
   qui n'existent pas (vrais noms: sin_hour, sin_dow, pas de node_idx
   dans traffic_features_live). Masque car DAG paused + fallback synthetic.
```

### 3.5 Predictions → Dashboard

```
gold.trafic_predictions (*/30 min, BASELINE uniquement)
  │
  │  axis_key, horizon_h=1, speed_pred, etat_pred, color,
  │  vitesse_limite_kmh, label, model_version, lat=NULL, lon=NULL
  │
  ├──→ traffic_widget.py (Usager) : affiche speed + etat. OK
  ├──→ gnn_map.py (Pro) : merge sur node_idx → TOUJOURS NULL → "Pas de predictions"
  └──→ data_loader.py : demande horizons 0/1/3 → seul horizon_h=1 peuple [D-1]
```

### 3.6 Routage → Itineraires

```
gold.dim_spatial_grid_mapping (nodes) + gold.dim_gnn_adjacency (edges)
  │
  ├──→ graph.py : build NetworkX graph
  │    └── speed lookup JOIN traffic_features_live ON channel_id = properties_twgid
  │        ❌ [R-1] JOIN JAMAIS MATCH → toutes les vitesses = 30 km/h par defaut
  │
  ├──→ pathfinder.py : Dijkstra shortest path
  │    └── weight = distance / speed (speed toujours 30 → routage distance-only)
  │
  └──→ pathfinder_multimodal.py : Velov (walk→cycle→walk) + Car
       └── stations Velov via referentiel.v_lieux_velov_smart : OK
```

---

## 4. Audit widget par widget

### 4.1 Widgets Usager (15 fichiers)

| Widget | Source donnees | Table/API | Reel? | Fail |
|--------|---------------|-----------|-------|------|
| `traffic_widget.py` | `cached_traffic()` + `cached_traffic_predictions()` | `gold.traffic_features_live` + `gold.trafic_predictions` | **OUI** (horizon_h=1 seul) | `DashboardDataError` |
| `velov_widget.py` | `cached_velov_stations()` + `cached_velov_predictions()` | `silver.velov_clean` + `gold.velov_predictions` | **OUI** | `DashboardDataError` |
| `velov_map.py` | `get_velov_stations_geo()` + predictions | `silver.velov_clean` + `gold.velov_predictions` | **OUI** | `DashboardDataError` |
| `weather_widget.py` | `cached_weather_hourly()` | `silver.meteo_hourly` | **OUI** | `DashboardDataError` |
| `search_bar.py` | `cached_lyon_addresses_with_coords()` | `referentiel.lieux_lyon` | **OUI** (21 lieux) | `DashboardDataError` |
| `itinerary.py` | SQL direct + `compute_itinerary()` | `referentiel.lieux_lyon` + routage | **OUI** (vitesses fausses) | `DashboardDataError` |
| `velov_trip.py` | `plan_velov_trip()` | `silver.velov_clean` + `referentiel.lieux_lyon` | **OUI** | `DashboardDataError` |
| `lieux_velov_map.py` | `get_lieux_with_velov()` | `referentiel.v_lieux_velov_proches` | **OUI** | `DashboardDataError` |
| `recommendation_card.py` | Renderer pur (recoit dict) | — | N/A | N/A |
| `alternative_card.py` | Renderer pur | — | N/A | N/A |
| `alert_card.py` | Renderer pur (page alimente) | `silver.chantiers_actifs` | N/A | N/A |
| `alert_timeline.py` | Renderer pur | — | N/A | N/A |
| `alert_settings.py` | UI seul (checkboxes) | — | N/A | N/A |
| `favorite_list.py` | `st.session_state` | Pas de DB | **SESSION-ONLY** | — |
| `why_explainer.py` | Renderer pur (non utilise) | — | N/A | N/A |

### 4.2 Widgets Elu (16 fichiers)

| Widget | Source donnees | Table/API | Reel? | Fail |
|--------|---------------|-----------|-------|------|
| `kpi_cards.py` | `cached_elu_kpis_dict()` | `gold.mv_kpis_12_months` | **❌ VUE JAMAIS CREEE** | `DashboardDataError` |
| `executive_summary.py` | `cached_elu_kpis_dict()` | `gold.mv_kpis_12_months` | **❌ VUE JAMAIS CREEE** | `DashboardDataError` |
| `trend_chart.py` | `cached_elu_kpis_dict()` | `gold.mv_kpis_12_months` | **❌ VUE JAMAIS CREEE** | `DashboardDataError` |
| `top_decisions.py` | `cached_bottlenecks_top()` | `gold.infrastructure_bottlenecks` | **PARTIEL** — 6 champs fabriques | `DashboardDataError` |
| `bottleneck_ranking.py` | `cached_bottlenecks_top()` | idem | **PARTIEL** — idem | `DashboardDataError` |
| `bottleneck_map.py` | `cached_bottlenecks_top()` | idem | **PARTIEL** — + coords hardcodees | `DashboardDataError` |
| `roi_calculator.py` | `cached_bottlenecks_top()` | idem | **PARTIEL** — ROI fabrique | `DashboardDataError` |
| `project_selector.py` | `cached_amenagements_passes()` | `gold.amenagements_history` | **❌ TABLE JAMAIS CREEE** | `DashboardDataError` |
| `delta_kpis.py` | Renderer pur | — | N/A | N/A |
| `impact_projection.py` | Valeurs hardcodees | — | **❌ HARDCODED** (st.warning affiche) | N/A |
| `map_painter.py` | Dict coords hardcoded | — | **❌ HARDCODED** | N/A |
| `news_section.py` | Liste statique | — | **❌ HARDCODED** | N/A |
| `cost_estimate.py` | Calculatrice (taux ingenierie) | — | N/A (outil) | N/A |
| `pdf_generator.py` | Renderer (recoit sections) | — | N/A | N/A |
| `slide_builder.py` | UI seul | — | N/A | N/A |
| `template_selector.py` | UI seul | — | N/A | N/A |

### 4.3 Widgets Pro TCL (20 fichiers)

| Widget | Source donnees | Table/API | Reel? | Fail |
|--------|---------------|-----------|-------|------|
| `alert_ticker.py` | `cached_recent_alerts()` | `silver.chantiers_actifs` | **OUI** | `DashboardDataError` |
| `network_map.py` | `cached_buses_positions()` | `silver.tcl_vehicles_clean` | **OUI** | `DashboardDataError` |
| `line_kpis.py` | `cached_line_kpis()` | `gold.mv_line_kpis_live` | **OUI** (SQL script existe) | `DashboardDataError` |
| `line_selector.py` | `cached_tcl_lines()` | `gold.tcl_vehicle_realtime` | **OUI** | `DashboardDataError` |
| `line_comparison.py` | `cached_line_kpis()` | `gold.mv_line_kpis_live` | **OUI** | `DashboardDataError` |
| `otp_heatmap.py` | `cached_otp_heatmap_data()` | `gold.mv_otp_heatmap` | **OUI** (SQL script existe) | `st.info` si vide |
| `correlation_matrix.py` | `cached_infra_bottlenecks()` | `gold.infrastructure_bottlenecks` | **OUI** | `DashboardDataError` |
| `segment_table.py` | `cached_infra_bottlenecks()` | idem | **OUI** | `DashboardDataError` |
| `gnn_map.py` | `cached_spatial_mapping()` + predictions | `gold.dim_spatial_grid_mapping` + `gold.trafic_predictions` | **❌ CASSE** — merge `node_idx` inexistant | Silencieux |
| `pipeline_management.py` | Airflow API + DB freshness | Airflow REST + `bronze.*` | **MIXTE** — DAGs reel, alerts feed hardcoded | `DashboardDataError` |
| `model_monitoring.py` | MLflow API + DB | MLflow + `gold.velov_predictions` | **MIXTE** — MLflow/Velov reel, training_history/drift hardcodes | `st.warning` |
| `otp_filters.py` | UI seul | — | N/A | N/A |
| `otp_projection.py` | Calculatrice (formule +1 bus = +2.5pts OTP) | — | N/A (outil) | N/A |
| `cause_analysis.py` | Renderer (recoit segment dict) | — | N/A | N/A |
| `before_after_chart.py` | Renderer (recoit valeurs) | — | N/A | N/A |
| `frequency_slider.py` | UI seul | — | N/A | N/A |
| `format_selector.py` | UI seul | — | N/A | N/A |
| `export_button.py` | Stub | — | **STUB** ("a brancher") | N/A |
| `report_builder.py` | UI + line_selector | `gold.tcl_vehicle_realtime` | Partiel | N/A |
| `saeiv_export.py` | Hardcoded KPIs C3/C13 | — | **❌ HARDCODED** | N/A |

---

## 5. Problemes critiques (CRASH runtime)

Ces fonctions SQL crash silencieusement (exception capturee → DataFrame vide) :

| # | Fonction `db_query.py` | Probleme | Impact |
|---|------------------------|----------|--------|
| DQ-1 | `get_traffic_for_node()` | 10 colonnes renommees (`node_idx`, `speed_lag_1`, `hour_sin`, `temperature_c`...) | Crash silencieux → DF vide |
| DQ-2 | `get_weather_hourly()` | `temperature_c` vs `temperature_2m` (si DDL non ALTER-e) | Crash potentiel |
| DQ-3 | `get_recent_alerts()` | 2 params `(hours, limit)` mais 1 seul `%s` dans la query | Crash systematique |
| DQ-4 | `get_segments()` | Table `silver.trafic_segments_clean` n'existe pas | Crash systematique |
| DQ-5 | `get_correlation_matrix()` | Table `gold.fact_correlation_matrix` n'existe pas | Crash systematique |
| DL-1 | `load_bottlenecks_summary()` | Appelle `get_bottlenecks_summary()` qui n'existe pas dans `db_query.py` | AttributeError |

**Queries fonctionnelles confirmees** :
- `get_latest_traffic()` — `computed_at, channel_id, speed_kmh` : OK
- `get_traffic_predictions()` — `axis_key, horizon_h, speed_pred` : OK
- `get_buses_positions()` — `gold.tcl_vehicle_realtime` : OK
- `get_velov_*()` — `silver.velov_clean` : OK
- Referentiel (lieux_lyon, lieux_transports, lieux_calendrier) : OK

---

## 6. Problemes de qualite des donnees (silencieux)

| # | Code | Description | Consequence |
|---|------|-------------|-------------|
| G-1 | `silver_to_gold.py` | JOIN `properties_twgid` (int) = `channel_id` ("LYO00xxx") jamais match | `lat/lon` toujours NULL dans `gold.traffic_features_live` |
| D-1 | `dag_live_speed_retrain.py` | Seul `horizon_h=1` insere | Horizons 0 (30min) et 3 (3h) toujours vides |
| R-1 | `graph.py` | Speed lookup JOIN jamais match | Toutes vitesses = 30 km/h, routage distance-only |
| G-3 | `silver_to_gold.py` | Bottleneck lat/lon = `HASHTEXT() % 1000 / 10000 + 45.75` | Pins carte a des positions aleatoires |
| M-2b | `xgboost_velov.py` | Target = valeur actuelle, pas `LEAD(bikes, N)` | Modele predit le present, pas le futur |

---

## 7. Code mort a nettoyer

| Fichier | Quoi | Taille | Action |
|---------|------|--------|--------|
| `data_loader.py:961-1039` | `_FALLBACK_MOCK_MODELS` | ~80 lignes | Supprimer |
| `model_monitoring.py:20-92` | `MOCK_MODELS` dict | ~70 lignes | Supprimer |
| `pipeline_management.py:209-249` | Health check mock | ~40 lignes | Supprimer |
| `pathfinder_multimodal.py:276-281,539-549` | Branches demo | ~15 lignes | Supprimer |
| `mlflow_integration.py:318,326,382` | Branches demo | ~10 lignes | Supprimer |
| `db_query.py:78-82` | `_with_fallback()` | ~5 lignes | Supprimer |
| `data_cache.py` (25 fonctions) | Parametre `force_mock=False` | ~25 signatures | Supprimer param |

---

## 8. Plan de correction priorise

### Sprint 9 — Priorite 1 (CRITIQUE, bloquant qualite)

| # | Tache | Fichier(s) | Effort |
|---|-------|-----------|--------|
| 1 | Reconcilier `channel_id` ↔ `properties_twgid` (table mapping ou ALTER) | `silver_to_gold.py`, `graph.py`, `dim_spatial_grid_mapping` | 2-3h |
| 2 | Supprimer `_build_mock_graph()` fallback, lever `DashboardDataError` | `graph.py:79-81` | 30min |
| 3 | Supprimer fallback `synthetic()` dans retrain_gnn, faire echouer le DAG | `retrain_gnn.py:152-153` | 30min |
| 4 | Corriger `FEATURE_COLS` XGBoost speed : `lag_h1→lag_1`, `rolling_mean_h1→rolling_mean_3` | `xgboost_speed.py` | 1h |
| 5 | Ajouter `LEAD(bikes_available, 6/12)` au target velov | `xgboost_velov.py` + `silver_to_gold.py` | 2h |
| 6 | Creer vue `gold.mv_kpis_12_months` (3 widgets Elu en dependent) | Script SQL + `scripts/sql/` | 2h |
| 7 | Corriger `get_recent_alerts()` : aligner params/placeholders | `db_query.py` | 15min |
| 8 | Supprimer `get_segments()` et `get_correlation_matrix()` (tables inexistantes) | `db_query.py` | 15min |

### Sprint 10 — Priorite 2 (MOYEN, qualite donnees)

| # | Tache | Fichier(s) | Effort |
|---|-------|-----------|--------|
| 9 | Remplacer bottleneck ROI fabriques par calcul reel (ou `st.warning`) | `data_loader.py:624-639` | 3h |
| 10 | Implementer `_compute_confidence()` reel (fraicheur donnees) | `pathfinder.py:163` | 1h |
| 11 | Creer transform Silver pour `air_quality` | `bronze_to_silver.py` | 2h |
| 12 | Creer table `gold.amenagements_history` ou desactiver page Elu_3 | Script SQL ou page | 2h |
| 13 | Rendre metriques Accueil dynamiques (COUNT capteurs, COUNT predictions) | `Accueil.py:157,163` | 30min |
| 14 | Purger code mort (6 blocs identifies section 7) | Multiple | 1h |
| 15 | Corriger labels trompeurs (4 fichiers identifies section 2.4) | Multiple | 30min |

### Sprint 11 — Priorite 3 (GNN, optimisation)

| # | Tache | Fichier(s) | Effort |
|---|-------|-----------|--------|
| 16 | Installer `h3` dans image Airflow, calculer vrais `matrix_i/j` | `build_spatial_mapping.py` | 2h |
| 17 | Corriger `dataset.py` colonnes GNN (`sin_hour` etc.) | `training/stgcn/dataset.py` | 1h |
| 18 | Peupler horizons 0 et 3 dans predictions | `dag_live_speed_retrain.py` | 2h |
| 19 | Persistence favoris en DB | `favorite_list.py` + schema | 3h |

---

## Annexe — Schema des tables referentielles (OK)

Ces tables sont correctement peuplees et utilisees :

| Table | Contenu | Peuplement |
|-------|---------|------------|
| `referentiel.lieux_lyon` | 21 lieux Lyon | `scripts/sql/seed_lieux_lyon.sql` |
| `referentiel.lieux_transports` | Arrets/stations | `scripts/sql/seed_lieux_transports.sql` |
| `referentiel.lieux_calendrier` | Cadences TCL | `scripts/sql/seed_lieux_calendrier.sql` |
| `referentiel.v_lieux_velov_proches` | Vue Velov proches | `scripts/sql/create_lieux_velov_proches.sql` |
| `referentiel.v_lieux_velov_smart` | Vue Velov smart | SQL script |

---

## 9. Vision par persona — Plan stratégique (Sprint 8+, 2026-06-12)

Patrice demande (2026-06-12 10:50) : "dis moi ce que je dois améliorer
ou il faut une vision global par type d'utilisateur".

Cette section traduit les findings techniques (sections 1-8) en
priorités produit par persona. L'objectif : que chaque type d'utilisateur
ait une expérience **100% données réelles** à la démo Jedha.

### 9.1 USAGER (le plus solide — 8/15 widgets 100% réels)

| Widget | État | Action |
|--------|------|--------|
| Mon Trajet (carte) | ✅ Fonctionne, mais JOIN channel_id↔properties_twgid casse | Sprint 9 #1 : réconcilier le mapping |
| Itinéraire voiture | ⚠️ Routage 30 km/h partout (graph fallback) | Sprint 9 #2 : supprimer `_build_mock_graph()` |
| Vélov + marche | ✅ Smart routing (alternatives + voisines) | — |
| Favoris | ⚠️ Session-only, perdu au refresh | Sprint 11 #19 : persistance DB |
| Files d'attente | ✅ Vitesse prédite (baseline), pas ML entraîné | Sprint 9 #4 : FEATURE_COLS correctes |
| Alertes | ✅ Live | — |
| Recommandation card | ⚠️ stub | Sprint 9+ |
| Why explainer | ✅ Live | — |
| RGPD | ✅ Page conformité | — |

**Verdict Usager** : on est à 80% réels. Le sprint 9 doit corriger le
routage 30 km/h (critique UX). Le sprint 11 ajoute la persistance favoris.

### 9.2 PRO TCL (correct — 7/20 widgets 100% réels)

| Widget | État | Action |
|--------|------|--------|
| PCC Live (carte + alertes) | ✅ Live, focus H+1h (Sprint 8+) | — |
| Heatmap OTP | ✅ Vue matérialisée (155 lignes, 4416 triplets) | — |
| Correlation matrix | ⚠️ table `fact_correlation_matrix` inexistante | Sprint 9 #8 : supprimer le widget OU créer la vue |
| Simulateur (sélecteur ligne) | ✅ 155 lignes TCL | — |
| Line KPIs (sort + explore) | ✅ Vue matérialisée | — |
| Export SAEIV | ⚠️ KPIs C3/C13 hardcodés | Sprint 10 : brancher sur `gold.mv_line_kpis_live` |
| Pipeline management | ✅ Stack Prometheus UP (Sprint 8+) | — |
| Model monitoring | ⚠️ sections training_history / drift hardcodées | Sprint 11 : brancher sur MLflow métriques historiques |
| Export PDF | ⚠️ stub (WeasyPrint non intégré) | Sprint 13+ |

**Verdict Pro TCL** : dashboard de control room fonctionnel, mais
certains widgets exposent des données statiques (correlation matrix,
export, model monitoring) qui donnent l'impression d'un POC. Sprint 9
supprime les fonctions cassées, sprint 10+ branche sur les vraies données.

### 9.3 ÉLU (ROUGE — 0 widget 100% réel)

**C'est la zone la plus exposée** : un élu qui voit des chiffres
fabriqués perd toute confiance. Sprint 9 + 10 doivent corriger en
priorité.

| Widget | État | Action |
|--------|------|--------|
| Synthèse ville | ❌ `gold.mv_kpis_12_months` INEXISTANTE | **Sprint 9 #6 : créer la vue SQL** (débloque 3 widgets) |
| Bottlenecks (carte Folium) | ❌ 6 champs fabriqués (voyageurs_jour, cout_M_euros) | **Sprint 10 #9 : calcul réel OU `st.warning("estimation")`** |
| Avant/Après | ❌ `gold.amenagements_history` INEXISTANTE | **Sprint 10 #12 : créer la table OU désactiver la page** |
| Simulateur aménagement | ⚠️ st.warning("estimation") | OK pour démo, calculs réels Sprint 11+ |
| Rapport PDF | ❌ 4 KPIs statiques | Sprint 13+ |
| Impact projection | ⚠️ 4 métriques hardcodées (-12%, +18%...) | Sprint 11+ : brancher sur scénarios réels |
| ROI calculator | ❌ champs bottleneck fake | Sprint 10 #9 (corriger avec bottleneck réel) |
| News section | ⚠️ contenu statique acceptable pour démo | OK démo Jedha |

**Verdict Élu** : **0 widget 100% réel** actuellement. C'est inacceptable
pour une démo à des décideurs Grand Lyon. **3 corrections prioritaires
(Sprint 9-10)** débloquent la confiance :
1. Créer `gold.mv_kpis_12_months` (3 widgets) — 2h
2. Désactiver/afficher warning sur le ROI bidon — 1h
3. Désactiver Elu_3_Avant_Après OU créer `amenagements_history` — 2h

### 9.4 Récapitulatif

| Persona | Widgets OK | À corriger (Sprint 9) | À corriger (Sprint 10-11) | Verdict démo Jedha |
|---------|-----------|----------------------|---------------------------|------------------|
| Usager | 8/15 | 2 (routage, FEATURE_COLS) | 1 (favoris) | ✅ Acceptable, focus sprint 11+ |
| Pro TCL | 7/20 | 2 (correlation, model) | 3 (export, monitoring, GNN) | ⚠️ Correct mais "POC-feel" |
| Élu | **0/15** | **3 critiques** | 3 hardcodes | ❌ **Inacceptable démo décideur** |

### 9.5 Sprint 9 — Plan d'action immédiat (1 semaine)

**Jour 1-2 — Fiabilité core** (Sprint 9 priorité 1) :
- #1 Réconcilier channel_id↔properties_twgid (2-3h)
- #2 Supprimer `_build_mock_graph()` fallback (30min)
- #3 Supprimer fallback `synthetic()` retrain_gnn (30min)
- #4 Corriger FEATURE_COLS XGBoost speed (1h)
- #5 LEAD(bikes_available, 6/12) dans target velov (2h)

**Jour 3 — Élu priorité** (Sprint 9 priorité 2) :
- #6 Créer vue `gold.mv_kpis_12_months` (2h) → débloque 3 widgets Élu
- #7-8 Corriger 5 queries SQL cassées (1h)

**Jour 4 — Finalisation** (Sprint 9-10) :
- #9 Remplacer bottleneck ROI fabriqués par calcul réel OU `st.warning` (3h)
- #12 Créer `gold.amenagements_history` OU désactiver Elu_3 (2h)

**Total** : ~15h = 1 semaine de dev focus. Permet à la démo Jedha
d'être présentée avec une **vision Élu 80% réelle** (au lieu de 0%
actuellement), un **Usager 95% réel**, un **Pro TCL 90% réel**.

### 9.6 Hors-scope Sprint 9-11 — backlog post-Jedha

- Tests e2e Playwright (couverture persona Élu, déjà partiel)
- Monitoring drift Evidently (déjà câblé, Sprint 11+ activation)
- GTFS Overpass API (vrai A* routier, Sprint 12+)
- Grafana dashboards custom (Sprint 13+)
- WAF + Vault (production réelle, post-démo)
