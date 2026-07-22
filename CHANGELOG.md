# Changelog

Toutes les modifications notables de ce projet sont documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased] - 2026-07-01 — Préparation certification RNCP : purge GNN + bugfixes prod + MLOps + DB (pas encore commité)

**600 tests verts** (601 avant retrait 1 test GNN) · ruff clean.

### Retiré

- Tandem GNN (ST-GRU-GNN) — code mort restant après l'archivage Sprint 24+ :
  `src/routing/graph.py` (`build_routing_graph`, `get_node_speed`,
  `get_nearest_node`), package `training/` (vide), 6 champs config hyperparams,
  entrée `stgcn_gnn` de l'API `/models`.
- `gold.dim_gnn_adjacency` renommée `gold.dim_spatial_adjacency` (migration_040)
  — la table servait en fait `gold.mv_congestion_propagation_pairs` (Axe 2),
  indépendante du GNN. Renommage plutôt que suppression.

### Corrigé

- `traffic_map.py` : crash `TypeError: Expected numeric dtype` (colonnes
  NUMERIC psycopg2/Decimal non coercées avant `.round()`). Nouveau helper
  `_coerce_numeric_columns` (`src/data/data_loader.py`).
- `cached_predictions_vs_actuals` manquante → `ImportError` sur
  `Usager_3_Notre_Modele.py` / `Usager_5_Statut_Service.py` (page crash prod).
  `gold.predictions_vs_actuals` archivée Sprint 24+ sans mise à jour de ces
  2 pages (ajoutées après, Sprint 22+). Fix : lit `gold.trafic_predictions`.
- `model_monitoring.py` : badge "XGB H+60min dispo" toujours (check fichier
  local `/app/models/xgb_speed_h60.json` inexistant, container streamlit sans
  volume `models/`). Fix : check fraîcheur `gold.trafic_predictions`.
- `refresh_osm_traffic_costs.py`, `refresh_sensor_saturation.py` :
  `statement_timeout=240s` ajouté — `execution_timeout` Airflow tuait le
  worker sans annuler la requête Postgres sous-jacente, causant un pileup de
  sessions zombies (3 incidents I/O récurrents dans la session, 20-45 min
  chacun).
- `idle_in_transaction_session_timeout` 0→10min (root cause d'un incident lock
  antérieur, cf. `docs/AUDIT_DB_2026-06-30.md`).

### Corrigé (suite — préparation certification RNCP, même jour)

- `build_spatial_mapping` : requête bornée 24h (cost -80%, 17.7s vs >8min) +
  connexion unique réutilisée au lieu de ~30k connexions individuelles. En
  échec quotidien depuis 8+ jours, run manuel validé en succès (30s).
- `maintenance_record_network_health` : `execute_query(fetch=True)` — kwarg
  inexistant, DAG en échec silencieux depuis sa création. `gold.network_health_history`
  vide depuis toujours (sparkline Élu cassée). Kwarg retiré, testé.
- `dag_inference_velov.py` (nouveau) : `gold.velov_predictions` n'avait jamais
  eu une seule ligne — le modèle Vélov s'entraînait mais aucune prédiction
  n'était jamais persistée. 454 lignes au premier cycle.
- MLflow Model Registry : client `mlflow` 3.14.0 (dashboard/API) incompatible
  avec le serveur 2.12.1 — `search_registered_models()` retournait `[]`
  silencieusement. Pin `mlflow<2.16` + `setuptools<81`, images rebuild.
- `maintenance_backfill_dim_spatial_lat_lon` réactivé : 1543 lignes
  `dim_spatial_grid_mapping` sans lat/lon → 0.
- Drift monitoring réactivé (`refresh_xgb_vs_tomtom` + `daily_drift_report`,
  mort 25 jours). `retrain_xgboost_speed` pausé (redondant, confirmé bit-identique
  sur 24 runs/jour).
- `VACUUM FULL osm.ways` (1,4 Go/3,8M dead → 39 Mo/0) + `silver.meteo_hourly`
  (718% bloat → 0). Mémoire container Postgres 2,5G → 4G.
- `silver_archive_to_minio` réactivé (connectivité vérifiée), tournera cette
  nuit pour archiver `silver.trafic_vitesse_propre` (29 Go).

Bilan DAGs : 25/27 actifs (2 pausés intentionnels et documentés). Rapport
complet : `docs/AUDIT_CERTIFICATION_2026-07-01.md`.

### Reste ouvert (non-bloquant)

- Thundering herd `:00`/`:30` — 5 DAGs re-décalés, root cause de fond
  (contention partagée) toujours présente.
- C2 (retrait `infrastructure_bottlenecks`) — étape 1/5 faite, étapes 3-5
  reportées (migration widgets + DROP TABLE, ~6h, risque moyen).

### Docs

- Triage complet : 17 docs déplacés vers `archive/{sprints,audits,analysis,misc}/`
  (specs/rapports livrés, snapshots datés). `archive/README.md` mis à jour.
  `docs/POSTGRES_TUNING_PROD.md` et `docs/AUDIT_AIRFLOW_POSTGRES_SPRINT24.md`
  mis à jour avec statut réel.

---

## [0.12.1] - 2026-06-25 — Sprint 22++ : Fix 9 bugs Elu_2_Bottlenecks — branche sur vraies données DB (branche `vps`)

**Commit** : `80bbb9b` — **658 tests verts (+8 nouveaux)** — ruff clean.

Spec complète : `docs/SPEC_FIX_ELU2_BOTTLENECKS.md` (491 lignes).

