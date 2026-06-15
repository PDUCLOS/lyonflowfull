"""create gold.velov_features — LyonFlowFull

Revision ID: 0003_velov_features_table
Revises: 0002_trafic_predictions_indexes
Create Date: 2026-06-14

Sprint P1.1 (2026-06-14) — Fix AUDIT_INTEGRATION_LIVE.md § 1.1.1.

Problème : ``gold.velov_features`` est créée **runtime** par le DAG
``transform_silver_to_gold`` (cf. ``src/transformation/silver_to_gold.py:247``)
mais absente du bootstrap initial ``deploy/init-db.sql``.

Conséquence : un bootstrap ``init-db.sql`` + alembic seul (sans avoir
jamais lancé le DAG gold) laisse la table absente → ``XGBoostVelovModel``
plante à ``_load_training_data()`` (``gold.velov_features does not exist``).
Le code Python référence déjà les bonnes colonnes
(``station_id_encoded, bikes_lag_1/2/3, rolling_mean_3h, hour_sin/cos,
temperature_c, rain_mm, is_vacances, is_ferie``) — aligné avec ce que
crée ``silver_to_gold.py``. La dette est uniquement sur le bootstrap.

Cette migration crée la table avec le même schéma que celui attendu par
le transform silver→gold, pour qu'un environnement fraîchement bootstrappé
ait la structure complète.

Note : la PK ``(station_id_encoded, measurement_time)`` matche le
``ON CONFLICT`` du transform (silver_to_gold.py:273).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_velov_features_table"
down_revision: str | None = "0002_trafic_predictions_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crée gold.velov_features avec PK + index."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gold.velov_features (
            station_id_encoded bigint NOT NULL,
            measurement_time timestamp with time zone NOT NULL,
            station_id character varying(50),
            bikes_available integer,
            bikes_lag_1 integer,
            bikes_lag_2 integer,
            bikes_lag_3 integer,
            rolling_mean_3h double precision,
            hour_sin double precision,
            hour_cos double precision,
            temperature_c double precision,
            rain_mm double precision,
            is_vacances boolean,
            is_ferie boolean,
            CONSTRAINT velov_features_pkey PRIMARY KEY (station_id_encoded, measurement_time)
        )
        """
    )
    # Index secondaire pour les lookups par station_id (sans encodage)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_velov_features_station_id_measurement "
        "ON gold.velov_features (station_id, measurement_time DESC)"
    )


def downgrade() -> None:
    """Supprime la table (perte de données, à utiliser avec précaution)."""
    op.execute("DROP INDEX IF EXISTS gold.idx_velov_features_station_id_measurement")
    op.execute("DROP TABLE IF EXISTS gold.velov_features")
