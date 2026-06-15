"""Seed initial users — Pro TCL, Élu.

Crée 2 comptes initiaux avec mots de passe depuis env vars :
- POSTGRES_USER ou PERSONA_PRO_TCL_USERNAME : user Pro TCL
- PERSONA_ELU_USERNAME : user Élu

Usage :
    python scripts/seed_users.py

Idempotent : UPSERT sur username.

Sprint P3.3 (2026-06-14) — AUDIT_INTEGRATION_LIVE.md § P3.3.
Ce script est la pièce qui complète la migration alembic 0004
(création de ``gold.app_users``). Sans seed, la table est vide après
migration → login API inutilisable.

Variables d'env (lues au boot) :
- PERSONA_PRO_TCL_USERNAME (défaut: "pro_tcl")
- PERSONA_PRO_TCL_PASSWORD (requis)
- PERSONA_ELU_USERNAME (défaut: "elu")
- PERSONA_ELU_PASSWORD (requis)
- ADMIN_USERNAME (défaut: "admin")
- ADMIN_PASSWORD (optionnel — admin seulement)

Cf. aussi ``sprint10-summary.md`` pour le flow complet d'auth.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ajouter le workspace au path
WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE))

import bcrypt  # noqa: E402

from src.db import execute_query  # noqa: E402


def seed_user(persona_id: str, username: str, password: str) -> bool:
    """Crée ou met à jour un utilisateur avec mot de passe bcrypt."""
    if not password:
        print(f"⚠️  Pas de mot de passe pour {username}, skip")
        return False

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()

    query = """
        INSERT INTO gold.app_users (persona_id, username, password_hash, is_active, created_at)
        VALUES (%s, %s, %s, TRUE, NOW())
        ON CONFLICT (username) DO UPDATE
        SET password_hash = EXCLUDED.password_hash,
            is_active = TRUE
    """
    try:
        execute_query(query, (persona_id, username, password_hash))
        print(f"✅ {persona_id:10} → {username}")
        return True
    except Exception as e:
        print(f"❌ Erreur seed {username}: {e}")
        return False


def main():
    # Pro TCL
    pro_username = os.getenv("PERSONA_PRO_TCL_USERNAME", "pro_tcl")
    pro_password = os.getenv("PERSONA_PRO_TCL_PASSWORD", "")
    seed_user("pro_tcl", pro_username, pro_password)

    # Élu
    elu_username = os.getenv("PERSONA_ELU_USERNAME", "elu")
    elu_password = os.getenv("PERSONA_ELU_PASSWORD", "")
    seed_user("elu", elu_username, elu_password)

    # Admin (optionnel)
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if admin_password:
        seed_user("admin", admin_username, admin_password)

    print("✅ Seed users terminé")


if __name__ == "__main__":
    main()
