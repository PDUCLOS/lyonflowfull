"""Widget — Affichage d'un itinéraire avec carte et segments.

Affiche :
- Carte Folium avec polyline colorée par vitesse (vert→rouge)
- Liste des segments avec longueur / vitesse / durée
- Comparaison temps actuel vs temps prédit (H+30min par défaut)
- Bouton "recommencer"

Sprint VPS-6 (2026-06-11) — démoctisé : résolution d'adresse via
``referentiel.lieux_lyon`` (PostgreSQL) au lieu du mock ``lyon_addresses``.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS
from src.data.data_loader import (
    _is_demo_mode,
    load_lyon_addresses,
)
from src.data.exceptions import DashboardDataError
from src.routing import Itinerary, compute_itinerary


def _resolve_address(text: str) -> tuple[float, float] | None:
    """Résout une adresse texte → (lon, lat) via la DB (referentiel.lieux_lyon).

    Sprint 8 (2026-06-12) — viré le fallback mock lyon_addresses.
    La DB est l'unique source. Si DB indispo, DashboardDataError.
    """
    from src.data.db_query import _is_db_available, execute_query

    if not _is_db_available():
        raise DashboardDataError(source="referentiel.lieux_lyon", detail="DB indisponible")

    if not text:
        return None
    # Strip emoji préfixe (search_bar préfixe avec emoji + espace)
    cleaned = text.strip()
    if cleaned and ord(cleaned[0]) > 0x2700:
        sp = cleaned.find(" ")
        if sp > 0 and sp <= 3:
            cleaned = cleaned[sp + 1:].strip()
    text_lower = cleaned.lower().strip()
    if not text_lower:
        return None
    rows = execute_query(
        """
        SELECT lon, lat FROM referentiel.lieux_lyon
        WHERE is_active = TRUE
          AND LOWER(name) LIKE %s
        ORDER BY LENGTH(name) ASC
        LIMIT 1
        """,
        (f"%{text_lower}%",),
    )
    if not rows:
        return None
    return (float(rows[0]["lon"]), float(rows[0]["lat"]))


def _sample_addresses(n: int = 5) -> list[str]:
    """Renvoie N adresses pour les messages d'erreur."""
    try:
        return load_lyon_addresses()[:n]
    except Exception:
        return []


def render_itinerary_result(
    origin: str,
    destination: str,
    horizon_minutes: int = 60,  # Sprint 8+ : focus H+1h (0 = maintenant)
) -> None:
    """Affiche l'itinéraire entre 2 adresses.

    Args:
        origin: adresse d'origine (texte)
        destination: adresse de destination (texte)
        horizon_minutes: 60 = H+1h (défaut Sprint 8+), 0 = maintenant
    """
    try:
        origin_coords = _resolve_address(origin)
        dest_coords = _resolve_address(destination)
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")
        return

    if not origin_coords:
        sample = ", ".join(_sample_addresses(5))
        st.error(f"❌ Adresse d'origine non reconnue : '{origin}'. Essayez : {sample}...")
        return
    if not dest_coords:
        st.error(f"❌ Adresse de destination non reconnue : '{destination}'.")
        return

    # Calcul itinéraire
    with st.spinner("🔍 Calcul itinéraire en cours..."):
        itinerary = compute_itinerary(
            origin_lon=origin_coords[0],
            origin_lat=origin_coords[1],
            destination_lon=dest_coords[0],
            destination_lat=dest_coords[1],
            horizon_minutes=horizon_minutes,
        )

    if not itinerary or not itinerary.segments:
        st.warning("⚠️ Aucun itinéraire trouvé. Le graphe routier n'est peut-être pas chargé.")
        return

    # Comparaison si horizon > 0
    comparison = None
    if horizon_minutes > 0:
        with st.spinner(f"🔮 Comparaison avec H+{horizon_minutes}min..."):
            current_itin = compute_itinerary(
                origin_lon=origin_coords[0],
                origin_lat=origin_coords[1],
                destination_lon=dest_coords[0],
                destination_lat=dest_coords[1],
                horizon_minutes=0,
            )
            if current_itin:
                comparison = {
                    "current_duration_s": current_itin.total_duration_s,
                    "current_avg_speed": current_itin.average_speed_kmh,
                    "delta_s": itinerary.total_duration_s - current_itin.total_duration_s,
                }

    # Affichage
    _render_summary(itinerary, comparison, horizon_minutes)
    _render_map(itinerary, origin_coords, dest_coords)
    _render_segments(itinerary)


