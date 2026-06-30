"""create referentiel.v_cadence_summary

Revision ID: 0010_referentiel_v_cadence_summary
Revises: 0009_rgpd_tables
Create Date: 2026-06-30

Sprint P3.3 (2026-06-30) — Dette schéma referentiel.

La vue ``referentiel.v_cadence_summary`` est lue par
``scripts/seed_lieux_calendrier.py`` (appelé par le DAG
``refresh_lieux_calendrier`` quotidien 5h) mais n'a jamais été créée
en migration.

Sans elle : le script sort en erreur (UndefinedTable), le DAG fail.

La vue agrège ``gold.tcl_vehicle_realtime`` sur 7 jours glissants pour
calculer la cadence observée par ligne / type de jour / tranche horaire :

- day_type  : 'weekday' (Lun-Ven) | 'saturday' | 'sunday'
- time_bucket : heure 2 chiffres ('06', '07', ..., '22')
- cadence_min_per_vehicle : 60 / n_vehicules_par_heure (approximation)
- n_observations : compte de passages comptés
- confidence : min(1.0, n_obs / 10) — augmente avec le volume de données
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_referentiel_v_cadence_summary"
down_revision: str | None = "0009_rgpd_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW referentiel.v_cadence_summary AS
        SELECT
            v.line_ref,
            CASE
                WHEN EXTRACT(DOW FROM v.recorded_at) = 0 THEN 'sunday'
                WHEN EXTRACT(DOW FROM v.recorded_at) = 6 THEN 'saturday'
                ELSE 'weekday'
            END                                                       AS day_type,
            LPAD(EXTRACT(HOUR FROM v.recorded_at)::text, 2, '0')     AS time_bucket,
            CASE
                WHEN COUNT(*) > 0
                    THEN ROUND((60.0 / NULLIF(COUNT(*), 0))::numeric, 2)
                ELSE NULL
            END                                                       AS cadence_min_per_vehicle,
            COUNT(*)::integer                                         AS n_observations,
            LEAST(1.0, COUNT(*) / 10.0)::numeric(4, 3)               AS confidence
        FROM gold.tcl_vehicle_realtime v
        WHERE v.recorded_at > NOW() - INTERVAL '7 days'
        GROUP BY
            v.line_ref,
            CASE
                WHEN EXTRACT(DOW FROM v.recorded_at) = 0 THEN 'sunday'
                WHEN EXTRACT(DOW FROM v.recorded_at) = 6 THEN 'saturday'
                ELSE 'weekday'
            END,
            LPAD(EXTRACT(HOUR FROM v.recorded_at)::text, 2, '0')
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS referentiel.v_cadence_summary")
