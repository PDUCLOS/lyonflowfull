# LyonFlow — Dictionnaire de colonnes PostgreSQL

> Généré à partir du dump de schéma réel (`deploy/init-db.sql`) + migrations (`scripts/sql/migration_0*.sql`, `scripts/sql/create_*.sql`). Colonnes exactes pour les tables issues du dump ; pour les tables ajoutées après (velov_features, velov_predictions, app_users, user_favorites, road_network_*, amenagements_history, MLflow) les colonnes proviennent de `docs/POSTGRES_DATABASE_REFERENCE.md` (référentiel projet déjà curé) faute de CREATE TABLE retrouvé dans le repo.

Voir aussi : [`docs/diagrams/03_schema_postgres_colonnes.drawio`](diagrams/03_schema_postgres_colonnes.drawio) (ERD visuel, mêmes données) et [`docs/POSTGRES_DATABASE_REFERENCE.md`](POSTGRES_DATABASE_REFERENCE.md) (stats, index, fonctions, triggers).

---

## Schéma `bronze`

**Ingestion brute** — 8 sources externes, immutable, `raw_data JSONB` conservé à côté des colonnes extraites.

### `bronze.trafic_boucles` — Table

> */5min. CHECK chk_dual_geom : geom et geom_4326 NULL ou NOT NULL ensemble.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `fetched_at` | `timestamptz` |  |
| `troncon_id` | `varchar(50)` |  |
| `troncon_name` | `varchar(255)` |  |
| `debit` | `int` |  |
| `taux_occupation` | `real` |  |
| `vitesse` | `real` |  |
| `raw_data` | `jsonb` |  |
| `geom` | `geometry(Point,2154)` |  |
| `geom_4326` | `geometry(Point,4326)` |  |

### `bronze.tcl_vehicles` — Table

> */5min SIRI Lite.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `int` | PK |
| `fetched_at` | `timestamptz` |  |
| `vehicle_ref` | `varchar` |  |
| `line_ref_raw` | `varchar` |  |
| `line_ref` | `varchar` |  |
| `latitude` | `float8` |  |
| `longitude` | `float8` |  |
| `delay_seconds` | `int` |  |
| `recorded_at` | `timestamptz` |  |
| `raw_data` | `jsonb` |  |

### `bronze.velov` — Table

> */5min GBFS.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `fetched_at` | `timestamptz` |  |
| `station_id` | `varchar(50)` |  |
| `station_name` | `varchar(255)` |  |
| `num_bikes_available` | `int` |  |
| `num_docks_available` | `int` |  |
| `is_installed` | `bool` |  |
| `is_renting` | `bool` |  |
| `is_returning` | `bool` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `geom` | `geometry(Point,4326)` |  |

### `bronze.meteo` — Table

> */1h Open-Meteo.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `fetched_at` | `timestamptz` |  |
| `measurement_time` | `timestamptz` |  |
| `temperature_2m` | `real` |  |
| `relative_humidity_2m` | `real` |  |
| `precipitation` | `real` |  |
| `rain` | `real` |  |
| `weather_code` | `int` |  |
| `cloud_cover` | `real` |  |
| `wind_speed_10m` | `real` |  |
| `wind_gusts_10m` | `real` |  |
| `visibility` | `real` |  |
| `surface_pressure` | `real` |  |

### `bronze.air_quality` — Table

> */1h Open-Meteo AQ.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `fetched_at` | `timestamptz` |  |
| `measurement_time` | `timestamptz` |  |
| `pm10` | `real` |  |
| `pm2_5` | `real` |  |
| `nitrogen_dioxide` | `real` |  |
| `ozone` | `real` |  |
| `sulphur_dioxide` | `real` |  |
| `carbon_monoxide` | `real` |  |
| `european_aqi` | `int` |  |

### `bronze.chantiers` — Table

> 1x/jour 03h Grand Lyon.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `fetched_at` | `timestamptz` |  |
| `chantier_id` | `varchar(100)` |  |
| `nom` | `varchar(500)` |  |
| `type_perturbation` | `varchar(255)` |  |
| `severite` | `varchar(100)` |  |
| `date_debut` | `date` |  |
| `date_fin` | `date` |  |
| `commune` | `varchar(255)` |  |
| `geom` | `geometry(Geometry,4326)` |  |
| `raw_data` | `jsonb` |  |

### `bronze.chantiers_historique` — Table

> 1x/semaine, avec statut terminé.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `numero` | `varchar(100)` |  |
| `nature_chantier` | `varchar(255)` |  |
| `nature_travaux` | `varchar(255)` |  |
| `etat` | `varchar(100)` |  |
| `date_debut` | `date` |  |
| `date_fin` | `date` |  |
| `mesures_police` | `varchar(500)` |  |
| `commune` | `varchar(255)` |  |
| `code_insee` | `varchar(10)` |  |
| `geom` | `geometry(Geometry,4326)` |  |
| `raw_data` | `jsonb` |  |

### `bronze.chantiers_voirie` — Table

> 1x/jour. Rétention 90j.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `fetched_at` | `timestamptz` |  |
| `chantier_id` | `varchar(100)` |  |
| `nature_travaux` | `varchar(255)` |  |
| `date_debut` | `date` |  |
| `date_fin` | `date` |  |
| `commune` | `varchar(255)` |  |
| `geom` | `geometry(Geometry,4326)` |  |
| `raw_data` | `jsonb` |  |

### `bronze.pvotrafic_snapshots` — Table

> */5min. UNIQUE(code,collected_at). Source multimodal_status_grid.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `collected_at` | `timestamptz` |  |
| `code` | `text` |  |
| `libelle` | `text` |  |
| `etat` | `varchar(2)` |  |
| `vitesse_kmh` | `float8` |  |
| `longueur_m` | `int` |  |
| `fournisseur` | `text` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `est_a_jour` | `bool` |  |
| `sens` | `smallint` |  |
| `data_updated_at` | `timestamptz` |  |

### `bronze.comptages` — Table

> */1h comptages alternatifs.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `fetched_at` | `timestamptz` |  |
| `site_id` | `varchar(50)` |  |
| `channel_id` | `varchar(50)` |  |
| `mobility_type` | `varchar(50)` |  |
| `count_value` | `int` |  |
| `measurement_time` | `timestamptz` |  |
| `geom` | `geometry(Point,4326)` |  |
| `raw_data` | `jsonb` |  |

