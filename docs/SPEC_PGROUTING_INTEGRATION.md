# SPEC — Intégration pgRouting : Routing voiture sur réseau routier OSM

> **Version** : 1.0 — 2026-06-21
> **Auteur** : Patrice DUCLOS
> **Branche cible** : `vps`
> **Priorité** : Critique (UX itinéraire voiture cassé — zigzag)

---

## 1. Diagnostic : pourquoi le routing voiture zigzague

### Root cause

Le graphe routier actuel (`src/routing/graph.py:_build_graph_from_db()`) est construit depuis :

- **`gold.dim_spatial_grid_mapping`** : ~1520 noeuds H3 res 13 (centres de cellules hexagonales)
- **`gold.dim_gnn_adjacency`** : ~4072 arêtes K=2 (2 voisins H3 les plus proches)

Ce graphe H3 est concu pour le **GNN** (prédiction spatiale de congestion). Ce n'est **PAS** un réseau routier : les aretes relient des cellules hexagonales par proximité géographique, pas par connexion routière. Résultat : les itinéraires traversent le Rhône, coupent des pâtés de maisons, et produisent des zigzags.

### Symptôme visible

Chaque noeud a `start_lon == end_lon` et `start_lat == end_lat` (un seul point par noeud H3). Les segments tracés sur la carte sont des lignes droites entre centres de cellules hexagonales — pas des routes.

### Fichiers impactés

| Fichier | Rôle | Impact |
|---------|------|--------|
| `src/routing/graph.py` | Construit le graphe NetworkX H3 | **REMPLACER** par requête pgRouting |
| `src/routing/pathfinder.py` | A* sur graphe NetworkX | **REFACTORER** — pgRouting fait le pathfinding |
| `src/routing/pathfinder_multimodal.py` | `plan_car_trip()` L532, `_road_itinerary_between()` L191 | Consommateurs — interface stable |
| `dashboard/components/widgets/usager/itinerary.py` | Rendu Folium polyline | **ADAPTER** pour géométrie multi-vertices |
| `src/routing/snap_to_roads.py` | Snap Overpass (dead code) | **SUPPRIMER** |
| `src/routing/__init__.py` | Facade publique | Mettre à jour exports |

---

## 2. Solution : pgRouting (extension PostgreSQL)

### Pourquoi pgRouting et pas OSRM / Valhalla / OSMnx

| Critère | pgRouting | OSRM | Valhalla | OSMnx |
|---------|-----------|------|----------|-------|
| Nouveau container Docker | **NON** (extension PG) | Oui (~2 Go RAM) | Oui (~3 Go RAM) | Non (Python) |
| Intégration SQL native | **Oui** (`execute_query()`) | API HTTP externe | API HTTP externe | NetworkX (pas SQL) |
| Coût trafic temps réel | **`UPDATE cost` trivial** | Rebuild profil custom | Rebuild costing | Manuel |
| Espace disque (Lyon) | ~300 Mo | ~200 Mo | ~250 Mo | ~150 Mo (en RAM) |
| RAM supplémentaire | ~200 Mo | ~2 Go | ~3 Go | ~1 Go (NetworkX) |
| Géométrie des routes | **`the_geom` par arete** | Polyline encodée | Polyline encodée | Shapely |

**pgRouting gagne** : zéro infrastructure nouvelle (extension dans le PostgreSQL existant), intégration SQL native via `execute_query()`, injection triviale des vitesses trafic, et surtout **le VPS n'a que 12 Go RAM** — ajouter un container OSRM/Valhalla n'est pas viable.

---

## 3. Prérequis : changement d'image Docker PostgreSQL

### ATTENTION — Opération production

L'image actuelle `postgis/postgis:16-3.4` ne contient PAS pgRouting. `CREATE EXTENSION pgrouting` échouera. Il faut changer l'image.

### Image cible

```
pgrouting/pgrouting:16-3.5-3.7.3
```

Cette image est construite **FROM** `postgis/postgis:16-3.4` — le PGDATA existant (bind mount `/mnt/postgres-data/pgdata` sur sdb) est **byte-compatible**. Pas de dump/restore nécessaire.

### Procédure

```bash
# 1. BACKUP OBLIGATOIRE AVANT TOUTE CHOSE
ssh root@51.83.159.224 "bash /opt/lyonflow/scripts/backup.sh"
# Vérifier que le backup offsite est à jour (scripts/backup-offsite.sh)

# 1b. VÉRIFICATION DU BACKUP (CRITIQUE — ne jamais sauter)
# Avant de toucher l'image PostgreSQL, on prouve que le dump peut restore.
# Si le backup est corrompu ou incomplet, le rollback devient impossible.
ssh root@51.83.159.224 <<'EOF'
BACKUP_FILE=$(ls -t /opt/lyonflow/backups/pgdump_*.sql.gz 2>/dev/null | head -1)
echo "Vérification backup : $BACKUP_FILE"
gunzip -c "$BACKUP_FILE" | head -50 | grep -q "PostgreSQL database dump" \
  || { echo "❌ Backup header manquant — fichier corrompu"; exit 1; }
# Restore à blanc dans une DB jetable
dropdb --if-exists lyonflow_restore_test 2>/dev/null || true
createdb lyonflow_restore_test
gunzip -c "$BACKUP_FILE" | psql -d lyonflow_restore_test -q >/dev/null 2>&1
# Sanity checks
echo "=== Vérification tables critiques ==="
for tbl in gold.traffic_features_live gold.dim_spatial_grid_mapping gold.dim_gnn_adjacency; do
  CNT=$(psql -d lyonflow_restore_test -t -A -c "SELECT COUNT(*) FROM $tbl;")
  echo "  $tbl : $CNT lignes"
  if [ "$CNT" -eq 0 ]; then
    echo "❌ Table $tbl VIDE — backup incomplet"
    exit 1
  fi
done
dropdb lyonflow_restore_test
echo "✅ Backup vérifié, restore validé"
EOF

# 2. Arrêter les services qui dépendent de postgres
# (Airflow scheduler, MLflow, API, Streamlit)
docker compose stop airflow-scheduler airflow-webserver airflow-worker \
  mlflow-server api dashboard celery-worker

# 3. Modifier docker-compose.yml (ligne 83)
# AVANT : image: postgis/postgis:16-3.4
# APRÈS : image: pgrouting/pgrouting:16-3.5-3.7.3

# 4. Pull + recreate postgres SEUL
docker compose pull postgres
docker compose up -d postgres

# 5. Attendre healthcheck (pg_isready)
docker compose exec postgres pg_isready -U $POSTGRES_USER -d lyonflow

# 6. Vérifier pgRouting disponible
docker compose exec postgres psql -U $POSTGRES_USER -d lyonflow \
  -c "SELECT * FROM pg_available_extensions WHERE name = 'pgrouting';"

# 7. Redémarrer les services
docker compose up -d
```

