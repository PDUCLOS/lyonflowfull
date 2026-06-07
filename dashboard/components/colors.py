"""Constantes couleurs — source unique de vérité.

Tous les widgets doivent importer depuis ce fichier plutôt que hardcoder
des hex. Permet de changer le thème en un seul endroit.

Note : les couleurs persona (--primary, --accent) restent gérées par
theme.py (CSS variables injectées selon le persona).
"""

from __future__ import annotations


# Couleurs de base (dark theme)
COLORS = {
    # Backgrounds
    "bg_card": "#1A1D24",
    "bg_card_alt": "#161A20",
    "border_card": "#2A2D34",
    "border_subtle": "#222831",

    # Status (utilisé dans alert_card, correlation_matrix, etc.)
    "status_ok": "#4CAF50",
    "status_warning": "#FF9800",
    "status_critical": "#E74C3C",
    "status_info": "#2196F3",
    "status_bus_lane_ok": "#2196F3",   # alias bleu spécifique

    # Personas (primary colors)
    "persona_usager": "#4CAF50",
    "persona_pro_tcl": "#FF9800",
    "persona_elu": "#3F51B5",

    # UI
    "text_primary": "#FAFAFA",
    "text_secondary": "#BBBBBB",
    "text_muted": "#888888",

    # Diagnostic (correlation bus × trafic)
    "diag_ok": "#4CAF50",
    "diag_infra": "#E74C3C",
    "diag_operations": "#FF9800",
    "diag_bus_lane_ok": "#2196F3",
}


# Helpers pour faciliter l'usage
STATUS_COLORS = {
    "ok": COLORS["status_ok"],
    "warning": COLORS["status_warning"],
    "critical": COLORS["status_critical"],
    "info": COLORS["status_info"],
}


DIAGNOSIS_COLORS = {
    "ok": COLORS["diag_ok"],
    "infra": COLORS["diag_infra"],
    "operations": COLORS["diag_operations"],
    "bus_lane_ok": COLORS["diag_bus_lane_ok"],
}