**Problème racine** : la page `Elu_2_Bottlenecks` affichait des données 100%
synthétiques (formules linéaires de l'index `i` de boucle), une carte vide
(dict coords hardcodé jamais matché), et jetait le seul signal réel (diagnosis).

### Bugs critiques ()

- **Bug 1** — `gain_min`, `cout_M_euros`, `roi_mois`, `delai_mois` hardcodés
  (`5 + i`, `2.5 - i * 0.15`, `18 + i * 3`, `6 + i * 2`). Fix : dérivés de
  `avg_bus_delay_s` + diagnosis + formule ROI cohérente. ROI unifié entre
  `bottleneck_ranking.py` et `roi_calculator.py`.
- **Bug 2** — Carte Folium ZÉRO marqueur. Dict coords de 10 rues hardcodé,
  mais `zone = clean_line_label(segment_id)` = `"L66 ; 20h"`, jamais matché.
  Fix : suppression du dict, lecture `b.get("lat"/"lon")` réelles depuis la MV.

### Bugs majeurs ()

- **Bug 3/9** — JOIN global par heure (moyenne tout Lyon) au lieu de JOIN
  spatial 0.001° par zone. Fix : `get_bottlenecks_summary` lit désormais
  `gold.mv_bus_traffic_spatial` (MV spatiale, refresh CONCURRENTLY */15 min).
- **Bug 4** — Diagnostic (seul signal réel, 4 valeurs `infra/operations/
  bus_lane_ok/ok`) jeté avant affichage. Fix : colonne Diagnostic ajoutée au
  ranking + couleur marqueurs carte + info-bulle calculateur ROI.
- **Bug 5** — `n_observations AS voyageurs_jour` (alias trompeur). Fix :
  estimation `voyageurs_jour = n_obs × 36` (1 obs ≈ 1 bus × ~80 passagers
  × ~45% occupation SYTRAL) — affichage "(estimé)" dans les widgets.

### Bugs moyens ()

- **Bug 6** — `lat/lon` calculés par `HASHTEXT(line_ref)` (coords déterministes
  mais fausses). Auto-résolu par Bug 3 (MV spatiale fournit vraies coords).
- **Bug 7** — ROI contradictoires (table `18 + i * 3` vs calculateur formule
  `voyageurs × gain × valeur_temps × 2 × jours_an / coût`). Fix : formule
  unique partagée.
- **Bug 8** — `DELETE FROM gold.infrastructure_bottlenecks` + `INSERT` complet
  toutes les 10 min (fenêtre "table vide"). Auto-résolu par Bug 3
  (REFRESH MATERIALIZED VIEW CONCURRENTLY).

### Fichiers modifiés (8)

| Fichier | Changements |
|---|---|
| `src/data/db_query.py` | `get_bottlenecks_summary` lit `mv_bus_traffic_spatial` (Bug 3/9) |
| `src/data/data_loader.py` | `load_bottlenecks_top` data-driven : gain/cout/ROI/voyageurs + `_build_bottleneck_description` (Bug 1/4/5/7) |
| `dashboard/components/widgets/elu/bottleneck_map.py` | Vraies coords lat/lon + couleur diagnostic (Bug 2/4) |
| `dashboard/components/widgets/elu/bottleneck_ranking.py` | Colonne Diagnostic + couleur (Bug 4) |
| `dashboard/components/widgets/elu/roi_calculator.py` | Affiche diagnostic sélectionné (Bug 7) |
| `dashboard/pages/Elu_2_Bottlenecks.py` | Wording + footer ROI cohérent |
| `tests/data/test_db_query_and_data_loader.py` | +3 tests : SQL source + dict format + empty case |
| `tests/persona/test_elu_widgets.py` | +5 tests : widget behavior (markers, diagnostic, lat/lon, no hardcodes) |

### Vérifications

- `pytest tests/ -q` : **658 verts**, 9 skipped (DB/ML indispo local), 0 régression
- `ruff check .` : clean
- `ruff format --check .` : clean

---

## [0.12.0] - 2026-06-25 — Sprint 22+ : Menu MLOps pour le persona Usager (3 pages citoyen) (branche `vps`)

**Commit** : `691eaaf` — **650 tests verts** — ruff clean.

Le persona Usager n'avait que 2 pages (Mon trajet + Alertes) alors que Pro
TCL a déjà un groupe MLOps (Pipeline Mgmt + Model Monitoring). Alignement
en **langage grand public** (cf. `theme.show_technical: false`) :

### Pages ajoutées (3)

| Icône | Page | Contenu |
|---|---|---|
| | `Usager_3_Notre_Modele.py` | Comment on prédit (langage citoyen) + précision 7j : donut accuracy_band, courbe MAE, qualité globale //|
| | `Usager_4_Sources_Donnees.py` | 8 sources Bronze + Silver + Gold expliquées (qui fournit, à quoi ça sert, fréquence), score santé 0-100, fraîcheur |
| | `Usager_5_Statut_Service.py` | 4 voyants synthétiques (Données / Modèle / Service / Alertes) + 5 derniers incidents + encart pédagogique |

### Choix design

- Aucune mention DAGs / MLflow / PostGIS dans le menu Usager (volontaire —
  le détail technique reste sur Pro_6 / Pro_7).
- Réutilisation des helpers existants : `cached_xgb_accuracy_summary`,
  `cached_predictions_vs_actuals`, `cached_source_health`, `cached_recent_alerts`.
- Style cohérent avec les autres pages (cards `lyonflow-card`, couleurs
  `COLORS["status_ok/warning/critical"]`, Plotly via `apply_lyf_theme`).

### Fichiers modifiés (4)

| Fichier | Changements |
|---|---|
| `dashboard/pages/Usager_3_Notre_Modele.py` | **NOUVEAU** (303 lignes) |
| `dashboard/pages/Usager_4_Sources_Donnees.py` | **NOUVEAU** (350 lignes) |
| `dashboard/pages/Usager_5_Statut_Service.py` | **NOUVEAU** (315 lignes) |
| `config/personas.yaml` | +3 entrées sous groupe `MLOps` () |

### Vérifications

- `pytest tests/` : 650 verts (0 régression vs 615 Sprint 21)
- `ruff check` + `ruff format` : clean
- Navigation YAML parsable : `get_navigation("usager")` retourne 5 entrées
  (2 Mobilité + 3 MLOps)

---

## [0.11.0] - 2026-06-22 — Sprint 20-21 : UX unifiée + Quantile regression + Documentation cleanup (branche `vps`)

Refonte UX transversale (4 axes), quantile regression XGBoost, sparkline santé réseau,
et nettoyage documentation (13 docs archivés, doublons mergés, docs centrales à jour).

### Added
- `dashboard/components/plotly_theme.py` — template Plotly unifié `LYF_TEMPLATE` + `COLORS` dict (Sprint 20 Axe B)
- `dashboard/components/error_display.py` — `show_error()` adapté par persona (Sprint 20 Axe D)
- `dashboard/components/loading_state.py` — `loading_wrapper()` context manager spinner (Sprint 20 Axe A)
- `dashboard/components/freshness_badge.py` — badge prochaine MAJ 15/15 pages (Sprint 20 Axe F)
- `dashboard/components/a11y.py` — `plotly_with_alt()`, `sr_only()`, 18 alt texts (Sprint 20 Axe E)
- `dashboard/components/sparkline.py` — sparkline 24h santé réseau (Sprint 21)
- `src/models/xgboost_quantile.py` — `XGBoostQuantileModel` P10/P50/P90 (Sprint 21)
- Migration 029 `gold.trafic_predictions_quantile` — bandes d'incertitude
- Migration 030 `gold.mv_network_health_history` — historique santé réseau 24h
- `scripts/backup-template.sh` — template backup pg_dump structuré (Sprint 21)

### Changed
- 11/11 widgets Plotly migrés vers `LYF_TEMPLATE` (0 `plotly_dark` restant)
- 32/32 widgets DB-hitting wrappés `loading_wrapper()`
- 16 widgets migrés vers `show_error()` unifié
- `CLAUDE.md` header Sprint 18 → Sprint 21, ajout état v0.11.0, composants UX
- `CHANGELOG.md` ajout entrée v0.11.0
- `SECURITY.md` version 0.1.x → 0.11.x + changelog sécurité enrichi
- `DASHBOARD_PAGES.md` section "mode démo" remplacée par "politique données"
- `docs/TODO.md` items P1.1, P1.2, P2.3, P3.1, P3.3, P4.2, P4.3 marqués DONE

### Removed
- `tests/ml/test_drift_detector.py` — doublon de `tests/monitoring/test_drift_detector.py`

### Archived (déplacer, jamais supprimer — RNCP 38777)
- 5 docs racine → `archive/sprints/` : BUGS_PRO_TCL_VPS, OPERATIONS_FINALES, SPRINT_14_PLAN, SPRINT_15_AUDIT, TODO_PRO_TCL_FIXES
- 3 docs → `archive/sprints/` : NEXT_STEPS_PGROUTING, ROUTING_FIX_STATUS, SPRINT_19_PLAN
- 2 docs → `archive/audits/` : DIAGNOSTIC_VPS_DASHBOARD, AUDIT_DASHBOARD_SPRINT15
- 3 docs → `archive/misc/` : PLAN_NO_MOCK_VPS, SPEC_APPLY_MIGRATIONS, PROJECT_STATUS_AND_GOALS

---

## [0.10.1] - 2026-06-23 — Sprint 18+ : 3 alternatives d'itinéraire via pgr_ksp (branche `vps`)

3 itinéraires alternatifs pour le routing voiture, sélectionnables par radio button.

### Added

- **`osm.route_car_ksp()`** — fonction SQL pgr_ksp (Yen K-shortest paths, `heap_paths := false`)
  retourne jusqu'à K chemins distincts avec géométrie + coût + label des rues principales.
- **`compute_route_pgrouting_ksp()`** (`graph.py`) — wrapper Python, groupement par `route_id`.
- **`compute_itinerary_alternatives()`** (`pathfinder.py`) — retourne `list[Itinerary]` (K max).
- **`_build_itinerary_from_edges()`** (`pathfinder.py`) — helper DRY partagé Dijkstra + KSP.
- **`_fmt_route_label()`** (`itinerary.py`) — label compact : "via Rue X, Rue Y (2.1 km · 5 min)".
- **Radio button UI** (`itinerary.py`) — sélecteur "Itinéraire" avec labels compacts.
  Alternatives cachées en `st.session_state` pour survivre aux reruns radio.

### Changed

- **`_compute_pgrouting_confidence()`** : cache TTL 1h (métrique globale, change lentement).
  Avant : recalcul COUNT + LEFT JOIN à chaque itinéraire → saturation sdb. Fix : `_CONFIDENCE_CACHE`.
- `_build_itinerary_from_edges()` : `road_name` fallback = `""` (au lieu de `f"edge_{id}"`).

### Tests

- +8 tests unitaires KSP (`test_pgrouting.py`) : groupement route_id, parsing GeoJSON,
  alternatives list, None handling, label formatting, unnamed roads.

---

## [0.10.0] - 2026-06-21 — Sprint 18 : pgRouting — routing voiture sur réseau routier OSM (branche `vps`)

Remplacement du graphe H3 K=2 (zigzag) par le réseau routier OSM réel
via pgRouting (extension PostgreSQL). Le routing voiture suit maintenant
les vraies rues de Lyon avec trafic temps réel.

### Root cause corrigée

Le routing voiture utilisait un graphe H3 hexagonal (K=2 nearest neighbors)
conçu pour le GNN, pas pour le pathfinding. Résultat : itinéraires en zigzag
traversant le Rhône et coupant des bâtiments. **pgRouting** résout le problème
à la racine avec `pgr_dijkstra` dirigé sur ~101k arêtes OSM réelles.

### Infrastructure

- **Image Docker PostgreSQL** : `postgis/postgis:16-3.4` → `pgrouting/pgrouting:16-3.5-3.7.3`
  (PostGIS 3.4 → 3.5, PGDATA byte-compatible, zéro dump/restore)
- **Extension** : `CREATE EXTENSION pgrouting` — Dijkstra dirigé côté SQL
- **Réseau OSM Lyon** : ~87k vertices + ~101k arêtes importées via `osm2pgrouting`
  (Geofabrik Rhône-Alpes → osmium extract bbox Lyon → 14 types highway)
- **Schéma** : `osm.ways`, `osm.ways_vertices_pgr`, `osm.sensor_positions`,
  `osm.mv_sensor_to_way` (41 737 arêtes mappées à un capteur Grand Lyon < 200m)
- **Migrations** : 026 (schéma + fonctions), 027 (réconciliation osm2pgrouting),
  028b (fix mv_sensor_to_way avec LATERAL KNN <-> operator, 6.6s au lieu de >1h)

### Routing voiture (refacto Python)

- **`src/routing/graph.py`** : + `compute_route_pgrouting()` (appel SQL `osm.route_car()`),
  + `get_nearest_osm_node()`. Graphe H3 conservé pour le GNN uniquement.
- **`src/routing/pathfinder.py`** : `compute_itinerary()` appelle pgRouting au lieu de
  `nx.astar_path()`. `ItinerarySegment.geometry` = polyline OSM multi-vertices.
  Confidence basée sur couverture capteurs (coverage-based, 50-100%).
- **`dashboard/components/widgets/usager/itinerary.py`** : `_render_map()` dessine
  `seg.geometry` (polylines OSM) au lieu de lignes droites entre nœuds H3.
- **`src/api/main.py`** : `ItinerarySegmentResponse.geometry` ajouté.
- **Contrat préservé** : `plan_car_trip()` et `_road_itinerary_between()` inchangés.

### Trafic temps réel

- **DAG `refresh_osm_traffic_costs`** (`*/15 min`) : injecte les vitesses capteurs
  Grand Lyon dans `osm.ways.cost` via `osm.refresh_traffic_costs()` (~39 597 arêtes).
- **Mapping capteur → arête** : `osm.sensor_positions` (1 159 capteurs, index GiST) →
  `osm.mv_sensor_to_way` (LATERAL KNN, couverture 41%).
- **Distribution observée** : 18 km/h (dense) → 56 km/h (fluide) sur Part-Dieu → Bellecour.

### Supprimé

- `src/routing/snap_to_roads.py` — dead code (Overpass snap), inutile avec pgRouting.
- Exports retirés de `__init__.py` : `build_routing_graph`, `shortest_path`,
  `get_nearest_node`, `CACHE_TTL_SECONDS`.

### Tests

- **+9 tests unitaires** (`tests/routing/test_pgrouting.py`) : parsing GeoJSON,
  dataclasses, geometry field, null/invalid handling, itinerary construction.
- **+7 tests intégration** (`tests/persona/test_routing.py`) : pgRouting end-to-end,
  géométrie multi-vertices, confidence, durée réaliste.
- 35 passed / 13 deselected (integration) · ruff clean.

### Fichiers ajoutés

| Fichier | Rôle |
|---------|------|
| `scripts/sql/migration_026_pgrouting_osm_network.sql` | Schéma `osm.*` + fonctions SQL |
| `scripts/sql/migration_027_reconcile_pgrouting_schema.sql` | Réconciliation post-osm2pgrouting |
| `scripts/sql/migration_028b_fix_mv_sensor_to_way_fast.sql` | Fix LATERAL KNN (perf) |
| `scripts/import_osm_lyon.sh` | Import OSM Lyon via osm2pgrouting |
| `scripts/osm2pgrouting_mapconfig.xml` | 14 types highway voiture |
| `dags/maintenance/refresh_osm_traffic_costs.py` | DAG `*/15 min` refresh coûts |
| `tests/routing/test_pgrouting.py` | 9 tests unitaires pgRouting |
| `docs/SPEC_PGROUTING_INTEGRATION.md` | Spec complète (15 sections) |
| `docs/ROUTING_FIX_STATUS.md` | Status + décisions |
| `docs/NEXT_STEPS_PGROUTING.md` | Next steps |

## [0.9.0] - 2026-06-21 — Sprint 17+ : Axe 2 niveau 2 — Granger statsmodels (branche `vps`)

Enrichissement de l'Axe 2 (Sprint 17) avec le test de causalité Granger
pour ajouter une couche de rigueur statistique à la direction de
propagation détectée par simple CORR cross-laggée. **Boucle la spec
interdépendances multimodales (7/7 axes + Granger niveau 2)**.

### Granger causality (Axe 2 niveau 2 — spec §3.3)

`statsmodels.tsa.stattools.grangercausalitytests` est plus RIGOUREUX que
la simple CORR cross-laggée parce qu'il teste si INCLURE les valeurs
passées de X AMÉLIORE la prédiction de Y (causalité statistique, pas
juste corrélation). Pour chaque paire, on teste les 2 directions (A→B
et B→A) et on garde la direction avec la p-value la plus faible.

- **Helper pur `compute_granger_causality()`** (~180 lignes) :
  - Top N paires par |CORR| (défaut 200, équilibre perf / couverture).
  - `statsmodels.grangercausalitytests(data, maxlag=3)` : 2 directions
    × 3 lags × top N = 1200 F-tests ≈ 5-10s.
  - Output : `granger_p_a_to_b, granger_p_b_to_a, granger_min_p,
    granger_direction, granger_significant` (p<0.05 par défaut).
  - Helper bas-niveau `_granger_min_p()` : `statsmodels` wrapper
    robuste (captures stdout/stderr, skip séries constantes/courtes).

- **Widget `propagation_map.py` enrichi** :
  - **KPI banner** : nouvelle 4ème card "Granger significatif"
    (p<0.05 sur N testées).
  - **Popup Folium** : section "Granger (causalité)" avec
    direction + p-value + statut significatif (vert/rouge).
  - **Tableau top 20** : nouvelle colonne "Granger p-val (direction)".
  - **Carte Folium AntPath** : pulse_color jaune (#FFEB3B) pour les
    paires Granger significatives (effet "highlighter" sur la carte).
  - **Légende** : nouvelle section "Granger (causalité)".
  - **Caption** : ajoute la mention Granger avec seuil p<0.05.

- **Tests `tests/widgets/test_propagation_map.py`** (50 tests verts,
  +10 nouveaux) :
  - `TestGrangerCausality` (5 tests) : empty inputs, vraie causalité
    (lag construction → p<0.05), bruit blanc, top_n limit, série
    constante skipped.
  - `TestGrangerMinP` (5 tests) : short series → None, constant → None,
    white noise (p-value valide), true Granger (p<0.05), seuil par
    défaut 0.05.

- **`requirements-base.txt`** : ajout `statsmodels>=0.14.0` (10 MB
  wheel, dépendance indirecte via pandas → déjà install).

### Notes de compromis

- **Performance** : Granger est ~5-10x plus lent que la simple CORR.
  On limite volontairement au top N=200 paires (les plus corrélées) pour
  rester sous la minute même sur 50k paires candidates après filtre
  min_obs. C'est un trade-off perf vs couverture, ajustable via
  `granger_top_n=...` au niveau du widget.

- **Hypothèse de linéarité** : Granger F-test suppose des relations
  linéaires. Pour la non-linéarité (plus robuste mais +lent), la spec
  mentionne Convergent Cross-Mapping (Mao et al., Wiley 2025) comme
  upgrade futur — hors scope actuel.

### Validation

- ruff check : All checks passed
- pytest : 450 verts / 10 skipped / 14 deselected (+10 nouveaux, 0 régression)

## [0.9.0] - 2026-06-21 — Sprint 17 : Axes 2 + 4 + 6 + 7 interdépendances multimodales (branche `vps`)

Livraison de **3 axes** du `docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md`
(883 lignes, 7 axes) qui restait à implémenter après les Sprints 15+ Axe 1
(grille multimodale) et 15+ Axe 3 (bus × trafic spatialisé) et Axe 5 (santé
réseau). Sprint 17 boucle la spec sauf Axe 6 (qualité données, futur) et
Axe 2 niveau Granger (futur, hors scope).

### Axe 7 — Météo comme variable d'interaction

Impact de la météo sur les 3 modes (trafic, TCL, Vélov) par bandes × mode,
avec delta vs "beau temps".

- **Migration 022** `scripts/sql/migration_022_meteo_impact.sql` :
  vue matérialisée `gold.mv_meteo_impact` (5 bandes × 3 modes + delta
  vs baseline fair). DROP IF EXISTS + CREATE MATERIALIZED VIEW
  idempotent.
- **Helpers db_query** : `get_meteo_impact()`.
- **Cache** : `cached_meteo_impact()` (TTL_SLOW = 300s, MV change 1×/jour).
- **Widget Pro_3** `meteo_impact.py` : tableau comparatif 5 bandes × 3
  modes + heatmap delta vs fair weather.
- **DAG** `refresh_meteo_impact.py` (04h30 quotidien) : REFRESH MV
  CONCURRENTLY.

### Axe 4 — Vélov ↔ TC report modal (z-score vélos dispos)

Détection d'incident TC par report modal Vélov : si ≥ 3 stations Vélov
proches d'une même ligne TC sont simultanément en alarme (z-score vélos
dispos < -2) → probable incident TC en cours.

- **Migration 023** `scripts/sql/migration_023_velov_transit_coupling.sql` :
  - Vue matérialisée `gold.mv_velov_transit_coupling` (positions GPS
    directes des véhicules TCL — pas centroïde AVG), z-score vélos
    dispos par station < 300m zone TC.
  - 3 commits successifs : (1) v1 centroïde AVG, (2) fix v2 positions
    GPS directes, (3) fix v3 fenêtre 15 min → 1h (test VPS : avec
    15 min, MV vide car pipeline > 15 min), (4) fix v4 DISTINCT ON
    (station_id, transit_line) — UNIQUE INDEX requis pour
    REFRESH CONCURRENTLY.
- **Helpers db_query** : `get_velov_transit_coupling()`,
  `get_velov_transit_coupling_summary()`.
- **Cache** : `cached_velov_transit_coupling()` + `_summary()`
  (TTL_FAST = 60s, réactivité temps réel).
- **Widget Pro_3** `modal_shift_alert.py` : bandeau KPI lignes TC en
  alerte + table des anomalies (z-score, ligne, station).
- **DAG** `refresh_velov_transit_coupling.py` (*/15 min) : REFRESH
  MV CONCURRENTLY (cadence rapide, détection incident temps réel).

### Axe 6 — Qualité des données (port LyonTraffic, data bounds)

Validation des valeurs Gold/Silver dans des plages physiquement
plausibles (Sprint 17 Axe 6, port du module `data_quality` de
`PDUCLOS/Lyontraffic` adapté au schéma LyonFlow).

- **Module `src/transformation/data_quality.py`** (~450 lignes) :
  - `QualityConfig` : seuils spec §7.1 (speed 0-130, temp -20/45,
    precip 0-100, delay 0-3600, null 30%, dup 5%, min_rows 100).
  - `CheckDetail` / `QualityReport` : dataclass sérialisable.
  - 4 sub-checks purs : `_check_range`, `_check_null_ratio`,
    `_check_duplicate_ratio`, `_check_min_rows`. Warning si 1-5%
    violations, critical au-delà.
  - 3 validators : `validate_traffic_features` (speed/temp/precip +
    null + dup + min_rows + doublons sur channel_id+computed_at),
    `validate_tcl_realtime` (delay_seconds + null + dup sur
    vehicle_ref+recorded_at), `validate_velov_clean` (bikes/docks
    ranges + null + dup sur station_id+measurement_time).
  - `run_all_validations()` : orchestrateur (retourne 3 reports).

- **Migration 025** `scripts/sql/migration_025_data_quality_log.sql` :
  table append-only `gold.data_quality_log` (id, checked_at,
  table_name, check_name, status, metric_value, threshold, details).
  Index sur (checked_at DESC, table_name). 1 ligne par CheckDetail.

- **Helpers `src/data/db_query.py`** : `get_quality_report(limit=100)`
  → dernier run par table depuis la vue append-only.

- **Cache Streamlit** : `cached_quality_report(limit=30)` (TTL_SLOW
  300s, 1×/jour alimenté par le DAG).

- **Widget Élu `data_quality_detail.py`** (~210 lignes) : drill-down
  des checks (3 KPI cards 1/table + tableau dernier run + historique
  5 derniers runs). **Complémentaire** de `data_quality_badge.py`
  (liveness sources vs qualité valeurs). Coût léger (1 query, cache
  300s), pas de button-gate.

- **DAG `data_quality_daily`** upgrade (Sprint 17 Axe 6) :
  - Remplace le stub `_data_quality_check()` qui déléguait à
    `health_checks.run_dag_health_check()` par un appel direct aux
    validators.
  - 3 loaders : `_load_traffic_features_df`, `_load_tcl_realtime_df`,
    `_load_velov_clean_df` (charge le DataFrame sur fenêtre 1h).
  - 6 task_ids legacy conservés (mapping 1-1 vers les 3 validators
    + sous-checks) : `bronze_freshness`, `bronze_volume`,
    `silver_nulls`, `silver_doublons`, `predictions_presentes`,
    `drift_baseline`.
  - INSERT 1 ligne par CheckDetail dans `gold.data_quality_log`
    (`_log_quality_report`). Raise `AirflowException` si overall
    == critical (alertes Airflow + Prometheus).

- **Tests `tests/data/test_data_quality.py`** (37 tests verts) :
  - `TestQualityConfig` : defaults conformes à la spec.
  - `TestDataclasses` : `to_dict()`, `is_critical`, `_aggregate_status`.
  - `TestCheckRange` / `TestCheckNullRatio` / `TestCheckDuplicateRatio` /
    `TestCheckMinRows` : 4 sub-checks purs, 5 cas chacun.
  - `TestValidateTrafficFeatures` : clean pass / speed out / null
    too high / dup too high / min_rows critical / empty df.
  - `TestValidateTclRealtime` : clean / delay out / negative warning.
  - `TestValidateVelovClean` : clean / negative bikes / bikes > 60.
  - `TestRunAllValidations` : 3 reports / empty warnings / shared config.
  - `TestEmptyReport` : empty df → warning (1 check failed).

### Axe 2 — Propagation de congestion (CORR cross-laggée Python)

Carte Folium animée (AntPath) montrant comment la congestion se propage
entre capteurs routiers adjacents, avec calcul de **corrélation croisée
laggée** pour détecter la direction de propagation.

- **Migration 024** `scripts/sql/migration_024_congestion_propagation.sql` :
  - 3 commits successifs : (1) v1 24h × 4 subqueries CORR par paire :
    timeout 3 min, (2) v2 6h × single-pass : timeout 4 min
    (CTE JOIN explose en cartésien), (3) v3 final : MV = index des
    50k paires (0.8s création), widget calcule CORR en Python
    (vectorisé, ~5s pour 5k paires après filtre min_obs).
  - Vue matérialisée `gold.mv_congestion_propagation_pairs` (index
    paires K=2 grid + lat/lon) + UNIQUE INDEX sur (node_a, node_b)
    pour REFRESH CONCURRENTLY.
- **Helpers db_query** : `get_congestion_propagation_pairs()`.
- **Helpers data_loader** : `load_congestion_propagation_pairs()`
  (MV) + `load_traffic_speeds_for_propagation(hours=6)` (JOIN
  `traffic_features_live` × `mv_twgid_to_lyo` pour mapping
  `properties_twgid` ↔ `channel_id` LYO).
- **Cache** : `cached_congestion_propagation_pairs()` (TTL_SLOW) +
  `cached_traffic_speeds_for_propagation(hours=6)` (TTL_REALTIME).
- **Widget Pro_3** `propagation_map.py` (500+ lignes) :
  - **Fonction pure** `compute_propagation_correlations()` :
    pivot large T × P, scan lag ±3 steps (= ±15 min), Pearson r
    normalisé strict (bornage |r| ≤ 1). Filtrage min_obs=30.
  - **Carte Folium AntPath** : lignes animées (les "fourmis"流动 le
    long de la ligne = direction visible par le sens du flux),
    couleur par intensité (rouge/orange/ambre/gris), épaisseur par
    |CORR|, légende HTML.
  - **Convention de lag** documentée : `lag > 0 = B lead A`
    (B est la source de propagation, flèche B → A),
    `lag < 0 = A lead B` (flèche A → B).
  - **KPI banner** : paires analysées / forte propagation / moyenne /
    directionnelle (|lag| > 0).
  - **Tableau top 20** par |r| avec direction propagation + lag minutes.
- **DAG** `refresh_congestion_propagation.py` (*/30 min) : REFRESH
  MV CONCURRENTLY (la MV change peu, le widget calcule les CORR
  à la volée).

### Compromis spec documentés (à valider au retour)

Sprint 17 fait **2 compromis perf vs spec** documentés en commentaire
dans les migrations 023 et 024 :

1. **Axe 4 fenêtre 15 min → 1h** : avec 15 min de fenêtre, la MV
   était vide car le pipeline Bronze→Silver met > 15 min à propager
   (Bronze 5min cadence + transform + Gold). Compromis : 1h couvre
   largement la détection d'incident (qui dure typiquement 30 min à
   2h). Le code reste paramétrable si on veut retester 15 min plus
   tard.
