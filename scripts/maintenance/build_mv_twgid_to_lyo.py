"""Backfill gold.mv_twgid_to_lyo via Polars + h3-py (H3 res 10 + k_ring(1)).

Sprint 10+ (2026-06-12) — Crée la table de mapping LYO0xxxx <-> properties_twgid
via hash join H3. Approche privilégiée : Polars (vectorisé, parallèle multi-core,
empreinte mémoire dérisoire même sur 1.7M rows).

**Stratégie** :
- H3 res 10 (rayon ~50m, arête ~24m) + k_ring(1) pour gérer les nœuds
  en bordure de cellule (sinon ~5% de misses, cf. note utilisateur Sprint 10+).
- 1 ligne par properties_twgid, channel_id = LYO le plus proche
  (premier match par défaut, possibilité d'affiner en Sprint 11+ avec
  score de distance).
- INSERT batch en Postgres via psycopg2 + execute_values.

**Idempotent** : TRUNCATE + INSERT à chaque run. Schedulé quotidien via
DAG ``maintenance_refresh_mappings`` (Sprint 10+).
"""

from __future__ import annotations

import logging
import sys

sys.path.insert(0, "/opt/airflow")

import h3
import polars as pl
import psycopg2.extras

from src.db.connection import execute_query, raw_connection

logger = logging.getLogger(__name__)

# H3 res 10 → rayon ~50m (compromis perf / précision)
H3_RES = 10
# k_ring(1) ajoute les 6 cellules voisines → 7 cellules par nœud
K_RING = 1


def _create_table_if_not_exists() -> None:
    """Crée la table gold.mv_twgid_to_lyo (idempotent)."""
    execute_query("""
        CREATE TABLE IF NOT EXISTS gold.mv_twgid_to_lyo (
            properties_twgid TEXT PRIMARY KEY,
            twgid_lat        DOUBLE PRECISION,
            twgid_lon        DOUBLE PRECISION,
            channel_id       TEXT,
            lyo_lat          DOUBLE PRECISION,
            lyo_lon          DOUBLE PRECISION,
            distance_m       DOUBLE PRECISION,
            created_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    execute_query("""
        CREATE INDEX IF NOT EXISTS idx_mv_twgid_to_lyo_channel
        ON gold.mv_twgid_to_lyo (channel_id)
    """)
    logger.info("Table gold.mv_twgid_to_lyo ready")


def _load_lyo() -> pl.DataFrame:
    """Charge les derniers LYO channel_id avec lat/lon (Polars via SQL COPY)."""
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (channel_id)
                channel_id, lat, lon
            FROM gold.traffic_features_live
            WHERE lat IS NOT NULL
              AND lon IS NOT NULL
              AND computed_at > NOW() - INTERVAL '14 days'
            ORDER BY channel_id, computed_at DESC
        """)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    df = pl.DataFrame(
        [dict(zip(cols, r)) for r in rows],
        schema_overrides={"channel_id": pl.Utf8, "lat": pl.Float64, "lon": pl.Float64},
    )
    logger.info("Loaded %d distinct LYO channels (Polars)", df.height)
    return df


def _load_twgid() -> pl.DataFrame:
    """Charge les nœuds H3 du graphe routier (Polars)."""
    rows = execute_query("""
        SELECT properties_twgid, lat, lon
        FROM gold.dim_spatial_grid_mapping
        WHERE lat IS NOT NULL
          AND lon IS NOT NULL
    """)
    df = pl.DataFrame(
        [{"properties_twgid": r["properties_twgid"], "lat": float(r["lat"]), "lon": float(r["lon"])} for r in rows],
        schema_overrides={
            "properties_twgid": pl.Utf8,
            "lat": pl.Float64,
            "lon": pl.Float64,
        },
    )
    logger.info("Loaded %d twgid nodes (Polars)", df.height)
    return df


def _add_h3_index(df: pl.DataFrame) -> pl.DataFrame:
    """Ajoute colonne h3_cell — utilise l'API vectorisée de h3-py v4.5+.

    Sprint 10+ fix : avant on itérait row-par-row (1 appel Python par
    cellule, ~10× plus lent). Maintenant ``h3.latlng_to_cell`` accepte
    directement des arrays numpy et retourne un array, le tout en C.
    """
    lat_arr = df["lat"].to_numpy()
    lon_arr = df["lon"].to_numpy()
    cells = h3.latlng_to_cell(lat_arr, lon_arr, H3_RES)
    return df.with_columns(pl.Series("h3_cell", cells))


