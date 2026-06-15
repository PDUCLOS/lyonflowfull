"""create gold.app_users — LyonFlowFull

Revision ID: 0004_app_users_table
Revises: 0003_velov_features_table
Create Date: 2026-06-14

Sprint P1.5 (2026-06-14) — Fix AUDIT_INTEGRATION_LIVE.md § 2.2.2.

Problème : l'endpoint ``/api/v1/auth/login`` (src/api/main.py:537) fait
un SELECT sur ``gold.app_users`` mais la table n'existe ni dans
``deploy/init-db.sql`` ni runtime. Conséquence : 500 systématique sur
login → auth personas Pro/Élu cassée en prod.

Cette migration crée la table avec les colonnes minimales nécessaires
à l'endpoint :

* ``user_id`` : UUID (PK)
* ``username`` : identifiant unique (UNIQUE)
* ``password_hash`` : bcrypt hash (cf. src/api/main.py:549)
* ``persona_id`` : 'pro_tcl' | 'elu' | 'admin' (CHECK constraint)
* ``is_active`` : bool (filtre dans le SELECT login)
* ``created_at``, ``last_login_at`` : audit/traçabilité

Aucun utilisateur n'est créé par défaut — l'admin doit les ajouter
manuellement ou via un script de seed (post-migration). Cf. scripts/
pour le seed à venir.

Le CHECK sur persona_id matche la spec des personas (cf.
src/persona/personas_loader.py et src/api/main.py:130).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_app_users_table"
down_revision: str | None = "0003_velov_features_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crée gold.app_users avec contraintes minimales."""
    # Nécessaire pour gen_random_uuid() (PostgreSQL 13+)
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gold.app_users (
            user_id uuid NOT NULL DEFAULT gen_random_uuid(),
            username character varying(64) NOT NULL,
            password_hash character varying(255) NOT NULL,
            persona_id character varying(32) NOT NULL,
            is_active boolean NOT NULL DEFAULT TRUE,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            last_login_at timestamp with time zone,
            CONSTRAINT app_users_pkey PRIMARY KEY (user_id),
            CONSTRAINT app_users_username_key UNIQUE (username),
            CONSTRAINT app_users_persona_id_check CHECK (
                persona_id IN ('pro_tcl', 'elu', 'admin')
            )
        )
        """
    )
    # Index secondaire utile pour les lookups par persona (admin dashboard)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_app_users_persona_id_active "
        "ON gold.app_users (persona_id) WHERE is_active = TRUE"
    )


def downgrade() -> None:
    """Supprime la table. Perte des comptes utilisateurs."""
    op.execute("DROP INDEX IF EXISTS gold.idx_app_users_persona_id_active")
    op.execute("DROP TABLE IF EXISTS gold.app_users")