### `bronze.parkings` — Table

> */5min Grand Lyon parkings.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `fetched_at` | `timestamptz` |  |
| `parking_id` | `varchar(50)` |  |
| `parking_name` | `varchar(255)` |  |
| `available_spots` | `int` |  |
| `total_spots` | `int` |  |
| `occupation_rate` | `real` |  |
| `geom` | `geometry(Point,4326)` |  |
| `raw_data` | `jsonb` |  |

### `bronze.prix_carburants` — Table

> 1x/jour data.economie.gouv.fr.

| Colonne | Type | Détail |
|---|---|---|
| `collected_at` | `timestamptz` | PK |
| `carburant` | `text` | PK |
| `prix_moyen_eur_l` | `numeric(5,3)` |  |
| `prix_min` | `numeric(5,3)` |  |
| `prix_max` | `numeric(5,3)` |  |
| `nb_stations` | `int` |  |
| `zone` | `text` |  |

### `bronze.tomtom_traffic` — Table

> */15min TomTom Flow API. UNIQUE(tile_key,fetched_at). Cross-val vs Grand Lyon.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `current_speed_kmh` | `float8` |  |
| `free_flow_speed_kmh` | `float8` |  |
| `ratio` | `float8` | (current/free_flow) |
| `confidence` | `float8` | 0..1 |
| `current_travel_time_s` | `int` |  |
| `free_flow_travel_time_s` | `int` |  |
| `tile_key` | `text` | ex 45.76_4.85 |
| `fetched_at` | `timestamptz` |  |
| `raw_data` | `jsonb` |  |

### `bronze.tomtom_flow` — Table

> journalier, TomTom Flow Segment (legacy, distinct de tomtom_traffic).

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `collected_at` | `timestamptz` |  |
| `point_name` | `varchar(255)` |  |
| `query_lat` | `float8` |  |
| `query_lon` | `float8` |  |
| `current_speed_kmh` | `real` |  |
| `free_flow_speed_kmh` | `real` |  |
| `ratio_congestion` | `real` |  |
| `confidence` | `real` |  |
| `frc` | `varchar(10)` |  |
| `road_closure` | `bool` |  |

### `bronze.vitesse_limite_ref` — Table

> 1x/semaine Grand Lyon Code de la route.

| Colonne | Type | Détail |
|---|---|---|
| `code` | `text` | PK |
| `libelle` | `text` |  |
| `vitesse_limite` | `int` |  |
| `codetroncon` | `text` |  |
| `matched_distance_m` | `real` |  |
| `source` | `text` |  |
| `matched_at` | `timestamptz` |  |

### `bronze.jours_feries` — Table

> 1x/mois calendrier.api.gouv.fr.

| Colonne | Type | Détail |
|---|---|---|
| `date_ferie` | `date` | PK |
| `nom` | `varchar(100)` |  |

### `bronze.calendrier_scolaire` — Table

> 1x/mois Zone A, data.education.gouv.fr.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `zone` | `varchar(10)` |  |
| `description` | `varchar(255)` |  |
| `start_date` | `date` |  |
| `end_date` | `date` |  |
| `annee_scolaire` | `varchar(20)` |  |

### `bronze.trafic_vitesse_brute` — Table

> Legacy brut, non utilisé en dashboard.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `int` | PK |
| `fetched_at` | `timestamptz` |  |
| `raw_data` | `jsonb` |  |

### `bronze.vigilance_meteo` — Table *(nouveau, migration_045, 2026-07-05)*

> Vigilance météo-france département 69 (Rhône), phénomène canicule uniquement.
> Source : API publique Opendatasoft (miroir gratuit sans clé, dataset
> `weatherref-france-vigilance-meteo-departement`). Ingestion */6h
> (DAG `collect_vigilance_meteo`). Pas de silver (faible volume, lu direct).

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigserial` | PK |
| `fetched_at` | `timestamptz` |  |
| `departement` | `text` | `'69'` (Rhône, fixe) |
| `couleur_canicule` | `text` | vert / jaune / orange / rouge |
| `echeance` | `text` | `'J'` (aujourd'hui) \| `'J1'` (demain) — seul `'J'` collecté |
| `begin_time` | `timestamptz` | début de la période de validité |
| `end_time` | `timestamptz` | fin de la période de validité |
| `bulletin_date` | `timestamptz` | date du bulletin officiel (6h/16h) |
| `raw_data` | `jsonb` | enregistrement Opendatasoft brut |

UNIQUE(`departement, echeance, begin_time, fetched_at`).

### `bronze.healthy_pvotrafic` — Vue

> Codes ayant renvoyé >=50 obs/24h avec variabilité (détection capteur vivant).

| Colonne | Type | Détail |
|---|---|---|
| `code` | `text` |  |
| `n_obs` | `bigint` |  |
| `n_etats` | `bigint` |  |
| `n_vitesses` | `bigint` |  |
| `max_speed` | `float8` |  |

### `bronze.healthy_sensors` — Vue

> Capteurs trafic_boucles avec données valides <24h, hors 'Vitesse reglementaire'.

| Colonne | Type | Détail |
|---|---|---|
| `channel_id` | `text` |  |
| `n_obs` | `bigint` |  |
| `n_distinct_speeds` | `bigint` |  |
| `min_speed` | `float8` |  |
| `max_speed` | `float8` |  |
| `speed_range` | `float8` |  |

---

## Schéma `silver`

**Nettoyage / normalisation** — dédup, géométries doubles (2154+4326), filtre qualité.

### `silver.trafic_boucles_clean` — Table

> 90j. Dédup + géo double projection depuis bronze.trafic_boucles.

| Colonne | Type | Détail |
|---|---|---|
| `channel_id` | `text` | PK |
| `fetched_at` | `timestamptz` | PK |
| `speed_kmh` | `float8` |  |
| `vitesse_limite_kmh` | `float8` |  |
| `is_sanitary` | `bool` | capteur sain |
| `geom` | `geometry(Point,4326)` |  |
| `geom_2154` | `geometry(Point,2154)` |  |
| `silver_updated_at` | `timestamptz` |  |

### `silver.trafic_vitesse_propre` — Table

> 29.7 Go, 1.55M lignes, infini (pas de purge). Fallback referentiel.v_avg_speed_7d.

| Colonne | Type | Détail |
|---|---|---|
| `id_rue` | `int` |  |
| `properties_twgid` | `varchar(100)` | UK avec transformed_at |
| `properties_gid` | `bigint` |  |
| `properties_libelle` | `text` |  |
| `properties_sens` | `text` |  |
| `properties_etat` | `text` |  |
| `properties_vitesse` | `float8` |  |
| `properties_last_update` | `timestamptz` |  |
| `properties_est_a_jour` | `bool` |  |
| `speed_category` | `text` |  |
| `speed_color_map` | `text` |  |
| `geometry_wgs84_wkt` | `text` |  |
| `points_json` | `jsonb` |  |

### `silver.tcl_vehicles_clean` — Table

> 90j. UNIQUE(line_ref,journey_ref,stop_ref,measurement_time). Parse SIRI.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigserial` | PK |
| `fetched_at` | `timestamptz` |  |
| `measurement_time` | `timestamptz` |  |
| `line_ref` | `text` |  |
| `direction_ref` | `text` |  |
| `journey_ref` | `text` |  |
| `stop_ref` | `text` |  |
| `delay_seconds` | `int` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `raw_data` | `jsonb` |  |

