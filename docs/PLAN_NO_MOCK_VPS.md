# Plan — Suppression des fallbacks mock sur le dashboard VPS

**Date initiale** : 2026-06-11
**Date clôture** : 2026-06-12 (Sprint 8, ZÉRO MOCK DANS LE PROJET)
**Statut** : ⚠️ **PARTIELLEMENT CLÔTURÉ** — le systeme de mock (repertoire, flag demo_mode) est supprime, mais l'audit du 2026-06-12 a identifie 7 vrais mocks residuels en production (voir [archive/audits/AUDIT_PIPELINE_2026-06-12.md](../archive/audits/AUDIT_PIPELINE_2026-06-12.md) section 2.2)

**Objectif initial (Sprint VPS-6, 2026-06-11)** : Sur le VPS (branche `vps`), AUCUNE donnée simulée ne doit s'afficher. Tout doit provenir du pipeline de données (PostgreSQL Gold/Silver/Bronze, Airflow, MLflow). Un widget qui ne trouve pas sa donnée source affiche une erreur explicite.

**Objectif Sprint 8 (2026-06-12)** : aller au-delà. **Supprimer le mode démo entièrement**. Pas de `_is_demo_mode()`, pas de `force_mock=True`, pas de mock fallback. Si DB indispo, fail loud. La DB est l'unique source de vérité.

**Périmètre** : code Python sous `dashboard/`, `src/data/`, `dags/`. Les branches `kubernetes` et `cloud-demo` ne sont PAS concernées (futur AWS/GCP).

