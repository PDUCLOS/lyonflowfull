"""Transforms Bronze → Silver.

Pour chaque source Bronze, crée/met à jour la table Silver correspondante.
- Dédup DISTINCT ON (channel_id, measurement_time)
- Parsing JSON → colonnes typées
- Géométrie WGS84 + Lamb93 (si applicable)
- Validation métier

Usage :
    from src.transformation.bronze_to_silver import transform_to_silver
    transform_to_silver(source="trafic_boucles")
"""

from __future__ import annotations

import logging

from src.db import raw_connection

logger = logging.getLogger(__name__)


def transform_to_silver(source: str, dry_run: bool = False) -> int:
    """Transform Bronze → Silver pour une source donnée.

    Args:
        source: 'trafic_boucles' | 'velov' | 'tcl_vehicles' | 'meteo' | 'chantiers'
        dry_run: si True, ne fait que logger ce qui serait fait.

    Returns:
        Nombre de lignes transformées.
    """
    transformers = {
        "trafic_boucles": _transform_trafic_boucles,
        "velov": _transform_velov,
        "tcl_vehicles": _transform_tcl_vehicles,
        "meteo": _transform_meteo,
        "chantiers": _transform_chantiers,
    }
    fn = transformers.get(source)
    if not fn:
        raise ValueError(f"Source inconnue: {source}")
    if dry_run:
        logger.info(f"[DRY-RUN] Transform {source} skipped")
        return 0
    return fn()


def _transform_trafic_boucles() -> int:
    """Bronze.trafic_boucles → silver.trafic_boucles_clean."""
    with raw_connection() as conn, conn.cursor() as cur:
        # 1. Lire Bronze non encore transformés (ou tous, idempotent)
        cur.execute("""
                SELECT id, fetched_at, raw_data
                FROM bronze.trafic_boucles
                ORDER BY fetched_at DESC
                LIMIT 10000
            """)
        rows = cur.fetchall()

        n_inserted = 0
        seen = set()
        for _id, fetched_at, raw_data in rows:
            # Parse la FeatureCollection GeoJSON
            if not isinstance(raw_data, dict):
                continue
            features = raw_data.get("features", [])
            for feat in features:
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})

                channel_id = props.get("id") or props.get("gid")
                if not channel_id:
                    continue
                measurement_time = fetched_at.replace(tzinfo=None) if fetched_at else None
                if not measurement_time:
                    continue

                # Dédup
                key = (channel_id, measurement_time)
                if key in seen:
                    continue
                seen.add(key)

                vitesse = props.get("vitesse")
                etat = props.get("etat")
                importance = props.get("importance")

                # Géométrie LineString WKT
                geom_wkt = None
                if geom.get("type") == "LineString":
                    coords = geom.get("coordinates", [])
                    if coords:
                        wkt_coords = ", ".join(f"{c[0]} {c[1]}" for c in coords)
                        geom_wkt = f"LINESTRING({wkt_coords})"

                try:
                    cur.execute(
                        """
                            INSERT INTO silver.trafic_boucles_clean
                                (measurement_time, channel_id, vitesse_kmh, etat,
                                 importance_code, geom_wgs84)
                            VALUES (%s, %s, %s, %s, %s,
                                CASE WHEN %s IS NOT NULL
                                     THEN ST_GeomFromText(%s, 4326)
                                     ELSE NULL END)
                            ON CONFLICT (channel_id, measurement_time) DO UPDATE
                            SET vitesse_kmh = EXCLUDED.vitesse_kmh,
                                etat = EXCLUDED.etat,
                                importance_code = EXCLUDED.importance_code
                        """,
                        (
                            measurement_time,
                            channel_id,
                            vitesse,
                            etat,
                            importance,
                            geom_wkt,
                            geom_wkt,
                        ),
                    )
                    n_inserted += 1
                except Exception as e:
                    logger.warning(f"Skip feature {channel_id}: {e}")
                    continue

        logger.info(f"Silver trafic_boucles: {n_inserted} rows inserted/updated")
        return n_inserted


def _transform_velov() -> int:
    """Bronze.velov → silver.velov_clean."""
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("""
                SELECT id, fetched_at, raw_data
                FROM bronze.velov
                ORDER BY fetched_at DESC
                LIMIT 5000
            """)
        rows = cur.fetchall()

        n_inserted = 0
        seen = set()
        for _id, fetched_at, raw_data in rows:
            if not isinstance(raw_data, dict):
                continue
            stations = raw_data.get("data", {}).get("stations", []) or raw_data.get("stations", [])
            for st in stations:
                sid = st.get("station_id")
                if not sid:
                    continue
                key = (sid, fetched_at)
                if key in seen:
                    continue
                seen.add(key)

                try:
                    cur.execute(
                        """
                            INSERT INTO silver.velov_clean
                                (fetched_at, station_id, station_name, bikes_available,
                                 stands_available, is_installed, is_renting, is_returning,
                                 lat, lon)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (station_id, fetched_at) DO UPDATE
                            SET bikes_available = EXCLUDED.bikes_available,
                                stands_available = EXCLUDED.stands_available
                        """,
                        (
                            fetched_at,
                            sid,
                            st.get("name", ""),
                            st.get("num_bikes_available", 0),
                            st.get("num_docks_available", 0),
                            st.get("is_installed", 1) == 1,
                            st.get("is_renting", 1) == 1,
                            st.get("is_returning", 1) == 1,
                            st.get("lat"),
                            st.get("lon"),
                        ),
                    )
                    n_inserted += 1
                except Exception as e:
                    logger.warning(f"Skip Vélov station {sid}: {e}")

        logger.info(f"Silver velov: {n_inserted} rows inserted/updated")
        return n_inserted


