"""Transforms Silver → Gold (Features ML-ready).

Pour chaque modèle :
- traffic_features_live : lags, deltas, temporel, météo
- velov_features : station_id label-encoded, lags, rolling means
- bus_delay_segments : agrégation par tronçon/ligne/heure
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.db import raw_connection


logger = logging.getLogger(__name__)


def transform_silver_to_gold(target: str = "all", dry_run: bool = False) -> dict:
    """Transform Silver → Gold pour un ou tous les modèles.

    Args:
        target: 'traffic' | 'velov' | 'bus_delay' | 'all'
        dry_run: si True, ne fait que logger.

    Returns:
        Dict {target: n_rows_inserted}.
    """
    if dry_run:
        logger.info(f"[DRY-RUN] Silver → Gold {target} skipped")
        return {}

    results = {}
    if target in ("traffic", "all"):
        results["traffic"] = _build_traffic_features()
    if target in ("velov", "all"):
        results["velov"] = _build_velov_features()
    if target in ("bus_delay", "all"):
        results["bus_delay"] = _build_bus_delay_segments()
    return results


def _build_traffic_features() -> int:
    """Construit gold.traffic_features_live avec lags/deltas/temporel/météo."""
    with raw_connection() as conn:
        with conn.cursor() as cur:
            # 1. Récupère les points de mesure Silver récents (5 dernières minutes)
            cur.execute("""
                SELECT measurement_time, channel_id, vitesse_kmh
                FROM silver.trafic_boucles_clean
                WHERE measurement_time > NOW() - INTERVAL '1 hour'
                ORDER BY measurement_time DESC
            """)
            rows = cur.fetchall()

            if not rows:
                logger.info("No trafic_boucles_clean data, skipping")
                return 0

            n_inserted = 0
            for measurement_time, channel_id, vitesse in rows:
                # Lookups : nœud GNN, lags, météo
                cur.execute("""
                    SELECT node_idx FROM gold.dim_spatial_grid_mapping
                    WHERE channel_id = %s LIMIT 1
                """, (channel_id,))
                row = cur.fetchone()
                if not row:
                    continue  # Pas de mapping, skip
                node_idx = row[0]

                # Lag 1 (mesure précédente du même capteur)
                cur.execute("""
                    SELECT vitesse_kmh FROM silver.trafic_boucles_clean
                    WHERE channel_id = %s
                      AND measurement_time < %s
                    ORDER BY measurement_time DESC LIMIT 1
                """, (channel_id, measurement_time))
                row = cur.fetchone()
                lag1 = float(row[0]) if row and row[0] is not None else None

                # Rolling mean 5min (5 dernières mesures avant t)
                cur.execute("""
                    SELECT AVG(vitesse_kmh) FROM (
                        SELECT vitesse_kmh FROM silver.trafic_boucles_clean
                        WHERE channel_id = %s
                          AND measurement_time < %s
                          AND measurement_time > %s - INTERVAL '5 minutes'
                        ORDER BY measurement_time DESC LIMIT 5
                    ) AS last5
                """, (channel_id, measurement_time, measurement_time))
                row = cur.fetchone()
                rolling_mean = float(row[0]) if row and row[0] is not None else None

                # Météo la plus proche
                cur.execute("""
                    SELECT temperature_c, rain_mm FROM silver.meteo_hourly
                    WHERE measurement_time <= %s
                    ORDER BY measurement_time DESC LIMIT 1
                """, (measurement_time,))
                row = cur.fetchone()
                temp = row[0] if row else None
                rain = row[1] if row else None

                # Temporel
                h = measurement_time.hour
                d = measurement_time.weekday()
                import math
                h_sin, h_cos = math.sin(2 * math.pi * h / 24), math.cos(2 * math.pi * h / 24)
                d_sin, d_cos = math.sin(2 * math.pi * d / 7), math.cos(2 * math.pi * d / 7)

                delta = (vitesse - lag1) if (vitesse is not None and lag1 is not None) else None

                # Importance code (placeholder — à enrichir)
                importance = "0"

                try:
                    cur.execute("""
                        INSERT INTO gold.traffic_features_live
                            (measurement_time, node_idx, channel_id, speed_kmh,
                             speed_lag_1, speed_lag_2, speed_lag_3, speed_delta_1,
                             rolling_mean_5min, hour_sin, hour_cos, day_sin, day_cos,
                             temperature_c, rain_mm, is_vacances, is_ferie, importance_code)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, FALSE, FALSE, %s)
                        ON CONFLICT (node_idx, measurement_time) DO UPDATE
                        SET speed_kmh = EXCLUDED.speed_kmh,
                            speed_lag_1 = EXCLUDED.speed_lag_1,
                            speed_delta_1 = EXCLUDED.speed_delta_1,
                            rolling_mean_5min = EXCLUDED.rolling_mean_5min
                    """, (
                        measurement_time, node_idx, channel_id, vitesse,
                        lag1, None, None, delta,
                        rolling_mean,
                        h_sin, h_cos, d_sin, d_cos,
                        temp, rain, importance,
                    ))
                    n_inserted += 1
                except Exception as e:
                    logger.warning(f"Skip traffic feature {channel_id}: {e}")

            logger.info(f"Gold traffic_features: {n_inserted} rows inserted/updated")
            return n_inserted


def _build_velov_features() -> int:
    """Construit gold.velov_features avec label encoding + lags."""
    with raw_connection() as conn:
        with conn.cursor() as cur:
            # Label encoder : station_id → integer
            cur.execute("""
                SELECT DISTINCT station_id FROM silver.velov_clean
                ORDER BY station_id
            """)
            stations = [r[0] for r in cur.fetchall()]

            if not stations:
                return 0

            # Map station_id → encoded (0..N-1)
            encoder = {sid: i for i, sid in enumerate(stations)}

            cur.execute("""
                SELECT fetched_at, station_id, bikes_available
                FROM silver.velov_clean
                WHERE fetched_at > NOW() - INTERVAL '1 hour'
                ORDER BY fetched_at DESC
            """)
            rows = cur.fetchall()

            n_inserted = 0
            for fetched_at, station_id, bikes in rows:
                if station_id not in encoder:
                    continue
                station_encoded = encoder[station_id]

                # Lag 1
                cur.execute("""
                    SELECT bikes_available FROM silver.velov_clean
                    WHERE station_id = %s AND fetched_at < %s
                    ORDER BY fetched_at DESC LIMIT 1
                """, (station_id, fetched_at))
                row = cur.fetchone()
                lag1 = row[0] if row else None

                import math
                h = fetched_at.hour
                d = fetched_at.weekday()
                h_sin, h_cos = math.sin(2 * math.pi * h / 24), math.cos(2 * math.pi * h / 24)

                # Météo
                cur.execute("""
                    SELECT temperature_c, rain_mm FROM silver.meteo_hourly
                    WHERE measurement_time <= %s
                    ORDER BY measurement_time DESC LIMIT 1
                """, (fetched_at,))
                row = cur.fetchone()
                temp = row[0] if row else None
                rain = row[1] if row else None

                try:
                    cur.execute("""
                        INSERT INTO gold.velov_features
                            (measurement_time, station_id_encoded, station_id, bikes_available,
                             bikes_lag_1, bikes_lag_2, bikes_lag_3, rolling_mean_3h,
                             hour_sin, hour_cos, temperature_c, rain_mm,
                             is_vacances, is_ferie)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                FALSE, FALSE)
                        ON CONFLICT (station_id_encoded, measurement_time) DO UPDATE
                        SET bikes_available = EXCLUDED.bikes_available,
                            bikes_lag_1 = EXCLUDED.bikes_lag_1
                    """, (
                        fetched_at, station_encoded, station_id, bikes,
                        lag1, None, None, None,
                        h_sin, h_cos, temp, rain,
                    ))
                    n_inserted += 1
                except Exception as e:
                    logger.warning(f"Skip velov feature {station_id}: {e}")

            logger.info(f"Gold velov_features: {n_inserted} rows inserted/updated")
            return n_inserted


def _build_bus_delay_segments() -> int:
    """Construit gold.bus_delay_segments (agrégation par tronçon/ligne/heure)."""
    with raw_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    DATE(fetched_at) AS date,
                    EXTRACT(HOUR FROM fetched_at)::INTEGER AS hour,
                    line_ref,
                    AVG(delay_seconds)::NUMERIC(8,2) AS avg_delay,
                    COUNT(*) AS n_obs
                FROM silver.tcl_vehicles_clean
                WHERE fetched_at > NOW() - INTERVAL '7 days'
                  AND line_ref IS NOT NULL
                GROUP BY DATE(fetched_at), EXTRACT(HOUR FROM fetched_at), line_ref
            """)
            rows = cur.fetchall()

            n_inserted = 0
            for date, hour, line_ref, avg_delay, n_obs in rows:
                try:
                    cur.execute("""
                        INSERT INTO gold.bus_delay_segments
                            (date, hour, line_ref, segment_id, avg_delay_seconds,
                             n_observations, is_vacances, is_ferie, weather_code)
                        VALUES (%s, %s, %s, 'all', %s, %s, FALSE, FALSE, NULL)
                        ON CONFLICT (date, hour, line_ref, segment_id) DO UPDATE
                        SET avg_delay_seconds = EXCLUDED.avg_delay_seconds,
                            n_observations = EXCLUDED.n_observations
                    """, (date, hour, line_ref, avg_delay, n_obs))
                    n_inserted += 1
                except Exception as e:
                    logger.warning(f"Skip bus delay {date} {hour} {line_ref}: {e}")

            logger.info(f"Gold bus_delay_segments: {n_inserted} rows inserted/updated")
            return n_inserted
