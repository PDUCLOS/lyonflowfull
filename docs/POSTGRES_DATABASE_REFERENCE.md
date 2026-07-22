# LyonFlow — Référentiel de la base PostgreSQL

> **Document de référence** sur la base PostgreSQL du projet LyonFlow, généré par introspection en direct sur la base de production (VPS `51.83.159.224`, conteneur `lyonflow-postgres`).
>
> **Date de génération** : 2026-07-01
> **Base** : `lyonflow` · PostgreSQL **16.9** · PostGIS **3.6.3** · pgRouting **3.7.3**
> **Taille totale** : **48 GB**
> **Schémas applicatifs** : 7 (`archive`, `bronze`, `silver`, `gold`, `osm`, `referentiel`, `public`)
> **Objets (hors sequences)** : **155** (78 tables, 27 vues, 11 vues matérialisées, 39 séquences)
>
> **Source de vérité du code (ETL)** : `scripts/sql/` (38 fichiers de migration) + `dags/` (DAGs Airflow). Si tu modifies le schéma, ajoute une migration dans `scripts/sql/migration_NNN_*.sql` et référence-la ici.
>
> **Mode lecture / écriture** : aucune donnée n'est inventée — tout est issu de requêtes `pg_catalog` / `information_schema` sur la base live au moment de la rédaction. Les comptages de lignes proviennent de `pg_class.reltuples` (estimation du planner, suffisamment précise pour une vue d'ensemble).
>
> ** Mise à jour 2026-07-05 (migration_045, pas encore ré-introspectée)** : ajout de `bronze.vigilance_meteo` (+1 table bronze), `silver.air_quality_clean` (+1 table silver), `gold.v_velov_safety_advisory` (+1 vue gold). Les compteurs/tailles ci-dessous (§2) datent du 2026-07-01 et n'incluent pas encore ces 3 objets — voir §4.2/§4.3/§5/§11 pour le détail à jour de ces nouveaux objets.

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Statistiques globales](#2-statistiques-globales)
3. [Architecture Medallion (Bronze → Silver → Gold)](#3-architecture-medallion-bronze--silver--gold)
4. [Schémas applicatifs](#4-schémas-applicatifs)
   - [4.1 `archive`](#41-archive--cold-storage-cycle-2-airflow-dag-archive_silver_to_minio)
   - [4.2 `bronze` — Ingestion brute](#42-bronze--ingestion-brute-17-tables--2-vues)
   - [4.3 `silver` — Nettoyage / Normalisation](#43-silver--nettoyage--normalisation-6-tables)
   - [4.4 `gold` — Couches analytique + ML + référentiel métier](#44-gold--couches-analytique--ml--référentiel-métier-31-tables--10-mvs--9-vues)
   - [4.5 `osm` — Réseau routier OSM / pgRouting](#45-osm--réseau-routier-osm--pgrouting)
   - [4.6 `referentiel` — Lieux & modes de transport](#46-referentiel--lieux--modes-de-transport)
   - [4.7 `public` — MLflow + spatial_ref_sys + favoris utilisateurs](#47-public--mlflow--spatial_ref_sys--favoris-utilisateurs)
   - [4.8 `rgpd` — Audit conformité](#48-rgpd--audit-conformité)
5. [Vues (lecture seule)](#5-vues-lecture-seule)
6. [Vues matérialisées (refresh périodique)](#6-vues-matérialisées-refresh-périodique)
7. [Fonctions applicatives](#7-fonctions-applicatives)
8. [Triggers](#8-triggers)
9. [Contraintes (PK, UK, CHECK)](#9-contraintes-pk-uk-check)
10. [Index notables & couverture des hot-paths](#10-index-notables--couverture-des-hot-paths)
11. [Lineage pipeline (qui alimente qui)](#11-lineage-pipeline-qui-alimente-qui)
12. [Fréquences de rafraîchissement](#12-fréquences-de-rafraîchissement)
13. [Maintenance & Rétention](#13-maintenance--rétention)
14. [Glossaire](#14-glossaire)
15. [Liens utiles](#15-liens-utiles)

---

## 1. Vue d'ensemble

LyonFlow stocke **trois domaines temps réel** (trafic routier, transports en commun TCL, vélos en libre-service Vélo'v), **un référentiel métier** de lieux emblématiques, **un graphe routier OSM** pour le calcul d'itinéraires voiture, **les sorties de 3 modèles ML**, et **l'état complet du tracking MLflow**.

### Principes directeurs

| Principe | Implémentation |
|----------|----------------|
| **Immutabilité des données brutes** | Schéma `bronze.*` : aucune colonne extracted n'est jamais mise à jour. Colonnes nullables + `raw_data JSONB` brut à côté. |
| **Idempotence des transformations** | Index uniques sur `(source_key, fetched_at)`/`(measurement_time)`. `INSERT ... ON CONFLICT DO NOTHING`. |
| **Zéro mock en production** | Sprint 8 (2026-06-12) : tous les fallbacks mock ont été supprimés. Si la DB tombe, les widgets `fail loud` (voir `src/data/exceptions.py`). |
| **Géométries double-projection** | Les géométries capteur/chantier/borne sont stockées en `2154` (Lambert-93, France, distances métriques) **ET** `4326` (WGS-84, GPS). Trigger `chk_dual_geom` enforce la cohérence. |
| **Source de vérité unique** | Les vues matérialisées **`gold.*`** sont la destination de toute lecture dashboard. Les schémas `bronze`/`silver` ne sont pas interrogés directement par les widgets. |
| **Pipeline Medallion strict** | Bronze = brut, Silver = nettoyé/dédup, Gold = features ML + KPI business + MVs. |

### Stack extensions PostgreSQL

| Extension | Version | Usage |
|-----------|---------|-------|
| `postgis` | 3.6.3 | Géométries, projections (2154 ↔ 4326), `ST_DWithin`, `ST_Distance`, `ST_Transform`. |
| `pgrouting` | 3.7.3 | `pgr_dijkstra` (routing voiture), `pgr_dijkstra` (K-shortest paths `route_car_ksp`). |
| `pgcrypto` | 1.3 | Hachage RGPD (sha256 `channel_hash`). |
| `plpgsql` | 1.0 | Triggers + fonctions applicatives. |

### PostgreSQL tuning (cf. `docs/POSTGRES_TUNING_PROD.md`)

- Image Docker : `pgrouting/pgrouting:16-3.5-3.7.3` (Sprint 18 : `postgis/postgis:16-3.4` → `pgrouting/pgrouting:16-3.5-3.7.3`, PGDATA byte-compatible).
- Disque : `/mnt/postgres-data/postgres` sur **sdb2** (100 Go SSD).
- Locale `fr_FR.UTF-8`, `DateStyle=ISO, MDY`, `TimeZone=Europe/Paris`.

---

## 2. Statistiques globales

### Par schéma

| Schéma | Tables | Vues | MVs | Sequences | Taille totale | Rôle |
|--------|--------|------|-----|-----------|---------------|------|
| `archive` | 4 | 0 | 0 | 0 | **164 MB** | Snapshot froid cyclé vers MinIO (Sprint 10+) |
| `bronze` | 17 | 2 | 0 | 17 | **5.9 GB** | Ingestion brute (8 sources externes) |
| `silver` | 6 | 0 | 0 | 3 | **37 GB** | Nettoyage + normalisation |
| `gold` | 31 | 9 | 10 | 11 | **4.5 GB** | Couches analytique + ML features/predictions |
| `osm` | 5 | 0 | 1 | 4 | **1.2 GB** | Réseau routier OSM + pgRouting |
| `public` | 19 | 2 | 0 | 1 | **11 MB** | MLflow tracking + `spatial_ref_sys` + favoris |
| `referentiel` | 3 | 7 | 0 | 3 | **312 KB** | Lieux & modes (DAG monthly) |
| `rgpd` | 1 | 0 | 0 | 1 | négligeable | Audit purges rétention |
| **TOTAL** | **86** | **20** | **11** | **40** | **48 GB** | |

> **Note** : `silver.trafic_vitesse_propre` = **29.7 GB** à lui seul (1.55 M rows, table de vérité-vitesse historique purifiée). C'est la table qui consomme le plus d'espace disque — voir [§13 Maintenance](#13-maintenance--rétention).

### Top 15 tables par taille

| # | Table | Schéma | Taille | Rows (estimés) |
|---|-------|--------|--------|---------------|
| 1 | `trafic_vitesse_propre` | silver | 29.7 GB | 1.55 M |
| 2 | `trafic_boucles` | bronze | 4.5 GB | 1.38 M |
| 3 | `traffic_features_live` | gold | 3.1 GB | 4.51 M |
| 4 | `velov_clean` | silver | 3.0 GB | 3.12 M |
| 5 | `trafic_boucles_clean` | silver | 2.9 GB | 9.66 M |
| 6 | `tcl_vehicles_clean` | silver | 1.9 GB | 1.90 M |
| 7 | `ways` | osm | 1.1 GB | 102 K |
| 8 | `chantiers` | bronze | 569 MB | 6 K |
| 9 | `road_importance_ref` | gold | 388 MB | 2.34 M |
| 10 | `trafic_predictions` | gold | 299 MB | 621 K |
| 11 | `velov_features` | gold | 286 MB | 1.06 M |
| 12 | `tcl_vehicles` | bronze | 278 MB | 5.9 K (récentes uniquement) |
| 13 | `pvotrafic_snapshots` | bronze | 248 MB | 1.07 M |
| 14 | `velov` | bronze | 238 MB | 5.9 K (récentes) |
| 15 | `bus_delay_segments` | gold | 138 MB | 182 K |

> **Note** : la divergence "MBs vs rows" pour `bronze.tcl_vehicles` (278 MB / 5.9 K rows) s'explique : la table est purgée régulièrement (rétention courte), mais conserve un gros volume de données historiques non purgées avant les fenêtres de rétention récentes. Idem pour `bronze.velov`.

### Top 30 tables par nombre de rows (estimés)

Toutes les tables & vues :

| Schéma | Objet | Type | Rows estimés | Rôle |
|--------|-------|------|--------------|------|
| silver | `trafic_boucles_clean` | table | **9 657 625** | Capteurs trafic dédupliqués |
| gold | `traffic_features_live` | table | 4 514 528 | Features ML temps réel |
| silver | `velov_clean` | table | 3 115 805 | Stations Vélov dédupliquées |
| gold | `road_importance_ref` | table | 2 340 895 | Importance réseau routier |
| silver | `tcl_vehicles_clean` | table | 1 900 501 | Positions véhicules TCL |
| silver | `trafic_vitesse_propre` | table | 1 552 253 | Vérité-vitesse (référentiel) |
| bronze | `trafic_boucles` | table | 1 379 264 | Brut capteurs Grand Lyon |
| bronze | `pvotrafic_snapshots` | table | 1 074 141 | Snapshots pvotrafic |
| gold | `velov_features` | table | 1 058 605 | Features ML Vélov |
| archive | `tcl_vehicle_realtime` | table | 1 004 473 | Snapshot TCL avant MinIO |
| gold | `trafic_predictions` | table | 620 920 | Prédictions trafic H+1h |
| archive | `velov_clean` | table | 482 414 | Snapshot Vélov avant MinIO |
| gold | `dim_temps` | table | 315 360 | Dimension temps (granularité 5 min, ~10 ans) |
| gold | `road_network_edges` | table | 184 534 | Arêtes graphe routier |
| gold | `bus_delay_segments` | table | 181 702 | Retards bus agrégés |
| gold | `road_network_nodes` | table | 112 687 | Nœuds graphe routier |
| osm | `ways` | table | 101 554 | Réseau routier OSM (import osm2pgrouting) |
| osm | `ways_vertices_pgr` | table | 87 696 | Sommets OSM |
| gold | `xgb_training_set` | table | 72 575 | Training set XGBoost matérialisé |
| archive | `velov_features_live` | table | 45 000 | Snapshot features Vélov |
| bronze | `tomtom_traffic` | table | 30 498 | Brut TomTom Traffic Flow |
| bronze | `air_quality` | table | 15 547 | Brut qualité de l'air Open-Meteo |
| gold | `dim_gnn_adjacency` | table | 12 865 | Adjacence graphe GNN H3 |
| gold | `h3_trafic_live` | table | 12 202 | Trafic agrégé par hex H3 |
| silver | `meteo_hourly` | table | 9 855 | Météo horaire dédupliquée |
| bronze | `meteo` | table | 9 419 | Brut Open-Meteo |
| bronze | `chantiers_voirie` | table | 9 324 | Chantiers voirie |
| public | `spatial_ref_sys` | table | 8 500 | PostGIS (standard) |
| public | `metrics` | table | 6 445 | MLflow métriques historisées |
| bronze | `chantiers` | table | 6 029 | Chantiers Grand Lyon |
| bronze | `tcl_vehicles` | table | 5 939 | Brut SIRI Lite |
| bronze | `vitesse_limite_ref` | table | 5 424 | Vitesses limites par `code_troncon` |
| bronze | `tomtom_flow` | table | 4 340 | Brut TomTom Flow API |
| gold | `dim_spatial_grid_mapping` | table | 3 946 | Mapping capteur ↔ nœud GNN |
| bronze | `comptages` | table | 3 000 | Comptages alternatifs |
| gold | `infrastructure_bottlenecks` | table | 2 749 | Bottlenecks infra bus × trafic |
| gold | `h3_trafic_predictions` | table | 2 748 | Prédictions agrégées par hex H3 |
| gold | `sensor_road_importance` | table | 2 403 | Importance routée par capteur |

### MVs (vues matérialisées)

| Schéma | MatView | Taille | Refresh | Source |
|--------|---------|--------|---------|--------|
| gold | `mv_multimodal_grid` | — | 10 min (DAG transform) | trafic + TCL + Vélov + météo |
| gold | `mv_bus_traffic_spatial` | — | 15 min | bus_delay × traffic_combined |
| gold | `mv_line_kpis_live` | — | horaire | tcl_vehicle_realtime |
| gold | `mv_otp_heatmap` | 7.5 MB | horaire | bus_delay_segments |
| gold | `mv_sensor_saturation` | — | 15 min (DAG refresh_sensor_saturation) | trafic_boucles_clean |
| gold | `mv_meteo_impact` | — | quotidien 04h | météo × modes |
| gold | `mv_congestion_propagation_pairs` | — | quotidien 04h | traffic_features_live |
| gold | `mv_velov_transit_coupling` | — | 15 min (DAG refresh_velov_transit_coupling) | Vélov × TCL GPS |
| gold | `mv_xgb_vs_tomtom` | — | 30 min | xgb_pred × TomTom Flow |
| gold | `mv_fact_traffic_pivot` | 92 MB | horaire | trafic_boucles_clean pivoté temps × capteur |
| osm | `mv_sensor_to_way` | — | (auto) | sensor_positions ↔ ways |

---

## 3. Architecture Medallion (Bronze → Silver → Gold)

LyonFlow suit strictement la **médaille** :

```
   ┌────────────────┐
   │  Sources       │  8 sources externes (Sprint 8+ toutes fonctionnelles)
   │  externes      │  Grand Lyon boucles, TCL SIRI Lite, Vélo'v GBFS,
   └───────┬────────┘  Open-Meteo (météo + AQ), chantiers, vitesse_limite,
           │           infra_ref, TomTom Traffic Flow (Sprint 13+)
           ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  Bronze (17 tables)                                            │
   │  - Ingestion brute, immutable                                  │
   │  - Colonnes extracted nullable + raw_data JSONB                │
   │  - fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()               │
   │  - Index uniques dédup : (source_key, fetched_at)              │
   │                                                                │
   │  8 DAGs collect_*_*/5min ou */15min ou 1x/jour                 │
   └────────────────────────────┬───────────────────────────────────┘
                                ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  Silver (6 tables)                                             │
   │  - Dédup (DISTINCT ON), géo 4326+2154, types normalisés        │
   │  - Filtre pureté (capteurs sains, stations actives, etc.)      │
   │                                                                │
   │  5 DAGs transform_bronze_to_silver */5 min                     │
   └────────────────────────────┬───────────────────────────────────┘
                                ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  Gold (31 tables + 10 MVs + 9 vues)                            │
   │  - 3 domaines : trafic (ML), bus (analyse), vélov (ML)         │
   │  - Multimodal (Sprint 15+) : mv_multimodal_grid, etc.          │
   │  - Sorties modèles : trafic_predictions, velov_predictions,    │
   │    stgcn_predictions_live, mv_xgb_vs_tomtom                   │
   │  - KPI Élu/Pro : bus_delay_segments, infrastructure_bottlenecks│
   │  - Quality : data_quality_log, v_data_completeness,            │
   │    v_source_health                                             │
   │                                                                │
   │  DAGs :                                                        │
   │  - transform_silver_to_gold */15min (3 domaines en parallèle)  │
   │  - dag_live_speed_retrain */30 min (XGBoost H+1h)             │
   │  - dag_daily_train 03h (GNN ST-GCN, complet)                  │
   │  - build_xgb_training_set quotidien 02h30                    │
   └────────────────────────────┬───────────────────────────────────┘
                                ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  OSM (5 tables + 1 MV)                                        │
   │  - Référentiel statique : ways, ways_vertices_pgr              │
   │  - Capteurs associés : sensor_positions, mv_sensor_to_way     │
   │  - Refresh trafic : osm.refresh_traffic_costs() */15 min      │
   │    → injecte speed_kmh temps réel dans osm.ways.cost          │
   └────────────────────────────────────────────────────────────────┘
                                ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  Referentiel (3 tables + 7 vues)                               │
   │  - Lieux emblématiques Lyon (21 lieux)                         │
   │  - Dessertes TCL par lieu (56 lignes)                          │
   │  - Cadences TCL observées (223 cadences)                       │
   │  - Voisinage Vélov (grappes < 200m)                            │
   └────────────────────────────────────────────────────────────────┘
                                ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  Public (19 tables)                                            │
   │  - MLflow Tracking (15 tables) : runs, metrics, params,        │
   │    experiments, registered_models, tags                        │
   │  - spatial_ref_sys (PostGIS standard)                          │
   │  - user_favorites (favoris dashboard par user)                 │
   └────────────────────────────────────────────────────────────────┘
                                ▼
                       Archive (4 tables)
                       - cycle vers MinIO via
                         dags/maintenance/silver_archive_to_minio
                         quotidien 04h (Parquet snappy)
```

---

## 4. Schémas applicatifs

### 4.1 `archive` — Cold storage (cycle 2, Airflow DAG `archive_silver_to_minio`)

> **Rôle** : snapshot des tables Silver jeunes (> 30 jours) partionné en Parquet snappy vers MinIO (`/mnt/postgres-data/minio/silver/YYYY/MM/`). Les tables archive sont purgées après upload MinIO.

| Table | Rows | Colonnes principales |
|-------|------|----------------------|
| `tcl_vehicle_realtime` | 1 004 473 | `recorded_at, vehicle_ref, line_ref, lat, lon, delay_seconds, is_delayed` |
| `tcl_vehicle_clean` | — | `recorded_at, vehicle_ref, line_ref, lat, lon, delay_seconds, is_delayed` |
| `velov_clean` | 482 414 | `id, station_id, fetched_at, num_bikes_available, num_docks_available, is_installed/renting/returning/maintenance, lat, lon, geom, silver_inserted_at/updated_at` |
| `velov_features_live` | 45 000 | `id, station_id, fetched_at, computed_at, lag_1/2/3/5/10/30/60, rolling_mean_5/10/30, target_h1/h3/h6, lat, lon` |

> **Note Sprint 10+** : Avant cette version, les archives étaient conservées en table → saturation sdb à 80%. Aujourd'hui, **stream pur vers MinIO**, pas de backup persistant.

---

### 4.2 `bronze` — Ingestion brute (17 tables + 2 vues)

> **Rôle** : données ingestées telles quelles par les 8 collecteurs (`src/ingestion/*.py`). Schéma hétérogène par source. Aucune colonne extracted obligatoire.

#### Tables principales

| Table | Source | Fréquence ingest | Rows estimés | Colonnes clés |
|-------|--------|------------------|--------------|--------------|
| `trafic_boucles` | Grand Lyon pvotrafic (OGC) | */5 min | 1 379 264 | `fetched_at, troncon_id, troncon_name, debit, taux_occupation, vitesse, geom_2154, geom_4326, raw_data JSONB` |
| `tcl_vehicles` | TCL SIRI Lite | */5 min | 5 939 (fenêtre) | `fetched_at, vehicle_ref, line_ref, recorded_position_lat/lon, delay_seconds, geom, raw_data` |
| `velov` | Vélo'v GBFS | */5 min | 5 972 (fenêtre) | `fetched_at, station_id, station_name, num_bikes_available, num_docks_available, is_installed/renting/returning, lat, lon, geom, raw_data` |
| `meteo` | Open-Meteo | */1 h | 9 419 | `fetched_at, measurement_time, temperature_2m, precipitation, wind_speed_10m, weather_code, raw_data` |
| `air_quality` | Open-Meteo Air Quality | */1 h | 15 547 | `fetched_at, measurement_time, pm10, pm2_5, nitrogen_dioxide, ozone, sulphur_dioxide, carbon_monoxide, european_aqi, raw_data` |
| `chantiers` | Grand Lyon chantiers | 1x/jour 03h | 6 029 | `fetched_at, chantier_id, nom, type_perturbation, severite, date_debut, date_fin, commune, geom, raw_data` |
| `chantiers_historique` | Idem (avec statut terminé) | 1x/sem | — | idem + `numero` UNIQUE |
| `chantiers_voirie` | Voirie spécifique | 1x/jour | 9 324 | `fetched_at, geom, raw_data` |
| `tomtom_traffic` | TomTom Flow API | */15 min | 30 498 | `tile_key, fetched_at, current_speed_kmh, free_flow_speed_kmh, confidence, road_closure, raw_data` |
| `tomtom_flow` | TomTom Flow Segment | journalier | 4 340 | `point_name, collected_at, current_speed_kmh, free_flow_speed_kmh, confidence, raw_data` |
| `vigilance_meteo` **(NOUVEAU 2026-07-05)** | API Opendatasoft (miroir gratuit vigilance météo-france, sans clé) | */6h | — | `fetched_at, departement ('69'), couleur_canicule, echeance ('J'), begin_time, end_time, bulletin_date, raw_data` (UNIQUE `(departement, echeance, begin_time, fetched_at)`). Sert `gold.v_velov_safety_advisory` (migration_045) |
| `pvotrafic_snapshots` | Snapshots pvotrafic | */5 min | 1 074 141 | `code, collected_at, value, raw_data` (UNIQUE `(code, collected_at)`) |
| `calendrier_scolaire` | data.education.gouv.fr | 1x/mois | — | `zone, description, start_date, end_date, annee_scolaire` (Zone A) |
| `jours_feries` | calendrier.api.gouv.fr | 1x/mois | — | `date_ferie, nom` |
| `vitesse_limite_ref` | Grand Lyon Code de la route | 1x/sem | 5 424 | `code, libelle, vitesse_limite_kmh` |
| `comptages` | Grand Lyon Comptages | */1 h | 3 000 | `site_id, measurement_time, count, debit, raw_data` |
| `parkings` | Grand Lyon Parkings | */5 min | — | `parking_id, fetched_at, places_libres, places_totales, statut, geom, raw_data` |
| `prix_carburants` | data.economie.gouv.fr | 1x/jour | — | `collected_at, carburant, zone, prix` (UNIQUE composite) |

#### Vues bronze

| Vue | Rôle | Colonnes |
|-----|------|----------|
| `healthy_pvotrafic` | Qualité de la dernière collecte pvotrafic (codes qui répondent) | — |
| `healthy_sensors` | Liste des capteurs ayant renvoyé des données < 24h | — |

#### Index notables bronze

- `bronze.trafic_boucles` :
  - `geom` GIST (2154), `geom_4326` GIST (4326) → recherche spatiale rapide
  - `(troncon_id, fetched_at)` UNIQUE WHERE troncon_id NOT NULL → dédup
  - `fetched_at` BRIN → fenêtre temporelle sans index bloated
  - Trigger `chk_dual_geom` : **les deux géométries 2154/4326 doivent être simultanément NULL ou simultanément NOT NULL**.
- `bronze.tcl_vehicles` :
  - `(fetched_at, vehicle_ref)` UNIQUE → dédup
  - `fetched_at` BRIN
- `bronze.velov` :
  - `station_id` B-tree
  - `fetched_at` BRIN
- `bronze.tomtom_traffic` :
  - `(tile_key, fetched_at)` UNIQUE
  - `fetched_at` BRIN

> **Schéma normalisé** : toutes les tables `bronze.*` ont `fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()` + une colonne `raw_data JSONB` qui conserve la réponse API exacte. Les colonnes extracted (`vitesse`, `debit`, etc.) peuvent être NULL si l'API ne les a pas renvoyées.

---

### 4.3 `silver` — Nettoyage / Normalisation (6 tables)

> **Rôle** : transformation bronze → silver : déduplication, validation, enrichissement géométrique, conversion d'unités. **Aucun fallback mock** : une source manquante = `DashboardDataError` (Sprint 8).

| Table | Source | Rétention | Rows | Colonnes clés |
|-------|--------|-----------|------|---------------|
| `trafic_boucles_clean` | bronze.trafic_boucles | 90 j | **9.66 M** | `channel_id, measurement_time, debit, taux_occupation, vitesse, vitesse_limite_kmh, troncon_name, importance_code, is_vacances, is_ferie, geom_2154, geom_4326` (PK : `(channel_id, measurement_time)`) |
| `trafic_vitesse_propre` | trafic_boucles_clean | infini | **1.55 M** | `properties_twgid, transformed_at, vitesse_kmh, geom` — table de référence vitesse (utilisée par `referentiel.v_avg_speed_7d`). UNIQUE `(properties_twgid, transformed_at)` |
| `tcl_vehicles_clean` | bronze.tcl_vehicles | 90 j | 1.90 M | `line_ref, journey_ref, stop_ref, vehicle_ref, measurement_time, lat, lon, delay_seconds, is_delayed, is_vacances, is_ferie, geom, line_mode` (UNIQUE `(line_ref, journey_ref, stop_ref, measurement_time)`) |
| `velov_clean` | bronze.velov | 30 j | 3.12 M | `station_id, measurement_time, num_bikes_available, num_docks_available, is_installed, is_renting, is_returning, is_maintenance, lat, lon, geom` (UNIQUE `(station_id, measurement_time)`) |
| `meteo_hourly` | bronze.meteo | 2 ans | 9 855 | `measurement_time, temperature_2m, precipitation, rain, is_raining, wind_speed_10m, wind_direction_10m, weather_code, visibility, humidity, uv_index, is_vacances, is_ferie` (PK `measurement_time`). **Drift détecté 2026-07-05** : le code vivant (`get_weather_hourly`, `_transform_meteo`) lit/écrit `temperature_c`/`rain_mm`, pas `temperature_2m`/`precipitation` — voir `docs/DICTIONNAIRE_COLONNES.md` pour le détail. |
| `chantiers_actifs` | bronze.chantiers | infini | — | `chantier_id, fetched_at, nom, type_perturbation, severite, date_debut, date_fin, commune, geom, is_active` (UNIQUE `(chantier_id, fetched_at)`) |
| `air_quality_clean` **(NOUVEAU 2026-07-05)** | bronze.air_quality | infini | — | `measurement_time, european_aqi, pm10, pm2_5, nitrogen_dioxide, ozone, carbon_monoxide, fetched_at` (PK `measurement_time`). Dédup pattern identique à `meteo_hourly`. Sert `gold.v_velov_safety_advisory` (migration_045) |

#### Notes importantes sur `silver`

- **`trafic_vitesse_propre`** (29.7 GB !) : table historique des vitesses "propres" (post-filtrage outliers). Sert de référentiel pour le fallback `referentiel.v_avg_speed_7d` quand `gold.trafic_predictions` est vide (zone sans capteur). **Découverte Sprint 9+** : la table accumule depuis le début du projet (~ 1.5 ans). Voir [§13 Maintenance](#13-maintenance--rétention) pour la stratégie de partitionnement / purge.
- **Géométries** : tous les schémas `silver` ont `geom` (PostGIS 4326 via SRID 4326 par défaut, sauf indication contraire). `trafic_boucles_clean` a `geom_2154` ET `geom_4326`.
- **Coverage CHECK** : `idx_silver_trafic_chn_time_geom` — partial index WHERE `geom IS NOT NULL` pour exclure les capteurs sans géométrie des jointures spatiales.

---

### 4.4 `gold` — Couches analytique + ML + référentiel métier (31 tables + 10 MVs + 9 vues)

> **Rôle** : source de vérité des widgets dashboard, des prédictions ML, et des KPI Élu/Pro TCL.

Le schéma `gold` est structuré en **6 sous-domaines** :

#### 4.4.1 Domaine Trafic (réactif XGBoost + spatial GNN)

| Table / MV / Vue | Type | Rôle |
|------------------|------|------|
| `traffic_features_live` | table | **Features ML XGBoost live**. 26 colonnes features (matching `FEATURE_COLS` dans `train_live_speed_model.py`). PK `(channel_id, fetched_at)`. Refresh */15 min par DAG `transform_silver_to_gold`. Rétention 30 jours. |
| `dim_spatial_grid_mapping` | table | Mapping `properties_twgid` ↔ `node_idx` (H3 res.13, `cell_to_local_ij`). ~3 946 nœuds. **Sprint 8** : trigger `trg_dim_spatial_has_lat_lon` refuse les INSERT avec `lat/lon NULL` pour les canaux `real_string`. **PK `properties_twgid`**. |
| `dim_gnn_adjacency` | table | Arêtes graphe GNN (K=2 `grid_disk`, bidirectionnel + self-loops). PK `(node_u, node_v)`. |
| `trafic_predictions` | table | Prédictions XGBoost H+1h pré-calculées. Schéma v0.3.1 : `axis_key, horizon_h, calculated_at, speed_pred, etat_pred, color, vitesse_limite_kmh, label, model_version, lat, lon`. PK `(axis_key, horizon_h, calculated_at)`. Refresh */30 min par `dag_live_speed_retrain`. |
| `channels_ref` | table | **Référentiel statique des capteurs** (~1 159 boucles Grand Lyon). `channel_id, site_id, site_name, mobility_type, direction, sens, lat, lon, geom, commune, nb_voies, debit_max_horaire`. PK `channel_id`. |
| `h3_trafic_live` | table | Trafic agrégé par hex H3 (res.10). PK `(hex_id, sens)`. CHECK `etat IN ('V','O','R','G')` (Vert/Orange/Rouge/Gris). |
| `h3_trafic_predictions` | table | Prédictions agrégées par hex H3 × horizon. PK `(hex_id, horizon_h)`. |
| `fact_correlation_matrix` | table | Matrice de corrélation features (peuplée par `evidently`). PK `(feature_x, feature_y)`. |
| `bus_delay_segments` | table | Retards bus agrégés par `(date, hour, line_ref, segment_id)` avec `avg_delay_seconds, n_observations, is_vacances, is_ferie, weather_code`. PK composite. Refresh */15 min. |
| `infrastructure_bottlenecks` | table | **Dette Sprint 22++** : JOIN global par heure déprécié. Remplacé par `gold.mv_bus_traffic_spatial` (spatial). Table conservée pour compatibilité mais plus alimentée. |

#### 4.4.2 Domaine ML & Prédictions

| Table | Rôle |
|-------|------|
| `xgb_training_set` | **Training set matérialisé** (Sprint 9+) : self-join `computed_at + 60min` au lieu de `LEAD() OVER` sur 2.4M rows. 72 K rows, refresh quotidien 02h30 par DAG `build_xgb_training_set`. Rétention 14 jours. **PK `feature_id`**, index `WHERE target_speed IS NOT NULL`. |
| `velov_features` | Features ML Vélov (`station_id_encoded, measurement_time, lag_1/2/3, rolling_mean_3, sin/cos_hour/dow, temperature_2m, precipitation, is_vacances, is_ferie`). PK `(station_id_encoded, measurement_time)`. |
| `velov_predictions` | Prédictions Vélov H+30min, H+1h (label encoding station, pas one-hot). Refresh */1 h. |
| `stgcn_predictions_live` | Prédictions GNN spatio-temporel (multi-horizon 1/3/6/12/24/36). PK `(predicted_for, node_idx)`. Refresh quotidien 03h par `dag_daily_train`. |
| `tarifs_modes` | **Sprint 15+** : référentiel tarifs (TCL, Vélo'v, parkings) pour comparateur de modes Usager. UNIQUE `(mode, produit, age_min, age_max)`. |
| `model_drift_reports` | Rapports Evidently (drift features). PK `computed_at`. |
| `features_traffic` | **Table ML historique** (vs `traffic_features_live`) : colonnes brutes pré-agrégation. PK `(channel_id, measurement_time)`. |
| `channels_ref` | (voir 4.4.1) |

#### 4.4.3 Domaine Bus (analyse)

| Table / MV | Rôle |
|------------|------|
| `bus_delay_segments` | (voir 4.4.1) |
| `tcl_vehicle_realtime` | Snapshot TCL temps réel (snapshot des dernières positions). Sert au widget `tcl_vehicle_map`. UNIQUE `(recorded_at, vehicle_ref)`. |

#### 4.4.4 Domaine Multimodal (Sprint 15+)

| MV / Vue | Rôle |
|----------|------|
| `mv_multimodal_grid` | Grille 0.01° (~1 km) Lyon. Fusionne `traffic_features_live + tcl_vehicle_realtime + velov_clean + meteo_hourly`. Score multimodal 0-10 + diagnostic dominant. Refresh */10 min par DAG `transform_silver_to_gold`. Sert widget Pro_TCL `multimodal_heatmap`. |
| `mv_bus_traffic_spatial` | **Axe 3 Sprint 15+** — JOIN spatial 0.001° (~100 m) bus × trafic. **Remplace** le bottleneck global `infrastructure_bottlenecks`. Sert `bottlenecks_spatial` widget (Elu_2). Refresh */15 min `CONCURRENTLY`. |
| `mv_line_kpis_live` | KPIs par ligne TCL (155 lignes) : OTP, retard moyen, charge, fréquence. Refresh */1 h. Sert widget Pro_TCL `line_kpis`. |
| `mv_otp_heatmap` | Heatmap OTP triplets `(line_id, date, hour)` (4 416 cellules × 7j). Refresh */1 h. Sert widget `otp_heatmap` Pro_2. |
| `mv_sensor_saturation` | Saturation %v85 + amplitude par capteur. Refresh */15 min par DAG `refresh_sensor_saturation`. **Avant Sprint 22** : vue non matérialisée qui timeoutait > 60s sur 889k rows. |
| `mv_meteo_impact` | Impact météo par mode (Sprint 22 Axe 7). Refresh quotidien 04h. |
| `mv_congestion_propagation_pairs` | Paires de corrélation propagation congestion cross-capteurs (Sprint 22 Axe 2). Refresh quotidien 04h. |
| `mv_velov_transit_coupling` | **Axe 4 Sprint 15+** — Z-score vélos dispos par station Vélov située < 300m zone TC. `z_score < -2` → anomaly_detected = TRUE. Refresh */15 min par DAG `refresh_velov_transit_coupling`. |
| `mv_xgb_vs_tomtom` | **Sprint 13+** — Paires (XGBoost H+1h, TomTom Flow) jointes spatialement (ST_DWithin 200m) et temporellement (±10 min). Refresh */30 min. Sert widget `backtest_dashboard` Pro_7 + drift Evidently. |
| `mv_fact_traffic_pivot` | **Sprint 7** — Pivot temps × capteur depuis `trafic_boucles_clean` (92 MB). Sert `correlation_matrix`. |
| `multimodal_status_grid` | Vue dérivée simplifiée de `mv_multimodal_grid` (top 100 cellules). Sert la carte Folium heatmap. |

#### 4.4.5 Domaine Utilisateurs & Qualité

| Table | Rôle |
|-------|------|
| `app_users` | Utilisateurs dashboard 3 personas. CHECK `persona_id IN ('pro_tcl','elu','admin')`, UNIQUE `username`. |
| `user_favorites` (public) | Favoris par user. PK `(user_id, id)`. |

#### 4.4.6 Domaine Modèle routier (legacy gold → migration osm)

| Table | Rôle |
|-------|------|
| `road_network_nodes` | Nœuds graphe routier Lyon (Overpass API OSM, bbox [45.65, 4.75, 45.80, 4.95]). PK `osm_id`. CHECK lat/lon ranges. |
| `road_network_edges` | Arêtes `(from_osm_id, to_osm_id)`. FK vers `road_network_nodes`. CHECK `length_m >= 0`. |
| `road_importance_ref` | Importance routée par `(hex_id, road_gid)` — 2.34M rows. Sert au scoring routing. |
| `sensor_road_importance` | Importance routée par capteur. PK `channel_id`. Sert v_source_health. |
| `road_network_refresh_log` | Log de refresh du graphe. PK `id`. |
| `amenagements_history` | Historique aménagements voirie (PK `amenagement_id`). Sert widget `amenagements_passes`. |
| `dim_temps` | Dimension temps, granularité 5 min, ~10 ans. PK `tranche_5min`. Sert tous les calculs weekly/monthly. |
| `data_quality_log` | Log checks qualité (Sprint 8+). CHECK `status IN ('ok','warning','critical')`. Sert widget `quality_log`. |
| `network_health_history` | Historique 15-min des scores santé réseau (Axe 5, widget Élu). CHECK `0 <= score <= 100`. Rétention 7 j. |
| `mv_kpis_12_months` | KPIs agrégés sur 12 mois (par `(month, kpi_key)`). |
| `mv_twgid_to_lyo` | Mapping `properties_twgid` ↔ `channel_id` (LYO) pour identifiants capteurs H3 ↔ boucles. |
| `channel_tomtom_mapping` | Mapping `channel_id` ↔ `tomtom_point_name` (Sprint 13+) : FK → `channels_ref`. Sert cross-validation. |

---

### 4.5 `osm` — Réseau routier OSM / pgRouting

> **Sprint 18 (2026-06-21)** : root cause "itinéraires voiture traversant le Rhône" résolue. Avant : graphe H3 K=2 (GNN) utilisé pour pathfinding voiture → zigzag. Après : réseau routier OSM réel (`pgr_dijkstra` sur ~87k vertices / ~101k arêtes OSM).

| Table / MV | Rows | Rôle |
|------------|------|------|
| `ways` | 101 554 | **Réseau routier OSM** (osm2pgrouting import depuis Geofabrik Rhône-Alpes). 14 types highway (motorway, trunk, primary, ...). Colonne `cost` / `reverse_cost` mises à jour **toutes les 15 min** par `osm.refresh_traffic_costs()`. PK `gid`. |
| `ways_vertices_pgr` | 87 696 | Sommets du graphe routier (PK `id`, UNIQUE `osm_id`). Index GIST sur `the_geom`. |
| `sensor_positions` | 1 159 (1 par canal) | Capteurs Grand Lyon (channel_id + point GiST) — peuplé depuis `gold.traffic_features_live`. PK `channel_id`. Index GIST `geom`. |
| `pointsofinterest` | — | POIs OSM (Geofabrik). PK `pid` (synthetic), UNIQUE `osm_id`. Sert potentiellement aux widgets itinéraire. |
| `configuration` | — | Configuration osm2pgrouting : tags routiers (UNIQUE `tag_id`). Sert `osm.ways.tag_id` FK. |
| `mv_sensor_to_way` | — | **MV critique Sprint 18** — LATERAL KNN `<->`, seuil 200m. Mapping capteur → arête OSM la plus proche. 41 737 arêtes couvertes. Refresh en parallèle du refresh trafic. |
| (vue) — | | Pas de vues user dans `osm.*`. |

#### Fonctions `osm.*` (cf. §7)

- `osm.refresh_traffic_costs()` — injecte vitesse capteurs dans `ways.cost`
- `osm.route_car(lon1, lat1, lon2, lat2)` — `pgr_dijkstra` dirigé
- `osm.route_car_ksp(...)` — K-shortest paths (alternatives)

#### FKs `osm.*`

```
ways.source        → ways_vertices_pgr.id
ways.source_osm    → ways_vertices_pgr.osm_id
ways.target        → ways_vertices_pgr.id
ways.target_osm    → ways_vertices_pgr.osm_id
ways.tag_id        → configuration.tag_id
```

---

### 4.6 `referentiel` — Lieux & modes de transport

> **Rôle** : couche "métier" — lieux emblématiques Lyon (search_bar Usager), dessertes TCL, cadences observées, voisinage Vélov.

| Table | Rows | Rôle |
|-------|------|------|
| `lieux_lyon` | 21 | **Référentiel statique** lieux emblématiques (gares, places, quartiers, parcs). PK `lieu_id`, UNIQUE `name`. Sert `search_bar` + `itinerary` widgets. Types : `gare`, `place`, `quartier`, `parc`. |
| `lieux_transports` | 56 | Dessertes TCL par lieu : `(lieu_id, line_ref, line_mode, stop_name, distance_m, rank, is_active, source='expert'\|'gtfs')`. FK → `lieux_lyon`. CHECK effective `('weekday','saturday','sunday_holiday','vacation')` sur jour type. |
| `lieux_calendrier` | 223 | Cadences TCL observées (min/véhicule) par `(line_ref, day_type, time_bucket)`. Sert le widget `Mon Trajet` / cadencement. Refresh quotidien recommandé (DAG `refresh_lieux_calendrier`). |
| (vues) | | 7 vues — voir §5 |

#### Vues `referentiel`

| Vue | Rôle |
|-----|------|
| `v_avg_speed_7d` | Vitesse moyenne historique 7j par nœud routier. **Fallback** si `gold.trafic_predictions` vide. |
| `v_cadence_observed_7d` | Observations brutes 7j glissants par `(line_ref, tranche, day_type)`. Base de calcul de `lieux_calendrier`. |
| `v_cadence_summary` | Cadence observée (min/véhicule) par `(line, tranche, day_type)` avec `confidence = nb observations`. |
| `v_velov_neighbors` | Maillage Vélov voisines < 200m. Lyon ~458 stations × ~10-20k paires. |
| `v_lieux_velov_proches` | **Sprint VPS-6** : top 3 bornes Vélov les plus proches par lieu (haversine + dispo temps réel). |
| `v_lieux_velov_plus_proche` | Top 1 borne par lieu (top 1 de `v_lieux_velov_proches`). |
| `v_lieux_velov_smart` | **Sprint VPS-6** : top 3 bornes Vélov avec score composite (distance + vélos + docks). Status `VIDE` / `PLEINE` / `FAIBLE` / `OK`. |

---

### 4.7 `public` — MLflow + `spatial_ref_sys` + favoris utilisateurs

> **Schéma par défaut** MLflow + PostGIS `spatial_ref_sys` (réglementaire) + table `user_favorites` du dashboard.

| Table / Vue | Source | Rôle |
|-------------|--------|------|
| `runs` | MLflow | Tracking server : un run = un entraînement/évaluation modèle. PK `run_uuid`. |
| `experiments` | MLflow | Expériences (groupes de runs). PK `experiment_id`. |
| `registered_models` | MLflow | Registry : modèles versionnés. PK `name`. |
| `model_versions` | MLflow | Versions par modèle (`name`, `version`). |
| `registered_model_aliases` | MLflow | Aliases (champion, challenger, etc.). |
| `model_version_tags` | MLflow | Tags par version (git_sha, sprint, etc.). |
| `registered_model_tags` | MLflow | Tags par modèle. |
| `experiment_tags` | MLflow | Tags par expérience. |
| `tags` | MLflow | Tags par run. |
| `inputs` / `input_tags` | MLflow | Inputs (datasets, modèles) par run/experiment. |
| `datasets` | MLflow | Datasets MLflow (snapshot du training set). |
| `params` | MLflow | Hyperparamètres par run. |
| `metrics` | MLflow | Métriques historisées par run (ex: `mae_h1 = 4.23`). PK `(key, timestamp, step, run_uuid, value, is_nan)`. |
| `latest_metrics` | MLflow | Snapshot dernière valeur par `(key, run_uuid)`. |
| `alembic_version` | MLflow | Migration tracking MLflow (alembic). |
| `schema_migrations` | MLflow | Idem (legacy). |
| `spatial_ref_sys` | PostGIS | Standard SRID registry (~8 500 SRIDs PostGIS). |
| `user_favorites` | LyonFlow | Favoris dashboard par user (clé `(user_id, id)`). |
| `geography_columns` | vue PostGIS | Catalogue colonnes `geography`. |
| `geometry_columns` | vue PostGIS | Catalogue colonnes `geometry`. |

> **Note** : 15 tables MLflow + 2 tables PostGIS + `user_favorites`. Totalité gérée par le serveur MLflow (DAG `dag_*_train*` → write runs/metrics).

---

### 4.8 `rgpd` — Audit conformité

> **Rôle** : traçabilité des purges de rétention (Bronze/Silver/Gold), consultable pour justifier la politique de conservation des données.

| Table | Rôle |
|-------|------|
| `purge_log` | Une ligne par purge exécutée : `(purged_at, schema_name, table_name, rows_purged, retention_days)`. Alimentée par `dags/maintenance/maintenance.py::_purge_table()` (DAG `purge_bronze`). Index `idx_rgpd_purge_log_purged_at` (DESC) pour consultation chronologique. |

---

## 5. Vues (lecture seule)

20 vues totales (hors PostGIS `geography_columns`/`geometry_columns`).

### Vues `bronze.*` (2)

| Vue | Rôle |
|-----|------|
| `bronze.healthy_pvotrafic` | Qualité de la dernière collecte pvotrafic (codes qui répondent). Sert `data_quality_badge`. |
| `bronze.healthy_sensors` | Liste des capteurs ayant renvoyé des données < 24h. Sert `health_checks.py`. |

### Vues `gold.*` (9)

| Vue | Rôle |
|-----|------|
| `gold.multimodal_status_grid` | Top 100 cellules saturées de `mv_multimodal_grid`. Sert carte Folium heatmap. |
| `gold.v_coherence_tomtom_vs_grandlyon` | **Sprint 13+** — Cohérence TomTom vs Grand Lyon (ST_DWithin 200m). `(tile_key, channel_id, distance_m, tomtom_speed_kmh, gl_speed_kmh, delta_kmh, ratio_diff, status ∈ ok|minor_drift|drift|no_data)`. Sert widget Pro_TCL `coherence_scatter`. |
| `gold.v_data_completeness` | **Sprint 16 Axe B** — Complétude colonnes critiques par table Silver (24h). `speed_pct, geo_pct, id_pct`. Sert widget `source_health_monitor` Pro_6. |
| `gold.v_dim_spatial_health` | **Sprint 8+** — Dette schéma lat/lon : la catégorie `integer_stringified` doit avoir `lat/lon = NULL` (h3_id valide), `real_string` doit avoir `lat/lon NOT NULL` (trigger enforce). |
| `gold.v_source_health` | **Sprint 16 Axe B** — Score santé par source (8 sources Bronze + Gold predictions). `age_minutes`, `health_score 0-100`, `status ∈ {healthy,delayed,stale,dead}`. Sert widget `source_health_monitor` (Pro_6) + `data_quality_badge` (Elu_1) + `check_all_sources()` (`health_checks.py`). |
| `gold.v_tomtom_gl_drift` | **Sprint 13+** — Capteurs GL suspectés HS (`>= 60% drift 24h`). Vue dérivée de `v_coherence_tomtom_vs_grandlyon`. Sert détecteur automatique capteurs HS. |
| `gold.v_tomtom_traffic_live` | Dernier snapshot TomTom Flow par tuile (24h). Sert carte trafic (Mon Trajet). |
| `gold.v_traffic_combined` | **Sprint VPS-6** — Vue unifiée trafic : priorité `gold_live (capteurs <5min) > gold_pred (H+1h) > tomtom`. Sert la carte dashboard partout à Lyon (y compris hors couverture boucles). |
| `gold.v_xgb_accuracy_summary` | **Sprint 16 Axe A** — KPIs agrégés par heure (MAE, MAPE, P90, `accuracy_band`) depuis `mv_xgb_vs_tomtom`. Sert widget `backtest_dashboard` pour courbe MAE + pie distribution. |
| `gold.v_velov_safety_advisory` **(NOUVEAU 2026-07-05, migration_045)** — JOIN dernier `silver.air_quality_clean` (fenêtre 3h) + dernière vigilance canicule `bronze.vigilance_meteo` dept 69 (fenêtre 12h). `status ∈ {ok,warning,severe,unknown}` — `unknown` si aucune des deux sources récente (jamais de faux "ok"). Sert `weather_widget`/`velov_trip`/`velov_widget` (Usager) via `dashboard/components/velov_safety_banner.py` : avertit sans bloquer le mode Vélov. |

### Vues `referentiel.*` (7)

Voir [§4.6](#46-referentiel--lieux--modes-de-transport).

### Vues `public.*` (2 — PostGIS standard)

| Vue | Rôle |
|-----|------|
| `public.geometry_columns` | Catalogue PostGIS des colonnes `geometry` (lecture seule, gérée par PostGIS). |
| `public.geography_columns` | Catalogue PostGIS des colonnes `geography`. |

---

## 6. Vues matérialisées (refresh périodique)

11 vues matérialisées, toutes dans `gold.*` sauf `osm.mv_sensor_to_way`.

| MV | Schéma | Taille | Refresh | Définition résumée |
|----|--------|--------|---------|---------------------|
| `mv_bus_traffic_spatial` | gold | — | */15 min `REFRESH CONCURRENTLY` | SELECT JOIN spatial 0.001° entre `tcl_vehicle_realtime` et `channels_ref` (top zones saturées bus × trafic). |
| `mv_congestion_propagation_pairs` | gold | — | quotidien 04h | Paires de capteurs avec lag cross-correlation Granger simplifié (cf. Axe 2 Sprint 15+). |
| `mv_fact_traffic_pivot` | gold | 92 MB | horaire | SELECT pivot temps × channel_id depuis `trafic_boucles_clean` (5-min granularity). Sert `correlation_matrix`. |
| `mv_line_kpis_live` | gold | — | horaire | Aggregations (OTP, retard, charge, fréquence) par ligne TCL depuis `tcl_vehicle_realtime` + cadences. |
| `mv_meteo_impact` | gold | — | quotidien 04h | Impact météo par mode (vent, pluie, temp) sur vitesse/cadence Vélov/fréquentation bus. |
| `mv_multimodal_grid` | gold | — | */10 min `REFRESH CONCURRENTLY` | Grille 0.01° Lyon : agrégation trafic + TCL temps réel + Vélov + météo. Score 0-10 + diagnostic. |
| `mv_otp_heatmap` | gold | 7.5 MB | horaire | Heatmap OTP triplets `(line_id, date, hour)` depuis `bus_delay_segments`. |
| `mv_sensor_saturation` | gold | — | */15 min par DAG `refresh_sensor_saturation` | Saturation %v85 + amplitude par capteur depuis `trafic_boucles_clean` (Sprint 22 Axe 6, remplace vue legacy). |
| `mv_velov_transit_coupling` | gold | — | */15 min par DAG `refresh_velov_transit_coupling` | Z-score vélos dispos par station Vélov < 300m zone TC (Sprint 17 Axe 4). `anomaly_detected = TRUE` si z<-2. |
| `mv_xgb_vs_tomtom` | gold | — | */30 min par DAG `refresh_xgb_vs_tomtom` | Paires (XGBoost H+1h, TomTom Flow) `ST_DWithin 200m, ±10 min` (Sprint 13+). |
| `mv_sensor_to_way` | osm | — | auto (sur triggers) | LATERAL KNN `<->` capteur → arête OSM la plus proche (< 200m). 41 737 arêtes couvertes. |

> **Note Sprint 18** : `osm.mv_sensor_to_way` est la MV critique qui permet d'injecter les vitesses capteurs dans `osm.ways.cost`. Si elle est vide → `refresh_traffic_costs()` ne fait rien → toutes les arêtes gardent `cost_default` (maxspeed OSM fixe).

---

## 7. Fonctions applicatives

12 fonctions **hors PostGIS** (les 1148 autres sont PostGIS standard, listés mais hors scope).

### `referentiel.*` (6)

| Fonction | Args | Retour | Usage |
|----------|------|--------|-------|
| `haversine_m(lat1, lon1, lat2, lon2)` | 4 doubles | `double precision` | Distance grand-cercle en mètres. Utilisée partout. |
| `estimate_car_trip(p_origin_lat, p_origin_lon, p_dest_lat, p_dest_lon, p_horizon_h, p_avg_speed_fallback_kmh)` | 6 doubles | TABLE `(... estimated_duration_min)` | Estimation rapide durée trajet voiture (utilisée comme fallback par `src/routing/`). |
| `estimate_velov_trip(...)` | 6 doubles | TABLE `(... segment, distance_m, duration_min, n_bikes_depart, n_docks_arrive)` | Itinéraire Vélov multi-segment, basé sur `referentiel.v_velov_neighbors`. |
| `nearest_traffic_nodes(lat, lon, k)` | lat, lon, k | TABLE `(... node_idx, properties_twgid, distance_m)` | K nœuds trafic les plus proches (pour itinéraire voiture). |
| `nearest_velov_stations(lat, lon, k, min_bikes, min_docks)` | 5 args | TABLE `(... station_id, distance_m, is_active)` | K stations Vélov filtrées par dispo minimale. |
| `predicted_speed_for_node(p_axis_key, p_horizon_h)` | 2 args | TABLE `(... speed_pred, etat_pred, color, calculated_at)` | Lit `gold.trafic_predictions` pour 1 nœud. |

### `osm.*` (3)

| Fonction | Args | Retour | Usage |
|----------|------|--------|-------|
| `refresh_traffic_costs()` | — | `integer` | **Injecte vitesses capteurs dans `osm.ways.cost`** (`*/15 min`). Lit `osm.sensor_positions` × `osm.mv_sensor_to_way` × dernier `gold.traffic_features_live.speed_kmh`. |
| `route_car(p_origin_lon, p_origin_lat, p_dest_lon, p_dest_lat)` | 4 doubles | TABLE `(... seq, edge_id, cost_s, agg_cost_s, length_m, road_name, geom_geojson)` | **Pathfinding voiture** (`pgr_dijkstra` sur `osm.ways`). Sprint 18 : remplace NetworkX H3. |
| `route_car_ksp(...)` | + `p_k` | TABLE `(... route_id, seq, ...)` | K-shortest paths voiture (alternatives). |

### `gold.*` (3)

| Fonction | Args | Retour | Usage |
|----------|------|--------|-------|
| `fn_network_health_score()` | — | TABLE `(... score 0-100, diagnosis, computed_at)` | **Axe 5 Sprint 15+** — Calcule le score santé réseau (0-100) avec redistribution poids si source indisponible. Sert widget `network_health_gauge` (Elu_1). |
| `check_dim_spatial_has_lat_lon()` | (trigger) | trigger | **Sprint 8** — Trigger BEFORE INSERT/UPDATE sur `dim_spatial_grid_mapping` : refuse lat/lon NULL pour canaux `real_string`. |
| `normalize_street_name(raw_name text)` | text | text | Normalisation noms de rues (lowercase + strip accents) pour matching inter-sources. |

---

## 8. Triggers

**1 seul trigger** sur la base de production.

| Trigger | Table | Type | Rôle |
|---------|-------|------|------|
| `trg_dim_spatial_has_lat_lon` | `gold.dim_spatial_grid_mapping` | BEFORE INSERT OR UPDATE (type 23) | **Sprint 8** — Refuse les INSERT/UPDATE avec `lat/lon NULL` pour les canaux de catégorie `real_string`. Catégories `integer_stringified` (créées par DAG legacy) peuvent avoir lat/lon NULL par construction (h3_id valide → backfill possible via `scripts/maintenance/backfill_dim_spatial_lat_lon.py`). |

> **Note** : la base ne contient **aucun trigger sur `bronze.*`** — le respect du schéma (e.g. dédup, géométrie duale) est garanti par **index uniques** et **CHECK constraints** plutôt que triggers.

---

## 9. Contraintes (PK, UK, CHECK)

**100 contraintes totales** dans les schémas applicatifs.

### Répartition par type

| Type | Count |
|------|-------|
| `PRIMARY KEY (p)` | ~50 |
| `UNIQUE (u)` | ~30 |
| `CHECK (c)` | ~13 |
| `FOREIGN KEY (f)` | ~10 |

### CHECK constraints notables

| Contrainte | Table | Définition |
|------------|-------|------------|
| `chk_dual_geom` | bronze.trafic_boucles | `(geom IS NULL) = (geom_4326 IS NULL)` — les deux géométries doivent être simultanément NULL ou non-NULL |
| `app_users_persona_id_check` | gold.app_users | `persona_id IN ('pro_tcl','elu','admin')` |
| `data_quality_log_status_check` | gold.data_quality_log | `status IN ('ok','warning','critical')` |
| `h3_trafic_live_etat_check` | gold.h3_trafic_live | `etat IN ('V','O','R','G')` |
| `network_health_history_score_check` | gold.network_health_history | `0 <= score <= 100` |
| `road_network_edges_length_pos` | gold.road_network_edges | `length_m >= 0` |
| `road_network_nodes_lat_check` | gold.road_network_nodes | `-90 <= lat <= 90` |
| `road_network_nodes_lon_check` | gold.road_network_nodes | `-180 <= lon <= 180` |
| `ck_calendrier_day_type` | referentiel.lieux_calendrier | `day_type IN ('weekday','saturday','sunday_holiday','vacation')` |

### Foreign keys

| FK | Table enfant → Table parent |
|----|------------------------------|
| `gold.channel_tomtom_mapping.channel_id → gold.channels_ref.channel_id` | Sprint 13+ |
| `gold.road_network_edges.from_osm_id → gold.road_network_nodes.osm_id` | |
| `gold.road_network_edges.to_osm_id → gold.road_network_nodes.osm_id` | |
| `osm.ways.source → osm.ways_vertices_pgr.id` | pgRouting |
| `osm.ways.source_osm → osm.ways_vertices_pgr.osm_id` | pgRouting |
| `osm.ways.target → osm.ways_vertices_pgr.id` | pgRouting |
| `osm.ways.target_osm → osm.ways_vertices_pgr.osm_id` | pgRouting |
| `osm.ways.tag_id → osm.configuration.tag_id` | pgRouting |
| `referentiel.lieux_transports.lieu_id → referentiel.lieux_lyon.lieu_id` ON DELETE CASCADE | |

> **Note** : la majorité des liens inter-tables sont **implicites** (e.g. `channel_id` partagé entre `bronze.trafic_boucles` et `gold.channels_ref` mais sans FK déclarée). C'est un choix de design Sprint 8+ pour rester flexible sur les ingestions (bronze peut recevoir des channel_ids inconnus).

---

## 10. Index notables & couverture des hot-paths

**238 indexes** au total. Focus sur les **hot-paths** (requêtes dashboard les plus fréquentes).

### Hot-path : trafic temps réel / prédictions

| Table | Index | Requête servie |
|-------|-------|----------------|
| `gold.traffic_features_live` | `idx_gold_traffic_channel_computed` (`channel_id, computed_at` INCLUDE speed_kmh, lag_1/2/3, rolling_mean_3) | `SELECT ... WHERE channel_id=? ORDER BY computed_at DESC LIMIT 1` (XGBoost predict live) |
| `gold.traffic_features_live` | `idx_gold_traffic_ml` (`channel_id, fetched_at` INCLUDE speed_kmh, lag_1/2/3, delta_current, delta_1, rolling_mean_3) | Dashboard widget "Prédiction vitesse" (cover index sans heap fetch) |
| `gold.trafic_predictions` | `idx_trafic_predictions_horizon_recent` (horizon_h, calculated_at DESC) | Carte Folium temps réel |
| `gold.trafic_predictions` | `idx_trafic_predictions_axis_horizon` (axis_key, horizon_h) | Lookup d'une ligne par axe/horizon |
| `gold.channel_tomtom_mapping` | PK on `channel_id` | Cross-validation TomTom/GL |
| `bronze.trafic_boucles` | `geom` GIST (2154), `geom_4326` GIST (4326) + `idx_trafic_boucles_troncon` | Buffer search cap sur carte Folium |

### Hot-path : Vélov

| Table | Index | Requête servie |
|-------|-------|----------------|
| `gold.velov_features` | `idx_gold_velov_features_station` (station_id_encoded, measurement_time DESC) | Widget "prédiction Vélov" par station |
| `gold.velov_features` | `idx_velov_features_station_id_measurement` (station_id, measurement_time DESC) | Lookup Vélov par ID brut |
| `gold.velov_predictions` | `idx_gold_velov_pred_station` (station_id, horizon_minutes) | Carte prédictions Vélov H+30/H+1 |
| `silver.velov_clean` | `silver_velov_uniq` UNIQUE (station_id, measurement_time) | Dédup transform |
| `silver.velov_clean` | `idx_silver_velov_station_time` (station_id, measurement_time DESC) | Lookup historique |

### Hot-path : Bus

| Table | Index | Requête servie |
|-------|-------|----------------|
| `gold.mv_otp_heatmap` | (DEFAULT) | Widget heatmap OTP (Pro_2) |
| `gold.mv_bus_traffic_spatial` | (DEFAULT) | Bottlenecks Élu (Elu_2 / Sprint 22++) |
| `gold.bus_delay_segments` | `idx_gold_bus_delay_line_time` (line_ref, date DESC) | Widget retards par ligne |
| `gold.bus_delay_segments` | PK composite (date, hour, line_ref, segment_id) | Dédup transform |

### Hot-path : Référentiel (lieux, Vélov)

| Vue/Table | Index | Requête servie |
|-----------|-------|----------------|
| `referentiel.v_lieux_velov_smart` (vue) | `referentiel.v_velov_neighbors` (vue mat-derived) | Itinéraire Vélov multi-bornes (Mon Trajet) |
| `referentiel.lieux_calendrier` | `uq_calendrier_line_day_hour` UNIQUE | Dédup transform cadences |

### Hot-path : Routage voiture (pgRouting)

| Table | Index | Requête servie |
|-------|-------|----------------|
| `osm.ways` | `ways_the_geom_idx` GIST (the_geom) | `pgr_dijkstra` NN |
| `osm.ways` | `idx_ways_cost` (cost WHERE > 0) | Dijkstra pondéré |
| `osm.ways` | `idx_ways_reverse_cost` (reverse_cost WHERE > 0) | Dijkstra dirigé bidirectionnel |
| `osm.sensor_positions` | `idx_sensor_positions_geom` GIST (geom) | `ST_DWithin 200m` vers `ways` |
| `osm.ways_vertices_pgr` | `ways_vertices_pgr_the_geom_idx` GIST | NN vertex |

### Hot-path : XGBoost training set

| Table | Index | Requête servie |
|-------|-------|----------------|
| `gold.xgb_training_set` | `idx_xgb_train_target_speed_not_null` (target_computed_at) WHERE target_speed NOT NULL | Sample XGBoost |
| `gold.xgb_training_set` | `idx_xgb_train_channel_target_at` (channel_id, target_computed_at DESC) | Lookup par capteur pour predict |

### Hot-path : TomTom coherence

| Table | Index | Requête servie |
|-------|-------|----------------|
| `gold.channel_tomtom_mapping` | PK channel_id | Cross-val TomTom ↔ GL |
| `gold.v_coherence_tomtom_vs_grandlyon` (vue) | — | Widget `coherence_scatter` |

### Hot-path : Data quality

| Table/Vue | Index | Requête servie |
|-----------|-------|----------------|
| `gold.data_quality_log` | `idx_gold_dql_checked_at_table` (checked_at DESC, table_name) | Widget log qualité |
| `gold.v_source_health` (vue) | — | Bandeau qualité Élu_1 |

### BRIN indexes (colonnes append-only)

| Table | Index BRIN | Bénéfice |
|-------|------------|----------|
| `bronze.comptages` | `idx_comptages_measurement_brin` (measurement_time) | Économise index bloated pour append-only |
| `bronze.pvotrafic_snapshots` | `idx_pvotrafic_collected_brin` (collected_at) | Idem |
| `bronze.tcl_vehicles` | `idx_tcl_vehicles_fetched_brin` (fetched_at) | Idem |
| `bronze.tomtom_traffic` | `idx_tomtom_fetched_brin` (fetched_at) | Idem |
| `bronze.trafic_boucles` | `idx_trafic_boucles_fetched_brin` (fetched_at) | Idem |
| `bronze.velov` | `idx_velov_fetched_brin` (fetched_at) | Idem |

> **Sprint 8+ leçon** : toutes les colonnes `fetched_at` Bronze utilisent BRIN quand append-only. Évite le bloated btree sur des millions de rows.

---

## 11. Lineage pipeline (qui alimente qui)

### Bronze → Silver

| Bronze | Silver | DAG / Fréquence |
|--------|--------|-----------------|
| `trafic_boucles` | `trafic_boucles_clean` + `trafic_vitesse_propre` | `transform_bronze_to_silver` (boucles) */5min |
| `tcl_vehicles` | `tcl_vehicles_clean` | `transform_bronze_to_silver` (TCL) */5min |
| `velov` | `velov_clean` | `transform_bronze_to_silver` (Vélov) */5min |
| `meteo` | `meteo_hourly` | `transform_bronze_to_silver` (météo) */1h |
| `chantiers` | `chantiers_actifs` | `transform_bronze_to_silver` (chantiers) 1x/jour |
| `air_quality` **(2026-07-05)** | `air_quality_clean` | `transform_bronze_to_silver` (air_quality) */5min |
| `pvotrafic_snapshots`, `comptages`, `vitesse_limite_ref`, `chantiers_voirie`, `chantiers_historique`, `parkings`, `prix_carburants`, `jours_feries`, `calendrier_scolaire`, `tomtom_flow`, `tomtom_traffic`, `vigilance_meteo` **(2026-07-05)** | (pas de silver direct — lus directement ou via gold.*) | — |

### Sécurité Vélov (2026-07-05, migration_045)

| Source | Cible | DAG / Fréquence |
|--------|-------|------------------|
| `silver.air_quality_clean` + `bronze.vigilance_meteo` | `gold.v_velov_safety_advisory` (vue, calculée à la volée) | Lu direct — pas de DAG de refresh dédié |
| `bronze.air_quality` | `silver.air_quality_clean` | `transform_bronze_to_silver` */5min |
| API Opendatasoft (vigilance météo dept 69) | `bronze.vigilance_meteo` | `collect_vigilance_meteo` */6h |

### Silver → Gold

| Silver | Gold | DAG / Fréquence |
|--------|------|-----------------|
| `trafic_boucles_clean` | `traffic_features_live` (XGBoost features), `h3_trafic_live`, `mv_fact_traffic_pivot`, `mv_sensor_saturation` | `transform_silver_to_gold` */15min |
| `tcl_vehicles_clean` | `bus_delay_segments`, `tcl_vehicle_realtime`, `mv_line_kpis_live`, `mv_otp_heatmap` | `transform_silver_to_gold` (bus) */15min |
| `velov_clean` | `velov_features`, `velov_predictions`, `mv_velov_transit_coupling` | `transform_silver_to_gold` (vélov) */1h |
| `meteo_hourly` | features (météo) injectées dans `traffic_features_live`, `velov_features`, `mv_meteo_impact` | — |

### Gold.training / Gold.predictions

| Source | Cible | DAG |
|--------|-------|-----|
| `traffic_features_live` (self-join computed_at+60min) | `xgb_training_set` | `build_xgb_training_set` quotidien 02h30 |
| `xgb_training_set` + GNN (`fact_traffic_series` via `dim_spatial_grid_mapping`) | `fact_correlation_matrix`, `dim_gnn_adjacency`, `stgcn_predictions_live` | `dag_daily_train` 03h (GNN) |
| `traffic_features_live` + `xgb_training_set` | `trafic_predictions` | `dag_live_speed_retrain` */30 min |
| `trafic_predictions` + `tomtom_traffic` (8.1, 13+) | `mv_xgb_vs_tomtom` | `refresh_xgb_vs_tomtom` */30 min |
| `velov_features` | `velov_predictions` | `dag_velov_retrain` */1 h :50 |

### OSM

| Source externe | Cible | DAG |
|----------------|-------|-----|
| Overpass API (Geofabrik Rhône-Alpes) | `gold.road_network_nodes`, `gold.road_network_edges` | `osm_init` (one-shot Sprint 18) |
| OSM (osm2pgrouting) | `osm.ways`, `osm.ways_vertices_pgr` | idem |
| `gold.traffic_features_live` → `osm.sensor_positions` (1 par canal) | Mapping temps réel | `refresh_osm_sensor_positions` */15 min |
| `osm.sensor_positions` × `ways` | `osm.mv_sensor_to_way` (LATERAL KNN <->) | refresh auto |
| `mv_sensor_to_way` + `traffic_features_live` | `osm.ways.cost`, `osm.ways.reverse_cost` | `osm.refresh_traffic_costs()` */15 min |

### Référentiel

| Source | Cible | Fréquence |
|--------|-------|-----------|
| Manuel (migration 016) | `referentiel.tarifs_modes` (gold) | 1-2x/an |
| Manuel (seed `lieux_lyon`, `lieux_transports`) | `referentiel.lieux_*` | 1x |
| `gold.tcl_vehicle_realtime` (7j glissants) | `referentiel.v_cadence_observed_7d` | calcul live |
| Idem | `referentiel.lieux_calendrier` | quotidien (DAG `refresh_lieux_calendrier`) |

### Sortie finale

```
gold.* → Streamlit dashboard (18 pages × 3 personas)
        → FastAPI endpoints (/api/traffic/*, /api/velov/*, /api/bus/*)
        → MLflow Tracking (gold.training runs/metrics)
```

---

## 12. Fréquences de rafraîchissement

### DAGs ingestion (bronze)

| Source | DAG | Fréquence | Cron |
|--------|-----|-----------|------|
| Grand Lyon boucles (pvotrafic OGC) | `collect_bronze` | */5 min | `*/5 * * * *` |
| TCL SIRI Lite | `collect_bronze` | */5 min | `*/5 * * * *` |
| Vélo'v GBFS | `collect_bronze` | */5 min | `*/5 * * * *` |
| Open-Meteo météo | `collect_bronze` | */1 h | `0 * * * *` |
| Open-Meteo AQ | `collect_bronze` | */1 h | `0 * * * *` |
| Chantiers | `collect_bronze` | 1x/jour | `0 3 * * *` |
| Vitesse limite ref | `collect_bronze` | 1x/sem | `0 4 * * 0` |
| Pistes cyclables + GTFS | `collect_bronze` | 1x/sem | `0 4 * * 0` |
| TomTom Traffic Flow | `collect_tomtom_traffic` | */15 min | `*/15 * * * *` (Sprint 13+) |
| Calendriers scolaires + jours fériés | `collect_calendriers_monthly` | mensuel | `0 0 1 * *` |
| Vigilance météo (canicule dept 69) **(NOUVEAU 2026-07-05)** | `collect_vigilance_meteo` | */6 h | `0 */6 * * *` |

### DAGs transformation (silver / gold)

| DAG | Fréquence | Cron |
|-----|-----------|------|
| `transform_bronze_to_silver` (5 parallèles) | */5 min | `*/5 * * * *` |
| `transform_silver_to_gold` (3 domaines) | */15 min | `*/15 * * * *` |
| `build_spatial_mapping` | 1x/jour | `0 1 * * *` |
| `mv_multimodal_grid` (REFRESH CONCURRENTLY) | */10 min | `*/10 * * * *` |
| `mv_bus_traffic_spatial` (REFRESH CONCURRENTLY) | */15 min | `*/15 * * * *` |
| `mv_sensor_saturation` | */15 min | `*/15 * * * *` |
| `mv_velov_transit_coupling` | */15 min | `*/15 * * * *` |
| `mv_line_kpis_live` (1 fois / h alignement) | */1 h | `0 * * * *` |
| `mv_xgb_vs_tomtom` | */30 min | `*/30 * * * *` |
| `mv_fact_traffic_pivot` | */1 h | `0 * * * *` |
| `mv_meteo_impact` | 1x/jour | `0 4 * * *` |
| `mv_congestion_propagation_pairs` | 1x/jour | `0 4 * * *` |
| `mv_otp_heatmap` | */1 h | `0 * * * *` |

### DAGs ML

| DAG | Fréquence | Cron |
|-----|-----------|------|
| `build_xgb_training_set` | 1x/jour | `30 2 * * *` |
| `dag_daily_train` (ST-GCN, GNN complet) | 1x/jour | `0 3 * * *` |
| `dag_live_speed_retrain` (XGBoost H+1h) | */30 min | `*/30 * * * *` |
| `dag_velov_retrain` (XGBoost H+30min, H+1h) | */1 h :50 | `50 * * * *` |

### DAGs maintenance

| DAG | Fréquence | Cron |
|-----|-----------|------|
| `maintenance.py` (VACUUM, ANALYZE, purge) | 1x/jour | `0 4 * * *` |
| `backfill_dim_spatial_lat_lon` | */5 min | `*/5 * * * *` (Sprint 8 hotfix) |
| `refresh_lieux_calendrier` | 1x/jour | `0 3 * * *` |
| `silver_archive_to_minio` | 1x/jour | `0 4 * * *` (Sprint 10+) |
| `refresh_osm_traffic_costs` (osm.refresh_traffic_costs) | */15 min | `*/15 * * * *` (Sprint 18) |
| `data_quality` (6 checks) | 1x/jour | `0 4 * * *` |
| `drift monitoring Evidently` | 1x/jour | `0 6 * * *` |

> **Sans conflit** : le scheduling Airflow est conçu pour que **deux DAGs ne touchent jamais la même table en même temps**. Voir `dags/maintenance/maintenance.py` pour la matrice d'exclusion.

---

## 13. Maintenance & Rétention

### Rétentions par table

| Table | Rétention | Stratégie purge |
|-------|-----------|-----------------|
| `bronze.trafic_boucles`, `pvotrafic_snapshots`, `tcl_vehicles`, `velov` | **7 j** | DELETE WHERE fetched_at < now() - interval '7 days' (DAG `maintenance.py` quotidien) |
| `bronze.air_quality`, `meteo` | **45 j** | DELETE WHERE fetched_at < now() - interval '45 days' |
| `bronze.chantiers_voirie` | **90 j** | DELETE WHERE fetched_at < now() - interval '90 days' |
| `silver.trafic_boucles_clean`, `velov_clean`, `tcl_vehicles_clean` | **30 j** | DELETE WHERE measurement_time < now() - interval '30 days' (après archivage MinIO) |
| `silver.meteo_hourly` | **2 ans** | DELETE WHERE measurement_time < now() - interval '2 years' |
| `silver.trafic_vitesse_propre` | **∞ (pas de purge)** | Croissance linéaire, ~30 MB/j. Voir partitionnement recommandé. |
| `silver.chantiers_actifs` | **∞** | Snapshot permanent chantiers actifs |
| `gold.traffic_features_live` | **30 j** | DELETE WHERE fetched_at < now() - interval '30 days' |
| `gold.xgb_training_set` | **14 j** | DELETE WHERE computed_at < now() - interval '14 days' |
| `gold.network_health_history` | **7 j** | DELETE WHERE recorded_at < now() - interval '7 days' |
| `gold.velov_features`, `velov_predictions` | **30 j** | DELETE WHERE measurement_time < now() - interval '30 days' |
| `gold.trafic_predictions` | **7 j** | DELETE WHERE calculated_at < now() - interval '7 days' |
| `gold.infrastructure_bottlenecks` | **30 j** | DELETE WHERE computed_at < now() - interval '30 days' |
| `gold.model_drift_reports` | **30 j** | DELETE WHERE computed_at < now() - interval '30 days' |
| `bronze.calendrier_scolaire`, `jours_feries` | **∞** | Référentiel mensuel, pas de purge |
| `referentiel.*` | **∞** | Référentiel statique |

### Routine VACUUM / ANALYZE

DAG `maintenance.py` quotidien 04h00 :

```sql
VACUUM (ANALYZE) bronze.trafic_boucles;
VACUUM (ANALYZE) silver.trafic_boucles_clean;
VACUUM (ANALYZE) gold.traffic_features_live;
-- etc., toutes les tables > 1M rows
```

### Alerte maintenance — `silver.trafic_vitesse_propre`

Cette table cumule **29.7 GB / 1.55M rows en 18 mois** et n'a aucune purge automatique. Scénarios alternatifs :

1. **Partitionnement par mois** (recommandé Sprint 24+) :
   ```sql
   CREATE TABLE silver.traffic_vitesse_propre_new (...)
     PARTITION BY RANGE (transformed_at);
   CREATE TABLE silver.tvp_2026_07 PARTITION OF silver.traffic_vitesse_propre_new
     FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
   -- etc.
   ```
2. **Purge contrôlée** : ne garder que les 24 derniers mois.
3. **Archivage MinIO** : Parquet snappy, comme `archive.*` mais sans index de service.

### Index morts (déjà purgés — Sprint 22)

cf. `scripts/sql/migration_038_drop_dead_indexes.sql`.

### Migrations récentes (par Sprint)

cf. `scripts/sql/migration_NNN_*.sql`. Liste :

- `migration_014_gold_coherence_tomtom_v2.sql` (Sprint 13+)
- `migration_015_aggregate_line_ref.sql` (Sprint 7+)
- `migration_016_tarifs_modes.sql` (Sprint 15+)
- `migration_017_multimodal_grid.sql` (Sprint 15+)
- `migration_018_bus_traffic_spatial.sql` (Sprint 15+)
- `migration_019_network_health.sql` (Sprint 15+)
- `migration_020_xgb_vs_tomtom.sql` (Sprint 16)
- `migration_021_source_health.sql` (Sprint 16)
- `migration_022_meteo_impact.sql` (Sprint 22 Axe 7)
- `migration_023_velov_transit_coupling.sql` (Sprint 17 Axe 4)
- `migration_024_congestion_propagation.sql` (Sprint 22 Axe 2)
- `migration_025_data_quality_log.sql`
- `migration_026_pgrouting_osm_network.sql` (Sprint 18)
- `migration_027_reconcile_pgrouting_schema.sql`
- `migration_028_fix_sensor_to_way.sql` + `028b_fix_mv_sensor_to_way_fast.sql`
- `migration_029_idx_ways_cost.sql`
- `migration_030_network_health_history.sql`
- `migration_032_route_car_ksp.sql`
- `migration_033_sensor_saturation.sql` (Sprint 22 Axe 6)
- `migration_034_sensor_saturation_mat.sql`
- `migration_035_mv_latest_sensor_position.sql`
- `migration_036_bus_traffic_spatial_48h.sql`
- `migration_037_idx_purge_traffic_features_live.sql`
- `migration_038_drop_dead_indexes.sql`
- `migration_039_perf_optimizations_applied.sql`

### Backups

- **DB quotidienne 03:00** via `scripts/backup.sh` (pg_dump full).
- **Offsite (Sprint VPS-2)** : via `scripts/backup-offsite.sh` → rclone vers Google Drive (systemd timer `lyonflow-backup.timer`). Action user requise (OAuth rclone).
- **Métadonnées restauration** : cf. `docs/RUNBOOK.md`.

### Gotchas PostgreSQL (rappel `lyonflow-postgresql.md`)

- **Postgres dump CRON concurrent = saturation** : `ps auxf | grep pg_dump` AVANT toute migration / autre dump. Nettoyer `/tmp/lyonflow_*.dump` côté container si tué.
- **Postgres client timeout ≠ query killed** : si `bash timeout` expire sur une query, elle continue côté serveur. Vérifier `pg_stat_activity` avant de relancer.

---

## 14. Glossaire

| Terme | Définition |
|-------|------------|
| **Medallion** | Architecture bronze/silver/gold — données brutes → nettoyées → analytique. |
| **H3** | Système d'indexation hexagonale Uber (résolutions 0-15). Lyon utilise res.10 (~50m), res.13 (~3m). |
| **pgRouting** | Extension Postgres pour le routage graphe (Dijkstra, A*, KSP, etc.). |
| **Channel ID (LYO)** | Identifiant capteur Grand Lyon (format `LYO00001`). |
| **`properties_twgid`** | Identifiant capteur H3 (legacy) — `gold.dim_spatial_grid_mapping` fait le mapping `properties_twgid ↔ channel_id (LYO)` via `mv_twgid_to_lyo`. |
| **Sprint** | Itération de développement LyonFlow (Sprint 1 → Sprint 22++). |
| **Persona** | Profil utilisateur dashboard : `pro_tcl` (opérateur TCL), `elu` (décideur Métropole), `usager` (citoyen), `admin` (technique). |
| **MVP** | Vue matérialisée. |
| **XGBoost H+1h** | Modèle gradient-boosting pour prédire la vitesse trafic à H+1 heure. |
| **GNN ST-GCN** | Graph Neural Network Spatio-Temporal (GRU + GCNConv × 2). |
| **TomTom** | Service externe de trafic (Flow API, tuiles 0.02°). Cross-validation Grand Lyon. |
| **PGR** | Plan de Gestion Réaliste (terme interne). |
| **Axe 1-7** | Axes d'optimisation interdépendances multimodales (cf. `docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md`). |
| **MV REFRESH CONCURRENTLY** | Commande qui permet de rafraîchir une vue matérialisée sans lock exclusif. |

---

## 15. Liens utiles

| Doc | Contenu |
|-----|---------|
| [`CLAUDE.md`](./CLAUDE.md) | Mémoire projet globale (pile, sprints, dette schéma). **Source de vérité**. |
| [`docs/POSTGRES_TUNING_PROD.md`](./POSTGRES_TUNING_PROD.md) | Paramètres tuning Postgres production (VPS). |
| [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md) | Architecture globale LyonFlow (Medallion, ML, dashboard). |
| [`docs/DASHBOARD_PAGES.md`](./DASHBOARD_PAGES.md) | Description des 18 pages × 3 personas (5 Usager + 6 Pro TCL + 5 Élu + Accueil + RGPD + A Propos). |
| [`docs/MONITORING.md`](./MONITORING.md) | Prometheus / Grafana / Alertmanager (Sprint 8+). |
| [`docs/RUNBOOK.md`](./RUNBOOK.md) | Procédures d'exploitation (incident, restore, scale). |
| [`docs/DATA_GOVERNANCE.md`](./DATA_GOVERNANCE.md) | Gouvernance données, RGPD, consent, purge. |
| [`docs/AUDIT_PROJET_2026-06-30.md`](./AUDIT_PROJET_2026-06-30.md) | Audit projet le plus récent. |
| [`docs/AUDIT_DB_2026-06-30.md`](./AUDIT_DB_2026-06-30.md) | Audit DB le plus récent. |
| `scripts/sql/migration_NNN_*.sql` | 38 fichiers de migration (DDL versionné). Source canonique du schéma. |
| `src/data/db_query.py` | 2 160 lignes — toutes les requêtes SQL consommées par le dashboard. Reflet exact des `gold.*` consommés. |
| `dags/` | DAGs Airflow (bronze / transforms / ml / maintenance). |
| `archive/sprints/` | Rapports de sprint historiques. |

### Connexions & authentification

| Méthode | Commande |
|---------|----------|
| **psql local → VPS DB** | `ssh ubuntu@51.83.159.224 "sudo docker exec -it lyonflow-postgres psql -U lyonflow -d lyonflow"` |
| **psql direct (si port forward)** | `PGPASSWORD=*** psql -h 51.83.159.224 -p 5432 -U lyonflow -d lyonflow` |
| **Healthcheck** | `./scripts/healthcheck-vps.sh` (20 checks) |
| **Backup manuel** | `ssh ubuntu@51.83.159.224 "cd /opt/lyonflow && bash scripts/backup.sh"` |
| **Restore** | cf. `docs/RUNBOOK.md` §4 |

### Variables d'environnement critiques (cf. `.env.example`)

```
POSTGRES_HOST=postgres          # DNS Docker interne (postgis/pgrouting image)
POSTGRES_PORT=5432
POSTGRES_DB=lyonflow
POSTGRES_USER=lyonflow
POSTGRES_PASSWORD=<chmod 600>
POSTGRES_AIRFLOW_DB=airflow
POSTGRES_MLFLOW_DB=mlflow
```

---

## Annexes

### A. Note sur les contraintes et la dette schéma

- **`bronze.trafic_boucles` → `gold.traffic_features_live`** : le typage `vitesse` (real) → `speed_kmh` (double) introduit une perte de précision négligeable. Sprint 8 n'a pas re-typé la colonne Bronze pour éviter une migration 18+ GB.
- **`gold.trafic_predictions.etat_pred`** : CHAR(1) avec valeurs `V|O|R|G` (vert/orange/rouge/gris). Héritage historique. Pour affichage : `gold.v_traffic_combined.color` est utilisé (libellé affiché).
- **`gold.infrastructure_bottlenecks`** (Sprint 22++) : la table existe encore mais **n'est plus alimentée**. La logique vit désormais dans `gold.mv_bus_traffic_spatial`. Voir `Elu_2_Bottlenecks` widget.

### B. Stack d'observabilité

| Stack | Endpoints |
|-------|-----------|
| Prometheus | `http://51.83.159.224:9090` (non exposé Nginx, accès SSH) |
| Grafana | `http://51.83.159.224:3000` (idem) |
| Alertmanager | `http://51.83.159.224:9093` (idem) |
| pgAdmin | non installé (CLI psql seul) |
| MLflow | `http://51.83.159.224:5000` (via Nginx, Basic Auth) |
| Streamlit | `https://51.83.159.224:8501` (via Nginx, TLS self-signed) |

### C. Scripts de référence rapide

```bash
# Toutes les tables par taille
ssh ubuntu@51.83.159.224 "sudo docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -c \"
SELECT n.nspname||'.'||c.relname AS table,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS size
FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')
ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 30;
\""

# Toutes les MVs dernière refresh
ssh ubuntu@51.83.159.224 "sudo docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -c \"
SELECT schemaname||'.'||matviewname AS matview,
       last_refresh,
       ispopulated
FROM pg_matviews
JOIN (SELECT NULL::timestamp) _(0) ON true
ORDER BY schemaname, matviewname;
\""
# (pg_matviews ne stocke pas last_refresh, voir dans les DAGs)

# Locks actifs
ssh ubuntu@51.83.159.224 "sudo docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -c \"
SELECT relation::regclass, mode, granted, pid
FROM pg_locks
WHERE relation IS NOT NULL AND mode IS NOT NULL
ORDER BY relation, mode;
\""

# Long-running queries
ssh ubuntu@51.83.159.224 "sudo docker exec lyonflow-postgres psql -U lyonflow -d lyonflow -c \"
SELECT pid, now() - query_start AS duration, state, query
FROM pg_stat_activity
WHERE query_start < now() - interval '1 minute'
  AND state != 'idle'
ORDER BY duration DESC;
\""
```

---

**Dernière mise à jour** : 2026-07-01 — généré par introspection live (`psql` → VPS) + cross-référencement `scripts/sql/` + `src/data/db_query.py`.

**Mainteneur du doc** : ce document doit être régénéré à chaque sprint qui touche la DB (nouvelle MV / table / vue / index majeur).
