"""Widget — Graphique avant/après."""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS


def render_before_after_chart(base_value: float, new_value: float, label: str = "OTP") -> None:
    """Affiche un graphique comparatif avant/après.

    Args:
        base_value: valeur de référence.
        new_value: nouvelle valeur projetée.
        label: nom de la métrique.
    """
    try:
        import plotly.graph_objects as go

        fig = go.Figure()

        # Barres
        fig.add_trace(
            go.Bar(
                x=["Avant", "Après"],
                y=[base_value, new_value],
                marker_color=[
                    COLORS["status_critical"] if new_value < base_value else COLORS["status_warning"],
                    COLORS["status_ok"] if new_value > base_value else COLORS["status_warning"],
                ],
                text=[f"{base_value:.1f}", f"{new_value:.1f}"],
                textposition="auto",
            )
        )

        # Flèche de delta
        delta = new_value - base_value
        arrow_color = COLORS["status_ok"] if delta > 0 else COLORS["status_critical"]
        fig.add_annotation(
            x=1,
            y=max(base_value, new_value) * 1.05,
            text=f"{'▲' if delta > 0 else '▼'} {abs(delta):.1f}pts",
            showarrow=False,
            font=dict(size=18, color=arrow_color),
        )

        fig.update_layout(
            title=f"{label} — Avant / Après",
            yaxis_title=label,
            height=300,
            template="plotly_dark",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    except ImportError:
        # Fallback markdown
        delta = new_value - base_value
        st.markdown(f"**Avant :** {base_value:.1f}\n\n**Après :** {new_value:.1f} ({delta:+.1f})")
