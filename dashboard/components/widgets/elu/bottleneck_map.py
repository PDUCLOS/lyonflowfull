"""Widget — Carte Folium des 10 bottlenecks.

Sprint 8 — Bottlenecks chargés via data_loader.cached_bottlenecks_top().

Sprint P2.2 (2026-06-14) — AUDIT_INTEGRATION_LIVE.md § 2.3.5.
Géocodage dynamique : on utilise lat/lon du dict retourné par
``load_bottlenecks_top`` (sprint P2.2 — requête sur
``gold.infrastructure_bottlenecks``). Le fallback hardcodé reste
uniquement pour le mode démo (force_mock=True), pas en prod.
"""

from __future__ import annotations

import logging

import streamlit as st

from dashboard.components.data_cache import cached_bottlenecks_top

logger = logging.getLogger(__name__)


# Coordonnées de fallback (mode démo uniquement) — cf. docstring P2.2
_FALLBACK_COORDS = {
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


def render_bottleneck_map(height: int = 500) -> None:
    """Affiche la carte Folium des 10 bottlenecks.

    Sprint P2.2 : géocodage dynamique via lat/lon retournés par
    ``load_bottlenecks_top`` (depuis ``gold.infrastructure_bottlenecks``).
    Le dict hardcodé ``_FALLBACK_COORDS`` n'est utilisé qu'en mode démo
    (DB indispo + ``LYONFLOW_DEMO_MODE=1``).

    Args:
        height: hauteur de la carte.
    """
    bottlenecks = cached_bottlenecks_top(force_mock=False)
    if not bottlenecks:
        st.info("Aucun bottleneck disponible.")
        return

    # Sprint P2.2 : compter ceux qui ont lat/lon (DB) vs fallback (démo)
    n_with_coords = sum(
        1 for b in bottlenecks
        if b.get("lat") is not None and b.get("lon") is not None
    )
    n_with_fallback = sum(
        1 for b in bottlenecks
        if b.get("lat") is None and b.get("zone") in _FALLBACK_COORDS
    )
    n_skipped = len(bottlenecks) - n_with_coords - n_with_fallback
    if n_skipped > 0:
        logger.warning(
            "bottleneck_map: %d/%d bottlenecks sans coords (ni DB ni fallback). "
            "Vérifier que la migration 0006 est appliquée.",
            n_skipped, len(bottlenecks),
        )

    try:
        import folium
        from streamlit_folium import st_folium

        # Centre Lyon
        m = folium.Map(location=[45.76, 4.84], zoom_start=12, tiles="CartoDB positron")

        for b in bottlenecks:
            zone = b.get("zone", "—")
            # Sprint P2.2 : priorité aux coords DB, fallback démo
            lat = b.get("lat")
            lon = b.get("lon")
            if lat is None or lon is None:
                fallback = _FALLBACK_COORDS.get(zone)
                if fallback is None:
                    # Pas de coords dispo — on saute ce bottleneck
                    # (avec un log warning ci-dessus).
                    continue
                lat, lon = fallback
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