### Impact pendant la migration

- **Downtime PostgreSQL** : ~30-60 secondes (pull image + restart container)
- **DAGs Airflow** : `retries=0` → le cycle suivant rattrape (aucun DAG ne perd de données, ils sont idempotents)
- **MLflow** : reconnexion automatique au restart
- **Streamlit** : `DashboardDataError` affiché aux utilisateurs pendant le downtime, recover automatique

### Modification `docker-compose.yml`

```yaml
# Ligne 83
  postgres:
    image: pgrouting/pgrouting:16-3.5-3.7.3  # ÉTAIT: postgis/postgis:16-3.4
    container_name: lyonflow-postgres
    # ... reste inchangé
```

---

## 4. Migration SQL 026 — CREATE EXTENSION + schéma réseau routier

Fichier : `scripts/sql/migration_026_pgrouting_osm_network.sql`

```sql
-- migration_026_pgrouting_osm_network.sql
-- pgRouting : réseau routier OSM pour routing voiture
-- Prérequis : image pgrouting/pgrouting:16-3.5-3.7.3

-- 1. Extension pgRouting
CREATE EXTENSION IF NOT EXISTS pgrouting CASCADE;

-- 2. Schéma dédié pour le réseau routier OSM
CREATE SCHEMA IF NOT EXISTS osm;

-- 3. Table des noeuds (intersections routières)
-- Peuplée par osm2pgrouting depuis l'extrait OSM Lyon
CREATE TABLE IF NOT EXISTS osm.ways_vertices_pgr (
    id         BIGSERIAL PRIMARY KEY,
    cnt        INTEGER,
    chk        INTEGER,
    ein        INTEGER,
    eout       INTEGER,
    the_geom   GEOMETRY(Point, 4326)
);

CREATE INDEX IF NOT EXISTS idx_ways_vertices_geom
    ON osm.ways_vertices_pgr USING GIST (the_geom);

-- 4. Table des arêtes (tronçons routiers)
-- Peuplée par osm2pgrouting
CREATE TABLE IF NOT EXISTS osm.ways (
    gid            BIGSERIAL PRIMARY KEY,
    class_id       INTEGER,
    length         DOUBLE PRECISION,     -- longueur en degrés (osm2pgrouting default)
    length_m       DOUBLE PRECISION,     -- longueur en mètres (calculée post-import)
    name           TEXT,
    source         BIGINT REFERENCES osm.ways_vertices_pgr(id),
    target         BIGINT REFERENCES osm.ways_vertices_pgr(id),
    cost           DOUBLE PRECISION,     -- coût forward (temps en secondes)
    reverse_cost   DOUBLE PRECISION,     -- coût reverse (-1 si sens unique)
    cost_default   DOUBLE PRECISION,     -- coût sans trafic (fallback)
    maxspeed_kmh   DOUBLE PRECISION DEFAULT 50.0,  -- vitesse max OSM ou par classe
    one_way        INTEGER DEFAULT 0,    -- 0=bidirectionnel, 1=forward, -1=reverse
    the_geom       GEOMETRY(LineString, 4326),
    source_osm     BIGINT,               -- OSM node ID source
    target_osm     BIGINT                -- OSM node ID target
);

CREATE INDEX IF NOT EXISTS idx_ways_geom ON osm.ways USING GIST (the_geom);
CREATE INDEX IF NOT EXISTS idx_ways_source ON osm.ways (source);
CREATE INDEX IF NOT EXISTS idx_ways_target ON osm.ways (target);

-- 5. Table de configuration des types de routes (osm2pgrouting)
CREATE TABLE IF NOT EXISTS osm.configuration (
    id         SERIAL PRIMARY KEY,
    tag_id     INTEGER,
    tag_key    TEXT,
    tag_value  TEXT,
    priority   DOUBLE PRECISION DEFAULT 1.0,
    maxspeed   DOUBLE PRECISION DEFAULT 50.0
);

-- 6. Vue matérialisée : mapping capteur Grand Lyon → arête OSM la plus proche
-- JOIN spatial KNN : chaque capteur est associé à l'arête OSM < 200m
-- C'est LE point critique — la plupart des arêtes OSM n'ont PAS de capteur nearby
CREATE MATERIALIZED VIEW IF NOT EXISTS osm.mv_sensor_to_way AS
WITH sensor_coords AS (
    SELECT
        m.properties_twgid,
        mv.channel_id AS lyo_channel_id,
        m.lat AS sensor_lat,
        m.lon AS sensor_lon,
        ST_SetSRID(ST_MakePoint(m.lon, m.lat), 4326) AS sensor_geom
    FROM gold.dim_spatial_grid_mapping m
    JOIN gold.mv_twgid_to_lyo mv ON mv.properties_twgid = m.properties_twgid
    WHERE m.lat IS NOT NULL AND m.lon IS NOT NULL
)
SELECT DISTINCT ON (w.gid)
    w.gid AS way_gid,
    s.lyo_channel_id,
    s.properties_twgid,
    ST_Distance(
        s.sensor_geom::geography,
        ST_ClosestPoint(w.the_geom, s.sensor_geom)::geography
    ) AS distance_m
FROM osm.ways w
CROSS JOIN LATERAL (
    SELECT *
    FROM sensor_coords sc
    WHERE ST_DWithin(
        sc.sensor_geom::geography,
        w.the_geom::geography,
        200  -- rayon 200m
    )
    ORDER BY sc.sensor_geom <-> ST_ClosestPoint(w.the_geom, sc.sensor_geom)
    LIMIT 1
) s
ORDER BY w.gid, distance_m ASC
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_sensor_to_way_gid
    ON osm.mv_sensor_to_way (way_gid);

-- 7. Fonction de refresh des coûts trafic
-- Appelée par le DAG toutes les 15 min
CREATE OR REPLACE FUNCTION osm.refresh_traffic_costs()
RETURNS INTEGER AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    -- Refresh le mapping capteur → arête
    REFRESH MATERIALIZED VIEW CONCURRENTLY osm.mv_sensor_to_way;

    -- Mettre à jour cost avec la vitesse trafic temps réel
    -- Arêtes avec capteur nearby : cost = length_m / vitesse_capteur
    -- Arêtes sans capteur : cost = cost_default (basé sur maxspeed OSM)
    WITH live_speeds AS (
        SELECT
            stw.way_gid,
            t.speed_kmh
        FROM osm.mv_sensor_to_way stw
        JOIN gold.traffic_features_live t
            ON t.channel_id = stw.lyo_channel_id
        WHERE t.computed_at >= NOW() - INTERVAL '1 hour'
            AND t.speed_kmh > 0
            AND t.speed_kmh IS NOT NULL
    ),
    latest_speeds AS (
        SELECT DISTINCT ON (way_gid)
            way_gid, speed_kmh
        FROM live_speeds
        ORDER BY way_gid, speed_kmh DESC
    )
    UPDATE osm.ways w
    SET cost = CASE
            WHEN ls.speed_kmh IS NOT NULL AND ls.speed_kmh > 0
                THEN w.length_m / (ls.speed_kmh / 3.6)  -- secondes
            ELSE w.cost_default
        END,
        reverse_cost = CASE
            WHEN w.one_way = 1 THEN -1  -- sens unique forward
            WHEN ls.speed_kmh IS NOT NULL AND ls.speed_kmh > 0
                THEN w.length_m / (ls.speed_kmh / 3.6)
            ELSE w.cost_default
        END
    FROM latest_speeds ls
    WHERE w.gid = ls.way_gid;

    GET DIAGNOSTICS updated_count = ROW_COUNT;

    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

-- 8. Fonction pgRouting wrapper — Dijkstra dirigé avec géométrie
-- Retourne le chemin avec la géométrie réelle de chaque arête
CREATE OR REPLACE FUNCTION osm.route_car(
    p_origin_lon  DOUBLE PRECISION,
    p_origin_lat  DOUBLE PRECISION,
    p_dest_lon    DOUBLE PRECISION,
    p_dest_lat    DOUBLE PRECISION
)
RETURNS TABLE (
    seq          INTEGER,
    edge_id      BIGINT,
    node_id      BIGINT,
    cost_s       DOUBLE PRECISION,
    agg_cost_s   DOUBLE PRECISION,
    length_m     DOUBLE PRECISION,
    speed_kmh    DOUBLE PRECISION,
    road_name    TEXT,
    geom_geojson TEXT
) AS $$
DECLARE
    v_source BIGINT;
    v_target BIGINT;
BEGIN
    -- Trouver le noeud OSM le plus proche de l'origine
    SELECT id INTO v_source
    FROM osm.ways_vertices_pgr
    ORDER BY the_geom <-> ST_SetSRID(ST_MakePoint(p_origin_lon, p_origin_lat), 4326)
    LIMIT 1;

    -- Trouver le noeud OSM le plus proche de la destination
    SELECT id INTO v_target
    FROM osm.ways_vertices_pgr
    ORDER BY the_geom <-> ST_SetSRID(ST_MakePoint(p_dest_lon, p_dest_lat), 4326)
    LIMIT 1;

    IF v_source IS NULL OR v_target IS NULL THEN
        RETURN;
    END IF;

    -- pgr_dijkstra dirigé + JOIN géométrie des arêtes
    RETURN QUERY
    SELECT
        d.seq::INTEGER,
        d.edge::BIGINT          AS edge_id,
        d.node::BIGINT          AS node_id,
        d.cost::DOUBLE PRECISION AS cost_s,
        d.agg_cost::DOUBLE PRECISION AS agg_cost_s,
        w.length_m,
        CASE
            WHEN w.cost > 0 AND w.length_m > 0
                THEN (w.length_m / w.cost) * 3.6  -- m/s → km/h
            ELSE w.maxspeed_kmh
        END AS speed_kmh,
        w.name AS road_name,
        ST_AsGeoJSON(w.the_geom)::TEXT AS geom_geojson
    FROM pgr_dijkstra(
        'SELECT gid AS id, source, target, cost, reverse_cost FROM osm.ways WHERE cost > 0',
        v_source,
        v_target,
        directed := true
    ) d
    LEFT JOIN osm.ways w ON w.gid = d.edge
    WHERE d.edge > 0  -- exclure le dernier row (edge=-1, noeud final)
    ORDER BY d.seq;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION osm.route_car IS
    'Routing voiture Dijkstra dirigé via pgRouting. Retourne chemin avec géométrie OSM par arête.';
```

