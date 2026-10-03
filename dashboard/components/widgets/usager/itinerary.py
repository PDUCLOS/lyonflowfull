"""Widget — Affichage d'un itinéraire voiture avec carte et segments.

Affiche :
- Jusqu'à 3 itinéraires réellement différents (radio selector)
- Carte Folium avec polyline colorée par vitesse (vert→rouge), alternatives en gris
- Liste des segments avec longueur / vitesse / durée
- KPI résumé (durée, distance, vitesse moyenne, confiance capteurs)

Résolution d'adresse via ``referentiel.lieux_lyon`` (PostgreSQL).
Alternatives cachées en session_state pour survivre aux reruns Streamlit.
"""

from __future__ import annotations

import logging
import math

import streamlit as st

from dashboard.components.a11y import st_folium_with_alt
from dashboard.components.colors import COLORS
from dashboard.components.error_display import show_error
from dashboard.components.map_tiles import FOLIUM_TILES
from src.data.data_loader import load_lyon_addresses
from src.data.exceptions import DashboardDataError
from src.routing import Itinerary, ItinerarySegment, compute_itinerary_alternatives

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
    origin_coords: tuple[float, float] | None = None,
    dest_coords: tuple[float, float] | None = None,
) -> dict | None:
    """Affiche l'itinéraire entre 2 adresses.

    Args:
        origin: adresse d'origine (texte)
        destination: adresse de destination (texte)
        origin_coords: (lon, lat) pré-résolu, évite double query DB.
        dest_coords: (lon, lat) pré-résolu.

    Returns:
        Dict ``{"duration_min", "distance_km", "feasible",
        "avg_speed_kmh", "source": "computed"}`` pour intégration au comparateur
        multimodal d'Usager_1. None si itinéraire non calculé.
    """
    try:
        if origin_coords is None:
            origin_coords = _resolve_address(origin)
        if dest_coords is None:
            dest_coords = _resolve_address(destination)
    except DashboardDataError as e:
        show_error("db_down", str(e))
        return None

    if not origin_coords:
        sample = ", ".join(_sample_addresses(5))
        show_error("geocoding_fail", f"Adresse d'origine non reconnue : '{origin}'. Essayez : {sample}...")
        return None
    if not dest_coords:
        show_error("geocoding_fail", f"Adresse de destination non reconnue : '{destination}'.")
        return None

    from dashboard.components.loading_state import empty_state, loading_wrapper

    # Cache alternatives in session_state to survive radio reruns
    cache_key = "itin_cached_alts"
    cached = st.session_state.get(cache_key)
    if cached and cached["origin"] == origin and cached["dest"] == destination:
        alternatives = cached["alternatives"]
    else:
        with loading_wrapper("Calcul des itinéraires en cours… (3 alternatives)", "🔍"):
            alternatives = compute_itinerary_alternatives(
                origin_lon=origin_coords[0],
                origin_lat=origin_coords[1],
                destination_lon=dest_coords[0],
                destination_lat=dest_coords[1],
                k=3,
            )
        st.session_state[cache_key] = {
            "origin": origin,
            "dest": destination,
            "alternatives": alternatives,
        }

    if not alternatives:
        empty_state(
            icon="🗺️",
            title="Aucun itinéraire trouvé",
            message="Le graphe routier n'est peut-être pas chargé. Vérifie "
            "que les données Gold sont à jour ou choisis un autre point "
            "d'arrivée.",
        )
        return None

    if len(alternatives) > 1:
        fastest = alternatives[0]
        options = [f"Itinéraire {i + 1} — {_fmt_route_label(it, fastest)}" for i, it in enumerate(alternatives)]
        chosen_idx = st.radio(
            "Choisis ton itinéraire",
            options=range(len(alternatives)),
            format_func=lambda i: options[i],
            index=0,
            key="itin_alt_choice",
            horizontal=True,
            help="Le n°1 est le plus rapide. Les autres empruntent d'autres axes "
            "(au plus 75 % de trajet commun, au plus +50 % de temps). Seules les voies "
            "ouvertes aux voitures sont utilisées (ni couloirs bus, ni voies tram).",
        )
        itinerary = alternatives[chosen_idx]
    else:
        chosen_idx = 0
        itinerary = alternatives[0]

    _render_summary(itinerary)
    others = [alt for i, alt in enumerate(alternatives) if i != chosen_idx]
    _render_map(itinerary, origin_coords, dest_coords, others=others, map_key=f"itin_map_{chosen_idx}")
    _render_segments(itinerary)

    return {
        "duration_min": float(itinerary.total_duration_s) / 60.0,
        "distance_km": float(itinerary.total_length_m) / 1000.0,
        "feasible": True,
        "avg_speed_kmh": float(getattr(itinerary, "average_speed_kmh", 0.0) or 0.0),
        "source": "computed",
    }


