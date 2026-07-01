# CLAUDE.md — LyonFlow

> Mémoire projet — **dernière mise à jour : 2026-07-01, préparation certification RNCP 38777** (600 tests verts, dashboard 18 pages / 59 widgets, zéro mock, ruff clean, 25/27 DAGs actifs). Voir "État au 2026-07-01" ci-dessous et `docs/AUDIT_CERTIFICATION_2026-07-01.md` pour le rapport complet.

## Projet

LyonFlow est une plateforme MLOps end-to-end de prédiction et d'analyse du trafic multimodal sur la Métropole de Lyon. Elle fusionne trois repos sources (caroheymes/Architect-IA-final-project, PDUCLOS/LyonFlow, PDUCLOS/lyontraffic) en un projet unifié.

**Auteur** : Patrice DUCLOS — Senior Data Analyst, Jedha RNCP 38777 (Architecte en IA)
**Repo** : PDUCLOS/lyonflow
**Cible production** : **VPS unique** `51.83.159.224` (Ubuntu, 6 CPU, 12 Go RAM, **2× 100 Go SSD** : sda = OS + code, sdb = PostgreSQL + MinIO + **Docker data-root** depuis Sprint 9+).

**Version actuelle** : **v0.12.1** (Sprints 1-7 + VPS 1-8 + 9+ + 11+ + 12+ + 13 + 13+ + 15+ + 17 + 17+ + 18 + 20 + 21 + 22 + 22+ + 22++) — branche `vps` ACTIVE
**Statut** : production VPS stable. Voir CHANGELOG.md pour le détail de chaque sprint.

### État au 2026-07-01 (Purge GNN + bugfixes prod + MLOps + certification RNCP)

> Commité localement (`0cc2693`), pas encore pushé sur `origin/vps`.