---

## 5. Import du réseau routier OSM Lyon

### Script : `scripts/import_osm_lyon.sh`

```bash
#!/usr/bin/env bash
# Import du réseau routier OSM de la Métropole de Lyon dans PostgreSQL via osm2pgrouting.
#
# Prérequis :
#   - osm2pgrouting installé (apt install osm2pgrouting)
#   - osmium-tool installé (apt install osmium-tool)
#   - PostgreSQL avec pgRouting activé
#
# Usage : ./scripts/import_osm_lyon.sh

set -euo pipefail

# --- Configuration ---
REGION_PBF_URL="https://download.geofabrik.de/europe/france/rhone-alpes-latest.osm.pbf"
WORK_DIR="/tmp/osm_lyon_import"
LYON_BBOX="4.72,45.69,4.94,45.82"  # Métropole de Lyon élargie
MAPCONFIG="$(dirname "$0")/osm2pgrouting_mapconfig.xml"

DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-lyonflow}"
DB_USER="${POSTGRES_USER:?POSTGRES_USER requis}"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "=== 1/5 Téléchargement Rhône-Alpes PBF (~400 Mo) ==="
if [ ! -f rhone-alpes-latest.osm.pbf ]; then
    wget -q --show-progress "$REGION_PBF_URL" -O rhone-alpes-latest.osm.pbf
fi

echo "=== 2/5 Extraction bbox Métropole de Lyon ==="
osmium extract \
    --bbox="$LYON_BBOX" \
    --strategy=complete_ways \
    rhone-alpes-latest.osm.pbf \
    -o lyon_metro.osm.pbf --overwrite

echo "=== 3/5 Conversion PBF → XML (osm2pgrouting exige du XML) ==="
osmium cat lyon_metro.osm.pbf -o lyon_metro.osm --overwrite

echo "=== 4/5 Import osm2pgrouting ==="
osm2pgrouting \
    --file lyon_metro.osm \
    --conf "$MAPCONFIG" \
    --dbname "$DB_NAME" \
    --username "$DB_USER" \
    --host "$DB_HOST" \
    --port "$DB_PORT" \
    --schema osm \
    --clean

echo "=== 5/5 Post-traitement : calcul length_m + cost_default ==="
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<'EOSQL'
-- Calculer la longueur réelle en mètres (geography cast)
UPDATE osm.ways
SET length_m = ST_Length(the_geom::geography)
WHERE length_m IS NULL OR length_m = 0;

-- Coût par défaut (sans trafic) = length_m / (maxspeed_kmh / 3.6)
UPDATE osm.ways
SET cost_default = length_m / (GREATEST(maxspeed_kmh, 5.0) / 3.6),
    cost = length_m / (GREATEST(maxspeed_kmh, 5.0) / 3.6);

-- Reverse cost pour sens uniques
UPDATE osm.ways
SET reverse_cost = CASE
    WHEN one_way = 1 THEN -1        -- sens unique forward only
    WHEN one_way = -1 THEN cost      -- sens unique reverse (cost forward = -1 déjà géré par osm2pgrouting)
    ELSE cost                         -- bidirectionnel
END;

-- Premier refresh du mapping capteur → arête OSM
REFRESH MATERIALIZED VIEW osm.mv_sensor_to_way;

-- Stats
SELECT
    COUNT(*) AS total_ways,
    COUNT(*) FILTER (WHERE length_m > 0) AS ways_with_length,
    ROUND(SUM(length_m)::numeric / 1000, 1) AS total_km
FROM osm.ways;

SELECT COUNT(*) AS total_vertices FROM osm.ways_vertices_pgr;

SELECT COUNT(*) AS sensors_mapped FROM osm.mv_sensor_to_way;
EOSQL

echo "=== Import terminé ==="
echo "Nettoyage possible : rm -rf $WORK_DIR"
```