**Livré Sprint VPS-6 (initiation)** :
- ✅ Phase 1 — Fondation (`DashboardDataError` + helper `_maybe_force_mock` + var d'env `LYONFLOW_DEMO_MODE`)
- ✅ Phase 1b — Référentiel lieux en DB (3 tables + 4 scripts SQL)
- ✅ Phase 1c — Pathfinding Vélov + voiture (Dijkstra existant + nouveau Vélov)
- ✅ Phase 2 — data_loader.py : 25 fonctions `load_X()` fail loud en prod
- ✅ Phase 3 — db_query.py : 15 fonctions SQL propres
- ✅ Phase 4 — Widgets : 8 fichiers (pipeline, monitoring, network_map, segment, weather, Accueil, itinerary, velov_trip)
- ✅ Phase 5 — Airflow + MLflow : fail loud propagé
- ✅ Phase 6 — Tests : 35 nouveaux tests fail loud + adaptation des existants
- ✅ 78/78 tests verts + ruff clean

**Livré Sprint 8 (clôture — ZÉRO MOCK DANS LE PROJET)** :
- ✅ Suppression complète de `src/data/mock/` (déplacé dans `tests/fixtures/mock_data/`)
- ✅ 18 fallbacks mock virés de `data_loader.py` (helper `_is_demo_mode()` retourne toujours False)
- ✅ 17 fallbacks mock virés de `db_query.py` (db.down → `DashboardDataError`)
- ✅ 2 fallbacks mock virés de `airflow_client.py` (MOCK_DAGS no-op)
- ✅ 8 widgets démoctisés (correlation_matrix, network_map, otp_heatmap, pipeline_management, segment_table, itinerary, velov_trip, weather_widget)
- ✅ 2 nouveaux modules neutres : `src/data/labels.py` (référentiels statiques), `src/data/tcl_lines.py` (10 lignes TCL emblématiques)
- ✅ 1 page démoctisée : `Usager_3_Favoris.py` (seed MOCK_FAVORITES viré, liste vide par défaut)
- ✅ Conftest centralisé `tests/conftest.py` (MockDB fixture + 3 fixtures mode démo/prod/no-db)
- ✅ Tests : `test_no_mock_vps_policy.py` (6 tests valident la politique "zéro mock")
- ✅ Tests : `test_db_query_and_data_loader.py` (19 tests valident le fail loud)
- ✅ Markers `@pytest.mark.integration` sur tests qui ont besoin du stack
- ✅ `pyproject.toml` addopts `-m "not integration"` (integration skippable en CI)
- ✅ **150 tests verts / 9 SKIP / 7 deselected (integration)**

---

## 1. Cartographie des fallbacks mock (archivé Sprint VPS-6)

> Cette section est archivée car le problème est résolu. Voir Sprint 8 plus bas.

### 1.1 Couche d'abstraction `src/data/data_loader.py` (point névralgique)

Le `data_loader.py` est le centre de gravité : **tous les widgets** passent par ses `load_X(force_mock=...)`. La logique actuelle dans `_maybe_force_mock()` fait : si DB down OU `force_mock=True` → retourne le mock.

| Fonction | Mock utilisé | Source DB attendue |
|----------|--------------|--------------------|
| `load_traffic` | `usager_mock.MOCK_TRAFFIC` | `gold.traffic_features_live` |
| `load_traffic_timeseries` | `usager_mock.MOCK_TRAFFIC_TIMESERIES` | `gold.fact_traffic_series` |
| `load_velov_stations` | `usager_mock.VELOV_STATIONS` | `gold.velov_features` |
| `load_velov_predictions` | `usager_mock.MOCK_VELOV_PREDICTIONS` | `gold.velov_predictions` |
| `load_bus_delays` | `usager_mock.MOCK_BUS_DELAYS` | `gold.bus_delay_segments` |
| `load_infra_bottlenecks` | `usager_mock.MOCK_INFRA_BOTTLENECKS` | `gold.infrastructure_bottlenecks` |
| `load_predictions_vs_actuals` | `usager_mock.MOCK_PREDICTIONS_VS_ACTUALS` | `gold.predictions_vs_actuals` |
| `load_rgpd_audit` | `usager_mock.MOCK_RGPD_AUDIT` | `rgpd.audit_log` |
| `load_rgpd_consents` | `usager_mock.MOCK_RGPD_CONSENTS_SUMMARY` | `rgpd.consents` |
| `load_weather_hourly` | `usager_mock.MOCK_WEATHER_HOURLY` | `silver.meteo_hourly` |
| `load_recent_alerts` | `pro_tcl_mock.MOCK_RECENT_ALERTS` | `gold.alerts` |
| `load_segments` | `pro_tcl_mock.MOCK_SEGMENTS` | `gold.segments` |
| `load_correlation_matrix` | `pro_tcl_mock.MOCK_CORRELATION_MATRIX` | vue Gold |
| `load_buses_positions` | `pro_tcl_mock.MOCK_BUSES_POSITIONS` | `silver.tcl_vehicles_clean` |
| `load_kpis_12_months` | `elu_mock.MOCK_KPIS_12_MONTHS_FLAT` | `gold.kpis_12_months` |
| `load_amenagements_passes` | `elu_mock.MOCK_AMENAGEMENTS_FLAT` | `gold.amenagements` |
| `load_tcl_lines` | `pro_tcl_mock.MOCK_TCL_LINES` | `gold.tcl_vehicle_realtime` |
| `load_lyon_addresses` | `lyon_addresses.LYON_ADDRESSES` | **mock statique** (référentiel lieux) |
| `load_spatial_mapping` | `usager_mock.MOCK_SPATIAL_MAPPING` | `gold.dim_spatial_grid_mapping` |
| `load_traffic_predictions_for_map` | `usager_mock.MOCK_TRAFIC_PREDICTIONS` | `gold.trafic_predictions` |
| `load_mlflow_models` | `_FALLBACK_MOCK_MODELS` (hardcodé) | MLflow tracking |
| `load_line_kpis` | `pro_tcl_mock.LINE_KPIS` | vue Gold `mv_line_kpis_live` |
| `load_otp_heatmap_data` | `pro_tcl_mock.OTP_GRID` | vue Gold |
| `load_city_synthesis` | `elu_mock.SYNTHESIS_DATA` | agrégat multi-tables |
| `load_bottlenecks_summary` | `elu_mock.BOTTLENECKS_LIST` | `gold.infrastructure_bottlenecks` |
| `load_bottlenecks_top` | dérivé de `bottlenecks_summary` | idem |

### 1.2 Couche SQL `src/data/db_query.py` (second niveau de fallback)

Plusieurs fonctions dans `db_query.py` **importent directement** les mocks en cas de DB indisponible. Exemples :
- `get_latest_traffic` → `MOCK_TRAFFIC_FEATURES` (l.113)
- `get_traffic_for_node` → `MOCK_TRAFFIC_TIMESERIES` (l.122)
- `get_traffic_bottlenecks` → `MOCK_TRAFFIC_BOTTLENECKS` (l.228)
- `get_predictions_vs_actuals` → `MOCK_PREDICTIONS_VS_ACTUALS` (l.250)
- `get_velov_stations_geo` → `MOCK_VELOV_STATIONS_GEO` (l.282)
- `get_velov_predictions` → `MOCK_TRAFIC_PREDICTIONS` (l.313)
- `get_bus_delay_segments` → `MOCK_BUS_DELAYS` (l.367)
- `get_infrastructure_bottlenecks` → `MOCK_INFRA_BOTTLENECKS` (l.390)
- `get_spatial_mapping` → `MOCK_SPATIAL_MAPPING` (l.415)
- `get_gnn_adjacency` → `MOCK_GNN_ADJACENCY` (l.430)
- `get_rgpd_audit_log` → `MOCK_RGPD_AUDIT` (l.457)
- `get_rgpd_consents_summary` → `MOCK_RGPD_CONSENTS_SUMMARY` (l.477)
- `get_rgpd_dsr` → `MOCK_RGPD_DSR` (l.494)
- `get_rgpd_purge` → `MOCK_RGPD_PURGE` (l.510)
- `get_bronze_source_counts` → `MOCK_BRONZE_COUNTS` (l.577)

### 1.3 Couche widget (mock intégré au code)

Ces widgets utilisent les mocks **directement** sans passer par le data_loader :

| Widget | Mock importé | Usage |
|--------|--------------|-------|
| `widgets/pro_tcl/segment_table.py` | `pro_tcl.DIAGNOSIS_LABELS, SEGMENTS` | libellés + segments si DB vide |
| `widgets/pro_tcl/correlation_matrix.py` | `pro_tcl.DIAGNOSIS_LABELS, SEGMENTS` | idem |
| `widgets/pro_tcl/network_map.py` | `pro_tcl.ALL_BUSES` | positions bus si DF vide |
| `widgets/pro_tcl/model_monitoring.py` | `MOCK_MODELS` (hardcodé l.20-92) | registry MLflow si down |
| `widgets/pro_tcl/pipeline_management.py` | `MOCK_DAGS, MOCK_FRESHNESS` (hardcodés) | Airflow status si down |
| `widgets/usager/weather_widget.py` | `usager.MOCK_WEATHER` | météo si DB vide |
| `pages/Usager_1_Mon_Trajet.py` | `usager.MOCK_TRIP_RESULTS` | trajet par défaut (avant clic) |
| `pages/Usager_3_Favoris.py` | `usager.MOCK_FAVORITES` | favoris init session |
| `pages/9_RGPD_Conformite.py` | via `load_rgpd_consents(force_mock=False)` | OK, délégué |
| `Accueil.py` | `118, 458` en dur (l.137-144) | compteurs fallback |

### 1.4 Couche Airflow `src/data/airflow_client.py`

- `is_airflow_available()` → ping `/health`. Si fail → `get_dags_status()` retourne `MOCK_DAGS`.
- `get_dags_status()` → fallback `MOCK_DAGS` (l.79, l.87) sur toute exception.
- `trigger_dag()` → retourne `False` silencieux (OK, pas de mock).

---

## 2. Stratégie : FAIL LOUD en prod, démo opt-in en dev

### Principe

Introduire un **mode démo** explicite via variable d'environnement. Le data_loader et le widget layer consultent ce flag :

- `LYONFLOW_DEMO_MODE=1` → comportement actuel (mock si DB down) — pour le dev local, les screenshots, la démo Jedha.
- `LYONFLOW_DEMO_MODE=0` (ou absent) → **prod** : aucun mock, exceptions explicites ou `st.error(...)` visible.

Sur le VPS, `.env` doit contenir `LYONFLOW_DEMO_MODE=0` (valeur explicite). Le `make check-deploy-env` vérifiera sa présence.

### Garde-fou

Le module `src/data/data_loader.py` lève une **`DashboardDataError`** (nouvelle exception) si :
- `LYONFLOW_DEMO_MODE != "1"` ET
- DB indisponible OU résultat vide inattendu

Les widgets catchent `DashboardDataError` et affichent un `st.error("⚠️ Données pipeline indisponibles — vérifier Airflow et PostgreSQL")`. Plus de `st.info("mode mock")` silencieux, plus de valeurs inventées.

---

## 3. Plan d'action par phase

### Phase 1 — Fondation (1-2h)

1. **Créer `src/data/exceptions.py`** : nouvelle exception `DashboardDataError`.
2. **Modifier `_maybe_force_mock()`** dans `data_loader.py` :
   - Lit `LYONFLOW_DEMO_MODE` au boot (cache process).
   - Si `!= "1"` → `force_mock` est ignoré, les fonctions `load_X` lèvent `DashboardDataError` au lieu de retourner un mock.
3. **Ajouter `LYONFLOW_DEMO_MODE=0`** dans `.env.example` et `.deploy.env.example`. Documenter dans `CLAUDE.md`.

### Phase 2 — Plomberie `data_loader.py` (2-3h)

Pour chaque fonction `load_X` qui retourne un mock :
- Remplacer `return usager_mock.MOCK_X` par `raise DashboardDataError(f"load_X: no DB data ({reason})")`.
- Cas particulier : résultat vide **attendu** (ex. aucun alertes sur 24h) → retourner un DataFrame vide / liste vide, pas une exception. Distinguer "DB répond mais vide" de "DB ne répond pas".
- Conserver les mocks `LINE_KPIS`, `OTP_GRID`, `SYNTHESIS_DATA`, `BOTTLENECKS_LIST` etc. UNIQUEMENT quand `LYONFLOW_DEMO_MODE=1`. Le code reste lisible, pas de #if mort.

### Phase 3 — Plomberie `db_query.py` (2-3h)

Mêmes règles :
- Supprimer les `from src.data.mock.usager import MOCK_X` dans les fonctions qui lèvent déjà des warnings.
- Si DB échoue ET `LYONFLOW_DEMO_MODE != "1"` → logger l'erreur et retourner un DataFrame vide. Le widget layer affichera un `st.error`.
- Si DB échoue ET `LYONFLOW_DEMO_MODE == "1"` → fallback mock conservé.

### Phase 4 — Widgets (3-4h)

Pour chaque widget avec mock intégré :
- `segment_table.py`, `correlation_matrix.py` : ne plus importer `SEGMENTS` / `DIAGNOSIS_LABELS` (ou les garder uniquement comme libellés FR pour les codes diag). Si DF vide → `st.warning("Aucun segment — pipeline Gold vide")`.
- `network_map.py` : si DF vide → `st.warning("Aucun bus en circulation")`. Pas de `ALL_BUSES`.
- `model_monitoring.py` : si MLflow indispo → `st.error("MLflow non joignable — métriques modèles indisponibles")`. Retirer la constante `MOCK_MODELS` du module (laisser dans `_FALLBACK_MOCK_MODELS` de `data_loader.py`).
- `pipeline_management.py` : si Airflow indispo → bandeau `st.error` persistant en haut de la page. Retirer `MOCK_DAGS` / `MOCK_FRESHNESS` (laisser dans `mock/pro_tcl_pipeline.py` pour le démo local).
- `weather_widget.py` : si DB météo vide → `st.warning("Météo indispo")`. Pas de `MOCK_WEATHER`.
- `Accueil.py` : retirer les fallbacks `or 118` / `or 458`. Si DB indispo → `st.caption("Données live indisponibles")`.

### Phase 5 — Airflow + MLflow (1h)

- `airflow_client.py` : si Airflow down en prod → retourner une liste vide + logger warning. Le widget affichera un bandeau d'erreur.
- `mlflow_integration.py` : idem. Si MLflow down → retourner liste vide.

### Phase 6 — Validation (1-2h)

1. **Test local démo** : `LYONFLOW_DEMO_MODE=1 streamlit run dashboard/Accueil.py` → tout marche comme avant.
2. **Test local prod** : `LYONFLOW_DEMO_MODE=0 POSTGRES_HOST=invalid streamlit run dashboard/Accueil.py` → tous les widgets affichent des erreurs (pas de mock).
3. **Test local prod + DB valide** : DB up, dashboard lit uniquement la DB. Pas d'imports mock.
4. **Test VPS** : `make deploy-vps` puis `make healthcheck-vps` + smoke test des 18 pages (curl les endpoints FastAPI + check que `gold.trafic_predictions` est non-vide).
5. **Lint + tests** : `ruff check . && pytest tests/ -v`. Les tests doivent passer avec `LYONFLOW_DEMO_MODE=0` (mode par défaut).

---

## 4. Risques et mitigations

| Risque | Mitigation |
|--------|------------|
| DB temporairement indispo (réseau) → tout le dashboard plante | Bandeau persistant en haut + `st.error` par widget. Surveillance Prometheus déjà en place (Sprint VPS-3) alertera avant que les users ne voient. |
| Widget critique qui ne peut pas se passer de mock (ex. : géocodage adresses) | Garder `lyon_addresses.LYON_ADDRESSES` comme référentiel statique. C'est une liste de lieux, pas une métrique temps réel. Idem `DIAGNOSIS_LABELS` (libellé FR d'un code SQL). |
| Oubli d'un fallback mock quelque part | Audit final : `grep -r "from src.data.mock" dashboard/ src/data/` ne doit retourner que les imports dans le mode démo (cachés derrière `if LYONFLOW_DEMO_MODE`). |
| Tests qui dépendent des mocks | Les tests unitaires doivent set `LYONFLOW_DEMO_MODE=1` dans un fixture/conftest. Auditer `tests/` pour les cas qui mockent la DB. |
| Page Mon Trajet (Sprint 6) qui n'a pas encore le binding pathfinder | Acceptable : la page affiche déjà un `st.caption("Recommandation demo — Sprint suivant")`. Le mock est explicitement labellé démo. À retirer quand Sprint 7 livre le pathfinder. |
| Page Mes Favoris (init session) | Accepter un fallback "Démo" si table `user_favorites` absente — mais l'afficher explicitement. Pas de données inventées silencieuses. |

