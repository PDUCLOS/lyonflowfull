"""create referentiel.* + gold.mv_line_kpis_live + gold.xgb_training_set — LyonFlowFull

Revision ID: 0006_referentiel_and_mvs
Revises: 0005_gold_bottleneck_tables
Create Date: 2026-06-14

Sprint P2.6 (2026-06-14) — Fix AUDIT_INTEGRATION_LIVE.md § dette schéma § P2.6.

Cette migration crée :

* ``referentiel.lieux_lyon`` : référentiel lieux Lyon (autocomplete, markers,
  routing). Alimenté par ``scripts/seed_lieux_lyon.py`` (Sprint 9+).
  Cf. ``dashboard/components/widgets/usager/velov_trip.py:439`` et
  ``src/routing/recommendation.py:117`` qui lisent cette table.

* ``referentiel.lieux_transports`` : dessertes TCL par lieu. Alimenté par
  ``scripts/seed_lieux_transports.py``. Cf. ``db_query.get_lieux_transports``.

* ``referentiel.lieux_calendrier`` : cadence observée par ligne/jour/heure.
  Alimenté par ``scripts/seed_lieux_calendrier.py``. Cf.
  ``src/routing/recommendation.py:188``.

* ``gold.mv_line_kpis_live`` : vue matérialisée des KPIs TCL (OTP, retard,
  fréquence, charge). Source unique du widget Pro/Élu (cf.
  ``db_query.get_line_kpis``). Refresh par
  ``dags/maintenance/refresh_lieux_calendrier.py`` (DAG mensuel).

* ``gold.xgb_training_set`` : table matérialisée pour XGBoost H+1h.
  Alimentée par ``dags/ml/build_xgb_training_set.py`` (02h30 quotidien).
  Cf. ``src/models/xgboost_speed.py:335``.

Les vues ``gold.mv_kpis_12_months``, ``gold.mv_otp_heatmap``,
``gold.fact_correlation_matrix``, ``gold.amenagements_history`` ne sont
pas dans cette migration — nice-to-have, à traiter en P3 si besoin.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_referentiel_and_mvs"
down_revision: str | None = "0005_gold_bottleneck_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crée les schémas referentiel + tables/vues Gold manquantes."""
    # Schéma referentiel
    op.execute("CREATE SCHEMA IF NOT EXISTS referentiel")

    # -------------------------------------------------------------------------
    # referentiel.lieux_lyon
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS referentiel.lieux_lyon (
            lieu_id bigserial NOT NULL,
            nom character varying(255) NOT NULL,
            lon double precision NOT NULL,
            lat double precision NOT NULL,
            type_lieu character varying(64),
            commune character varying(64),
            geom public.geometry(Point, 4326),
            updated_at timestamp with time zone DEFAULT now(),
            CONSTRAINT lieux_lyon_pkey PRIMARY KEY (lieu_id)
        )
        """
    )
    # Sprint P2-bis (2026-06-15) — Le schéma prod préexistant utilise
    # ``name`` (et pas ``nom``) + n'a PAS de colonne ``geom``.
    # Les CREATE INDEX IF NOT EXISTS ne sont pas idempotents au niveau
    # colonne : on saute si la colonne manque. Utilise EXECUTE dans DO $$
    # (execute-as-string) pour éviter le parsing du statement-fencing
    # psycopg2 sur les blocs $$ multi-statements.
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM information_schema.columns "
        "           WHERE table_schema='referentiel' AND table_name='lieux_lyon' AND column_name='nom') "
        "THEN EXECUTE 'CREATE INDEX IF NOT EXISTS idx_lieux_lyon_nom ON referentiel.lieux_lyon (nom)'; "
        "END IF; "
        "END $$"
    )
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM information_schema.columns "
        "           WHERE table_schema='referentiel' AND table_name='lieux_lyon' AND column_name='geom') "
        "THEN EXECUTE 'CREATE INDEX IF NOT EXISTS idx_lieux_lyon_geom ON referentiel.lieux_lyon USING gist (geom)'; "
        "END IF; "
        "END $$"
    )

    # -------------------------------------------------------------------------
    # referentiel.lieux_transports
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS referentiel.lieux_transports (
            lieu_id bigint NOT NULL,
            line_ref character varying(32) NOT NULL,
            line_mode character varying(16),
            stop_name character varying(128),
            distance_m integer,
            rank smallint,
            CONSTRAINT lieux_transports_pkey PRIMARY KEY (lieu_id, line_ref)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_lieux_transports_lieu_id "
        "ON referentiel.lieux_transports (lieu_id)"
    )

    # -------------------------------------------------------------------------
    # referentiel.lieux_calendrier
    # PK = (line_ref, day_type, time_bucket) — matche le ON CONFLICT
    # de scripts/seed_lieux_calendrier.py
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS referentiel.lieux_calendrier (
            line_ref character varying(32) NOT NULL,
            day_type character varying(16) NOT NULL,
            time_bucket character varying(8) NOT NULL,
            cadence_min_per_vehicle numeric(6, 2),
            n_observations integer,
            confidence numeric(4, 3),
            computed_at timestamp with time zone DEFAULT now(),
            CONSTRAINT lieux_calendrier_pkey PRIMARY KEY (line_ref, day_type, time_bucket)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_lieux_calendrier_line_ref "
        "ON referentiel.lieux_calendrier (line_ref)"
    )

    # -------------------------------------------------------------------------
    # gold.mv_line_kpis_live (vue matérialisée)
    # Colonnes alignées sur db_query.get_line_kpis (cf. P0.4 fix).
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS gold.mv_line_kpis_live AS
        SELECT
            v.line_ref                                                    AS line_id,
            COALESCE(MAX(v.line_ref), v.line_ref)                         AS line_name,
            -- OTP : ratio véhicules is_delayed=false / total
            ROUND(
                (100.0 * SUM(CASE WHEN NOT v.is_delayed THEN 1 ELSE 0 END)
                 / NULLIF(COUNT(*), 0))::numeric, 1
            )                                                             AS otp_pct,
            -- Retard moyen
            ROUND(AVG(v.delay_seconds)::numeric / 60.0, 2)                 AS avg_delay_min,
            -- Fréquence (veh/h) — placeholder : nb véhicules uniques / 1h
            COUNT(DISTINCT v.vehicle_ref)                                 AS frequency_pph,
            -- Charge : proxy via max delay
            ROUND(
                LEAST(AVG(v.delay_seconds) / 60.0, 100.0)::numeric, 1
            )                                                             AS occupancy_pct,
            CURRENT_DATE                                                  AS date
        FROM gold.tcl_vehicle_realtime v
        WHERE v.recorded_at > NOW() - INTERVAL '1 hour'
        GROUP BY v.line_ref
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_line_kpis_live_line_id "
        "ON gold.mv_line_kpis_live (line_id)"
    )

    # -------------------------------------------------------------------------
    # gold.xgb_training_set
    # Aligné sur build_xgb_training_set.py (cf. docstring P1.1 — 11 features).
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gold.xgb_training_set (
            id bigserial NOT NULL,
            computed_at timestamp with time zone NOT NULL,
            target_computed_at timestamp with time zone NOT NULL,
            channel_id text NOT NULL,
            channel_hash double precision,
            target_speed double precision,
            speed_kmh double precision,
            lag_1 double precision,
            lag_2 double precision,
            lag_3 double precision,
            rolling_mean_3 double precision,
            sin_hour double precision,
            cos_hour double precision,
            temperature_2m double precision,
            precipitation double precision,
            is_vacances boolean,
            is_ferie boolean,
            lat double precision,
            lon double precision,
            importance_code smallint,
            created_at timestamp with time zone DEFAULT now(),
            CONSTRAINT xgb_training_set_pkey PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_xgb_training_set_channel_computed "
        "ON gold.xgb_training_set (channel_id, computed_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_xgb_training_set_target_speed "
        "ON gold.xgb_training_set (target_speed) WHERE target_speed IS NOT NULL"
    )


def downgrade() -> None:
    """Supprime tout (perte de données)."""
    op.execute("DROP INDEX IF EXISTS gold.idx_xgb_training_set_target_speed")
    op.execute("DROP INDEX IF EXISTS gold.idx_xgb_training_set_channel_computed")
    op.execute("DROP TABLE IF EXISTS gold.xgb_training_set")
    op.execute("DROP INDEX IF EXISTS gold.idx_mv_line_kpis_live_line_id")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS gold.mv_line_kpis_live")
    op.execute("DROP INDEX IF EXISTS referentiel.idx_lieux_calendrier_line_ref")
    op.execute("DROP TABLE IF EXISTS referentiel.lieux_calendrier")
    op.execute("DROP INDEX IF EXISTS referentiel.idx_lieux_transports_lieu_id")
    op.execute("DROP TABLE IF EXISTS referentiel.lieux_transports")
    op.execute("DROP INDEX IF EXISTS referentiel.idx_lieux_lyon_geom")
    op.execute("DROP INDEX IF EXISTS referentiel.idx_lieux_lyon_nom")
    op.execute("DROP TABLE IF EXISTS referentiel.lieux_lyon")
    # Ne supprime PAS le schéma referentiel (peut contenir d'autres tables)