def _main_road(itin: Itinerary, exclude: frozenset[str] = frozenset()) -> str | None:
    """Rue nommée la plus longue de l'itinéraire, hors ``exclude``."""
    lengths: dict[str, float] = {}
    for seg in itin.segments:
        if seg.channel_id and seg.channel_id not in exclude:
            lengths[seg.channel_id] = lengths.get(seg.channel_id, 0.0) + seg.length_m
    return max(lengths, key=lengths.__getitem__) if lengths else None


def _fmt_route_label(itin: Itinerary, fastest: Itinerary | None = None) -> str:
    """Label compact du radio button d'alternative.

    Le départ et l'arrivée sont communs à tous les itinéraires : on affiche
    ce qui les distingue, l'écart de temps avec le plus rapide et l'axe
    principal qui n'est pas sur le plus rapide.
    Format : "3.6 km · 11 min (+2 min) · via Rue Baraban"
    """
    label = f"{itin.total_length_m / 1000.0:.1f} km · {itin.total_duration_s / 60.0:.0f} min"
    road = _main_road(itin)
    if fastest is not None and fastest is not itin:
        delta_min = round((itin.total_duration_s - fastest.total_duration_s) / 60.0)
        label += f" (+{delta_min} min)" if delta_min >= 1 else " (même durée)"
        fastest_roads = frozenset(seg.channel_id for seg in fastest.segments if seg.channel_id)
        road = _main_road(itin, exclude=fastest_roads) or road
    if road:
        label += f" · via {road[:35] + '…' if len(road) > 35 else road}"
    return label


def _render_summary(itinerary: Itinerary) -> None:
    """Affiche le résumé (durée, distance, vitesse moyenne, confiance)."""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Durée totale", f"{itinerary.total_duration_min:.1f} min")
    with col2:
        st.metric("Distance", f"{itinerary.total_length_m / 1000:.2f} km")
    with col3:
        st.metric("Vitesse moyenne", f"{itinerary.average_speed_kmh:.1f} km/h")
    with col4:
        st.metric("Confiance", f"{int(itinerary.confidence * 100)}%")


