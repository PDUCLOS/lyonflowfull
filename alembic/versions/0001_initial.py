"""initial schema — LyonFlowFull

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-06

Schéma initial complet :
- Schémas : bronze, silver, gold, rgpd, governance, mlflow, airflow
- Tables Bronze (8), Silver (5), Gold (8), RGPD (4), Governance (2)
- Indexes, contraintes, triggers
- PostGIS extension

Note : en pratique, on utilise deploy/init-db.sql pour le bootstrap initial.
Cette migration Alembic sert pour les évolutions futures.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Le schéma initial est créé par deploy/init-db.sql
    # Cette migration est un placeholder pour les évolutions futures
    # On marque juste la version pour qu'Alembic sache qu'on est à jour
    op.execute("SELECT 1")  # no-op


def downgrade() -> None:
    # Symétrique inverse — ne supprime PAS le schéma (trop dangereux)
    # En cas de rollback complet : drop database et recréer
    op.execute("SELECT 1")  # no-op