### `silver.velov_clean` — Table

> 30j. UNIQUE(station_id,measurement_time). 3.3M+ lignes.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigserial` | PK |
| `fetched_at` | `timestamptz` |  |
| `measurement_time` | `timestamptz` |  |
| `station_id` | `text` |  |
| `station_name` | `text` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `num_bikes_available` | `int` |  |
| `num_docks_available` | `int` |  |
| `is_active` | `bool` |  |

### `silver.meteo_hourly` — Table

> 2 ans. Dédup par measurement_time.
>
> **Drift détecté (2026-07-05)** : `deploy/init-db.sql` (dump figé) liste
> `temperature_2m`/`precipitation`, mais le code vivant (`src/data/db_query.py::get_weather_hourly`,
> `src/transformation/bronze_to_silver.py::_transform_meteo`) lit/écrit
> `temperature_c`/`rain_mm` — la table a été altérée en prod sans mise à jour
> du dump versionné. Colonnes confirmées par le code vivant marquées ci-dessous ;
> les autres viennent du dump et n'ont pas été revérifiées ce tour-ci.

| Colonne | Type | Détail |
|---|---|---|
| `measurement_time` | `timestamptz` | PK |
| `temperature_c` | `float8` | confirmé code vivant (était `temperature_2m` dans le dump) |
| `rain_mm` | `float8` | confirmé code vivant (était `precipitation`/`rain` dans le dump) |
| `wind_speed_10m` | `float8` | confirmé code vivant |
| `humidity` | `float8` | confirmé code vivant |
| `weather_code` | `int` | confirmé code vivant |
| `cloud_cover` | `float8` | non revérifié (dump) |
| `visibility` | `float8` | non revérifié (dump) |
| `wind_gusts_10m` | `float8` | non revérifié (dump) |
| `uv_index` | `real` | non revérifié (dump) |
| `fetched_at` | `timestamptz` | non revérifié (dump) |
| `is_forecast` | `bool` | non revérifié (dump) |

### `silver.air_quality_clean` — Table *(nouveau, migration_045, 2026-07-05)*

> Dédup de `bronze.air_quality` par `measurement_time` (même pattern que `silver.meteo_hourly`).
> Alimente `gold.v_velov_safety_advisory`.

| Colonne | Type | Détail |
|---|---|---|
| `measurement_time` | `timestamptz` | PK |
| `european_aqi` | `int` | indice européen 1-6 — seule colonne utilisée pour le gating sécurité |
| `pm10` | `real` | |
| `pm2_5` | `real` | |
| `nitrogen_dioxide` | `real` | |
| `ozone` | `real` | |
| `carbon_monoxide` | `real` | |
| `fetched_at` | `timestamptz` | |

### `silver.chantiers_actifs` — Table

> Infini. UNIQUE(chantier_id,fetched_at). Trigger trg_silver_chantiers_is_active.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigserial` | PK |
| `fetched_at` | `timestamptz` |  |
| `chantier_id` | `text` |  |
| `titre` | `text` |  |
| `description` | `text` |  |
| `date_debut` | `date` |  |
| `date_fin` | `date` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `is_active` | `bool` | trigger recalcule depuis date_debut/date_fin |
| `raw_data` | `jsonb` |  |

---

## Schéma `gold`

**Trafic & ML** — features XGBoost, prédictions, référentiel capteurs, graphe spatial.

### `gold.channels_ref` — Table

> Référentiel statique ~1159 capteurs Grand Lyon.

| Colonne | Type | Détail |
|---|---|---|
| `channel_id` | `varchar(50)` | PK |
| `site_id` | `varchar(50)` |  |
| `site_name` | `varchar(255)` |  |
| `mobility_type` | `varchar(50)` |  |
| `direction` | `varchar(10)` |  |
| `sens` | `smallint` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `geom` | `geometry(Point,4326)` |  |
| `commune` | `varchar(10)` |  |
| `nb_voies` | `smallint` |  |
| `debit_max_horaire` | `int` |  |

### `gold.traffic_features_live` — Table