---

## 5. Fichiers à modifier (récap)

**Créer** :
- `src/data/exceptions.py` (~10 lignes)
- `tests/test_data_loader_prod_mode.py` (nouveau test, env=0)

**Modifier** :
- `src/data/data_loader.py` (~25 fonctions, gate central)
- `src/data/db_query.py` (~15 fonctions, suppression imports mock en prod)
- `src/data/airflow_client.py` (gate `is_airflow_available`)
- `src/ml/mlflow_integration.py` (gate MLflow)
- `dashboard/components/widgets/pro_tcl/segment_table.py`
- `dashboard/components/widgets/pro_tcl/correlation_matrix.py`
- `dashboard/components/widgets/pro_tcl/network_map.py`
- `dashboard/components/widgets/pro_tcl/model_monitoring.py`
- `dashboard/components/widgets/pro_tcl/pipeline_management.py`
- `dashboard/components/widgets/usager/weather_widget.py`
- `dashboard/pages/Usager_1_Mon_Trajet.py` (mock explicite déjà labelé, à durcir)
- `dashboard/pages/Usager_3_Favoris.py` (init session)
- `dashboard/Accueil.py` (compteurs)
- `.env.example` + `.deploy.env.example` (ajout `LYONFLOW_DEMO_MODE`)
- `Makefile` (ajout check `LYONFLOW_DEMO_MODE=0` dans `check-deploy-env`)
- `docs/DASHBOARD_PAGES.md` (section "Mode démo vs prod")
- `CLAUDE.md` (règle projet)