### Fichier de configuration : `scripts/osm2pgrouting_mapconfig.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <tag_name name="highway" id="1">
    <tag_value name="motorway"       id="101" priority="1.0"  maxspeed="130" />
    <tag_value name="motorway_link"  id="102" priority="1.0"  maxspeed="60"  />
    <tag_value name="trunk"          id="103" priority="1.05" maxspeed="110" />
    <tag_value name="trunk_link"     id="104" priority="1.05" maxspeed="50"  />
    <tag_value name="primary"        id="105" priority="1.15" maxspeed="80"  />
    <tag_value name="primary_link"   id="106" priority="1.15" maxspeed="40"  />
    <tag_value name="secondary"      id="107" priority="1.5"  maxspeed="50"  />
    <tag_value name="secondary_link" id="108" priority="1.5"  maxspeed="30"  />
    <tag_value name="tertiary"       id="109" priority="1.75" maxspeed="50"  />
    <tag_value name="tertiary_link"  id="110" priority="1.75" maxspeed="30"  />
    <tag_value name="residential"    id="111" priority="2.5"  maxspeed="30"  />
    <tag_value name="living_street"  id="112" priority="3.0"  maxspeed="20"  />
    <tag_value name="service"        id="113" priority="3.5"  maxspeed="20"  />
    <tag_value name="unclassified"   id="114" priority="2.0"  maxspeed="50"  />
  </tag_name>
</configuration>
```

> **Note `mapconfig.xml`** : osm2pgrouting ne lit que les types de `highway` listés ici. On exclut volontairement `footway`, `cycleway`, `path`, `pedestrian`, `steps` — le routing voiture n'emprunte pas ces voies. Les `priority` sont utilisées comme facteur de coût (1.0 = autoroute rapide, 3.5 = service lent).

### Espace disque estimé

| Élément | Taille |
|---------|--------|
| PBF Rhône-Alpes (téléchargement) | ~400 Mo (temporaire) |
| `lyon_metro.osm` (extrait XML) | ~150 Mo (temporaire) |
| Tables `osm.ways` + `osm.ways_vertices_pgr` + index | ~200-300 Mo |
| **Total permanent en DB** | **~300 Mo sur sdb** |

Sdb a 43 Go libres — pas de risque.

---

## 6. DAG Airflow — Refresh coûts trafic

Fichier : `dags/maintenance/refresh_osm_traffic_costs.py`

```python
"""DAG — Refresh des coûts trafic sur le réseau routier OSM.

Appelle osm.refresh_traffic_costs() toutes les 15 min pour
injecter les vitesses capteurs Grand Lyon dans les arêtes OSM.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.postgres.operators.postgres import PostgresOperator

default_args = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="refresh_osm_traffic_costs",
    default_args=default_args,
    description="Refresh coûts trafic temps réel sur arêtes OSM (pgRouting)",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 6, 1),
    catchup=False,
    tags=["maintenance", "routing", "pgrouting"],
) as dag:
    refresh = PostgresOperator(
        task_id="refresh_traffic_costs",
        postgres_conn_id="lyonflow_postgres",
        sql="SELECT osm.refresh_traffic_costs();",
    )
```

### Scheduling (sans conflit)

```
:00   Collecte bronze
:02   Collecte SIRI + Vélov
:05   Transform bronze → silver
:15   Transform silver → gold
*/15  refresh_osm_traffic_costs  ← NOUVEAU (léger : 1 REFRESH MV + 1 UPDATE)
:20   dag_live_speed_retrain
:25   Retrain XGBoost trafic
:50   Retrain Vélov
```

Pas de conflit : le refresh OSM costs est un simple UPDATE SQL (~500ms), indépendant des transforms gold.

---

## 7. Refactoring `src/routing/graph.py`

### Changements

Le fichier passe de "build NetworkX graph from H3" à "query pgRouting via SQL". Le graphe NetworkX **disparait** pour le routing voiture. Les fonctions `build_routing_graph()`, `get_nearest_node()`, `get_node_speed()` restent exportées pour rétro-compatibilité mais changent d'implémentation.

```python
"""Routing — réseau routier OSM via pgRouting.

