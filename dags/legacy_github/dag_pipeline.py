"""
================================================================================
dag_pipeline.py — VERSION LEGACY adaptée depuis le repo GitHub
================================================================================

Origine : https://github.com/caroheymes/Architect-IA-final-project/blob/main/dags/dag_pipeline.py
Adapté pour LEADDATA sur VPS (sans cluster Ray) — 2026-06-05.

DIFFÉRENCES vs version GitHub :
  1. POSTGRES_HOST défaut = `postgres` (docker network) au lieu de `localhost`
  2. POSTGRES_PASSWORD vide si non défini (fallback sur l'env Airflow container)
  3. Auth WFS : fallback GRANDLYON_USERNAME/GRANDLYON_PASSWORD (cf. collect_pvotrafic)
     puis API_LOGIN/API_PASSWORD (cf. repo GitHub)
  4. Task 4 `export_to_csv_task` : utilise `dags.utils.export_db_to_csv` (stub
     local), pas l'export Ray du repo GitHub.
  5. Task 5 `trigger_stgcn_prediction_on_ray` : tente Ray avec timeout court ;
     si Ray indisponible, log un warning et réussit (degraded mode).
  6. Schémas DB : AUCUNE migration nécessaire — les 5 tables cibles
     (`bronze.trafic_vitesse_brute`, `silver.trafic_vitesse_propre`,
     `gold.{dim_spatial_grid_mapping, dim_gnn_adjacency, fact_traffic_series}`)
     existent déjà dans LEADDATA avec les schémas attendus.

PIPELINE (5 tasks, séquentiel) :
  ingest_grand_lyon_traffic
    → spatial_transformation_and_mapping
    → materialize_gold_layer
    → export_gold_to_csv  (CSV local — pas Ray)
    → stgcn_predict_on_ray  (skip silencieux si pas de Ray)

FRÉQUENCE : toutes les 5 min (cf. repo GitHub).

NOTE ML : ce DAG est PARALLÈLE à la chaîne LEADDATA standard
(bronze.trafic_boucles → silver.trafic_boucles_clean → gold.traffic_features_live
→ dag_live_speed_retrain XGBoost). Il ne remplace rien, il ajoute une
deuxième voie d'ingestion/vérification basée sur le WFS Grand Lyon direct.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

import h3
import numpy as np
import pandas as pd
import pyproj
import pytz
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from geopandas import GeoDataFrame
from shapely.geometry import LineString, Polygon, shape
from shapely.ops import transform
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIG — adaptée pour LEADDATA / VPS
# =============================================================================

API_URL = (
    "https://data.grandlyon.com/geoserver/metropole-de-lyon/ows"
    "?SERVICE=WFS&VERSION=2.0.0&request=GetFeature"
    "&typename=metropole-de-lyon:pvo_patrimoine_voirie.pvotrafic"
    "&outputFormat=application/json&SRSNAME=EPSG:2154&startIndex=0&sortby=gid"
)
# Authentification WFS Grand Lyon.
# Ordre de priorité : API_LOGIN/API_PASSWORD (repo GitHub)
#                    > GRANDLYON_USERNAME/GRANDLYON_PASSWORD (LEADDATA standard)
#                    > vide (WFS public sans auth)
API_LOGIN = os.getenv("API_LOGIN") or os.getenv("GRANDLYON_USERNAME", "")
API_PASSWORD = os.getenv("API_PASSWORD") or os.getenv("GRANDLYON_PASSWORD", "")

DB_USER = os.getenv("POSTGRES_USER", "lyonflow")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")  # docker network (LEADDATA)
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_DB = os.getenv("POSTGRES_DB", "lyonflow")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_DB}"
OUTPUT_DIR = "/opt/airflow/data"


# =============================================================================
# HELPERS — identiques au repo GitHub
# =============================================================================

def transform_line_to_point(ligne_2154):
    """Échantillonne une LineString Shapely en points équidistants de 7 mètres (Lambert-93 → WGS84)."""
    if not ligne_2154 or ligne_2154.is_empty:
        return []
    proj_vers_4326 = pyproj.Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True).transform
    distances = np.arange(0, ligne_2154.length, 7)
    points = [ligne_2154.interpolate(d) for d in distances]
    if ligne_2154.length % 7 != 0:
        points.append(ligne_2154.interpolate(ligne_2154.length))
    points = [transform(proj_vers_4326, p) for p in points]
    return points


def create_merged_polygon_from_hexes(h3_id_list):
    """Fusionne un ensemble de cellules H3 en un polygone Shapely unique. Supporte h3 v3 + v4."""
    if not h3_id_list:
        return None
    unique_hexes = list(set(h3_id_list))
    try:
        # h3 v4 (>=4.0) — utilisé sur LEADDATA (h3==4.5.0)
        if hasattr(h3, "cells_to_geo"):
            geojson_dict = h3.cells_to_geo(unique_hexes)
            return shape(geojson_dict)
        elif hasattr(h3, "cells_to_geojson"):
            geojson_dict = h3.cells_to_geojson(unique_hexes)
            return shape(geojson_dict)
        else:
            polygons = []
            for h in unique_hexes:
                boundary = h3.cell_to_boundary(h)
                polygons.append(Polygon([(lon, lat) for lat, lon in boundary]))
            from shapely.ops import unary_union
            return unary_union(polygons)
    except Exception as e:
        logger.error("Error merging H3 hexagons: %s", e)
        return None


def get_speed_category(speed):
    """Catégorise une vitesse (km/h) en libellé lisible."""
    if pd.isna(speed):
        return "Unknown"
    elif speed <= 20:
        return "Slow (0-20 km/h)"
    elif speed > 50:
        return "Fast (>50 km/h)"
    else:
        return "Medium (20-50 km/h)"


# =============================================================================
# TASK 1 — Ingestion WFS Grand Lyon → bronze.trafic_vitesse_brute
# =============================================================================

def ingest_traffic_data(**context):
    """Ingestion temps réel depuis l'API WFS Grand Lyon (pvotrafic).

    Auth : basic auth. Si vide, requête anonyme (le WFS pvotrafic est public).
    Idempotence : le scheduler Airflow garantit un run_id unique par schedule ;
    chaque run insère 1 ligne dans bronze.trafic_vitesse_brute avec son fetched_at.
    """
    logger.info("Starting real-time traffic data ingestion...")
    try:
        response = requests.get(API_URL, auth=(API_LOGIN, API_PASSWORD), timeout=30)
        response.raise_for_status()
        raw_payload = response.json()
        logger.info("Successfully fetched data from Grand Lyon WFS API.")
    except requests.exceptions.RequestException as e:
        logger.error("Error querying Grand Lyon API: %s", e)
        raise Exception(f"Ingestion failed: {e}")

    timezone = pytz.timezone("Europe/Paris")
    fetched_at = datetime.now(timezone)

    logger.info("Connecting to PostgreSQL container...")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            # Schéma et table créés par init-db.sql — on s'assure juste qu'ils existent
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS bronze;"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bronze.trafic_vitesse_brute (
                    id SERIAL PRIMARY KEY,
                    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    raw_data JSONB NOT NULL
                );
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_bronze_fetched_at
                ON bronze.trafic_vitesse_brute (fetched_at DESC);
            """))
            logger.info("Inserting raw payload to bronze.trafic_vitesse_brute...")
            conn.execute(
                text("INSERT INTO bronze.trafic_vitesse_brute (fetched_at, raw_data) VALUES (:fetched_at, :raw_data);"),
                {"fetched_at": fetched_at, "raw_data": json.dumps(raw_payload)},
            )
        logger.info("Ingestion successfully saved to bronze at %s", fetched_at.isoformat())
    finally:
        engine.dispose()


