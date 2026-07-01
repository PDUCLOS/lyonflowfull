# Audit de certification RNCP 38777 — LyonFlow

> **Date** : 2026-07-01
> **Auteur** : Patrice DUCLOS (assisté Claude Code)
> **Objet** : État vérifié de la plateforme MLOps LyonFlow en vue de la certification
> RNCP 38777 (Architecte en IA). Ce document synthétise les vérifications et
> corrections effectuées le jour même — architecture, DB, pipelines, ML, tests.
>
> **Méthode** : toutes les métriques ci-dessous sont issues de requêtes live sur
> le VPS de production (`51.83.159.224`) ou de l'exécution de la suite de tests
> locale, pas de valeurs déclaratives.

---

## 1. Synthèse exécutive

| Domaine | Statut | Détail |
|---|---|---|
| Tests | ✅ | 600 passés, 1 skip (DB indispo en local), 0 échec |
| Lint | ✅ | `ruff check .` — 0 erreur |
| Containers VPS | ✅ | 10/10 healthy |
| DAGs Airflow | ✅ | 25/27 actifs, 2 pausés intentionnellement (documentés §4) |
| Pipeline trafic (XGBoost) | ✅ | Entraînement + inférence + persistance vérifiés bout-en-bout |
| Pipeline Vélov (XGBoost) | ✅ | **Corrigé aujourd'hui** — aucune prédiction n'était jamais persistée |
| MLflow Model Registry | ✅ | **Corrigé aujourd'hui** — 6 modèles versionnés, stage Production |
| Drift monitoring (Evidently) | ✅ | **Réactivé aujourd'hui** — mort depuis 25 jours |
| Bloat DB | ✅ | 2 tables critiques VACUUM FULL (osm.ways 1.4GB→39MB, meteo_hourly) |
| Disque VPS | ✅ | sda1 67% (33G libres), sdb 66% (33G libres) |
| Qualité données (lat/lon) | ✅ | **Corrigé aujourd'hui** — 1543 lignes NULL → 0 |
| Sparkline santé réseau (Élu) | ✅ | **Corrigé aujourd'hui** — table vide depuis toujours (bug code) |

---

## 2. Architecture (rappel)

Plateforme MLOps end-to-end — prédiction et analyse du trafic multimodal,
Métropole de Lyon. Architecture medallion (Bronze/Silver/Gold) sur PostgreSQL 16
+ PostGIS 3.5 + pgRouting 3.7.3, orchestrée par Airflow 2.9, trackée par MLflow 2.15,
servie par Streamlit (dashboard 18 pages × 3 personas, 59 widgets) + FastAPI (9
endpoints).

- **27 DAGs Airflow** (25 actifs)
- **~280 fichiers Python**, ~25 000 lignes
- **600 tests** (unitaires + widgets), ratio test/code ≈ 0,6
- **1 modèle ML trafic** (XGBoost H+1h, focus fiabilité VPS) + **1 modèle Vélov**
  (XGBoost H+1h) — le tandem GNN historique (ST-GRU-GNN) a été archivé
  (`archive/legacy/gnn/`) et ses dernières traces actives nettoyées le jour même
  (voir §5.1)

---

## 3. Corrections appliquées aujourd'hui (2026-07-01)

### 3.1 Purge GNN du code actif

Le tandem GNN était déjà archivé (Sprint 24+, 2026-06-30) mais des traces
fonctionnelles subsistaient : fonctions mortes (`build_routing_graph`,
`get_node_speed`), package `training/` vide, 6 champs de config hyperparamètres
morts, wording utilisateur (dashboard) mentionnant encore GNN. Nettoyage complet
— voir `CLAUDE.md` §"État au 2026-07-01" pour le détail fichier par fichier.

**Piège évité** : `gold.dim_gnn_adjacency` semblait être un reliquat GNN mais
alimente en réalité `gold.mv_congestion_propagation_pairs` (Axe 2, propagation
de congestion) — table renommée `gold.dim_spatial_adjacency` (migration_040)
plutôt que supprimée. Zéro perte de fonctionnalité.

### 3.2 Bugs production trouvés et corrigés

