# Sprint VPS-6 — Rapport (2026-06-11)

**Branche** : `vps` (commit `a71d039`)
**Type** : Refactor plomberie dashboard + nouveau pathfinding multimode
**Durée réelle** : ~2h wallclock (10 itérations agent, 1 session)
**Statut** : ✅ Livré, pushé, 78/78 tests verts, ruff clean

---

## Objectif

Sur le **VPS** (production), **AUCUNE donnée simulée** ne doit s'afficher.
Tout doit provenir du pipeline (PostgreSQL Gold/Silver/Bronze, Airflow,
MLflow). Un widget qui ne trouve pas sa donnée source affiche une erreur
explicite (`st.error`), pas un fallback mock silencieux.

Le dev local garde un **mode démo opt-in** (`LYONFLOW_DEMO_MODE=1`) pour
développer sans DB, faire des screenshots, préparer des démos Jedha.

## Livré (28 fichiers, +3132 / -275 lignes)

### Politique fail loud

| Fichier | Rôle |
|---------|------|
| `src/data/exceptions.py` (NEW) | Nouvelle exception `DashboardDataError(source, detail)` |
| `src/data/data_loader.py` | Helper central `_is_demo_mode()` + `_maybe_force_mock()` + `_require_db_or_raise()`. 25 `load_X()` lèvent `DashboardDataError` au lieu de servir un mock en prod. |
| `src/data/db_query.py` | 4 nouvelles fonctions SQL (`get_lieux_lyon_*`, `get_lieux_transports`, `get_cadence_for_line`) + 15 fonctions mises à jour |
| `src/data/airflow_client.py` | `get_dags_status()` lève `DashboardDataError` en prod, fallback mock uniquement en démo |
| `src/ml/mlflow_integration.py` | `list_registered_models()` lève `DashboardDataError` en prod |

### Référentiel lieux en DB (remplace `src/data/mock/lyon_addresses.py`)

| Fichier | Rôle |
|---------|------|
| `scripts/sql/create_referentiel_lieux.sql` | Table `referentiel.lieux_lyon` (21 lieux GPS emblématiques) |
| `scripts/sql/create_referentiel_transports.sql` | Table `referentiel.lieux_transports` (N-N lieu × ligne TCL, ~50 liaisons seedées à la main avec connaissance du réseau) |
| `scripts/sql/create_lieux_calendrier.sql` | Table `referentiel.lieux_calendrier` + vues `v_cadence_observed_7d` + `v_cadence_summary` |
| `scripts/seed_lieux_calendrier.py` | Idempotent, calcule les cadences depuis `gold.tcl_vehicle_realtime` + `bronze.calendrier_scolaire` + `bronze.jours_feries` |

### Pathfinding multimode

| Fichier | Rôle |
|---------|------|
| `scripts/sql/create_pathfinder_helpers.sql` | Fonctions SQL : `haversine_m`, `nearest_velov_stations`, `nearest_traffic_nodes`, `predicted_speed_for_node`, `estimate_car_trip`, `estimate_velov_trip` |
| `src/routing/pathfinder_multimodal.py` (NEW) | `plan_velov_trip()` (3 segments : marche → Vélov → marche) + `plan_car_trip()` (wrapper `compute_itinerary` avec fail loud) |
| `dashboard/components/widgets/usager/velov_trip.py` (NEW) | Widget Folium : carte avec polylines colorées (gris pointillé marche, bleu Vélov) + markers stations Vélov avec vélos/docks dispo |

### Widgets démoctisés (8 fichiers)

