# CLAUDE.md — LyonFlow

> Mémoire projet — **dernière mise à jour : 2026-06-25, Sprint 22++ (Elu_2 fix + menu MLOps Usager)** (658 tests verts, dashboard 18 pages / 59 widgets, zéro mock, ruff clean).

## Projet

LyonFlow est une plateforme MLOps end-to-end de prédiction et d'analyse du trafic multimodal sur la Métropole de Lyon. Elle fusionne trois repos sources (caroheymes/Architect-IA-final-project, PDUCLOS/LyonFlow, PDUCLOS/lyontraffic) en un projet unifié.

**Auteur** : Patrice DUCLOS — Senior Data Analyst, Jedha RNCP 38777 (Architecte en IA)
**Repo** : PDUCLOS/lyonflow
**Cible production** : **VPS unique** `51.83.159.224` (Ubuntu, 6 CPU, 12 Go RAM, **2× 100 Go SSD** : sda = OS + code, sdb = PostgreSQL + MinIO + **Docker data-root** depuis Sprint 9+).

**Version actuelle** : **v0.12.1** (Sprints 1-7 + VPS 1-8 + 9+ + 11+ + 12+ + 13 + 13+ + 15+ + 17 + 17+ + 18 + 20 + 21 + 22 + 22+ + 22++) — branche `vps` ACTIVE
**Statut** : production VPS stable. Voir CHANGELOG.md pour le détail de chaque sprint.

### État au 2026-06-25 (Sprint 22+ + 22++ — v0.12.1 — Menu MLOps Usager + Elu_2 DB-driven)

- **18 pages × 3 personas** (5 Usager + 6 Pro TCL + 5 Élu + Accueil + RGPD + A_Propos) · **59 widgets** · **8 collecteurs Bronze** · **15 DAGs Airflow**
- ~280 fichiers Python · ~25 000 lignes
- **658 tests verts** · ruff clean
- **Sprint 22+ (2026-06-25, commit `691eaaf`, v0.12.0) — Menu MLOps Usager** :
  - **3 pages citoyen** sans jargon ML/DAG/PostGIS (cf. `theme.show_technical: false`) :
    - 🤖 **Notre modèle** (`Usager_3_Notre_Modele.py`) : précision 7j en clair, donut accuracy_band, courbe MAE.
    - 🌐 **Sources de données** (`Usager_4_Sources_Donnees.py`) : 8 sources + fraîcheur + score santé.
    - 🩺 **Statut du service** (`Usager_5_Statut_Service.py`) : 4 voyants synthétiques + top 5 incidents.
  - **Helpers réutilisés** : `cached_xgb_accuracy_summary`, `cached_predictions_vs_actuals`, `cached_source_health`, `cached_recent_alerts`.
- **Sprint 22++ (2026-06-25, commit `80bbb9b`, v0.12.1) — Elu_2 sur vraies données DB** :
  - Spec complète `docs/SPEC_FIX_ELU2_BOTTLENECKS.md` (491 lignes, 9 bugs).
  - **Bug 3/9** : `get_bottlenecks_summary` lit `gold.mv_bus_traffic_spatial` (MV spatiale 0.001°) au lieu de `gold.infrastructure_bottlenecks` (JOIN global par heure).
  - **Bug 1/4/5/7** : `load_bottlenecks_top` data-driven — gain = `avg_delay_s/60*0.5`, cout = `f(diagnosis)`, ROI = formule unifiée, voyageurs = `n_obs × 36`.
  - **Bug 2** : `bottleneck_map` lit vraies coords lat/lon, couleur par diagnostic (plus de dict coords hardcodé).
  - **Bug 4** : `bottleneck_ranking` colonne Diagnostic (🔴 infra / 🟠 ops / 🟢 voie bus / ⚪ ok).
  - **Bug 7** : `roi_calculator` affiche diagnostic, ROI cohérent avec ranking.
- **Tests** : +8 verts (3 dans `test_db_query_and_data_loader.py`, 5 dans `test_elu_widgets.py`).
- **Docs** : `DASHBOARD_PAGES.md`, `CLAUDE.md`, `CHANGELOG.md` mis à jour pour refléter 18 pages / 59 widgets / 658 tests.

### État au 2026-06-22 (Ops cleanup VPS — sda1 88% → 47%)

