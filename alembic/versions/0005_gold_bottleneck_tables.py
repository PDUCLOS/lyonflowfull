"""create gold.bus_delay_segments + gold.infrastructure_bottlenecks — LyonFlowFull

Revision ID: 0005_gold_bottleneck_tables
Revises: 0004_app_users_table
Create Date: 2026-06-14

Sprint P2.5 (2026-06-14) — Fix AUDIT_INTEGRATION_LIVE.md § dette schéma.

Ces 2 tables sont créées **runtime** par le DAG
``transform_silver_to_gold`` (cf. ``src/transformation/silver_to_gold.py:285,411``)
mais absentes du bootstrap initial ``deploy/init-db.sql``.

Conséquence : un bootstrap ``init-db.sql`` + alembic seul (sans avoir
jamais lancé le DAG gold) laisse les 2 tables absentes → les widgets
``Pro_4_Simulateur`` (qui lit ``gold.bus_delay_segments``) et la carte
Élu (qui lit ``gold.infrastructure_bottlenecks``) plantent.

Cette migration crée les 2 tables avec le même schéma que celui attendu
par le transform silver→gold, pour qu'un environnement fraîchement
bootstrappé ait la structure complète.

Le code Python des transforms ``silver_to_gold.py`` n'est pas modifié —
il référence déjà les bonnes colonnes.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_gold_bottleneck_tables"
down_revision: str | None = "0004_app_users_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crée les 2 tables bottleneck avec PK + index."""
    # gold.bus_delay_segments
    # PK = (date, hour, line_ref, segment_id) — matche le ON CONFLICT
    # du transform (silver_to_gold.py:311).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gold.bus_delay_segments (
            date date NOT NULL,
            hour smallint NOT NULL,
            line_ref character varying(32) NOT NULL,
            segment_id character varying(64) NOT NULL,
            avg_delay_seconds numeric(8, 2),
            n_observations integer,
            is_vacances boolean,
            is_ferie boolean,
            weather_code integer,
            CONSTRAINT bus_delay_segments_pkey PRIMARY KEY (date, hour, line_ref, segment_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bus_delay_segments_line_ref_date "
        "ON gold.bus_delay_segments (line_ref, date DESC)"
    )

    # gold.infrastructure_bottlenecks
    # Pas de PK stricte côté DB (le transform fait DELETE + INSERT à
    # chaque exécution, donc la PK technique n'a pas de sens avec un
    # computed_at = NOW()). On met une PK composite (segment_id, line_ref,
    # computed_at) pour permettre des UPSERTs propres le jour où le
    # transform passera en mode incrémental.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gold.infrastructure_bottlenecks (
            id bigserial NOT NULL,
            segment_id character varying(64) NOT NULL,
            line_ref character varying(32) NOT NULL,
            diagnosis character varying(64),
            computed_at timestamp with time zone NOT NULL DEFAULT now(),
            bus_delay_seconds numeric(8, 2),
            traffic_speed_kmh numeric(8, 2),
            traffic_congestion numeric(4, 3),
            lat double precision,
            lon double precision,
            n_observations integer,
            CONSTRAINT infrastructure_bottlenecks_pkey PRIMARY KEY (id)
        )
        """
    )
    # Index pour les lookups (cf. P2.2 — geocoder bottlenecks carte Élu)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_infra_bottlenecks_line_ref_computed "
        "ON gold.infrastructure_bottlenecks (line_ref, computed_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_infra_bottlenecks_geo "
        "ON gold.infrastructure_bottlenecks (lat, lon) "
        "WHERE lat IS NOT NULL AND lon IS NOT NULL"
    )


def downgrade() -> None:
    """Supprime les 2 tables (perte de données)."""
    op.execute("DROP INDEX IF EXISTS gold.idx_infra_bottlenecks_geo")
    op.execute("DROP INDEX IF EXISTS gold.idx_infra_bottlenecks_line_ref_computed")
    op.execute("DROP TABLE IF EXISTS gold.infrastructure_bottlenecks")
    op.execute("DROP INDEX IF EXISTS gold.idx_bus_delay_segments_line_ref_date")
    op.execute("DROP TABLE IF EXISTS gold.bus_delay_segments")
