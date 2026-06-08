"""Widget — Carte Folium des 10 bottlenecks.

Sprint 8 — Bottlenecks chargés via data_loader.cached_bottlenecks_top().
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_bottlenecks_top


def render_bottleneck_map(height: int = 500) -> None:
    """Affiche la carte Folium des 10 bottlenecks.

    Args:
        height: hauteur de la carte.
    """
    # Coordonnées approximatives des bottlenecks
    coords = {
        "Rue Garibaldi": (45.7575, 4.8461),
        "Cours Lafayette": (45.7542, 4.8411),
        "Carrefour Part-Dieu": (45.7607, 4.8589),
        "Quai Claude Bernard": (45.7513, 4.8360),
        "Av. Berthelot": (45.7450, 4.8501),
        "Cours Vitton": (45.7721, 4.8553),
        "Pont Lafayette": (45.7651, 4.8369),
        "Place Bellecour": (45.7575, 4.8324),
        "Av. Jean Jaurès": (45.7690, 4.8340),
        "Gare de Vaise": (45.7798, 4.8058),
    }

    bottlenecks = cached_bottlenecks_top(force_mock=False)
    if not bottlenecks:
        st.info("Aucun bottleneck disponible.")
        return

    try:
        import folium
        from streamlit_folium import st_folium

        # Centre Lyon
        m = folium.Map(location=[45.76, 4.84], zoom_start=12, tiles="CartoDB positron")

        for b in bottlenecks:
            zone = b.get("zone", "—")
            if zone not in coords:
                continue
            lat, lon = coords[zone]
            roi = b.get("roi_mois", 999)
            color = "green" if roi <= 12 else "orange" if roi <= 24 else "red"

            folium.CircleMarker(
                location=[lat, lon],
                radius=10 + b.get("rank", 1) * 1.5,
                color=color,
                fill=True,
                fill_opacity=0.6,
                popup=folium.Popup(
                    f"<b>#{b.get('rank')} {zone}</b><br>"
                    f"Lignes: {', '.join(b.get('lines_impacted', []))}<br>"
                    f"Voyageurs/j: {b.get('voyageurs_jour', 0):,}<br>"
                    f"Gain: {b.get('gain_min', 0)} min · Coût: {b.get('cout_M_euros', 0)} M€<br>"
                    f"ROI: {int(roi)} mois",
                    max_width=300,
                ),
                tooltip=f"#{b.get('rank')} {zone}",
            ).add_to(m)

        st_folium(m, width=None, height=height, returned_objects=[])

    except ImportError:
        # Fallback : tableau simple
        st.warning("⚠️ Folium non disponible — affichage liste")
        for b in bottlenecks:
            st.markdown(
                f"**#{b.get('rank')} {b.get('zone')}** "
                f"— {b.get('voyageurs_jour', 0):,} voy/j, "
                f"gain {b.get('gain_min', 0)} min, "
                f"coût {b.get('cout_M_euros', 0)} M€, "
                f"ROI {int(b.get('roi_mois', 0))} mois"
            )
