"""Constantes du module data — seuils et valeurs de référence.

Centralise les seuils métier pour éviter la duplication de valeurs arbitraires
(ex. les valeurs 300/1800 partagées entre ``load_traffic()`` et
``render_traffic_widget()``).

Convention : les constantes exportées sont en MAJUSCULES, sans
préfixe underscore. Les fonctions ou variables privées restent en minuscules.
"""

from __future__ import annotations

# =============================================================================
# Freshness — âge maximal d'une mesure DB pour la classifier
# =============================================================================
# Seuils utilisés à la fois par ``load_traffic()`` (data_loader.py) pour
# calculer ``freshness_status`` et par ``render_traffic_widget()`` pour
# afficher le bandeau adaptatif. Ces valeurs doivent rester synchronisées.
FRESHNESS_LIVE_MAX_S: int = 300  # < 5 min → Donnée en direct (Live)
FRESHNESS_STALE_MAX_S: int = 1800  # < 30 min → Donnée obsolète (Stale)
# > FRESHNESS_STALE_MAX_S → Donnée bloquée (Stuck)


# =============================================================================
# Congestion — seuil de détection bouchon (vitesse moyenne Lyon)
# =============================================================================
# Référence ADEME 2024, étude de l'impact du trafic urbain.
# < 25 km/h en ville = bouchon structurel (ralenti, +40% de consommation et émissions).
CONGESTION_SPEED_THRESHOLD_KMH: float = 25.0
