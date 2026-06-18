# Changelog

Toutes les modifications notables de ce projet sont documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [0.6.7] - 2026-06-18 — Sprint 13+ : TomTom Niveau 1 réactivé + cross-validation (branche `vps`)

Réactive TomTom Traffic Flow comme **deuxième source indépendante de vitesse
routière** (vs boucles inductives Grand Lyon) et livre le premier niveau de
validation croisée : ingestion Bronze stable + vue SQL de cohérence spatiale +
widget Pro_TCL "Cohérence sources vitesse" avec détecteur de capteurs HS.

### Ajouté
- **Classe `TomTomTrafficFlow(DataCollector)`** dans `src/ingestion/tomtom_traffic.py`.
  Wrapper conforme au pattern des 7 autres collecteurs (Sprint 8 fix no-op).
- **DAG `collect_tomtom_traffic` RÉACTIVÉ** (`dags/bronze/collect_tomtom_traffic.py`) :
  passe du no-op au vrai `TomTomTrafficFlow().run()` via PythonOperator, `*/15 min`,
  `retries=0`. Quota free tier 2500 req/jour largement respecté (1152 req/jour).
- **Migration SQL 14** `scripts/sql/migration_14_gold_coherence_tomtom_v2.sql` :
  - Vue `gold.v_coherence_tomtom_vs_grandlyon` — JOIN spatial PostGIS `ST_DWithin`
    TomTom ↔ capteurs `gold.channels_ref` < 200 m. Calcule `delta_kmh`,
    `ratio_diff`, `status` (ok|minor_drift|drift|no_data).
  - Vue `gold.v_tomtom_gl_drift` — capteurs avec ≥ 60% drift sur 24h
    (= candidats "capteur HS" à investiguer côté Grand Lyon).
- **Helpers DB** : `get_tomtom_coherence()` + `get_tomtom_gl_drift()`
  dans `src/data/db_query.py` ; wrappers `load_tomtom_coherence()` +
  `load_tomtom_gl_drift()` dans `src/data/data_loader.py` (fail loud
  via `DashboardDataError` — politique zéro mock Sprint 8).
- **Widget Pro_TCL `coherence_scatter.py`** :
  - 4 KPI cards par status (ok / minor_drift / drift / no_data)
  - Scatter Plotly TomTom_speed vs GL_speed (ligne y=x en pointillés)
  - Top 20 pires deltas (barres horizontales)
  - Tableau des capteurs GL suspectés HS (depuis `v_tomtom_gl_drift`)
- **Cache Streamlit** : `cached_tomtom_coherence` (TTL 30s) +
  `cached_tomtom_gl_drift` (TTL 60s) dans `dashboard/components/data_cache.py`.
- **Câblage page** : section "Cohérence TomTom × Grand Lyon" ajoutée à
  `dashboard/pages/Pro_3_Correlation.py` (sous la matrice bus × trafic).

### Changed
- `src/ingestion/__init__.py` : TomTom décommenté + ajouté à `REALTIME_COLLECTORS`
  (cohérent avec les 7 autres collecteurs Bronze temps réel).
- `src/data/db_query.py` : 3 nouveaux helpers SQL (sprint 13+) — pas de
  changement sur les helpers existants.

### Fixed
- **Dette Sprint 8** : DAG `collect_tomtom_traffic` sort du no-op
  ("le module n'a jamais eu de classe DataCollector conforme" — résolu).

**Tests** : 218 verts (+15 nouveaux), 10 skipped, 7 deselected. Ruff clean.

## [0.6.6] - 2026-06-18 — Sprint 13 : audit cohérence pipeline + UX (branche `vps`)

Audit complet de cohérence du dashboard (18 pages × 3 personas). Élimine le
drift de version, ajoute l'auto-refresh par persona, et finit le nettoyage
`force_mock` / `_is_demo_mode` dans la couche data.

### Ajouté
- **Auto-refresh par persona** : `dashboard/components/auto_refresh.py` utilise
  `streamlit-autorefresh`. Intervalles : Pro TCL 30s, Usager 60s, Élu 300s —
  lus depuis `config/personas.yaml`. Câblé dans les **18 pages**.
