#!/usr/bin/env python3
"""Génère la migration des restrictions d'accès voiture du graphe OSM.

osm2pgrouting n'importe que le tag ``highway`` : les couloirs bus
(``access=no`` + ``bus=yes``), les plateformes tram (``railway=tram`` posées
sur un ``highway=service``) et les voies privées se retrouvent routables en
voiture. Ce script interroge Overpass sur la même bbox que
``import_osm_lyon.sh`` et écrit ``scripts/sql/migration_053_osm_car_access.sql``
(table ``osm.car_access_restrictions`` + colonne ``osm.ways.car_access``).

Règle d'accès (du tag le plus spécifique au plus général, comme OSRM) :
``motorcar`` > ``motor_vehicle`` > ``vehicle`` > ``access``. Le premier tag
renseigné décide. Sans tag d'accès, une voie ``railway=tram`` est interdite.

Usage : python scripts/generate_osm_car_access.py [--from-tsv export.tsv]
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Même emprise que import_osm_lyon.sh (LYON_BBOX = lon_min,lat_min,lon_max,lat_max)
BBOX = (45.69, 4.72, 45.82, 4.94)
# Classes importées par osm2pgrouting_mapconfig.xml
ROUTED_HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "residential",
    "living_street", "service", "unclassified",
}  # fmt: skip
ACCESS_KEYS = ("motorcar", "motor_vehicle", "vehicle", "access")
FORBIDDEN_VALUES = {"no", "psv", "bus", "emergency", "agricultural", "forestry", "military", "official"}
PRIVATE_VALUES = {"private"}
COLUMNS = ("@id", "highway", "railway", *ACCESS_KEYS)
OUTPUT = Path(__file__).resolve().parent / "sql" / "migration_053_osm_car_access.sql"


def classify(tags: dict[str, str]) -> str:
    """Retourne 'no', 'private' ou 'yes' pour une voie OSM."""
    for key in ACCESS_KEYS:
        value = (tags.get(key) or "").split(";")[0].strip()
        if value:
            if value in FORBIDDEN_VALUES:
                return "no"
            if value in PRIVATE_VALUES:
                return "private"
            return "yes"
    if tags.get("railway") == "tram":
        return "no"
    return "yes"


def fetch_overpass_tsv() -> str:
    """Récupère les tags d'accès de toutes les voies highway de la bbox."""
    south, west, north, east = BBOX
    query = (
        f'[out:csv({",".join("::id" if c == "@id" else c for c in COLUMNS)};true;"\\t")][timeout:180];'
        f'way["highway"]({south},{west},{north},{east});out;'
    )
    body = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(OVERPASS_URL, data=body, headers={"User-Agent": "lyonflow-routing/1.0"})
    with urllib.request.urlopen(request, timeout=240) as response:
        return response.read().decode("utf-8")


def build_restrictions(tsv: str) -> dict[str, list[int]]:
    """Regroupe les osm_id restreints par niveau d'accès."""
    restricted: dict[str, list[int]] = {"no": [], "private": []}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        if row.get("highway") not in ROUTED_HIGHWAYS:
            continue
        level = classify(row)
        if level in restricted:
            restricted[level].append(int(row["@id"]))
    for ids in restricted.values():
        ids.sort()
    return restricted


def _array_literal(ids: list[int], per_line: int = 12) -> str:
    lines = [", ".join(str(i) for i in ids[n : n + per_line]) for n in range(0, len(ids), per_line)]
    return "ARRAY[\n    " + ",\n    ".join(lines) + "\n]::BIGINT[]"


