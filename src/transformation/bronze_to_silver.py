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

import contextlib
import logging
import re
from datetime import UTC, datetime, timedelta

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


def _parse_grandlyon_vitesse(raw: object) -> float | None:
    """Parse la nouvelle forme WFS Grand Lyon v3 (2026+).

    Exemples acceptés :
      - "18 km/h"        → 18.0
      - "56.5 km/h"      → 56.5
      - "Vitesse réglementaire"  → None (capteur en vitesse libre, vitesse_kmh inconnue)
      - "" / None        → None

    Returns:
        Vitesse en km/h (float) ou None si non exploitable.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    s = raw.strip()
    if not s:
        return None
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*km/h", s)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def _transform_trafic_boucles() -> int:
    """Bronze.trafic_boucles → silver.trafic_boucles_clean.

    Nouveau format WFS Grand Lyon (juin 2026+) :
      - props["code"]      : channel_id (ex. "LYO02336")  ← source de vérité
      - props["gid"]       : identifiant numérique interne
      - props["twgid"]     : identifiant numérique (utilisé par dim_spatial_grid_mapping)
      - props["etat"]      : code 1 char — G (vert), V (orange), R (rouge)
      - props["vitesse"]   : "18 km/h" (mesurée) ou "Vitesse réglementaire" (libre)
      - props["est_a_jour"]: bool — on garde seulement les capteurs frais
      - props["sens"], props["libelle"], props["longueur"], props["fournisseur"]

    Schéma silver v0.3.1 :
      channel_id, measurement_time, vitesse_kmh, vitesse_limite_kmh,
      is_sanitary, geom (4326), geom_2154, silver_updated_at

    Performance : le DAG tourne toutes les 5 min, on ne process donc que les
    5 dernières minutes de bronze (1 cycle) pour rester < 1 minute runtime.
    """
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("""
                SELECT id, fetched_at, raw_data
                FROM bronze.trafic_boucles
                WHERE fetched_at > NOW() - INTERVAL '5 minutes'
                ORDER BY fetched_at DESC
                LIMIT 200
            """)
        rows = cur.fetchall()

        n_inserted = 0
        seen: set[tuple[str, object]] = set()
        for _id, fetched_at, raw_data in rows:
            if not isinstance(raw_data, dict):
                continue
            features = raw_data.get("features", [])
            for feat in features:
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})

                channel_id = props.get("code")
                if not channel_id:
                    continue

                measurement_time = fetched_at.replace(tzinfo=None) if fetched_at else None
                if not measurement_time:
                    continue

                key = (channel_id, measurement_time)
                if key in seen:
                    continue
                seen.add(key)

                vitesse_kmh = _parse_grandlyon_vitesse(props.get("vitesse"))
                vitesse_limite_kmh = 50.0  # Lyon intra-muros
                is_sanitary_flag = bool(props.get("est_a_jour", False))

                geom_wkt = None
                if geom.get("type") == "LineString":
                    coords = geom.get("coordinates", [])
                    if coords:
                        # silver.trafic_boucles_clean.geom est typé geometry(Point, 4326)
                        # (contrainte schema legacy) — on ne peut pas y stocker
                        # un LineString directement. Workaround : on prend le
                        # point médian du segment. Cela donne une position
                        # approximative du capteur (centre du tronçon routier).
                        # TODO Sprint 10 : modifier le schéma pour passer en
                        # geometry(LineString, 4326) (ou geometry générique) et
                        # stocker le segment complet.
                        mid = coords[len(coords) // 2]
                        geom_wkt = f"POINT({mid[0]} {mid[1]})"

                cur.execute("SAVEPOINT sp_trafic")
                try:
                    cur.execute(
                        """
                            INSERT INTO silver.trafic_boucles_clean
                                (channel_id, measurement_time,
                                 vitesse_kmh, vitesse_limite_kmh,
                                 is_sanitary, geom, geom_2154,
                                 silver_updated_at)
                            VALUES (%s, %s, %s, %s, %s,
                                CASE WHEN %s IS NOT NULL
                                     THEN ST_GeomFromText(%s, 4326)
                                     ELSE NULL END,
                                CASE WHEN %s IS NOT NULL
                                     THEN ST_Transform(
                                            ST_GeomFromText(%s, 4326), 2154)
                                     ELSE NULL END,
                                NOW())
                            ON CONFLICT (channel_id, measurement_time) DO UPDATE
                            SET vitesse_kmh       = EXCLUDED.vitesse_kmh,
                                vitesse_limite_kmh= EXCLUDED.vitesse_limite_kmh,
                                is_sanitary       = EXCLUDED.is_sanitary,
                                geom              = EXCLUDED.geom,
                                geom_2154         = EXCLUDED.geom_2154,
                                silver_updated_at = NOW()
                        """,
                        (
                            channel_id,
                            measurement_time,
                            vitesse_kmh,
                            vitesse_limite_kmh,
                            is_sanitary_flag,
                            geom_wkt,
                            geom_wkt,
                            geom_wkt,
                            geom_wkt,
                        ),
                    )
                    cur.execute("RELEASE SAVEPOINT sp_trafic")
                    n_inserted += 1
                except Exception as e:
                    # Rollback au savepoint : annule juste l'INSERT foireux,
                    # pas toute la transaction. On garde tous les autres
                    # inserts valides.
                    try:
                        cur.execute("ROLLBACK TO SAVEPOINT sp_trafic")
                    except Exception:
                        pass
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
                                (fetched_at, measurement_time, station_id, station_name,
                                 num_bikes_available, num_docks_available, is_active,
                                 lat, lon)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (station_id, measurement_time) DO UPDATE
                            SET num_bikes_available = EXCLUDED.num_bikes_available,
                                num_docks_available = EXCLUDED.num_docks_available,
                                is_active = EXCLUDED.is_active
                        """,
                        (
                            fetched_at,
                            fetched_at,  # measurement_time = fetched_at (GBFS pas de timestamp station-level)
                            sid,
                            st.get("name", ""),
                            st.get("num_bikes_available", 0),
                            st.get("num_docks_available", 0),
                            bool(
                                st.get("is_installed", 1) == 1
                                and st.get("is_renting", 1) == 1
                                and st.get("is_returning", 1) == 1
                            ),
                            st.get("lat"),
                            st.get("lon"),
                        ),
                    )
                    n_inserted += 1
                except Exception as e:
                    logger.warning(f"Skip Vélov station {sid}: {e}")

        logger.info(f"Silver velov: {n_inserted} rows inserted/updated")
        return n_inserted