- **`dashboard/components/widgets/common/__init__.py`** : couche de re-export
  cross-persona. `render_traffic_map_compact` partagé entre Usager et Élu sans
  dépendance directe à `widgets/pro_tcl/`.
- **`scripts/coherence-check.sh`** : 12 checks automatisés (version unique,
  zéro mock, auto-refresh, cross-persona, TTL cohérence). Target `make coherence-check`.
- **Dépendance `streamlit-autorefresh>=1.0.0`** dans `requirements.txt`.
- **5 tests** ajoutés (`test_deprecated_functions_removed` + nettoyage fixtures).

### Changed
- **Version unique** : `src/config.py` → `0.6.6`. Sidebar (`navigation.py`),
  `A_Propos.py`, `9_RGPD_Conformite.py`, `Usager_1_Mon_Trajet.py` importent
  tous `get_settings().app_version`. Zéro version hardcodée dans le dashboard.
- **`src/data/data_loader.py`** : suppression complète de `_is_demo_mode()`,
  `_maybe_force_mock()`, `_demo_mode_cache`. Param `force_mock` retiré de ~29
  signatures + appels internes.
- **`dashboard/components/data_cache.py`** : `force_mock` retiré de 24
  fonctions wrapper + appels `dl.load_*()`.
- **5 widgets** : commentaires historiques "mock" nettoyés (itinerary, velov_trip,
  model_monitoring, correlation_matrix, pipeline_management).
- **`Pro_7_Model_Monitoring.py`** : docstring "fallback mock" → "fail loud".
- **`Usager_4_Files.py`** : docstring "page interne" nettoyée.

### Removed
- `_is_demo_mode()`, `_maybe_force_mock()`, `_demo_mode_cache` (dead code depuis Sprint 8)
- `force_mock` param de ~60 signatures dans `data_loader.py` + `data_cache.py`
- Toute version hardcodée (v0.3.0, v0.6.1, v0.6.5) dans le dashboard

**Tests** : 203 verts, 4 skipped, 7 deselected, 0 régression. Ruff clean (6 cosmétiques pré-existantes).

## [0.6.5] - 2026-06-17 — Nettoyage final audits Pro TCL + Usager (branche `vps`)

Complète les 30 items des trackers
[archive/audits/AUDIT_PRO_TCL_FIXES.md](archive/audits/AUDIT_PRO_TCL_FIXES.md)
(14 items) et [archive/audits/AUDIT_USAGER_FIXES.md](archive/audits/AUDIT_USAGER_FIXES.md)
(16 items). La majorité des corrections avait déjà été livrée dans les
Sprints 8+ à 11+ — cette release finit le ménage.

### Changed
- **`dashboard/components/widgets/pro_tcl/model_monitoring.py`** :
  nettoyage des 3 dernières mentions "fallback mock (mode démo)" /
  "(MLflow ou mock)" dans les docstrings + bandeau d'avertissement MLflow
  (UX : "MLflow non accessible — aucun modèle à afficher" au lieu de
  "affichage fallback mock (mode démo)").