2. **Axe 2 CORR en Python** : 4 min timeout SQL pur (24h × 4
   subqueries) vs 0.8s pour la MV d'index seule. Compromis : la MV
   stocke juste les paires, le widget calcule les CORR en Python
   vectorisé (~5s pour 5k paires). Phase 2 spec §3.3 (Granger
   statsmodels) reste hors scope Sprint 17.

### Bilan Sprint 17

| Métrique | Avant (0.8.0) | Après (0.9.0) |
|----------|---------------|---------------|
| Axes spec implémentés | 3/7 (Axe 1, 3, 5) | **7/7** (+ 2, 4, 6, 7) |
| Widgets | 55 | **57** (+2 propagation + data quality detail) |
| Migrations SQL | 021 | **025** (+022, 023, 024, 025) |
| DAGs | 15 | **17** (+3 refresh Axe 2/4/7) |
| Tests | ~325 | **~440** (+37 data quality) |

### Fixes VPS durant Sprint 17

- **Worker Airflow débloqué** : `pg_terminate_backend` sur PID 1315609
  (idle in transaction depuis 2h+). Pipeline Bronze→Silver a
  recommencé à propager (0 → 464 → 4640 rows/1h).
- **Toutes les migrations Sprint 17** validées en conditions réelles
  sur le VPS.

