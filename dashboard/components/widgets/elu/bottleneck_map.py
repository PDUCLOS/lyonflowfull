"""Widget — Carte Folium des 10 bottlenecks.

 Bottlenecks chargés via data_loader.cached_bottlenecks_top().

 (2026-06-25) — Fix Bug 2 du SPEC_FIX_ELU2_BOTTLENECKS.md :
* Suppression du dict ``coords`` hardcodé (10 noms de rues → tout était
  skippé car ``zone`` valait ``"L66 ; 20h"``).
* Utilisation des **coordonnées GPS réelles** (lat/lon) retournées par
  ``load_bottlenecks_top`` depuis ``gold.mv_bus_traffic_spatial``.
* **Couleur par diagnostic** (Bug 4) au lieu du ROI synthétique (Bug 1) :
  - rouge = infra, orange = operations, vert = bus_lane_ok, gris = ok.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.a11y import st_folium_with_alt
from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_bottlenecks_top
from dashboard.components.loading_state import loading_wrapper

# Couleur Folium par diagnostic (alignée avec la palette COLORS du projet)
_DIAGNOSIS_FOLIUM_COLOR = {
    "infra": "red",
    "operations": "orange",
    "bus_lane_ok": "green",
    "ok": "gray",
}


def render_bottleneck_map(height: int = 500) -> None:
    with loading_wrapper("Chargement Bottleneck map…", "⏳"):
        """Affiche la carte Folium des 10 bottlenecks.

    Args:
        height: hauteur de la carte.
    """
    bottlenecks = cached_bottlenecks_top()
    if not bottlenecks:
        st.info("Aucun bottleneck disponible.")
        return

    try:
        import folium

        # Centre Lyon
        m = folium.Map(location=[45.76, 4.84], zoom_start=12, tiles="CartoDB positron")

        n_rendered = 0
        n_skipped_no_coords = 0
        for b in bottlenecks:
            zone = b.get("zone", "—")
            lat = b.get("lat")
            lon = b.get("lon")

            # Bug 2 fix : on lit lat/lon du dict (réelles depuis
            # gold.mv_bus_traffic_spatial), plus de dict coords hardcodé.
            if lat is None or lon is None:
                n_skipped_no_coords += 1
                continue

            # Bug 4 fix : couleur par diagnostic, plus par ROI synthétique
            diagnosis = b.get("diagnosis", "ok")
            color = _DIAGNOSIS_FOLIUM_COLOR.get(diagnosis, "gray")

            roi = b.get("roi_mois", 999)
            lignes = ", ".join(b.get("lines_impacted", [])) or "—"

            folium.CircleMarker(
                location=[lat, lon],
                radius=10 + b.get("rank", 1) * 1.5,
                color=color,
                fill=True,
                fill_opacity=0.6,
                popup=folium.Popup(
                    f"<b>#{b.get('rank')} {zone}</b><br>"
                    f"Diagnostic : <b>{diagnosis}</b><br>"
                    f"Lignes : {lignes}<br>"
                    f"Voyageurs/j (estimés) : {b.get('voyageurs_jour', 0):,}<br>"
                    f"Gain : {b.get('gain_min', 0)} min · Coût : {b.get('cout_M_euros', 0)} M€<br>"
                    f"ROI : {int(roi)} mois<br>"
                    f"<small>lat/lon : {lat:.4f}, {lon:.4f}</small>",
                    max_width=320,
                ),
                tooltip=f"#{b.get('rank')} {zone} ({diagnosis})",
            ).add_to(m)
            n_rendered += 1

        if n_rendered == 0:
            st.warning(
                f"⚠️ {len(bottlenecks)} bottleneck(s) trouvé(s) mais aucun "
                f"n'a de coordonnées GPS exploitables. Vérifier la migration "
                f"018 (gold.mv_bus_traffic_spatial)."
            )

        # Légende diagnostic (Bug 4)
        st.caption("🟥 Infra (travaux) · 🟧 Opérationnel (réglage) · 🟩 Voie bus OK · ⚪ Sous surveillance")

        st_folium_with_alt(m, width=None, height=height, returned_objects=[])

    except ImportError:
        # Fallback : tableau simple
        st.warning("⚠️ Folium non disponible — affichage liste")
        for b in bottlenecks:
            st.markdown(
                f"**#{b.get('rank')} {b.get('zone')}** "
                f"({b.get('diagnosis', '—')}) — "
                f"{b.get('voyageurs_jour', 0):,} voy/j, "
                f"gain {b.get('gain_min', 0)} min, "
                f"coût {b.get('cout_M_euros', 0)} M€, "
                f"ROI {int(b.get('roi_mois', 0))} mois"
            )

    # Référence cohérente (utilisée par d'autres widgets du persona).
    _ = COLORS
