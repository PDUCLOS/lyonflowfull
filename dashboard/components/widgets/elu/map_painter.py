"""Widget — Map painter (placeholder pour component React custom ).

En sélection manuelle d'une zone sur la carte.
En component React custom (deck.gl + MapboxDraw) pour dessiner
librement le tracé d'un aménagement.

 Bottlenecks via data_loader.cached_bottlenecks_top() (fallback).
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.a11y import st_folium_with_alt
from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_bottlenecks_top
from dashboard.components.loading_state import loading_wrapper


def render_map_painter(height: int = 400) -> dict:
    with loading_wrapper("Chargement Map painter…", "⏳"):
        """Affiche un map painter (sélection manuelle pour ).

    Args:
        height: hauteur de la carte.

    Returns:
        Dict avec 'selected_zone' (str ou None).
    """
    st.markdown("##### Simulateur d'aménagement")

    st.caption("sélection manuelle. component React custom deck.gl + MapboxDraw pour dessiner librement.")

    try:
        import folium

        # Carte avec marqueurs des bottlenecks existants
        m = folium.Map(location=[45.76, 4.84], zoom_start=12, tiles="CartoDB positron")

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

        for zone, (lat, lon) in coords.items():
            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color=COLORS["persona_elu"],
                fill=True,
                fill_opacity=0.5,
                tooltip=zone,
            ).add_to(m)

        result = st_folium_with_alt(m, width=None, height=height, returned_objects=["last_clicked"])

        clicked = result.get("last_clicked") if result else None
        selected_zone = None
        if clicked:
            lat, lon = clicked.get("lat"), clicked.get("lng")
            # Trouver la zone la plus proche
            min_dist = float("inf")
            for zone, (zlat, zlon) in coords.items():
                d = (lat - zlat) ** 2 + (lon - zlon) ** 2
                if d < min_dist:
                    min_dist = d
                    selected_zone = zone
            if min_dist < 0.001:  # ~30m
                st.success(f"Zone sélectionnée : **{selected_zone}**")
            else:
                selected_zone = None
                st.info("Cliquez sur un point proche d'un bottleneck connu")

        return {"selected_zone": selected_zone}

    except ImportError:
        st.warning("Folium non disponible — fallback selectbox")
        bottlenecks = cached_bottlenecks_top()
        zones = [b.get("zone", "—") for b in bottlenecks]
        if not zones:
            return {"selected_zone": None}
        selected = st.selectbox("Zone", zones, key="map_painter_fallback")
        return {"selected_zone": selected}
