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

from dashboard.components.a11y import st_folium_with_alt
from dashboard.components.colors import COLORS
from dashboard.components.error_display import show_error
from dashboard.components.loading_state import loading_wrapper
from src.data.exceptions import DashboardDataError
from src.routing.pathfinder_multimodal import (
    VelovItinerary,
    VelovSegment,
    plan_velov_trip,
)

# Couleurs des polylines par mode
_MODE_COLOR = {
    "walk": "#9E9E9E",  # gris — marche
    "cycle": "#1976D2",  # bleu — Vélov
    "destination": "#9E9E9E",  # gris — marche vers destination
}


def render_velov_trip(
    origin: str,
    destination: str,
    origin_coords: tuple[float, float] | None = None,
    dest_coords: tuple[float, float] | None = None,
    height: int = 450,
) -> dict | None:
    """Affiche le trajet Vélov + marche entre 2 points.

    Args:
        origin: nom de lieu (résolu via referentiel.lieux_lyon).
        destination: nom de lieu destination.
        origin_coords: (lon, lat) — si fourni, évite la résolution.
        dest_coords: (lon, lat) — idem.
        height: hauteur de la carte en pixels.

    Returns:
    Axe C — Dict ``{"duration_min", "distance_km", "feasible",
        "source": "computed"}`` pour intégration au comparateur multimodal
        d'Usager_1. None si le trajet n'a pas pu être calculé (adresse non
        résolue, pas de station Vélov, erreur DB).
    """
    with loading_wrapper("Chargement Velov trip…", "⏳"):
        # Résolution des adresses si pas fournies
        if origin_coords is None:
            try:
                origin_coords = _resolve_lieu(origin)
            except DashboardDataError as e:
                show_error("db_down", str(e))
                return
        if dest_coords is None:
            try:
                dest_coords = _resolve_lieu(destination)
            except DashboardDataError as e:
                show_error("db_down", str(e))
                return

        if not origin_coords or not dest_coords:
            show_error(
                "geocoding_fail",
                f"❌ Adresses non résolues. Origin={origin!r} → {origin_coords}, Dest={destination!r} → {dest_coords}",
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
                show_error("db_down", str(e))
                return

        # (2026-06-17) — viré le check `itin.source == "demo"` :
        # plan_velov_trip() ne retourne plus source="demo" (mode démo supprimé).

        if not itin.segments:
            st.warning(
                "⚠️ Aucune station Vélov disponible à proximité. "
                "Vérifiez que silver.velov_clean est alimentée (DAG collect_bronze)."
            )
            return

        _render_velov_summary(itin)
        # (2026-06-19) — Cards stations proéminentes (départ + arrivée)
        # avec vélos/docks/méca-élec/statut coloré/distance à pied.
        _render_station_cards(itin)
        # Diagnostics VIDE/PLEINE
        for diag in itin.diagnostics:
            st.warning(diag)
        # Alternatives smart-routed
        _render_alternatives_card(
            "Alternatives à la borne de départ",
            itin.origin_alternatives,
            "origin",
        )
        _render_alternatives_card(
            "Alternatives à la borne d'arrivée",
            itin.dest_alternatives,
            "dest",
        )
        # Légende maillage
        _render_neighbors_legend(itin.origin_neighbors, itin.dest_neighbors)
        # Carte + segments
        _render_velov_map(itin, origin_coords, dest_coords, height=height)
        _render_velov_segments(itin)

        # Axe C — Retour dict pour comparateur multimodal.
        # itin.total_distance_m est en mètres, total_duration_min en minutes.
        return {
            "duration_min": float(itin.total_duration_min),
            "distance_km": float(itin.total_distance_m) / 1000.0,
            "feasible": True,
            "source": "computed",
        }


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


def _render_station_cards(itin: VelovItinerary) -> None:
    """(2026-06-19) — 2 cards stations proéminentes (départ + arrivée).

    Affichées directement après le résumé KPIs (pas dans un expander).
    Visibilité immédiate de : nom, vélos dispo (méca+élec si dispo), docks,
    statut coloré (vert OK / orange FAIBLE / rouge VIDE-PLEINE), distance à pied.

    Sources :
    - cycle_seg.from_label / to_label (noms stations via smart routing)
    - cycle_seg.n_bikes_depart / n_docks_arrive (dispo temps réel)
    - cycle_seg.n_bikes_mechanical / n_bikes_electrical (optionnel, GBFS)
    - walk_seg / from_seg (distances à pied)
    """
    if not itin.segments:
        return
    cycle_seg = next((s for s in itin.segments if s.mode == "cycle"), None)
    walk_seg = next((s for s in itin.segments if s.mode == "walk"), None)
    dest_seg = next((s for s in itin.segments if s.mode == "destination"), None)
    if cycle_seg is None:
        return

    st.markdown("#### 🚲 Bornes Vélov utilisées")

    col1, col2 = st.columns(2)
    with col1:
        _render_single_station_card(
            role="🟢 DÉPART",
            station_label=cycle_seg.from_label,
            n_bikes=cycle_seg.n_bikes_depart,
            n_docks=None,  # pas dans le segment walk actuel
            n_mech=cycle_seg.n_bikes_mechanical,
            n_elec=cycle_seg.n_bikes_electrical,
            walk_distance_m=walk_seg.distance_m if walk_seg else 0.0,
            walk_duration_min=walk_seg.duration_min if walk_seg else 0.0,
        )
    with col2:
        _render_single_station_card(
            role="🔴 ARRIVÉE",
            station_label=cycle_seg.to_label,
            n_bikes=None,  # pas dans le segment destination actuel
            n_docks=cycle_seg.n_docks_arrive,
            n_mech=None,
            n_elec=None,
            walk_distance_m=dest_seg.distance_m if dest_seg else 0.0,
            walk_duration_min=dest_seg.duration_min if dest_seg else 0.0,
        )


def _render_single_station_card(
    role: str,
    station_label: str,
    n_bikes: int | None,
    n_docks: int | None,
    n_mech: int | None,
    n_elec: int | None,
    walk_distance_m: float,
    walk_duration_min: float,
) -> None:
    """Une card station (Sprint 14) — vélos, docks, statut coloré, marche.

    Statut couleur :
    - 🔴 VIDE / PLEINE (rouge) si vélos == 0 ou docks == 0
    - 🟠 FAIBLE (orange) si vélos < 5 ou docks < 5
    - 🟢 OK (vert) sinon (≥5 vélos ET ≥5 docks)
    """
    # Couleur + label statut
    if n_bikes == 0:
        color, status_label = "#F44336", "🔴 VIDE"
    elif n_docks == 0:
        color, status_label = "#F44336", "🔴 PLEINE"
    elif (n_bikes is not None and n_bikes < 5) or (n_docks is not None and n_docks < 5):
        color, status_label = "#FF9800", "🟠 FAIBLE"
    else:
        color, status_label = "#4CAF50", "🟢 OK"

    # Détail méca/élec si GBFS le fournit
    mech_elec_html = ""
    if n_mech is not None or n_elec is not None:
        m = int(n_mech) if n_mech is not None else 0
        e = int(n_elec) if n_elec is not None else 0
        mech_elec_html = (
            '<div class="lyf-sublabel" style="opacity:0.65;margin-top:0.3rem;'
            'line-height:1.4;">'
            f"├── 🔧 {m} mécaniques<br/>└── ⚡ {e} électriques"
            "</div>"
        )

    bikes_str = f"{int(n_bikes)} vélos" if n_bikes is not None else "N/A"
    docks_str = f"{int(n_docks)} places" if n_docks is not None else "N/A"

    st.html(
        f"""
        <div class="lyonflow-card" style="border-left:4px solid {color};">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <span class="lyf-sublabel" style="background:{color};color:white;padding:0.2rem 0.6rem;border-radius:12px;font-weight:600;">{role}</span>
                <span class="lyf-sublabel" style="font-weight:700;color:{color};">{status_label}</span>
            </div>
            <div style="font-size:1rem;font-weight:700;margin:0.5rem 0 0.3rem 0;">
                🚲 {station_label}
            </div>
            <div style="display:flex;gap:1rem;align-items:baseline;">
                <div style="font-size:1.1rem;font-weight:700;color:{color};">🚲 {bikes_str}</div>
                <div class="lyf-detail" style="opacity:0.85;">🅿️ {docks_str}</div>
            </div>
            {mech_elec_html}
            <div class="lyf-sublabel" style="opacity:0.7;margin-top:0.5rem;border-top:1px solid rgba(255,255,255,0.1);padding-top:0.4rem;">
                📍 {int(walk_distance_m)}m à pied (~{walk_duration_min:.0f} min)
            </div>
        </div>
        """
    )


def _render_velov_map(
    itin: VelovItinerary,
    origin_coords: tuple[float, float],
    dest_coords: tuple[float, float],
    height: int = 450,
) -> None:
    """Carte Folium avec polylines par segment + markers."""
    try:
        import folium
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

    # Maillage : lignes entre voisines < 200m (Sprint VPS-6 hotfix 2)
    # On dessine les arêtes du graphe local pour visualiser la grappe.
    _render_velov_maillage(m, itin.origin_neighbors, itin.dest_neighbors)

    # Markers Vélov aux stations utilisées
    for seg in itin.segments:
        if (
            seg.mode in ("cycle",)
            or (seg.mode == "walk" and "Vélov" in seg.notes)
            or (seg.mode == "destination" and seg.from_label and seg.from_label != "Destination")
        ):
            if seg.n_bikes_depart is not None or seg.n_docks_arrive is not None:
                popup = (
                    f"🚲 <b>{seg.to_label if seg.mode == 'walk' else seg.from_label}</b><br/>"
                    + (f"🚴 Vélos dispo : {seg.n_bikes_depart}<br/>" if seg.n_bikes_depart is not None else "")
                    + (f"🅿️ Docks libres : {seg.n_docks_arrive}<br/>" if seg.n_docks_arrive is not None else "")
                    + f"📏 {seg.distance_m:.0f} m · 🕐 {seg.duration_min} min"
                )
                if seg.mode == "walk":
                    s_lat, s_lon = seg.to_lat, seg.to_lon
                else:
                    s_lat, s_lon = seg.from_lat, seg.from_lon
                folium.Marker(
                    [s_lat, s_lon],
                    popup=popup,
                    icon=folium.Icon(color="blue", icon="bicycle", prefix="fa"),
                ).add_to(m)

    st_folium_with_alt(m, width=None, height=height, returned_objects=[])


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
                    <div class="lyf-detail" style="background:{color};color:white;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:600;flex-shrink:0;">
                        {i}
                    </div>
                    <div style="flex:1;">
                        <div style="font-weight:600;font-size:0.9rem;">
                            {mode_label} : {seg.from_label} → {seg.to_label}
                        </div>
                        <div style="font-size:0.8rem;opacity:0.7;">
                            📏 {seg.distance_m:.0f} m · 🕐 {seg.duration_min} min{extras}
                        </div>
                        {f'<div class="lyf-sublabel" style="opacity:0.6;font-style:italic;">{seg.notes}</div>' if seg.notes else ""}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_alternatives_card(
    title: str,
    alternatives: list[dict],
    role: str,  # "origin" | "dest"
) -> None:
    """Carte horizontale des bornes alternatives (Sprint VPS-6 hotfix 2).

    Affichée quand la borne #1 a status VIDE ou PLEINE. Propose à l'usager
    de marcher vers une autre borne à proximité.
    """
    if not alternatives:
        return
    st.markdown(f"##### 🔄 Alternatives à la borne {role} ({len(alternatives)})")
    st.caption(
        f"Marche à pied entre bornes voisines — la borne #1 est {'VIDE' if role == 'origin' else 'PLEINE'}"
        if (role == "origin" and any(a.get("status") == "VIDE" for a in alternatives))
        else "Bornes alternatives avec vélos/docks disponibles."
    )
    cols = st.columns(min(3, len(alternatives)))
    for col, alt in zip(cols, alternatives):
        if not alt.get("velov_name"):
            continue
        # Couleur selon dispo
        status = alt.get("status", "UNKNOWN")
        color_map = {
            "OK": COLORS["status_ok"],
            "FAIBLE": COLORS["status_warning"],
            "VIDE": COLORS["status_critical"],
            "PLEINE": COLORS["status_warning"],
        }
        color = color_map.get(status, COLORS["text_muted"])
        bikes = alt.get("num_bikes_available", 0) or 0
        docks = alt.get("num_docks_available", 0) or 0
        walk_min = round(alt.get("distance_m", 0) / 1000.0 / 4.5 * 60.0, 1)
        with col:
            st.html(
                f"""
                <div class="lyonflow-card" style="border-left:4px solid {color};">
                    <div class="lyf-detail" style="font-weight:600;">
                        🚲 {alt["velov_name"]}
                    </div>
                    <div class="lyf-sublabel" style="opacity:0.7;margin-top:0.2rem;">
                        {status} · 📏 {int(alt.get("distance_m", 0))}m · 🚶 {walk_min}min
                    </div>
                    <div style="font-size:1.2rem;font-weight:700;margin:0.3rem 0;color:{color};">
                        🚴 {bikes} vélos
                    </div>
                    <div class="lyf-sublabel" style="opacity:0.7;">
                        🅿️ {docks} docks
                    </div>
                </div>
                """
            )


def _render_velov_maillage(
    m,  # folium.Map
    origin_neighbors: list[dict],
    dest_neighbors: list[dict],
) -> None:
    """Dessine le maillage local des bornes Vélov (lignes entre voisines < 200m).

    Requires folium — imported locally to match the pattern in _render_velov_map.

    Sprint VPS-6 hotfix 2 — visualise la "grappe" de bornes autour des
    2 stations Vélov utilisées. Permet à l'usager de voir s'il y a des
    alternatives à pied.
    """
    import folium

    edges_drawn = set()  # éviter doublons (a-b == b-a)
    for neighbors, color in (
        (origin_neighbors, "#1976D2"),  # bleu pour voisines départ
        (dest_neighbors, "#388E3C"),  # vert pour voisines arrivée
    ):
        for n in neighbors:
            sid_a = n.get("station_id_a", "")
            sid_b = n.get("station_id_b", "")
            if not sid_a or not sid_b:
                continue
            key = tuple(sorted([sid_a, sid_b]))
            if key in edges_drawn:
                continue
            edges_drawn.add(key)
            try:
                line = folium.PolyLine(
                    locations=[
                        [n["lat_a"], n["lon_a"]],
                        [n["lat_b"], n["lon_b"]],
                    ],
                    color=color,
                    weight=1.5,
                    opacity=0.4,
                    dash_array="2, 4",
                )
                line.add_to(m)
            except KeyError:
                # Fallback si la shape du dict est différente
                pass


def _render_neighbors_legend(
    origin_neighbors: list[dict],
    dest_neighbors: list[dict],
) -> None:
    """Mini-caption : nombre de voisines à < 200m pour chaque borne."""
    parts = []
    if origin_neighbors:
        parts.append(f"🚲 Borne départ : {len(origin_neighbors)} voisine(s) à < 200m (maillage actif)")
    if dest_neighbors:
        parts.append(f"🚲 Borne arrivée : {len(dest_neighbors)} voisine(s) à < 200m (maillage actif)")
    if parts:
        st.caption(" · ".join(parts))


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

    Robuste aux labels préfixés par emoji (ex: ``"🌳 Parc de la Tête d'Or, Lyon"``
    retourné par ``search_bar.render_search_bar()``). L'emoji et l'espace
    initial sont strippés avant la query SQL.
    """
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
            cleaned = cleaned[sp + 1 :].strip()
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
