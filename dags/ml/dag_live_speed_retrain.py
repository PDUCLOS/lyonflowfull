"""DAG — Retrain XGBoost Speed + persiste prédictions dans gold.trafic_predictions.

Sprint VPS-5 (2026-06-10) — Ce DAG comble le trou laissé par le refactor v0.3.1 :
le nouveau schéma `gold.trafic_predictions` (colonnes axis_key, horizon_h,
calculated_at, speed_pred, etat_pred, ...) n'était alimenté par aucun DAG
depuis le déploiement, alors que `db_query.get_traffic_predictions()`
ainsi que les widgets dashboard l'attendent.

Plan (cf analyse_trafficlyon.md ligne 106) :
  1. Train 4 modèles XGBoost speed (H+5min, H+1h, H+3h, H+6h)
  2. Pour chaque axe de `gold.dim_spatial_grid_mapping` (~1518),
     prédire la vitesse via `XGBoostSpeedModel.predict(node_idx, horizon_minutes)`
  3. INSERT en batch dans `gold.trafic_predictions` (psycopg2 executemany)
  4. Cleanup : DELETE les prédictions > 7 jours (RGPD rétention)

Note d'horizon : le modèle prend `horizon_minutes` (5/60/180/360) mais
le schéma gold stocke `horizon_h` (0/1/3/6). On mappe à l'INSERT.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from airflow import DAG
from airflow.operators.python import PythonOperator

from src.db.connection import raw_connection

logger = logging.getLogger(__name__)

# Mapping horizon_minutes (modèle) -> horizon_h (schéma gold)
HORIZON_MAP = {  # 2026-06-11: focus H+1h stable
    60: 1,   # H+1h
}

# Vitesse limite par défaut (Lyon intra-muros : 50 km/h)
DEFAULT_SPEED_LIMIT = 50.0


def _color_for_speed(speed_kmh: float, limit_kmh: float) -> str:
    """Retourne la couleur de l'axe selon vitesse_pred / vitesse_limite."""
    if limit_kmh <= 0:
        return "gray"
    ratio = speed_kmh / limit_kmh
    if ratio >= 0.8:
        return "green"
    if ratio >= 0.5:
        return "orange"
    return "red"


def _etat_for_speed(speed_kmh: float, limit_kmh: float) -> str:
    """Code état court (1 char) : F=fluide, M=modéré, D=dense, B=bloqué."""
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


def _train_all_xgboost_speed() -> dict:
    """Task 1 — Entraîne les 4 modèles XGBoost speed (best-effort).

    Sprint VPS-5 — Le code XGBoost (src/models/xgboost_speed.py) référence des colonnes
    obsolètes (speed_lag_1, node_idx, hour_sin, temperature_c, rain_mm, measurement_time)
    qui n'existent plus dans gold.traffic_features_live (v0.3.1 a renommé en
    lag_1/delta_1/rolling_mean_3/sin_hour/temperature_2m/precipitation/computed_at).

    Refactor modèle = Sprint 9+. En attendant, on logge l'échec mais on ne bloque
    pas le DAG : la task ``predict_and_persist_gold`` utilise un baseline
    (vitesse courante propagée) pour que le dashboard ait des données.

    Returns:
        Dict {"h{min}min": {"error": str} | {"mae": float, "r2": float}}
    """
    from src.models.xgboost_speed import XGBoostSpeedModel

    results = {}
    for horizon_minutes in HORIZON_MAP:
        try:
            model = XGBoostSpeedModel()
            metrics = model.train_one(horizon_minutes=horizon_minutes)
            results[f"h{horizon_minutes}min"] = metrics
            logger.info("Train H+%dmin OK: %s", horizon_minutes, metrics)
        except Exception as e:
            logger.warning(
                "Train H+%dmin FAILED (schema drift probable) — fallback baseline activé: %s",
                horizon_minutes,
                e,
            )
            results[f"h{horizon_minutes}min"] = {"error": str(e), "fallback": "baseline"}
    return results