def _render_summary(
    itinerary: Itinerary,
    comparison: dict | None,
    horizon_minutes: int,
) -> None:
    """Affiche le résumé (durée, distance, vitesse moyenne, comparaison)."""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "🕐 Durée totale",
            f"{itinerary.total_duration_min:.1f} min",
            delta=(
                f"+{comparison['delta_s'] / 60:.1f} min vs maintenant"
                if comparison and comparison["delta_s"] > 0
                else f"{comparison['delta_s'] / 60:.1f} min vs maintenant"
                if comparison
                else None
            ),
            delta_color="inverse" if comparison and comparison["delta_s"] > 0 else "normal",
        )
    with col2:
        st.metric("📏 Distance", f"{itinerary.total_length_m / 1000:.2f} km")
    with col3:
        st.metric("🚗 Vitesse moyenne", f"{itinerary.average_speed_kmh:.1f} km/h")
    with col4:
        st.metric("🎯 Confiance", f"{int(itinerary.confidence * 100)}%")

    if comparison:
        st.caption(
            f"📊 Comparaison : maintenant = {comparison['current_duration_s'] / 60:.1f} min · "
            f"H+{horizon_minutes}min = {itinerary.total_duration_min:.1f} min"
        )


def _render_map(
    itinerary: Itinerary,
    origin_coords: tuple[float, float],
    dest_coords: tuple[float, float],
) -> None:
    """Affiche la carte Folium avec polyline par segment."""
    try:
        import folium
        from streamlit_folium import st_folium

        # Centre sur le milieu de l'itinéraire
        all_lons = (
            [origin_coords[0], dest_coords[0]]
            + [s.start_lon for s in itinerary.segments]
            + [s.end_lon for s in itinerary.segments]
        )
        all_lats = (
            [origin_coords[1], dest_coords[1]]
            + [s.start_lat for s in itinerary.segments]
            + [s.end_lat for s in itinerary.segments]
        )
        center_lat = sum(all_lats) / len(all_lats)
        center_lon = sum(all_lons) / len(all_lons)

        m = folium.Map(location=[center_lat, center_lon], zoom_start=13, tiles="CartoDB positron")

        # Markers
        folium.Marker(
            origin_coords,
            popup=f"🟢 {itinerary.origin_node}",
            icon=folium.Icon(color="green", icon="play"),
        ).add_to(m)
        folium.Marker(
            dest_coords,
            popup=f"🔴 {itinerary.destination_node}",
            icon=folium.Icon(color="red", icon="stop"),
        ).add_to(m)

        # Polyline par segment (couleur selon vitesse)
        for seg in itinerary.segments:
            color = _speed_to_color(seg.speed_kmh)
            folium.PolyLine(
                locations=[
                    [seg.start_lat, seg.start_lon],
                    [seg.end_lat, seg.end_lon],
                ],
                color=color,
                weight=5,
                opacity=0.8,
                popup=(
                    f"<b>{seg.channel_id}</b><br>"
                    f"📏 {seg.length_m:.0f} m<br>"
                    f"🚗 {seg.speed_kmh:.0f} km/h<br>"
                    f"🕐 {seg.duration_s / 60:.1f} min"
                ),
            ).add_to(m)

        st_folium(m, width=None, height=400, returned_objects=[])

    except ImportError:
        st.warning("⚠️ folium non disponible — affichage liste uniquement")


def _render_segments(itinerary: Itinerary) -> None:
    """Affiche la liste détaillée des segments."""
    with st.expander(f"🛣️ Détail des {len(itinerary.segments)} segments", expanded=False):
        for i, seg in enumerate(itinerary.segments, 1):
            color = _speed_to_color(seg.speed_kmh)
            st.markdown(
                f"""
                <div style="display:flex;align-items:center;gap:0.8rem;
                            padding:0.5rem;background:var(--bg-card);border-radius:4px;
                            margin:0.3rem 0;border-left:4px solid {color};">
                    <div style="background:{color};color:white;width:24px;height:24px;
                                border-radius:50%;display:flex;align-items:center;
                                justify-content:center;font-weight:600;font-size:0.85rem;
                                flex-shrink:0;">
                        {i}
                    </div>
                    <div style="flex:1;">
                        <div style="font-weight:600;font-size:0.9rem;">{seg.channel_id}</div>
                        <div style="font-size:0.8rem;opacity:0.7;">
                            📏 {seg.length_m:.0f} m · 🚗 {seg.speed_kmh:.0f} km/h · 🕐 {seg.duration_s / 60:.1f} min
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _speed_to_color(speed_kmh: float) -> str:
    """Convertit une vitesse en couleur (vert=fluide → rouge=bloqué)."""
    if speed_kmh >= 40:
        return COLORS["status_ok"]  # vert
    if speed_kmh >= 25:
        return COLORS["chart_green_light"]  # vert clair
    if speed_kmh >= 15:
        return COLORS["status_warning"]  # orange
    if speed_kmh >= 8:
        return COLORS["status_critical"]  # rouge
    return COLORS["chart_red_deep"]  # rouge foncé