### Déploiement Sprint 17 sur VPS

- **Migrations SQL** : 022, 023 (×4 commits), 024 (×3 commits) appliquées.
- **DAGs** : `refresh_meteo_impact` (04h30), `refresh_velov_transit_coupling`
  (*/15), `refresh_congestion_propagation` (*/30).
- **Widget** `propagation_map` button-gated dans Pro_3_Correlation.

## [0.8.0] - 2026-06-20 — Sprint 16 : Backtest Engine + Data Quality + Durées réelles (branche `vps`)

Sprint le plus ambitieux du projet : 3 axes, ~3 jours, 4 nouveaux widgets,
2 nouveaux DAGs, 2 migrations SQL, 18 nouveaux tests. Boucle MLOps complète
maintenant fermée (train → infer → **validate vs oracle externe**).

### Backtest Engine (Axe A — TomTom Niveau 2)

Validation XGBoost H+1h contre TomTom Traffic Flow (GPS flottes = oracle
externe). C'est la fin de la boucle MLOps ouverte en Sprint 8+.

- **Migration 020** : ``gold.mv_xgb_vs_tomtom`` (MV, jointure spatiale
  ST_DWithin 200m + temporelle ±10min) + ``gold.v_xgb_accuracy_summary``
  (MAE/MAPE/P90 par heure) + 3 index.
