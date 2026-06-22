#!/usr/bin/env bash
# Import du réseau routier OSM de la Métropole de Lyon dans PostgreSQL via osm2pgrouting.
#
# Prérequis :
#   - osm2pgrouting installé (apt install osm2pgrouting)
#   - osmium-tool installé (apt install osmium-tool)
#   - PostgreSQL avec pgRouting activé (migration_026)
#
# Usage : ./scripts/import_osm_lyon.sh

set -euo pipefail

REGION_PBF_URL="https://download.geofabrik.de/europe/france/rhone-alpes-latest.osm.pbf"
WORK_DIR="/tmp/osm_lyon_import"
LYON_BBOX="4.72,45.69,4.94,45.82"
MAPCONFIG="$(cd "$(dirname "$0")" && pwd)/osm2pgrouting_mapconfig.xml"

DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-lyonflow}"
DB_USER="${POSTGRES_USER:?POSTGRES_USER requis}"

if [ ! -f "$MAPCONFIG" ]; then
    echo "❌ mapconfig.xml introuvable : $MAPCONFIG"
    exit 1
fi

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
-- Longueur réelle en mètres (geography cast)
UPDATE osm.ways
SET length_m = ST_Length(the_geom::geography)
WHERE length_m IS NULL OR length_m = 0;

-- Coût par défaut (sans trafic) = length_m / (maxspeed_kmh / 3.6) en secondes
UPDATE osm.ways
SET cost_default = length_m / (GREATEST(maxspeed_kmh, 5.0) / 3.6),
    cost = length_m / (GREATEST(maxspeed_kmh, 5.0) / 3.6);

-- Reverse cost pour sens uniques
UPDATE osm.ways
SET reverse_cost = CASE
    WHEN one_way = 1 THEN -1
    WHEN one_way = -1 THEN cost
    ELSE cost
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

echo ""
echo "=== Import terminé ==="
echo "Nettoyage possible : rm -rf $WORK_DIR"
echo "Test : SELECT * FROM osm.route_car(4.8357, 45.7640, 4.8589, 45.7607) LIMIT 5;"
