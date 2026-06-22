# pgRouting — Next Steps

> **Date** : 2026-06-21
> **Contexte** : Phase 2 (refacto Python) livrée. pgRouting fonctionne, le dashboard utilise les vraies rues OSM. Il reste 5 items.

---

## Ce qui marche maintenant

- pgRouting installé (`pgrouting/pgrouting:16-3.5-3.7.3`)
- 87k vertices + 101k arêtes OSM importées (Métropole de Lyon)
- `osm.route_car()` retourne des itinéraires avec géométrie réelle
- `graph.py` → `compute_route_pgrouting()` (SQL direct)
- `pathfinder.py` → `compute_itinerary()` via pgRouting
- `itinerary.py` → `_render_map()` dessine les polylines OSM
- API `/api/v1/itinerary` fonctionne (Part-Dieu → Bellecour = 82 segments, noms de rues)
- Plus de zigzag

## Ce qui ne marche PAS encore

**Le routing utilise `cost_default` (maxspeed OSM fixe) au lieu des vitesses trafic temps réel.** Parce que `mv_sensor_to_way` est vide.

---

## Item 1 — Fix `mv_sensor_to_way` vide (CRITIQUE, 10 min)

### Root cause

```
mv_sensor_to_way JOIN chain:
  dim_spatial_grid_mapping.properties_twgid = "LYO02236"  (format actuel)
  → mv_twgid_to_lyo.properties_twgid = "537"             (format ancien, MV pas refresh)
  → JOIN = 0 rows
  → sensor_coords CTE vide
  → mv_sensor_to_way vide
```

`build_spatial_mapping.py` insère `channel_id` (format LYO) dans `properties_twgid`. `mv_twgid_to_lyo` a été matérialisée quand le format était integer. Les deux ne matchent plus.

### Fix

Migration 028 bypass toute la chaîne. Va directement depuis `traffic_features_live` (qui a `channel_id` LYO + `lat` + `lon`).

```bash
# Sur le VPS
psql -U $POSTGRES_USER -d lyonflow -f scripts/sql/migration_028_fix_sensor_to_way.sql
```

Résultat attendu :
- `sensors_total` : ~1100
- `ways_with_sensor` : ~2000-5000
- `avg_distance_m` : ~80-120m

### Vérification

```sql
-- Doit retourner > 0
SELECT COUNT(*) FROM osm.mv_sensor_to_way;

-- Doit retourner > 0 (arêtes mises à jour)
SELECT osm.refresh_traffic_costs();

-- Les vitesses doivent varier (pas toutes 50 ou 30)
SELECT road_name, speed_kmh FROM osm.route_car(4.8357, 45.7640, 4.8589, 45.7607) LIMIT 10;
```

---

## Item 2 — Activer le DAG refresh (5 min)

Le fichier `dags/maintenance/refresh_osm_traffic_costs.py` existe et tourne `*/15 min`. Il faut juste l'unpauser dans Airflow UI.

```bash
# Ou via CLI
airflow dags unpause refresh_osm_traffic_costs
```

Vérifier qu'il apparaît dans le scheduler et qu'un run réussit.

---

## Item 3 — Benchmark perfo (15 min)

Tester que le routing est assez rapide pour l'UX.

```sql
-- Benchmark : 10 routes aléatoires, mesurer le temps
\timing on

-- Court (2-3 km)
SELECT COUNT(*) FROM osm.route_car(4.8357, 45.7640, 4.8589, 45.7607);

-- Moyen (5-6 km)
SELECT COUNT(*) FROM osm.route_car(4.8058, 45.7798, 4.8700, 45.7310);

-- Long (10+ km)
SELECT COUNT(*) FROM osm.route_car(4.7720, 45.7800, 4.9200, 45.7200);
```

Cible : p95 < 150ms. Si trop lent → ajouter index `CREATE INDEX idx_ways_cost ON osm.ways (cost) WHERE cost > 0;`

---

## Item 4 — Doc updates (30 min, je peux faire)

| Fichier | Quoi |
|---------|------|
| `CHANGELOG.md` | Entrée Sprint 17+ : pgRouting, migration 026-028, refacto routing |
| `CLAUDE.md` | Section routing mise à jour (pgRouting au lieu de H3 K=2). Stack technique : ajouter pgRouting. Structure : `osm.*` schéma |
| `AGENTS.md` | Si pertinent |

---

## Item 5 — Tests pytest (30 min, je peux faire)

- Fixer les tests existants (imports cassés par suppression `shortest_path`/`get_nearest_node`)
- Ajouter tests intégration pgRouting (`@pytest.mark.integration`)
- Le `ModuleNotFoundError: plotly` est un problème d'env local (pas lié à pgRouting)

---

## Ordre recommandé

```
1. Migration 028 sur VPS          ← CRITIQUE (trafic temps réel)
2. Vérifier SELECT COUNT(*) > 0   ← valide le fix
3. Activer DAG                    ← automatise le refresh
4. Benchmark                      ← valide la perf
5. Doc updates                    ← je fais en parallèle
6. Tests                          ← je fais en parallèle
```

Items 1-4 : toi sur le VPS (~30 min total).
Items 5-6 : moi en local pendant que tu fais le VPS.