- **Helpers db_query** : ``get_xgb_vs_tomtom()``, ``get_xgb_accuracy_summary()``.
- **Cache** : ``cached_xgb_vs_tomtom()``, ``cached_xgb_accuracy_summary()``.
- **Widget Pro_7** ``backtest_dashboard.py`` : 4 KPI cards (MAE, MAPE, P90,
  n_pairs) + scatter Plotly XGB vs TomTom + courbe MAE temporelle
  7 jours + bar distribution accuracy_band + table top 10 pires prédictions.
  Button-gate via ``deferred_render()`` (coût élevé).
- **Widget Élu** ``drift_status_badge.py`` : bandeau compact 1 ligne,
  diagnostic différentiel (modèle dégradé / changement trafic réel /
  oracle dégradé / erreurs en hausse / stable).
- **DAG** ``refresh_xgb_vs_tomtom`` (*/30 min) : REFRESH MV CONCURRENTLY.
- **DAG** ``daily_drift_report`` (05h30 quotidien) : PSI drift detection
  + Evidently v0.7 optional (rapports HTML on-demand).
- **Upgrade** ``check_drift_evidently()`` : passe du placeholder "count
  reports" à lecture du dernier rapport + classification (ok/warning/critical).

### Data Quality (Axe B — Monitoring multi-source)

