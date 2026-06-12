"""Widget — Carte lieux × Vélov proches (Sprint VPS-6, 2026-06-11).

Affiche sur une carte Folium :
* 21 lieux emblématiques (markers bleus avec icône par type)
* Pour chaque lieu : la borne Vélov la plus proche (marker vélo)
* Lignes pointillées reliant chaque lieu à sa borne Vélov (gradient de
  couleur selon distance : vert < 100m, orange < 300m, rouge > 300m)
* Popups : nom du lieu, station Vélov + vélos/docks dispo, distance à pied

Source 100% pipeline (vue referentiel.v_lieux_velov_proches + silver.velov_clean).
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import _is_demo_mode
from src.data.exceptions import DashboardDataError

# Icônes par type de lieu
_TYPE_ICON = {
    "gare": "🚉",
    "place": "📍",
    "monument": "🏛",
    "quartier": "🏘",
    "parc": "🌳",
    "universite": "🎓",
    "banlieue": "🏙",
}


def _distance_color(distance_m: float) -> str:
    """Couleur du segment lieu→Vélov selon la distance.

    < 100m : vert (très proche, accessible à pied en 1 min)
    < 300m : orange (5 min à pied, OK)
    >= 300m : rouge (loin, considérer une autre station)
    """
    if distance_m < 100:
        return "#4CAF50"  # vert
    if distance_m < 300:
        return "#FF9800"  # orange
    return "#F44336"      # rouge


def render_lieux_velov_map(
    lieux_with_velov: list[dict] | None = None,
    height: int = 600,
) -> None:
    """Affiche la carte Folium reliant chaque lieu à sa borne Vélov proche.

    Args:
        lieux_with_velov: liste pré-calculée. Si None, charge via
            ``db_query.get_lieux_with_velov()``.
        height: hauteur de la carte en pixels.
    """
    if _is_demo_mode():
        st.info("🟡 Mode démo — carte lieux × Vélov indisponible. "
                "Connecter la DB pour voir le rendu réel.")
        return

    if lieux_with_velov is None:
        try:
            from src.data.db_query import get_lieux_with_velov
            lieux_with_velov = get_lieux_with_velov(k=1)
        except DashboardDataError as e:
            st.error(f"⚠️ {e}")
            return

    if not lieux_with_velov:
        st.info("Aucun lieu avec borne Vélov proche à afficher.")
        return

    try:
        import folium
    except ImportError:
        st.warning("⚠️ folium non disponible — affichage liste uniquement")
        _render_lieux_velov_list(lieux_with_velov)
        return

    # Centre sur la moyenne des lieux
    center_lat = sum(lieu["lieu_lat"] for lieu in lieux_with_velov) / len(lieux_with_velov)
    center_lon = sum(lieu["lieu_lon"] for lieu in lieux_with_velov) / len(lieux_with_velov)

    m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="CartoDB positron")

    n_paires = 0
    n_dist_warn = 0  # bornes à > 300m

    for lieu in lieux_with_velov:
        icon = _TYPE_ICON.get(lieu["lieu_type"], "📍")
        st.markdown(f"**{icon} {lieu['lieu_name']}** ({lieu['lieu_type']})")
        for b in lieu.get("bornes", []):
            st.caption(
                f"  🚲 {b['velov_name']} — {int(b['distance_m'])}m — "
                f"{b['num_bikes_available']} vélos, {b['num_docks_available']} docks"
            )


def _lieu_popup_html(lieu: dict) -> str:
    icon = _TYPE_ICON.get(lieu["lieu_type"], "📍")
    bornes_html = ""
    for b in lieu.get("bornes", []):
        color = _distance_color(b["distance_m"])
        bornes_html += (
            f"<div style='margin-top:0.3rem;padding-left:0.5rem;"
            f"border-left:3px solid {color};'>"
            f"🚲 <b>{b['velov_name']}</b><br/>"
            f"📏 {int(b['distance_m'])}m · "
            f"🚴 {b['num_bikes_available']} vélos · "
            f"🅿️ {b['num_docks_available']} docks"
            f"</div>"
        )
    return f"""
    <div style='font-family:sans-serif;'>
        <div style='font-size:1rem;font-weight:600;'>
            {icon} {lieu['lieu_name']}
        </div>
        <div style='font-size:0.75rem;opacity:0.7;
                    text-transform:uppercase;letter-spacing:0.5px;'>
            {lieu['lieu_type']}
        </div>
        {bornes_html}
    </div>
    """


def _borne_popup_html(lieu: dict, b: dict) -> str:
    color = _distance_color(b["distance_m"])
    walk_min = round(b["distance_m"] / 1000.0 / 4.5 * 60.0, 1)  # 4.5 km/h
    return f"""
    <div style='font-family:sans-serif;'>
        <div style='font-size:0.85rem;font-weight:600;'>
            🚲 {b['velov_name']}
        </div>
        <div style='font-size:0.7rem;opacity:0.7;margin-top:0.2rem;'>
            Relié à <b>{lieu['lieu_name']}</b>
        </div>
        <div style='font-size:0.7rem;opacity:0.7;margin-top:0.2rem;'>
            Relié à <b>{lieu['lieu_name']}</b>
        </div>
        <div style='margin-top:0.4rem;font-size:0.85rem;'>
            📏 <b>{int(b['distance_m'])}m</b> · 🚶 {walk_min} min à pied
        </div>
        <div style='margin-top:0.4rem;'>
            🚴 {b['num_bikes_available']} vélos dispo · 🅿️ {b['num_docks_available']} docks
        </div>
    </div>
    """