Sprint XX — Remplacement du graphe H3 K=2 (dim_spatial_grid_mapping +
dim_gnn_adjacency) par le réseau routier OSM importé via osm2pgrouting.
Le pathfinding est délégué à pgr_dijkstra côté PostgreSQL.

Fonctions publiques :
- compute_route_pgrouting(origin, dest) : appelle osm.route_car()
- get_nearest_osm_node(lon, lat) : noeud OSM le plus proche
- build_routing_graph() : DÉPRÉCIÉ — rétro-compatibilité
"""

from __future__ import annotations

import json
import logging

from src.db import execute_query

logger = logging.getLogger(__name__)


def compute_route_pgrouting(
    origin_lon: float,
    origin_lat: float,
    dest_lon: float,
    dest_lat: float,
) -> list[dict] | None:
    """Calcule un itinéraire voiture via pgr_dijkstra (réseau routier OSM).

    Appelle la fonction SQL osm.route_car() qui :
    1. Trouve les noeuds OSM les plus proches de l'origine / destination
    2. Exécute pgr_dijkstra dirigé avec coûts trafic temps réel
    3. Retourne le chemin avec la géométrie réelle de chaque arête

    Returns:
        Liste de dicts par arête du chemin :
        {seq, edge_id, cost_s, agg_cost_s, length_m, speed_kmh,
         road_name, geom_geojson}
        Ou None si pas de chemin.
    """
    rows = execute_query(
        "SELECT * FROM osm.route_car(%s, %s, %s, %s)",
        (origin_lon, origin_lat, dest_lon, dest_lat),
    )
    if not rows:
        return None

    result = []
    for r in rows:
        geojson_str = r.get("geom_geojson")
        geom = json.loads(geojson_str) if geojson_str else None
        result.append({
            "seq": int(r["seq"]),
            "edge_id": int(r["edge_id"]),
            "cost_s": float(r["cost_s"]),
            "agg_cost_s": float(r["agg_cost_s"]),
            "length_m": float(r["length_m"] or 0),
            "speed_kmh": float(r["speed_kmh"] or 30.0),
            "road_name": r.get("road_name") or "",
            "geom_coordinates": geom["coordinates"] if geom else [],
        })
    return result


def get_nearest_osm_node(lon: float, lat: float) -> int | None:
    """Trouve le noeud OSM le plus proche d'un point GPS."""
    rows = execute_query(
        """
        SELECT id FROM osm.ways_vertices_pgr
        ORDER BY the_geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
        LIMIT 1
        """,
        (lon, lat),
    )
    return int(rows[0]["id"]) if rows else None
```

### Ce qui est supprimé de `graph.py`

- `_build_graph_from_db()` — remplacé par `compute_route_pgrouting()`
- `_build_mock_graph()` — plus de mock (politique zéro mock Sprint 8)
- `build_routing_graph()` → déprécié, peut lever `DeprecationWarning` ou être conservé pour le GNN
- `get_nearest_node()` → remplacé par `get_nearest_osm_node()`
- `_haversine_m_local()` — plus nécessaire
- Cache module-level `_graph_cache` — pgRouting est stateless côté Python

### Ce qui reste

- `get_node_speed()` peut rester pour d'autres usages (GNN, widgets) mais n'est plus utilisé par le routing voiture

---

## 8. Refactoring `src/routing/pathfinder.py`

### Changements clés

`compute_itinerary()` appelle `compute_route_pgrouting()` au lieu de build + A*. Les dataclasses `Itinerary` et `ItinerarySegment` conservent leur contrat — on AJOUTE un champ `geometry` sans casser l'existant.

```python
@dataclass
class ItinerarySegment:
    """Un segment dans l'itinéraire."""

    channel_id: str
    length_m: float
    speed_kmh: float
    duration_s: float
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float
    geometry: list[list[float]] | None = None  # NOUVEAU — coordonnées [lon, lat] de la géométrie OSM


@dataclass
class Itinerary:
    # ... inchangé
