"""Assistant pour la table `gold.network_health_history`.

Ce module lit l'historique des scores de santé globale du réseau. Ces données
sont notamment utilisées pour générer le graphique de tendance (sparkline) sur 24h
dans l'interface principale.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from src.db import execute_query

logger = logging.getLogger(__name__)


def get_network_health_history(hours: int = 24) -> list[dict]:
    """Récupère l'historique des scores de santé du réseau sur une période donnée.

    Args:
        hours: Fenêtre temporelle en heures (par défaut 24h, ce qui équivaut 
               à environ 96 instantanés enregistrés toutes les 15 minutes).

    Returns:
        Une liste de dictionnaires contenant les clés suivantes :
        {recorded_at, score, traffic_score, tcl_score, velov_score, meteo_score}.
        Retourne une liste vide si la table n'est pas encore provisionnée ou 
        ne contient aucune ligne.
    """
    try:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
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
        # Si la table n'a pas encore été créée (par exemple avant le premier déploiement complet)
        # ou que la base de données est indisponible, on met en place un fallback gracieux.
        logger.debug("La table gold.network_health_history est illisible ou inexistante (ignoré): %s", e)
        return []
