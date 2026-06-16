"""add line_label to gold.mv_otp_heatmap + clamp otp_pct [0, 100]

Revision ID: 0008_mv_otp_heatmap_cleanup
Revises: 0007_gold_views_and_history
Create Date: 2026-06-16

Sprint P2-quater (2026-06-16) — Fix dashboard Pro_TCL Heatmap OTP.

Deux problèmes UX rapportés par user :

1. **Labels pollués** : les ``line_id`` retournés par ``gold.mv_otp_heatmap``
   ont le format ``ActIV:Line::Z18:SYTRAL`` (le ``line_ref`` source de
   ``gold.bus_delay_segments``). Le widget heatmap affiche ça tel quel
   → illisible. Le format souhaité est juste ``Z18`` (le segment
   entre le 2e ``::`` et le ``:SYTRAL`` final).

2. **Valeurs OTP aberrantes** : la heatmap affiche parfois des ``1000%``,
   ``1001%`` sur certaines cases (rapporté par user). Bien que la DB
   ne contienne pas de telles valeurs (max = 100.0), on clamp par
   sécurité dans la vue matérialisée.

**Solution** :
- DROP MATERIALIZED VIEW gold.mv_otp_heatmap
- RECREATE avec une colonne supplémentaire ``line_label`` (regex
  ``regexp_replace(line_id, '^ActIV:Line::(.*?):SYTRAL$', '\\1')``)
  + ``otp_pct`` clampée entre 0 et 100 (``LEAST(GREATEST(..., 0), 100)``)
- RECREATE l'index unique sur (line_id, date, hour)
- REFRESH MATERIALIZED VIEW (rebuild data)

Coût : 1 REFRESH complet (~5-10s sur 12k rows). Acceptable en migration
alembic vu qu'on n'a pas de traffic live pendant le deploy.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_mv_otp_heatmap_cleanup"
down_revision: str | None = "0007_gold_views_and_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add line_label column + clamp otp_pct in mv_otp_heatmap."""
    # 1) DROP l'ancienne vue + index
    op.execute("DROP INDEX IF EXISTS gold.idx_mv_otp_heatmap_line_date_hour")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS gold.mv_otp_heatmap")

    # 2) RECREATE avec colonnes améliorées :
    #    - line_label : segment court extrait du line_id SYTRAL
    #    - otp_pct    : clampé entre 0 et 100 (défense en profondeur)
    #
    # NB : la définition source de la vue (basée sur gold.bus_delay_segments)
    # est recopiée telle quelle — cf. \d+ gold.mv_otp_heatmap en prod.
    # Seul le SELECT final change pour ajouter line_label et clamp.
    op.execute(
        """
        CREATE MATERIALIZED VIEW gold.mv_otp_heatmap AS
        SELECT
            line_ref AS line_id,
            regexp_replace(line_ref, '^ActIV:Line::(.*?):SYTRAL$', r'\1') AS line_label,
            date,
            hour,
            LEAST(GREATEST(
                ROUND(
                    100.0 * SUM(
                        CASE WHEN avg_delay_seconds < 120 THEN 1 ELSE 0 END
                    )::numeric / NULLIF(COUNT(*), 0)::numeric,
                    1
                ),
                0
            ), 100) AS otp_pct,
            ROUND(AVG(avg_delay_seconds), 1) AS avg_delay_s,
            SUM(n_observations) AS n_obs
        FROM gold.bus_delay_segments
        GROUP BY line_ref, date, hour
        ORDER BY line_ref, date, hour
        """
    )

    # 3) Index unique (PK logique pour REFRESH CONCURRENTLY si besoin plus tard)
    op.execute(
        "CREATE UNIQUE INDEX idx_mv_otp_heatmap_line_date_hour "
        "ON gold.mv_otp_heatmap (line_id, date, hour)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mv_otp_heatmap_date "
        "ON gold.mv_otp_heatmap (date DESC)"
    )

    # 4) REFRESH pour peupler la vue
    op.execute("REFRESH MATERIALIZED VIEW gold.mv_otp_heatmap")


def downgrade() -> None:
    """Restore l'ancienne vue sans line_label ni clamp."""
    op.execute("DROP INDEX IF EXISTS gold.idx_mv_otp_heatmap_line_date_hour")
    op.execute("DROP INDEX IF EXISTS gold.idx_mv_otp_heatmap_date")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS gold.mv_otp_heatmap")
    # Recreate minimal (no data, sera repeuplée par DAG daily)
    op.execute(
        """
        CREATE MATERIALIZED VIEW gold.mv_otp_heatmap AS
        SELECT
            v.line_ref AS line_id,
            DATE(v.recorded_at) AS date,
            EXTRACT(HOUR FROM v.recorded_at)::int AS hour,
            ROUND(
                100.0 * SUM(CASE WHEN NOT v.is_delayed THEN 1 ELSE 0 END)::numeric
                / NULLIF(COUNT(*), 0)::numeric,
                1
            ) AS otp_pct
        FROM gold.tcl_vehicle_realtime v
        WHERE v.recorded_at > NOW() - INTERVAL '7 days'
        GROUP BY v.line_ref, DATE(v.recorded_at), EXTRACT(HOUR FROM v.recorded_at)
        WITH NO DATA
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_otp_heatmap_line_date_hour "
        "ON gold.mv_otp_heatmap (line_id, date, hour)"
    )