def _expand_k_ring(df: pl.DataFrame) -> pl.DataFrame:
    """Explose les h3_cell en k_ring(K_RING) — chaque nœud → 7 cellules.

    Sprint 10+ fix : ``h3.grid_disk`` est aussi vectorisé en v4.5+.
    """
    cells = df["h3_cell"].to_numpy()
    # grid_disk vectorisé : retourne un array d'array
    disks = h3.grid_disk(cells, K_RING)
    return (
        df.with_columns(
            pl.Series("h3_cell_kr", list(disks))  # pl.Series auto-détecte List
        )
        .select(["properties_twgid", "twgid_lat", "twgid_lon", "h3_cell_kr"])
        .explode("h3_cell_kr")
        .rename({"h3_cell_kr": "h3_cell"})
    )


def _build_mapping(lyo: pl.DataFrame, twgid: pl.DataFrame) -> pl.DataFrame:
    """Hash join H3 + calcul distance haversine pour tri."""
    logger.info("Computing H3 index for LYO...")
    lyo_h3 = _add_h3_index(lyo)
    logger.info("Computing H3 index for twgid + k_ring(%d)...", K_RING)
    twgid_h3 = _add_h3_index(twgid).rename({"lat": "twgid_lat", "lon": "twgid_lon"})
    twgid_expanded = _expand_k_ring(twgid_h3)

    # Hash join vectorisé (Polars) — O(N+M) sur les cellules
    # Polars ne supporte pas `suffix=` comme pandas, on rename manuellement.
    lyo_h3_renamed = lyo_h3.rename(
        {
            "channel_id": "channel_id_lyo",
            "lat": "lyo_lat",
            "lon": "lyo_lon",
        }
    )
    joined = twgid_expanded.join(lyo_h3_renamed, on="h3_cell", how="inner")
    # Dédup : 1 channel_id par properties_twgid (premier match)
    # On garde la distance minimale si dispo
    if joined.is_empty():
        logger.warning("No matches found")
        return joined

    joined = joined.with_columns(
        # Distance haversine approx (suffit pour tie-break, pas critique)
        (
            2
            * 6371000
            * (
                (pl.col("twgid_lat").radians() - pl.col("lyo_lat").radians()).sin() ** 2
                + pl.col("twgid_lat").radians().cos()
                * pl.col("lyo_lat").radians().cos()
                * (pl.col("twgid_lon").radians() - pl.col("lyo_lon").radians()).sin() ** 2
            )
            .sqrt()
            .arcsin()
        ).alias("distance_m")
    )

    # Garder le match le plus proche par properties_twgid
    result = (
        joined.sort("distance_m")
        .unique(subset=["properties_twgid"], keep="first")
        .select(
            [
                "properties_twgid",
                "twgid_lat",
                "twgid_lon",
                pl.col("channel_id_lyo").alias("channel_id"),
                "lyo_lat",
                "lyo_lon",
                "distance_m",
            ]
        )
    )
    logger.info(
        "Mapping built: %d unique twgid ↔ lyo (mean dist %.1fm, max %.1fm)",
        result.height,
        result["distance_m"].mean() or 0,
        result["distance_m"].max() or 0,
    )
    return result


def _persist(mapping: pl.DataFrame) -> int:
    """TRUNCATE + INSERT batch en Postgres via execute_values."""
    if mapping.is_empty():
        return 0
    execute_query("TRUNCATE TABLE gold.mv_twgid_to_lyo")
    rows = [tuple(r) for r in mapping.iter_rows()]
    with raw_connection() as conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO gold.mv_twgid_to_lyo (
                properties_twgid, twgid_lat, twgid_lon,
                channel_id, lyo_lat, lyo_lon, distance_m
            ) VALUES %s
            """,
            rows,
            template=None,
            page_size=500,
        )
    return len(rows)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    _create_table_if_not_exists()
    lyo = _load_lyo()
    twgid = _load_twgid()
    if lyo.is_empty() or twgid.is_empty():
        logger.warning("Empty source data — abort")
        return 0
    mapping = _build_mapping(lyo, twgid)
    n = _persist(mapping)
    logger.info("DONE: %d rows inserted in gold.mv_twgid_to_lyo", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
