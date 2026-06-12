"""DAG — Prédiction XGBoost Speed + persiste dans gold.trafic_predictions.

Sprint 9+ (Optimisation) — L'entraînement a été déplacé dans un DAG quotidien 
(`dag_daily_speed_train.py`). Ce DAG-ci ne gère plus que l'inférence temps réel.
Il utilise le vrai modèle XGBoost au lieu de la baseline naïve.

Plan :
  1. Pour chaque axe, on prédit la vitesse via `XGBoostSpeedModel.predict()`
  2. INSERT en batch dans `gold.trafic_predictions` (psycopg2 executemany)
  3. Cleanup : DELETE les prédictions > 7 jours (RGPD rétention)

Note d'horizon : le modèle prend `horizon_minutes` (60) mais
le schéma gold stocke `horizon_h` (1). On mappe à l'INSERT.
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



def _predict_and_persist() -> dict:
    """Task 1 — Pour chaque channel_id avec données, persiste une vraie prédiction XGBoost.

    Stratégie (Sprint 9+ Optimisation) : Le modèle XGBoost entraîné la nuit dernière
    est utilisé. La baseline naïve a été retirée.

    Returns:
        Dict {"rows_inserted": int, "horizons": {h: count}, "duration_s": float}
    """
    from src.models.xgboost_speed import XGBoostSpeedModel

    started = datetime.now()
    
    # Load model once for all predictions
    model = XGBoostSpeedModel()
    model.load(horizons=list(HORIZON_MAP.keys()))

    with raw_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # On récupère toutes les features nécessaires pour le predict
        cur.execute(
            """
            SELECT DISTINCT ON (channel_id)
                channel_id, speed_kmh, lag_1, lag_2, lag_3, rolling_mean_3,
                sin_hour, cos_hour, temperature_2m, precipitation,
                is_vacances, is_ferie, vitesse_limite_kmh
            FROM gold.traffic_features_live
            WHERE speed_kmh IS NOT NULL
            ORDER BY channel_id, computed_at DESC
            """
        )
        axes = cur.fetchall()

    logger.info("Predicting XGBoost for %d axes x %d horizons", len(axes), len(HORIZON_MAP))

    rows_to_insert: list[tuple] = []
    per_horizon_count: dict[int, int] = {}

    for horizon_minutes, horizon_h in HORIZON_MAP.items():
        per_horizon_count[horizon_minutes] = 0
        for axis in axes:
            limit = float(axis.get("vitesse_limite_kmh") or DEFAULT_SPEED_LIMIT)
            
            # Predict
            pred_result = model.predict(str(axis["channel_id"]), horizon_minutes=horizon_minutes, features=axis)
            speed = pred_result["predicted_speed_kmh"]
            model_version = pred_result["model_version"]
            
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
                    f"xgboost_speed_{model_version}",
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
    # Sprint 8+3 (2026-06-12) — Fiabilité VPS : retries=0 pour ne pas
    # empiler des runs en cas d'échec (le DAG tourne déjà toutes les
    # 30min, on attendra le prochain cycle).
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="dag_live_speed_retrain",
    description="Prédictions XGBoost speed et persistance dans gold.trafic_predictions (inférence uniquement).",
    default_args=default_args,
    schedule="*/30 * * * *",  # 2026-06-11: 30min, focus H+1h (cf analyse_trafficlyon.md)
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ml", "xgboost", "traffic", "predictions", "gold"],
) as dag:
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

    predict >> cleanup