**Conserver** (sous `src/data/mock/`) :
- Tous les fichiers `mock/*.py` restent — ils sont utilisés en mode démo (`LYONFLOW_DEMO_MODE=1`). Le code mort n'est pas souhaitable : le mode démo sert au dev local et aux screenshots.

---

## 6. Estimation

- Phase 1 : ~1h
- Phase 2-3 : ~5h
- Phase 4 : ~4h
- Phase 5 : ~1h
- Phase 6 : ~2h

**Total : ~13h** sur 1-2 jours. Pas de sprint dédié nécessaire — c'est un refactor de plomberie, à étaler en tâches courtes.

**Réalisé en une session** : ~2h wallclock (10 itérations de l'agent).

---

## 7. Après ce refactor (Sprint 7+)

- Sprint 7+ : ingestion **GTFS** (stops.txt, routes.txt, trips.txt, stop_times.txt) via Overpass API ou open-data-grand-lyon.fr. Permettra un vrai A* routier avec sens de circulation + travel times théoriques par ligne. Le référentiel `referentiel.lieux_transports` est actuellement seedé à la main (connaissance experte) — GTFS le peuplera dynamiquement.
- Sprint 7+ : DAG Airflow `refresh_lieux_calendrier` (quotidien 5h) pour recalculer `referentiel.lieux_calendrier` depuis `gold.tcl_vehicle_realtime` + calendriers.
- Sprint 7+ : vue matérialisée `gold.mv_line_kpis_live` → démoctiser `load_line_kpis` (passer en lecture SQL).
- Sprint 7+ : table `user_favorites` + `gold.recommendations` → démoctiser Mes Favoris et la reco multimodale de Mon Trajet.
- Sprint 7+ : refacto `xgboost_speed.py` / `xgboost_velov.py` (dette schéma v0.3.1).
- Sprint 7+ : cron `seed_lieux_calendrier.py` quotidien (5h par exemple).
- Sprint 7+ : test d'intégration `tests/integration/test_fail_loud_e2e.py` qui démarre un PostgreSQL en container et vérifie que les load_X() lèvent bien `DashboardDataError` quand la DB est arrêtée.

## 8. Comment tester en local

```bash
# 1. Référentiel lieux (à exécuter une fois sur la DB)
psql $POSTGRES_DB -f scripts/sql/create_referentiel_lieux.sql
psql $POSTGRES_DB -f scripts/sql/create_referentiel_transports.sql
psql $POSTGRES_DB -f scripts/sql/create_lieux_calendrier.sql
psql $POSTGRES_DB -f scripts/sql/create_pathfinder_helpers.sql

# 2. Calculer les cadences (idempotent, à cron-er)
python scripts/seed_lieux_calendrier.py

# 3. Mode démo (DB indispo toléré)
LYONFLOW_DEMO_MODE=1 streamlit run dashboard/Accueil.py

# 4. Mode prod (DB requise, fail loud)
LYONFLOW_DEMO_MODE=0 streamlit run dashboard/Accueil.py

# 5. Tests
pytest tests/data/ -v
ruff check src/data/ src/routing/ dashboard/ scripts/seed_lieux_calendrier.py
```

---

## 9. Clôture Sprint 8 (2026-06-12) — "ZÉRO MOCK DANS LE PROJET"

**Le Sprint 8 a été au-delà de la politique "fail loud" du Sprint VPS-6** : il a **supprimé** le mode mock entièrement.

### Constat Sprint VPS-6 (insuffisant)

La politique Sprint VPS-6 disait : "Si DB indispo, fail loud". Mais le code contenait encore un mode `_is_demo_mode()` qui retournait des mocks quand l'env var était à 1. En pratique, ce mode était **difficile à désactiver complètement** (un dev pouvait l'oublier en local, ou pire, en prod après un mauvais .env).