> 30j. 26 features ML XGBoost (FEATURE_COLS). */15min via transform_silver_to_gold.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `channel_id` | `text` |  |
| `fetched_at` | `timestamptz` |  |
| `computed_at` | `timestamptz` |  |
| `speed_kmh` | `float8` |  |
| `vitesse_limite_kmh` | `float8` |  |
| `lag_1` | `float8` | vitesse t-15min |
| `lag_2` | `float8` | t-30min |
| `lag_3` | `float8` | t-45min |
| `delta_current` | `float8` |  |
| `delta_1` | `float8` |  |
| `rolling_mean_3` | `float8` | moy. glissante 3 pas |
| `hour_of_day` | `smallint` |  |
| `day_of_week` | `smallint` |  |
| `is_weekend` | `smallint` |  |
| `sin_hour` | `float8` | encodage cyclique |
| `cos_hour` | `float8` |  |
| `sin_dow` | `float8` |  |
| `cos_dow` | `float8` |  |
| `channel_hash` | `float8` | hash(channel_id)%1e6 |
| `temperature_2m` | `float8` |  |
| `precipitation` | `float8` |  |
| `rain` | `float8` |  |
| `is_raining` | `smallint` |  |
| `visibility` | `float8` |  |
| `wind_speed_10m` | `float8` |  |
| `weather_code` | `smallint` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `importance_code` | `smallint` |  |
| `x_2154` | `float8` |  |
| `y_2154` | `float8` |  |
| `is_vacances` | `bool` |  |
| `is_ferie` | `bool` |  |

### `gold.dim_spatial_grid_mapping` — Table

> ~3946 nœuds H3 res.13. Trigger trg_dim_spatial_has_lat_lon (real_string => lat/lon NOT NULL).

| Colonne | Type | Détail |
|---|---|---|
| `node_idx` | `int` |  |
| `properties_twgid` | `varchar(100)` | PK |
| `matrix_i` | `int` |  |
| `matrix_j` | `int` |  |
| `h3_id` | `varchar(15)` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `updated_at` | `timestamptz` |  |

### `gold.dim_spatial_adjacency` — Table

> Ex dim_gnn_adjacency (migration_040, 2026-07-01). 58061 arêtes K=2. Sert Axe2 mv_congestion_propagation_pairs, indépendant du GNN archivé.

| Colonne | Type | Détail |
|---|---|---|
| `node_u` | `int` | PK |
| `node_v` | `int` | PK |
| `is_connected` | `bool` |  |
| `updated_at` | `timestamptz` |  |

### `gold.trafic_predictions` — Table

> 7j. Prédictions XGBoost H+1h pré-calculées. */30min dag_live_speed_retrain.

| Colonne | Type | Détail |
|---|---|---|
| `axis_key` | `text` | PK, = code tronçon |
| `horizon_h` | `int` | PK, 1=H+1h |
| `calculated_at` | `timestamptz` | PK |
| `speed_pred` | `numeric(6,2)` |  |
| `etat_pred` | `char(1)` | V/O/R/G |
| `color` | `varchar(7)` |  |
| `vitesse_limite_kmh` | `numeric(6,2)` |  |
| `label` | `varchar(256)` |  |
| `model_version` | `varchar(32)` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `x_2154` | `float8` |  |
| `y_2154` | `float8` |  |

### `gold.predictions_vs_actuals` — Table

> Backtesting historique (distinct de gold.trafic_predictions, table figée depuis archivage GNN — cf. bugfix 2026-07 qui bascule les widgets sur trafic_predictions live).

| Colonne | Type | Détail |
|---|---|---|
| `axis_key` | `text` | PK |
| `horizon_h` | `int` | PK |
| `calculated_at` | `timestamptz` | PK |
| `target_at` | `timestamptz` |  |
| `matched_at` | `timestamptz` |  |
| `speed_pred` | `numeric(6,2)` |  |
| `speed_actual` | `numeric(6,2)` |  |
| `abs_error` | `numeric(6,2)` | GENERATED abs(pred-actual) |
| `signed_error` | `numeric(6,2)` | GENERATED pred-actual |
| `inserted_at` | `timestamptz` |  |

### `gold.h3_trafic_live` — Table

> Trafic agrégé par hexagone H3 res.10.

| Colonne | Type | Détail |
|---|---|---|
| `hex_id` | `text` | PK |
| `sens` | `varchar(4)` | PK |
| `etat` | `char(1)` | CHECK V/O/R/G |
| `mean_speed` | `float8` |  |
| `nb_troncons` | `int` |  |
| `computed_at` | `timestamptz` |  |

### `gold.h3_trafic_predictions` — Table

> Prédictions agrégées par hex x horizon.

| Colonne | Type | Détail |
|---|---|---|
| `hex_id` | `text` | PK |
| `horizon_h` | `int` | PK |
| `etat_pred` | `char(1)` |  |
| `etat_label` | `varchar(20)` |  |
| `speed_pred` | `numeric(6,2)` |  |
| `vitesse_limite` | `numeric(6,2)` |  |
| `label` | `varchar(256)` |  |
| `axis_key` | `text` |  |
| `libelle` | `varchar(255)` |  |
| `calculated_at` | `timestamptz` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |

### `gold.xgb_training_set` — Table

> 14j, 72K lignes. Training set matérialisé (self-join +60min). 1x/jour 02h30 build_xgb_training_set.

| Colonne | Type | Détail |
|---|---|---|
| `feature_id` | `bigserial` | PK |
| `computed_at` | `timestamptz` |  |
| `target_computed_at` | `timestamptz` | = computed_at + 60min |
| `channel_id` | `text` |  |
| `channel_hash` | `float8` |  |
| `target_speed` | `float8` | cible du modèle |
| `speed_kmh` | `float8` |  |
| `lag_1` | `float8` |  |
| `lag_2` | `float8` |  |
| `lag_3` | `float8` |  |
| `rolling_mean_3` | `float8` |  |
| `sin_hour` | `float8` |  |
| `cos_hour` | `float8` |  |
| `temperature_2m` | `float8` |  |
| `precipitation` | `float8` |  |
| `is_vacances` | `bool` |  |
| `is_ferie` | `bool` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `importance_code` | `smallint` |  |
| `created_at` | `timestamptz` |  |

### `gold.model_drift_reports` — Table

> 30j. 1x/jour 06h drift monitoring Evidently.

| Colonne | Type | Détail |
|---|---|---|
| `computed_at` | `timestamptz` | PK |
| `dataset_drift` | `bool` |  |
| `drift_share` | `numeric(5,4)` |  |
| `n_ref` | `int` |  |
| `n_current` | `int` |  |
| `ref_from` | `timestamptz` |  |
| `ref_to` | `timestamptz` |  |
| `current_from` | `timestamptz` |  |
| `current_to` | `timestamptz` |  |
| `report` | `jsonb` | rapport Evidently complet |