- **Purge GNN du code actif** : tandem GNN archivé Sprint 24+ mais des traces actives subsistaient (fonctions mortes, config, docs). Nettoyage complet :
  - `src/routing/graph.py` : viré `build_routing_graph`, `get_node_speed`, `get_nearest_node` (0 appelant réel, legacy H3 K=2 remplacé par pgRouting Sprint 18).
  - `training/` : dossier supprimé (package vide depuis l'archivage, 0 import).
  - `src/config.py` : viré 6 champs hyperparams GNN morts (`seq_len`, `horizons`, `hidden_channels`, `weight_jam`, `weight_slow`, `gnn_map_visible`).
  - `src/api/main.py`, `pyproject.toml` (per-file-ignores morts), CLAUDE.md (stack/piliers ML/provenance/structure/env vars), dashboard (wording user-facing).
  - **Piège évité** : `gold.dim_gnn_adjacency` n'était pas mort — sert `gold.mv_congestion_propagation_pairs` (Axe 2, indépendant du GNN). Renommée `gold.dim_spatial_adjacency` (migration_040, appliquée VPS, 12865 lignes préservées) plutôt que supprimée.
- **Bugs prod trouvés + fixés** (déployés VPS) :
  - `traffic_map.py` : crash `TypeError: Expected numeric dtype` — colonnes NUMERIC psycopg2 (Decimal) non coercées avant `.round()`. Fix via nouveau helper `_coerce_numeric_columns` (`src/data/data_loader.py`).
  - `cached_predictions_vs_actuals` manquante dans `data_cache.py` — crash `ImportError` sur `Usager_3_Notre_Modele.py` et `Usager_5_Statut_Service.py`. `gold.predictions_vs_actuals` (backtest) avait été archivée avec le GNN Sprint 24+ sans mettre à jour ces 2 pages (ajoutées après, Sprint 22+). Fix : lit `gold.trafic_predictions` (live) à la place.
  - `model_monitoring.py` : badge "XGB H+60min dispo" toujours ❌ — `ModelRegistry.is_available()` vérifie un fichier local (`/app/models/xgb_speed_h60.json`) inexistant car le container `streamlit` n'a aucun volume `models/` monté. Fix : check fraîcheur `gold.trafic_predictions` à la place.
  - Titre carte Pro_1 clarifié : "Trafic — Live (temps réel) vs H+1h (prédit)".
- **Incidents I/O VPS récurrents (3× dans la session)** : `refresh_traffic_costs` et `mv_sensor_saturation` bloqués 20-45 min en boucle, saturant sdb. Root cause : `execution_timeout` Airflow tue le worker Python mais **pas** la requête Postgres sous-jacente (I/O bloquant insensible à l'annulation) → pileup de sessions zombies à chaque cycle `*/15min`. Fix : `statement_timeout=240s` ajouté aux connexions psycopg2 de `refresh_osm_traffic_costs.py` et `refresh_sensor_saturation.py`. Tuning `idle_in_transaction_session_timeout` 0→10min appliqué (confirmé actif). **Root cause de fond non réglée** : thundering herd `:00`/`:30` (10 DAGs concurrents, cf. `docs/AUDIT_AIRFLOW_POSTGRES_SPRINT24.md` item C1/#3) — la vraie priorité pour éliminer ces incidents plutôt que les mitiger.
- **`build_spatial_mapping` — RÉSOLU** (était en échec 8+ jours, 2026-06-20 → 2026-06-27). Root cause double : requête sans borne temporelle (10,2M lignes scannées, cost 483k) + ~30 000 connexions Postgres individuelles/run (1 par ligne/arête). Fix : requête bornée 24h (cost 99k, -80%, 17.7s mesuré vs >8min avant) + connexion unique réutiluée + `statement_timeout=480s`. Run manuel validé : succès en 30s, `dim_spatial_grid_mapping` (3946 lignes) + `dim_spatial_adjacency` (58061 arêtes) rafraîchis.
- **`maintenance_backfill_dim_spatial_lat_lon` — RÉSOLU** (unpaused + déclenché). 1543 lignes `dim_spatial_grid_mapping` sans lat/lon → 0 après backfill.
- **`maintenance_record_network_health` — bug trouvé + corrigé** : `execute_query(fetch=True)` — kwarg inexistant, DAG en échec silencieux depuis sa création (2026-06-22). `gold.network_health_history` était vide depuis toujours → sparkline santé réseau (widget Élu) cassée. Kwarg retiré, DAG unpaused + testé, première ligne insérée.
- **`silver_archive_to_minio` — unpaused** (connectivité MinIO vérifiée, buckets OK). Tournera sur son schedule normal (04h00) pour archiver `silver.trafic_vitesse_propre` (29 Go).
- **DB control — RÉSOLU** : `VACUUM FULL osm.ways` (1,4 Go/3,8M tuples morts → 39 Mo/0 mort, routing revérifié fonctionnel) + `VACUUM FULL silver.meteo_hourly` (718% bloat → 0). `ANALYZE` global relancé (stats remises à jour après recréation container). Mémoire container Postgres 2,5G → **4G** (alignée sur le tuning interne déjà actif).
- **Nouveau DAG `dag_inference_velov.py`** — miroir de `dag_inference_xgboost.py`. `gold.velov_predictions` était vide depuis toujours (0 ligne, aucun jamais) : le modèle Vélov s'entraînait mais rien ne persistait de prédiction. 454 lignes produites au premier cycle, widget `Usager_1_Mon_Trajet` confirmé sans erreur.
- **MLflow Model Registry — faux "vide" résolu** : client `mlflow` 3.14.0 (dashboard/API, non épinglé) incompatible avec le serveur 2.12.1 (2.x) — `search_registered_models()` retournait `[]` silencieusement. Fix : `mlflow<2.16` + `setuptools<81` (pkg_resources retiré en v81) épinglés dans `requirements-base.txt`, images `streamlit`/`api` rebuild + redéployées. Confirmé : 6 modèles versionnés, stage Production, visibles depuis tous les containers.
- **Drift monitoring réactivé** : `refresh_xgb_vs_tomtom` + `daily_drift_report` étaient pausés (dépendance en cascade), `gold.model_drift_reports` mort depuis 2026-06-06 (25 jours). Les deux unpaused, premier cycle confirmé succès.
- **`retrain_xgboost_speed` pausé intentionnellement** : redondant avec `dag_daily_speed_train` (source `gold.xgb_training_set` ne change qu'1×/jour, un retrain horaire produisait 24 runs MLflow bit-identiques/jour, vérifié à 12 décimales).
- **Bilan DAGs** : 25/27 actifs (était ~20/26 avec plusieurs en échec silencieux). Les 2 pausés restants sont documentés et intentionnels (`retrain_xgboost_speed`, `refresh_heavy_mv` — ce dernier lié au retrait en cours d'`infrastructure_bottlenecks`, C2).
- **Docs** : triage complet (voir `archive/README.md` mis à jour) — 17 docs déplacés vers `archive/{sprints,audits,analysis,misc}/` (specs/rapports livrés, snapshots datés). `docs/POSTGRES_TUNING_PROD.md` et `docs/AUDIT_AIRFLOW_POSTGRES_SPRINT24.md` mis à jour avec statut réel. Rapport complet pour certification RNCP : `docs/AUDIT_CERTIFICATION_2026-07-01.md`.

> **Historique détaillé des sprints antérieurs** (22++ → Sprint 5) : voir
> `CHANGELOG.md` (changelog structuré par version) et `archive/sprints/`
> (rapports complets). Retiré d'ici le 2026-07-01 pour garder ce fichier
> exploitable — c'était ~200 lignes de narration déjà dupliquée ailleurs.

## Décisions ouvertes (en attente Patrice)

| Item | Statut | Impact si pas tranché |
|------|--------|----------------------|
| **`rclone config` destination offsite** | 🔴 Pending (interactif OAuth) | Backup-offsite fail clean tous les jours, journalctl spam |
| **Prometheus absent** (intentionnel Sprint 15+) | 🟡 À confirmer | Grafana affiche "no data" sur dashboards provisionnés |
| **Phase 3 / Phase 4 (K8s, cloud-demo)** | 🌑 Dormant | Aucune action avant AWS/GCP post-Jedha |
| **Axes spec interdépendances (2/4/6/7)** | ⏸ À planifier | Pas bloquant pour RNCP 38777 |
| **Thundering herd `:00`/`:30`** (10 DAGs concurrents) | 🟡 Mitigé (2026-07-01) | 5 DAGs re-décalés hors `:00/:15/:30/:45`, root cause de fond (contention CPU/IO partagée) toujours présente mais moins de collisions exactes |
| **C2 — retrait `infrastructure_bottlenecks`** | 🟡 Étape 1/5 faite (writer pausé) | Étapes 3-5 (migrer 2 widgets + DROP TABLE) reportées à un créneau dédié (~6h, risque moyen) |
| **`silver.trafic_vitesse_propre` 29 Go** | 🟡 Archivage MinIO relancé (2026-07-01) | DAG unpaused, tournera cette nuit (04h00, ~2h), libérera l'espace progressivement |

**Recommandation par défaut** (si pas de décision user explicite) :
- rclone : GCP Service Account JSON (pas d'OAuth, automation-friendly)
- Prometheus : laisser absent (Sprint 15+ justifié, exporters coûtent 200 MB mais Grafana mort de toute façon)
- Axes 2/4/6/7 : Axe 6 (qualité données) en priorité 1 post-Jedha

### Roadmap interdépendances (7 axes — voir `docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md`)
- ✅ **Axe 1** : grille multimodale 0.01° (fusion trafic + TCL + Vélov + météo)
- ✅ **Axe 3** : bus × trafic spatialisé (JOIN zone 100 m)
- ✅ **Axe 5** : score santé réseau 0-100 (`gold.fn_network_health_score()` + jauge `network_health_gauge.py`, bandeau Élu)
- ⏸ **Axe 6** : qualité données (`data_quality.py`, port LyonTraffic) — priorité 1 post-Jedha
- ⏸ **Axe 4** : report modal Vélov ↔ TC (PostGIS ST_DWithin 300 m, z-score)
- ⏸ **Axe 2** : propagation congestion (lag cross-correlation Granger simplifié)
- ⏸ **Axe 7** : météo comme variable d'interaction (impact quantifié par mode)

### Roadmap TomTom (3 niveaux — voir CHANGELOG.md pour décision utilisateur)
- ✅ **Niveau 1** : ingestion propre + cohérence sources + détecteur capteur HS
- ⏸ **Niveau 2** : backtest engine — MAE croisé XGBoost vs TomTom (oracle externe), drift detection Evidently (réactivé 2026-07-01, cf. état ci-dessus)
- ⏸ **Niveau 3** (optionnel) : TomTom Routing API pour routing voiture temps réel — payant, gain UX marginal vs Niveau 2

### Phases

- ✅ Phase 1 — Production-ready local (branche `main`, Sprints 1-7)
- ✅ **Phase 2 — Déploiement VPS production (branche `vps`, ACTIVE)** — Sprints VPS 1-8
- ⏸ Phase 3 (futur, AWS/GCP) — Kubernetes (branche `kubernetes`, dormante)
- ⏸ Phase 4 (futur, AWS/GCP) — Cloud démo Jedha (branche `cloud-demo`, dormante)

Voir [AGENTS.md](AGENTS.md) pour les conventions et la mémoire projet.

---

## Règles projet

- **Pas de changement de repo/commit/push sans accord explicite de l'utilisateur**
- **Déploiement : VPS unique (51.83.159.224)** — branche `vps` = cible production
- **Pas de merge `kubernetes` ni `cloud-demo` dans `vps` ou `main`** (dormantes, futur AWS/GCP)
- **🔴 BACKUP OFFSITE OBLIGATOIRE** (Sprint VPS-2) — Ne JAMAIS laisser de backup persistant sur sdb. Stream pur vers Google Drive via rclone ou serveur SSH distant. Cf. `scripts/backup-offsite.sh`. Disque sda1 à 64% (35 Go libres sur 96 Go) après migration Docker data-root Sprint 9+.
- **🔴 DOCKER DATA-ROOT SUR SDB** (Sprint 9+ 2026-06-17) — `/etc/docker/daemon.json` = `{"data-root": "/mnt/postgres-data/docker"}`. **NE PAS revenir à /var/lib/docker** sans migration formelle — risque saturation sda1. Toutes les images + containers + volumes Docker sont sur sdb (29 Go).
- Langue : français pour pipeline/docs, anglais pour code modèle
- **SQL paramétré partout**, zéro f-string dans les requêtes (`psycopg2 %s`)
- **🔴 ZÉRO MOCK DANS LE PROJET** (Sprint 8, 2026-06-12) — Variable d'env `LYONFLOW_DEMO_MODE=0` obligatoire en prod. Toute source de données indisponible (PostgreSQL, Airflow, MLflow) lève `DashboardDataError` et le widget affiche `st.error`. Mode démo **supprimé** (helper `_is_demo_mode()` retourne toujours `False` — déprécié, à retirer Sprint 9+). Plan détaillé : [docs/PLAN_NO_MOCK_VPS.md](docs/PLAN_NO_MOCK_VPS.md).
- **🔴 RÉFÉRENTIEL LIEUX EN DB** (Sprint VPS-6) — Tables `referentiel.lieux_lyon` (21 lieux emblématiques), `referentiel.lieux_transports` (56 liaisons), `referentiel.lieux_calendrier` (223 cadences weekday). Plus de mock codé en dur.
- **🔴 BACKFILL lat/lon obligatoire** (Sprint 8) — Le DAG `maintenance_backfill_dim_spatial_lat_lon` tourne toutes les 5 min et dérive les coords depuis `h3_id` (h3-py 4.5). Trigger SQL `trg_dim_spatial_has_lat_lon` refuse les INSERT avec lat/lon NULL pour les canaux `real_string`.
- **Fiabilité VPS** (Sprint 8+) — DAGs critiques ont `retries=0` (le cycle suivant rattrape). Prometheus + Alertmanager + Grafana UP. Healthcheck `scripts/healthcheck-vps.sh` 20 checks.

---

## Stack technique

| Couche | Technologie |
|--------|-------------|
| Orchestration | Apache Airflow 2.9 (**10 DAGs actifs** + 1 cron backfill + 1 archive silver + 1 TomTom */15 + 1 **refresh_osm_traffic_costs** */15) |
| Base de données | PostgreSQL 16 + PostGIS 3.5 + **pgRouting 3.7.3** (4 schémas : bronze/silver/gold/osm + referentiel). Image Docker : `pgrouting/pgrouting:16-3.5-3.7.3` |
| ML Tracking / Registry | MLflow 2.12 |
| ML Trafic | XGBoost **H+1h uniquement** (1 modèle, focus fiabilité VPS) — toutes les 30 min |
| ML Vélov | XGBoost (label encoding, H+1h) — toutes les heures :50 |
| ML Bus | XGBoost delay (phase analyse — collecte SIRI Lite en prod) |
| API | FastAPI |
| Dashboard | Streamlit multi-pages (18 pages × 3 personas — 5 Usager + 6 Pro TCL + 5 Élu + Accueil + RGPD + A_Propos) |
| Monitoring | Prometheus + Alertmanager + Grafana (stack monitoring Sprint 8+) |
| Transformation | psycopg2 pur (pas de Polars dans Airflow) |
| CI/CD | GitHub Actions |
| Infra | Docker Compose (2 fichiers : `docker-compose.yml` + `docker-compose.monitoring.yml`) |
| Reverse proxy | Nginx 1.27 |

---

## 4 Piliers ML

### 1. Trafic routier : XGBoost

| Modèle | Rôle | Retrain | Force |
|--------|------|---------|-------|
| XGBoost speed H+1h | Réactif — changements récents | Toutes les 30 min | Météo/vacances/lags, focus fiabilité |

> Le tandem GNN (ST-GRU-GNN spatial) a été archivé Sprint 24+ (2026-06-30) —
> voir table « Supprimé / Archivé ». XGBoost H+1h est l'unique modèle trafic en production.

### 2. Bus : Analyse → Prédiction

**Phase 1 — Analyse** (collecte SIRI Lite, Sprint 7+ en prod) :
- Retard agrégé par tronçon de ligne, tranche horaire, jour, météo, vacances
- Détection accumulation retard sur le parcours

**Phase 2 — Croisement infrastructure** :
- Bus retard + trafic congestionné = problème infrastructure
- Bus retard + trafic fluide = problème opérationnel
- Trafic congestionné + bus OK = voie dédiée fonctionnelle

**Phase 3 — Prédiction** (quand données suffisantes) :
- XGBoost delay : prédire `delay_seconds` par ligne/segment/heure
- Features : heure, jour, vacances, météo, vitesse trafic adjacente, historique retard

### 3. Vélov : H+1h, économe

- **H+1h uniquement** (focus H+1h strict comme le trafic — H+30min plus entraîné depuis Sprint VPS-6, `xgb_velov_h30.pkl` orphelin)
- Label encoding stations (pas 458 one-hot → économie RAM de 9GB à ~500MB)
- **Features Sprint 8+ (référentiel schema v0.3.1)** : `station_id_encoded, bikes_lag_1/2/3, rolling_mean_3h, hour_sin/cos, temperature_c, rain_mm, is_vacances, is_ferie`
- Retrain **hourly :50**

### 4. Recommandation trajet multimodale

Pour chaque mode (voiture, bus/tram, vélov, marche, métro) :
- **Voiture** : **pgRouting `pgr_dijkstra` sur réseau routier OSM** (Sprint 18) — `compute_itinerary()` → `osm.route_car()` (~87k vertices, ~101k arêtes). Trafic temps réel injecté `*/15 min` via `osm.refresh_traffic_costs()` (41 737 arêtes mappées à capteurs Grand Lyon < 200m).
- **Bus/Tram** : prédiction retard SIRI → temps ajusté
- **Vélov** : smart routing (Sprint VPS-6) — `plan_velov_trip()` avec scoring composite (distance + vélos/docks dispo), alternatives si borne #1 VIDE/PLEINE, maillage voisines < 200m
- **Marche** : distance (toujours disponible)
- **Métro** : GTFS (fiable, peu de retard)

**Scoring composite** : 50% temps + 30% coût + 20% éco (CO2)

---

## Pipeline de Données — Architecture Medallion

### Bronze (Ingestion — 8 sources, Sprint 8+ toutes fonctionnelles)

| Source | Fréquence | Table | Statut |
|--------|-----------|-------|--------|
| Grand Lyon boucles (pvotrafic OGC) | */5 min | `bronze.trafic_boucles` | ✅ 12/h |
| TCL SIRI Lite | */5 min | `bronze.tcl_vehicles` | ✅ 11/h |
| Vélo'v GBFS | */5 min | `bronze.velov` | ✅ 11/h |
| Open-Meteo weather | */1h | `bronze.meteo` | ✅ 13/h |
| Open-Meteo air quality | */1h | `bronze.air_quality` | ✅ 72 records/test (Sprint 8 fix) |
| Grand Lyon chantiers | 1x/jour | `bronze.chantiers` | ✅ 428 records (Sprint 8 fix) |
| Vitesse limite ref | 1x/semaine | `bronze.vitesse_limite_ref` | ✅ |
| Pistes cyclables + GTFS | 1x/semaine | `bronze.infra_ref` | ✅ |
| TomTom Traffic Flow | */15 min | `bronze.tomtom_traffic` | ✅ ACTIF (Sprint 13+, classe `TomTomTrafficFlow(DataCollector)`) — cross-validation Grand Lyon |

Tables référentielles (peuplées mensuellement) :
- `bronze.calendrier_scolaire` (Zone A, data.education.gouv.fr)
- `bronze.jours_feries` (calendrier.api.gouv.fr)

Chaque table Bronze : `fetched_at TIMESTAMPTZ` + `raw_data JSONB` + colonnes extracted (nullable). Immutable. Rétention par purge (7j→45j selon volume).

### Silver (Nettoyage — 5 tables)

| Table | Source | Transformation |
|-------|--------|---------------|
| `silver.trafic_boucles_clean` | bronze.trafic_boucles | Dédup DISTINCT ON, capteurs sains, géo 4326+2154 |
| `silver.tcl_vehicles_clean` | bronze.tcl_vehicles | Parse SIRI, delay_seconds, line_ref, dédup |
| `silver.velov_clean` | bronze.velov | Dédup, stations actives |
| `silver.meteo_hourly` | bronze.meteo | Dédup par measurement_time |
| `silver.chantiers_actifs` | bronze.chantiers | Filtre date_debut ≤ now ≤ date_fin |

### Gold (Features + Analytique — 3 domaines)

**Domaine Trafic** (schéma v0.3.1) :

| Table | Rôle |
|-------|------|
| `gold.traffic_features_live` | Features ML : `channel_id, computed_at, speed_kmh, vitesse_limite_kmh, lag_h1/h2/h3, delta_h1, rolling_mean_h1, sin_hour, cos_hour, sin_dow, cos_dow, temperature_2m, precipitation, is_vacances, is_ferie, lat, lon` |
| `gold.dim_spatial_grid_mapping` | Capteurs → nœuds spatiaux (H3 res.13, cell_to_local_ij). ~1520 nœuds, PK = `properties_twgid` (Sprint 8 hotfix 5 : backfill lat/lon via h3-py 4.5) |
| `gold.dim_spatial_adjacency` | Arêtes graphe (K=2 grid_disk, bidirectionnel + self-loops) — sert `gold.mv_congestion_propagation_pairs` (Axe 2) |
| `gold.fact_traffic_series` | Séries temporelles normalisées (5 canaux) |
| **`gold.trafic_predictions`** | Prédictions pré-calculées. Schéma v0.3.1 : `axis_key, horizon_h (1), calculated_at, speed_pred, etat_pred, color, vitesse_limite_kmh, label, model_version, lat, lon`. Alimentée toutes les 30 min par `dag_live_speed_retrain` (focus H+1h depuis Sprint VPS-6) |
| `gold.predictions_vs_actuals` | Backtesting pour comparaison modèles |

> **Dette schéma Sprint 5 — RÉSOLUE Sprint 8+** : `src/models/xgboost_speed.py` référençait `speed_lag_1, node_idx, hour_sin, temperature_c, rain_mm, measurement_time` qui n'existaient plus. Refacto Sprint 8+ : alignement complet sur schéma v0.3.1 avec convention focus H+1h (`lag_h1`, `rolling_mean_h1`, etc.).

**Domaine Bus** :

| Table | Rôle |
|-------|------|
| `gold.bus_delay_segments` | Retard agrégé par tronçon/ligne/heure/jour/météo/vacances |
| `gold.infrastructure_bottlenecks` | Croisement retard bus × congestion trafic → diagnostic infra (JOIN global par heure) |
| `gold.mv_bus_traffic_spatial` | **Sprint 15+ Axe 3** — JOIN spatial 0.001° bus × trafic (corrige bottleneck global). Option B : coexiste avec l'ancien |
| `gold.mv_line_kpis_live` | Vue matérialisée KPIs par ligne (155 lignes) — Sprint 7 |
| `gold.mv_otp_heatmap` | Heatmap OTP triplets (4416 lignes×date×hour) — Sprint 7 |

**Domaine Multimodal** (Sprint 15+) :

| Table | Rôle |
|-------|------|
| `gold.mv_multimodal_grid` | **Axe 1** — Grille 0.01° fusionnant trafic + TCL + Vélov + météo. Score multimodal 0-10 + diagnostic |

**Domaine Vélov** :

| Table | Rôle |
|-------|------|
| `gold.velov_features` | station_id label-encoded, temporel, météo, vacances, lags, rolling |
| `gold.velov_predictions` | H+30min, H+1h |

### Schéma OSM (Sprint 18 — pgRouting)

| Table / Vue | Rôle |
|-------------|------|
| `osm.ways` | Réseau routier OSM (~101k arêtes, importé via osm2pgrouting). Colonnes `cost` / `reverse_cost` mises à jour `*/15 min` par `refresh_traffic_costs()` |
| `osm.ways_vertices_pgr` | Nœuds du réseau routier (~87k vertices) |
| `osm.sensor_positions` | 1 159 capteurs Grand Lyon (channel_id + point GiST). Peuplé depuis `traffic_features_live` |
| `osm.mv_sensor_to_way` | Vue matérialisée : mapping capteur → arête OSM la plus proche (LATERAL KNN `<->`, seuil 200m). 41 737 arêtes couvertes |
| `osm.route_car(lon1, lat1, lon2, lat2)` | Fonction SQL : `pgr_dijkstra` dirigé, retourne chemin avec géométrie GeoJSON par arête |
| `osm.refresh_traffic_costs()` | Fonction SQL : injecte vitesses capteurs dans `cost` / `reverse_cost` des arêtes |

---

## Scheduling Airflow — Sans conflit

```
:00  Collecte bronze (boucles + AQ + chantiers)
:02  Collecte bronze (SIRI Lite + Vélov)
:05  Transform bronze → silver (5 parallèles)
:15  Transform silver → gold (3 domaines parallèles)
:20  dag_live_speed_retrain (Sprint VPS-5, focus H+1h) — train XGBoost H+1h + INSERT gold.trafic_predictions
*/30  Idem, toutes les 30 min (cf. v0.6.5 — focus H+1h)
*/5   backfill_dim_spatial_lat_lon (Sprint 8 cron, idempotent)
*/15  refresh_osm_traffic_costs (Sprint 18 — injecte vitesses capteurs dans osm.ways.cost, ~20s)
:25  Retrain XGBoost trafic (legacy, 4 horizons, ~10 min)
:50  Retrain Vélov (2 horizons : H+30min, H+1h, ~5 min)
04h  Data quality daily (6 checks) + bottleneck analysis
06h  Drift monitoring Evidently
1er du mois: refresh calendrier scolaire + jours fériés
```

---

## Sécurité — 10 règles

1. **Zéro credential dans le code**. Tout via `os.getenv()` avec validation au boot. Pas de fallback hardcodé.
2. **SQL paramétré partout**. `psycopg2 %s`. Zéro f-string SQL.
3. **MLflow avec auth** (Basic auth via Nginx).
4. **API key obligatoire** sur FastAPI. Header `X-API-Key`. Rate limiting.
5. **Réseau interne**. Ports Docker sur `127.0.0.1` sauf Nginx. Nginx reverse proxy unique.
6. **SSH key only**. Désactiver password auth. Clé `~/.ssh/lyonflow_deploy`.
7. **Pas de secrets dans git**. `.env` dans `.gitignore`. Gitleaks en CI.
8. **Containers non-root**. USER `appuser` dans Dockerfiles.
9. **RGPD**. Pas de PII dans logs. Purge auto Bronze. Page conformité dans dashboard.
10. **Fernet key Airflow** générée, pas hardcodée.

---

## Dashboard — Architecture 3 personas

**18 pages × 3 personas** (Usager, Pro TCL, Élu) + Accueil + RGPD + A_Propos. **59 widgets**.

### Composants UX transversaux (Sprint 20+)

| Fichier | Rôle |
|---------|------|
| `dashboard/components/plotly_theme.py` | `LYF_TEMPLATE` + `COLORS` dict. `apply_lyf_theme(fig)`. |
| `dashboard/components/error_display.py` | `show_error(error_type, detail)` — message adapté par persona. |
| `dashboard/components/loading_state.py` | `loading_wrapper(msg, icon)` — context manager spinner. |
| `dashboard/components/freshness_badge.py` | Badge prochaine MAJ par persona (30s/60s/300s). |
| `dashboard/components/a11y.py` | `plotly_with_alt(fig)`, `sr_only(text)` — accessibilité. |
| `dashboard/components/sparkline.py` | Sparkline 24h pour jauge santé réseau. |
| `dashboard/components/auto_refresh.py` | Auto-refresh par persona (streamlit-autorefresh). |

### Couleurs bottlenecks (carte Folium)

- **Rouge** : bus ET trafic souffrent (bottleneck infrastructure)
- **Orange** : trafic congestionné seul
- **Bleu** : pistes cyclables contournant zones rouges
- **Violet** : stations métro accessibles à pied (~500m) depuis zones rouges
- **Vert** : alternatives fonctionnelles identifiées

### Pro_4_Simulateur — Sélecteur de ligne TCL (Sprint VPS-5)

Charge **toutes les lignes TCL distinctes** depuis `gold.tcl_vehicle_realtime.line_ref` (155 lignes via `gold.mv_line_kpis_live` + 10 emblématiques via `src/data/tcl_lines.py`). Auto-catégorisation : `T*` → 🚊 tram, `M*` → 🚇 metro, reste → 🚌 bus. **Sprint 8+ : pas de mock fallback**.

### Widget KPIs par ligne — Sort + Explore (Sprint VPS-5)

Le widget `dashboard/components/widgets/pro_tcl/line_kpis.py` expose :
- **Sélecteur "Trier par"** : 10 options (OTP↑↓, Retard↑↓, Charge↑↓, Fréq↑↓, Line ID A-Z/Z-A)
- **Slider "Top N"** : 5 → 50 lignes affichées
- **Checkbox "Détails par ligne"** : déplie chaque ligne en cards 4 KPIs
- **Tableau Streamlit** avec barres de progression sur OTP et Charge
- Tri natif Streamlit (click sur les headers)

---

## Provenance des composants

| Composant | Repo source | Raison |
|-----------|-------------|--------|
| Pipeline Medallion psycopg2 | trafficlyon | Production-proven, pas de Polars dans Airflow |
| Structure DAGs | trafficlyon | Le plus mature (10 DAGs testés) |
| Dashboard 18+ pages | trafficlyon | Le plus complet |
| src/ingestion/ collecteurs | LyonFlow | Architecture la plus propre (ABC, tenacity retry) |
| src/routing/ recommandation | LyonFlow | Multimodal scoring composite |
| FastAPI endpoints | LyonFlow | Structure API avancée |
| Pathfinding H3 Dijkstra | LyonFlow | Sprint 8 hotfix 2 — graphe routier Sprint 5 |

### Supprimé / Archivé

| Composant | Raison |
|-----------|--------|
| Kafka | Jamais utilisé réellement |
| MinIO | **Réhabilité Sprint 10+** — bind mount sur sdb2, archive silver > 30j (Parquet snappy) via `dags/maintenance/silver_archive_to_minio.py` |
| 458 one-hot vélov | 9GB RAM, remplacé par label encoding |
| Orbit DLT challenger | Conflit schedule, complexité sans gain |
| AR(1) predictor fallback | Dead code |
| Ray cluster HPO | Optuna local suffit |
| **TomTom API** | Réactivé Sprint 13+ (v0.6.7). Classe `TomTomTrafficFlow(DataCollector)` wrappe `collect_lyon_tiles()` + `save_lyon_tiles_to_bronze()`. DAG `collect_tomtom_traffic` tourne */15 min sur 12 tuiles Lyon (1152 req/jour, free tier 2500). Vue `gold.v_coherence_tomtom_vs_grandlyon` (migration 14) fait le JOIN spatial PostGIS `ST_DWithin < 200 m` pour la cross-validation vs boucles inductives Grand Lyon. Détecteur automatique de capteurs HS via `gold.v_tomtom_gl_drift`. |
| **Mode démo / mocks** | **VIRÉ Sprint 8**. Politique "zéro mock" — `src/data/mock/` → `tests/fixtures/mock_data/`. Cleanup `_is_demo_mode` (7× F401) en cours Sprint 9+ |
| **snap_to_roads.py** | **VIRÉ Sprint 18**. Dead code (Overpass snap), inutile avec pgRouting. Jamais importé |
| **NetworkX A* routing** | **VIRÉ Sprint 18**. Remplacé par pgRouting `pgr_dijkstra` côté SQL. Exports retirés : `build_routing_graph`, `shortest_path`, `get_nearest_node`, `CACHE_TTL_SECONDS` |
| **13 docs stale** | **ARCHIVÉS Sprint 21**. 5 root-level + 8 docs/ → `archive/{sprints,audits,misc}/`. Convention : déplacer, jamais supprimer (RNCP). |
| **tests/ml/test_drift_detector.py** | **MERGÉ Sprint 21**. Doublon de `tests/monitoring/test_drift_detector.py` (même module, couverture inférieure). |
| **PROJECT_STATUS_AND_GOALS.md** | **ARCHIVÉ Sprint 21**. Figé Sprint 8, supplanté par CLAUDE.md. |
| **Elu_2 économie hardcodée** (`5 + i`, `2.5 - i * 0.15`, `18 + i * 3`, `6 + i * 2`) | **VIRÉ Sprint 22++** (v0.12.1). Données désormais dérivées de `gold.mv_bus_traffic_spatial` (gain = `avg_delay_s/60*0.5`, cout = `f(diagnosis)`, ROI = formule unifiée, voyageurs = `n_obs × 36`). |
| **`gold.infrastructure_bottlenecks` (JOIN global par heure)** | **VIRÉ Sprint 22++** (v0.12.1). Remplacé par `gold.mv_bus_traffic_spatial` (MV spatiale 0.001° ≈ 100 m, refresh CONCURRENTLY */15 min). |
| **Dict coords hardcodé `bottleneck_map.py`** | **VIRÉ Sprint 22++** (v0.12.1). 10 noms de rues jamais matchés (`zone` = `"L66 ; 20h"`). Remplacé par lecture `b.get("lat"/"lon")` réelles depuis la MV spatiale. |
| **ST-GRU-GNN (tandem GNN+XGBoost trafic)** | **VIRÉ Sprint 24+** (2026-06-30, code) puis nettoyage complet des mentions actives 2026-07-01. Modèle FinalProjet (`training/stgcn/`, `dags/ml/retrain_gnn.py`, `src/models/stgcn_wrapper.py`) conservé pour traçabilité RNCP dans `archive/legacy/gnn/`. XGBoost H+1h est l'unique modèle trafic en prod. `gold.dim_gnn_adjacency` renommée `gold.dim_spatial_adjacency` (toujours utilisée par Axe 2 propagation congestion, indépendante du GNN) — migration à appliquer. |
| **`docs/DASHBOARD_PAGES.md` (pages obsolètes Favoris/Files/Pro_5_Export)** | **CORRIGÉ Sprint 22++** (v0.12.1). Pages remplacées par Usager_3/4/5 (MLOps citoyen). Pro_5_Export abandonné depuis Sprint 13+ — export via Elu_5_Rapport. |

---

## Déploiement

**Cible production : VPS unique** — `51.83.159.224` (Ubuntu, 6 CPU, 12 Go RAM, 2× 100 Go SSD).
Branche `vps` = source de vérité du déploiement actif.

### Stack VPS (branche `vps`)

| Composant | Détail |
|-----------|--------|
| Reverse proxy | Nginx 1.27 (Sprint VPS-1) — DNS `lyonflow.fr` mort, accès par IP `https://51.83.159.224` |
| Process supervisor | systemd unit `lyonflow.service` (Sprint VPS-2) |
| Backup DB | systemd timer quotidien 03:00 → `scripts/backup.sh` (Sprint VPS-2) + offsite `scripts/backup-offsite.sh` |
| Rollback | `make rollback-vps` (Sprint VPS-2) |
| Monitoring | Prometheus + Alertmanager + Grafana via `docker-compose.monitoring.yml` (Sprint 8 : tous UP) |
| Exporters | node, postgres, nginx, redis (Sprint VPS-3) |
| Métriques custom | `src/api/metrics.py` — prédictions, latence, personas, DAGs, MLflow, DB (Sprint VPS-4) |
| **Pipeline trafic** | `dags/ml/dag_live_speed_retrain.py` (Sprint VPS-5) — train XGBoost H+1h + INSERT `*/30` dans `gold.trafic_predictions` |
| **Backfill lat/lon** | `dags/maintenance/backfill_dim_spatial_lat_lon.py` (Sprint 8) — `*/5min`, dérive depuis `h3_id` |
| **Healthcheck** | `scripts/healthcheck-vps.sh` (Sprint 8) — 20 checks (containers, disque, CPU/RAM, DB, endpoints) |
| Stockage DB | `/opt/lyonflow/postgres_data` (volume Docker, disque sdb) |
| Réseau | Ports internes sur 127.0.0.1 uniquement, Nginx seul exposé 80/443 |
| Secrets | `.env` chmod 600, jamais en repo |

### ⚠️ Gotchas déploiement VPS (mis à jour Sprint 18)

- **`/opt/lyonflow/logs/`** doit être `chown 50000:0` récursivement après chaque `rsync` frais. Sinon le worker Celery crash en boucle sur `PermissionError` (Sprint VPS-5).
- **DNS `lyonflow.fr` mort** (NXDOMAIN) + cert TLS Let's Encrypt expiré → accès par IP `https://51.83.159.224` (warning cert self-signed).
- **Disque sda1 à 64%** (35 Go libres) après migration Docker data-root (Sprint 9+). Plus de migration à prévoir pour le moment.
- **Cache Python .pyc** dans les containers Airflow : purger `find /opt/airflow -name __pycache__ -type d -exec rm -rf {} +` après chaque modification de `src/`. Sinon les DAGs chargent l'ancienne version (Sprint 8+ leçon apprise).
- **Mapping `dim_spatial_grid_mapping.properties_twgid`** (entiers ou strings) ≠ `traffic_features_live.channel_id` (format LYO000xx) — **Sprint 8+ : backfill via h3-py résout lat/lon mais le mapping d'identité est toujours à réconcilier**.
- **Image Docker PostgreSQL changée Sprint 18** : `pgrouting/pgrouting:16-3.5-3.7.3` (était `postgis/postgis:16-3.4`). PostGIS 3.4 → 3.5 upgrade est backward-compatible (PGDATA inchangé), mais nécessite `ALTER EXTENSION postgis UPDATE` au premier démarrage. **NE PAS revenir à l'image postgis/postgis** — pgRouting serait perdu.
- **mv_sensor_to_way vide = routing sans trafic réel** : si la vue matérialisée est vide, `refresh_traffic_costs()` ne met rien à jour → toutes les arêtes gardent `cost_default` (maxspeed OSM fixe). Vérifier : `SELECT COUNT(*) FROM osm.mv_sensor_to_way;` doit retourner ~41k.

### Commandes déploiement VPS

```bash
make check-deploy-env       # vérifie .deploy.env (chmod 600 + vars critiques)
make deploy-vps             # rsync + restart systemd
./scripts/healthcheck-vps.sh  # 20 checks (Sprint 8+)
make rollback-vps           # rollback dernière release
make monitoring-up          # stack Prometheus/Grafana/Alertmanager
make tls-status             # statut cert Let's Encrypt
```

### Branches dormantes (futur AWS/GCP, NE PAS MERGER)

- `kubernetes` — Phase K8s complète (Kustomize + monitoring). Cible : EKS / GKE futur.
- `cloud-demo` — Phase démo Jedha (Scaleway Kapsule éphémère). Cible : POC cloud public ponctuel.

---

## Structure cible

```
lyonflow/
├── CLAUDE.md
├── AGENTS.md
├── README.md
├── CHANGELOG.md
├── .env.example
├── .deploy.env
├── .gitignore
├── docker-compose.yml
├── docker-compose.monitoring.yml
├── Dockerfile
├── pyproject.toml
├── dags/
│   ├── bronze/             # 3 DAGs (collect_bronze, collect_calendriers_monthly, collect_tomtom_traffic no-op)
│   ├── transforms/         # 2 DAGs (transform_bronze_to_silver, transform_silver_to_gold, build_spatial_mapping)
│   ├── ml/                 # 2 DAGs (dag_live_speed_retrain, retrain_xgboost, retrain_gnn)
│   ├── maintenance/        # 3 DAGs (maintenance.py, backfill_dim_spatial_lat_lon, refresh_lieux_calendrier)
│   └── legacy_github/      # BLOQUÉ par .airflowignore (Sprint 8 audit writers)
├── src/
│   ├── config.py
│   ├── data/
│   │   ├── data_loader.py      # fail loud via DashboardDataError
│   │   ├── db_query.py         # helpers SQL, fallbacks mock virés
│   │   ├── airflow_client.py   # fail loud via DashboardDataError
│   │   ├── exceptions.py       # DashboardDataError
│   │   ├── labels.py           # NOUVEAU Sprint 8 : référentiels statiques
│   │   └── tcl_lines.py        # NOUVEAU Sprint 8 : 10 lignes TCL emblématiques
│   ├── ingestion/          # 8 collecteurs (DataCollector ABC)
│   ├── transformation/     # feature engineering
│   ├── models/             # XGBoost H+1h focus, delay predictor
│   ├── routing/            # pathfinder_multimodal (Vélov smart + voiture Dijkstra)
│   ├── monitoring/         # Evidently, drift
│   └── api/                # FastAPI endpoints
├── scripts/
│   ├── sql/                # 20+ migrations (referentiel, vues matérialisées, audit)
│   ├── maintenance/        # backfill scripts
│   └── healthcheck-vps.sh  # NOUVEAU Sprint 8
├── dashboard/              # 18 pages × 3 personas (5 Usager + 6 Pro TCL + 5 Élu + Accueil + RGPD + A_Propos)
├── tests/
│   ├── conftest.py             # NOUVEAU Sprint 8 : MockDB + 3 fixtures
│   ├── data/                   # tests unitaires data_loader/db_query
│   ├── ml/                     # tests modèles
│   ├── persona/                # tests widgets
│   ├── integration/            # tests intégration (skippés par défaut)
│   ├── e2e/                    # tests e2e (skippés)
│   └── fixtures/mock_data/     # NOUVEAU Sprint 8 : mocks déplacés ici
├── docs/
│   ├── ADR/                # 4 ADRs (architecture, personas, docker, psycopg2)
│   ├── RCA/                # Root Cause Analysis (post-mortems incidents)
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── DATA_GOVERNANCE.md
│   ├── DEPLOYMENT.md
│   ├── DASHBOARD_PAGES.md
│   ├── MONITORING.md
│   ├── VPS_HARDENING.md
│   ├── RUNBOOK.md
│   ├── REPO_STRUCTURE.md
│   ├── GIT_STRUCTURE.md
│   ├── CONTROLE_VPS_VS_CLOUD_DEMO.md
│   ├── POSTGRES_DATABASE_REFERENCE.md   # référentiel DB introspecté (live)
│   ├── POSTGRES_TUNING_PROD.md          # tuning Postgres, statut appliqué
│   ├── AUDIT_AIRFLOW_POSTGRES_SPRINT24.md  # actionable, plan D partiel
│   └── SPEC_OPTIMISATION_INTERDEPENDANCES.md  # actionable : axes 2/4/6/7 restants
├── SPRINT_*.md             # rapports de sprint (archivés — voir archive/sprints/)
└── kubernetes/             # Phase 3 dormante
```

---

## Variables d'environnement

| Variable | Obligatoire | Usage |
|----------|-------------|-------|
| `POSTGRES_USER` | oui | DB user |
| `POSTGRES_PASSWORD` | oui | DB password |
| `POSTGRES_HOST` | oui | DB host |
| `POSTGRES_DB` | oui | DB name |
| `MLFLOW_TRACKING_URI` | oui | MLflow server |
| `LYONFLOW_API_KEY` | oui | FastAPI auth |
| `AIRFLOW_FERNET_KEY` | oui | Chiffrement Airflow |
| `LYONFLOW_DEMO_MODE` | oui (Sprint 8) | **Doit être `0` en prod** (helper retourne toujours False) |
| `LYON_DEFAULT_SPEED` | non (30.0) | Vitesse imputation fallback |
| `LYON_LATITUDE` | non (45.7640) | Latitude centre Lyon (collecteurs Open-Meteo, chantiers) |
| `LYON_LONGITUDE` | non (4.8357) | Longitude centre Lyon |
| `TOMTOM_API_KEY` | non (mais recommandé) | TomTom free tier (2500 req/jour). Sprint 13+ : ingestion active si clé configurée, no-op gracieux sinon (log warning, 0 rows). |

---

## Commandes

```bash
# Lint
ruff check . --output-format=github
ruff format --check .

# Type check (Sprint 15+ v0.7.1 : mypy clean, plus de --ignore-missing-imports CLI)
# La config vit dans pyproject.toml [tool.mypy] + explicit_package_bases = true.
mypy dags/ src/

# Tests (Sprint 8+ : addopts inclut "-m not integration")
pytest tests/ -v --tb=short
pytest tests/ -m integration  # pour les tests qui ont besoin du stack

# Healthcheck VPS (Sprint 8+)
./scripts/healthcheck-vps.sh

# Stack complète
docker-compose up -d --build
docker compose -f docker-compose.monitoring.yml up -d  # monitoring
```