# =============================================================================
# TASK 2 — Bronze → Silver (H3 res 13, LineString sampling 7m)
# =============================================================================

def transform_traffic_data(**context):
    """Bronze → silver.trafic_vitesse_propre.

    Échantillonne chaque LineString tous les 7m, indexe en H3 res 13, agrège
    par capteur avec fallback moyenne historique, catégorise la vitesse, et
    APPEND dans silver (idempotent : la PK est (transformed_at, properties_twgid)).
    """
    logger.info("Starting spatial data transformation...")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            logger.info("Fetching the latest raw record from bronze layer...")
            query = text("""
                SELECT raw_data FROM bronze.trafic_vitesse_brute
                ORDER BY fetched_at DESC LIMIT 1;
            """)
            result = conn.execute(query).fetchone()

        if not result:
            logger.warning("No data found in bronze.trafic_vitesse_brute. Cannot transform.")
            return

        raw_payload = result[0]
        features = raw_payload.get("features", [])
        if not features:
            logger.warning("Source payload contains no features.")
            return

        trafic = pd.json_normalize(features)
        cols = [c.replace(".", "_") for c in trafic.columns]
        trafic.columns = cols

        selected_columns = [
            "geometry_coordinates", "properties_libelle", "properties_sens",
            "properties_etat", "properties_vitesse", "properties_last_update",
            "properties_est_a_jour", "properties_twgid", "properties_gid",
        ]
        for col in selected_columns:
            if col not in trafic.columns:
                trafic[col] = None
        trafic = trafic[selected_columns]
        if "properties_est_a_jour" in trafic.columns:
            trafic = trafic[trafic.properties_est_a_jour != False]

        trafic["geometry_coordinates_obj"] = trafic["geometry_coordinates"].apply(LineString)
        gdf = GeoDataFrame(data=trafic, geometry="geometry_coordinates_obj")
        gdf.set_crs(epsg=2154, inplace=True, allow_override=True)

        logger.info("Interpolating segments every 7 meters...")
        gdf["points"] = [transform_line_to_point(elem) for elem in gdf.geometry_coordinates_obj]

        logger.info("Mapping interpolated coordinates to H3 resolution 13 cells...")
        gdf["hexes"] = gdf.points.apply(lambda pts: [h3.latlng_to_cell(p.y, p.x, 13) for p in pts])

        logger.info("Unifying H3 cell clusters into polygons...")
        gdf["merged_h3_geometry"] = gdf["hexes"].apply(create_merged_polygon_from_hexes)

        gdf["properties_vitesse"] = gdf["properties_vitesse"].astype(str).str.split(" ").str[0]
        gdf["properties_vitesse"] = pd.to_numeric(gdf["properties_vitesse"], errors="coerce")

        mean_speed_df = (
            gdf.groupby(by="properties_libelle").agg(mean_speed=("properties_vitesse", "mean")).reset_index()
        )
        gdf = gdf.merge(mean_speed_df, on="properties_libelle", how="left")
        gdf["properties_vitesse"] = [
            elem if not pd.isna(elem) else mean_speed if not pd.isna(mean_speed) else np.nan
            for elem, mean_speed in zip(gdf.properties_vitesse, gdf.mean_speed)
        ]
        gdf = gdf.drop(columns=["mean_speed"], errors="ignore")

        gdf["speed_category"] = [get_speed_category(speed) for speed in gdf.properties_vitesse]
        gdf["speed_color_map"] = gdf["speed_category"].map(
            {"Slow (0-20 km/h)": "red", "Medium (20-50 km/h)": "orange",
             "Fast (>50 km/h)": "green", "Unknown": "gray"}
        )

        gdf_wgs84 = gdf.to_crs(epsg=4326)
        gdf["id_rue"] = gdf.index

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        # EXPORTS CSV/JSON DÉSACTIVÉS (commit fix(dags): disable-csv-export)
        # Cause: 22G de {csv,json}/2026_*_transformed.* en 2j, pas de rotation.
        # df_csv.to_csv(...) et gdf_wgs84_copy.to_file(...) commentés.
        gdf_wgs84_copy = gdf_wgs84.copy()
        gdf_wgs84_copy["points"] = gdf_wgs84_copy["points"].apply(lambda lst: [[p.x, p.y] for p in lst] if lst else [])
        gdf_wgs84_copy["merged_h3_geometry"] = gdf_wgs84_copy["merged_h3_geometry"].apply(
            lambda x: x.__geo_interface__ if x else None
        )

        logger.info("Formatting data and pushing to PostgreSQL silver schema...")
        df_silver = pd.DataFrame(gdf_wgs84_copy)
        df_silver["id_rue"] = df_silver.index
        df_silver["geometry_wgs84_wkt"] = df_silver["geometry_coordinates_obj"].apply(
            lambda geom: geom.wkt if geom else None
        )
        df_silver["points_json"] = df_silver["points"].apply(lambda lst: json.dumps(lst) if lst else None)
        df_silver["hexes_json"] = df_silver["hexes"].apply(lambda lst: json.dumps(lst) if lst else None)
        df_silver["merged_h3_geometry_json"] = df_silver["merged_h3_geometry"].apply(
            lambda d: json.dumps(d) if d else None
        )

        paris_tz = pytz.timezone("Europe/Paris")
        transformed_at_value = datetime.now(paris_tz)
        df_silver["transformed_at"] = transformed_at_value

        columns_to_write = [
            "id_rue", "properties_twgid", "properties_gid", "properties_libelle",
            "properties_sens", "properties_etat", "properties_vitesse",
            "properties_last_update", "properties_est_a_jour",
            "speed_category", "speed_color_map", "geometry_wgs84_wkt",
            "points_json", "hexes_json", "merged_h3_geometry_json", "transformed_at",
        ]
        columns_to_write = [c for c in columns_to_write if c in df_silver.columns]
        df_silver_clean = df_silver[columns_to_write].copy()

        # Dédupliquer sur properties_twgid — la contrainte UNIQUE
        # uq_silver_trafic_vitesse_propre_twgid_ts (twgid, transformed_at) l'exige.
        # Le WFS peut renvoyer plusieurs features pour le même tronçon
        # (ex. 2 sens), ce qui causait la collision "duplicate key value"
        # observée le 2026-06-05. On garde la première occurrence par tronçon.
        before = len(df_silver_clean)
        df_silver_clean = df_silver_clean.drop_duplicates(
            subset=["properties_twgid"], keep="first"
        ).reset_index(drop=True)
        dropped = before - len(df_silver_clean)
        if dropped:
            logger.info("Deduplicated %d rows on properties_twgid (kept first)", dropped)

        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver;"))
            # Idempotence : nettoyer les rows de ce run avant d'insérer.
            # La table a une contrainte UNIQUE uq_silver_trafic_vitesse_propre_twgid_ts
            # sur (properties_twigid, transformed_at) — sans ce DELETE, les retry
            # du scheduler et les chevauchements de timestamps provoqueraient
            # des collisions (cf. erreur "Key already exists" du 2026-06-05).
            deleted = conn.execute(
                text("DELETE FROM silver.trafic_vitesse_propre WHERE transformed_at = :ts"),
                {"ts": transformed_at_value},
            ).rowcount
            logger.info(
                "Cleaned %d existing rows for transformed_at=%s (idempotence)",
                deleted, transformed_at_value.isoformat(),
            )
            logger.info("Appending clean records to silver.trafic_vitesse_propre table...")
            df_silver_clean.to_sql(
                name="trafic_vitesse_propre", con=conn, schema="silver",
                if_exists="append", index=False, chunksize=500,
            )
        logger.info("Successfully pushed transformed data to silver.trafic_vitesse_propre!")
    except Exception as e:
        logger.error("Transformation failed: %s", e)
        raise
    finally:
        engine.dispose()