def render_sql(restricted: dict[str, list[int]]) -> str:
    """Produit la migration 053 (idempotente, rejouable après un ré-import OSM)."""
    return f"""-- migration_053_osm_car_access.sql
-- ============================================================================
-- Restrictions d'accès voiture sur le graphe pgRouting (osm.ways)
-- ============================================================================
-- FICHIER GÉNÉRÉ par scripts/generate_osm_car_access.py le {date.today().isoformat()}
-- (source : Overpass API, bbox {BBOX}). Ne pas éditer à la main.
--
-- osm2pgrouting n'importe que le tag highway : l'itinéraire voiture empruntait
-- la plateforme du tram T1 et des couloirs bus (access=no, bus=yes) à la
-- Part-Dieu. car_access = 'no' (interdit), 'private' (pénalisé, utile pour
-- sortir d'une résidence), 'yes' (libre). Filtré par osm.route_car et
-- osm.route_car_ksp (migration 054).
--
-- Idempotente : à rejouer après chaque scripts/import_osm_lyon.sh (--clean
-- recrée osm.ways sans la colonne).
-- Voies interdites : {len(restricted["no"])} · voies privées : {len(restricted["private"])}
-- ============================================================================

-- ALTER TABLE osm.ways prend un verrou exclusif : échouer proprement plutôt que
-- bloquer les itinéraires si refresh_osm_traffic_costs tient la table.
SET lock_timeout = '15s';

CREATE TABLE IF NOT EXISTS osm.car_access_restrictions (
    osm_id     BIGINT PRIMARY KEY,
    car_access TEXT   NOT NULL CHECK (car_access IN ('no', 'private'))
);

COMMENT ON TABLE osm.car_access_restrictions IS
    'Voies OSM interdites (no) ou privées (private) aux voitures. Généré par scripts/generate_osm_car_access.py.';

TRUNCATE osm.car_access_restrictions;

INSERT INTO osm.car_access_restrictions (osm_id, car_access)
SELECT unnest({_array_literal(restricted["no"])}), 'no';

INSERT INTO osm.car_access_restrictions (osm_id, car_access)
SELECT unnest({_array_literal(restricted["private"])}), 'private'
ON CONFLICT (osm_id) DO NOTHING;

-- Ajout sans réécriture de la table (défaut constant, PostgreSQL >= 11)
ALTER TABLE osm.ways ADD COLUMN IF NOT EXISTS car_access TEXT NOT NULL DEFAULT 'yes';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ways_car_access_check' AND conrelid = 'osm.ways'::regclass
    ) THEN
        ALTER TABLE osm.ways
            ADD CONSTRAINT ways_car_access_check CHECK (car_access IN ('yes', 'private', 'no'));
    END IF;
END $$;

-- Ne touche que les lignes qui changent (colonne non indexée → mises à jour HOT)
UPDATE osm.ways w
SET car_access = r.car_access
FROM osm.car_access_restrictions r
WHERE r.osm_id = w.osm_id
  AND w.car_access <> r.car_access;

UPDATE osm.ways w
SET car_access = 'yes'
WHERE w.car_access <> 'yes'
  AND NOT EXISTS (SELECT 1 FROM osm.car_access_restrictions r WHERE r.osm_id = w.osm_id);

COMMENT ON COLUMN osm.ways.car_access IS
    'Accès voiture : yes / private (pénalisé) / no (exclu du routage). Source osm.car_access_restrictions.';

-- Nœuds routables : plus grande composante fortement connexe du graphe voiture.
-- Exclure les voies interdites crée des îlots (ex. parvis Part-Dieu relié
-- seulement par des couloirs bus) : y accrocher un départ donnait « aucun
-- itinéraire ». osm.car_snap_vertex (migration 054) n'accroche qu'à ces nœuds.
ALTER TABLE osm.ways_vertices_pgr ADD COLUMN IF NOT EXISTS car_routable BOOLEAN NOT NULL DEFAULT false;

DROP TABLE IF EXISTS pg_temp.car_main_nodes;
CREATE TEMP TABLE car_main_nodes AS
WITH scc AS (
    SELECT component, node
    FROM pgr_strongComponents(
        'SELECT gid AS id, source, target, cost, reverse_cost FROM osm.ways WHERE cost > 0 AND car_access <> ''no'''
    )
)
SELECT node FROM scc
WHERE component = (SELECT component FROM scc GROUP BY component ORDER BY count(*) DESC LIMIT 1);

UPDATE osm.ways_vertices_pgr v
SET car_routable = false
WHERE v.car_routable AND NOT EXISTS (SELECT 1 FROM car_main_nodes m WHERE m.node = v.id);

UPDATE osm.ways_vertices_pgr v
SET car_routable = true
WHERE NOT v.car_routable AND EXISTS (SELECT 1 FROM car_main_nodes m WHERE m.node = v.id);

DROP TABLE car_main_nodes;

COMMENT ON COLUMN osm.ways_vertices_pgr.car_routable IS
    'Nœud de la plus grande composante fortement connexe du graphe voiture (car_access <> no) : point d''accroche.';

ANALYZE osm.ways;
ANALYZE osm.ways_vertices_pgr;
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-tsv", type=Path, help="Export Overpass CSV déjà téléchargé")
    args = parser.parse_args()

    tsv = args.from_tsv.read_text(encoding="utf-8") if args.from_tsv else fetch_overpass_tsv()
    if not tsv.startswith("@id"):
        print("Réponse Overpass inattendue :", tsv[:200], file=sys.stderr)
        return 1
    restricted = build_restrictions(tsv)
    OUTPUT.write_text(render_sql(restricted), encoding="utf-8")
    print(f"{OUTPUT.name} : {len(restricted['no'])} interdites, {len(restricted['private'])} privées")
    return 0


if __name__ == "__main__":
    sys.exit(main())
