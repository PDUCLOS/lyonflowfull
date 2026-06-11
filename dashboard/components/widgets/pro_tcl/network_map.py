"""Widget — Carte réseau Pydeck (bus GPS colorés par retard).

Sprint 8 — Positions bus chargées via data_loader.cached_buses_positions()
(qui lit silver.tcl_vehicles_clean).

Sprint VPS-6 (2026-06-11) — fail loud en prod :
* DB répond, données présentes : carte temps réel.
* DB répond, table vide : ``st.info("Aucun bus en circulation")``.
* DB indispo en prod : ``DashboardDataError`` → ``st.error``.
* Mode démo (``LYONFLOW_DEMO_MODE=1``) : fallback ``ALL_BUSES`` mock autorisé.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_buses_positions
from src.data.data_loader import _is_demo_mode
from src.data.exceptions import DashboardDataError


def _delay_to_color(delay_min: int) -> list:
    """Retourne une couleur RGB selon le retard."""
    if delay_min == 0:
        return [76, 175, 80, 220]  # vert
    if delay_min <= 3:
        return [255, 193, 7, 220]  # jaune
    if delay_min <= 6:
        return [255, 152, 0, 220]  # orange
    return [231, 76, 60, 220]  # rouge


def render_network_map(buses: list | None = None, height: int = 400) -> None:
    """Affiche la carte réseau temps réel des bus.

    Args:
        buses: liste de bus (mock ou réel). Si None, charge via data_loader.
        height: hauteur de la carte en pixels.
    """
    if buses is None:
        try:
            df = cached_buses_positions(force_mock=False)
        except DashboardDataError as e:
            st.error(f"⚠️ {e}")
            return
        if not df.empty:
            # Adapter le format DB → format attendu par le widget
            def _safe_delay_min(seconds):
                """Convertit delay_seconds en minutes, None/string safe."""
                try:
                    return int(float(seconds) / 60)
                except (TypeError, ValueError):
                    return 0

            buses = [
                {
                    "bus_id": row.get("vehicle_ref", "—"),
                    "line_id": row.get("line_ref", "—"),
                    "lat": row.get("lat", 0) or 0,
                    "lon": row.get("lng", 0) or 0,
                    "segment": "—",  # pas dans la table de base
                    "delay_min": _safe_delay_min(row.get("delay_seconds")),
                }
                for _, row in df.iterrows()
            ]
        elif _is_demo_mode():
            # Mode démo uniquement : fallback mock
            from src.data.mock.pro_tcl import ALL_BUSES

            buses = ALL_BUSES
        else:
            # Prod : DB répond mais vide
            st.info("Aucun bus en circulation actuellement.")
            return

    if not buses:
        st.info("Aucun bus en circulation.")
        return

    # Préparer DataFrame pour pydeck
    df = pd.DataFrame(buses)
    df["color"] = df["delay_min"].apply(_delay_to_color)

    try:
        import pydeck as pdk

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position=["lon", "lat"],
            get_color="color",
            get_radius=80,
            pickable=True,
        )

        view_state = pdk.ViewState(
            latitude=45.76,
            longitude=4.84,
            zoom=11.5,
            pitch=0,
        )

        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            tooltip={
                "html": "<b>{bus_id}</b><br/>Ligne: {line_id}<br/>Segment: {segment}<br/>Retard: {delay_min} min",
                "style": {
                    "backgroundColor": COLORS["bg_card"],
                    "color": "white",
                    "padding": "8px",
                    "borderRadius": "4px",
                },
            },
        )

        st.pydeck_chart(deck, use_container_width=True, height=height)

    except ImportError:
        # Fallback si pydeck n'est pas installé
        st.warning("⚠️ Pydeck non disponible — fallback liste")
        st.dataframe(
            df[["bus_id", "line_id", "segment", "delay_min"]],
            use_container_width=True,
            height=height,
        )