- sda1 libéré de **40 GB** (88% → **47%**, 52G libres).
- **Cleanup Docker** : `docker builder prune -a` (-34.52 GB cache) + containerd overlayfs snapshotter GC (`/var/lib/containerd` 48G → 20G, snapshots **253 → 161**/255 max).
- **Backup obsolète purgé** : `/opt/lyonflow/backups/backup_pre_028_*.dump` (13G, pre-migration 028 vérifiée OK : `osm.sensor_positions` 1159 + `osm.mv_sensor_to_way` 41737).
- **Backup-offsite systemd timer CRÉÉ** (était absent malgré la doc — corrigé) :
  - `/etc/systemd/system/lyonflow-backup.service` (oneshot, env from `/opt/lyonflow/.backup-offsite.conf`)
  - `/etc/systemd/system/lyonflow-backup.timer` (Quotidien **03:00 UTC** ± 15min random, `Persistent=true`)
  - Config `/opt/lyonflow/.backup-offsite.conf` (chmod 600) avec template + instructions `rclone config` interactif
  - Status : `Active: active (waiting)` next `Tue 2026-06-23 03:03:33 UTC`
  - **Action user requise** : `sudo rclone config` (Google Drive OAuth) + décommenter `GDRIVE_BACKUP_DEST=backups/lyonflow` dans `.backup-offsite.conf`
- **Prometheus absent confirmé** (intentionnel, Sprint 15+) — voir commentaires `docker-compose.monitoring.yml:14-18`. Exporters (node/postgres/nginx) + Grafana + Alertmanager UP mais affichent "no data".
- **Nginx restart-loop résolu** (était "Restarting 1141 fois" → maintenant healthy).

## Décisions ouvertes (en attente Patrice)

| Item | Statut | Impact si pas tranché |
|------|--------|----------------------|
| **`rclone config` destination offsite** | 🔴 Pending (interactif OAuth) | Backup-offsite fail clean tous les jours, journalctl spam |
| **Prometheus absent** (intentionnel Sprint 15+) | 🟡 À confirmer | Grafana affiche "no data" sur dashboards provisionnés |
| **Phase 3 / Phase 4 (K8s, cloud-demo)** | 🌑 Dormant | Aucune action avant AWS/GCP post-Jedha |
| **Axes spec interdépendances (2/4/6/7)** | ⏸ À planifier | Pas bloquant pour RNCP 38777 |