Passage du monitoring basique (6 checks quotidiens mono-table) à un
**monitoring par source temps réel** avec score de qualité agrégé.

- **Migration 021** : ``gold.v_source_health`` (8 sources + score 0-100
  + statut healthy/delayed/stale/dead) + ``gold.v_data_completeness``
  (% non-NULL colonnes critiques Silver 24h).
- **Helpers db_query** : ``get_source_health()``, ``get_data_completeness()``.
- **Widget Pro_6** ``source_health_monitor.py`` : jauge Plotly 0-100
  (poids trafic=3, TCL=2, Vélov=2, autres=1) + grille 8 sources + 3
  barres complétude Silver.
- **Widget Élu** ``data_quality_badge.py`` : bandeau 1 ligne (n healthy/stale/dead + score).
- **Upgrade** ``check_all_sources()`` : remplace les 6 checks mono-table
  (legacy ``ALL_CHECKS_LEGACY`` conservé pour transition).

### Durées réelles (Axe C — Comparateur multimodal)

Remplace les vitesses moyennes hardcodées (Vélov 12, TC 18, Voiture 25 km/h)
par les durées réellement calculées par chaque widget trajet.

- **velov_trip, transit_trip, itinerary** : signature ``-> dict | None``,
  retour ``{duration_min, distance_km, feasible, source: "computed"}``.
- **Usager_1** : ``session_state["trip_<key>"]`` pour chaque mode + passage
  des durées réelles à ``render_mode_comparison()`` (fallback estimation
  si pas encore calculé).
- **mode_comparison** : badge "Durée calculée" (vert) ou "Estimé"
  (orange) selon ``result.source``.

### Refacto : PSI primary + Evidently v0.7 optional (post-Sprint 16)

Suite du diagnostic complet dans ``docs/SPEC_EVIDENTLY_CONFIGURATION.md``
(855 lignes).

- **Problème** : ``drift_detector.py`` utilisait l'API Evidently v0.4
  (imports cassés en v0.7) → DAG ``daily_drift_report`` timeout 30s
  à l'import sur le VPS.
- **Décision** : PSI devient le moteur principal (zéro deps, déjà
  testé, déterministe). Evidently v0.7 reste en optionnel (rapports
  HTML on-demand depuis Pro_7 ou notebook local).
- **Bénéfice** : -250 Mo image Docker (evidently + 13 deps transitives
  virées du chemin critique), DAG quotidien 5-10s au lieu de 15-30s.
- **Modifications** :
  - ``src/monitoring/drift_detector.py`` : API v0.4 → PSI primary
    + ``generate_html_drift_report()`` (Evidently v0.7, on-demand).
  - ``drift_status_badge._diagnose_drift()`` : diagnostic différentiel
    (5 cas : modèle dégradé / trafic réel / oracle dégradé / erreurs
    en hausse / stable).
  - ``requirements-airflow.txt`` : ``evidently>=0.4,<0.5`` **viré**.
  - ``requirements-base.txt`` : ``evidently>=0.7.0`` marqué optional
    (PEP 508 ``; extra == "drift-reports"``).
  - ``tests/monitoring/test_evidently_configuration.py`` (24 tests).

### Bug fix migration 021 (post-Sprint 16)

- ``silver.trafic_boucles_clean`` a une colonne ``geom`` (et ``geom_2154``
  PostGIS), pas ``geom_wgs84``. La migration 021 plantait au déploiement.
  Fix appliqué + redéployé.

### Bilan Sprint 16

| Métrique | Avant (0.7.1) | Après (0.8.0) |
|----------|---------------|---------------|
| Widgets | 51 | **55** (+4) |
| DAGs | 13 | **15** (+2) |
| Tests | ~301 | **~325** |
| Sources monitorées | 1 (trafic) | **8** (toutes Bronze + Gold) |
| Validation modèle | aucune externe | **XGBoost vs TomTom oracle** |
| Drift detection | placeholder | **Evidently DataDriftPreset + PSI quotidien** |
| Durées comparateur | estimées | **calculées** (+ fallback estimé) |

### Déploiement Sprint 16 sur VPS

- **Migrations SQL** : 020 + 021 appliquées manuellement (script apply
  à venir — voir TODO).
- **DAGs** : ``refresh_xgb_vs_tomtom`` (is_paused=True, schedule */30),
  ``daily_drift_report`` (is_paused=True, schedule 30 5 * * *).
- **Tags déployés** : ``vps-20260620-111838``, ``vps-20260620-092233``.

## [0.7.1] - 2026-06-19 — Sprint 15+ : mypy clean (42 → 0 erreurs) + training/stgcn package (branche `vps`)

Sprint dédié **type safety** : résout le `Source file found twice` (root cause
structurelle) puis fixe les 42 erreurs mypy par catégorie, sans aucun changement
de logique métier.

**Diagnostic root cause** :
- `training/` n'avait pas de `__init__.py` → mypy résolvait
  `training/stgcn/dataset.py` à la fois comme `dataset` (top-level via scan) ET
  `training.stgcn.dataset`.
- Solution : `__init__.py` dans `training/` et `training/stgcn/` (+ cohérence
  Python avec `src/__init__.py` et `src/data/__init__.py`).
- `pyproject.toml [tool.mypy]` : `explicit_package_bases = true` (sécurité).
  NE PAS ajouter `mypy_path = "src"` : crée conflit `ingestion` vs
  `src.ingestion`.

**42 erreurs mypy corrigées en 6 catégories** :

| Catégorie | Compte | Fix pattern |
|-----------|--------|-------------|
| `Unused type: ignore` | 12 | Suppression — `ignore_missing_imports=true` rend les `# type: ignore` sur torch/mlflow/weasyprint inutiles |
| `None has no attribute` | 6 | Annotations `_model: Any` + assertions `is not None` après try/except ImportError ou check `load()` |
| `Incompatible types` assignment | 8 | Annotations explicites (`list[np.ndarray]`, `dict[str, Any]`, `tuple`), renommage `val_preds_arr` post-concatenate, `final_metrics` permissive |
| `Argument X incompatible` (Path optional) | 3 | Double `or` : `model_dir or os.getenv(...) or default` (mypy ne narrow pas la default de `os.getenv`) |
| `int/float from object` | 4 | `cast(int, ...)` / `cast(float, ...)` sur `execute_scalar(...) or 0` (helper DB retourne `object \| None`) |
| Autres | 2 | `list_experiments()` → `search_experiments()` (API MLflow 2.x, fix de bug réel) + `max()` filter `is not None` + `cast(datetime, ...)` |

**Bonus ruff** : 7× W293 + 1× W291 + F401 cast unused → `ruff --fix --unsafe-fixes`.

**Bilan** :
- mypy : `Success: no issues found in 82 source files`
- ruff : `All checks passed`
- pytest : **301 verts / 4 skipped / 14 deselected** (aucune régression)

**Fichiers** : 19 modifiés, +89/-47 lignes, 4 créés (3 `__init__.py` + structure).
Commit : `3c7d7b6 feat(sprint15+): mypy clean (42 → 0 erreurs) + training/stgcn devient package`.

## [0.7.0] - 2026-06-19 — Sprint 15+ : Axe 1 — Grille multimodale (branche `vps`)

Première livraison de `docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md` :
**fusion multi-sources sur grille spatiale 0.01° (~1 km)** combinant
trafic routier + TCL temps réel + Vélov + météo en une seule vue. C'est
la fondation qui permet les axes suivants du spec (bus × trafic
spatialisé, propagation congestion, couplage Vélov ↔ TC).

