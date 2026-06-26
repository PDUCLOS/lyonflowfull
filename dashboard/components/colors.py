"""Constantes couleurs — source unique de vérité.

Tous les widgets doivent importer depuis ce fichier plutôt que hardcoder
des hex. Permet de changer le thème en un seul endroit.

Note : les couleurs persona (--primary, --accent) restent gérées par
theme.py (CSS variables injectées selon le persona).
"""

from __future__ import annotations

# Couleurs de base (dark theme - Glassmorphism & Slate)
COLORS = {
    # Backgrounds
    "bg_app": "#0B0F19",  # Slate deep
    "bg_card": "rgba(30, 41, 59, 0.5)",  # Slate 800 + alpha pour glassmorphism
    "bg_card_alt": "rgba(15, 23, 42, 0.5)",  # Slate 900 + alpha
    "bg_card_deep": "#0F172A",  # Slate 900 opaque
    "border_card": "rgba(148, 163, 184, 0.12)",  # Slate border subtile
    "border_subtle": "rgba(148, 163, 184, 0.05)",
    # Status
    "status_ok": "#10B981",  # Emerald 500
    "status_warning": "#F59E0B",  # Amber 500
    "status_critical": "#EF4444",  # Red 500
    "status_info": "#3B82F6",  # Blue 500
    "status_bus_lane_ok": "#3B82F6",
    # Personas (primary colors vibrantes)
    "persona_usager": "#10B981",  # Emerald
    "persona_usager_accent": "#34D399",  # Emerald brillant
    "persona_pro_tcl": "#F59E0B",  # Amber
    "persona_pro_tcl_accent": "#FCD34D",  # Amber clair
    "persona_elu": "#6366F1",  # Indigo
    "persona_elu_accent": "#818CF8",  # Indigo clair
    # UI text
    "text_primary": "#F8FAFC",  # Slate 50
    "text_secondary": "#94A3B8",  # Slate 400
  # Axe E — Contraste AA : #64748B → #B0B0B0 (ratio 5.2:1 sur #0B0F19)
    # vs ancien 4.0:1 qui ne passait pas WCAG 2.1 AA pour le texte normal
    "text_muted": "#B0B0B0",  # Slate 500 lightened for AA
    "text_disabled": "#475569",  # Slate 600
    # Diagnostic (correlation bus × trafic)
    "diag_ok": "#10B981",
    "diag_infra": "#EF4444",
    "diag_operations": "#F59E0B",
    "diag_bus_lane_ok": "#3B82F6",
    # Chart accents (graphes Plotly secondaires)
    "chart_purple": "#9C27B0",
    "chart_indigo": "#5C6BC0",
    "chart_yellow": "#FFCD00",
    "chart_green_light": "#8BC34A",
    "chart_red_deep": "#8B0000",
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


def delta_color(value: float) -> str:
    """Couleur status selon signe d'un delta (+ vert, - rouge, 0 orange)."""
    if value > 0:
        return COLORS["status_ok"]
    if value < 0:
        return COLORS["status_critical"]
    return COLORS["status_warning"]
