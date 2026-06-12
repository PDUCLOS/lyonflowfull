"""Mocks pipeline Pro TCL (DAGs Airflow + freshness sources).

Utilises uniquement comme fallback quand Airflow REST API ou la DB ne
sont pas joignables (mode demo, tests). Le widget pipeline_management
affiche un banner d'avertissement dans ce cas.
"""

from __future__ import annotations

MOCK_DAGS: list[dict] = [
    {
        "dag_id": "collect_bronze",
        "schedule": "*/5 * * * *",
        "last_run": "2026-06-06 14:55:00",
        "last_status": "success",
        "last_duration_s": 12,
        "next_run": "2026-06-06 15:00:00",
        "description": "Collecte 8 sources temps réel",
        "paused": False,
    },
    {
        "dag_id": "collect_calendriers_monthly",
        "schedule": "@monthly",
        "last_run": "2026-06-01 03:00:00",
        "last_status": "success",
        "last_duration_s": 5,
        "next_run": "2026-07-01 03:00:00",
        "description": "Collecte calendriers (vacances, fériés)",
        "paused": False,
    },
    {
        "dag_id": "transform_bronze_to_silver",
        "schedule": "*/5 * * * *",
        "last_run": "2026-06-06 14:55:00",
        "last_status": "success",
        "last_duration_s": 8,
        "next_run": "2026-06-06 15:00:00",
        "description": "Bronze → Silver (5 sources)",
        "paused": False,
    },
    {
        "dag_id": "transform_silver_to_gold",
        "schedule": "*/10 * * * *",
        "last_run": "2026-06-06 14:50:00",
        "last_status": "success",
        "last_duration_s": 14,
        "next_run": "2026-06-06 15:00:00",
        "description": "Silver → Gold (3 builders)",
        "paused": False,
    },
    {
        "dag_id": "build_spatial_mapping",
        "schedule": "30 2 * * *",
        "last_run": "2026-06-06 02:30:00",
        "last_status": "success",
        "last_duration_s": 22,
        "next_run": "2026-06-07 02:30:00",
        "description": "Construit dim_spatial_grid_mapping + adjacency",
        "paused": False,
    },
    {
        "dag_id": "retrain_xgboost_speed",
        "schedule": "25 * * * *",
        "last_run": "2026-06-06 14:25:00",
        "last_status": "success",
        "last_duration_s": 184,
        "next_run": "2026-06-06 15:25:00",
        "description": "Retrain XGBoost Speed (4 horizons)",
        "paused": False,
    },
    {
        "dag_id": "retrain_xgboost_velov",
        "schedule": "50 * * * *",
        "last_run": "2026-06-06 14:50:00",
        "last_status": "success",
        "last_duration_s": 142,
        "next_run": "2026-06-06 15:50:00",
        "description": "Retrain XGBoost Velov (2 horizons)",
        "paused": False,
    },
    {
        "dag_id": "data_quality_daily",
        "schedule": "15 4 * * *",
        "last_run": "2026-06-06 04:15:00",
        "last_status": "success",
        "last_duration_s": 28,
        "next_run": "2026-06-07 04:15:00",
        "description": "6 checks qualité quotidien",
        "paused": False,
    },
    {
        "dag_id": "purge_bronze",
        "schedule": "0 3 * * *",
        "last_run": "2026-06-06 03:00:00",
        "last_status": "success",
        "last_duration_s": 8,
        "next_run": "2026-06-07 03:00:00",
        "description": "Purge Bronze rétention",
        "paused": False,
    },
]


MOCK_FRESHNESS: list[dict] = [
    {"source": "trafic_boucles", "last_ingestion": "2026-06-06 14:55:00", "n_records_24h": 316800, "status": "ok"},
    {"source": "velov", "last_ingestion": "2026-06-06 14:55:00", "n_records_24h": 132192, "status": "ok"},
    {"source": "tcl_vehicles", "last_ingestion": "2026-06-06 14:55:00", "n_records_24h": 69120, "status": "ok"},
    {"source": "meteo", "last_ingestion": "2026-06-06 13:00:00", "n_records_24h": 24, "status": "ok"},
    {"source": "air_quality", "last_ingestion": "2026-06-06 13:00:00", "n_records_24h": 24, "status": "ok"},
    {"source": "chantiers", "last_ingestion": "2026-06-06 03:00:00", "n_records_24h": 1, "status": "ok"},
    {"source": "calendrier_scolaire", "last_ingestion": "2026-06-01 03:00:00", "n_records_24h": 0, "status": "stale"},
    {"source": "jours_feries", "last_ingestion": "2026-06-01 03:00:00", "n_records_24h": 0, "status": "stale"},
]
