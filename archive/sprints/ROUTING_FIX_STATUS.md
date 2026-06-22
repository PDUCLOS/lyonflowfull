# Routing voiture — État d'avancement et décision

> **Date** : 2026-06-21
> **Statut** : Fichiers prêts, en attente déploiement VPS

---

## Problème identifié

Le routing voiture produit des **zigzags** parce que le graphe (`src/routing/graph.py`) est construit depuis les cellules H3 du GNN (K=2 nearest neighbors), pas depuis un réseau routier réel. Les itinéraires traversent le Rhône, coupent des bâtiments, et ne suivent aucune rue.

## Solution choisie : pgRouting (option E — ni A, ni B, ni C, ni D)

Aucune des 4 options proposées n'est optimale :

| Option | Problème principal |
|--------|-------------------|
| A. Snap Overpass | Maquille le visuel mais le routage reste faux. 5-10s de latence (20 requêtes Overpass). |
| B. OSRM Docker | +2 Go RAM sur un VPS à 12 Go déjà chargé. Pas de trafic temps réel natif. |
| C. SQL récursif PostGIS | Réinventer pgRouting à la main. Complexe, lent, bugprone. |
| D. API externe | Coût récurrent, dépendance externe, quota. |

**pgRouting** = extension PostgreSQL native. Zéro container supplémentaire, zéro RAM additionnelle significative (~200 Mo), intégration SQL directe via `execute_query()`, injection triviale des vitesses trafic capteurs. C'est l'option C mais en **propre** — l'extension fait le Dijkstra dirigé côté serveur au lieu de le coder à la main.

### Ce qui change concrètement

- **Image Docker PostgreSQL** : `postgis/postgis:16-3.4` → `pgrouting/pgrouting:16-3.5-3.7.3` (compatible, même PGDATA)
- **Réseau routier** : ~30-50k segments OSM de la Métropole de Lyon importés via `osm2pgrouting`
- **Pathfinding** : `pgr_dijkstra(directed := true)` remplace `nx.astar_path()` sur graphe H3
- **Géométrie** : chaque arête retourne `ST_AsGeoJSON(the_geom)` — les polylines suivent les rues réelles
- **Trafic temps réel** : DAG `*/15 min` met à jour `cost = length_m / speed_capteur` sur les arêtes proches d'un capteur Grand Lyon (JOIN spatial < 200m)
- **Sens uniques** : supportés nativement (`reverse_cost = -1`)

## Fichiers déjà créés (dans le repo local)

| Fichier | Contenu |
|---------|---------|
| `docs/SPEC_PGROUTING_INTEGRATION.md` | Spec complète — 15 sections, diagnostic + implémentation + rollback |
| `scripts/sql/migration_026_pgrouting_osm_network.sql` | `CREATE EXTENSION pgrouting` + schéma `osm.*` + fonctions SQL (`route_car`, `refresh_traffic_costs`) |
| `scripts/import_osm_lyon.sh` | Download Geofabrik Rhône-Alpes → osmium extract Lyon → osm2pgrouting |
| `scripts/osm2pgrouting_mapconfig.xml` | 14 types de voies routières (motorway → service) |
| `dags/maintenance/refresh_osm_traffic_costs.py` | DAG Airflow — refresh coûts trafic `*/15 min` |

## Prochaines étapes

### Phase 1 — Infrastructure (à faire sur le VPS)

1. Backup PostgreSQL + vérification restore
2. Modifier `docker-compose.yml` : changer l'image postgres
3. Pull + restart container postgres
4. Exécuter `migration_026_pgrouting_osm_network.sql`
5. Installer `osm2pgrouting` + `osmium-tool` sur le VPS
6. Exécuter `import_osm_lyon.sh`
7. Tester : `SELECT * FROM osm.route_car(4.8357, 45.7640, 4.8589, 45.7607);`

### Phase 2 — Refactoring Python (après validation pgRouting en prod)

1. Refactorer `src/routing/graph.py` — remplacer NetworkX par appel SQL pgRouting
2. Refactorer `src/routing/pathfinder.py` — segments avec géométrie multi-vertices
3. Adapter `dashboard/components/widgets/usager/itinerary.py` — polylines réelles
4. Supprimer `src/routing/snap_to_roads.py` (dead code)
5. Tests + validation visuelle

### Temps estimé total : 5-7 heures

---

## Pourquoi pas le snap Overpass (option A)

L'option A "règle le visuel" mais :

1. **Le routage reste mathématiquement faux** — Dijkstra sur H3 K=2 ignore les sens uniques, les impasses, les ponts. Snapper les points sur des rues ne corrige pas le chemin.
2. **Latence** — 20 requêtes Overpass × 200-500ms = 5-10 secondes par itinéraire. Inacceptable en UX.
3. **Fragilité** — Overpass API publique est rate-limitée (10 req/s globalement, pas par client). En charge, timeout garanti.
4. **Double travail** — Si on snap maintenant et qu'on fait pgRouting après, le snap est du throwaway code.

pgRouting résout le problème **à la racine** : vrai réseau routier, vrai Dijkstra dirigé, vraies géométries, trafic temps réel.