**Recommandation par défaut** (si pas de décision user explicite) :
- rclone : GCP Service Account JSON (pas d'OAuth, automation-friendly)
- Prometheus : laisser absent (Sprint 15+ justifié, exporters coûtent 200 MB mais Grafana mort de toute façon)
- Axes 2/4/6/7 : Axe 6 (qualité données) en priorité 1 post-Jedha

### État au 2026-06-22 (Sprint 21 — v0.11.0 — UX + Quantile + Sparkline + Docs cleanup)

- 15 pages × 3 personas · **~60 widgets** · **8 collecteurs Bronze** · **15 DAGs Airflow**
- ~180 fichiers Python · ~24 000 lignes
- **615 tests verts** · ruff clean
- **Sprint 20 (UX unifiée) — 4 axes livrés** :
  - **Axe B — Plotly theme** : `plotly_theme.py` (`LYF_TEMPLATE` + `COLORS` dict). 11/11 widgets migrés, 0 `plotly_dark` restant.
  - **Axe D — Error display** : `error_display.py` (`show_error(error_type, detail)` adapté par persona). 16 widgets migrés.
  - **Axe A — Loading wrapper** : `loading_state.py` (`loading_wrapper()` context manager). 32/32 widgets DB-hitting wrappés.
  - **Axe F — Freshness badge** : `freshness_badge.py` (badge prochaine MAJ). 15/15 pages câblées.
  - **Axe E — Accessibilité** : `a11y.py` (`plotly_with_alt`, `sr_only`). 18 alt texts pré-écrits.
- **Sprint 21 (bonus)** :
  - **Quantile regression XGBoost** : `XGBoostQuantileModel` (P10/P50/P90). Migration 029 `gold.trafic_predictions_quantile`. Bandes d'incertitude Plotly.
  - **Sparkline 24h** : `sparkline.py` widget + migration 030 `gold.mv_network_health_history`. Câblé dans `network_health_gauge`.
  - **Backup template** : `scripts/backup-template.sh` (pg_dump structuré).
- **Documentation cleanup (Sprint 21)** :
  - 13 docs stale archivés (`archive/sprints/`, `archive/audits/`, `archive/misc/`).
  - Merge `tests/ml/test_drift_detector.py` (doublon) → `tests/monitoring/`.
  - `SECURITY.md` version 0.1.x → 0.11.x. `DASHBOARD_PAGES.md` section "mode démo" supprimée.

### État au 2026-06-21 (Sprint 18 — v0.10.0 — pgRouting routing voiture OSM)

- 15 pages × 3 personas · **51 widgets** · **8 collecteurs Bronze** · **14 DAGs Airflow** (+1 `refresh_osm_traffic_costs` */15)
- ~175 fichiers Python · ~23 000 lignes
- **35 tests routing (26 unit + 9 pgRouting)** · ruff clean
- **Sprint 18 (2026-06-21) — pgRouting : routing voiture sur réseau routier OSM** :
  - **Root cause zigzag** : graphe H3 K=2 (GNN) utilisé pour le pathfinding voiture → itinéraires traversant le Rhône. Fix : `pgr_dijkstra` sur réseau routier OSM réel (~101k arêtes).
  - **Image Docker** : `postgis/postgis:16-3.4` → `pgrouting/pgrouting:16-3.5-3.7.3` (PGDATA byte-compatible).
  - **Import OSM** : Geofabrik Rhône-Alpes → osmium extract bbox Lyon → osm2pgrouting. 87k vertices, 101k arêtes, 14 types highway.
  - **Trafic temps réel** : `osm.sensor_positions` (1159 capteurs GiST) → `osm.mv_sensor_to_way` (41 737 arêtes, LATERAL KNN <->). DAG `refresh_osm_traffic_costs` `*/15 min` (~39 597 arêtes updated, ~20s).
  - **Refacto Python** : `graph.py` + `compute_route_pgrouting()`, `pathfinder.py` via pgRouting, `itinerary.py` polylines OSM multi-vertices. Contrat `plan_car_trip()`/`_road_itinerary_between()` préservé.
  - **Supprimé** : `snap_to_roads.py` (dead code). Exports retirés : `build_routing_graph`, `shortest_path`, `get_nearest_node`.
  - **Schéma `osm.*`** : `ways`, `ways_vertices_pgr`, `sensor_positions`, `mv_sensor_to_way`, fonctions `route_car()` + `refresh_traffic_costs()`.

### État au 2026-06-19 (Sprint 15+ — v0.7.1 — mypy clean + training/stgcn package)

- 15 pages × 3 personas · **51 widgets** · **8 collecteurs Bronze** · **13 DAGs Airflow**
- ~170 fichiers Python · ~22 000 lignes
- **301 tests verts / 4 SKIP / 14 deselected** · ruff clean · **mypy clean (82 fichiers, 0 erreur)**
- **Sprint 15+ v0.7.1 — Type safety** :
  - **Root cause "Source file found twice"** : `training/` n'avait pas de `__init__.py` → mypy résolvait `training/stgcn/dataset.py` à la fois comme `dataset` ET `training.stgcn.dataset`. Fix : `__init__.py` dans `training/` + `training/stgcn/` (+ cohérence avec `src/__init__.py` + `src/data/__init__.py`).
  - **`pyproject.toml [tool.mypy]`** : `explicit_package_bases = true` (sécurité).
  - **42 → 0 erreurs mypy** en 6 catégories : `Unused type: ignore` (12), `None has no attribute` (6), `Incompatible types` (8), `Argument X` Path optional (3), `int/float from object` (4), autres (2 — MLflow API + max type-var).
  - **Patterns réutilisables** : `cast(int, execute_scalar(...) or 0)`, double `or` pour `Path(model_dir or os.getenv(...) or default)`, assertions `is not None` après try/except.
  - **Aucun changement de logique métier** — typage pur. 19 fichiers, +89/-47 lignes.

### État au 2026-06-19 (Sprint 15+ — v0.7.0 — Interdépendances multimodales)

- 15 pages × 3 personas · **51 widgets** (+3 : multimodal_heatmap, bus_traffic_spatial, mode_comparison) · **8 collecteurs Bronze** · **13 DAGs Airflow** (10 actifs + 1 cron backfill + 1 archive silver + 1 TomTom actif)
- 9 endpoints API · 3 modèles ML · RGPD complet · ~170 fichiers Python · ~22 000 lignes
- **283 tests verts (+65 nouveaux) / 4 SKIP / 14 deselected** · ruff clean
- **Sprint 15+ (2026-06-19) — Analyse interdépendances multimodales (Axes 1 + 3)** :
  - **Spec complète** : `docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md` (7 axes, 883 lignes). Diagnostic lacunes + solutions SQL + widgets + tests + roadmap priorisée.
  - **Axe 1 — Grille multimodale** (migration 17) : vue matérialisée `gold.mv_multimodal_grid` fusionnant trafic + TCL + Vélov + météo sur grille 0.01° (~1 km). Score multimodal 0-10 par cellule. Widget `multimodal_heatmap.py` : carte Folium rectangles colorés + 4 KPI cards + tableau top saturées. DAG refresh */10 min (REFRESH CONCURRENTLY).
  - **Axe 3 — Bus × trafic spatialisé** (migration 18) : vue matérialisée `gold.mv_bus_traffic_spatial` avec JOIN spatial 0.001° (~100 m). Corrige le bottleneck global (`_BOTTLENECK_SQL` JOIN par heure globale → JOIN par zone locale). Widget `bus_traffic_spatial.py` : scatter Plotly + KPI + top zones. Option B non-breaking (coexiste avec ancien bottleneck). DAG refresh */15 min.
  - **Comparateur modes Usager** : spec `docs/SPEC_COMPARATEUR_MODES_USAGER.md`. Migration 16 `referentiel.tarifs_modes`. Eco-calculator (`eco_calculator.py`), widgets `mode_comparison.py` + `mode_summary.py`. Radio "Optimiser pour" (temps/coût) dans search_bar.
  - **Tests** : +65 tests (multimodal_grid 7 + bus_traffic_spatial 11 + comparateur + fixtures + audit).

### Roadmap interdépendances (7 axes, voir SPEC_OPTIMISATION_INTERDEPENDANCES.md)
- ✅ **Axe 1** (Sprint 15+) : grille multimodale 0.01° (fusion trafic + TCL + Vélov + météo)
- ✅ **Axe 3** (Sprint 15+) : bus × trafic spatialisé (JOIN zone 100 m)
- ✅ **Axe 5** (Sprint 15+) : score santé réseau 0-100 (migration 019 `gold.fn_network_health_score()` + widget jauge Plotly `network_health_gauge.py` en bandeau Élu). Redistribution poids si source indisponible.
- ⏸ **Axe 6** : qualité données (`data_quality.py`, port LyonTraffic)
- ⏸ **Axe 4** : report modal Vélov ↔ TC (PostGIS ST_DWithin 300 m, z-score)
- ⏸ **Axe 2** : propagation congestion (lag cross-correlation Granger simplifié)
- ⏸ **Axe 7** : météo comme variable d'interaction (impact quantifié par mode)

### État au 2026-06-18 (Sprint 13+ — v0.6.7 — TomTom Niveau 1)

- 15 pages × 3 personas · **48 widgets** (+1 coherence_scatter) · **8 collecteurs Bronze** (TomTom réactivé) · **13 DAGs Airflow** (10 actifs + 1 cron backfill + 1 archive silver + 1 **TomTom actif**)
- 9 endpoints API · 3 modèles ML · RGPD complet · ~165 fichiers Python · ~21 000 lignes
- **218 tests verts (+15 nouveaux) / 10 SKIP / 7 deselected** · ruff clean
- **Sprint 13+ (2026-06-18) — TomTom Niveau 1 (cross-validation sources)** :
  - **Dette Sprint 8 résolue** : DAG `collect_tomtom_traffic` sort du no-op. Nouvelle classe `TomTomTrafficFlow(DataCollector)` wrappe les fonctions existantes (`collect_lyon_tiles()` + `save_lyon_tiles_to_bronze()`). `*/15 min`, `retries=0`. Quota free tier 2500 req/jour largement respecté (1152 req/jour).
  - **Vue SQL `gold.v_coherence_tomtom_vs_grandlyon`** (migration 14) : JOIN spatial PostGIS `ST_DWithin < 200 m` entre tuiles TomTom (12 tuiles 0.02°) et capteurs `gold.channels_ref`. Pour chaque paire (tile_key, channel_id) calcule `delta_kmh`, `ratio_diff`, `status` (ok | minor_drift | drift | no_data).
  - **Vue SQL `gold.v_tomtom_gl_drift`** (migration 14) : capteurs avec ≥ 60% drift sur 24h → candidats "capteur HS". C'est le **détecteur automatique de capteurs en panne** côté Grand Lyon.
  - **Widget Pro_TCL `coherence_scatter`** : 4 KPI cards par status + scatter Plotly TomTom vs GL avec ligne y=x + heatmap top 20 deltas + tableau capteurs HS suspects. Câblé dans `Pro_3_Correlation.py` (sous la matrice bus × trafic).
  - **Helpers DB** : `get_tomtom_coherence()` + `get_tomtom_gl_drift()` (db_query) + `load_tomtom_coherence()` + `load_tomtom_gl_drift()` (data_loader, fail loud via `DashboardDataError` — politique zéro mock Sprint 8). Caches Streamlit `cached_tomtom_coherence` (30s) + `cached_tomtom_gl_drift` (60s).
  - **Câblage ingestion** : `TomTomTrafficFlow` importé + ajouté à `REALTIME_COLLECTORS` dans `src/ingestion/__init__.py`. Pattern unifié avec les 7 autres collecteurs Bronze.
  - **Tests** : 10 nouveaux tests (4 class `TestTomTomTrafficFlowNoKey`, 4 `TestTomTomTrafficFlowWithKey`, 3 `TestTomTomTrafficFlowImports` + 6 coherence helpers + 5 widget smoke) = **+15 verts**.

### Roadmap TomTom (3 niveaux, voir CHANGELOG.md pour décision utilisateur)
- ✅ **Niveau 1** (Sprint 13+) : ingestion propre + cohérence sources + détecteur HS
- ⏸ **Niveau 2** (Sprint 14, ~1 sem) : backtest engine — MAE croisé XGBoost vs TomTom (oracle externe). Drift detection Evidently.
- ⏸ **Niveau 3** (Sprint 15+, optionnel) : TomTom Routing API pour routing voiture temps réel. Payant, gain UX marginal vs Niveau 2.

### État au 2026-06-17 (Sprint 11+)

- 15 pages × 3 personas · 47 widgets · 8 collecteurs Bronze · **13 DAGs Airflow** (10 actifs + 1 cron backfill + 1 TomTom no-op + 1 archive silver-to-minio)
- 9 endpoints API · 3 modèles ML (XGBoost H+1h focus + SpatioTemporalGCN sur données réelles) · RGPD complet
- ~165 fichiers Python · ~21 000 lignes · **206 tests verts / 3 SKIP / 7 deselected (integration)** · ruff 54 → 6 erreurs cosmétiques
- Couche data complète (db_query + data_loader) — `gold.trafic_predictions` repeuplée toutes les 15 min par `dag_inference_xgboost`
- **Sprint 11+ (2026-06-17) — 3 fronts livrés** :
  - **Libellés TCL lisibles** : `clean_line_label()` dans `src/data/db_query.py` convertit `ActIV:Line::66:SYTRAL_h20` → `L66 ; 20h`. Widgets Pro TCL (`line_kpis`, `otp_heatmap`, `bottlenecks`) affichent `L66` au lieu de l'identifiant brut. 30 tests unitaires (parametrize sur 5 catégories).
  - **OOM-kill SIRI/Velov résolu** : `_transform_tcl_vehicles()` et `_transform_velov()` avec `LIMIT 5000 → 200` (worker Celery 6 Go pic mémoire passe de 5.8 Go à 1.2 Go). Tasks stables depuis 14h.
  - **Reorg documentation** : 26 docs historiques (8 sprints, 12 audits, 4 analyses, 2 misc) déplacés sous `archive/{sprints,audits,analysis,misc}/`. `archive/README.md` documente la convention (déplacer, jamais supprimer, traçabilité RNCP 38777).
  - Voir [archive/sprints/SPRINT_11_REPORT.md](archive/sprints/SPRINT_11_REPORT.md) pour détails.

### État au 2026-06-18 (Sprint 13 — v0.6.6)

- 15 pages × 3 personas · 47 widgets · 8 collecteurs Bronze · 13 DAGs Airflow
- 9 endpoints API · 3 modèles ML · RGPD complet · ~165 fichiers Python · ~21 000 lignes
- **203 tests verts / 4 SKIP / 7 deselected** · ruff clean (6 cosmétiques pré-existantes)
- **Sprint 13 (2026-06-18) — Audit cohérence pipeline + UX** :
  - **Version unique** : source de vérité `src/config.py` (`get_settings().app_version`). Sidebar, A_Propos, RGPD, Usager_1 — tous importent dynamiquement. Zéro version hardcodée dans le dashboard.
  - **Auto-refresh par persona** : `dashboard/components/auto_refresh.py` + `streamlit-autorefresh`. Pro TCL 30s, Usager 60s, Élu 300s. Câblé dans les 15 pages.
  - **Nettoyage complet `force_mock`** : suppression de `_is_demo_mode()`, `_maybe_force_mock()`, `_demo_mode_cache` dans `data_loader.py`. Param `force_mock` viré de ~60 signatures (data_loader + data_cache). Docstrings nettoyées dans 5 widgets.
  - **Cross-persona widgets** : `dashboard/components/widgets/common/__init__.py` re-exporte `render_traffic_map_compact`. `Usager_1` et `Elu_1` importent depuis `widgets.common` (plus de dépendance directe Pro TCL → Usager).
  - **Script cohérence** : `scripts/coherence-check.sh` (12 checks) + target `make coherence-check`. Vérifie : version unique, zéro mock, auto-refresh, cross-persona, TTL cohérence.
  - **`pyproject.toml`** : version `0.6.6`, dépendance `streamlit-autorefresh>=1.0.0`

### État au 2026-06-18 (Sprint 12+ — v0.6.5)

- 15 pages × 3 personas · 47 widgets · 8 collecteurs Bronze · 13 DAGs Airflow
- 9 endpoints API · 3 modèles ML · RGPD complet · ~165 fichiers Python · ~21 000 lignes
- **198 tests verts / 0 régression** · ruff clean
- **Sprint 12+ (2026-06-18, commit `862d991`) — Cleanup final audits Pro TCL + Usager** :
  - **UX "mode démo"** : `model_monitoring.py` 3 docstrings "MLflow ou mock" → "MLflow live" + bandeau warning MLflow reformulé
  - **Commentaires obsolètes** : `Elu_1_Synthese.py:68` + `Elu_5_Rapport.py:56` corrigés ("fallback mock auto" → "fail loud si DB indispo")
  - **Code cleanup `force_mock`** : 35 calls sites dans **26 fichiers dashboard/** nettoyés (`force_mock=False` viré, param conservé dans signatures pour rétro-compat)
  - **Weather widget** : `_weather_icon()` utilise `_LABEL_TO_EMOJI` constant module-level
  - **Ruff** : 2 trailing whitespace W291 auto-fixées
  - **Trackers d'audit fermés** : 100% des 30 items des `archive/audits/AUDIT_PRO_TCL_FIXES.md` (14) + `AUDIT_USAGER_FIXES.md` (16) — majorité déjà livrée dans les Sprints 8+ à 11+, ce sprint finit le ménage

### État au 2026-06-12

- 15 pages × 3 personas · 47 widgets · 8 collecteurs Bronze · **13 DAGs Airflow** (10 actifs + 1 cron backfill + 1 TomTom no-op + 1 archive silver-to-minio)
- 9 endpoints API · 3 modèles ML (XGBoost H+1h focus + SpatioTemporalGCN sur données réelles) · RGPD complet
- ~165 fichiers Python · ~21 000 lignes · **176 tests verts / 3 SKIP / 7 deselected (integration)** · ruff 54 erreurs cosmétiques (Sprint 9+ : cleanup `_is_demo_mode` + fix W291/I001 en cours)
- Couche data complète (db_query + data_loader) — `gold.trafic_predictions` repeuplée toutes les 15 min par `dag_inference_xgboost`
- **Sprint 8 (2026-06-12)** — **3 dettes critiques résolues** :
  - **ZÉRO MOCK DANS LE PROJET** : suppression complète de `src/data/mock/` (déplacé dans `tests/fixtures/mock_data/`). Tous les widgets, data_loader, db_query, airflow_client fail loud via `DashboardDataError`. 18 fallbacks mock virés.
  - **Focus H+1h** (Sprint VPS-6) : features XGBoost alignées schéma v0.3.1 (11 features : `speed_kmh, lag_1, lag_2, lag_3, rolling_mean_3, sin_hour, cos_hour, temperature_2m, precipitation, is_vacances, is_ferie`). 1 modèle H+1h uniquement.
  - **Ingestion Bronze stable** : `air_quality` (72 records) et `chantiers` (428 records) débloqués (dette schéma UNIQUE INDEX sur colonnes extracted). Healthcheck `scripts/healthcheck-vps.sh` 20/20 OK.
- **Sprint 8+** : durcissement Prometheus/Grafana/Alertmanager (config YAML cassée depuis v2.54, restart-loop résolu). Backups offsite (Sprint VPS-2) toujours actifs.
- **Sprint 9+ (2026-06-12, commit `7947cb1` + `fc806d2`)** — **Optimisation pipeline** :
  - **Découplage training/inf** : `dag_live_speed_retrain` (1x/30min, lourd) → `dag_daily_speed_train` (03h00, 1x/jour) + `dag_inference_xgboost` (15min, inférence pure, pas de fit()). **-98% CPU training**.
  - **Bug critique baseline 30.0** : `XGBoostSpeedModel.predict()` renvoyait 30.0 km/h constant (fallback silencieux) quand modèle pas chargé. **Fail loud** désormais (RuntimeError).
  - **Mapping LYO ↔ properties_twgid** : `gold.mv_twgid_to_lyo` (Polars + h3-py v4.5 vectorisé, H3 res 10 + k_ring(1)) — 1007 mappings, mean dist 103m. **speed_map graphe : 100% à 30.0 → 62% réel** (24 km/h mean).
  - **GNN sur données réelles** : `training/stgcn/dataset.py` aligné sur `caroheymes/Architect-IA-final-project`, lit `gold.fact_traffic_series` (889 234 rows × 1544 nœuds × 7 jours, vitesses 1-130 km/h). Plus de fallback `synthetic()`. Volume bind `training/` ajouté à airflow-scheduler.
  - **Materialised training set** : `gold.xgb_training_set` (quotidien 02h30, self-join H+1h indexé, 358 695 rows en 54s) + covering index `idx_gold_traffic_channel_computed`. XGBoost ne fait plus de `LEAD() OVER` 2.4M rows.
  - **Carte itinéraire voiture** : polyligne continue pointillée (au lieu de 8 traits dispersés) + cercles H3. Sprint 10+ : snap-to-roads Overpass.
  - **MinIO sdb2** : migré de `sda1` (80% plein) vers `/mnt/postgres-data/minio` (bind mount sdb2, 43 Go libres). DAG `silver_archive_to_minio` quotidien 04h00 (Parquet snappy + DELETE + VACUUM ANALYZE).
  - **Fix bugs latents** : `Usager_1_Mon_Trajet.py` import conflict (F811) + undefined names (F821). `time` ajouté à `xgboost_speed.py`. MLflow tracking vérifié (URI propagé).
  - **Tests** : 170 → 176 verts (Sprint 8+ → 9+), aucune régression.
  - Voir [archive/sprints/SPRINT_9_OPTIMISATIONS.md](archive/sprints/SPRINT_9_OPTIMISATIONS.md) pour détails.

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
| ML Trafic (spatial) | ST-GRU-GNN (PyTorch Geometric) — **daily 03h** |
| ML Trafic (réactif) | XGBoost **H+1h uniquement** (1 modèle, focus fiabilité VPS) — toutes les 30 min |
| ML Vélov | XGBoost (label encoding, 2 horizons H+30min + H+1h) — toutes les heures :50 |
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

### 1. Trafic routier : GNN + XGBoost en tandem

| Modèle | Rôle | Retrain | Force |
|--------|------|---------|-------|
| ST-GRU-GNN | Spatial — propagation congestion entre segments | Daily 03h | Dépendances spatiales, horizons longs |
| XGBoost speed H+1h | Réactif — changements récents | Toutes les 30 min | Météo/vacances/lags, focus fiabilité |

**Architecture GNN** (SpatioTemporalGCN) :
- GRU (5 canaux input, hidden_channels) → dernier hidden state
- 2× GCNConv + LeakyReLU + skip connections
- Linear → prédictions multi-horizon
- Graphe : ~1520 nœuds (H3 res 13), ~9540 arêtes K=2

**Ensemble** : les deux prédictions conservées. Recommandation trajet utilise le meilleur par segment (MAE comparé dans `gold.predictions_vs_actuals`).

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

### 3. Vélov : 2 horizons, économe

- **H+30min et H+1h uniquement** (focus H+1h comme le trafic)
- Label encoding stations (pas 458 one-hot → économie RAM de 9GB à ~500MB)
- **Features Sprint 8+ (référentiel schema v0.3.1)** : `station_id_encoded, bikes_lag_1/2/3, rolling_mean_3h, hour_sin/cos, temperature_c, rain_mm, is_vacances, is_ferie`
- Retrain **hourly :50**

### 4. Recommandation trajet multimodale

Pour chaque mode (voiture, bus/tram, vélov, marche, métro) :
- **Voiture** : **pgRouting `pgr_dijkstra` sur réseau routier OSM** (Sprint 18) — `compute_itinerary()` → `osm.route_car()` (~87k vertices, ~101k arêtes). Trafic temps réel injecté `*/15 min` via `osm.refresh_traffic_costs()` (41 737 arêtes mappées à capteurs Grand Lyon < 200m). Graphe H3 K=2 conservé uniquement pour le GNN.
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
| `gold.dim_spatial_grid_mapping` | Capteurs → nœuds GNN (H3 res.13, cell_to_local_ij). ~1520 nœuds, PK = `properties_twgid` (Sprint 8 hotfix 5 : backfill lat/lon via h3-py 4.5) |
| `gold.dim_gnn_adjacency` | Arêtes graphe (K=2 grid_disk, bidirectionnel + self-loops) |
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
03h  Retrain GNN daily (lourd, GPU si dispo)
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
| ST-GRU-GNN modèle + dataset | FinalProjet | Architecture validée, matrice adjacence H3 |
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

- `kubernetes` — Phase K8s complète (Kustomize + monitoring + GPU GNN). Cible : EKS / GKE futur.
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
│   ├── models/             # GNN, XGBoost H+1h focus, delay predictor
│   ├── routing/            # pathfinder_multimodal (Vélov smart + voiture Dijkstra)
│   ├── monitoring/         # Evidently, drift
│   └── api/                # FastAPI endpoints
├── training/
│   └── stgcn/              # GNN model, dataset, train, HPO
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
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── DATA_GOVERNANCE.md
│   ├── DEPLOYMENT.md
│   ├── DASHBOARD_PAGES.md
│   ├── MONITORING.md
│   ├── VPS_HARDENING.md
│   ├── RUNBOOK.md
│   ├── PLAN_NO_MOCK_VPS.md
│   ├── PROJECT_STATUS_AND_GOALS.md
│   ├── REPO_STRUCTURE.md
│   ├── GIT_STRUCTURE.md
│   ├── CONTROLE_VPS_VS_CLOUD_DEMO.md
│   ├── SPEC_OPTIMISATION_INTERDEPENDANCES.md  # Sprint 15+ : 7 axes optimisation
│   └── SPEC_COMPARATEUR_MODES_USAGER.md       # Sprint 15+ : comparateur 3 modes
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
| `SEQ_LEN` | non (120) | Longueur séquence GNN |
| `HORIZONS` | non (6,12,36) | Horizons prédiction GNN |
| `HIDDEN_CHANNELS` | non (128) | Dimension GRU/GCN |
| `WEIGHT_JAM` | non (15) | Pénalité congestion (staircase loss) |
| `WEIGHT_SLOW` | non (5) | Pénalité ralenti |
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
mypy dags/ training/ src/

# Tests (Sprint 8+ : addopts inclut "-m not integration")
pytest tests/ -v --tb=short
pytest tests/ -m integration  # pour les tests qui ont besoin du stack

# Healthcheck VPS (Sprint 8+)
./scripts/healthcheck-vps.sh

# Stack complète
docker-compose up -d --build
docker compose -f docker-compose.monitoring.yml up -d  # monitoring
```