- **`dashboard/components/widgets/usager/weather_widget.py`** :
  refacto `_weather_icon()` → utilise une constante `_LABEL_TO_EMOJI`
  au niveau module (au lieu d'un dict reconstruit à chaque appel).
- **`dashboard/pages/Elu_1_Synthese.py:68`** + **`Elu_5_Rapport.py:56`** :
  mise à jour des commentaires "fallback mock auto via data_loader" →
  "fail loud si DB indispo" (Sprint 8 — déjà effectif, juste le
  commentaire qui datait).

### Removed
- **`force_mock=False` removed from 26 dashboard files** : tous les
  appels `cached_*(force_mock=False)` nettoyés. Le param reste dans
  les signatures `cached_*()` de `dashboard/components/data_cache.py`
  pour rétro-compat (mais n'est plus jamais passé en argument).
  Économie : 35 lignes de bruit de code, lecture plus claire.

### Documentation
- Les **2 trackers d'audit** dans `archive/audits/` (snapshot du
  2026-06-17) restent intacts pour traçabilité RNCP 38777. Cette
  release ferme **100% des 30 items** listés (cf. résumé ci-dessous).

### Résumé trackers
| Tracker | Items | Statut |
|---------|-------|--------|
| `AUDIT_PRO_TCL_FIXES.md` | 14 | ✅ 100% résolus (Sprints 8+ à 11+ + cette release) |
| `AUDIT_USAGER_FIXES.md` | 16 | ✅ 100% résolus (Sprints 8+ à 11+ + cette release) |

**Tests** : 198 verts, 0 régression. Ruff clean sur les fichiers touchés.

## [0.6.4] - 2026-06-17 — Sprint 11+ : libellés TCL lisibles + reorg docs (branche `vps`)

Voir [archive/sprints/SPRINT_11_REPORT.md](archive/sprints/SPRINT_11_REPORT.md)
pour le détail complet.

### Ajouté
- **`src/data/db_query.clean_line_label()`** : helper qui convertit un
  `line_ref` brut SIRI Lite (`"ActIV:Line::66:SYTRAL_h20"`) en libellé
  lisible pour le dashboard (`"L66 ; 20h"`). Conserve tels quels les
  identifiants déjà lisibles (`T1`, `M_A`, `C3`, ...). 30 tests unitaires
  couvrent les 5 cas (format ActIV, déjà lisibles, vide/None, whitespace,
  non-string, format inconnu).
- **Colonnes `line_label` / `road_label`** sur les DataFrames de
  `get_bottlenecks_summary`, `get_line_kpis`, `get_otp_heatmap` — les
  widgets Pro TCL affichent désormais `"L66"` au lieu de
  `"ActIV:Line::66:SYTRAL"`.
- **`tests/data/test_clean_line_label.py`** (30 tests) : couverture
  exhaustive du helper + cas limites (None, vide, type non-string,
  format inconnu, whitespace).

### Changed
- **`dashboard/components/widgets/pro_tcl/line_kpis.py`** : affichage
  par `line_label` (`"L66"`) au lieu de `line_id` brut
  (`"ActIV:Line::66:SYTRAL"`). Le `line_id` reste la clé interne pour
  le tri technique si besoin.
- **`dashboard/components/widgets/pro_tcl/otp_heatmap.py`** : axe Y de
  la heatmap affiche les libellés lisibles. Le `line_id` brut reste la
  clé interne du dict pour l'agrégation par date.
- **`dashboard/Accueil.py`** : caption refactor — virer toute mention
  "mode démo" (politique zéro mock depuis Sprint 8). Distingue
  explicitement **LIVE (DB PostgreSQL Gold)** vs **RÉFÉRENCE (Grand Lyon
  Open Data)** vs **CAPACITÉ ML** dans le footer stats.
- **`src/data/data_loader.load_bottlenecks_top()`** : utilise
  `line_label` et `road_label` (calculés par `get_bottlenecks_summary`)
  au lieu de mocks hardcodés `["C3", "C13"]`.

### Fixed
- **`src/transformation/bronze_to_silver._transform_tcl_vehicles()`** :
  `LIMIT 5000 → 200` dans le SELECT bronze (OOM-kill du worker Airflow
  sur 5000 SIRI JSON ≈ 2.5 Go en mémoire Python). 200 couvre largement
  la fenêtre roulante 15-min et libère 5+ Go de RAM dans le worker.
- **Idem sur `_transform_velov()`** : `LIMIT 5000 → 200` par cohérence
  (même profil de risque OOM).

### Removed
- **`dashboard/pages/9_RGPD_Conformite.py`** : suppression du bloc
  "Activité RGPD" (registre Article 30) et du "Contact DPO" placeholder
  (`dpo@lyonflowfull.fr`). Le schéma `rgpd.audit_log` n'est pas peuplé
  en prod — à recâbler quand l'implémentation sera complète.

### Documentation
- **Reorg complète** : tous les rapports de sprint (`SPRINT_*.md`), audits
  (`AUDIT_*.md`), analyses des 3 repos sources (`analysis_*.md`),
  `B4_CANCELLED.md` et `etude_marche_ui.md` sont déplacés sous
  `archive/{sprints,audits,analysis,misc}/`. `archive/README.md`
  documente la nouvelle structure et la convention (déplacer, jamais
  supprimer, traçabilité RNCP 38777).
- **Toutes les références** dans `CLAUDE.md`, `AGENTS.md`, `README.md`,
  `CHANGELOG.md`, `docs/PLAN_NO_MOCK_VPS.md`, `docs/REPO_STRUCTURE.md`,
  `docs/RUNBOOK.md` sont mises à jour vers les chemins `archive/...`.

## [0.6.3] - 2026-06-11 — Focus H+1h + Nginx healthcheck fix (branche `vps`)

Voir [archive/sprints/SPRINT_VPS-6_REPORT.md](archive/sprints/SPRINT_VPS-6_REPORT.md) pour le détail.

### Changed
- **`dags/ml/dag_live_speed_retrain.py`** : `HORIZON_MAP` réduit à `{60: 1}`
  (focus **H+1h stable** uniquement, suppression H+0/3/6). Schedule `:20 hourly`
  → **`*/30 * * * *`** (toutes les 30 min, fenêtre d'usage idéale pour H+1h).
- **`docker-compose.yml`** : healthcheck Nginx `http://localhost/nginx-health`
  → `http://127.0.0.1/nginx-health` (fix `::1` IPv6 connection refused).

### Database cleanup
- **`gold.trafic_predictions`** : `DELETE 232 284` rows (horizons 0/3/6). Reste
  **77 514** rows `horizon_h=1` uniquement, fraîche à <5 min.

### Fixed
- **Nginx Docker healthcheck** : échouait 2654 fois consécutives (~22h) car
  Alpine `wget localhost` résout en IPv6 `::1` et Nginx n'écoute qu'en IPv4.
  Fix = forcer IPv4 dans le healthcheck. `Status=healthy, FailStreak=0` depuis
  11:28 UTC+2.

## [0.6.2] - 2026-06-10 — Réparation 3 chaînes bronze→silver→gold silencieusement cassées

Voir [archive/sprints/SPRINT_VPS-5_REPORT.md](archive/sprints/SPRINT_VPS-5_REPORT.md) pour le détail complet.

### Ajouté
- **DAG `dags/ml/dag_live_speed_retrain.py`** : train 4 XGBoost speed (5min/1h/3h/6h)
  + INSERT hourly dans `gold.trafic_predictions` (schéma v0.3.1).
  Schedule `:20` hourly. Stratégie = **baseline** (dernière vitesse observée
  par channel_id, propagée sur 4 horizons), car le vrai modèle XGBoost a un
  drift de schéma à fixer en Sprint 9+ (voir "Dette technique").
- **Widget KPIs par ligne** (`dashboard/components/widgets/pro_tcl/line_kpis.py`)
  : sélecteur de tri (10 options : OTP/Retard/Charge/Fréq/LineID ↑↓), slider
  Top N (5→50), checkbox "Détails par ligne" avec cards dépliables, tableau
  Streamlit avec barres de progression OTP/Charge.
- **Pro_4_Simulateur** : `load_tcl_lines()` charge **166 lignes TCL distinctes**
  depuis `gold.tcl_vehicle_realtime.line_ref` (9 trams T1..T7/TB11/TB12 +
  157 bus). Auto-catégorisation `T*=tram, M*=metro, reste=bus`. Mock fallback.

### Corrige
- **Pipeline trafic reconnecté** : `gold.trafic_predictions` n'était plus
  alimentée depuis 2026-06-06 (4 jours de trou). Cause : aucun DAG ne
  persistait les prédictions après le refactor v0.3.1.
- **`src/data/db_query.get_traffic_predictions()`** réécrit pour le nouveau
  schéma v0.3.1 (mapping horizon_minutes → horizon_h, colonnes `axis_key,
  horizon_h, calculated_at, speed_pred, etat_pred`).
- **`src/data/db_query.get_traffic_bottlenecks()`** : `node_idx/measurement_time`
  → `channel_id/computed_at` (colonnes inexistantes en v0.3.1).
- **`src/monitoring/health_checks.py.check_predictions_presentes()`** :
  `prediction_timestamp` → `calculated_at`.
- **`dashboard/components/widgets/pro_tcl/model_monitoring.py`** : idem dans
  la liste data-quality tables.
- **`src/data/data_loader.py.load_traffic()`** : utilise la nouvelle signature
  `get_traffic_predictions(horizon_minutes=...)` et colonnes `speed_pred`.
- **Bug permissions `logs/`** : `chown -R 50000:0 /opt/lyonflow/logs` après
  chaque rsync (sinon le worker Celery crash silencieusement et les tasks
  restent en `queued`). Fix durable TODO = entrypoint Dockerfile.
- **Bug air UI "DAGs visibles"** : `airflow dags reserialize` + `rm -rf __pycache__`
  quand un nouveau DAG n'apparaît pas après rsync.

### Dette technique (Sprint 9+)
- **`src/models/xgboost_speed.py` + `xgboost_velov.py`** : 9+ colonnes
  référencées n'existent plus dans `gold.traffic_features_live` v0.3.1
  (`speed_lag_1, node_idx, hour_sin, temperature_c, rain_mm, measurement_time`
  → `lag_1, delta_1, sin_hour, temperature_2m, precipitation, computed_at`).
  Le `train_one()` échoue → le baseline prend le relais dans `dag_live_speed_retrain`.
- **Mapping `dim_spatial_grid_mapping.properties_twgid` (entiers)** ≠
  **`traffic_features_live.channel_id` (format LYO00xxx)** : pas de JOIN possible
  → `lat/lon` écrits NULL dans `gold.trafic_predictions`. Réconcilier en Sprint 9+.

## [0.6.2] - 2026-06-10 — Réparation 3 chaînes bronze→silver→gold silencieusement cassées

Suite au déploiement Sprint VPS-5, 3 chaînes de données étaient en
**échec silencieux** depuis 2-15 jours (DAGs verts mais 0 rows insérées).
Cause = dette schéma `gold.traffic_features_live` v0.3.1 (colonnes
renommées : `lag_1`, `delta_1`, `sin_hour`, `temperature_2m`,
`precipitation`, `computed_at`...) **non propagée à `silver_to_gold.py`**,
combinée à un changement de structure JSON côté WFS Grand Lyon, GBFS
Vélov et SIRI Lite TCL (juin 2026+).

### Corrigé

#### bronze_to_silver (3 transformers)

- **`_transform_trafic_boucles`** : nouveau format WFS Grand Lyon
  - `channel_id` extrait de `props["code"]` (ex. `LYO02336`), plus de
    `props["id"]` (chemin WFS complet, pas un identifiant capteur).
  - `vitesse` parsé depuis `"18 km/h"` → `18.0` (avant : string brute).
  - Filtre fraîcheur basé sur `fetched_at` (le WFS signale
    `est_a_jour=false` quasi systématiquement à cause de la dérive
    d'horloge des capteurs).
  - Geom : `silver.trafic_boucles_clean` attend `geometry(Point, 4326)`,
    le WFS renvoie `LineString` → workaround = point médian du segment.
    TODO Sprint 10 : passer la colonne en `LineString`.
  - SAVEPOINT par feature pour ne pas perdre les inserts valides en
    cas d'erreur sur une feature.

- **`_transform_tcl_vehicles`** : SIRI 2.0
  - `LineRef`, `VehicleRef`, `DirectionRef`, `StopPointRef` sont des
    objets `{"value": "..."}` au lieu de strings brutes → extraction
    via helper `_siri_ref()`.

- **`_transform_velov`** : inchangé, déjà fonctionnel (lat/lon absents
  du nouveau payload GBFS → NULL accepté).

#### silver_to_gold (5 requêtes SQL)

- **`_TRAFFIC_SQL`** : alignement schéma v0.3.1 (12+ colonnes renommées)
  - JOIN sur `dim_spatial_grid_mapping.properties_twgid` (et plus
    `channel_id` qui n'existe pas dans dim).
  - LATERAL `meteo` avec alias explicites (`temperature_c` →
    `temperature_2m`, `rain_mm` → `precipitation`).
  - `x_2154, y_2154` NULL (colonnes pas encore dans dim).
  - ON CONFLICT adapté : `(channel_id, fetched_at)`.

- **`_VELOV_SQL`** : CTE lit `silver.velov_clean.num_bikes_available`
  (et plus `bikes_available` qui n'existe pas).

- **`_BUS_DELAY_SQL`** : PK réel `(date, hour, line_ref, segment_id)`
  (et plus `(line_ref, segment_id, hour_of_day, day_of_week)`).

- **`_BOTTLENECK_SQL`** : filtre `date >= CURRENT_DATE - 7 days` (et
  plus `computed_at > ...` qui n'existe pas sur `bus_delay_segments`).

- **Nouveau `_build_tcl_realtime` + `_TCL_REALTIME_SQL`** : alimente
  `gold.tcl_vehicle_realtime` (Pro_4_Simulateur) depuis
  `silver.tcl_vehicles_clean` via `DISTINCT ON journey_ref` (dernière
  position par véhicule). Cleanup 1h (le Pro a besoin d'historique pour
  les graphes "trajet des 5 dernières minutes").

#### DAG `transform_silver_to_gold.py`

- Remplacement des **NOOP explicites** (`build_traffic_features`,
  `build_velov_features`) par les vrais appels `_run_traffic`,
  `_run_velov`. Le docstring "Tasks NOOP (gérées par
  legacy_github/dag_pipeline.py)" est obsolète : la chaîne
  `transform_silver_to_gold` est désormais autonome.
- Ajout de `build_tcl_realtime` dans la chaîne.
- Dépendance bottleneck : `[traffic, velov, tcl_realtime, bus_delay] >> bottleneck`.

### Résultats e2e (vérifiés sur VPS, snapshots 14:32 UTC+2)

| Table                              | Avant    | Après (15 min) |
| ---------------------------------- | -------- | -------------- |
| `silver.trafic_boucles_clean`      | 0 recent | **7 209 rows** |
| `silver.tcl_vehicles_clean`        | 0 recent | **1 546 rows** |
| `gold.traffic_features_live`       | 0 recent | **2 084 rows** |
| `gold.velov_features`              | 0 recent | **926 rows**   |
| `gold.bus_delay_segments`          | 0 rows   | **1 567 rows** |
| `gold.tcl_vehicle_realtime`        | 0 (15j)  | **577 rows**   |
| `gold.infrastructure_bottlenecks`  | 0 rows   | **1 567 rows** |

### Dette technique restante (Sprint 10+)

- `silver.trafic_boucles_clean.geom` devrait être `geometry(LineString, 4326)`
  (ou générique) pour stocker le tronçon complet au lieu du point médian.
- `gold.dim_spatial_grid_mapping` devrait exposer `x_2154, y_2154` (pour
  permettre le `JOIN` géométrique côté `_TRAFFIC_SQL`).
- `src/models/xgboost_speed.py` référence encore les anciennes colonnes
  (`speed_lag_1`, `node_idx`, `hour_sin`, `temperature_c`, `rain_mm`,
  `measurement_time`). Le baseline `dag_live_speed_retrain` prend le
  relais en attendant — Sprint 9+ prévu pour la migration.

## [0.6.0] - 2026-06-07 — VPS production (branche `vps`, ACTIVE)

**Décision déploiement : VPS unique.** Branche `vps` = source de vérité du
déploiement actif. Les branches `kubernetes` et `cloud-demo` restent dormantes,
préparées pour un futur déploiement AWS/GCP, **non mergées dans `vps` ou `main`**.

### Sprint VPS-1 — TLS + hardening

- **TLS Let's Encrypt** via certbot (`make certbot-init`, `make certbot-renew`)
- **nginx/ssl.conf** : HSTS, ciphers modernes, OCSP stapling
- **scripts/check-deploy-env.sh** : vérifie `.deploy.env` chmod 600 + vars critiques
- **docs/VPS_HARDENING.md** : SSH key-only, ufw firewall, fail2ban, users dédiés
- **make healthcheck-vps**, **make tls-status**

### Sprint VPS-2 — systemd + backup + rollback

- **scripts/systemd/lyonflow.service** : process supervisor
- **scripts/systemd/lyonflow-backup.timer** + `.service` : backup quotidien 03:00
- **scripts/backup.sh** + **scripts/restore.sh** : pg_dump compressed + rétention 30j
- **make rollback-vps** : rollback automatique dernière release
- **make tag-vps** : tag versionné déploiements
- CI `.github/workflows/ci.yml` : branche `vps` ajoutée

### Sprint VPS-3 — monitoring Prometheus / Grafana / Alertmanager

- **docker-compose.monitoring.yml** : Prometheus, Alertmanager, Grafana,
  node-exporter, postgres-exporter, nginx-exporter, redis-exporter
- **monitoring/prometheus/prometheus.yml** : scrape 15s, rétention 30j
- **monitoring/prometheus/rules/** : alertes api.yml, database.yml, system.yml
- **monitoring/alertmanager/alertmanager.yml** : webhook Discord/Slack
- **monitoring/grafana/dashboards/** : lyonflow-overview.json + lyonflow-business.json
- **nginx stub_status** sur localhost+Docker networks pour nginx-exporter
- **docs/MONITORING.md** : guide complet
- **make monitoring-up/down/status/logs**

### Sprint VPS-4 — métriques FastAPI custom

- **src/api/metrics.py** : Counter/Histogram/Gauge custom
  - `lyonflow_predictions_total` (model, horizon, status)
  - `lyonflow_prediction_latency_seconds` (model)
  - `lyonflow_persona_requests_total` (persona, endpoint)
  - `lyonflow_dag_runs_total` (dag_id, state)
  - `lyonflow_mlflow_active_runs` (experiment_name)
  - `lyonflow_db_query_duration_seconds` (query_type)
- **prometheus_fastapi_instrumentator** : expose `/metrics` standard FastAPI
  (http_requests_total, http_request_duration_seconds, process_*)
- Instrumentation `/api/v1/predict/traffic` + `/api/v1/predict/velov`

### Audit isolation

- **docs/CONTROLE_VPS_VS_CLOUD_DEMO.md** : matrice 3 contextes (VPS / K8s / cloud-demo)
  - Isolation physique VPS ↔ cloud-demo (cluster Scaleway séparé)
  - Isolation logique VPS ↔ K8s (namespace + NetworkPolicy)
  - Garde-fous PostgreSQL prod (volume `/opt/lyonflow/postgres_data`)

## [0.5.0-rc1] - 2026-06-07 — Phase 3 Cloud demo Jedha (branche `cloud-demo`, DORMANTE)

### Ajouté
- **Terraform Scaleway Kapsule** ephemere (control plane + 2 pools POP2)
- **Overlay `jedha-demo`** extends `kubernetes/base` (1 replica, hosts demo)
- **Scripts** `spin-up.sh` / `tear-down.sh` / `seed-demo-data.sh`
- **Docs soutenance** `SOUTENANCE_RNCP_38777.md` (pitch + Q&A + URLs)
- **DEMO_SCRIPT.md** : minute par minute 20 min + parade pannes
- Cout estime : ~0,40 €/h, ~2 € pour 3 repetitions + jour J

## [0.4.0] - 2026-06-07 — Phase 2 Kubernetes complete (branche `kubernetes`, DORMANTE)

### Ajouté
- **Kustomize base + overlays** (dev/prod) : 8 services manifests
- **Postgres StatefulSet** PostGIS 16 + PVC + backup CronJob daily
- **FastAPI/Streamlit** Deployment + HPA + Ingress TLS + PDB
- **Airflow Helm values** KubernetesExecutor + git-sync DAGs
- **Monitoring** kube-prometheus-stack + ServiceMonitor + 9 alertes
- **GNN trainer CronJob** nodeSelector GPU + tolerations + PVC weights
- **4 Dockerfiles** (api, dashboard, airflow, gnn CUDA 12.1)
- **CI workflow** `k8s-images.yml` buildx multi-arch + ghcr push + Trivy
- **Tests de charge** k6 (100 VU API) + Locust (Streamlit sessions)
- **Migration script** VPS→K8s avec checksums MD5 gold tables
- **Documentation** DEPLOY.md, RUNBOOK.md, DECOMMISSION.md

## [0.3.1] - 2026-06-07 — Fix pipeline (branche `main` + `vps`)

### Corrige
- **is_vacances/is_ferie** : 2 fonctions PL/pgSQL `_is_vacances(date)` /
  `_is_ferie(date)` enrichissent depuis bronze.calendrier_scolaire /
  bronze.jours_feries. Avant : valeur hardcodee `FALSE`.
- **N+1 SQL silver_to_gold.py** : remplace boucle Python 4 sous-queries
  par `INSERT...SELECT` avec window LAG/AVG + LATERAL meteo + JOIN
  spatial. Speedup x100 estime sur 1000 capteurs.
- **Doublon `src/ingestion/collectors.py`** : supprime (meme contenu
  que `__init__.py`).

### Change
- `src/ingestion/__init__.py` expose **classes** (lazy) au lieu d'instances
  pre-construites. Nouveaux : `REALTIME_COLLECTORS`, `MONTHLY_COLLECTORS`,
  `ALL_COLLECTOR_CLASSES`.
- DAGs `collect_bronze.py`, `collect_calendriers_monthly.py` : boucle
  `for cls in COLLECTORS` au lieu d'instanciation hardcodee.
- DAG `transform_silver_to_gold.py` : 3 fonctions Python nommees au
  lieu de lambdas (XCom serialisation propre).

### Conserve
- MinIO path dans `src/ingestion/base.py` (deprecated mais opt-in).

## [0.3.0] - 2026-06-06 — Phase 1 production-ready local (branche `main`)

### Sprint 7 — GNN training

#### Ajouté
- **SpatioTemporalGCN** PyTorch Geometric (`training/stgcn/model.py`)
- **STGCNDataset** + **STGCNTrainer** + **STGCNWrapper** production
- DAG Airflow `retrain_gnn.py` (daily 03h sur GPU)
- 19 tests (12 OK sans torch, 6 skip, 1 skip cuda.is_available)

### Sprint 6 — Couche data offline-first

#### Ajouté
- `src/data/db_query.py` (~480L) : helpers SQL parametres typeSafe
- `src/data/data_loader.py` (~280L) : cache + retry + fallback mock
- 6 widgets migres vers DB (sur 47, voir `archive/sprints/SPRINT_6_REPORT.md`)
- Page RGPD live + 42 nouveaux tests

## [0.1.0] - 2026-06-06 — Sprint 5

### Sprint 5 — Production-ready local

#### Ajouté
- **Infrastructure** : Docker Compose (12 services), Dockerfile non-root,
  Nginx reverse proxy avec rate limiting, init-db.sql complet
- **Ingestion** : 8 collecteurs Bronze (DataCollector ABC + tenacity)
- **Transforms** : Bronze→Silver (5 transformers) + Silver→Gold (3 builders)
- **ML** : XGBoost Speed (4 horizons) + Vélov (3 horizons)
- **API** : FastAPI 8 endpoints (predict, recommend, bottlenecks, RGPD, auth)
- **RGPD** : consentement, audit log, DSR, hashing SHA256
- **Data Governance** : data dictionary, lineage, PII classification
- **Airflow** : 6 DAGs (collect, transforms, retrain, maintenance)
- **File Manager** : page upload/download Streamlit
- **CI/CD** : GitHub Actions (lint, security, tests, docker build, Trivy)
- **Documentation** : README, ARCHITECTURE, DEPLOYMENT, DATA_GOVERNANCE
- **Monitoring** : 6 health checks + rate limit middleware
- **Sécurité** : scanning secrets, JWT auth, audit trail

### Sprint 1-4 — UI Foundation

#### Ajouté
- 3 personas (Usager, Pro TCL, Élu) avec auth par mot de passe
- 16 pages Streamlit (Mon Trajet, PCC Live, Synthèse exécutive, etc.)
- 45 widgets réutilisables
- Mock data Lyon réaliste (12 lignes TCL, 458 stations Vélov, etc.)
- Génération PDF (WeasyPrint + fallback reportlab)
- 28 tests (tous verts)
- Sélecteur de persona dans la sidebar

### Notes
- **Déploiement production actif** : VPS (branche `vps`, 0.6.0)
- Branche `kubernetes` (0.4.0) : DORMANTE, préparée AWS/GCP futur
- Branche `cloud-demo` (0.5.0-rc1) : DORMANTE, POC cloud ponctuel futur
- VPS replacement : garder PostgreSQL, remplacer le reste
