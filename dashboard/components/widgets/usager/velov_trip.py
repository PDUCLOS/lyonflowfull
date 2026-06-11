"""Widget — Trajet Vélov + marche avec carte.

Affiche (Sprint VPS-6, 2026-06-11) :
- Carte Folium avec 2 polylines colorées (marche = pointillé gris, Vélov = bleu)
- Markers : origine (vert), station Vélov départ (bleu), station Vélov arrivée (bleu),
  destination (rouge)
- Popups : nom station, vélos dispo, docks dispo, distance à pied
- Bandeau de résumé : 3 segments avec durée et distance
- Alerte si la marche > 1500m vers une station

Source de données : 100% pipeline (Sprint VPS-6, fail loud) :
* silver.velov_clean (dispo temps réel)
* referentiel.lieux_lyon (coordonnées GPS)
* src.routing.pathfinder.compute_itinerary (graphe routier pour le segment vélo)
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import _is_demo_mode
from src.data.exceptions import DashboardDataError
from src.routing.pathfinder_multimodal import (
    VelovItinerary,
    VelovSegment,
    plan_velov_trip,
)

# Couleurs des polylines par mode
_MODE_COLOR = {
    "walk": "#9E9E9E",         # gris — marche
    "cycle": "#1976D2",        # bleu — Vélov
    "destination": "#9E9E9E",  # gris — marche vers destination
}


def render_velov_trip(
    origin: str,
    destination: str,
    origin_coords: tuple[float, float] | None = None,
    dest_coords: tuple[float, float] | None = None,
    height: int = 450,
) -> None:
    """Affiche le trajet Vélov + marche entre 2 points.

    Args:
        origin: nom de lieu (résolu via referentiel.lieux_lyon).
        destination: nom de lieu destination.
        origin_coords: (lon, lat) — si fourni, évite la résolution.
        dest_coords: (lon, lat) — idem.
        height: hauteur de la carte en pixels.
    """
    # Résolution des adresses si pas fournies
    if origin_coords is None:
        try:
            origin_coords = _resolve_lieu(origin)
        except DashboardDataError as e:
            st.error(f"⚠️ {e}")
            return
    if dest_coords is None:
        try:
            dest_coords = _resolve_lieu(destination)
        except DashboardDataError as e:
            st.error(f"⚠️ {e}")
            return

    if not origin_coords or not dest_coords:
        st.error(
            f"❌ Adresses non résolues. Origin={origin!r} → {origin_coords}, "
            f"Dest={destination!r} → {dest_coords}"
        )
        return

    origin_lon, origin_lat = origin_coords
    dest_lon, dest_lat = dest_coords

    # Calcul du trajet Vélov
    with st.spinner("🚲 Recherche stations Vélov + calcul trajet…"):
        try:
            itin = plan_velov_trip(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                origin_label=origin,
                dest_label=destination,
            )
        except DashboardDataError as e:
            st.error(f"⚠️ {e}")
            return

    if itin.source == "demo":
        st.info("🟡 Mode démo — données Vélov non chargées. Connecter la DB pour voir le trajet réel.")
        return

    if not itin.segments:
        st.warning(
            "⚠️ Aucune station Vélov disponible à proximité. "
            "Vérifiez que silver.velov_clean est alimentée (DAG collect_bronze)."
        )
        return

    _render_velov_summary(itin)
    _render_velov_map(itin, origin_coords, dest_coords, height=height)
    _render_velov_segments(itin)


def _render_velov_summary(itin: VelovItinerary) -> None:
    """KPIs haut : 4 colonnes (durée totale, distance, vitesse Vélov, statut)."""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "🕐 Durée totale",
            f"{itin.total_duration_min:.1f} min",
        )
    with col2:
        st.metric("📏 Distance", f"{itin.total_distance_m / 1000:.2f} km")
    with col3:
        # Vitesse moyenne pondérée sur le segment Vélov
        cycle_seg = next((s for s in itin.segments if s.mode == "cycle"), None)
        if cycle_seg and cycle_seg.duration_min > 0:
            avg_kmh = cycle_seg.distance_m / 1000.0 / cycle_seg.duration_min * 60
            st.metric("🚲 Vélov moyen", f"{avg_kmh:.1f} km/h")
        else:
            st.metric("🚲 Vélov moyen", "—")
    with col4:
        status = "✅ Faisable" if itin.feasible else "⚠️ À vérifier"
        st.metric("📊 Statut", status)

    # Alertes spécifiques
    for seg in itin.segments:
        if "⚠️" in seg.notes:
            st.warning(f"⚠️ {seg.from_label} → {seg.to_label} : {seg.notes}")


def _render_velov_map(
    itin: VelovItinerary,
    origin_coords: tuple[float, float],
    dest_coords: tuple[float, float],
    height: int = 450,
) -> None:
    """Carte Folium avec polylines par segment + markers."""
    try:
        import folium
        from streamlit_folium import st_folium
    except ImportError:
        st.warning("⚠️ folium/streamlit-folium non disponible — affichage liste uniquement")
        return

    # Centre sur le milieu de l'itinéraire
    all_lons = [origin_coords[0], dest_coords[0]]
    all_lats = [origin_coords[1], dest_coords[1]]
    for seg in itin.segments:
        all_lons.extend([seg.from_lon, seg.to_lon])
        all_lats.extend([seg.from_lat, seg.to_lat])
    center_lat = sum(all_lats) / len(all_lats)
    center_lon = sum(all_lons) / len(all_lons)

    m = folium.Map(location=[center_lat, center_lon], zoom_start=13, tiles="CartoDB positron")

    # Marker origine
    folium.Marker(
        [origin_coords[1], origin_coords[0]],
        popup=f"🟢 <b>{itin.origin_label}</b><br/>Point de départ",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(m)

    # Marker destination
    folium.Marker(
        [dest_coords[1], dest_coords[0]],
        popup=f"🔴 <b>{itin.destination_label}</b><br/>Point d'arrivée",
        icon=folium.Icon(color="red", icon="stop"),
    ).add_to(m)

    # Polylines par segment + markers stations Vélov
    for seg in itin.segments:
        color = _MODE_COLOR.get(seg.mode, "#666")
        # dash_array pour la marche (pointillé)
        dash_array = "5, 8" if seg.mode in ("walk", "destination") else None

        polyline = folium.PolyLine(
            locations=[
                [seg.from_lat, seg.from_lon],
                [seg.to_lat, seg.to_lon],
            ],
            color=color,
            weight=5,
            opacity=0.85,
            dash_array=dash_array,
            popup=_segment_popup_html(seg),
        )
        polyline.add_to(m)

        # Marker Vélov (uniquement sur les nœuds stations)
        if seg.mode in ("cycle",) or (seg.mode == "walk" and "Vélov" in seg.notes) \
                or (seg.mode == "destination" and seg.from_label and seg.from_label != "Destination"):
            # Marker station Vélov départ/arrivée
            if seg.n_bikes_depart is not None or seg.n_docks_arrive is not None:
                popup = (
                    f"🚲 <b>{seg.to_label if seg.mode == 'walk' else seg.from_label}</b><br/>"
                    + (f"🚴 Vélos dispo : {seg.n_bikes_depart}<br/>" if seg.n_bikes_depart is not None else "")
                    + (f"🅿️ Docks libres : {seg.n_docks_arrive}<br/>" if seg.n_docks_arrive is not None else "")
                    + f"📏 {seg.distance_m:.0f} m · 🕐 {seg.duration_min} min"
                )
                # Position de la station = to_label (départ) ou from_label (arrivée)
                if seg.mode == "walk":
                    s_lat, s_lon = seg.to_lat, seg.to_lon
                else:
                    s_lat, s_lon = seg.from_lat, seg.from_lon
                folium.Marker(
                    [s_lat, s_lon],
                    popup=popup,
                    icon=folium.Icon(color="blue", icon="bicycle", prefix="fa"),
                ).add_to(m)

    st_folium(m, width=None, height=height, returned_objects=[])


def _render_velov_segments(itin: VelovItinerary) -> None:
    """Cards détaillées des 3 segments."""
    with st.expander(f"🛣️ Détail des {len(itin.segments)} segments", expanded=False):
        for i, seg in enumerate(itin.segments, 1):
            mode_label = {
                "walk": "🚶 Marche",
                "cycle": "🚲 Vélov",
                "destination": "🚶 Marche",
            }.get(seg.mode, seg.mode)
            color = _MODE_COLOR.get(seg.mode, "#666")

            extras = ""
            if seg.n_bikes_depart is not None:
                extras += f" · 🚴 {seg.n_bikes_depart} vélos"
            if seg.n_docks_arrive is not None:
                extras += f" · 🅿️ {seg.n_docks_arrive} docks"

            st.markdown(
                f"""
                <div style="display:flex;align-items:center;gap:0.8rem;
                            padding:0.6rem;background:var(--bg-card);border-radius:4px;
                            margin:0.3rem 0;border-left:4px solid {color};">
                    <div style="background:{color};color:white;width:28px;height:28px;
                                border-radius:50%;display:flex;align-items:center;
                                justify-content:center;font-weight:600;font-size:0.85rem;
                                flex-shrink:0;">
                        {i}
                    </div>
                    <div style="flex:1;">
                        <div style="font-weight:600;font-size:0.9rem;">
                            {mode_label} : {seg.from_label} → {seg.to_label}
                        </div>
                        <div style="font-size:0.8rem;opacity:0.7;">
                            📏 {seg.distance_m:.0f} m · 🕐 {seg.duration_min} min{extras}
                        </div>
                        {f'<div style="font-size:0.75rem;opacity:0.6;font-style:italic;">{seg.notes}</div>' if seg.notes else ''}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _segment_popup_html(seg: VelovSegment) -> str:
    """HTML du popup Folium pour un segment."""
    mode_label = {
        "walk": "🚶 Marche",
        "cycle": "🚲 Vélov",
        "destination": "🚶 Marche",
    }.get(seg.mode, seg.mode)
    html = f"<b>{mode_label}</b><br/>{seg.from_label} → {seg.to_label}<br/>"
    html += f"📏 {seg.distance_m:.0f} m<br/>🕐 {seg.duration_min} min"
    if seg.n_bikes_depart is not None:
        html += f"<br/>🚴 {seg.n_bikes_depart} vélos dispo"
    if seg.n_docks_arrive is not None:
        html += f"<br/>🅿️ {seg.n_docks_arrive} docks libres"
    return html


def _resolve_lieu(text: str) -> tuple[float, float] | None:
    """Résout un nom de lieu → (lon, lat) depuis ``referentiel.lieux_lyon``.

    En mode démo : utilise le mock ``lyon_addresses``.

    Robuste aux labels préfixés par emoji (ex: ``"🌳 Parc de la Tête d'Or, Lyon"``
    retourné par ``search_bar.render_search_bar()``). L'emoji et l'espace
    initial sont strippés avant la query SQL.
    """
    if _is_demo_mode():
        from src.data.mock.lyon_addresses import resolve_address
        return resolve_address(text)

    from src.data.db_query import _is_db_available, execute_query
    from src.data.exceptions import DashboardDataError

    if not _is_db_available():
        raise DashboardDataError(source="referentiel.lieux_lyon", detail="DB indisponible")

    if not text:
        return None
    # Strip emoji préfixe (search_bar préfixe avec "🏙 Villeurbanne", etc.)
    # Les emojis sont en dehors du BMP, on strip le 1er "mot" s'il est <= 3 chars
    # et ne contient que des non-ASCII.
    cleaned = text.strip()
    if cleaned and ord(cleaned[0]) > 0x2700:  # Symboles Unicode (emojis)
        # Skip premier char + espace
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
