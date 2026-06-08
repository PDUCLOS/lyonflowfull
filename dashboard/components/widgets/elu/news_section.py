"""Widget — Bloc 'À annoncer' (suggestions de communication politique)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS


def render_news_section() -> None:
    """Affiche le bloc 'À annoncer' avec suggestions pour le conseil municipal."""
    st.markdown("##### 📰 À annoncer au prochain conseil municipal")

    announcements = [
        {
            "type": "Annonce majeure",
            "icon": "🎉",
            "text": (
                "**« Lyon devient la 1ère métropole française à diagnostiquer "
                "ses bottlenecks de mobilité en croisant retards bus et trafic "
                "routier via open data et intelligence artificielle. »**"
            ),
            "color": COLORS["persona_elu"],
        },
        {
            "type": "Résultat chiffré",
            "icon": "📊",
            "text": (
                "**« +1.4 points de part modale TC en 12 mois** — soit l'équivalent "
                "de 14 000 véhicules particuliers retirés du trafic quotidien. »"
            ),
            "color": COLORS["status_ok"],
        },
        {
            "type": "Engagement",
            "icon": "🤝",
            "text": (
                "**« Réduction de 22% du nombre de bottlenecks actifs** — "
                "résultat des 5 aménagements prioritaires lancés en 2023-2024. »"
            ),
            "color": COLORS["status_warning"],
        },
        {
            "type": "Perspective",
            "icon": "🔮",
            "text": (
                "**« 5 décisions d'infrastructure à arbitrer ce trimestre** "
                "représentent un ROI moyen de 14 mois sur 24 M€ investis. »"
            ),
            "color": COLORS["chart_purple"],
        },
    ]

    for ann in announcements:
        st.markdown(
            f"""
            <div style="background:var(--bg-card);border-left:4px solid {ann["color"]};
                        border-radius:8px;padding:0.8rem 1rem;margin:0.5rem 0;">
                <div style="font-size:0.7rem;opacity:0.6;text-transform:uppercase;
                            letter-spacing:0.5px;">{ann["type"]} {ann["icon"]}</div>
                <div style="margin-top:0.3rem;font-size:0.95rem;line-height:1.5;">
                    {ann["text"]}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
