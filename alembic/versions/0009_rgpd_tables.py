"""create rgpd.audit_log + user_consents + data_subject_requests + purge_log

Revision ID: 0009_rgpd_tables
Revises: 0008_mv_otp_heatmap_cleanup
Create Date: 2026-06-30

Sprint P3.2 (2026-06-30) — Dette schéma RGPD.

Quatre tables RGPD référencées dans src/rgpd/service.py et
dags/maintenance/maintenance.py mais jamais créées en migration :

* rgpd.audit_log       : registre Article 30 — toute action tracée
* rgpd.user_consents   : consentements utilisateurs (analytics, etc.)
* rgpd.data_subject_requests : demandes Article 15/17/20 (accès, suppression…)
* rgpd.purge_log       : historique des purges Bronze/Silver (RGPD rétention)

Sans ces tables :
- log_audit() échoue silencieusement (catch Exception) → pas de trace d'audit
- purge_bronze DAG échoue sur INSERT rgpd.purge_log → relation does not exist
- Dashboard RGPD affiche uniquement les mocks (DB empty → fallback mock)
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_rgpd_tables"
down_revision: str | None = "0008_mv_otp_heatmap_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # rgpd.audit_log — registre Article 30
    # Colonnes : event_time, actor, action, resource_type, resource_id,
    #            ip_address, user_agent, details
    # ip_address et user_agent sont hashés SHA256 avant insertion (service.py).
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rgpd.audit_log (
            id             bigserial PRIMARY KEY,
            event_time     timestamptz NOT NULL DEFAULT now(),
            actor          character varying(64) NOT NULL,
            action         character varying(64) NOT NULL,
            resource_type  text,
            resource_id    text,
            ip_address     character varying(32),
            user_agent     character varying(32),
            details        jsonb
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_rgpd_audit_log_event_time ON rgpd.audit_log (event_time DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_rgpd_audit_log_actor ON rgpd.audit_log (actor)")

    # -------------------------------------------------------------------------
    # rgpd.user_consents — consentements par utilisateur et type
    # user_identifier = SHA256[:32] de l'identifiant réel.
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rgpd.user_consents (
            id                bigserial PRIMARY KEY,
            user_identifier   character varying(32) NOT NULL,
            consent_type      character varying(64) NOT NULL,
            granted           boolean NOT NULL,
            granted_at        timestamptz NOT NULL DEFAULT now(),
            expires_at        timestamptz,
            ip_hash           character varying(32),
            user_agent_hash   character varying(32)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_rgpd_user_consents_user ON rgpd.user_consents (user_identifier, consent_type)"
    )

    # -------------------------------------------------------------------------
    # rgpd.data_subject_requests — DSR Article 15/17/20
    # request_id = UUID v4 généré côté applicatif.
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rgpd.data_subject_requests (
            request_id      character varying(36) PRIMARY KEY,
            user_identifier character varying(32) NOT NULL,
            request_type    character varying(32) NOT NULL,
            status          character varying(16) NOT NULL DEFAULT 'pending',
            requested_at    timestamptz NOT NULL DEFAULT now(),
            completed_at    timestamptz,
            notes           text
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_rgpd_dsr_status ON rgpd.data_subject_requests (status, requested_at DESC)"
    )

    # -------------------------------------------------------------------------
    # rgpd.purge_log — historique des purges Bronze/Silver (rétention RGPD)
    # Alimentée par dags/maintenance/maintenance.py _purge_bronze().
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rgpd.purge_log (
            id             bigserial PRIMARY KEY,
            schema_name    character varying(64) NOT NULL,
            table_name     character varying(128) NOT NULL,
            rows_purged    integer NOT NULL DEFAULT 0,
            retention_days integer NOT NULL,
            purged_at      timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_rgpd_purge_log_purged_at ON rgpd.purge_log (purged_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS rgpd.idx_rgpd_purge_log_purged_at")
    op.execute("DROP TABLE IF EXISTS rgpd.purge_log")
    op.execute("DROP INDEX IF EXISTS rgpd.idx_rgpd_dsr_status")
    op.execute("DROP TABLE IF EXISTS rgpd.data_subject_requests")
    op.execute("DROP INDEX IF EXISTS rgpd.idx_rgpd_user_consents_user")
    op.execute("DROP TABLE IF EXISTS rgpd.user_consents")
    op.execute("DROP INDEX IF EXISTS rgpd.idx_rgpd_audit_log_actor")
    op.execute("DROP INDEX IF EXISTS rgpd.idx_rgpd_audit_log_event_time")
    op.execute("DROP TABLE IF EXISTS rgpd.audit_log")
