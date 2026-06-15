"""index gold.trafic_predictions — LyonFlowFull

Revision ID: 0002_trafic_predictions_indexes
Revises: 0001_initial
Create Date: 2026-06-14

Sprint P0 (2026-06-14) — Fix AUDIT_INTEGRATION_LIVE.md § 1.1.3.

Problème : ``gold.trafic_predictions`` n'a aucun index sur
``calculated_at``. Le DAG ``dag_live_speed_retrain`` fait :

* INSERT hourly (~4400 rows/h : 4 horizons × ~1100 axes)
* DELETE WHERE calculated_at < NOW() - INTERVAL '7 days' (cleanup)
* SELECT WHERE calculated_at >= NOW() - INTERVAL '2 hours' (dashboard)

Sur 7 jours à 4400 rows/h, ça donne ~740k rows. Le DELETE/SELECT hourly
fait du seq scan → dégradation progressive.

Cette migration ajoute 2 index :
* ``idx_trafic_predictions_calculated_at`` : couvre DELETE + SELECT dashboard
* ``idx_trafic_predictions_horizon_calc`` : couvre le SELECT avec filtre
  horizon_h (widget carte GNN)

Idempotence : ``CREATE INDEX IF NOT EXISTS`` pour permettre de rejouer
la migration sans erreur. Alembic tracke la version dans
``alembic_version`` → pas de double-exécution.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_trafic_predictions_indexes"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Ajoute les index manquants sur gold.trafic_predictions."""
    # Index 1 : calculated_at seul (couvre le cleanup + SELECT dashboard simple)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_trafic_predictions_calculated_at "
        "ON gold.trafic_predictions (calculated_at DESC)"
    )
    # Index 2 : composite (horizon_h, calculated_at) — couvre le SELECT filtré
    # utilisé par get_traffic_predictions() du dashboard (carte GNN par horizon).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_trafic_predictions_horizon_calc "
        "ON gold.trafic_predictions (horizon_h, calculated_at DESC)"
    )


def downgrade() -> None:
    """Supprime les index. Pas de perte de données (juste perf)."""
    op.execute("DROP INDEX IF EXISTS gold.idx_trafic_predictions_horizon_calc")
    op.execute("DROP INDEX IF EXISTS gold.idx_trafic_predictions_calculated_at")
