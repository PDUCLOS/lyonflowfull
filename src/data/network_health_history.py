"""Helper DB pour gold.network_health_history (Sprint 21 P4.3).

Lit l'historique des scores de santé réseau pour la sparkline 24h.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.db import execute_query

logger = logging.getLogger(__name__)


def get_network_health_history(hours: int = 24) -> list[dict]:
    """Retourne l'historique des scores de santé réseau sur les N dernières heures.

    Args:
        hours: fenêtre temporelle (défaut 24h, soit 96 snapshots à */15 min).

    Returns:
        Liste de dicts {recorded_at, score, traffic_score, tcl_score, velov_score, meteo_score}.
        Liste vide si la table n'existe pas encore ou si < 1 row.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = execute_query(
            """
            SELECT
                recorded_at,
                score,
                traffic_score,
                tcl_score,
                velov_score,
                meteo_score
            FROM gold.network_health_history
            WHERE recorded_at >= %s
            ORDER BY recorded_at ASC
            """,
            (cutoff,),
            fetch=True,
        )
        return [dict(row) for row in rows] if rows else []
    except Exception as e:
        # Table pas encore créée (pre-deploy) ou DB indispo → fallback gracieux
        logger.debug("gold.network_health_history non lisible (ignoré): %s", e)
        return []
