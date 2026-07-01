"""DAG — Inférence XGBoost Vélov temps réel (1x/15min).

Miroir de ``dag_inference_xgboost.py`` (trafic), même découplage train/inf :

- **retrain_xgboost_velov (hourly :50)** : entraîne le modèle (lourd)
- **dag_inference_velov (CE DAG, */15min)** : ne fait que prédire
  - charge le modèle 1 fois par run (depuis disque ou MLflow Registry)
  - lit les stations actives depuis silver.velov_clean
  - INSERT batch dans gold.velov_predictions
  - cleanup RGPD > 7 jours

Manque avant ce DAG (trouvé 2026-07-01, audit MLOps) : le modèle
``xgboost_velov`` s'entraînait bien (fichier .pkl frais, run MLflow tracké)
mais aucune prédiction n'était jamais persistée — ``gold.velov_predictions``
restait vide en permanence. Le widget ``velov_map.py`` (page
``Usager_1_Mon_Trajet.py``) affichait donc la carte sans jamais montrer la
prédiction H+1h (dégradation silencieuse, pas de crash).

**Pas de fit() dans ce DAG** : inférence pure.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import psycopg2
import psycopg2.extras
from airflow import DAG
from airflow.operators.python import PythonOperator

from src.db.connection import execute_query, raw_connection

logger = logging.getLogger(__name__)

DAG_ID = "dag_inference_velov"
DEFAULT_ARGS = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 0,  # le cycle suivant rattrape, pas de cascade
    "execution_timeout": timedelta(minutes=10),
}

HORIZON_MINUTES = 60


def _get_model():
    """Charge le modèle XGBoost Vélov H+1h depuis le disque ou MLflow Registry."""
    from src.models.xgboost_velov import XGBoostVelovModel

    model = XGBoostVelovModel()
    model.load()
    if HORIZON_MINUTES not in model.models:
        raise RuntimeError(
            "Modèle XGBoost Vélov H+1h non disponible. Le DAG 'retrain_xgboost_velov' doit tourner pour entraîner le modèle."
        )
    return model


def _load_active_stations() -> list[dict]:
    """Charge les stations Vélov actives (données fraîches < 30 min)."""
    rows = execute_query("""
        SELECT DISTINCT ON (station_id) station_id
        FROM silver.velov_clean
        WHERE measurement_time > NOW() - INTERVAL '30 minutes'
          AND is_active = TRUE
        ORDER BY station_id, measurement_time DESC
    """)
    return rows


def _predict_and_persist() -> dict:
    """Vraie inférence XGBoost Vélov : pour chaque station, INSERT gold.velov_predictions."""
    started = datetime.now(UTC)
    model = _get_model()
    stations = _load_active_stations()
    if not stations:
        logger.warning("Aucune station Vélov active (30 min) — skip")
        return {"rows_inserted": 0, "n_stations": 0, "duration_s": 0.0}

    now = datetime.now(UTC)
    target_ts = now + timedelta(minutes=HORIZON_MINUTES)
    rows_to_insert: list[tuple] = []

    for station in stations:
        station_id = str(station["station_id"])
        try:
            pred_result = model.predict(station_id, horizon_minutes=HORIZON_MINUTES)
        except Exception as e:
            logger.warning("Predict failed for station %s: %s — skip", station_id, e)
            continue

        if pred_result.get("model_name") == "fallback":
            continue  # pas de features / modèle non chargé pour cette station

        rows_to_insert.append(
            (
                now,
                target_ts,
                HORIZON_MINUTES,
                station_id,
                pred_result["predicted_bikes"],
                pred_result["model_name"],
                pred_result["model_version"],
            )
        )

    if not rows_to_insert:
        return {"rows_inserted": 0, "n_stations": len(stations), "duration_s": 0.0}

    insert_sql = """
        INSERT INTO gold.velov_predictions (
            prediction_timestamp, target_timestamp, horizon_minutes,
            station_id, predicted_bikes, model_name, model_version
        )
        VALUES %s
    """
    with raw_connection() as conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, insert_sql, rows_to_insert, template=None, page_size=200)

    duration = (datetime.now(UTC) - started).total_seconds()
    logger.info(
        "Inserted %d Velov predictions in %.2fs (stations=%d)",
        len(rows_to_insert),
        duration,
        len(stations),
    )
    return {
        "rows_inserted": len(rows_to_insert),
        "n_stations": len(stations),
        "duration_s": duration,
    }


def _cleanup_old_predictions(retention_days: int = 7) -> int:
    """Purge gold.velov_predictions > retention_days (RGPD)."""
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM gold.velov_predictions
            WHERE prediction_timestamp < NOW() - make_interval(days => %s)
            """,
            (retention_days,),
        )
        deleted = cur.rowcount
    logger.info("Purged %d old Velov predictions (>%d days)", deleted, retention_days)
    return deleted


with DAG(
    dag_id=DAG_ID,
    default_args=DEFAULT_ARGS,
    description="Inférence XGBoost Vélov H+1h toutes les 15 min (léger, pas de fit)",
    # Décalé 4,19,34,49 (au lieu de */15 pile) — évite le thundering herd
    # :00/:15/:30/:45 (cf. docs/AUDIT_AIRFLOW_POSTGRES_SPRINT24.md item C1).
    schedule_interval="4,19,34,49 * * * *",
    start_date=datetime(2026, 7, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "inference", "velov"],
) as dag:
    predict = PythonOperator(
        task_id="predict_and_persist_gold",
        python_callable=_predict_and_persist,
        execution_timeout=timedelta(minutes=8),
    )
    cleanup = PythonOperator(
        task_id="cleanup_old_predictions",
        python_callable=_cleanup_old_predictions,
        op_kwargs={"retention_days": 7},
        execution_timeout=timedelta(minutes=2),
    )
    predict >> cleanup
