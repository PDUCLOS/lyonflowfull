"""Export gold tables → Parquet pour training GNN sur OVH AI Training.

Usage (depuis le VPS) :
    python scripts/export_gnn_data.py --output-dir /tmp/gnn_export/

Exporte 3 fichiers :
    - features.parquet : fact_traffic_series (7 derniers jours)
    - adjacency.parquet : dim_gnn_adjacency (edge list)
    - spatial_mapping.parquet : dim_spatial_grid_mapping (node_idx ↔ channel_id)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.db.connection import execute_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def export(output_dir: str, days: int = 7) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    logger.info("Exporting fact_traffic_series (%d days)...", days)
    features = pd.DataFrame(
        execute_query(
            """
            SELECT "timestamp", node_idx, properties_vitesse AS speed_kmh
            FROM gold.fact_traffic_series
            WHERE "timestamp" >= NOW() - make_interval(days => %s)
              AND properties_vitesse IS NOT NULL
            ORDER BY "timestamp", node_idx
            """,
            (days,),
        )
    )
    if features.empty:
        logger.error("fact_traffic_series vide — rien a exporter")
        sys.exit(1)
    features.to_parquet(out / "features.parquet", index=False)
    logger.info("  → %d rows, %d nodes", len(features), features["node_idx"].nunique())

    logger.info("Exporting dim_gnn_adjacency...")
    adjacency = pd.DataFrame(
        execute_query(
            """
            SELECT node_u, node_v
            FROM gold.dim_gnn_adjacency
            WHERE is_connected = TRUE
            """
        )
    )
    if adjacency.empty:
        logger.error("dim_gnn_adjacency vide — graphe non construit")
        sys.exit(1)
    adjacency.to_parquet(out / "adjacency.parquet", index=False)
    logger.info("  → %d edges", len(adjacency))

    logger.info("Exporting dim_spatial_grid_mapping...")
    mapping = pd.DataFrame(
        execute_query(
            """
            SELECT node_idx, properties_twgid AS channel_id, h3_id, lat, lon
            FROM gold.dim_spatial_grid_mapping
            ORDER BY node_idx
            """
        )
    )
    mapping.to_parquet(out / "spatial_mapping.parquet", index=False)
    logger.info("  → %d nodes mapped", len(mapping))

    total_mb = sum(f.stat().st_size for f in out.glob("*.parquet")) / 1024 / 1024
    logger.info("Export done: %.1f MB in %s", total_mb, out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export GNN training data to Parquet")
    parser.add_argument("--output-dir", default="/tmp/gnn_export", help="Output directory")
    parser.add_argument("--days", type=int, default=7, help="Days of history to export")
    args = parser.parse_args()
    export(args.output_dir, args.days)