### `gold.road_importance_ref` — Table

> 2.34M lignes. Importance réseau routier par hex x route.

| Colonne | Type | Détail |
|---|---|---|
| `hex_id` | `text` | PK |
| `road_gid` | `int` | PK |
| `road_name` | `text` |  |
| `importance` | `text` |  |
| `importance_code` | `smallint` |  |
| `sens` | `text` |  |

### `gold.sensor_road_importance` — Table

> Sert gold.v_source_health.

| Colonne | Type | Détail |
|---|---|---|
| `channel_id` | `text` | PK |
| `importance_code` | `smallint` |  |
| `importance_label` | `text` |  |

### `gold.stgcn_predictions_live` — Table

> Modèle GNN archivé Sprint 24+ — table conservée traçabilité RNCP, plus alimentée en prod.

| Colonne | Type | Détail |
|---|---|---|
| `predicted_for` | `timestamptz` | PK |
| `input_window_end` | `timestamptz` |  |
| `node_idx` | `int` | PK |
| `properties_twgid` | `varchar(100)` |  |
| `predicted_speed_kmh` | `float8` |  |
| `created_at` | `timestamptz` |  |

### `gold.features_traffic` — Table

> Table ML historique pré-Sprint8, distincte de traffic_features_live (colonnes brutes pré-agrégation).

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigint` | PK |
| `channel_id` | `varchar(50)` |  |
| `measurement_time` | `timestamptz` |  |
| `count_value` | `int` |  |
| `hour_of_day` | `smallint` |  |
| `day_of_week` | `smallint` |  |
| `month` | `smallint` |  |
| `is_weekend` | `bool` |  |
| `sin_hour` | `real` |  |
| `cos_hour` | `real` |  |
| `sin_dow` | `real` |  |
| `cos_dow` | `real` |  |
| `avg_temperature` | `real` |  |
| `avg_precipitation` | `real` |  |
| `weather_code` | `smallint` |  |
| `mobility_type` | `varchar(50)` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `lag_1h..lag_168h` | `real` | 8 lags historiques |
| `rolling_mean_3h/6h/24h` | `real` |  |
| `delta_1h` | `real` |  |

### `gold.dim_temps` — Table

> Dimension temps, granularité 5min, ~10 ans (315K lignes). Sert calculs weekly/monthly.

| Colonne | Type | Détail |
|---|---|---|
| `tranche_5min` | `timestamptz` | PK |
| `tranche_15min` | `timestamptz` |  |
| `tranche_horaire` | `timestamptz` |  |
| `date_calcul` | `date` |  |
| `heure` | `smallint` |  |
| `minute_5` | `smallint` |  |
| `jour_semaine` | `smallint` |  |
| `is_weekend` | `bool` |  |
| `mois` | `smallint` |  |
| `trimestre` | `smallint` |  |
| `saison` | `varchar(10)` |  |
| `is_ferie` | `bool` |  |
| `is_vacances_a` | `bool` |  |
| `annee` | `smallint` |  |

### `gold.channel_tomtom_mapping` — Table

> Mapping capteur GL <-> tuile TomTom. Sert cross-validation Sprint 13+.

| Colonne | Type | Détail |
|---|---|---|
| `channel_id` | `varchar(50)` | PK, FK -> channels_ref |
| `tomtom_point_name` | `varchar(255)` |  |
| `tomtom_lat` | `float8` |  |
| `tomtom_lon` | `float8` |  |
| `distance_m` | `int` |  |

### `gold.v_velov_safety_advisory` — Vue *(nouveau, migration_045, 2026-07-05)*

> JOIN dernier `silver.air_quality_clean` (fenêtre 3h) + dernière vigilance
> canicule `bronze.vigilance_meteo` dept 69 (fenêtre 12h). Renvoie toujours
> exactement 1 ligne (statut `unknown` si aucune des deux sources récente —
> jamais de faux "ok"). Sert `weather_widget`/`velov_trip`/`velov_widget`
> (persona Usager) via `dashboard/components/velov_safety_banner.py`.
>
> Les 8 autres vues `gold.*` non matérialisées (v_source_health,
> v_coherence_tomtom_vs_grandlyon, v_xgb_accuracy_summary, ...) sont
> documentées dans `POSTGRES_DATABASE_REFERENCE.md` §5, pas reprises ici.

| Colonne | Type | Détail |
|---|---|---|
| `european_aqi` | `int` | indice européen 1-6, NULL si pas de mesure récente |
| `couleur_canicule` | `text` | vert/jaune/orange/rouge, NULL si pas de bulletin récent |
| `status` | `text` | `ok` \| `warning` \| `severe` \| `unknown` |
| `reason` | `text` | message humain (ex. "Pollution dégradée (indice européen 4/6)") |
| `aqi_measured_at` | `timestamptz` | horodatage de la mesure AQI utilisée |
| `vigilance_bulletin_at` | `timestamptz` | horodatage du bulletin vigilance utilisé |

---

## Schéma `gold`

**Bus / Multimodal / Vélov / Qualité** — KPIs, MVs spatiales, référentiels tarifs/santé.

### `gold.bus_delay_segments` — Table

> UNIQUE(line_ref,segment_id,hour_of_day,day_of_week). Retard agrégé. */15min.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigserial` | PK |
| `line_ref` | `text` |  |
| `segment_id` | `text` |  |
| `hour_of_day` | `smallint` |  |
| `day_of_week` | `smallint` |  |
| `is_vacances` | `bool` |  |
| `is_ferie` | `bool` |  |
| `weather_code` | `int` |  |
| `avg_delay_seconds` | `real` |  |
| `p90_delay_seconds` | `real` |  |
| `n_observations` | `int` |  |
| `computed_at` | `timestamptz` |  |

### `gold.infrastructure_bottlenecks` — Table

