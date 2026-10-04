"""gold: versionnage tables velov_features et velov_predictions

Revision ID: 0003_velov_features_predictions
Revises: 0002_perf_optimizations
Create Date: 2026-06-30

Sprint P3.4 (2026-06-30) — Align alembic avec migration SQL 039.

Ces deux tables existaient dans scripts/migrate_realign_v0.3.1.sql
mais n'avaient pas de migration Alembic dédiée. En cas de recréation DB
depuis zéro via alembic upgrade head, elles auraient été absentes.

Cette migration est idempotente (IF NOT EXISTS) et mirror exactement
scripts/sql/migration_039_velov_features_predictions.sql.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_velov_features_predictions"
down_revision: str | None = "0002_perf_optimizations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS gold.velov_features (
            id                  BIGSERIAL PRIMARY KEY,
            measurement_time    TIMESTAMPTZ NOT NULL,
            station_id          TEXT NOT NULL,
            station_id_encoded  INTEGER NOT NULL,
            num_bikes_available INTEGER,
            capacity            INTEGER,
            fill_ratio          REAL,
            hour_sin            REAL,
            hour_cos            REAL,
            day_sin             REAL,
            day_cos             REAL,
            is_vacances         BOOLEAN,
            is_ferie            BOOLEAN,
            rain_mm             REAL,
            temperature_c       REAL,
            lag_30min           REAL,
            lag_60min           REAL,
            rolling_mean_1h     REAL,
            CONSTRAINT gold_velov_feat_uniq UNIQUE (station_id, measurement_time)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_gold_velov_feat_time
            ON gold.velov_features (measurement_time DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS gold.velov_predictions (
            id                   BIGSERIAL PRIMARY KEY,
            prediction_timestamp TIMESTAMPTZ NOT NULL,
            target_timestamp     TIMESTAMPTZ NOT NULL,
            horizon_minutes      SMALLINT NOT NULL,
            station_id           TEXT NOT NULL,
            predicted_bikes      REAL,
            actual_bikes         REAL,
            model_name           TEXT,
            model_version        TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_gold_velov_pred_time
            ON gold.velov_predictions (prediction_timestamp DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_gold_velov_pred_station
            ON gold.velov_predictions (station_id, horizon_minutes)
    """)

    op.execute("""
        INSERT INTO public.schema_migrations (version) VALUES (39)
        ON CONFLICT (version) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gold.velov_predictions")
    op.execute("DROP TABLE IF EXISTS gold.velov_features")
    op.execute("DELETE FROM public.schema_migrations WHERE version = 39")
