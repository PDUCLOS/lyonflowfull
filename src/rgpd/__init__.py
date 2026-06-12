"""RGPD — conformité, consent, audit, data subject rights."""

from src.rgpd.service import (
    get_user_consent,
    log_audit,
    log_data_subject_request,
    purge_old_audit_logs,
    set_user_consent,
)

__all__ = [
    "get_user_consent",
    "log_audit",
    "log_data_subject_request",
    "purge_old_audit_logs",
    "set_user_consent",
]
