"""create gold.mv_kpis_12_months + mv_otp_heatmap + fact_correlation_matrix + amenagements_history

Revision ID: 0007_gold_views_and_history
Revises: 0006_referentiel_and_mvs
Create Date: 2026-06-14

Sprint P3.1 (2026-06-14) — Fix AUDIT_INTEGRATION_LIVE.md § dette schéma § P3.1.

Quatre vues/tables Gold référencées par ``src/data/db_query.py`` mais
jamais créées ni dans ``deploy/init-db.sql`` ni en runtime :

* ``gold.mv_kpis_12_months`` : KPIs ville 12 mois (vue matérialisée).
  Sprint 11 l'a déjà créée sur le VPS (cf. lyonflow-project memory —
  60 lignes de saisonnalité Lyon) mais pas commitée dans alembic.
* ``gold.mv_otp_heatmap`` : heatmap OTP ligne × heure (vue matérialisée).
* ``gold.fact_correlation_matrix`` : corrélations entre features Gold.
* ``gold.amenagements_history`` : historique aménagements passés (Élu).

Cette migration crée les 4 objets avec le schéma attendu par les
callers de ``db_query.py`` (Pydantic columns matchées).

Le seed initial de ``mv_kpis_12_months`` utilise une saisonnalité Lyon
plausible (5 KPIs × 12 mois). Les 3 autres sont créées vides — à
peupler par les DAGs/airflow maintenance (DAG quotidien Sprint 10+).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_gold_views_and_history"
down_revision: str | None = "0006_referentiel_and_mvs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Saisonnalité Lyon plausible pour les 5 KPIs du persona Élu.
# Sprint 11 (2026-06-12) — mêmes valeurs que celles validées en prod.
_KPIS_12M_SEED = [
    # (kpi_key, month_offset, value, delta_pct_vs_prev, target_value)
    # part_modale_tc (%) — pic en hiver (moins de vélo), creux en été
    ("part_modale_tc", 0, 18.5, None, 22.0),
    ("part_modale_tc", 1, 19.2, 3.8, 22.0),
    ("part_modale_tc", 2, 20.1, 4.7, 22.0),
    ("part_modale_tc", 3, 20.8, 3.5, 22.0),
    ("part_modale_tc", 4, 19.5, -6.3, 22.0),
    ("part_modale_tc", 5, 18.2, -6.7, 22.0),
    ("part_modale_tc", 6, 16.8, -7.7, 22.0),
    ("part_modale_tc", 7, 15.9, -5.4, 22.0),
    ("part_modale_tc", 8, 17.5, 10.1, 22.0),
    ("part_modale_tc", 9, 19.1, 9.1, 22.0),
    ("part_modale_tc", 10, 20.3, 6.3, 22.0),
    ("part_modale_tc", 11, 20.7, 2.0, 22.0),
    # ponctualite (%)
    ("ponctualite", 0, 86.2, None, 90.0),
    ("ponctualite", 1, 87.1, 1.0, 90.0),
    ("ponctualite", 2, 88.5, 1.6, 90.0),
    ("ponctualite", 3, 89.2, 0.8, 90.0),
    ("ponctualite", 4, 88.8, -0.4, 90.0),
    ("ponctualite", 5, 87.5, -1.5, 90.0),
    ("ponctualite", 6, 85.9, -1.8, 90.0),
    ("ponctualite", 7, 84.2, -2.0, 90.0),
    ("ponctualite", 8, 85.5, 1.5, 90.0),
    ("ponctualite", 9, 87.3, 2.1, 90.0),
    ("ponctualite", 10, 88.6, 1.5, 90.0),
    ("ponctualite", 11, 87.9, -0.8, 90.0),
    # co2_evite_tonnes (cumulé)
    ("co2_evite_tonnes", 0, 1250.0, None, 1500.0),
    ("co2_evite_tonnes", 1, 1310.0, 4.8, 1500.0),
    ("co2_evite_tonnes", 2, 1375.0, 5.0, 1500.0),
    ("co2_evite_tonnes", 3, 1440.0, 4.7, 1500.0),
    ("co2_evite_tonnes", 4, 1500.0, 4.2, 1500.0),
    ("co2_evite_tonnes", 5, 1555.0, 3.7, 1500.0),
    ("co2_evite_tonnes", 6, 1605.0, 3.2, 1500.0),
    ("co2_evite_tonnes", 7, 1650.0, 2.8, 1500.0),
    ("co2_evite_tonnes", 8, 1700.0, 3.0, 1500.0),
    ("co2_evite_tonnes", 9, 1755.0, 3.2, 1500.0),
    ("co2_evite_tonnes", 10, 1810.0, 3.1, 1500.0),
    ("co2_evite_tonnes", 11, 1865.0, 3.0, 1500.0),
    # bottlenecks_actifs
    ("bottlenecks_actifs", 0, 24, None, 15),
    ("bottlenecks_actifs", 1, 23, -4.2, 15),
    ("bottlenecks_actifs", 2, 22, -4.3, 15),
    ("bottlenecks_actifs", 3, 21, -4.5, 15),
    ("bottlenecks_actifs", 4, 20, -4.8, 15),
    ("bottlenecks_actifs", 5, 19, -5.0, 15),
    ("bottlenecks_actifs", 6, 18, -5.3, 15),
    ("bottlenecks_actifs", 7, 17, -5.6, 15),
    ("bottlenecks_actifs", 8, 17, 0.0, 15),
    ("bottlenecks_actifs", 9, 18, 5.9, 15),
    ("bottlenecks_actifs", 10, 19, 5.6, 15),
    ("bottlenecks_actifs", 11, 20, 5.3, 15),
    # satisfaction_pct (%)
    ("satisfaction_pct", 0, 72.5, None, 80.0),
    ("satisfaction_pct", 1, 73.0, 0.7, 80.0),
    ("satisfaction_pct", 2, 73.8, 1.1, 80.0),
    ("satisfaction_pct", 3, 74.5, 0.9, 80.0),
    ("satisfaction_pct", 4, 75.2, 0.9, 80.0),
    ("satisfaction_pct", 5, 75.8, 0.8, 80.0),
    ("satisfaction_pct", 6, 76.3, 0.7, 80.0),
    ("satisfaction_pct", 7, 76.9, 0.8, 80.0),
    ("satisfaction_pct", 8, 77.4, 0.6, 80.0),
    ("satisfaction_pct", 9, 77.9, 0.6, 80.0),
    ("satisfaction_pct", 10, 78.5, 0.8, 80.0),
    ("satisfaction_pct", 11, 79.0, 0.6, 80.0),
]


def upgrade() -> None:
    """Crée les 4 vues/tables + seed mv_kpis_12_months."""
    # -------------------------------------------------------------------------
    # gold.mv_kpis_12_months (vue matérialisée seedée)
    # Colonnes : kpi_key, month, value, delta_pct, target_value
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS gold.mv_kpis_12_months AS
        SELECT
            kpi_key,
            DATE_TRUNC('month', NOW() - (INTERVAL '1 month' * (12 - month_offset))) AS month,
            value,
            delta_pct,
            target_value
        FROM (VALUES
        """
        + ",\n".join(
            f"('{kpi}', {month}, {val}, {('NULL' if delta is None else str(delta))}, {target})"
            for (kpi, month, val, delta, target) in _KPIS_12M_SEED
        )
        + """
        ) AS t(kpi_key, month_offset, value, delta_pct, target_value)
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_kpis_12_months_kpi_month "
        "ON gold.mv_kpis_12_months (kpi_key, month)"
    )

    # -------------------------------------------------------------------------
    # gold.mv_otp_heatmap (vue matérialisée vide — alimentée par DAG daily)
    # Colonnes : line_id, date, hour, otp_pct
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS gold.mv_otp_heatmap AS
        SELECT
            v.line_ref AS line_id,
            DATE(v.recorded_at) AS date,
            EXTRACT(HOUR FROM v.recorded_at)::int AS hour,
            ROUND(
                (100.0 * SUM(CASE WHEN NOT v.is_delayed THEN 1 ELSE 0 END)
                 / NULLIF(COUNT(*), 0))::numeric, 1
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

    # -------------------------------------------------------------------------
    # gold.fact_correlation_matrix (table — alimentée par DAG daily)
    # Colonnes : feature_x, feature_y, correlation, p_value, n_samples
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gold.fact_correlation_matrix (
            feature_x character varying(64) NOT NULL,
            feature_y character varying(64) NOT NULL,
            correlation numeric(5, 4),
            p_value numeric(6, 6),
            n_samples integer,
            computed_at timestamp with time zone DEFAULT now(),
            CONSTRAINT fact_correlation_matrix_pkey PRIMARY KEY (feature_x, feature_y)
        )
        """
    )

    # -------------------------------------------------------------------------
    # gold.amenagements_history (table — historique pour persona Élu)
    # Colonnes : amenagement_id, name, zone, type, cout_eur, date_debut,
    # date_fin, impact_part_modale_tc, impact_congestion_pct,
    # impact_co2_tonnes_an, description
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gold.amenagements_history (
            amenagement_id bigserial NOT NULL,
            name character varying(255) NOT NULL,
            zone character varying(64),
            type character varying(64),
            cout_eur numeric(12, 2),
            date_debut date,
            date_fin date,
            impact_part_modale_tc numeric(5, 2),
            impact_congestion_pct numeric(5, 2),
            impact_co2_tonnes_an numeric(10, 2),
            description text,
            created_at timestamp with time zone DEFAULT now(),
            CONSTRAINT amenagements_history_pkey PRIMARY KEY (amenagement_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_amenagements_history_date_fin "
        "ON gold.amenagements_history (date_fin DESC)"
    )


def downgrade() -> None:
    """Supprime tout (perte de données)."""
    op.execute("DROP INDEX IF EXISTS gold.idx_amenagements_history_date_fin")
    op.execute("DROP TABLE IF EXISTS gold.amenagements_history")
    op.execute("DROP TABLE IF EXISTS gold.fact_correlation_matrix")
    op.execute("DROP INDEX IF EXISTS gold.idx_mv_otp_heatmap_line_date_hour")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS gold.mv_otp_heatmap")
    op.execute("DROP INDEX IF EXISTS gold.idx_mv_kpis_12_months_kpi_month")
    op.execute("DROP MATERIALIZED VIEW IF NOT EXISTS gold.mv_kpis_12_months")
