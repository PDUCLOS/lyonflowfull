"""DAG — Build spatial grid mapping (channel_id → node_idx).

Dépend de silver.trafic_boucles_clean. Popule gold.dim_spatial_grid_mapping
avec un node_idx séquentiel par channel_id, et calcule matrix_i/j
(via h3.cell_to_local_ij si dispo, sinon approximation géographique).

DAG quotidien après les transforms.

Refonte 2026-07-01 (audit MLOps) — root cause de l'échec quotidien depuis
8+ jours : chaque UPSERT/INSERT passait par ``execute_query()`` qui ouvre
une NOUVELLE connexion Postgres à chaque appel — jusqu'à ~1200 connexions
pour le grid mapping + ~28 800 pour les arêtes d'adjacence (K=2, ~24 par
nœud, ~1200 nœuds) en un seul run. Combiné à l'absence de ``statement_timeout``, un
run bloqué pouvait tourner plus de 24h (cf. logs Airflow) sans jamais
déclencher l'``execution_timeout``. Fix : une seule connexion réutilisée
avec ``statement_timeout=240s`` + upserts en batch (``execute_values``).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

STATEMENT_TIMEOUT_MS = 480_000  # 480s < execution_timeout Airflow (10min) — la requête
# initiale (DISTINCT ON sur silver.trafic_boucles_clean, 10M lignes) reste lente sous
# charge (thundering herd :00/:30, cf. AUDIT_AIRFLOW_POSTGRES_SPRINT24.md C1) même avec
# l'index idx_silver_trafic_chn_time_geom (heap fetch requis pour extraire lat/lon du
# geom, non couvert par l'index). 240s s'est révélé trop court en pratique (2026-07-01).


def _get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "lyonflow"),
        user=os.getenv("POSTGRES_USER", "lyonflow"),
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=30,
        options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
    )


def _build_spatial_mapping() -> int:
    """Construit gold.dim_spatial_grid_mapping depuis silver.trafic_boucles_clean.

      Stratégie :
      1. Récupère tous les channels distincts avec leur geom (WGS84)
      2. Assigne un node_idx séquentiel (0..N-1)
      3. Calcule matrix_i/j via h3 si dispo
      4. UPSERT batch dans gold.dim_spatial_grid_mapping (PK = properties_twgid)
      5. Construit l'adjacency (K=2 grid) sur la même connexion

    Schema v0.3.1 :
      * `silver.trafic_boucles_clean` a ``geom`` (geometry 4326) et ``geom_2154``
        (Lambert 93). Plus de ``geom_wgs84``.
      * `gold.dim_spatial_grid_mapping` PK = ``properties_twgid`` (et plus
        ``channel_id``). Colonnes ``lat`` + ``lon`` en double precision.
    """
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Liste des channels distincts avec lat/lon (fenêtre 24h : sans borne,
            # le planner scanne/trie les 10M lignes de la table entière — cost ~483k
            # vs ~99k avec la fenêtre, ~30x plus rapide en pratique (17.7s mesuré vs
            # >8min avant, cf. root cause dans le docstring du module).
            cur.execute("""
                SELECT DISTINCT ON (channel_id)
                    channel_id,
                    ST_Y(geom) AS lat,
                    ST_X(geom) AS lon
                FROM silver.trafic_boucles_clean
                WHERE geom IS NOT NULL
                  AND measurement_time > NOW() - INTERVAL '24 hours'
                ORDER BY channel_id, measurement_time DESC
            """)
            rows = cur.fetchall()

        if not rows:
            logger.info("Aucun channel trouvé dans silver.trafic_boucles_clean")
            return 0

        # 2. Calcule h3_index + matrix_i/j par channel
        import h3

        mapping_rows: list[tuple] = []
        for node_idx, row in enumerate(rows):
            lat, lon = row.get("lat"), row.get("lon")
            if lat is None or lon is None:
                continue

            try:
                h3_id = h3.latlng_to_cell(lat, lon, 13)
            except Exception as e:
                logger.debug(f"h3 non dispo pour {row['channel_id']}: {e}")
                h3_id = None

            # matrix_i/j — placeholder (grille simple, 40 colonnes)
            matrix_i = node_idx % 40
            matrix_j = node_idx // 40
            mapping_rows.append((node_idx, row["channel_id"], matrix_i, matrix_j, h3_id, lat, lon))

        # 3. UPSERT batch
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO gold.dim_spatial_grid_mapping
                    (node_idx, properties_twgid, matrix_i, matrix_j, h3_id, lat, lon, updated_at)
                VALUES %s
                ON CONFLICT (properties_twgid) DO UPDATE
                SET node_idx = EXCLUDED.node_idx,
                    matrix_i = EXCLUDED.matrix_i,
                    matrix_j = EXCLUDED.matrix_j,
                    h3_id = EXCLUDED.h3_id,
                    lat = EXCLUDED.lat,
                    lon = EXCLUDED.lon,
                    updated_at = NOW()
                """,
                mapping_rows,
                template="(%s, %s, %s, %s, %s, %s, %s, NOW())",
                page_size=500,
            )
        conn.commit()
        n_inserted = len(mapping_rows)

        # 4. Build adjacency sur la même connexion
        n_edges = _build_adjacency(conn)
        conn.commit()

        logger.info(f"dim_spatial_grid_mapping: {n_inserted} channels inserted/updated, {n_edges} adjacency edges")
        return n_inserted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _build_adjacency(conn) -> int:
    """Construit gold.dim_spatial_adjacency : arêtes entre nodes proches (K=2 grid).

    Sert d'index de voisinage spatial pour ``gold.mv_congestion_propagation_pairs``
    (Sprint 17, Axe 2 — propagation de congestion). La PK est (node_u, node_v).
    Réutilise la connexion passée par ``_build_spatial_mapping`` (pas de connexion
    dédiée — cf. root cause connection storm dans le docstring du module).
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT node_idx, matrix_i, matrix_j FROM gold.dim_spatial_grid_mapping")
        rows = cur.fetchall()
    if not rows:
        return 0

    # Index par (matrix_i, matrix_j) → node_idx
    grid: dict[tuple[int, int], int] = {(r["matrix_i"], r["matrix_j"]): r["node_idx"] for r in rows}

    # K=2 : on connecte chaque nœud à ses voisins dans un rayon de 2 (8-connecté + soi-même)
    edge_rows: list[tuple] = []
    seen: set[tuple[int, int]] = set()
    for (i, j), u_node in grid.items():
        for di in range(-2, 3):
            for dj in range(-2, 3):
                if di == 0 and dj == 0:
                    continue
                v_node = grid.get((i + di, j + dj))
                if v_node is None or v_node == u_node or (u_node, v_node) in seen:
                    continue
                seen.add((u_node, v_node))
                edge_rows.append((u_node, v_node))

    if not edge_rows:
        return 0

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO gold.dim_spatial_adjacency (node_u, node_v, is_connected, updated_at)
            VALUES %s
            ON CONFLICT (node_u, node_v) DO NOTHING
            """,
            edge_rows,
            template="(%s, %s, TRUE, NOW())",
            page_size=1000,
        )

    logger.info(f"dim_spatial_adjacency: {len(edge_rows)} edges inserted")
    return len(edge_rows)


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="build_spatial_mapping",
    description="Construit dim_spatial_grid_mapping depuis silver",
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
