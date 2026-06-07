"""RGPD — service centralisé.

Implemente :
- log_audit : trace toute action (RGPD Article 30 — registre des traitements)
- log_data_subject_request : enregistre les demandes utilisateurs
- Anonymisation des IP / user_agent (hash sha256)
"""

from __future__ import annotations

import hashlib
import hmac  # constant-time comparison
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from src.config import get_settings
from src.db import execute_query, execute_scalar


logger = logging.getLogger(__name__)


def _hash(value: str) -> str:
    """Hash SHA256 d'une valeur (pour anonymisation RGPD)."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def log_audit(
    actor: str,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """Enregistre une action dans le log d'audit.

    Args:
        actor: qui a fait l'action (user, api, system:dag_xxx, etc.).
        action: verbe d'action (login, predict, export, view, etc.).
        resource_type: type de ressource touchée.
        resource_id: ID de la ressource.
        ip_address: IP (sera hashée avant stockage).
        user_agent: User agent (sera hashé).
        details: dict de détails complémentaires (sera JSON-sérialisé).
    """
    import json
    query = """
        INSERT INTO rgpd.audit_log
            (event_time, actor, action, resource_type, resource_id,
             ip_address, user_agent, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        execute_query(query, (
            datetime.now(timezone.utc),
            actor[:64],  # truncate
            action[:64],
            resource_type,
            resource_id,
            _hash(ip_address) if ip_address else None,  # hash IP
            _hash(user_agent) if user_agent else None,   # hash UA
            json.dumps(details, default=str) if details else None,
        ))
    except Exception as e:
        # Ne pas faire échouer l'action principale si l'audit log échoue
        logger.warning(f"Audit log failed: {e}")


def log_data_subject_request(
    user_identifier: str,
    request_type: str,
    notes: Optional[str] = None,
) -> str:
    """Enregistre une demande RGPD (accès, suppression, portabilité, rectification).

    Args:
        user_identifier: identifiant anonyme de l'utilisateur (déjà hashé upstream).
        request_type: 'access' | 'deletion' | 'portability' | 'rectification'
        notes: notes optionnelles.

    Returns:
        request_id (UUID string).
    """
    import uuid
    request_id = str(uuid.uuid4())
    query = """
        INSERT INTO rgpd.data_subject_requests
            (request_id, user_identifier, request_type, status, requested_at, notes)
        VALUES (%s, %s, %s, 'pending', %s, %s)
    """
    try:
        execute_query(query, (
            request_id, _hash(user_identifier), request_type,
            datetime.now(timezone.utc), notes,
        ))
        logger.info(f"RGPD request {request_id} recorded: {request_type}")
    except Exception as e:
        logger.error(f"RGPD request failed: {e}")
        raise
    return request_id


def purge_old_audit_logs(days: int = 365) -> int:
    """Purge les audit logs > N jours (rétention RGPD)."""
    # PostgreSQL ne permet PAS de paramétrer à l'intérieur d'INTERVAL
    # Solution : utiliser make_interval(jours => N) ou concat
    query = """
        DELETE FROM rgpd.audit_log
        WHERE event_time < NOW() - make_interval(days => %s)
    """
    from src.db import raw_connection
    with raw_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (days,))
            return cur.rowcount


def get_user_consent(user_identifier: str) -> dict:
    """Récupère l'état du consentement d'un utilisateur."""
    query = """
        SELECT consent_type, granted, granted_at, expires_at
        FROM rgpd.user_consents
        WHERE user_identifier = %s
        ORDER BY granted_at DESC
    """
    rows = execute_query(query, (_hash(user_identifier),))
    return {r["consent_type"]: r for r in rows}


def set_user_consent(
    user_identifier: str,
    consent_type: str,
    granted: bool,
    expires_at: Optional[datetime] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Enregistre le consentement (ou refus) d'un utilisateur."""
    import json
    query = """
        INSERT INTO rgpd.user_consents
            (user_identifier, consent_type, granted, expires_at,
             ip_hash, user_agent_hash)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    execute_query(query, (
        _hash(user_identifier), consent_type, granted, expires_at,
        _hash(ip_address) if ip_address else None,
        _hash(user_agent) if user_agent else None,
    ))
    log_audit(
        actor=user_identifier[:8],
        action=f"consent_{'granted' if granted else 'revoked'}",
        resource_type="consent",
        resource_id=consent_type,
        details={"expires_at": expires_at.isoformat() if expires_at else None},
    )