> VIRÉ Sprint 22++ : JOIN global/heure remplacé par mv_bus_traffic_spatial (spatial 100m). Table conservée, plus alimentée.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigserial` | PK |
| `segment_id` | `text` |  |
| `line_ref` | `text` |  |
| `diagnosis` | `text` | infra|operations|bus_lane_ok|ok |
| `bus_delay_seconds` | `real` |  |
| `traffic_speed_kmh` | `real` |  |
| `traffic_congestion` | `real` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `computed_at` | `timestamptz` |  |
| `n_observations` | `int` |  |

### `gold.tcl_vehicle_realtime` — Table

> Snapshot dernières positions TCL. UNIQUE(recorded_at,vehicle_ref).

| Colonne | Type | Détail |
|---|---|---|
| `id` | `int` | PK |
| `recorded_at` | `timestamptz` |  |
| `vehicle_ref` | `varchar` |  |
| `line_ref` | `varchar` |  |
| `latitude` | `float8` |  |
| `longitude` | `float8` |  |
| `delay_seconds` | `int` |  |
| `is_delayed` | `bool` |  |

### `gold.mv_bus_traffic_spatial` — Vue matérialisée

> */15min CONCURRENTLY. JOIN spatial 0.001°(~100m) tcl_vehicle_realtime x channels_ref. Remplace infrastructure_bottlenecks. Sert Elu_2 Bottlenecks.

| Colonne | Type | Détail |
|---|---|---|
| `segment_id / line_ref` | `text` |  |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `avg_delay_s` | `real` |  |
| `diagnosis` | `text` | infra|operations|bus_lane_ok|ok |
| `n_observations` | `int` |  |

### `gold.mv_multimodal_grid` — Vue matérialisée

> */10min CONCURRENTLY. Fusion traffic_features_live+tcl_vehicle_realtime+velov_clean+meteo_hourly. Axe1. Sert multimodal_heatmap Pro_TCL.

| Colonne | Type | Détail |
|---|---|---|
| `grid_lat/grid_lon` | `numeric` | grille 0.01°(~1km) |
| `score_multimodal` | `numeric` | 0-10 |
| `diagnostic` | `text` | dominant : trafic/bus/velov/meteo |
| `vitesse_voiture_kmh` | `float8` |  |
| `retard_tcl_sec` | `numeric` |  |
| `velos_dispo` | `bigint` |  |

### `gold.mv_line_kpis_live` — Vue matérialisée

> Horaire. 155 lignes TCL. Sert line_kpis Pro_TCL.

| Colonne | Type | Détail |
|---|---|---|
| `line_ref` | `text` |  |
| `otp_pct` | `numeric` | ponctualité |
| `avg_delay_s` | `numeric` |  |
| `charge_pct` | `numeric` |  |
| `frequence_min` | `numeric` |  |

### `gold.mv_otp_heatmap` — Vue matérialisée

> Horaire. 4416 cellules x 7j. 7.5MB. Sert otp_heatmap Pro_2.

| Colonne | Type | Détail |
|---|---|---|
| `line_id` | `text` | PK |
| `date` | `date` | PK |
| `hour` | `int` | PK |
| `otp_pct` | `numeric` |  |
| `n_obs` | `int` |  |

### `gold.mv_sensor_saturation` — Vue matérialisée

> */15min DAG refresh_sensor_saturation. Fix migration_041 (borné 24h, ex full-scan). Sert sensor_saturation Pro_TCL.

| Colonne | Type | Détail |
|---|---|---|
| `channel_id` | `text` | PK |
| `pct_v85_saturation` | `numeric` |  |
| `amplitude_kmh` | `numeric` |  |
| `n_obs_7d/24h` | `int` |  |

### `gold.mv_velov_transit_coupling` — Vue matérialisée

> */15min. Axe4 Sprint17. Sert modal_shift_alert Pro_TCL.

| Colonne | Type | Détail |
|---|---|---|
| `station_id` | `text` | PK |
| `z_score` | `numeric` | vélos dispo vs moyenne |
| `anomaly_detected` | `bool` | z<-2 |
| `distance_tc_m` | `numeric` | <300m |

### `gold.mv_congestion_propagation_pairs` — Vue matérialisée

> 1x/jour 04h. Axe2 Sprint15+. Sert propagation_map Pro_TCL.

| Colonne | Type | Détail |
|---|---|---|
| `channel_id_source` | `text` |  |
| `channel_id_target` | `text` |  |
| `lag_minutes` | `int` |  |
| `correlation` | `numeric` | cross-corr Granger simplifié |

### `gold.mv_meteo_impact` — Vue matérialisée

> 1x/jour 04h. Axe7. Sert meteo_impact Pro_TCL.

| Colonne | Type | Détail |
|---|---|---|
| `mode` | `text` | voiture/velov/bus |
| `weather_bucket` | `text` |  |
| `impact_pct` | `numeric` | delta vitesse/cadence vs normale |

### `gold.mv_xgb_vs_tomtom` — Vue matérialisée

> */30min. ST_DWithin 200m + ±10min. Sert backtest_dashboard Pro_7 + drift Evidently.

| Colonne | Type | Détail |
|---|---|---|
| `channel_id` | `text` |  |
| `tile_key` | `text` |  |
| `xgb_speed_pred` | `numeric` |  |
| `tomtom_speed_kmh` | `numeric` |  |
| `delta_kmh` | `numeric` |  |
| `matched_at` | `timestamptz` |  |

### `gold.mv_fact_traffic_pivot` — Vue matérialisée

> Horaire. 92MB. Pivot temps x capteur. Sert correlation_matrix Pro_3.

| Colonne | Type | Détail |
|---|---|---|
| `timestamp` | `timestamptz` |  |
| `node_idx` | `int` |  |
| `properties_vitesse` | `float8` |  |

### `gold.tarifs_modes` — Table

> UNIQUE(mode,produit,age_min,age_max). Référentiel tarifs TCL/Vélov/parkings, Sprint15+. Manuel.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `serial` | PK |
| `mode` | `text` |  |
| `produit` | `text` |  |
| `produit_label` | `text` |  |
| `age_min` | `int` |  |
| `age_max` | `int` |  |
| `prix_eur` | `numeric(6,3)` |  |
| `duree_min` | `int` |  |
| `notes` | `text` |  |
| `updated_at` | `timestamptz` |  |

### `gold.network_health_history` — Table

> 7j. */15min DAG record_network_health, insère gold.fn_network_health_score(). Sert network_health_gauge Elu_1.

| Colonne | Type | Détail |
|---|---|---|
| `recorded_at` | `timestamptz` | PK |
| `score` | `numeric(5,2)` | CHECK 0-100 |
| `traffic_score` | `numeric(5,2)` |  |
| `tcl_score` | `numeric(5,2)` |  |
| `velov_score` | `numeric(5,2)` |  |
| `meteo_score` | `numeric(5,2)` |  |
| `available_sources` | `text[]` |  |

### `gold.data_quality_log` — Table

> Append-only. 3 validators x N sous-checks, 1x/jour 04h. Sert quality_log widget.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigserial` | PK |
| `checked_at` | `timestamptz` |  |
| `table_name` | `text` |  |
| `check_name` | `text` |  |
| `status` | `text` | CHECK ok/warning/critical |
| `metric_value` | `float8` |  |
| `threshold` | `float8` |  |
| `details` | `text` |  |

