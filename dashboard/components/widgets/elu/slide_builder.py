"""Widget — Builder de slides (1 slide = 1 dict)."""

from __future__ import annotations

import streamlit as st


def render_slide_builder() -> list:
    """Affiche un builder de slides (multi-select de sections).

    Returns:
        Liste de dicts {'order': int, 'type': str, 'content': dict}.
    """
    st.markdown("##### 🎬 Slides à inclure")

    slide_types = st.multiselect(
        "Sections",
        [
            "🟢 Slide de couverture",
            "📊 Slide KPIs",
            "🎯 Slide Bottlenecks",
            "📈 Slide Évolution 12 mois",
            "📰 Slide À annoncer",
            "📋 Slide Méthodologie",
            "📞 Slide Contact",
        ],
        default=[
            "🟢 Slide de couverture",
            "📊 Slide KPIs",
            "🎯 Slide Bottlenecks",
            "📰 Slide À annoncer",
        ],
        key="slide_builder_types",
    )

    slides = []
    for i, t in enumerate(slide_types, 1):
        slides.append({
            "order": i,
            "type": t,
            "content": {},  # Sera rempli par le générateur PDF
        })

    return slides