| Fichier | Changement |
|---------|-----------|
| `dashboard/components/widgets/pro_tcl/pipeline_management.py` | Bandeau "🟡 mode demo" → `DashboardDataError` → `st.error` en prod. Mock `MOCK_DAGS`/`MOCK_FRESHNESS` conservé uniquement en démo |
| `dashboard/components/widgets/pro_tcl/model_monitoring.py` | `MOCK_MODELS` hardcodé → fallback mock uniquement en démo. Prod : `DashboardDataError` |
| `dashboard/components/widgets/pro_tcl/network_map.py` | `ALL_BUSES` mock → fallback uniquement en démo. Prod : `st.info("Aucun bus en circulation")` si table vide, sinon live |
| `dashboard/components/widgets/pro_tcl/segment_table.py` | `SEGMENTS` mock → fallback démo uniquement. `DIAGNOSIS_LABELS` conservé (libellé FR d'un code SQL, pas une métrique inventée) |
| `dashboard/components/widgets/pro_tcl/correlation_matrix.py` | Idem segment_table |
| `dashboard/components/widgets/usager/weather_widget.py` | `MOCK_WEATHER` → fallback démo uniquement |
| `dashboard/components/widgets/usager/itinerary.py` | Résolution d'adresse via `referentiel.lieux_lyon` en DB au lieu de `mock.lyon_addresses.resolve_address` |
| `dashboard/Accueil.py` | Compteurs hardcodés `or 118` / `or 458` supprimés. Si DB indispo → `st.error` |

### Page Mon Trajet

`dashboard/pages/Usager_1_Mon_Trajet.py` : section "Recommandations
multimodales (mock)" → "Trajet Vélov + voiture sur carte" (100% pipeline).
Plus de `MOCK_TRIP_RESULTS["default"]` ni de liste d'options mock.

### Tests

| Fichier | Tests |
|---------|-------|
| `tests/data/test_no_mock_vps_policy.py` (NEW) | **35 tests** : mode prod fail loud (19 load_X testées + helpers) + mode démo fallback + `DashboardDataError` + `is_demo_mode` |
| `tests/data/test_db_query_and_data_loader.py` | Adapté pour mode démo (fixture `enable_demo_mode` qui set `LYONFLOW_DEMO_MODE=1`) |

**Total** : 78/78 tests verts. **Ruff** : all clean sur tous les nouveaux fichiers
(scripts/, src/data/, src/routing/, src/ml/, dashboard/widgets, dashboard/pages,
dashboard/Accueil.py, tests/data/).

### Documentation

| Fichier | Mise à jour |
|---------|-------------|
| `AGENTS.md` | 2 nouvelles règles strictes (#7 zéro mock, #8 référentiel lieux en DB) |
| `CLAUDE.md` | Section Sprint VPS-6 dans le statut, 2 nouvelles règles projet, version bumped |
| `docs/DASHBOARD_PAGES.md` | Section "Mode démo vs Mode production" en tête, `Usager_1_Mon_Trajet` doc revue (Vélov + voiture) |
| `docs/RUNBOOK.md` | Section "Diagnostic Sprint VPS-6 (fail loud)" avec procédure de récupération |
| `docs/PROJECT_STATUS_AND_GOALS.md` | Section 1 mise à jour avec VPS-6 (fail loud, référentiel lieux, pathfinding) |
| `docs/PLAN_NO_MOCK_VPS.md` | Plan complet, statut ✅ TERMINÉ, section 8 "Comment tester en local" |
| `SPRINT_VPS-6_REPORT.md` (NEW) | Ce rapport |
| `.env.example` | Nouvelle variable `LYONFLOW_DEMO_MODE=0` documentée |
| `scripts/check-deploy-env.sh` | Bloque le deploy si `LYONFLOW_DEMO_MODE != 0` |

## Procédure de déploiement

1. **Migrations SQL** (idempotentes, peuvent être rejouées) :
   ```bash
   ssh -i ~/.ssh/lyonflow_deploy ubuntu@51.83.159.224
   cd /opt/lyonflow
   for sql in scripts/sql/create_referentiel_lieux.sql \
              scripts/sql/create_referentiel_transports.sql \
              scripts/sql/create_lieux_calendrier.sql \
              scripts/sql/create_pathfinder_helpers.sql; do
       PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB -f $sql
   done
   python scripts/seed_lieux_calendrier.py
   ```

2. **Vérifier `.env` du VPS** contient `LYONFLOW_DEMO_MODE=0` :
   ```bash
   ssh ... "grep LYONFLOW_DEMO_MODE /opt/lyonflow/.env"
   ```

3. **Deploy** :
   ```bash
   make check-deploy-env
   make deploy-vps
   make healthcheck-vps
   ```

4. **Smoke test** : ouvrir `https://51.83.159.224/dashboard/`, aller sur
   "Mon trajet" (Usager), vérifier que le widget Vélov affiche la carte
   avec les polylines colorées et les markers stations.

## Sprint 7+ (Sprint backlog)

- [ ] **DAG Airflow `refresh_lieux_calendrier`** quotidien 5h pour recalculer
  les cadences automatiquement (remplace le lancement manuel)
- [ ] **Ingestion GTFS** (stops.txt, routes.txt, trips.txt, stop_times.txt)
  via Overpass API ou open-data-grand-lyon.fr → vrai A* routier avec sens
  de circulation + travel times théoriques
- [ ] **Vue matérialisée `gold.mv_line_kpis_live`** → démoctiser
  `load_line_kpis` (passer en lecture SQL)
- [ ] **Table `user_favorites`** + `gold.recommendations` → démoctiser
  Mes Favoris et la reco multimodale de Mon Trajet
- [ ] **Test d'intégration `tests/integration/test_fail_loud_e2e.py`**
  qui démarre un PostgreSQL en container et vérifie que les load_X()
  lèvent bien `DashboardDataError` quand la DB est arrêtée
- [ ] **Refacto `xgboost_speed.py` / `xgboost_velov.py`** (dette schéma
  v0.3.1 — déjà mentionnée dans AGENTS.md mais non bloquante)

## Métriques

| Métrique | Avant | Après |
|----------|-------|-------|
| Lignes mock dans le code (fallback silent) | ~200 | 0 (toutes gardent le mode démo derrière `_is_demo_mode()`) |
| Fichiers avec `force_mock` hardcodé silencieux | 25+ | 0 |
| Tests fail loud | 0 | 35 |
| Widgets avec carte | 1 (voiture) | 2 (voiture + Vélov) |
| Lieux en DB | 0 (mock statique) | 21 (référentiel) |
| Cadences observables | 0 (inventées) | Calculées depuis 7j glissants |

## Crédits

- **Sprint owner** : Patrice DUCLOS + Claude (Mavis)
- **Stack modifiée** : PostgreSQL 16, Streamlit 1.x, Folium, NetworkX
- **Refs** : Plan détaillé [docs/PLAN_NO_MOCK_VPS.md](PLAN_NO_MOCK_VPS.md)
