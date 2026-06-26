"""Thème Plotly unifié — cohérent avec le theme.py CSS du dashboard.

 Axe B (2026-06-22) — Remplace ``plotly_dark`` (inadapté car le
dashboard n'est pas en dark mode Plotly natif) et les templates ad-hoc par
un template unique aligné sur les couleurs COLORS du thème CSS.

Usage dans chaque widget Plotly :

    from dashboard.components.plotly_theme import LYF_TEMPLATE, apply_lyf_theme
    fig = go.Figure(...)
    apply_lyf_theme(fig)
    # ou directement :
    fig.update_layout(template=LYF_TEMPLATE)

Cf. docs/SPEC_SPRINT_20_UX.md §3.
"""

from __future__ import annotations

import plotly.graph_objects as go

from dashboard.components.colors import COLORS

# Template Plotly unifié LyonFlow
LYF_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        # Fond transparent pour s'intégrer au glassmorphism des cards Streamlit
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        # Police et couleur de texte primaire
        font={
            "family": "Inter, sans-serif",
            "color": COLORS.get("text_primary", "#F8FAFC"),
            "size": 13,
        },
        # Titre aligné à gauche
        title={
            "font": {"size": 16, "color": COLORS.get("text_primary", "#F8FAFC")},
            "x": 0.0,
            "xanchor": "left",
        },
        # Colorway (ordre utilisé pour les séries multiples)
        colorway=[
            COLORS.get("chart_purple", "#9C27B0"),
            COLORS.get("chart_indigo", "#5C6BC0"),
            COLORS.get("chart_yellow", "#FFCD00"),
            COLORS.get("chart_green_light", "#8BC34A"),
            COLORS.get("status_info", "#3B82F6"),
            COLORS.get("status_ok", "#10B981"),
        ],
        # Axes avec grille subtile adaptée au dark mode
        xaxis={
            "gridcolor": "rgba(148, 163, 184, 0.12)",  # border_card alpha
            "zerolinecolor": "rgba(148, 163, 184, 0.20)",
            "color": COLORS.get("text_secondary", "#94A3B8"),
        },
        yaxis={
            "gridcolor": "rgba(148, 163, 184, 0.12)",
            "zerolinecolor": "rgba(148, 163, 184, 0.20)",
            "color": COLORS.get("text_secondary", "#94A3B8"),
        },
        # Tooltip dark mode cohérent
        hoverlabel={
            "bgcolor": COLORS.get("bg_card_deep", "#0F172A"),
            "font_color": COLORS.get("text_primary", "#F8FAFC"),
            "bordercolor": COLORS.get("border_card", "rgba(148, 163, 184, 0.12)"),
        },
        # Légende transparente
        legend={
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"color": COLORS.get("text_secondary", "#94A3B8")},
        },
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
    ),
)


def apply_lyf_theme(fig: go.Figure) -> go.Figure:
    """Applique le thème LyonFlow à un Figure existant (in-place + return).

    Args:
        fig: Figure Plotly à thémiser.

    Returns:
        Le même Figure (modifié in-place), pour permettre le chaînage :
        ``fig = apply_lyf_theme(go.Figure(...))``.
    """
    fig.update_layout(template=LYF_TEMPLATE)
    return fig