```

### Nouvelle `compute_itinerary()`

```python
def compute_itinerary(
    origin_lon: float,
    origin_lat: float,
    destination_lon: float,
    destination_lat: float,
    horizon_minutes: int = 0,
    use_cache: bool = True,
) -> Itinerary | None:
    """API haut-niveau : 2 points GPS → itinéraire détaillé via pgRouting."""
    from src.routing.graph import compute_route_pgrouting

    edges = compute_route_pgrouting(origin_lon, origin_lat, destination_lon, destination_lat)
    if not edges:
        return None

    segments = []
    total_length = 0.0
    total_duration = 0.0

    for edge in edges:
        coords = edge["geom_coordinates"]
        # start = premier point de la géométrie, end = dernier
        start_lon, start_lat = coords[0] if coords else [origin_lon, origin_lat]
        end_lon, end_lat = coords[-1] if coords else [destination_lon, destination_lat]

        seg = ItinerarySegment(
            channel_id=edge.get("road_name") or f"edge_{edge['edge_id']}",
            length_m=edge["length_m"],
            speed_kmh=edge["speed_kmh"],
            duration_s=edge["cost_s"],
            start_lon=start_lon,
            start_lat=start_lat,
            end_lon=end_lon,
            end_lat=end_lat,
            geometry=coords,  # NOUVEAU — polyline complète de l'arête
        )
        segments.append(seg)
        total_length += edge["length_m"]
        total_duration += edge["cost_s"]

    avg_speed = (total_length / (total_duration / 3600 * 1000)) if total_duration > 0 else 0

    return Itinerary(
        origin_node=str(edges[0]["edge_id"]),
        destination_node=str(edges[-1]["edge_id"]),
        horizon_minutes=horizon_minutes,
        segments=segments,
        total_length_m=total_length,
        total_duration_s=total_duration,
        average_speed_kmh=avg_speed,
        confidence=_compute_pgrouting_confidence(),
    )


def _compute_pgrouting_confidence() -> float:
    """Calcule la confiance basée sur la couverture réelle des capteurs.

    - coverage_ratio = % d'arêtes OSM qui ont un capteur Grand Lyon nearby
      avec vitesse temps réel < 1h
    - confidence = 0.5 + 0.5 * coverage_ratio (plancher 50%, max 100%)

    Sans capteur → utilise maxspeed_kmh OSM (estimation moins fiable).
    Avec capteur → vitesse réelle = haute confiance.

    Returns:
        float entre 0.5 et 1.0
    """
    try:
        from src.db import execute_query
        rows = execute_query("""
            WITH coverage AS (
                SELECT
                    COUNT(*) AS total_ways,
                    COUNT(*) FILTER (
                        WHERE t.speed_kmh IS NOT NULL
                          AND t.computed_at >= NOW() - INTERVAL '1 hour'
                    ) AS covered_ways
                FROM osm.ways w
                LEFT JOIN osm.mv_sensor_to_way stw ON stw.way_gid = w.gid
                LEFT JOIN gold.traffic_features_live t
                  ON t.channel_id = stw.lyo_channel_id
            )
            SELECT
                CASE WHEN total_ways > 0
                     THEN covered_ways::FLOAT / total_ways::FLOAT
                     ELSE 0.0
                END AS coverage_ratio
            FROM coverage
        """)
        if rows and rows[0].get("coverage_ratio") is not None:
            cov = float(rows[0]["coverage_ratio"])
            return min(1.0, max(0.5, 0.5 + 0.5 * cov))
    except Exception as e:
        logger.warning("Impossible de calculer coverage_ratio (%s) — fallback 0.75", e)
    return 0.75  # fallback conservateur si DB indispo
```

### Fonctions supprimées

- `shortest_path()` — pgRouting fait le pathfinding
- `_build_traffic_aware_graph()` — les coûts sont dans `osm.ways.cost`
- `_compute_confidence()` — remplacé par valeur fixe (ou calcul simple basé sur fraîcheur des coûts)

### Fonctions conservées

- `_haversine_m()` — utile ailleurs

---

## 9. Adaptation du widget `itinerary.py` (rendu Folium)

### Problème actuel

`_render_map()` trace des **lignes droites** entre `(seg.start_lat, seg.start_lon)` pour chaque segment. Avec pgRouting, chaque segment a une géométrie multi-vertices (`geometry: [[lon,lat], [lon,lat], ...]`) qui suit la route réelle.

### Modification de `_render_map()`

```python
def _render_map(itinerary, origin_coords, dest_coords):
    # ... (markers inchangés) ...

    # AVANT : full_path = liste de points uniques
    # APRÈS : chaque segment a sa propre polyline multi-vertices

    for i, seg in enumerate(itinerary.segments):
        color = _speed_to_color(seg.speed_kmh)

        if seg.geometry and len(seg.geometry) >= 2:
            # Géométrie OSM réelle : [lon, lat] → Folium veut [lat, lon]
            locations = [[pt[1], pt[0]] for pt in seg.geometry]
        else:
            # Fallback ligne droite (ne devrait pas arriver avec pgRouting)
            locations = [
                [seg.start_lat, seg.start_lon],
                [seg.end_lat, seg.end_lon],
            ]

        folium.PolyLine(
            locations=locations,
            color=color,
            weight=6,
            opacity=0.85,
            popup=(
                f"🚗 <b>{seg.speed_kmh:.0f} km/h</b><br>"
                f"📏 {seg.length_m:.0f} m · 🕐 {seg.duration_s:.0f}s"
                f"{'<br>🛣️ ' + seg.channel_id if seg.channel_id else ''}"
            ),
        ).add_to(m)
```

### Résultat visuel attendu

- **Avant** : lignes droites entre centres de cellules H3 → zigzag
- **Après** : polylines qui suivent le tracé réel des rues OSM → itinéraire lisible

---

## 10. Mise à jour `src/routing/__init__.py`

```python
"""Routing — facade publique."""

from src.routing.eco_calculator import (
    calculate_impact,
    get_comparison,
    recommend_mode,
)
from src.routing.graph import (
    compute_route_pgrouting,
    get_nearest_osm_node,
)
from src.routing.pathfinder import (
    Itinerary,
    ItinerarySegment,
    compute_itinerary,
)

