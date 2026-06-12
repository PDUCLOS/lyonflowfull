#!/usr/bin/env python3
"""Backfill lat/lon pour gold.dim_spatial_grid_mapping.

Sprint 8 hotfix 5 (2026-06-12) — Le graphe H3 a 1543 nœuds avec
properties_twgid au format entier (stringifié) qui n'ont jamais eu
lat/lon backfillés. On les dérive depuis h3_id via h3-py 4.5.

Idempotent : ne touche que les rows où lat IS NULL OR lon IS NULL.

Usage:
    docker compose exec -T streamlit python /app/scripts/maintenance/backfill_dim_spatial_lat_lon.py
"""
import sys
sys.path.insert(0, "/app")

import h3
from src.db.connection import execute_query


def main() -> None:
    # 1. Récupérer les rows sans lat/lon
    rows = execute_query(
        """
        SELECT node_idx, properties_twgid, h3_id
        FROM gold.dim_spatial_grid_mapping
        WHERE lat IS NULL OR lon IS NULL
        """
    )
    print(f"[backfill] {len(rows)} rows missing lat/lon")
    if not rows:
        return

    # 2. Calculer lat/lon via h3-py
    updates = []
    for r in rows:
        try:
            lat, lon = h3.cell_to_latlng(r["h3_id"])
            updates.append((lat, lon, r["node_idx"]))
        except Exception as e:
            print(f"[backfill] skip node_idx={r['node_idx']} h3_id={r['h3_id']} : {e}")

    print(f"[backfill] {len(updates)} lat/lon computed from h3_id")

    # 3. UPDATE en batch via raw SQL (execute_query ne supporte pas multi-rows UPDATE)
    from src.db.connection import raw_connection
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SET search_path TO public, gold, bronze, silver, referentiel, airflow_db, mlflow"
        )
        cur.executemany(
            """
            UPDATE gold.dim_spatial_grid_mapping
            SET lat = %s, lon = %s
            WHERE node_idx = %s
            """,
            updates,
        )
        conn.commit()
        print(f"[backfill] {cur.rowcount} rows updated")

    # 4. Vérification
    after = execute_query(
        """
        SELECT count(*) AS total, count(lat) AS with_lat, count(lon) AS with_lon
        FROM gold.dim_spatial_grid_mapping
        """
    )
    print(f"[backfill] AFTER: {after}")


if __name__ == "__main__":
    main()