# =============================================================================
# TASK 3 — Silver → Gold (H3 grid + adjacency + facts)
# =============================================================================

def materialize_gold_layer(**context):
    """Silver → gold.{dim_spatial_grid_mapping, dim_gnn_adjacency, fact_traffic_series}.

    Logique identique au repo GitHub. Tables gold déjà créées par init-db.sql.
    """
    logger.info("Starting Gold layer materialization...")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        # Pas de CREATE TABLE — tables déjà créées par init-db.sql avec le bon schéma
        with engine.begin() as conn:
            logger.info("Scanning silver.trafic_vitesse_propre to identify active sensors...")
            query_stats = """
                SELECT
                    properties_twgid,
                    COUNT(*) as total_measures,
                    SUM(CASE WHEN properties_vitesse IS NULL THEN 1 ELSE 0 END) as null_measures
                FROM silver.trafic_vitesse_propre
                GROUP BY properties_twgid;
            """
            df_stats = pd.read_sql(query_stats, con=engine)

            if df_stats.empty:
                logger.warning("No data found in silver.trafic_vitesse_propre. Cannot proceed.")
                return

            df_stats["nan_percentage"] = (df_stats["null_measures"] / df_stats["total_measures"]) * 100.0
            active_segments = df_stats[df_stats["nan_percentage"] < 90.0]["properties_twgid"].tolist()
            logger.info(
                "Detected %d total segments, with %d active segments (<90%% NaNs).",
                len(df_stats), len(active_segments),
            )

            if not active_segments:
                logger.warning("No active segments found. Cannot proceed to Gold.")
                return

            query_hexes = f"""
                SELECT DISTINCT ON (properties_twgid) properties_twgid, hexes_json
                FROM silver.trafic_vitesse_propre
                WHERE properties_twgid IN ({",".join(["'" + str(s) + "'" for s in active_segments])});
            """
            df_hexes = pd.read_sql(query_hexes, con=conn)

        h3_cells_data = []
        for _, row in df_hexes.iterrows():
            twigid = row["properties_twgid"]
            raw_hexes = row["hexes_json"]
            # Guard: raw_hexes peut être None, str, list, ou np.ndarray selon
            # comment pandas décode le jsonb. On évite pd.isna() sur des
            # collections — ça retourne un array et fait planter l'opérateur
            # `or` (cf. "truth value of array is ambiguous" du 2026-06-05).
            if raw_hexes is None:
                continue
            if isinstance(raw_hexes, (list, np.ndarray)):
                if len(raw_hexes) == 0:
                    continue
                cells = list(raw_hexes)
            elif isinstance(raw_hexes, str):
                if pd.isna(raw_hexes) or not raw_hexes.strip():
                    continue
                cleaned = (
                    raw_hexes.replace("[", "").replace("]", "").replace("'", "")
                    .replace('"', "").replace("\n", " ").replace(",", " ")
                )
                cells = [c.strip() for c in cleaned.split() if c.strip()]
            else:
                cells = []
            for cell in cells:
                if isinstance(cell, str) and len(cell) >= 15:
                    h3_cells_data.append({"properties_twgid": twigid, "h3_id": cell})

        df_h3 = pd.DataFrame(h3_cells_data)
        if df_h3.empty:
            raise ValueError("No valid H3 cells extracted for active sensors.")

        local_origin = df_h3.iloc[0]["h3_id"]

        if hasattr(h3, "cell_to_local_ij"):
            h3_to_ij_func = h3.cell_to_local_ij
        elif hasattr(h3, "experimental_h3_to_local_ij"):
            h3_to_ij_func = h3.experimental_h3_to_local_ij
        else:
            raise AttributeError("Installed H3 library lacks local IJ projection support.")

        coords_i, coords_j, valid_indices = [], [], []
        for idx, row in df_h3.iterrows():
            try:
                ij = h3_to_ij_func(local_origin, row["h3_id"])
                coords_i.append(ij[0])
                coords_j.append(ij[1])
                valid_indices.append(idx)
            except Exception:
                continue

        df_h3_projected = df_h3.iloc[valid_indices].copy()
        df_h3_projected["i"] = coords_i
        df_h3_projected["j"] = coords_j

        min_i, max_i = df_h3_projected["i"].min(), df_h3_projected["i"].max()
        min_j, max_j = df_h3_projected["j"].min(), df_h3_projected["j"].max()
        df_h3_projected["matrix_i"] = (df_h3_projected["i"] - min_i).astype(int)
        df_h3_projected["matrix_j"] = (df_h3_projected["j"] - min_j).astype(int)

        unique_active_twgids = df_h3_projected["properties_twgid"].unique()
        twigid_to_node_idx = {twigid: idx for idx, twigid in enumerate(unique_active_twgids)}

        df_mapping_unique = df_h3_projected.drop_duplicates(subset=["properties_twgid"]).copy()
        df_mapping_unique["node_idx"] = df_mapping_unique["properties_twgid"].map(twigid_to_node_idx)
        df_mapping_unique["updated_at"] = datetime.now(pytz.timezone("Europe/Paris"))

        df_mapping_to_write = df_mapping_unique[
            ["node_idx", "properties_twgid", "matrix_i", "matrix_j", "h3_id", "updated_at"]
        ].copy()

        # Edges (H3 grid_disk K=2)
        cell_to_nodes = {}
        for _, row in df_h3_projected.iterrows():
            twg = row["properties_twgid"]
            if twg in twigid_to_node_idx:
                node_idx = twigid_to_node_idx[twg]
                cell = row["h3_id"]
                cell_to_nodes.setdefault(cell, set()).add(node_idx)

        if hasattr(h3, "grid_disk"):
            get_neighbors_func = h3.grid_disk
        elif hasattr(h3, "k_ring"):
            get_neighbors_func = h3.k_ring
        else:
            raise AttributeError("Installed H3 library lacks neighborhood functions (grid_disk/k_ring).")

        edges = set()
        for cell, nodes in cell_to_nodes.items():
            neighbors = get_neighbors_func(cell, 2)
            for neighbor_cell in neighbors:
                if neighbor_cell in cell_to_nodes:
                    for u in nodes:
                        for v in cell_to_nodes[neighbor_cell]:
                            if u != v:
                                edges.add((min(u, v), max(u, v)))

        df_adjacency = pd.DataFrame(list(edges), columns=["node_u", "node_v"])
        df_adjacency["is_connected"] = True
        df_adjacency["updated_at"] = datetime.now(pytz.timezone("Europe/Paris"))

        # Latest snapshot + imputation
        logger.info("Fetching the latest transformed timestamp from silver...")
        with engine.begin() as conn:
            latest_time_result = conn.execute(
                text("SELECT MAX(transformed_at) FROM silver.trafic_vitesse_propre;")
            ).fetchone()

        if not latest_time_result or not latest_time_result[0]:
            logger.warning("No records found in silver layer. Skipping facts update.")
            return

        latest_timestamp = latest_time_result[0]
        logger.info("Latest timestamp in silver is %s. Fetching snapshot...", latest_timestamp)

        query_snapshot = text("""
            SELECT properties_twgid, properties_vitesse
            FROM silver.trafic_vitesse_propre
            WHERE transformed_at = :latest_time;
        """)
        df_snapshot = pd.read_sql(query_snapshot, con=engine, params={"latest_time": latest_timestamp})

        query_history_avg = """
            SELECT properties_twgid, AVG(properties_vitesse) as avg_vitesse
            FROM silver.trafic_vitesse_propre
            WHERE properties_vitesse IS NOT NULL
            GROUP BY properties_twgid;
        """
        df_history_avg = pd.read_sql(query_history_avg, con=engine)
        history_avg_dict = dict(zip(df_history_avg["properties_twgid"], df_history_avg["avg_vitesse"]))

        snapshot_dict = dict(zip(df_snapshot["properties_twgid"], df_snapshot["properties_vitesse"]))

        gold_facts = []
        for twigid in unique_active_twgids:
            node_idx = twigid_to_node_idx[twigid]
            val = snapshot_dict.get(twigid, np.nan)
            imputed = False
            if pd.isna(val):
                imputed = True
                default_speed = float(os.getenv("LYON_DEFAULT_SPEED", 30.0))
                val = history_avg_dict.get(twigid, default_speed)
                if pd.isna(val):
                    val = default_speed
            gold_facts.append({
                "timestamp": latest_timestamp,
                "node_idx": node_idx,
                "properties_vitesse": float(val),
                "imputed": imputed,
            })

        df_facts = pd.DataFrame(gold_facts)

        logger.info("Writing updates to Gold Layer tables inside a transaction...")
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE gold.dim_spatial_grid_mapping;"))
            df_mapping_to_write.to_sql(
                name="dim_spatial_grid_mapping", con=conn, schema="gold",
                if_exists="append", index=False,
            )
            conn.execute(text("TRUNCATE TABLE gold.dim_gnn_adjacency;"))
            df_adjacency.to_sql(
                name="dim_gnn_adjacency", con=conn, schema="gold",
                if_exists="append", index=False,
            )
            conn.execute(
                text("DELETE FROM gold.fact_traffic_series WHERE timestamp = :latest_time;"),
                {"latest_time": latest_timestamp},
            )
            df_facts.to_sql(
                name="fact_traffic_series", con=conn, schema="gold",
                if_exists="append", index=False, chunksize=500,
            )

        logger.info("Successfully materialized Gold Layer for timestamp %s", latest_timestamp)
        logger.info("   - %d active sensors mapped", len(df_mapping_to_write))
        logger.info("   - %d edges in adjacency table", len(df_adjacency))
        logger.info("   - %d fact records written (%d imputed)", len(df_facts), int(df_facts["imputed"].sum()))
    except Exception as e:
        logger.error("Gold Layer materialization failed: %s", e)
        raise
    finally:
        engine.dispose()