def _predict_and_persist() -> dict:
    """Task 2 — Pour chaque channel_id avec données, persiste une prédiction par horizon.

    Stratégie (Sprint VPS-5) : **baseline = dernière vitesse observée**, propagée
    sur les 4 horizons. C'est volontairement naïf pour débloquer le dashboard.
    Sera remplacé par les vraies prédictions XGBoost dès que ``src/models/xgboost_speed.py``
    sera migré vers le schéma v0.3.1 (Sprint 9+).

    Note technique (Sprint VPS-5) :
    * ``dim_spatial_grid_mapping.properties_twgid`` contient des entiers (537, 1593...)
      qui ne correspondent PAS au format ``LYO00xxx`` de ``traffic_features_live.channel_id``.
    * On ne fait donc PAS de JOIN entre les deux. On itère sur les channel_ids distincts
      de traffic_features_live (~1100) directement, en gardant lat/lon NULL.
    * Quand le mapping axis_key ↔ node_idx sera réconcilié (Sprint 9+), on pourra
      géocoder les prédictions sur la carte.

    Returns:
        Dict {"rows_inserted": int, "horizons": {h: count}, "duration_s": float}
    """
    started = datetime.now()

    with raw_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # DISTINCT ON : 1 ligne par channel_id avec le dernier computed_at
        # (un INNER JOIN sur MAX(computed_at) matche 1.9M rows car tous les batch
        # ont le même timestamp ; DISTINCT ON est l'idiome Postgres correct ici)
        cur.execute(
            """
            SELECT DISTINCT ON (channel_id)
                channel_id, speed_kmh, vitesse_limite_kmh
            FROM gold.traffic_features_live
            WHERE speed_kmh IS NOT NULL
            ORDER BY channel_id, computed_at DESC
            """
        )
        axes = cur.fetchall()

    logger.info("Predicting baseline for %d axes x %d horizons", len(axes), len(HORIZON_MAP))

    rows_to_insert: list[tuple] = []
    per_horizon_count: dict[int, int] = {}

    for horizon_minutes, horizon_h in HORIZON_MAP.items():
        per_horizon_count[horizon_minutes] = 0
        for axis in axes:
            speed = float(axis.get("speed_kmh") or 30.0)
            limit = float(axis.get("vitesse_limite_kmh") or DEFAULT_SPEED_LIMIT)
            color = _color_for_speed(speed, limit)
            etat = _etat_for_speed(speed, limit)
            rows_to_insert.append(
                (
                    str(axis["channel_id"]),  # axis_key = channel_id (format LYO00xxx)
                    horizon_h,
                    datetime.now(),  # calculated_at — colonne NOT NULL sans default
                    speed,
                    etat,
                    color,
                    limit,
                    f"H+{horizon_minutes}min",
                    "baseline_v0.3.1",
                    None,  # lat — pas de JOIN avec dim_spatial_grid_mapping (Sprint 9+)
                    None,  # lon
                )
            )
            per_horizon_count[horizon_minutes] += 1

    if not rows_to_insert:
        return {"rows_inserted": 0, "horizons": per_horizon_count, "duration_s": 0.0}

    insert_sql = """
        INSERT INTO gold.trafic_predictions (
            axis_key, horizon_h, calculated_at, speed_pred, etat_pred, color,
            vitesse_limite_kmh, label, model_version, lat, lon
        )
        VALUES %s
    """

    with raw_connection() as conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            insert_sql,
            rows_to_insert,
            template=None,
            page_size=200,
        )

    duration = (datetime.now() - started).total_seconds()
    logger.info(
        "Inserted %d baseline predictions in %.1fs (per horizon: %s)",
        len(rows_to_insert),
        duration,
        per_horizon_count,
    )
    return {
        "rows_inserted": len(rows_to_insert),
        "horizons": per_horizon_count,
        "duration_s": duration,
    }


def _cleanup_old_predictions(retention_days: int = 7) -> int:
    """Task 3 — Purge les prédictions > retention_days (RGPD)."""
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


default_args = {
    "owner": "lyonflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="dag_live_speed_retrain",
    description=(
        "Retrain 4 XGBoost speed (5min/1h/3h/6h) + persiste prédictions "
        "dans gold.trafic_predictions (nouveau schéma v0.3.1 axis_key/horizon_h/calculated_at). "
        "Alimente les widgets dashboard et la couche routing."
    ),
    default_args=default_args,
    schedule="*/30 * * * *",  # 2026-06-11: 30min, focus H+1h (cf analyse_trafficlyon.md)
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "xgboost", "traffic", "predictions", "gold"],
) as dag:
    train = PythonOperator(
        task_id="train_xgboost_speed_all_horizons",
        python_callable=_train_all_xgboost_speed,
        execution_timeout=timedelta(minutes=20),
    )

    predict = PythonOperator(
        task_id="predict_and_persist_gold",
        python_callable=_predict_and_persist,
        execution_timeout=timedelta(minutes=15),
    )

    cleanup = PythonOperator(
        task_id="cleanup_old_predictions",
        python_callable=_cleanup_old_predictions,
        op_kwargs={"retention_days": 7},
        execution_timeout=timedelta(minutes=2),
    )

    train >> predict >> cleanup
