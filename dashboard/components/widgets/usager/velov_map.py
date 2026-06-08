"""Widget — Carte Vélo'v stations + prédictions de disponibilité.

Affiche toutes les stations Vélo'v sur la carte de Lyon avec :
* Couleur = nb de vélos disponibles **actuel** (silver.velov_clean)
* Tooltip = nom station + vélos/places actuels + prédiction H+30/H+1h
* Mode "Maintenant" ou "Prédiction H+X" (selectbox)

Source données :
* ``silver.velov_clean`` via ``get_velov_stations_geo()``
* ``gold.velov_predictions`` via ``get_velov_predictions(30 ou 60)``

Sprint 10 — comble le gap "on prédit la dispo mais on l'affiche pas".
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_velov_predictions
from src.data.db_query import get_velov_stations_geo


def _bikes_to_color(bikes: int) -> list:
    """Échelle de couleur basée sur le nb de vélos."""
    if bikes is None or bikes == 0:
        return [231, 76, 60, 220]  # rouge — vide
    if bikes < 5:
        return [255, 152, 0, 220]  # orange — faible
    if bikes < 10:
        return [255, 193, 7, 220]  # jaune — moyen
    return [76, 175, 80, 220]  # vert — OK


def _docks_to_color(docks: int) -> list:
    """Couleur basée sur places libres (mode 'rendre un vélo')."""
    if docks is None or docks == 0:
        return [231, 76, 60, 220]
    if docks < 3:
        return [255, 152, 0, 220]
    return [76, 175, 80, 220]


def _load_stations_with_predictions(horizon_minutes: int = 30) -> pd.DataFrame:
    """Joint stations courantes + prédictions du modèle XGBoost Vélo'v.

    Returns:
        DataFrame: station_id, station_name, lat, lng, bikes_available,
        docks_available, predicted_bikes_30, predicted_bikes_60.
    """
    stations = get_velov_stations_geo()
    if stations.empty:
        return stations

    # Prédictions H+30 et H+1h (peut être vide si DAG pas tourné)
    pred_30 = cached_velov_predictions(horizon_minutes=30, force_mock=False)
    pred_60 = cached_velov_predictions(horizon_minutes=60, force_mock=False)

    # Garder la prédiction la plus récente par station
    if not pred_30.empty and "station_id" in pred_30.columns:
        pred_30_latest = (
            pred_30.sort_values("prediction_timestamp", ascending=False)
            .drop_duplicates(subset=["station_id"])
            .rename(columns={"predicted_bikes": "predicted_bikes_30"})
            [["station_id", "predicted_bikes_30"]]
        )
        stations = stations.merge(pred_30_latest, on="station_id", how="left")
    else:
        stations["predicted_bikes_30"] = None

    if not pred_60.empty and "station_id" in pred_60.columns:
        pred_60_latest = (
            pred_60.sort_values("prediction_timestamp", ascending=False)
            .drop_duplicates(subset=["station_id"])
            .rename(columns={"predicted_bikes": "predicted_bikes_60"})
            [["station_id", "predicted_bikes_60"]]
        )
        stations = stations.merge(pred_60_latest, on="station_id", how="left")
    else:
        stations["predicted_bikes_60"] = None

    return stations


def render_velov_map(
    *,
    height: int = 400,
    horizon_default: int = 0,
    show_horizon_selector: bool = True,
    key_suffix: str = "",
) -> None:
    """Carte Vélo'v avec choix Maintenant / H+30 / H+1h.

    Args:
        height: hauteur pydeck.
        horizon_default: 0 (maintenant), 30 ou 60.
        show_horizon_selector: affiche selectbox de l'horizon.
        key_suffix: suffixe key Streamlit (évite collisions).
    """
    df = _load_stations_with_predictions()
    if df.empty:
        st.info("Pas de stations Vélo'v disponibles (vérifier `silver.velov_clean`).")
        return

    horizon = horizon_default
    if show_horizon_selector:
        labels = {0: "Maintenant", 30: "Prédiction H+30min", 60: "Prédiction H+1h"}
        horizon = st.selectbox(
            "Horizon",
            list(labels.keys()),
            index=list(labels.keys()).index(horizon_default) if horizon_default in labels else 0,
            format_func=lambda x: labels[x],
            key=f"velov_map_horizon_{key_suffix}",
        )

    # Choisir colonne d'affichage
    if horizon == 30:
        df["bikes_display"] = df["predicted_bikes_30"].fillna(df["bikes_available"])
    elif horizon == 60:
        df["bikes_display"] = df["predicted_bikes_60"].fillna(df["bikes_available"])
    else:
        df["bikes_display"] = df["bikes_available"]

    df["bikes_display"] = df["bikes_display"].fillna(0).astype(int)
    df["color"] = df["bikes_display"].apply(_bikes_to_color)

    try:
        import pydeck as pdk

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position=["lng", "lat"],
            get_color="color",
            get_radius=60,
            pickable=True,
        )
        view = pdk.ViewState(latitude=45.76, longitude=4.84, zoom=11.5, pitch=0)
        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=view,
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            tooltip={
                "html": (
                    "<b>{station_name}</b><br/>"
                    "🚲 Maintenant: <b>{bikes_available}</b> vélos · {docks_available} places<br/>"
                    "🔮 H+30: <b>{predicted_bikes_30}</b> · H+1h: <b>{predicted_bikes_60}</b>"
                ),
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
        st.warning("Pydeck non installé — fallback table.")
        st.dataframe(
            df[["station_name", "bikes_available", "docks_available",
                "predicted_bikes_30", "predicted_bikes_60"]].head(50),
            use_container_width=True,
            hide_index=True,
        )

    # Stats globales
    total_bikes = int(df["bikes_display"].sum())
    empty_stations = int((df["bikes_display"] == 0).sum())
    low_stations = int((df["bikes_display"] < 5).sum())
    cols = st.columns(4)
    label = {0: "Maintenant", 30: "H+30min", 60: "H+1h"}[horizon]
    cols[0].metric("Stations", len(df))
    cols[1].metric(f"Vélos ({label})", total_bikes)
    cols[2].metric("Stations vides", empty_stations, delta=None)
    cols[3].metric("Stations < 5 vélos", low_stations)

    st.caption(
        "Légende : 🔴 0 vélo · 🟠 <5 vélos · 🟡 <10 vélos · 🟢 ≥10 vélos · "
        "Prédictions : XGBoost Vélo'v (retrain :50)"
    )


def render_velov_map_compact(*, height: int = 280, key_suffix: str = "") -> None:
    """Version compacte (Usager) — Maintenant uniquement, pas de selectbox."""
    df = _load_stations_with_predictions()
    if df.empty:
        st.caption("🟡 Carte Vélo'v indisponible (pas de stations en Silver)")
        return

    df["bikes_display"] = df["bikes_available"].fillna(0).astype(int)
    df["color"] = df["bikes_display"].apply(_bikes_to_color)

    try:
        import pydeck as pdk

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position=["lng", "lat"],
            get_color="color",
            get_radius=55,
            pickable=True,
        )
        view = pdk.ViewState(latitude=45.76, longitude=4.84, zoom=11.5, pitch=0)
        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=view,
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            tooltip={
                "html": (
                    "<b>{station_name}</b><br/>"
                    "🚲 {bikes_available} · 🅿️ {docks_available}<br/>"
                    "🔮 H+30: {predicted_bikes_30}"
                ),
                "style": {
                    "backgroundColor": COLORS["bg_card"],
                    "color": "white",
                    "padding": "6px",
                    "borderRadius": "4px",
                },
            },
        )
        st.pydeck_chart(deck, use_container_width=True, height=height)
    except ImportError:
        st.dataframe(
            df[["station_name", "bikes_available", "predicted_bikes_30"]].head(20),
            use_container_width=True,
            hide_index=True,
        )
    st.caption("🔴 vide · 🟠 <5 · 🟡 <10 · 🟢 ≥10 · Tooltip = prédiction H+30min")