### `gold.velov_features` — Table

> 30j. Label encoding stations (pas one-hot, économie RAM 9GB->500MB).

| Colonne | Type | Détail |
|---|---|---|
| `station_id_encoded` | `int` | PK |
| `measurement_time` | `timestamptz` | PK |
| `station_id` | `text` |  |
| `lag_1/2/3` | `float8` | vélos dispo décalés |
| `rolling_mean_3` | `float8` |  |
| `sin_hour/cos_hour` | `float8` |  |
| `sin_dow/cos_dow` | `float8` |  |
| `temperature_2m` | `float8` |  |
| `precipitation` | `float8` |  |
| `is_vacances` | `bool` |  |
| `is_ferie` | `bool` |  |

### `gold.velov_predictions` — Table

> 30j. H+1h (H+30min plus entraîné depuis VPS-6). */1h :50 dag_velov_retrain.

| Colonne | Type | Détail |
|---|---|---|
| `station_id` | `text` |  |
| `horizon_minutes` | `int` | 30 ou 60 |
| `predicted_bikes` | `float8` |  |
| `predicted_at` | `timestamptz` |  |

### `gold.app_users` — Table

> Utilisateurs dashboard 3 personas protégés.

| Colonne | Type | Détail |
|---|---|---|
| `user_id` | `serial` | PK |
| `username` | `text` | UNIQUE |
| `persona_id` | `text` | CHECK pro_tcl/elu/admin |
| `password_hash` | `text` |  |

### `gold.road_network_nodes` — Table

> Legacy Overpass API (gold, distinct de osm.ways_vertices_pgr).

| Colonne | Type | Détail |
|---|---|---|
| `osm_id` | `bigint` | PK |
| `lat` | `float8` | CHECK -90..90 |
| `lon` | `float8` | CHECK -180..180 |

### `gold.road_network_edges` — Table

> Legacy graphe routier gold (remplacé par osm.ways Sprint18 pour le routing).

| Colonne | Type | Détail |
|---|---|---|
| `from_osm_id` | `bigint` | FK -> road_network_nodes |
| `to_osm_id` | `bigint` | FK |
| `length_m` | `float8` | CHECK >=0 |

### `gold.amenagements_history` — Table

> Sert widget amenagements_passes (Elu_3 Avant/Après).

| Colonne | Type | Détail |
|---|---|---|
| `amenagement_id` | `serial` | PK |
| `nom` | `text` |  |
| `date_travaux` | `date` |  |
| `avant_apres` | `jsonb` | stats trafic/retard avant/après |

### `gold.mv_twgid_to_lyo` — Vue matérialisée

> Mapping identifiants H3 <-> boucles Grand Lyon. Sert osm.mv_sensor_to_way.

| Colonne | Type | Détail |
|---|---|---|
| `properties_twgid` | `text` |  |
| `channel_id` | `text` | format LYO000xx |

---

## Schéma `osm`

**Réseau routier OSM / pgRouting** — routing voiture temps réel.

### `osm.ways` — Table

> ~101k arêtes, import osm2pgrouting (Geofabrik Rhône-Alpes). cost/reverse_cost injectés par osm.refresh_traffic_costs().

| Colonne | Type | Détail |
|---|---|---|
| `gid` | `bigserial` | PK |
| `class_id` | `int` |  |
| `length` | `float8` |  |
| `length_m` | `float8` |  |
| `name` | `text` |  |
| `source` | `bigint` | FK -> ways_vertices_pgr.id |
| `target` | `bigint` | FK -> ways_vertices_pgr.id |
| `cost` | `float8` | maj */15min |
| `reverse_cost` | `float8` | maj */15min |
| `cost_default` | `float8` | maxspeed OSM fixe |
| `maxspeed_kmh` | `float8` | def 50 |
| `one_way` | `int` |  |
| `the_geom` | `geometry(LineString,4326)` |  |
| `source_osm` | `bigint` |  |
| `target_osm` | `bigint` |  |

### `osm.ways_vertices_pgr` — Table