def _parse_siri_delay(raw_delay) -> int:
    """Parse SIRI Delay: integer seconds or ISO 8601 duration (PT2M30S)."""
    if raw_delay is None:
        return 0
    if isinstance(raw_delay, (int, float)):
        return int(raw_delay)
    s = str(raw_delay).strip()
    if not s.startswith("PT"):
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 0
    total = 0
    s = s[2:]
    for unit, factor in [("H", 3600), ("M", 60), ("S", 1)]:
        if unit in s:
            val, s = s.split(unit, 1)
            with contextlib.suppress(ValueError, TypeError):
                total += int(float(val)) * factor
    return total


def _siri_ref(node: object) -> str | None:
    """SIRI 2.0 (juin 2026+) : les refs (LineRef, VehicleRef, StopPointRef, ...)
    sont des objets ``{"value": "ActIV:..."}`` au lieu de strings brutes.

    Cette fonction extrait la string de value, ou None si structure inattendue.
    """
    if node is None:
        return None
    if isinstance(node, str):
        return node or None
    if isinstance(node, dict):
        v = node.get("value")
        if isinstance(v, str) and v:
            return v
    return None


def _transform_tcl_vehicles() -> int:
    """Bronze.tcl_vehicles -> silver.tcl_vehicles_clean.

    Schema silver : UNIQUE (line_ref, journey_ref, stop_ref, measurement_time).

    Nouveau format SIRI 2.0 (juin 2026+) : LineRef, VehicleRef, DirectionRef,
    StopPointRef sont des objets ``{"value": "..."}`` et non plus des strings.
    Ancien code ``mvj.get("LineRef")`` retournait un dict, qui passait la garde
    ``if not line_ref`` (dict truthy) puis crashait à l'INSERT TEXT.
    """
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute("""
                SELECT id, fetched_at, raw_data
                FROM bronze.tcl_vehicles
                ORDER BY fetched_at DESC
                LIMIT 5000
            """)
        rows = cur.fetchall()

        n_inserted = 0
        seen: set[tuple[str, str, str, object]] = set()
        for _id, fetched_at, raw_data in rows:
            if not isinstance(raw_data, dict):
                continue
            delivery = (
                raw_data.get("Siri", {})
                .get("ServiceDelivery", {})
                .get("VehicleMonitoringDelivery", [{}])[0]
            )
            activities = delivery.get("VehicleActivity", [])
            if not activities:
                continue

            for act in activities:
                mvj = act.get("MonitoredVehicleJourney", {})

                line_ref = _siri_ref(mvj.get("LineRef"))
                if not line_ref:
                    continue

                fvj = mvj.get("FramedVehicleJourneyRef") or {}
                journey_ref = (
                    fvj.get("DatedVehicleJourneyRef")
                    if isinstance(fvj, dict)
                    else None
                ) or _siri_ref(mvj.get("VehicleRef")) or "unknown"

                call = mvj.get("MonitoredCall") or {}
                stop_ref = _siri_ref(call.get("StopPointRef")) or "unknown"

                key = (line_ref, journey_ref, stop_ref, fetched_at)
                if key in seen:
                    continue
                seen.add(key)

                delay_s = _parse_siri_delay(mvj.get("Delay"))
                loc = mvj.get("VehicleLocation") or {}
                direction_ref = _siri_ref(mvj.get("DirectionRef"))

                try:
                    cur.execute(
                        """
                            INSERT INTO silver.tcl_vehicles_clean
                                (fetched_at, measurement_time, line_ref,
                                 direction_ref, journey_ref, stop_ref,
                                 delay_seconds, lat, lon)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (line_ref, journey_ref, stop_ref, measurement_time)
                            DO UPDATE SET
                                delay_seconds = EXCLUDED.delay_seconds,
                                fetched_at    = EXCLUDED.fetched_at
                        """,
                        (
                            fetched_at,
                            fetched_at,
                            line_ref,
                            direction_ref,
                            journey_ref,
                            stop_ref,
                            delay_s,
                            loc.get("Latitude") if isinstance(loc, dict) else None,
                            loc.get("Longitude") if isinstance(loc, dict) else None,
                        ),
                    )
                    n_inserted += 1
                except Exception as e:
                    logger.warning("Skip TCL %s/%s: %s", line_ref, journey_ref, e)

        logger.info("Silver tcl_vehicles: %d rows inserted/updated", n_inserted)
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