# =============================================================================
# TASK 4 — Export gold → CSV local (stub LEADDATA, pas Ray)
# =============================================================================

# DÉSACTIVÉ — exports CSV/JSON virés, on garde Postgres.
# def export_to_csv_task(**context):
#     from utils.export_db_to_csv import run_export
#     os.environ["DATA_FOLDER"] = "/opt/airflow/project/data/in"
#     os.environ["SEQ_LEN_EXPORT"] = "150"
#     run_export()


# =============================================================================
# TASK 5 — STGCN predict on Ray (RÉSILIENT — graceful skip si pas de Ray)
# =============================================================================

def trigger_stgcn_prediction_on_ray(**context):
    """Soumet un job STGCN au cluster Ray, si disponible.

    Sur LEADDATA, le cluster Ray n'est PAS déployé. Cette task :
      1. Tente un health check rapide sur `RAY_DASHBOARD_URL` (défaut http://ray-head:8265).
      2. Si KO (timeout / connection refused) → log warning et return (skip silencieux).
      3. Si OK → soumet le job, polle jusqu'à terminaison, raise si FAILED.
    """
    import time

    ray_dashboard_url = os.getenv("RAY_DASHBOARD_URL", "http://ray-head:8265")
    submit_url = f"{ray_dashboard_url}/api/jobs/"

    # 1. Health check court (2s) — si Ray absent, on ne perd pas 30s à attendre
    try:
        health = requests.get(f"{ray_dashboard_url}/api/jobs/", timeout=2)
        health.raise_for_status()
    except Exception as e:
        logger.warning(
            "Ray cluster not reachable at %s (%s: %s). "
            "Skipping STGCN prediction. Pour activer : déployer un cluster Ray "
            "et set RAY_DASHBOARD_URL. Le DAG continue sans cette étape.",
            ray_dashboard_url, type(e).__name__, e,
        )
        return  # Graceful degradation

    # 2. Ray disponible — soumettre le job
    payload = {
        "entrypoint": "cd /home/ray/project && python training/stgcn/predict_stgcn.py",
        "runtime_env": {
            "env_vars": {
                "USE_LOCAL_CSV": "false",
                "DATA_FOLDER": "/home/ray/project/data/in",
                "DATA_FOLDER_OUT": "/home/ray/project/data/out",
                "MODEL_PATH": "/home/ray/project/models/stgcn_prod_latest.pt",
                "SCALER_PATH": "/home/ray/project/models/stgcn_scaler.pkl",
                "SEQ_LEN": "120",
                "HORIZONS": "6,12,36",
                "POSTGRES_HOST": "postgres",
                "POSTGRES_PORT": "5432",
                "POSTGRES_USER": os.getenv("POSTGRES_USER", "lyonflow"),
                "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
                "POSTGRES_DB": os.getenv("POSTGRES_DB", "lyonflow"),
            }
        },
    }
    logger.info("Submitting prediction job to Ray at %s...", submit_url)
    response = requests.post(submit_url, json=payload, timeout=30)
    response.raise_for_status()
    job_id = response.json()["job_id"]
    logger.info("Ray job submitted. ID: %s", job_id)

    status_url = f"{ray_dashboard_url}/api/jobs/{job_id}"
    while True:
        time.sleep(10)
        status_resp = requests.get(status_url, timeout=30)
        status_resp.raise_for_status()
        status = status_resp.json()["status"]
        logger.info("Ray job %s status: %s", job_id, status)
        if status == "SUCCEEDED":
            logger.info("Ray STGCN prediction job completed successfully.")
            return
        elif status in ("FAILED", "STOPPED"):
            err = f"Ray STGCN prediction job failed: {status}"
            logger.error(err)
            try:
                logs_resp = requests.get(f"{ray_dashboard_url}/api/jobs/{job_id}/logs", timeout=30)
                if logs_resp.status_code == 200:
                    logger.error("Ray job logs:\n%s", logs_resp.json().get("logs", ""))
            except Exception:
                pass
            raise Exception(err)


# =============================================================================
# DAG
# =============================================================================

default_args = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(seconds=30),
}

with DAG(
    dag_id="lyonflow_traffic_pipeline",
    default_args=default_args,
    description="Legacy GitHub pipeline (adapted to LEADDATA) — Ingest Grand Lyon WFS + spatial H3 + gold + STGCN predict",
    schedule_interval="*/5 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["lyonflow", "legacy-github", "ingest", "transform", "h3", "stgcn"],
) as dag:
    ingest_task = PythonOperator(
        task_id="ingest_grand_lyon_traffic",
        python_callable=ingest_traffic_data,
    )
    transform_task = PythonOperator(
        task_id="spatial_transformation_and_mapping",
        python_callable=transform_traffic_data,
    )
    gold_task = PythonOperator(
        task_id="materialize_gold_layer",
        python_callable=materialize_gold_layer,
    )
    # export_task DÉSACTIVÉ — voir TASK 4 ci-dessus
    predict_task = PythonOperator(
        task_id="stgcn_predict_on_ray",
        python_callable=trigger_stgcn_prediction_on_ray,
    )

    # Flow: ingest → transform → gold → predict (export retiré)
    ingest_task >> transform_task >> gold_task >> predict_task
