"""DAG — Inférence XGBoost Speed temps réel (1x/15min).

 Optimisation (2026-06-12) — Remplace
``dag_live_speed_retrain`` qui entraînait toutes les 30 min (gaspillage
CPU/RAM). Maintenant :

- **dag_daily_speed_train (03h00)** : entraîne le modèle (lourd)
- **dag_inference_xgboost (CE DAG, */15min)** : ne fait que prédire
  - charge le modèle 1 fois (mis en cache en mémoire par Airflow worker)
  - lit les derniers features depuis gold.traffic_features_live
  - INSERT batch dans gold.trafic_predictions
  - cleanup RGPD > 7 jours

**Pas de fit() dans ce DAG** : inférence pure, ~10-30s par exécution.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from airflow import DAG
from airflow.operators.python import PythonOperator

from src.db.connection import execute_query, raw_connection

logger = logging.getLogger(__name__)

DAG_ID = "dag_inference_xgboost"
DEFAULT_ARGS = {
    "owner": "lyonflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 0,  # le cycle suivant rattrape , pas de cascade)
    "execution_timeout": timedelta(minutes=10),
}

# Mapping horizon_minutes (modèle) -> horizon_h (schéma gold)
HORIZON_MAP = {60: 1}
DEFAULT_SPEED_LIMIT = 50.0


def _get_model():
    """Charge le modèle XGBoost H+1h depuis le disque ou MLflow Registry.

    fix : le cache process-local ``_model_cache`` a été
      supprimé — avec CeleryExecutor (worker_concurrency=2), chaque DAG run
      tourne dans un process Python distinct, donc le cache n'est jamais
      réutilisé (le coût du ``model.load()`` est marginal : ~50ms, < 1 % du
      temps total de la task). Pas de fallback baseline (zéro mock) : si
      le modèle n'est pas chargé, RuntimeError explicite.
    """
    from src.models.xgboost_speed import XGBoostSpeedModel

    model = XGBoostSpeedModel()
    model.load()  # charge depuis disque ou MLflow Registry
    if 60 not in model.models:
        raise RuntimeError(
            "Modèle XGBoost H+1h non disponible. Le DAG 'dag_daily_speed_train' doit tourner pour entraîner le modèle."
        )
    return model


def _color_for_speed(speed_kmh: float, limit_kmh: float) -> str:
    if limit_kmh <= 0:
        return "gray"
    ratio = speed_kmh / limit_kmh
    if ratio >= 0.8:
        return "green"
    if ratio >= 0.5:
        return "orange"
    return "red"


def _etat_for_speed(speed_kmh: float, limit_kmh: float) -> str:
    if limit_kmh <= 0:
        return "?"
    ratio = speed_kmh / limit_kmh
    if ratio >= 0.8:
        return "F"
    if ratio >= 0.5:
        return "M"
    if ratio >= 0.25:
        return "D"
    return "B"


def _load_axes() -> list[dict]:
    """Charge les axes (= channels avec données Gold récentes).

      On itère sur les channel_id distincts de traffic_features_live
    (cf. note dans le code legacy — le mapping axis_key ↔
      node_idx reste à réconcilier côté gold.dim_spatial_grid_mapping).
    """
    rows = execute_query("""
        SELECT DISTINCT ON (channel_id)
            channel_id,
            vitesse_limite_kmh,
            lat,
            lon
        FROM gold.traffic_features_live
        WHERE computed_at > NOW() - INTERVAL '2 hours'
          AND speed_kmh IS NOT NULL
        ORDER BY channel_id, computed_at DESC
    """)
    return rows


def _predict_and_persist() -> dict:
    """Vraie inférence XGBoost : pour chaque channel, INSERT gold.trafic_predictions."""
    started = datetime.now()
    model = _get_model()
    axes = _load_axes()
    if not axes:
        logger.warning("Aucun axe avec données Gold récentes (2h) — skip")
        return {"rows_inserted": 0, "n_axes": 0, "duration_s": 0.0}

    rows_to_insert: list[tuple] = []
    per_horizon_count: dict[int, int] = {}

    for horizon_minutes, horizon_h in HORIZON_MAP.items():
        per_horizon_count[horizon_minutes] = 0
        for axis in axes:
            limit = float(axis.get("vitesse_limite_kmh") or DEFAULT_SPEED_LIMIT)
            try:
                pred_result = model.predict(
                    str(axis["channel_id"]),
                    horizon_minutes=horizon_minutes,
                )
            except Exception as e:
                logger.warning("Predict failed for %s: %s — skip", axis["channel_id"], e)
                continue

            speed = pred_result["predicted_speed_kmh"]
            model_version = pred_result["model_version"]
            color = _color_for_speed(speed, limit)
            etat = _etat_for_speed(speed, limit)
            rows_to_insert.append(
                (
                    str(axis["channel_id"]),
                    horizon_h,
                    datetime.now(),
                    speed,
                    etat,
                    color,
                    limit,
                    f"H+{horizon_minutes}min",
                    f"xgboost_speed_{model_version}",
                    axis.get("lat"),
                    axis.get("lon"),
                )
            )
            per_horizon_count[horizon_minutes] += 1

    if not rows_to_insert:
        return {"rows_inserted": 0, "n_axes": len(axes), "duration_s": 0.0}

    insert_sql = """
        INSERT INTO gold.trafic_predictions (
            axis_key, horizon_h, calculated_at, speed_pred, etat_pred, color,
            vitesse_limite_kmh, label, model_version, lat, lon
        )
        VALUES %s
    """
    with raw_connection() as conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, insert_sql, rows_to_insert, template=None, page_size=200)

    duration = (datetime.now() - started).total_seconds()
    logger.info(
        "Inserted %d XGBoost predictions in %.2fs (axes=%d, horizons=%s)",
        len(rows_to_insert),
        duration,
        len(axes),
        per_horizon_count,
    )
    return {
        "rows_inserted": len(rows_to_insert),
        "n_axes": len(axes),
        "horizons": per_horizon_count,
        "duration_s": duration,
    }


def _cleanup_old_predictions(retention_days: int = 7) -> int:
    """Purge gold.trafic_predictions > retention_days (RGPD)."""
    with raw_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM gold.trafic_predictions
            WHERE calculated_at < NOW() - make_interval(days => %s)
            """,
            (retention_days,),
        )
        deleted = cur.rowcount
    logger.info("Purged %d old predictions (>%d days)", deleted, retention_days)
    return deleted


with DAG(
    dag_id=DAG_ID,
    default_args=DEFAULT_ARGS,
    description="Inférence XGBoost H+1h toutes les 15 min (léger, pas de fit)",
    schedule_interval="*/15 * * * *",  # toutes les 15 min
    start_date=datetime(2026, 6, 12),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "inference", "xgboost", "sprint9"],
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
