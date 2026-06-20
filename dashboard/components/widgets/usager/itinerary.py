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

import logging

import streamlit as st

from dashboard.components.colors import COLORS
from src.data.data_loader import load_lyon_addresses
from src.data.exceptions import DashboardDataError
from src.routing import Itinerary, compute_itinerary

logger = logging.getLogger(__name__)


def _resolve_address(text: str) -> tuple[float, float] | None:
    """Résout une adresse texte → (lon, lat) via la DB (referentiel.lieux_lyon).

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
) -> dict | None:
    """Affiche l'itinéraire entre 2 adresses.

    Args:
        origin: adresse d'origine (texte)
        destination: adresse de destination (texte)
        horizon_minutes: 60 = H+1h (défaut Sprint 8+), 0 = maintenant

    Returns:
        Sprint 16 Axe C — Dict ``{"duration_min", "distance_km", "feasible",
        "avg_speed_kmh", "source": "computed"}`` pour intégration au comparateur
        multimodal d'Usager_1. None si itinéraire non calculé.
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
    from dashboard.components.loading_state import empty_state, loading_wrapper

    with loading_wrapper("Calcul itinéraire en cours…", "🔍"):
        itinerary = compute_itinerary(
            origin_lon=origin_coords[0],
            origin_lat=origin_coords[1],
            destination_lon=dest_coords[0],
            destination_lat=dest_coords[1],
            horizon_minutes=horizon_minutes,
        )

    if not itinerary or not itinerary.segments:
        empty_state(
            icon="🗺️",
            title="Aucun itinéraire trouvé",
            message="Le graphe routier n'est peut-être pas chargé. Vérifie "
            "que les données Gold sont à jour ou choisis un autre point "
            "d'arrivée.",
        )
        return

    # Comparaison si horizon > 0
    comparison = None
    if horizon_minutes > 0:
        with loading_wrapper(f"Comparaison avec H+{horizon_minutes}min…", "🔮"):
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

    # Sprint 16 Axe C — Retour dict pour comparateur multimodal.
    # itinerary.total_duration_s est en secondes, total_length_m en mètres.
    return {
        "duration_min": float(itinerary.total_duration_s) / 60.0,
        "distance_km": float(itinerary.total_length_m) / 1000.0,
        "feasible": True,
        "avg_speed_kmh": float(getattr(itinerary, "average_speed_kmh", 0.0) or 0.0),
        "source": "computed",
    }


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
    """Affiche la carte Folium avec segments colorés par vitesse trafic.

    origin_coords / dest_coords = (lon, lat) from DB.
    Folium expects [lat, lon].
    """
    try:
        import folium
        from streamlit_folium import st_folium

        o_lat, o_lon = origin_coords[1], origin_coords[0]
        d_lat, d_lon = dest_coords[1], dest_coords[0]

        node_latlons = [(seg.start_lat, seg.start_lon) for seg in itinerary.segments]
        all_lats = [o_lat, d_lat] + [p[0] for p in node_latlons]
        all_lons = [o_lon, d_lon] + [p[1] for p in node_latlons]

        center_lat = sum(all_lats) / len(all_lats)
        center_lon = sum(all_lons) / len(all_lons)

        m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles="CartoDB positron")

        folium.Marker(
            [o_lat, o_lon],
            popup="🟢 Départ",
            icon=folium.Icon(color="green", icon="play"),
        ).add_to(m)
        folium.Marker(
            [d_lat, d_lon],
            popup="🔴 Arrivée",
            icon=folium.Icon(color="red", icon="stop"),
        ).add_to(m)

        # Full path: origin → node₀ → node₁ → … → destination
        full_path = [(o_lat, o_lon), *node_latlons, (d_lat, d_lon)]

        # Draw colored segments between consecutive points
        for i in range(len(full_path) - 1):
            p1, p2 = full_path[i], full_path[i + 1]
            seg_idx = min(i, len(itinerary.segments) - 1)
            seg = itinerary.segments[seg_idx]
            color = _speed_to_color(seg.speed_kmh)

            folium.PolyLine(
                locations=[list(p1), list(p2)],
                color=color,
                weight=6,
                opacity=0.85,
                popup=(f"🚗 <b>{seg.speed_kmh:.0f} km/h</b><br>📏 {seg.length_m:.0f} m · 🕐 {seg.duration_s:.0f}s"),
            ).add_to(m)

        # Small colored circle at each node
        for i, seg in enumerate(itinerary.segments):
            color = _speed_to_color(seg.speed_kmh)
            folium.CircleMarker(
                location=[seg.start_lat, seg.start_lon],
                radius=5,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.9,
                tooltip=f"#{i + 1} · {seg.speed_kmh:.0f} km/h",
            ).add_to(m)

        m.fit_bounds(
            [[min(all_lats) - 0.003, min(all_lons) - 0.003], [max(all_lats) + 0.003, max(all_lons) + 0.003]],
        )

        st_folium(m, width=None, height=400, returned_objects=[])

        st.markdown(
            "**Légende trafic** : 🟢 Fluide (>40 km/h) · 🟡 Modéré (25-40) · 🟠 Dense (15-25) · 🔴 Bloqué (<15)"
        )

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
                    <div class="lyf-detail" style="background:{color};color:white;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:600;flex-shrink:0;">
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
