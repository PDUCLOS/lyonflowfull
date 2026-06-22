"""Sparkline Plotly minimaliste pour tendances 24h (Sprint 21 P4.3).

Utilisé par le widget Élu `network_health_gauge` pour afficher un mini-graphique
de l'évolution du score de santé réseau sur les dernières 24h (96 snapshots à
*/15 min).

Caractéristiques :
- Plotly (cohérent avec le reste du dashboard)
- Sans axes, sans légende, sans interactivité (juste une trend line)
- Couleur adaptative (vert si hausse, rouge si baisse)
- Hauteur fixe 80px pour intégration compacte
"""
from __future__ import annotations

import plotly.graph_objects as go

from dashboard.components.plotly_theme import apply_lyf_theme


def render_sparkline(
    values: list[float],
    timestamps: list | None = None,
    height: int = 80,
    line_color: str | None = None,
) -> go.Figure:
    """Génère une sparkline Plotly minimaliste.

    Args:
        values: liste de valeurs numériques (ex: scores 0-100 sur 24h).
        timestamps: liste optionnelle de timestamps pour l'axe x (sinon indices).
        height: hauteur en pixels (défaut 80).
        line_color: couleur de la ligne (défaut : vert si hausse, rouge si baisse).

    Returns:
        Figure Plotly prête à être passée à st.plotly_chart().
    """
    if not values:
        # Fallback : graphe vide avec message
        fig = go.Figure()
        fig.add_annotation(
            text="Historique bientôt disponible",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font={"size": 12, "color": "#94A3B8"},
        )
        fig.update_layout(height=height, showlegend=False)
        apply_lyf_theme(fig)
        return fig

    # Auto-color : vert si trend haussière, rouge si baissière
    if line_color is None:
        if values[-1] > values[0]:
            line_color = "#10B981"  # vert (hausse)
        elif values[-1] < values[0]:
            line_color = "#EF4444"  # rouge (baisse)
        else:
            line_color = "#94A3B8"  # gris (stable)

    # Conversion hex → rgba semi-transparent pour le fill
    def hex_to_rgba(hex_color: str, alpha: float = 0.1) -> str:
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    fill_color = hex_to_rgba(line_color, 0.1) if line_color.startswith("#") else line_color

    fig = go.Figure()

    # Aire sous la courbe (effet "sparkline")
    fig.add_trace(go.Scatter(
        x=timestamps or list(range(len(values))),
        y=values,
        mode="lines",
        line=dict(color=line_color, width=2, shape="spline", smoothing=0.5),
        fill="tozeroy",
        fillcolor=fill_color,
        showlegend=False,
        hovertemplate="%{y:.1f}<extra></extra>",
    ))

    # Configuration sparkline : pas d'axes, pas de grille
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=5, b=5),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    apply_lyf_theme(fig)
    return fig