| Bug | Symptôme | Cause racine | Fix |
|---|---|---|---|
| Crash carte trafic | `TypeError: Expected numeric dtype` | Colonnes NUMERIC psycopg2 (Decimal) non coercées avant `.round()` | Helper `_coerce_numeric_columns` |
| Crash pages Usager 3/5 | `ImportError: cached_predictions_vs_actuals` | Fonction jamais implémentée après l'archivage GNN d'une table dont elle dépendait | Fonction ajoutée, lit `gold.trafic_predictions` |
| Badge "XGB H+60min dispo" toujours ❌ | Faux négatif permanent | Check fichier local (`.json`) sur un container sans volume modèles monté, extension réelle `.pkl` de toute façon | Check fraîcheur DB à la place |
| **Prédictions trafic timestampées +2h dans le futur** | `calculated_at` > `now()` de ~2h | `datetime.now()` naïf (heure locale CEST) au lieu de `datetime.now(UTC)` | `dag_inference_xgboost.py` corrigé |
| **0 prédiction Vélov jamais persistée** | `gold.velov_predictions` vide depuis toujours | Aucun DAG d'inférence n'existait — seul l'entraînement tournait | **Nouveau DAG** `dag_inference_velov.py` créé |
| MLflow Model Registry "vide" vu du dashboard | `list_registered_models()` retournait `[]` | Client `mlflow` 3.14.0 (dashboard/API) incompatible avec serveur 2.12.1 (2.x) | `mlflow<2.16` + `setuptools<81` épinglés, images rebuild |
| Sparkline santé réseau vide | `gold.network_health_history` 0 ligne depuis toujours | `execute_query(fetch=True)` — kwarg inexistant, DAG en échec silencieux permanent | Kwarg retiré |
| 1543 capteurs sans lat/lon | Carte GNN historique (dead) incomplète | DAG de backfill jamais exécuté (paused depuis 2026-06-12) | DAG réactivé, backfill exécuté (0 NULL restant) |
| `build_spatial_mapping` en échec 8 jours consécutifs | Timeout Airflow après 24h+ de blocage | Requête sans borne temporelle (10,2M lignes scannées) + ~30 000 connexions Postgres individuelles par run | Requête bornée 24h (cost -80%, 17.7s vs >8min) + connexion unique réutilisée |

### 3.3 Root cause structurelle : incidents I/O récurrents

