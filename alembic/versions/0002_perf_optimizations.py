"""perf: autovacuum tuning + plpgsql helpers permanents

Revision ID: 0002_perf_optimizations
Revises: 0001_initial
Create Date: 2026-06-30

Sprint P3.4 (2026-06-30) — Optimisations pipeline data.

1. Autovacuum agressif sur gold.tcl_vehicle_realtime et
   gold.traffic_features_live (DELETE massif toutes les 10 min →
   bloat rapide sans tuning).

2. Fonctions PL/pgSQL _is_ferie/_is_vacances permanentes en DB.
   Avant cette migration : silver_to_gold.py recréait ces fonctions
   via CREATE OR REPLACE à chaque call (3x per 10-min run = DDL inutile).
   Avec la migration : fonctions existent dès le déploiement initial.
   silver_to_gold._ensure_helpers() reste en fallback mais devient NOP
   si les fonctions sont déjà là.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_perf_optimizations"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Autovacuum sur tables haute-fréquence
    # gold.tcl_vehicle_realtime : DELETE + INSERT toutes les 10 min
    # gold.traffic_features_live : UPSERT massif toutes les 10 min
    # -------------------------------------------------------------------------
    op.execute("""
        ALTER TABLE gold.tcl_vehicle_realtime SET (
            autovacuum_vacuum_scale_factor  = 0.01,
            autovacuum_vacuum_cost_delay    = 2,
            autovacuum_analyze_scale_factor = 0.005
        )
    """)
    op.execute("""
        ALTER TABLE gold.traffic_features_live SET (
            autovacuum_vacuum_scale_factor  = 0.02,
            autovacuum_vacuum_cost_delay    = 5,
            autovacuum_analyze_scale_factor = 0.01
        )
    """)

    # -------------------------------------------------------------------------
    # 2. Fonctions PL/pgSQL calendaires permanentes
    # -------------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION _is_ferie(d date) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT EXISTS (
                SELECT 1
                FROM bronze.jours_feries jf
                WHERE jf.date_ferie = d
                   OR (jf.raw_data IS NOT NULL
                       AND (jf.raw_data->>'date')::date = d)
            );
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION _is_vacances(d date) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT EXISTS (
                SELECT 1
                FROM bronze.calendrier_scolaire cs
                WHERE cs.start_date <= d
                  AND cs.end_date   >= d
                  AND cs.zone ILIKE 'A'
            )
            OR EXISTS (
                SELECT 1
                FROM bronze.calendrier_scolaire cs,
                     LATERAL jsonb_array_elements(
                         CASE WHEN jsonb_typeof(cs.raw_data->'records') = 'array'
                              THEN cs.raw_data->'records'
                              ELSE '[]'::jsonb END
                     ) AS rec
                WHERE cs.start_date IS NULL
                  AND (rec->'fields'->>'start_date')::date <= d
                  AND (rec->'fields'->>'end_date')::date   >= d
                  AND COALESCE(rec->'fields'->>'zones', '') ILIKE '%zone a%'
            );
        $$
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE gold.tcl_vehicle_realtime RESET (autovacuum_vacuum_scale_factor, autovacuum_vacuum_cost_delay, autovacuum_analyze_scale_factor)"
    )
    op.execute(
        "ALTER TABLE gold.traffic_features_live RESET (autovacuum_vacuum_scale_factor, autovacuum_vacuum_cost_delay, autovacuum_analyze_scale_factor)"
    )
    op.execute("DROP FUNCTION IF EXISTS _is_ferie(date)")
    op.execute("DROP FUNCTION IF EXISTS _is_vacances(date)")
