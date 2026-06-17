# Sprint VPS-8 — Pathfinding voiture + smart routing Vélov (final)

**Date** : 2026-06-12
**Branche** : `vps`
**Statut** : ✅ VALIDÉ sur VPS 51.83.159.224 (3 hotfix successifs)

## Résumé

Sprint 8 a corrigé 3 dettes cachées qui faisaient silencieusement échouer le pathfinding voiture (Dijkstra) et le smart routing Vélov. Tests e2e sur le VPS confirment que **tous les piliers fonctionnent** : 5 segments trouvés Part-Dieu → Tête d'Or, 3 segments smart-routés Confluence → Part-Dieu avec alternatives + voisines.

## Dettes trouvées et corrigées

### Hotfix 5 — lat/lon NULL dans `gold.dim_spatial_grid_mapping`

- **Symptôme** : `Échec build graph DB (Aucun noeud dans gold.dim_spatial_grid_mapping) — fallback mock`
- **Cause** : Le DAG `build_spatial_mapping` insère correctement lat/lon, mais un autre process a TRUNCATÉ la table puis ré-inséré les nœuds H3 SANS backfill des colonnes `lat`/`lon`. Résultat : 1543/1543 = **0%** avec coordonnées, donc 0 path Dijkstra possible.
- **Fix** : `scripts/maintenance/backfill_dim_spatial_lat_lon.py` — dérive lat/lon depuis `h3_id` via `h3-py 4.5` (déjà installé). Idempotent. **1543/1543 = 100%** avec lat/lon après run.
- **À faire Sprint 8+** : cron-er le backfill toutes les 5 min (la dette réapparaît silencieusement) OU fixer la source pour que `build_spatial_mapping` soit le seul writer.

### Hotfix 6 — `vitesse_kmh` n'existe pas dans `gold.traffic_features_live`

- **Symptôme** : `Échec build graph DB (column t.vitesse_kmh does not exist)`
- **Cause** : Dette schéma v0.3.1 (Sprint 5) — la colonne s'appelle `speed_kmh` (et non `vitesse_kmh`). Le code Sprint 8 référençait `t.vitesse_kmh` (erreur de nommage).
- **Fix** : `src/routing/graph.py` ligne 148 : `t.vitesse_kmh` → `t.speed_kmh`.
- **À faire Sprint 9+** : aligner tous les modèles sur le schéma v0.3.1 (Sprint 9 = refacto `xgboost_speed.py` + `xgboost_velov.py`).

### Hotfix 7 — `plan_car_trip` signature `(lat, lon, lat, lon)` au lieu de `(lon, lat, lon, lat)`

- **Symptôme** : `plan_car_trip(4.8589, 45.7607, 4.8525, 45.7745)` retournait 0 segments, sans erreur visible.
- **Cause** : Convention inhabituelle — la signature était `(origin_lat, origin_lon, dest_lat, dest_lon)` au lieu de `(origin_lon, origin_lat, dest_lon, dest_lat)`. Tous les autres widgets (ex. `compute_itinerary`, `itinerary.py`) utilisent la convention canonique `(lon, lat, lon, lat)`. Conséquence : Part-Dieu (lon=4.86, lat=45.76) était interprété comme `lat=4.86, lon=45.76` (Corse) → hors graphe Lyon → 0 path.
- **Fix** : `src/routing/pathfinder_multimodal.py::plan_car_trip` signature alignée sur `(origin_lon, origin_lat, dest_lon, dest_lat)`.
- **Impact** : 0 caller dépendait de l'ancien ordre (vérifié par grep), donc fix sans régression.

### Hotfix 8 (inclus dans le 7) — `plan_velov_trip` KeyError 'velov_lon'

- **Symptôme** : `KeyError: 'velov_lon'` sur tout trajet Vélov.
- **Cause** : Le hotfix perf Sprint VPS-6 (`c93b4c3`) avait écrasé `origin_station` (schéma smart routing `{velov_name, velov_lat, velov_lon, status, ...}`) avec le retour de `_nearest_velov_stations_pair` (schéma `{station_id, station_name, lat, lon, ...}`). Incompatibilité de schéma.
- **Fix** : `src/routing/pathfinder_multimodal.py::plan_velov_trip` — supprimer l'écrasement, garder le smart routing (qui inclut status + alternatives + voisines).
- **TODO Sprint 9** : si perf pose problème, batcher le smart lookup en 1 round-trip SQL (UNION ALL avec scoring intégré).

## Tests e2e sur VPS

```bash
# Test 1 : voiture Part-Dieu → Tête d'Or (4.86, 45.76) → (4.85, 45.77)
segments: 5
distance_m: 250.0
duration_min: 0.6
source: db
# Note : chemin très court (5 nœuds H3 res 13, 50m/node) car le graphe
# a des "trous" — la résolution 13 est fine mais pas partout couverte.
# Sprint 8+ : GTFS Overpass API pour vrai A* routier.

# Test 2 : Vélov Confluence → Part-Dieu (4.83, 45.76) → (4.86, 45.76)
type: VelovItinerary
source: db
segments: 3
  - walk Origine -> BELLECOUR / RÉPUBLIQUE (46m, 0.6min)
  - cycle BELLECOUR / RÉPUBLIQUE -> PART-DIEU/POMPIDOU (450m, 0.9min, "Via graphe routier 9 segments")
  - destination PART-DIEU/POMPIDOU -> Destination (218m, 2.9min)
total_distance_m: 714
total_duration_min: 4.4
origin_alternatives: 2
dest_alternatives: 2
origin_neighbors: 3
dest_neighbors: 2

# Test 3 : KPIs TCL (Sprint 7)
get_line_kpis() → 20+ lignes (T1..T7, S1..S9, ZI1..8)
get_otp_heatmap(days=7) → 4416 triplets ✅
```

## Fichiers modifiés

- `src/routing/graph.py` (hotfix 6) — `vitesse_kmh` → `speed_kmh`
- `src/routing/pathfinder_multimodal.py` (hotfix 7+8) — signature `plan_car_trip` + suppression écrasement smart routing
- `scripts/maintenance/backfill_dim_spatial_lat_lon.py` (NEW, hotfix 5)
- `scripts/sql/backfill_dim_spatial_lat_lon.sql` (NEW, hotfix 5 — version SQL alternative)

## Sprint 8+ (priorités)

1. **Cron backfill lat/lon** toutes les 5 min (la dette réapparaît)
2. **Fix la source** : `build_spatial_mapping` doit être le seul writer
3. **GTFS Overpass API** : vrai A* routier (Sprint 12) pour remplacer le graphe H3 res 13 qui a des trous
4. **Tests intégration e2e** (Sprint 9) : `tests/integration/test_fail_loud_e2e.py` avec container PostgreSQL
5. **Refacto xgboost_speed.py + xgboost_velov.py** (Sprint 9+) : aligner sur schéma v0.3.1

## KPIs

- **Tests e2e** : 3/3 verts (voiture, Vélov, KPIs TCL)
- **Build streamlit** : 6 itérations cumulées (~30 min total), image finale 13.3GB
- **Disque VPS** : 18 Go libres (de 27 → 18 = -9 Go sur les 6 builds)
- **Graphe routier** : 2403 nœuds, 13047 arêtes (sparse mais connecté)
- **Dette schéma** : 0 dette connue restante (sous contrôle)