__all__ = [
    "Itinerary",
    "ItinerarySegment",
    "calculate_impact",
    "compute_itinerary",
    "compute_route_pgrouting",
    "get_comparison",
    "get_nearest_osm_node",
    "recommend_mode",
]
```

### Exports supprimés

- `build_routing_graph` — plus de graphe NetworkX pour le routing voiture
- `get_nearest_node` — remplacé par `get_nearest_osm_node`
- `get_node_speed` — interne au graphe H3, pas au routing OSM
- `shortest_path` — pgRouting fait le pathfinding
- `CACHE_TTL_SECONDS` — plus de cache NetworkX

### Impact sur les callers

| Caller | Import actuel | Changement |
|--------|--------------|------------|
| `pathfinder_multimodal.py:plan_car_trip()` L568 | `from src.routing.pathfinder import compute_itinerary` | **Aucun** — `compute_itinerary()` conserve la même signature |
| `pathfinder_multimodal.py:_road_itinerary_between()` L205 | `from src.routing.pathfinder import compute_itinerary` | **Aucun** — même signature, même return type |
| `itinerary.py` L20 | `from src.routing import Itinerary, compute_itinerary` | **Aucun** — `Itinerary` et `compute_itinerary` conservés |
| `api/main.py` | `from src.routing import compute_itinerary` | **Aucun** |

---

## 11. Suppression de `snap_to_roads.py`

Ce fichier est du dead code (jamais importé nulle part). Avec pgRouting le snap est natif (noeud OSM le plus proche via `<->` operator).

```bash
git rm src/routing/snap_to_roads.py
```

---

## 12. Gestion des sens uniques

pgRouting supporte le routing dirigé via `directed := true` dans `pgr_dijkstra`. Les sens uniques sont encodés dans `osm.ways` :

| `one_way` | `cost` | `reverse_cost` | Signification |
|-----------|--------|----------------|---------------|
| 0 | > 0 | > 0 | Bidirectionnel |
| 1 | > 0 | -1 | Forward only (sens unique) |
| -1 | -1 | > 0 | Reverse only |

`osm2pgrouting` peuple `one_way` automatiquement depuis les tags OSM `oneway=yes/no/-1`. La fonction `osm.refresh_traffic_costs()` préserve les `-1` (sens interdits).

---

## 13. Tests

### Tests unitaires à adapter

```
tests/routing/test_graph.py          → tester compute_route_pgrouting() avec MockDB
tests/routing/test_pathfinder.py     → tester compute_itinerary() avec mock pgRouting
tests/routing/test_snap_to_roads.py  → SUPPRIMER
tests/persona/test_itinerary.py      → tester rendu avec geometry multi-vertices
```

### Nouveaux tests

```python
# tests/routing/test_pgrouting.py

def test_compute_route_pgrouting_returns_edges(mock_db):
    """osm.route_car() retourne des arêtes avec géométrie."""
    mock_db.set_results([
        {"seq": 1, "edge_id": 42, "node_id": 1, "cost_s": 12.5,
         "agg_cost_s": 12.5, "length_m": 150.0, "speed_kmh": 43.2,
         "road_name": "Rue de la République",
         "geom_geojson": '{"type":"LineString","coordinates":[[4.83,45.76],[4.832,45.761],[4.834,45.762]]}'},
    ])
    from src.routing.graph import compute_route_pgrouting
    result = compute_route_pgrouting(4.83, 45.76, 4.85, 45.77)
    assert result is not None
    assert len(result) == 1
    assert result[0]["road_name"] == "Rue de la République"
    assert len(result[0]["geom_coordinates"]) == 3  # 3 points dans la polyline


def test_itinerary_segment_has_geometry():
    """ItinerarySegment conserve la géométrie OSM."""
    from src.routing.pathfinder import ItinerarySegment
    seg = ItinerarySegment(
        channel_id="Rue X", length_m=100, speed_kmh=30,
        duration_s=12, start_lon=4.83, start_lat=45.76,
        end_lon=4.84, end_lat=45.77,
        geometry=[[4.83, 45.76], [4.835, 45.765], [4.84, 45.77]],
    )
    assert seg.geometry is not None
    assert len(seg.geometry) == 3
```

### Test d'intégration (marqué `@pytest.mark.integration`)

```python
@pytest.mark.integration
def test_pgrouting_extension_available():
    """pgRouting est installé et accessible."""
    from src.db import execute_query
    rows = execute_query("SELECT pgr_version();")
    assert rows is not None
    assert "3.6" in str(rows[0])


@pytest.mark.integration
def test_osm_network_loaded():
    """Le réseau OSM Lyon est importé."""
    from src.db import execute_query
    rows = execute_query("SELECT COUNT(*) as cnt FROM osm.ways;")
    assert int(rows[0]["cnt"]) > 10000  # Lyon a ~30-50k segments routiers