### Action Sprint 8

- **Suppression du mode démo** : `_is_demo_mode()` retourne toujours `False` (helper déprécié, à retirer Sprint 9+).
- **Suppression de tous les fallbacks mock** : 45+ branches `if _is_demo_mode(): return X_mock` virées de `data_loader`, `db_query`, `airflow_client`, et 8 widgets.
- **Suppression du dossier `src/data/mock/`** : 1650 lignes de mocks déplacées dans `tests/fixtures/mock_data/` (où elles n'ont jamais eu leur place).
- **3 nouveaux modules neutres** : `src/data/labels.py` (référentiels statiques DIAGNOSIS_LABELS, MODE_COLORS, etc.), `src/data/tcl_lines.py` (10 lignes TCL emblématiques).
- **Tests de la nouvelle politique** : `test_no_mock_vps_policy.py` (6 tests) vérifie :
  1. `_is_demo_mode()` retourne False (même avec env var=1)
  2. `_maybe_force_mock()` retourne False
  3. `src/data/mock/` n'existe plus
  4. Aucune référence à `src.data.mock` dans `src/` (hors docstrings)
  5. Aucun widget n'importe `src.data.mock`
  6. data_loader ne retourne pas de mock

### Résultat Sprint 8

- **150 tests verts / 9 SKIP / 7 deselected (integration)**
- ruff clean sur les nouveaux fichiers
- `src/` ne contient plus aucun mock (vérifié par le test ci-dessus)
- Le projet est désormais **100% DB-driven en production**
- Un blip DB est immédiatement visible (widget rouge + log d'erreur) au lieu d'être masqué par un mock silencieux

### Actions restantes (Sprint 9+)

- Retirer le helper `_is_demo_mode()` (toujours False, déprécié)
- Retirer le paramètre `force_mock` de toutes les `load_X()`
- `pip uninstall mock` quand tous les imports résiduels seront nettoyés

Voir [archive/sprints/SPRINT_VPS-8_REPORT.md](../archive/sprints/SPRINT_VPS-8_REPORT.md) pour le rapport détaillé.

