"""Wrappers caches Streamlit pour les loaders DB.

`st.cache_data(ttl=N)` evite de re-frapper la DB a chaque render. Les TTL
sont ajustes par typologie:

- Live trafic / velov / TCL: 30s (donnees temps reel)
- KPIs / heatmaps: 60s (agreges 5min cote DB)
- MLflow / spatial mapping / GNN: 300s (change rarement)
- Synthese / referentiel: 600s (quasi statique)

Usage cote widgets::

    from dashboard.components.data_cache import cached_traffic, cached_velov
    traffic = cached_traffic()
    velov_df = cached_velov()
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from src.data import data_loader as dl

TTL_REALTIME = 30
TTL_FAST = 60
TTL_SLOW = 300
TTL_STATIC = 600


# =============================================================================
# Trafic / Velov / TCL (live)
# =============================================================================


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_traffic() -> dict[str, Any]:
    return dl.load_traffic()


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_traffic_timeseries(node_idx: int, hours: int = 4) -> pd.DataFrame:
    return dl.load_traffic_timeseries(node_idx=node_idx, hours=hours)


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_velov_stations() -> list[dict]:
    return dl.load_velov_stations()


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_velov_predictions(horizon_minutes: int = 60) -> pd.DataFrame:
    return dl.load_velov_predictions(horizon_minutes=horizon_minutes)


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_buses_positions(limit: int = 200) -> pd.DataFrame:
    return dl.load_buses_positions(limit=limit)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_bus_delays(line_ref: str | None = None, days: int = 7) -> pd.DataFrame:
    return dl.load_bus_delays(line_ref=line_ref, days=days)


# =============================================================================
# Bottlenecks / KPI / synthese
# =============================================================================


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_infra_bottlenecks(top: int = 15) -> pd.DataFrame:
    return dl.load_infra_bottlenecks(top=top)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_bottlenecks_summary() -> pd.DataFrame:
    return dl.load_bottlenecks_summary()


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_bottlenecks_top() -> list[dict]:
    return dl.load_bottlenecks_top()


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_predictions_vs_actuals(limit: int = 200) -> pd.DataFrame:
    return dl.load_predictions_vs_actuals(limit=limit)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_city_synthesis() -> dict:
    return dl.load_city_synthesis()


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_elu_kpis_dict() -> dict:
    return dl.load_elu_kpis_dict()


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_line_kpis(line_ids: tuple[str, ...] | None = None) -> dict:
    line_ids_list = list(line_ids) if line_ids else None
    return dl.load_line_kpis(line_ids=line_ids_list)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_otp_heatmap_data() -> pd.DataFrame:
    return dl.load_otp_heatmap_data()


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_correlation_matrix(limit: int = 50) -> pd.DataFrame:
    return dl.load_correlation_matrix(limit=limit)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_segments(limit: int = 200) -> pd.DataFrame:
    return dl.load_segments(limit=limit)


# =============================================================================
# Meteo / alertes / amenagements
# =============================================================================


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_weather_hourly(hours: int = 24) -> pd.DataFrame:
    return dl.load_weather_hourly(hours=hours)


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_recent_alerts(hours: int = 24, limit: int = 50) -> pd.DataFrame:
    return dl.load_recent_alerts(hours=hours, limit=limit)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_amenagements_passes(limit: int = 50) -> pd.DataFrame:
    return dl.load_amenagements_passes(limit=limit)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_kpis_12_months() -> pd.DataFrame:
    return dl.load_kpis_12_months()


# =============================================================================
# RGPD
# =============================================================================


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_rgpd_audit(limit: int = 50) -> pd.DataFrame:
    return dl.load_rgpd_audit(limit=limit)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_rgpd_consents() -> pd.DataFrame:
    return dl.load_rgpd_consents()


# =============================================================================
# Referentiel TCL / spatial / MLflow
# =============================================================================


@st.cache_data(ttl=TTL_STATIC, show_spinner=False)
def cached_tcl_lines() -> list[dict]:
    return dl.load_tcl_lines()


@st.cache_data(ttl=TTL_STATIC, show_spinner=False)
def cached_lyon_addresses() -> list[str]:
    return dl.load_lyon_addresses()


@st.cache_data(ttl=TTL_STATIC, show_spinner=False)
def cached_lyon_addresses_with_coords() -> list[dict]:
    """Adresses Lyon avec coords GPS (pour cartes, markers)."""
    return dl.load_lyon_addresses_with_coords()


@st.cache_data(ttl=TTL_STATIC, show_spinner=False)
def cached_spatial_mapping() -> pd.DataFrame:
    return dl.load_spatial_mapping()


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_traffic_predictions_for_map(horizon_minutes: int = 60, limit: int = 500) -> pd.DataFrame:
    """Cache les prédictions trafic pour la carte GNN.

    Args typés explicitement (pas *args/**kwargs) pour garantir le hashage
    correct des arguments par @st.cache_data (sinon UnhashableParamError si
    un caller passe un dict/list/df).
    """
    return dl.load_traffic_predictions_for_map(horizon_minutes=horizon_minutes, limit=limit)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_mlflow_models() -> list[dict]:
    return dl.load_mlflow_models()


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_mlflow_experiment_summary() -> dict:
    return dl.load_mlflow_experiment_summary()


# =============================================================================
# TomTom coherence (Sprint 13+, 2026-06-18)
# =============================================================================


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_tomtom_coherence(limit: int = 500) -> pd.DataFrame:
    """Cohérence TomTom ↔ capteurs Grand Lyon (dernière heure)."""
    return dl.load_tomtom_coherence(limit=limit)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_tomtom_gl_drift(limit: int = 200) -> pd.DataFrame:
    """Capteurs GL suspectés HS (24h, agrégé)."""
    return dl.load_tomtom_gl_drift(limit=limit)


# =============================================================================
# Grille multimodale (Sprint 15+, 2026-06-19) — Axe 1
# =============================================================================
# Vue matérialisée refresh toutes les 10 min côté DAG, cache Streamlit TTL 60s
# (= 1 cycle de refresh) pour éviter les rafales côté dashboard.
# =============================================================================


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_multimodal_grid(limit: int = 5000) -> pd.DataFrame:
    """Grille multimodale temps réel (Sprint 15+, 2026-06-19).

    Vue matérialisée ``gold.mv_multimodal_grid`` : trafic + TCL + Vélov +
    météo fusionnés sur grille 0.01°. TTL 60s = 1 cycle de refresh DAG.
    """
    return dl.load_multimodal_grid(limit=limit)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_multimodal_grid_diagnosis_counts() -> pd.DataFrame:
    """Distribution des diagnostics dominants (Sprint 15+, 2026-06-19).

    Pour le bandeau KPI du widget ``multimodal_heatmap`` : compte les
    cellules par diagnostic dominant.
    """
    return dl.load_multimodal_grid_diagnosis_counts()


# =============================================================================
# Bus × trafic spatialisé (Sprint 15+, Axe 3 — migration 18)
# =============================================================================


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_bus_traffic_spatial(
    line_ref: str | None = None, limit: int = 5000
) -> pd.DataFrame:
    """Corrélation bus × trafic spatialisée (Sprint 15+, Axe 3).

    MV ``gold.mv_bus_traffic_spatial`` : JOIN spatial 0.001° (~100 m).
    TTL 60s = 1 cycle de refresh DAG (*/15 min).
    """
    return dl.load_bus_traffic_spatial(line_ref=line_ref, limit=limit)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_bus_traffic_spatial_diagnosis_counts(
    line_ref: str | None = None,
) -> pd.DataFrame:
    """Distribution diagnostics spatialisés (Sprint 15+, Axe 3)."""
    return dl.load_bus_traffic_spatial_diagnosis_counts(line_ref=line_ref)


# =============================================================================
# Score santé réseau (Sprint 15+, Axe 5 — migration 019)
# =============================================================================


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_network_health_score() -> pd.DataFrame:
    """Score de santé réseau 0-100 temps réel (Sprint 15+, Axe 5).

    Fonction SQL ``gold.fn_network_health_score()`` — pas de MV, calcul
    live. TTL 30s car c'est le KPI de synthèse exécutive.
    """
    return dl.load_network_health_score()


# =============================================================================
# Transport en commun (Sprint 14, 2026-06-19)
# =============================================================================


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_transit_itinerary(origin: str, destination: str) -> dict | None:
    """Itinéraire TC entre 2 lieux (routing référentiel, 21 lieux emblématiques).

    Args typés explicitement (str, pas ``*args``) pour garantir le hashage
    Streamlit correct.

    Returns:
        Dict sérialisable (cf. ``load_transit_itinerary``) ou ``None`` si pas
        de trajet possible (O == D, lieu inexistant, etc.).
    """
    return dl.load_transit_itinerary(origin=origin, destination=destination)


# =============================================================================
# Sprint 15+ (2026-06-19) — Comparateur de modes Usager (Phase 1 + Phase 2)
# =============================================================================


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_car_itinerary(
    origin_lon: float,
    origin_lat: float,
    dest_lon: float,
    dest_lat: float,
    origin_label: str,
    dest_label: str,
    horizon_minutes: int = 60,
) -> dict | None:
    """Itinéraire voiture traffic-aware — wrapper cache Streamlit.

    Args typés explicitement (floats + str) pour garantir le hashage
    Streamlit correct (``@st.cache_data`` ne hash pas correctement les
    tuples nommés via *args/**kwargs).

    Sprint 15+ (2026-06-19) : ajouté pour le comparateur de modes Usager
    (Phase 1 + Phase 2). Voir ``docs/SPEC_COMPARATEUR_MODES_USAGER.md``.
    """
    return dl.load_car_itinerary(
        origin_lon=origin_lon,
        origin_lat=origin_lat,
        dest_lon=dest_lon,
        dest_lat=dest_lat,
        origin_label=origin_label,
        dest_label=dest_label,
        horizon_minutes=horizon_minutes,
    )


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_velov_itinerary(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    origin_label: str,
    dest_label: str,
) -> dict | None:
    """Itinéraire Vélov + marche — wrapper cache Streamlit.

    Args typés explicitement pour le hashage Streamlit correct.
    Sprint 15+ (2026-06-19) : ajouté pour le comparateur de modes Usager.
    """
    return dl.load_velov_itinerary(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        dest_lat=dest_lat,
        dest_lon=dest_lon,
        origin_label=origin_label,
        dest_label=dest_label,
    )


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_mode_impact(mode: str, distance_km: float, is_congested: bool = False) -> dict:
    """Cache l'impact CO2/coût pour un mode.

    Pur Python (pas de DB) — module-level cache léger via Streamlit pour
    homogénéïté avec les autres wrappers et permettre au cache de se vider
    via ``clear_all_caches()`` lors d'un refresh manuel.

    Sprint 15+ (2026-06-19) : ajouté pour ``render_mode_summary()`` et
    ``render_mode_comparison()``. L'impact ne dépend que de (mode, distance,
    is_congested) — hashable, cache efficace.
    """
    from src.routing.eco_calculator import calculate_impact

    return dict(
        calculate_impact(
            mode=mode,
            distance_km=distance_km,
            is_congested=is_congested,
        ),
    )


def clear_all_caches() -> None:
    """Vide tous les caches Streamlit (utilisable depuis un bouton 'refresh')."""
    st.cache_data.clear()