```

---

## 14. Checklist d'implémentation

### Phase 1 — Infrastructure (1-2h)

- [ ] Backup PostgreSQL VPS (`scripts/backup.sh` + offsite)
- [ ] Modifier `docker-compose.yml` : image `pgrouting/pgrouting:16-3.5-3.7.3`
- [ ] Pull + restart postgres, vérifier `pg_available_extensions`
- [ ] Exécuter `migration_026_pgrouting_osm_network.sql`

### Phase 2 — Import OSM (30 min)

- [ ] Installer `osm2pgrouting` + `osmium-tool` sur le VPS
- [ ] Créer `scripts/osm2pgrouting_mapconfig.xml`
- [ ] Créer + exécuter `scripts/import_osm_lyon.sh`
- [ ] Vérifier : `SELECT COUNT(*) FROM osm.ways` > 10 000
- [ ] Vérifier : `SELECT COUNT(*) FROM osm.mv_sensor_to_way` > 100
- [ ] Tester : `SELECT * FROM osm.route_car(4.8357, 45.7640, 4.8589, 45.7607) LIMIT 5;`

### Phase 3 — Refactoring Python (2-3h)

- [ ] Refactorer `src/routing/graph.py` (nouvelle implémentation pgRouting)
- [ ] Refactorer `src/routing/pathfinder.py` (compute_itinerary via pgRouting)
- [ ] Ajouter `geometry` à `ItinerarySegment`
- [ ] Adapter `dashboard/components/widgets/usager/itinerary.py` (polylines multi-vertices)
- [ ] Mettre à jour `src/routing/__init__.py`
- [ ] Supprimer `src/routing/snap_to_roads.py`
- [ ] Vérifier que `plan_car_trip()` et `_road_itinerary_between()` fonctionnent sans changement

#### 3b — Mise à jour documentation (sinon divergence)

La migration invalide toute la doc actuelle qui parle de "graphe H3 KNN pour voiture".
Sans cette étape, on retombe dans le bug récurrent docs qui divergent du code.

- [ ] `AGENTS.md` — section routing → pointer vers pgRouting, retirer mention H3 KNN pour voiture
- [ ] `CLAUDE.md` — idem
- [ ] `README.md` — section architecture / routing mise à jour
- [ ] `CHANGELOG.md` — entrée `feat(routing): migration pgRouting sur réseau OSM réel`
- [ ] `BUGS_PRO_TCL_VPS_2026-06-19.md` — cocher BUG zigzag si listé
- [ ] `SPRINT_*_PLAN_*.md` actifs — vérifier qu'aucun ne référence l'approche H3 KNN
- [ ] `docs/SPEC_APPLY_MIGRATIONS.md` — ajouter migration 026 à la liste

### Phase 4 — DAG + Tests (1h)

- [ ] Créer `dags/maintenance/refresh_osm_traffic_costs.py`
- [ ] Adapter les tests existants
- [ ] Écrire les nouveaux tests pgRouting
- [ ] `pytest tests/ -v --tb=short` — 0 régression
- [ ] `ruff check .` — 0 erreur
- [ ] Phase 3b (mise à jour docs) — fait avant la fin de Phase 3

### Phase 5 — Validation visuelle (30 min)

#### 5.1 — Vérification visuelle

- [ ] Lancer le dashboard Streamlit
- [ ] Tester un itinéraire Part-Dieu → Bellecour
- [ ] Vérifier que la polyline suit les rues (pas de zigzag)
- [ ] Vérifier les couleurs trafic par segment
- [ ] Tester un itinéraire long (Vaise → Bron) — vérifier sens uniques

#### 5.2 — Benchmark perfo (p95 < 150ms)

```python
# scripts/bench_pgrouting.py — exécuté en local + sur VPS
import time
from src.routing import compute_itinerary

ROUTES = [
    (4.8589, 45.7607, 4.8420, 45.7480),  # Part-Dieu → Confluence
    (4.8058, 45.7798, 4.8700, 45.7310),  # Vaise → Bron
    (4.8461, 45.7496, 4.8501, 45.7450),  # Saxe → Berthelot
]

times = []
for i in range(30):  # 10 queries × 3 routes = 30 samples
    for o_lon, o_lat, d_lon, d_lat in ROUTES:
        t0 = time.perf_counter()
        compute_itinerary(o_lon, o_lat, d_lon, d_lat)
        times.append((time.perf_counter() - t0) * 1000)

times.sort()
p50, p95, p99 = times[len(times)//2], times[int(len(times)*0.95)], times[-1]
print(f"p50={p50:.0f}ms p95={p95:.0f}ms p99={p99:.0f}ms")
assert p95 < 150, f"❌ p95={p95:.0f}ms > 150ms — investiguer"
print("✅ Perfo OK")
```

#### 5.3 — Routes de référence vs Google Maps

| Route | Distance pgRouting cible | Durée pgRouting cible |
|-------|--------------------------|------------------------|
| Part-Dieu → Confluence | ≤ 10 km | ≤ 25 min |
| Vaise → Bron | ≤ 14 km | ≤ 30 min |
| Villeurbanne → Gerland | ≤ 8 km | ≤ 20 min |

Critère : distance pgRouting ≤ 1.3× distance Google Maps / OSRM.

```python
# scripts/bench_reference_routes.py
import requests
from src.routing import compute_itinerary

REFERENCE_ROUTES = [
    ("Part-Dieu → Confluence",
     4.8589, 45.7607, 4.8420, 45.7480,
     10.0, 25),  # max_distance_km, max_duration_min
    ("Vaise → Bron",
     4.8058, 45.7798, 4.8700, 45.7310,
     14.0, 30),
    ("Villeurbanne → Gerland",
     4.8800, 45.7715, 4.8260, 45.7280,
     8.0, 20),
]

for name, olon, olat, dlon, dlat, max_km, max_min in REFERENCE_ROUTES:
    itin = compute_itinerary(olon, olat, dlon, dlat)
    dist_km = itin.total_length_m / 1000
    dur_min = itin.total_duration_s / 60
    status = "✅" if dist_km <= max_km and dur_min <= max_min else "❌"
    print(f"{status} {name}: {dist_km:.1f}km / {dur_min:.0f}min (cible ≤ {max_km}km / {max_min}min)")
```

### Temps total estimé : 6-8 heures (incluant 5 ajouts review)

#### Récap des ajouts review (2026-06-21)

| Ajout | Section | Pourquoi |
|-------|---------|----------|
| 1. Backup verification | Phase 1 | Sans restore à blanc, rollback impossible si dump corrompu |
| 2. Confidence coverage-based | pathfinder.py refactor | 0.90 hardcodé est mensonger si capteurs couvrent < 50% |
| 3. Benchmark p95 < 150ms | Phase 5.2 | Cold query pgRouting = 200-500ms, risque UX timeout |
| 4. Doc updates checklist | Phase 3b | Évite le bug récurrent docs/code divergents |
| 5. Routes de référence | Phase 5.3 | Sanity check quantitatif (pas que visuel) vs Google Maps |

---

## 15. Rollback

Si pgRouting pose problème en production :

```bash
# 1. Revenir à l'image PostGIS simple
# docker-compose.yml : image: postgis/postgis:16-3.4
docker compose pull postgres && docker compose up -d postgres

# 2. Le PGDATA est compatible (pgrouting image = FROM postgis)
# Les tables osm.* restent mais ne gênent pas

# 3. Le routing Python retombe sur l'ancien graphe H3
# (si graph.py conserve le fallback NetworkX)
```

Recommandation : garder le fallback NetworkX H3 dans `graph.py` pendant la phase de validation (1-2 semaines), puis le supprimer une fois pgRouting validé en production.