### Ajouté
- **Migration 17** `scripts/sql/migration_017_multimodal_grid.sql` :
  - Vue matérialisée `gold.mv_multimodal_grid` (DROP IF EXISTS +
    CREATE MATERIALIZED VIEW — pattern idempotent comme la migration 15).
  - Agrège sur grille 0.01° (FULL OUTER JOIN des 3 CTEs + CROSS JOIN
    météo single-row) : `gold.traffic_features_live` × `gold.tcl_vehicle_realtime`
    × `silver.velov_clean` × `silver.meteo_hourly`.
  - **Score multimodal 0-10** : `clamp(0.5 × pct_congestion/10 +
    0.5 × pct_delayed/10 - bonus_vélov)` (bonus = 1.0 si vélos ≥ 5).
  - **Diagnostic dominant** : `saturated` (>60% cong. ET >40% retard),
    `road_congested` (>60% cong.), `transit_delayed` (>40% retard),
    `velov_scarce` (vélos < 3 ET ≥ 1 station), `ok` (reste).
  - 3 index : unique `(lat, lon)` (requis pour REFRESH CONCURRENTLY),
    `diagnosis`, `score_multimodal DESC`.
- **Helpers DB** : `get_multimodal_grid(limit)` + `get_multimodal_grid_diagnosis_counts()`
  dans `src/data/db_query.py` (pattern `_df_from_query` — DataFrame vide
  si DB indispo, fail loud au niveau data_loader).
