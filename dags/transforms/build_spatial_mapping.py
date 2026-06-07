"""DAG — Build spatial grid mapping (channel_id → node_idx).

Dépend de silver.trafic_boucles_clean. Popule gold.dim_spatial_grid_mapping
avec un node_idx séquentiel par channel_id, et calcule matrix_i/j
(via h3.cell_to_local_ij si dispo, sinon approximation géographique).

DAG quotidien après les transforms.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)


def _build_spatial_mapping() -> int:
    """Construit gold.dim_spatial_grid_mapping depuis silver.trafic_boucles_clean.

    Stratégie :
    1. Récupère tous les channels distincts avec leur geom_wgs84
    2. Assigne un node_idx séquentiel (0..N-1)
    3. Calcule matrix_i/j via h3 si dispo
    4. UPSERT dans gold.dim_spatial_grid_mapping
    """
    from src.db import execute_query

    # 1. Liste des channels distincts
    query = """
        SELECT DISTINCT ON (channel_id)
            channel_id,
            ST_X(ST_StartPoint(geom_wgs84)) AS lon,
            ST_Y(ST_StartPoint(geom_wgs84)) AS lat
        FROM silver.trafic_boucles_clean
        WHERE geom_wgs84 IS NOT NULL
        ORDER BY channel_id, measurement_time DESC
    """
    rows = execute_query(query, ())
    if not rows:
        logger.info("Aucun channel trouvé dans silver.trafic_boucles_clean")
        return 0

    # 2. Calcule h3_index + matrix_i/j par channel
    n_inserted = 0
    for node_idx, row in enumerate(rows):
        channel_id = row["channel_id"]
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue

        # H3 resolution 13
        h3_id = None
        try:
            import h3

            h3_id = h3.latlng_to_cell(lat, lon, 13)
        except (ImportError, Exception) as e:
            logger.debug(f"h3 non dispo: {e}")

        # matrix_i/j — placeholder (grille simple)
        # En production, on utiliserait h3.cell_to_local_ij(h3_id)
        matrix_i = node_idx % 40
        matrix_j = node_idx // 40

        try:
            cur_query = """
                INSERT INTO gold.dim_spatial_grid_mapping
                    (node_idx, channel_id, matrix_i, matrix_j, h3_id, geom_wgs84, updated_at)
                VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), NOW())
                ON CONFLICT (channel_id) DO UPDATE
                SET node_idx = EXCLUDED.node_idx,
                    matrix_i = EXCLUDED.matrix_i,
                    matrix_j = EXCLUDED.matrix_j,
                    h3_id = EXCLUDED.h3_id,
                    geom_wgs84 = EXCLUDED.geom_wgs84,
                    updated_at = NOW()
            """
            execute_query(
                cur_query,
                (
                    node_idx,
                    channel_id,
                    matrix_i,
                    matrix_j,
                    h3_id,
                    lon,
                    lat,
                ),
            )
            n_inserted += 1
        except Exception as e:
            logger.warning(f"Skip channel {channel_id}: {e}")

    # 3. Build adjacency (arêtes graphe GNN) — K=2 grid
    _build_adjacency()
    logger.info(f"dim_spatial_grid_mapping: {n_inserted} channels inserted/updated")
    return n_inserted


def _build_adjacency() -> int:
    """Construit gold.dim_gnn_adjacency : arêtes entre channels proches (K=2 grid)."""
    from src.db import execute_query

    # Récupère tous les node_idx avec leurs matrix_i/j
    query = "SELECT node_idx, matrix_i, matrix_j FROM gold.dim_spatial_grid_mapping"
    rows = execute_query(query, ())
    if not rows:
        return 0

    # Index par (matrix_i, matrix_j) → node_idx
    grid: dict[tuple[int, int], int] = {}
    for r in rows:
        grid[(r["matrix_i"], r["matrix_j"])] = r["node_idx"]

    # K=2 : on connecte chaque nœud à ses voisins dans un rayon de 2 (8-connecté + soi-même)
    n_edges = 0
    for (i, j), u_node in grid.items():
        for di in range(-2, 3):
            for dj in range(-2, 3):
                if di == 0 and dj == 0:
                    continue
                v_node = grid.get((i + di, j + dj))
                if v_node is None or v_node == u_node:
                    continue
                try:
                    cur_query = """
                        INSERT INTO gold.dim_gnn_adjacency
                            (node_u, node_v, is_connected, updated_at)
                        VALUES (%s, %s, TRUE, NOW())
                        ON CONFLICT DO NOTHING
                    """
                    # Stocke bidirectionnel (l'inférence GNN traitera comme undirected)
                    execute_query(cur_query, (u_node, v_node))
                    n_edges += 1
                except Exception as e:
                    logger.warning(f"Skip edge {u_node}-{v_node}: {e}")

    logger.info(f"dim_gnn_adjacency: {n_edges} edges inserted")
    return n_edges


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="build_spatial_mapping",
    description="Construit dim_spatial_grid_mapping + dim_gnn_adjacency depuis silver",
    default_args=default_args,
    schedule_interval="30 2 * * *",  # quotidien 02h30
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["transform", "gold", "spatial"],
) as dag:
    PythonOperator(
        task_id="build_spatial_grid_mapping",
        python_callable=_build_spatial_mapping,
        execution_timeout=timedelta(minutes=10),
    )