> ~87k sommets du réseau routier.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigserial` | PK |
| `cnt` | `int` |  |
| `chk` | `int` |  |
| `ein` | `int` |  |
| `eout` | `int` |  |
| `the_geom` | `geometry(Point,4326)` |  |

### `osm.configuration` — Table

> Config osm2pgrouting : tags routiers -> priorité/vitesse.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `serial` | PK |
| `tag_id` | `int` |  |
| `tag_key` | `text` |  |
| `tag_value` | `text` |  |
| `priority` | `float8` | def 1.0 |
| `maxspeed` | `float8` | def 50 |

### `osm.sensor_positions` — Table

> ~1159 capteurs, peuplé depuis gold.traffic_features_live (14j).

| Colonne | Type | Détail |
|---|---|---|
| `channel_id` | `text` | PK |
| `lat` | `float8` |  |
| `lon` | `float8` |  |
| `geom` | `geometry(Point,4326)` |  |

### `osm.pointsofinterest` — Table

> POIs OSM (Geofabrik). Usage potentiel itinéraire.

| Colonne | Type | Détail |
|---|---|---|
| `pid` | `bigserial` | PK |
| `osm_id` | `bigint` | UNIQUE |
| `name` | `text` |  |
| `geom` | `geometry` |  |

### `osm.mv_sensor_to_way` — Vue matérialisée

> LATERAL KNN <->. 41737 arêtes couvertes. Critique pour refresh_traffic_costs().

| Colonne | Type | Détail |
|---|---|---|
| `way_gid` | `bigint` | PK, FK -> ways.gid |
| `lyo_channel_id` | `text` |  |
| `properties_twgid` | `text` |  |
| `distance_m` | `float8` | <200m |

---

## Schéma `referentiel`

**Lieux & modes de transport** — 21 lieux emblématiques, dessertes, cadences, maillage Vélov.

### `referentiel.lieux_lyon` — Table

> 21 lieux emblématiques Lyon, seed manuel. Sert search_bar + itinerary.

| Colonne | Type | Détail |
|---|---|---|
| `lieu_id` | `serial` | PK |
| `name` | `text` | UNIQUE |
| `lon` | `float8` |  |
| `lat` | `float8` |  |
| `type` | `text` | gare/place/quartier/parc/universite/banlieue/monument |
| `is_active` | `bool` | def true, soft delete |
| `created_at` | `timestamptz` |  |
| `updated_at` | `timestamptz` |  |

### `referentiel.lieux_transports` — Table

> 56 dessertes. UNIQUE(lieu_id,line_ref,stop_name).

| Colonne | Type | Détail |
|---|---|---|
| `id` | `serial` | PK |
| `lieu_id` | `int` | FK -> lieux_lyon ON DELETE CASCADE |
| `line_ref` | `text` | ex T1,M_A,C3,38 |
| `line_mode` | `text` | metro/tram/bus/funicular |
| `stop_name` | `text` |  |
| `distance_m` | `int` | à pied, estimé |
| `rank` | `int` | 1=plus proche |
| `is_active` | `bool` |  |
| `source` | `text` | expert|gtfs |
| `created_at` | `timestamptz` |  |
| `updated_at` | `timestamptz` |  |

### `referentiel.lieux_calendrier` — Table

> 223 cadences. UNIQUE(line_ref,day_type,time_bucket). Peuplé depuis gold.tcl_vehicle_realtime.

| Colonne | Type | Détail |
|---|---|---|
| `id` | `serial` | PK |
| `line_ref` | `text` |  |
| `day_type` | `text` | CHECK weekday/saturday/sunday_holiday/vacation |
| `time_bucket` | `text` | ex '06:00' |
| `cadence_min_per_vehicle` | `float8` |  |
| `n_observations` | `int` |  |
| `confidence` | `text` | low/medium/high |
| `computed_at` | `timestamptz` |  |

### `referentiel.v_avg_speed_7d` — Vue

> Fallback si gold.trafic_predictions vide.

| Colonne | Type | Détail |
|---|---|---|
| `node_idx/vitesse_moyenne_7j` | `—` |  |

### `referentiel.v_cadence_observed_7d` — Vue

> Base brute 7j glissants de lieux_calendrier.

| Colonne | Type | Détail |
|---|---|---|
| `line_ref,tranche,day_type,n_obs` | `—` |  |

### `referentiel.v_cadence_summary` — Vue

> Cadence + confidence = nb observations.

| Colonne | Type | Détail |
|---|---|---|
| `line,tranche,day_type,confidence` | `—` |  |

### `referentiel.v_velov_neighbors` — Vue

> Maillage Vélov <200m, ~10-20k paires.

| Colonne | Type | Détail |
|---|---|---|
| `station_id,neighbor_id,distance_m` | `—` |  |

### `referentiel.v_lieux_velov_proches` — Vue

> Top3 bornes proches par lieu (haversine+dispo).

| Colonne | Type | Détail |
|---|---|---|
| `lieu_id,station_id,rank<=3` | `—` |  |

### `referentiel.v_lieux_velov_plus_proche` — Vue

> Top1 de v_lieux_velov_proches.

| Colonne | Type | Détail |
|---|---|---|
| `lieu_id,station_id` | `—` |  |

### `referentiel.v_lieux_velov_smart` — Vue

> Score composite distance+vélos+docks. Fix migration_042/043 (index+fenêtre 15min).

| Colonne | Type | Détail |
|---|---|---|
| `lieu_id,station_id,score,status` | `—` | VIDE/PLEINE/FAIBLE/OK |

---

## Schéma `public`

**MLflow + PostGIS + favoris** — tracking ML géré par le serveur MLflow.

### `public.user_favorites` — Table

> Favoris dashboard par utilisateur.

| Colonne | Type | Détail |
|---|---|---|
| `user_id` | `text` | PK |
| `id` | `serial` | PK |
| `favorite_type` | `text` |  |
| `payload` | `jsonb` |  |

### `public.spatial_ref_sys` — Table

> Registre SRID PostGIS.

| Colonne | Type | Détail |
|---|---|---|
| `srid` | `int` | PK |
| `...` | `—` | standard PostGIS ~8500 SRIDs |

### `public.MLflow (15 tables)` — Table

> Tracking + Registry MLflow 2.12. Géré par le serveur MLflow, non modifié à la main.

| Colonne | Type | Détail |
|---|---|---|
| `runs` | `—` | PK run_uuid |
| `experiments` | `—` | PK experiment_id |
| `registered_models` | `—` | PK name |
| `model_versions` | `—` |  |
| `registered_model_aliases` | `—` |  |
| `metrics` | `—` | PK(key,timestamp,step,run_uuid,value,is_nan) |
| `params, tags, datasets, inputs...` | `—` | standard MLflow schema |

## Schéma `rgpd`

**Audit conformité** — traçabilité des purges de rétention (Bronze/Silver/Gold).

### `rgpd.purge_log` — Table *(migration_046)*

> Une ligne par purge exécutée par `dags/maintenance/maintenance.py::_purge_table()` (DAG `purge_bronze`).

| Colonne | Type | Détail |
|---|---|---|
| `id` | `bigserial` | PK |
| `purged_at` | `timestamptz` | Défaut `now()`. Index `idx_rgpd_purge_log_purged_at` (DESC) |
| `schema_name` | `text` | Schéma de la table purgée (ex: `bronze`) |
| `table_name` | `text` | Nom de la table purgée (ex: `trafic_boucles`) |
| `rows_purged` | `bigint` | Nombre de lignes supprimées |
| `retention_days` | `int` | Rétention appliquée (jours) |
