"""Constantes du module data — seuils et valeurs de référence.

Centralise les seuils métier pour éviter la duplication (ex. magic
numbers 300/1800 dupliqués entre ``load_traffic()`` et
``render_traffic_widget()`` avant Sprint 22+).

Convention : les constantes exportées sont en MAJUSCULES, sans
préfixe underscore. Les helpers privés restent en lowercase.
"""

from __future__ import annotations

# =============================================================================
# Freshness — âge maximal d'une mesure DB pour la classifier
# =============================================================================
# Seuils utilisés à la fois par ``load_traffic()`` (data_loader.py) pour
# calculer ``freshness_status`` et par ``render_traffic_widget()`` pour
# afficher le bandeau adaptatif. Doivent rester synchronisés.
FRESHNESS_LIVE_MAX_S: int = 300       # < 5 min  → 🟢 Live
FRESHNESS_STALE_MAX_S: int = 1800     # < 30 min → 🟡 Stale
# > FRESHNESS_STALE_MAX_S              → 🔴 Stuck


# =============================================================================
# Congestion — seuil de détection bouchon (vitesse moyenne Lyon)
# =============================================================================
# Référence ADEME 2024, étude impact trafic urbain. < 25 km/h en ville =
# bouchon structurel (ralenti +40% conso + émissions).
CONGESTION_SPEED_THRESHOLD_KMH: float = 25.0