def _transform_tcl_vehicles() -> int:
    """Bronze.tcl_vehicles → silver.tcl_vehicles_clean."""
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("""
                SELECT id, fetched_at, raw_data
                FROM bronze.tcl_vehicles
                ORDER BY fetched_at DESC
                LIMIT 5000
            """)
        rows = cur.fetchall()

        n_inserted = 0
        seen = set()
        for _id, fetched_at, raw_data in rows:
            if not isinstance(raw_data, dict):
                continue
            # SIRI Lite structure: ServiceDelivery > VehicleMonitoringDelivery > VehicleActivity[]
            delivery = raw_data.get("Siri", {}).get("ServiceDelivery", {}).get("VehicleMonitoringDelivery", [{}])[0]
            activities = delivery.get("VehicleActivity", [])

            for act in activities:
                monitored = act.get("MonitoredVehicleJourney", {})
                vehicle_ref = monitored.get("VehicleRef") or monitored.get("VehicleMode")
                if not vehicle_ref:
                    continue
                key = (vehicle_ref, fetched_at)
                if key in seen:
                    continue
                seen.add(key)

                try:
                    cur.execute(
                        """
                            INSERT INTO silver.tcl_vehicles_clean
                                (fetched_at, vehicle_ref, line_ref, direction_ref,
                                 delay_seconds, latitude, longitude, monitored)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (vehicle_ref, fetched_at) DO UPDATE
                            SET delay_seconds = EXCLUDED.delay_seconds,
                                line_ref = EXCLUDED.line_ref
                        """,
                        (
                            fetched_at,
                            vehicle_ref,
                            monitored.get("LineRef"),
                            monitored.get("DirectionRef"),
                            monitored.get("Delay", 0),
                            monitored.get("VehicleLocation", {}).get("Latitude"),
                            monitored.get("VehicleLocation", {}).get("Longitude"),
                            True,
                        ),
                    )
                    n_inserted += 1
                except Exception as e:
                    logger.warning(f"Skip TCL vehicle {vehicle_ref}: {e}")

        logger.info(f"Silver tcl_vehicles: {n_inserted} rows inserted/updated")
        return n_inserted


def _transform_meteo() -> int:
    """Bronze.meteo → silver.meteo_hourly."""
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("""
                SELECT id, fetched_at, raw_data
                FROM bronze.meteo
                ORDER BY fetched_at DESC
                LIMIT 200
            """)
        rows = cur.fetchall()

        n_inserted = 0
        for _id, _fetched_at, raw_data in rows:
            if not isinstance(raw_data, dict):
                continue
            hourly = raw_data.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            hums = hourly.get("relative_humidity_2m", [])
            rains = hourly.get("precipitation", [])
            winds = hourly.get("wind_speed_10m", [])
            codes = hourly.get("weather_code", [])

            for i, t in enumerate(times):
                try:
                    cur.execute(
                        """
                            INSERT INTO silver.meteo_hourly
                                (measurement_time, temperature_c, humidity_pct,
                                 rain_mm, wind_kmh, weather_code)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (measurement_time) DO UPDATE
                            SET temperature_c = EXCLUDED.temperature_c,
                                rain_mm = EXCLUDED.rain_mm
                        """,
                        (
                            t,
                            temps[i] if i < len(temps) else None,
                            hums[i] if i < len(hums) else None,
                            rains[i] if i < len(rains) else None,
                            winds[i] if i < len(winds) else None,
                            codes[i] if i < len(codes) else None,
                        ),
                    )
                    n_inserted += 1
                except Exception as e:
                    logger.warning(f"Skip meteo {t}: {e}")

        logger.info(f"Silver meteo: {n_inserted} rows inserted/updated")
        return n_inserted


def _transform_chantiers() -> int:
    """Bronze.chantiers → silver.chantiers_actifs (avec filtrage dates actives)."""
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("""
                SELECT id, fetched_at, raw_data
                FROM bronze.chantiers
                ORDER BY fetched_at DESC
                LIMIT 200
            """)
        rows = cur.fetchall()

        n_inserted = 0
        for _id, _fetched_at, raw_data in rows:
            if not isinstance(raw_data, dict):
                continue
            features = raw_data.get("features", [])
            for feat in features:
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})

                chantier_id = props.get("id")
                if not chantier_id:
                    continue

                date_debut = props.get("date_debut")
                date_fin = props.get("date_fin")
                localisation = props.get("localisation", "")
                impact_lines = props.get("lignes_tcl", "").split(",") if props.get("lignes_tcl") else []

                # Point geometry
                geom_wkt = None
                if geom.get("type") == "Point":
                    coords = geom.get("coordinates", [])
                    if len(coords) == 2:
                        geom_wkt = f"POINT({coords[0]} {coords[1]})"

                try:
                    cur.execute(
                        """
                            INSERT INTO silver.chantiers_actifs
                                (chantier_id, date_debut, date_fin, localisation,
                                 impact_lines, geom_wgs84, updated_at)
                            VALUES (%s, %s, %s, %s, %s,
                                CASE WHEN %s IS NOT NULL
                                     THEN ST_GeomFromText(%s, 4326)
                                     ELSE NULL END,
                                NOW())
                            ON CONFLICT (chantier_id) DO UPDATE
                            SET date_debut = EXCLUDED.date_debut,
                                date_fin = EXCLUDED.date_fin,
                                updated_at = NOW()
                        """,
                        (
                            chantier_id,
                            date_debut,
                            date_fin,
                            localisation,
                            impact_lines,
                            geom_wkt,
                            geom_wkt,
                        ),
                    )
                    n_inserted += 1
                except Exception as e:
                    logger.warning(f"Skip chantier {chantier_id}: {e}")

        logger.info(f"Silver chantiers: {n_inserted} rows inserted/updated")
        return n_inserted