- **Wrappers fail-loud** : `load_multimodal_grid(limit)` +
  `load_multimodal_grid_diagnosis_counts()` dans `src/data/data_loader.py`.
  Lèvent `DashboardDataError` si DB indispo OU si la MV est vide
  (> 30 min = DAG refresh qui n'a pas tourné).
- **Cache Streamlit** : `cached_multimodal_grid()` (TTL 60s = 1 cycle
  de refresh DAG) + `cached_multimodal_grid_diagnosis_counts()` dans
  `dashboard/components/data_cache.py`.
- **Widget `dashboard/components/widgets/pro_tcl/multimodal_heatmap.py`** :
  - 4 KPI cards : Saturé / Tendu (route + TC) / Vélov scarce / Fluide
  - Carte Folium avec rectangles colorés par `score_multimodal` (rouge
    saturé, orange tendu, vert fluide). Popup détaillé : vitesse trafic,
    retard TCL, vélos/docks dispo, météo.
  - Tableau top 15 cellules saturées avec badge coloré sur Diagnostic.
  - Fail loud via DashboardDataError → `st.error(...)` côté page.
- **Câblage page** : section "Vue multimodale grille 0.01°" ajoutée
  à `dashboard/pages/Pro_3_Correlation.py` (sous la section TomTom
  × GL, en bas de page — zéro impact sur les widgets existants).
- **DAG refresh** : nouvelle tâche `refresh_mv_multimodal_grid` dans
  `dags/transforms/transform_silver_to_gold.py` (dépend de
  `traffic + velov + tcl_realtime`). Refresh `REFRESH MATERIALIZED VIEW
  CONCURRENTLY` toutes les 10 min (index unique requis). Vérifie que
  la MV existe avant refresh (warning clair si migration 17 pas
  appliquée, sans planter le DAG).

### Changed
- `src/transformation/silver_to_gold.py` : `target='multimodal_grid'`
  ajouté à `transform_silver_to_gold()` + helper `_refresh_multimodal_grid()`.
- `dashboard/components/widgets/pro_tcl/__init__.py` : export
  `render_multimodal_heatmap` (ajouté à `__all__`).
- `dashboard/pages/Pro_3_Correlation.py` : import `render_multimodal_heatmap`
  + section dédiée + caption explicative des 3 sources de données.

### Fixed
- **Adaptation schéma réel** : le spec initial utilisait
  `silver.meteo_hourly.temperature_2m` / `precipitation` mais le schéma
  effectif a `temperature_c` / `rain_mm` (cf. `silver_to_gold.py:192-193`).
  Le commentaire en tête de la migration documente cette divergence.

**Tests** : 265 verts (+7 nouveaux test_multimodal_grid.py), 11 skipped,
14 deselected. Ruff clean sur les 8 fichiers du PR.

### Bonus Sprint 15+ — Comparateur de modes Usager (Phase 1 + Phase 2)

Première livraison de `docs/SPEC_COMPARATEUR_MODES_USAGER.md` :
**comparateur temps/coût/CO2** pour les 3 modes (TC, Voiture, Vélov)
avec recommandation selon critère choisi (temps ou coût).

#### Ajouté
- **Migration 16** `scripts/sql/migration_016_tarifs_modes.sql` :
  table référentielle `referentiel.tarifs_modes` (€/km, g CO2/km
  par mode + vitesse moyenne + source ADEME). Pattern idempotent
  (DROP IF EXISTS + CREATE).
- **Helpers routage** : `src/routing/eco_calculator.py` —
  `calculate_impact(mode, distance_km, is_congested)` + `get_comparison(...)`
  + `recommend_mode(...)`. Pur Python (zéro DB — utilise tarifs_modes
  chargés via fonction dédiée). Testable hors-ligne.
- **Wrappers fail-loud** : `load_car_itinerary(...)` + `load_velov_itinerary(...)`
  dans `src/data/data_loader.py`. Sérialisent les dataclasses en dict
  pour compatibilité `@st.cache_data` Streamlit.
- **Cache Streamlit** : `cached_car_itinerary` + `cached_velov_itinerary`
  + `cached_mode_impact` dans `dashboard/components/data_cache.py`.
- **Widget `dashboard/components/widgets/usager/mode_comparison.py`** :
  comparateur 3 modes côte à côte (cartes temps + coût + CO2) avec
  badge "recommandé" selon critère.
- **Widget `dashboard/components/widgets/usager/mode_summary.py`** :
  enrichissement Phase 1 — KPI cards (temps, coût, CO2) sous l'itinéraire
  du mode sélectionné.
- **Câblage search_bar** : radio "Optimiser pour" (Temps / Coût)
  dans `dashboard/components/widgets/usager/search_bar.py`. Clé
  `critere` ajoutée au dict retourné (consommée par les 2 widgets).
- **Spec de référence** : `docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md`
  (883 lignes, 7 axes — Axe 1 = grille multimodale livrée dans cette
  entrée, Axes 2-7 = backlog).

#### Changed
- `src/routing/__init__.py` : export public `calculate_impact`,
  `get_comparison`, `recommend_mode` (facade routing).
- `dashboard/components/widgets/usager/__init__.py` : export
  `render_mode_comparison` + `render_mode_summary`.

**Tests** : 265 verts (Sprint 15+ multimodal + comparateur, +7 test_multimodal_grid.py),
11 skipped, 14 deselected. Ruff clean sur les 8 fichiers du PR.

### Axe 3 (Sprint 15+) — Couplage bus × trafic spatialisé

Deuxième livraison de `docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md` :
**JOIN spatial PostGIS** entre positions temps réel des véhicules TCL
(`gold.tcl_vehicle_realtime`) et trafic routier (`gold.traffic_features_live`)
sur grille **0.001° ≈ 100 m** + bucket horaire.

Corrige la lacune structurelle de `_BOTTLENECK_SQL` qui faisait le JOIN
bus × trafic par **heure globale** (le retard du bus L12 à 8h était
corrélé au trafic **moyen** de tout Lyon, pas au trafic local du
tronçon Part-Dieu ↔ Gerland).

#### Ajouté
- **Migration 18** `scripts/sql/migration_018_bus_traffic_spatial.sql` :
  - Vue matérialisée `gold.mv_bus_traffic_spatial` (DROP IF EXISTS +
    CREATE MATERIALIZED VIEW — pattern idempotent).
  - Agrège `gold.tcl_vehicle_realtime` (avg_delay_sec, n_obs,
    n_delayed) × `gold.traffic_features_live` (avg_speed, n_sensors)
    par (line_ref, hour, lat3, lon3) avec jointure gauche sur la
    zone spatio-temporelle (résolution 0.001° ≈ 100 m).
  - **Diagnostic dominant** 4 états : `infra` (bus retard + trafic
    bouché), `operations` (bus retard + trafic fluide), `bus_lane_ok`
    (bus à l'heure + trafic bouché = voie bus fonctionnelle), `ok`.
  - **Score congestion** `traffic_congestion` ∈ [0, 1] :
    `1 - LEAST(avg_speed / 50, 1)` (50 km/h = vitesse max fluide).
  - 3 index : unique `(line_ref, hour, lat, lon)` (requis pour
    REFRESH CONCURRENTLY), `diagnosis`, `line_ref`.
- **Helpers DB** : `get_bus_traffic_spatial(limit)` +
  `get_bus_traffic_spatial_diagnosis_counts()` dans `src/data/db_query.py`
  (pattern `_df_from_query`).
- **Wrappers fail-loud** : `load_bus_traffic_spatial(limit)` +
  `load_bus_traffic_spatial_diagnosis_counts()` dans
  `src/data/data_loader.py` — lèvent `DashboardDataError` si DB indispo
  OU si la MV est vide (> 30 min = DAG refresh qui n'a pas tourné).
- **Cache Streamlit** : `cached_bus_traffic_spatial` (TTL 60s) +
  `cached_bus_traffic_spatial_diagnosis_counts` dans
  `dashboard/components/data_cache.py`.
- **Widget `dashboard/components/widgets/pro_tcl/bus_traffic_spatial.py`** :
  - 4 KPI cards (infra / operations / bus_lane_ok / ok)
  - Scatter Plotly `bus_delay_sec` (X) × `traffic_speed_kmh` (Y)
    coloré par diagnosis + ligne médiane retard 120s en pointillés
  - Tableau top zones infra avec line_ref + zone GPS + retard + vitesse
  - Fail loud via DashboardDataError → `st.error(...)` côté page.
- **Câblage page** : section "Couplage bus × trafic spatialisé" ajoutée
  à `dashboard/pages/Pro_3_Correlation.py` (entre la matrice globale
  et le scatter TomTom × GL — zéro impact sur les widgets existants).
- **DAG refresh** : nouvelle tâche `refresh_mv_bus_traffic_spatial` dans
  `dags/transforms/transform_silver_to_gold.py` (toutes les 15 min,
  REFRESH CONCURRENTLY grâce à l'index unique, dépend de
  `tcl_realtime + traffic`). Fail-safe si migration 18 pas appliquée
  (warning clair, ne plante pas le DAG).
- `src/transformation/silver_to_gold.py` : target `bus_traffic_spatial`
  ajouté à `transform_silver_to_gold()` + helper
  `_refresh_bus_traffic_spatial()` (vérifie MV existe avant refresh).

#### Changed
- `dashboard/components/widgets/pro_tcl/__init__.py` : export
  `render_bus_traffic_spatial` (ajouté à `__all__`).
- `dashboard/pages/Pro_3_Correlation.py` : import `render_bus_traffic_spatial`
  + section dédiée.

#### Notes
- **Option B (non-breaking)** : la MV coexiste avec
  `gold.infrastructure_bottlenecks`. Le widget `bus_traffic_spatial.py`
  lit cette MV ; `correlation_matrix.py` continue de lire l'ancienne.
  Bascule vers Option A (remplacement) après ≥ 7 jours de validation
  sur données réelles.

**Tests** : 273 verts (+11 nouveaux test_bus_traffic_spatial.py),
3 skipped, 9 deselected. Ruff clean sur les 9 fichiers du PR.

### Axe 5 (Sprint 15+) — Score santé réseau temps réel

Troisième livraison de `docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md` :
**KPI unique 0-100** synthétisant l'état global du réseau de mobilité
Lyon (trafic + TCL + Vélov + météo) avec redistribution automatique des
poids si une source est indisponible (évite le faux "parfait" quand
un composant tombe).

#### Ajouté
- **Migration 19** `scripts/sql/migration_019_network_health.sql` :
  - Fonction SQL `gold.fn_network_health_score()` (DROP + CREATE,
    idempotent — pas de MV car calcul stateless).
  - Formule : `100 - pct_congestion × 0.3 - pct_tcl_delayed × 0.3 -
    pct_velov_empty × 0.2 - meteo_penalty × 0.2` (poids total 1.0).
  - **Météo** : `precipitation > 5 → 15pts`, `> 1 → 8pts`,
    `temperature < 0 → 10pts`, `> 35 → 5pts`, sinon 0.
  - **Redistribution poids** : si `traffic / tcl / velov` indisponible
    (aucune donnée < 30 min), son poids est mis à 0 et le `scale` =
    `1 / somme_poids_restants` redistribue sur les sources encore UP.
  - **Diagnostic** : `healthy > 75`, `stressed > 50`, `degraded > 25`,
    sinon `critical`. Retourne aussi `traffic_available`,
    `tcl_available`, `velov_available`, `meteo_available` (booléens)
    pour le widget.
- **Helper DB** : `get_network_health_score()` dans `src/data/db_query.py`
  (pattern `_df_from_query`).
- **Wrapper fail-loud** : `load_network_health_score()` dans
  `src/data/data_loader.py` — lève `DashboardDataError` si DB indispo
  OU si la fonction SQL ne retourne aucune ligne (migration 19 pas
  appliquée).
- **Cache Streamlit** : `cached_network_health_score` (TTL 30s —
  KPI de synthèse exécutive, plus court que les autres caches).
- **Widget `dashboard/components/widgets/elu/network_health_gauge.py`** :
  - Jauge Plotly principale (`mode='gauge+number'`) 0-100 colorée
    par palier (vert > 75, jaune 50-75, orange 25-50, rouge < 25)
  - 4 sous-jauges (Trafic / TCL / Vélov / Météo) avec valeur courante
    + couleur proportionnelle au seuil
  - Bannière diagnostic ("Réseau fluide" / "Sous tension" /
    "Dégradé" / "Critique") avec timestamp
  - Bandeau "Sources indisponibles" listant les composantes down
    + explication de la redistribution des poids
  - Fail loud via DashboardDataError → `st.error(...)`
  - **Sparkline 24h** : TODO Sprint suivant (nécessite table
    `gold.network_health_history` populée par un DAG */15 min —
    V1 sans historique, la jauge principale donne déjà le temps réel)
- **Câblage page** : bandeau en haut de `dashboard/pages/Elu_1_Synthese.py`
  (juste après le titre et avant le bloc narratif `render_executive_summary`).
  Visible immédiatement à l'ouverture de la page de synthèse exécutive.
- `dashboard/components/widgets/elu/__init__.py` : export
  `render_network_health_gauge` (ajouté à `__all__`).

#### Notes
- **Min score atteignable = 17** (pas 0) avec la formule actuelle
  (`100 - 30 - 30 - 20 - 3 = 17`). Le `GREATEST(0, ...)` est une
  sécurité au cas où les poids changent.
- **Pas de recalibrage** des poids (0.3/0.3/0.2/0.2) sur données
  réelles — fait en V2 quand on aura 30 jours d'historique.

**Tests** : 290 verts (+17 nouveaux test_network_health.py :
fail loud DB indispo, fail loud résultat vide, formule 0/zéro/minimum,
redistribution poids quand source down, 8 parametrize seuils de
diagnostic, smoke widget fail loud, signature export).
Ruff clean sur les 4 fichiers du PR.

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
| `AUDIT_PRO_TCL_FIXES.md` | 14 | 100% résolus (Sprints 8+ à 11+ + cette release) |
| `AUDIT_USAGER_FIXES.md` | 16 | 100% résolus (Sprints 8+ à 11+ + cette release) |

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
  (`dpo@lyonflow.fr`). Le schéma `rgpd.audit_log` n'est pas peuplé
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
