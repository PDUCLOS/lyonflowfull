"""Data Governance — dictionnaire de données + lineage + RBAC.

Module de support pour la traçabilité, RGPD, et la documentation automatique.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.db import execute_query


logger = logging.getLogger(__name__)


def register_data_dictionary_entry(
    schema_name: str,
    table_name: str,
    column_name: str,
    data_type: str,
    description: str,
    pii_level: str = "none",
    source: Optional[str] = None,
    example_value: Optional[str] = None,
) -> None:
    """Enregistre/met à jour une entrée du dictionnaire de données.

    Args:
        schema_name: bronze / silver / gold / rgpd / governance
        table_name: nom de la table
        column_name: nom de la colonne
        data_type: TEXT, INTEGER, JSONB, GEOMETRY, etc.
        description: description humaine
        pii_level: 'none' | 'low' | 'medium' | 'high' (classification RGPD)
        source: origine de la donnée (API, calcul, etc.)
        example_value: exemple (anonymisé)
    """
    query = """
        INSERT INTO governance.data_dictionary
            (schema_name, table_name, column_name, data_type, description,
             pii_level, source, example_value, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (schema_name, table_name, column_name) DO UPDATE
        SET data_type = EXCLUDED.data_type,
            description = EXCLUDED.description,
            pii_level = EXCLUDED.pii_level,
            source = EXCLUDED.source,
            example_value = EXCLUDED.example_value,
            updated_at = NOW()
    """
    execute_query(query, (
        schema_name, table_name, column_name, data_type, description,
        pii_level, source, example_value,
    ))


def register_lineage(
    source_table: str,
    target_table: str,
    transformation: str,
    dag_id: Optional[str] = None,
) -> None:
    """Enregistre une relation de lignée entre 2 tables."""
    query = """
        INSERT INTO governance.lineage
            (source_table, target_table, transformation, dag_id, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
    """
    execute_query(query, (source_table, target_table, transformation, dag_id))


def get_lineage_for_table(table_name: str) -> list[dict]:
    """Récupère toutes les relations de lignée impliquant une table."""
    query = """
        SELECT source_table, target_table, transformation, dag_id
        FROM governance.lineage
        WHERE source_table = %s OR target_table = %s
        ORDER BY updated_at DESC
    """
    return execute_query(query, (table_name, table_name))


def get_pii_columns() -> list[dict]:
    """Liste toutes les colonnes PII (pour audit RGPD)."""
    query = """
        SELECT schema_name, table_name, column_name, pii_level, description
        FROM governance.data_dictionary
        WHERE pii_level IN ('low', 'medium', 'high')
        ORDER BY pii_level DESC, schema_name, table_name
    """
    return execute_query(query, ())


def export_table_schema_documentation() -> str:
    """Exporte la doc schéma au format Markdown (pour docs/SCHEMA.md)."""
    query = """
        SELECT schema_name, table_name, column_name, data_type,
               description, pii_level, source
        FROM governance.data_dictionary
        ORDER BY schema_name, table_name, column_name
    """
    rows = execute_query(query, ())

    lines = ["# LyonFlowFull — Data Dictionary\n"]
    current_table = None
    for r in rows:
        full_table = f"{r['schema_name']}.{r['table_name']}"
        if full_table != current_table:
            current_table = full_table
            lines.append(f"\n## `{full_table}`\n")
            lines.append("| Column | Type | PII | Source | Description |")
            lines.append("|--------|------|-----|--------|-------------|")
        pii = r["pii_level"] or "none"
        pii_emoji = {"high": "🔴", "medium": "🟠", "low": "🟡", "none": "🟢"}.get(pii, "—")
        lines.append(
            f"| `{r['column_name']}` | {r['data_type']} | {pii_emoji} {pii} | "
            f"{r['source'] or '—'} | {r['description'] or '—'} |"
        )
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Auto-registration au boot (idempotent)
# -----------------------------------------------------------------------------
def auto_register_schema() -> None:
    """Enregistre les principales tables/colonnes du schéma LyonFlowFull.

    À appeler au démarrage de l'app ou via un DAG d'initialisation.
    Idempotent (UPSERT).
    """
    entries = [
        # Bronze
        ("bronze", "trafic_boucles", "fetched_at", "TIMESTAMPTZ",
         "Date/heure d'ingestion depuis l'API", "none", "Grand Lyon WFS"),
        ("bronze", "trafic_boucles", "raw_data", "JSONB",
         "Réponse API brute (FeatureCollection GeoJSON)", "none", "Grand Lyon WFS"),
        ("bronze", "trafic_boucles", "channel_id", "TEXT",
         "ID du capteur (extrait depuis raw_data)", "low", "extracted"),
        # Silver
        ("silver", "trafic_boucles_clean", "vitesse_kmh", "NUMERIC",
         "Vitesse moyenne mesurée (km/h)", "none", "extracted"),
        ("silver", "trafic_boucles_clean", "geom_wgs84", "GEOMETRY",
         "Géométrie LineString EPSG:4326", "none", "PostGIS"),
        ("silver", "velov_clean", "bikes_available", "INTEGER",
         "Nombre de vélos disponibles", "none", "GBFS"),
        ("silver", "tcl_vehicles_clean", "delay_seconds", "INTEGER",
         "Retard du véhicule en secondes", "none", "SIRI Lite"),
        # Gold
        ("gold", "traffic_features_live", "speed_kmh", "NUMERIC",
         "Vitesse instantanée (feature ML)", "none", "computed"),
        ("gold", "traffic_features_live", "speed_lag_1", "NUMERIC",
         "Vitesse au timestep précédent (lag)", "none", "computed"),
        ("gold", "infrastructure_bottlenecks", "diagnosis", "TEXT",
         "Classification: ok/infra/operations/bus_lane_ok", "none", "computed"),
        # RGPD
        ("rgpd", "user_consents", "user_identifier", "TEXT",
         "Hash anonyme de l'utilisateur (SHA256)", "medium", "computed"),
        ("rgpd", "audit_log", "actor", "TEXT",
         "Acteur ayant effectué l'action (anonymisé)", "low", "computed"),
        ("rgpd", "audit_log", "ip_address", "TEXT",
         "Adresse IP hashée (SHA256)", "medium", "computed"),
        # Governance
        ("governance", "data_dictionary", "pii_level", "TEXT",
         "Niveau PII (none/low/medium/high) RGPD", "none", "manual"),
    ]
    for entry in entries:
        try:
            register_data_dictionary_entry(
                schema_name=entry[0],
                table_name=entry[1],
                column_name=entry[2],
                data_type=entry[3],
                description=entry[4],
                pii_level=entry[5],
                source=entry[6],
            )
        except Exception as e:
            logger.warning(f"Failed to register {entry[0]}.{entry[1]}.{entry[2]}: {e}")

    # Lignée
    register_lineage("bronze.trafic_boucles", "silver.trafic_boucles_clean",
                     "Parse JSON + dédup + géométrie", "transform_bronze_to_silver")
    register_lineage("silver.trafic_boucles_clean", "gold.traffic_features_live",
                     "lags + deltas + temporel + météo", "transform_silver_to_gold")
    register_lineage("bronze.velov", "silver.velov_clean",
                     "Parse GBFS", "transform_bronze_to_silver")
    register_lineage("silver.velov_clean", "gold.velov_features",
                     "Label encoding + lags", "transform_silver_to_gold")
    register_lineage("bronze.tcl_vehicles", "silver.tcl_vehicles_clean",
                     "Parse SIRI Lite", "transform_bronze_to_silver")
    register_lineage("silver.tcl_vehicles_clean", "gold.bus_delay_segments",
                     "Aggregation by hour/line", "transform_silver_to_gold")

    logger.info("Data governance auto-registration complete")