def _render_map(
    itinerary: Itinerary,
    origin_coords: tuple[float, float],
    dest_coords: tuple[float, float],
    others: list[Itinerary] | None = None,
    map_key: str = "itin_map",
) -> None:
    """Affiche la carte Folium avec segments colorés par vitesse trafic.

    origin_coords / dest_coords = (lon, lat) from DB.
    Folium expects [lat, lon].
    ``others`` : alternatives non sélectionnées, tracées en gris sous l'itinéraire
    choisi. ``map_key`` change avec la sélection pour forcer le rendu de la carte.
    """
    try:
        import folium

        o_lat, o_lon = origin_coords[1], origin_coords[0]
        d_lat, d_lon = dest_coords[1], dest_coords[0]

        others = others or []
        node_latlons = [(seg.start_lat, seg.start_lon) for it in [itinerary, *others] for seg in it.segments]
        all_lats = [o_lat, d_lat] + [p[0] for p in node_latlons]
        all_lons = [o_lon, d_lon] + [p[1] for p in node_latlons]

        # Centre et zoom calculés sur l'emprise : fit_bounds n'est pas toujours
        # appliqué quand la carte est recréée (changement d'itinéraire).
        center_lat = (min(all_lats) + max(all_lats)) / 2
        center_lon = (min(all_lons) + max(all_lons)) / 2
        zoom = _zoom_for_bounds(max(all_lats) - min(all_lats), max(all_lons) - min(all_lons), center_lat)

        m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, tiles=FOLIUM_TILES)

        folium.Marker(
            [o_lat, o_lon],
            popup="Départ",
            icon=folium.Icon(color="green", icon="play"),
        ).add_to(m)
        folium.Marker(
            [d_lat, d_lon],
            popup="Arrivée",
            icon=folium.Icon(color="red", icon="stop"),
        ).add_to(m)

        # Alternatives non sélectionnées : trait gris pointillé, sous l'itinéraire choisi
        for alt in others:
            for seg in alt.segments:
                folium.PolyLine(
                    locations=_segment_latlons(seg),
                    color=COLORS["text_disabled"],
                    weight=4,
                    opacity=0.6,
                    dash_array="6 8",
                    tooltip="Autre itinéraire",
                ).add_to(m)

        # chaque segment peut avoir une géométrie OSM multi-vertices
        # (LineString). On l'utilise pour tracer des polylines qui suivent
        # les vraies rues, pas des lignes droites entre nœuds H3.
        for seg in itinerary.segments:
            color = _speed_to_color(seg.speed_kmh)

            locations = _segment_latlons(seg)

            popup = f"<b>{seg.speed_kmh:.0f} km/h</b><br>{seg.length_m:.0f} m · {seg.duration_s:.0f}s"
            if seg.channel_id:
                popup += f"<br>{seg.channel_id}"

            folium.PolyLine(
                locations=locations,
                color=color,
                weight=6,
                opacity=0.85,
                popup=popup,
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

        st_folium_with_alt(m, width=None, height=400, returned_objects=[], key=map_key)

        st.markdown("**Légende trafic** : Fluide (>40 km/h) · Modéré (25-40) · Dense (15-25) · Bloqué (<15)")

    except ImportError:
        st.warning("folium non disponible — affichage liste uniquement")


def _zoom_for_bounds(
    span_lat: float, span_lon: float, center_lat: float, width_px: int = 400, height_px: int = 400
) -> int:
    """Zoom Web Mercator le plus élevé qui fait tenir l'emprise dans la carte (marge comprise)."""
    margin = 0.006  # même marge que fit_bounds (±0.003°)
    lon_extent = max(span_lon + margin, 1e-4)
    # En Mercator, 1° de latitude s'étire de 1/cos(lat) par rapport à 1° de longitude
    lat_extent = max((span_lat + margin) / math.cos(math.radians(center_lat)), 1e-4)
    zoom = math.log2(min(width_px * 360 / (256 * lon_extent), height_px * 360 / (256 * lat_extent)))
    return max(10, min(16, math.floor(zoom)))


def _segment_latlons(seg: ItinerarySegment) -> list[list[float]]:
    """Polyline [[lat, lon], ...] d'un segment (géométrie OSM [[lon, lat], ...])."""
    if seg.geometry and len(seg.geometry) >= 2:
        return [[float(pt[1]), float(pt[0])] for pt in seg.geometry]
    # Fallback si géométrie absente (ne devrait plus arriver avec pgRouting)
    return [[seg.start_lat, seg.start_lon], [seg.end_lat, seg.end_lon]]


def _render_segments(itinerary: Itinerary) -> None:
    """Affiche la liste détaillée des segments."""
    with st.expander(f"Détail des {len(itinerary.segments)} segments", expanded=False):
        for i, seg in enumerate(itinerary.segments, 1):
            color = _speed_to_color(seg.speed_kmh)
            road_label = seg.channel_id or "Voie sans nom"
            st.markdown(
                f"""
                <div style="display:flex;align-items:center;gap:0.8rem;
                            padding:0.5rem;background:var(--bg-card);border-radius:4px;
                            margin:0.3rem 0;border-left:4px solid {color};">
                    <div class="lyf-detail" style="background:{color};color:white;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:600;flex-shrink:0;">
                        {i}
                    </div>
                    <div style="flex:1;">
                        <div style="font-weight:600;font-size:0.9rem;">{road_label}</div>
                        <div style="font-size:0.8rem;opacity:0.7;">
                            {seg.length_m:.0f} m · {seg.speed_kmh:.0f} km/h · {seg.duration_s / 60:.1f} min
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