3 incidents distincts observés dans la journée (`refresh_traffic_costs` et
`mv_sensor_saturation` bloqués 20-45 min en boucle). Root cause confirmée :
`execution_timeout` Airflow tue le worker Python mais **pas** la requête
Postgres sous-jacente (I/O bloquant insensible à l'annulation côté client) →
pileup de sessions zombies. Fix : `statement_timeout` ajouté aux connexions
psycopg2 de 3 DAGs (`refresh_osm_traffic_costs`, `refresh_sensor_saturation`,
`build_spatial_mapping`).

**Root cause de fond** (mitigée mais pas éliminée) : thundering herd `:00`/`:30`
— jusqu'à 10 DAGs se déclenchant simultanément sur une base à ressources
limitées. 5 DAGs re-décalés (`refresh_osm_traffic_costs` → 3,18,33,48 ;
`refresh_velov_transit_coupling` → 12,27,42,57 ; `refresh_congestion_propagation`
→ 10,40 ; `refresh_xgb_vs_tomtom` → 5,35 ; `refresh_heavy_mv` → 15,45).

### 3.4 Maintenance base de données

| Action | Avant | Après |
|---|---|---|
| Mémoire container Postgres | 2,5 Go | **4 Go** (aligné sur le tuning interne déjà appliqué : `shared_buffers=1GB`) |
| `VACUUM FULL osm.ways` | 1,4 Go, 3,8M tuples morts (36×) | **39 Mo, 0 mort** |
| `VACUUM FULL silver.meteo_hourly` | 718% bloat | **0 mort** |
| `ANALYZE` global | Stats obsolètes (recréation container) | Stats à jour |

---

## 4. DAGs — état final (25/27 actifs)

### Pausés intentionnellement (2)

| DAG | Raison |
|---|---|
| `retrain_xgboost_speed` | Redondant avec `dag_daily_speed_train` (1×/jour) — la source (`gold.xgb_training_set`) ne change qu'une fois par jour ; un retrain horaire produisait 24 runs MLflow bit-identiques par jour |
| `refresh_heavy_mv` | Contient le writer legacy `infrastructure_bottlenecks` (remplacé par `gold.mv_bus_traffic_spatial`, Sprint 22++) — désactivation = étape 1/5 d'un plan de retrait propre (item C2, `docs/AUDIT_AIRFLOW_POSTGRES_SPRINT24.md`). `gold.mv_bus_traffic_spatial` reste alimentée par un autre chemin, aucun impact utilisateur constaté |

### Réactivés/corrigés aujourd'hui (5)

`maintenance_backfill_dim_spatial_lat_lon`, `maintenance_record_network_health`,
`silver_archive_to_minio`, `refresh_xgb_vs_tomtom`, `daily_drift_report`.

---

## 5. Pipeline ML — vérification bout-en-bout

### 5.1 Trafic (XGBoost H+1h)

- Entraînement quotidien (`dag_daily_speed_train`, 03h00) sur `gold.xgb_training_set`
  (matérialisée quotidiennement).
- Inférence */15min (`dag_inference_xgboost`) → `gold.trafic_predictions`,
  fraîcheur vérifiée < 3 min.
- Tracking MLflow : run réels, métriques cohérentes (MAE ≈ 2.12 km/h).

### 5.2 Vélov (XGBoost H+1h)

- Entraînement horaire (`retrain_xgboost_velov`) — fonctionnait déjà.
- **Inférence** : n'existait pas avant aujourd'hui. Nouveau DAG
  `dag_inference_velov.py` (miroir du pipeline trafic) → `gold.velov_predictions`,
  **454 lignes produites au premier cycle**, fraîcheur < 3 min vérifiée en continu.

### 5.3 MLflow Model Registry

6 modèles enregistrés, tous en stage `Production`, versions à jour (jusqu'à
v317 pour `xgboost_speed_h60`) : `xgboost_speed_h5/h60/h180/h360`,
`xgb_velov_h30/h60`. Visible depuis tous les containers (dashboard, API,
Airflow) après correction de la dérive de version du client `mlflow`.

### 5.4 Drift monitoring (Evidently)

`daily_drift_report` (05h30 quotidien) réactivé — comparait `gold.mv_xgb_vs_tomtom`
(J-7→J-1 vs 24h). Était mort depuis le 2026-06-06 (25 jours), dépendance
(`refresh_xgb_vs_tomtom`) elle-même pausée. Les deux réactivés, premier cycle
confirmé en succès.

---

## 6. Base de données — état détaillé

**Taille totale** : 48 Go · **7 schémas** applicatifs (bronze/silver/gold/osm/
referentiel/archive/public) · **150+ tables/vues**.

| Schéma | Tables | Taille |
|---|---|---|
| silver | 6 | 37 Go |
| bronze | 17 | 6 Go |
| gold | 41 | 4,6 Go |
| archive | 4 | 164 Mo |
| osm | 6 | 58 Mo (post-VACUUM, était ~1,5 Go) |
| public | 19 | 11 Mo |
| referentiel | 3 | 288 Ko |

**Item connu non résolu** : `silver.trafic_vitesse_propre` (29 Go, table legacy)
— DAG d'archivage MinIO réactivé aujourd'hui, tournera automatiquement ce soir
(04h00, ~2h d'exécution prévue, Parquet snappy + purge).

---

## 7. Sécurité (rappel, non modifié aujourd'hui)

- Zéro credential en dur dans le code (`os.getenv()` partout).
- SQL 100% paramétré (`psycopg2 %s`).
- Secrets `.env` chmod 600, hors git.
- Containers non-root (`USER appuser`).

---

## 8. Ce qui reste ouvert (non-bloquant pour la certification)

| Item | Statut | Impact |
|---|---|---|
| `infrastructure_bottlenecks` — retrait complet (C2 étapes 3-5) | ⏸ Reporté | Cosmétique / dette technique, aucun bug utilisateur |
| `silver.trafic_vitesse_propre` archivage | 🔄 Lancé, tournera cette nuit | Libérera ~25 Go à terme |
| `rclone` backup offsite (destination OAuth) | 🔴 Pending | Backup local fonctionne, offsite pas configuré |
| Rien commité sur git | — | Décision utilisateur en attente |

---

## 9. Conclusion

Tous les composants vérifiés en direct sur le VPS de production sont
**fonctionnels et cohérents** : pipelines de données, entraînement et inférence
ML (trafic + Vélov), tracking/registry MLflow, monitoring de drift, dashboard
18 pages. Les 9 bugs listés en §3.2 étaient tous **réels et actifs avant
aujourd'hui** (vérifiés par logs, requêtes SQL live, et tests avant/après) —
aucun n'est une régression introduite par les corrections elles-mêmes.

Suite de tests : **600/600 verts**. Aucune erreur d'import Airflow. Aucun
container en échec.
