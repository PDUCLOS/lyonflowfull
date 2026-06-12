"""DAG — Refresh quotidien du graphe routier OSM (Overpass API).

Sprint 12 (2026-06-12) — Refresh quotidien du graphe routier Lyon
depuis OpenStreetMap via Overpass API. Remplace le build H3 res 13.

Schedule : quotidien à 03:00 (nuit, moins de traffic Overpass).
Tasks :
1. create_schema  : crée les tables gold.road_network_* si elles n'existent pas
2. refresh_graph  : fetch Overpass → build DiGraph → store dans DB
3. verify_graph   : vérifie que le graphe a des nodes/edges et log les stats

Le graphe est ensuite consommé par src.routing.graph (Sprint 12 refacto)
qui charge depuis gold.road_network_nodes/edges au lieu de
gold.dim_spatial_grid_mapping + gold.dim_gnn_adjacency.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

# Lyon bbox [lat_s, lon_w, lat_n, lon_e]
LYON_BBOX = [45.65, 4.75, 45.80, 4.95]

default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def _create_schema() -> dict:
    """Crée/vérifie les tables gold.road_network_* (idempotent)."""
    from src.db.connection import raw_connection

    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS gold.road_network_nodes (
                osm_id          BIGINT PRIMARY KEY,
                lat             DOUBLE PRECISION NOT NULL,
                lon             DOUBLE PRECISION NOT NULL,
                highway_type    TEXT,
                ways_count      INTEGER DEFAULT 1,
                CONSTRAINT road_network_nodes_lat_check  CHECK (lat  BETWEEN -90  AND  90),
                CONSTRAINT road_network_nodes_lon_check  CHECK (lon  BETWEEN -180 AND 180)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS gold.road_network_edges (
                from_osm_id     BIGINT NOT NULL REFERENCES gold.road_network_nodes (osm_id),
                to_osm_id       BIGINT NOT NULL REFERENCES gold.road_network_nodes (osm_id),
                length_m        DOUBLE PRECISION NOT NULL,
                maxspeed_kmh    INTEGER,
                highway_type    TEXT,
                osm_way_id      BIGINT,
                oneway          BOOLEAN DEFAULT FALSE,
                CONSTRAINT road_network_edges_pk       PRIMARY KEY (from_osm_id, to_osm_id),
                CONSTRAINT road_network_edges_length_pos CHECK (length_m >= 0)
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rnn_nodes_geom
                ON gold.road_network_nodes (lat, lon);
            CREATE INDEX IF NOT EXISTS idx_rnn_nodes_highway
                ON gold.road_network_nodes (highway_type) WHERE highway_type IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_rne_from
                ON gold.road_network_edges (from_osm_id);
            CREATE INDEX IF NOT EXISTS idx_rne_to
                ON gold.road_network_edges (to_osm_id);
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS gold.road_network_refresh_log (
                id              SERIAL PRIMARY KEY,
                refreshed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                nodes_count     INTEGER NOT NULL,
                edges_count     INTEGER NOT NULL,
                bbox_used       TEXT,
                osm_query_hash  TEXT,
                status          TEXT DEFAULT 'success'
            );
            """
        )
    logger.info("Schema gold.road_network_* verified/created")
    return {"schema": "ok"}


def _refresh_graph(bbox: list[float] = LYON_BBOX) -> dict:
    """Task principale : fetch Overpass + build + store."""
    from src.routing.gtfs_graph_builder import build_and_store

    result = build_and_store(bbox=bbox, use_cache=False)  # always fresh fetch
    if "error" in result:
        raise RuntimeError(f"Overpass build failed: {result['error']}")
    logger.info("refresh_graph result: %s", result)
    return result


def _verify_graph() -> dict:
    """Vérifie que le graphe est sain et log les stats."""
    from src.db.connection import execute_scalar

    nodes = execute_scalar("SELECT COUNT(*) FROM gold.road_network_nodes")
    edges = execute_scalar("SELECT COUNT(*) FROM gold.road_network_edges")
    last_refresh = execute_scalar("SELECT refreshed_at FROM gold.road_network_refresh_log ORDER BY id DESC LIMIT 1")
    status = execute_scalar("SELECT status FROM gold.road_network_refresh_log ORDER BY id DESC LIMIT 1")

    logger.info(
        "Graph stats: nodes=%s, edges=%s, last_refresh=%s, status=%s",
        nodes,
        edges,
        last_refresh,
        status,
    )

    # Seuil minimal : 1000 nodes (Lyon devrait avoir ~5000+ nodes)
    if nodes and int(nodes) < 1000:
        raise ValueError(f"Graphe trop petit ({nodes} nodes < 1000) — vérifiez Overpass")

    return {
        "nodes": nodes,
        "edges": edges,
        "last_refresh": str(last_refresh) if last_refresh else None,
        "status": status,
    }


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

with DAG(
    dag_id="dag_refresh_road_network",
    description=(
        "Refresh quotidien du graphe routier Lyon depuis Overpass API (OSM). "
        "Bbox Lyon intra-muros [45.65, 4.75, 45.80, 4.95]. "
        "Remplace le build H3 res 13 (dim_spatial_grid_mapping). "
        "Schedule: 03:00 daily."
    ),
    default_args=default_args,
    schedule_interval="0 3 * * *",  # 03:00 daily
    start_date=datetime(2026, 6, 13),  # Start tomorrow
    catchup=False,
    max_active_runs=1,
    tags=["routing", "osm", "road-network", "gold"],
) as dag:
    create_schema = PythonOperator(
        task_id="create_schema",
        python_callable=_create_schema,
        execution_timeout=timedelta(minutes=2),
    )

    refresh_graph = PythonOperator(
        task_id="refresh_graph",
        python_callable=_refresh_graph,
        op_kwargs={"bbox": LYON_BBOX},
        execution_timeout=timedelta(minutes=10),
    )

    verify_graph = PythonOperator(
        task_id="verify_graph",
        python_callable=_verify_graph,
        execution_timeout=timedelta(minutes=2),
    )

    # Linear: schema → refresh → verify
    create_schema >> refresh_graph >> verify_graph
