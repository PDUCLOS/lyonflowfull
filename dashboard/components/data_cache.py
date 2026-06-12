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
def cached_traffic(force_mock: bool = False) -> dict[str, Any]:
    return dl.load_traffic(force_mock=force_mock)


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_traffic_timeseries(node_idx: int, hours: int = 4, force_mock: bool = False) -> pd.DataFrame:
    return dl.load_traffic_timeseries(node_idx=node_idx, hours=hours, force_mock=force_mock)


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_velov_stations(force_mock: bool = False) -> list[dict]:
    return dl.load_velov_stations(force_mock=force_mock)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_velov_predictions(horizon_minutes: int = 60, force_mock: bool = False) -> pd.DataFrame:  # Sprint 8+ : focus H+1h
    return dl.load_velov_predictions(horizon_minutes=horizon_minutes, force_mock=force_mock)


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_buses_positions(limit: int = 200, force_mock: bool = False) -> pd.DataFrame:
    return dl.load_buses_positions(limit=limit, force_mock=force_mock)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_bus_delays(line_ref: str | None = None, days: int = 7, force_mock: bool = False) -> pd.DataFrame:
    return dl.load_bus_delays(line_ref=line_ref, days=days, force_mock=force_mock)


# =============================================================================
# Bottlenecks / KPI / synthese
# =============================================================================


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_infra_bottlenecks(top: int = 15, force_mock: bool = False) -> pd.DataFrame:
    return dl.load_infra_bottlenecks(top=top, force_mock=force_mock)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_bottlenecks_summary(force_mock: bool = False) -> pd.DataFrame:
    return dl.load_bottlenecks_summary(force_mock=force_mock)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_bottlenecks_top(force_mock: bool = False) -> list[dict]:
    return dl.load_bottlenecks_top(force_mock=force_mock)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_predictions_vs_actuals(limit: int = 200, force_mock: bool = False) -> pd.DataFrame:
    return dl.load_predictions_vs_actuals(limit=limit, force_mock=force_mock)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_city_synthesis(force_mock: bool = False) -> dict:
    return dl.load_city_synthesis(force_mock=force_mock)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_elu_kpis_dict(force_mock: bool = False) -> dict:
    return dl.load_elu_kpis_dict(force_mock=force_mock)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_line_kpis(line_ids: tuple[str, ...] | None = None, force_mock: bool = False) -> dict:
    line_ids_list = list(line_ids) if line_ids else None
    return dl.load_line_kpis(line_ids=line_ids_list, force_mock=force_mock)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_otp_heatmap_data(force_mock: bool = False) -> pd.DataFrame:
    return dl.load_otp_heatmap_data(force_mock=force_mock)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_correlation_matrix(limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    return dl.load_correlation_matrix(limit=limit, force_mock=force_mock)


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_segments(limit: int = 200, force_mock: bool = False) -> pd.DataFrame:
    return dl.load_segments(limit=limit, force_mock=force_mock)


# =============================================================================
# Meteo / alertes / amenagements
# =============================================================================


@st.cache_data(ttl=TTL_FAST, show_spinner=False)
def cached_weather_hourly(hours: int = 24, force_mock: bool = False) -> pd.DataFrame:
    return dl.load_weather_hourly(hours=hours, force_mock=force_mock)


@st.cache_data(ttl=TTL_REALTIME, show_spinner=False)
def cached_recent_alerts(hours: int = 24, limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    return dl.load_recent_alerts(hours=hours, limit=limit, force_mock=force_mock)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_amenagements_passes(limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    return dl.load_amenagements_passes(limit=limit, force_mock=force_mock)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_kpis_12_months(force_mock: bool = False) -> pd.DataFrame:
    return dl.load_kpis_12_months(force_mock=force_mock)


# =============================================================================
# RGPD
# =============================================================================


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_rgpd_audit(limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    return dl.load_rgpd_audit(limit=limit, force_mock=force_mock)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_rgpd_consents(force_mock: bool = False) -> pd.DataFrame:
    return dl.load_rgpd_consents(force_mock=force_mock)


# =============================================================================
# Referentiel TCL / spatial / MLflow
# =============================================================================


@st.cache_data(ttl=TTL_STATIC, show_spinner=False)
def cached_tcl_lines(force_mock: bool = False) -> list[dict]:
    return dl.load_tcl_lines(force_mock=force_mock)


@st.cache_data(ttl=TTL_STATIC, show_spinner=False)
def cached_lyon_addresses(force_mock: bool = False) -> list[str]:
    return dl.load_lyon_addresses(force_mock=force_mock)


@st.cache_data(ttl=TTL_STATIC, show_spinner=False)
def cached_lyon_addresses_with_coords(force_mock: bool = False) -> list[dict]:
    """Adresses Lyon avec coords GPS (pour cartes, markers)."""
    return dl.load_lyon_addresses_with_coords(force_mock=force_mock)


@st.cache_data(ttl=TTL_STATIC, show_spinner=False)
def cached_spatial_mapping(force_mock: bool = False) -> pd.DataFrame:
    return dl.load_spatial_mapping(force_mock=force_mock)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_traffic_predictions_for_map(horizon_minutes: int = 60, limit: int = 500) -> pd.DataFrame:  # Sprint 8+ : focus H+1h
    """Cache les prédictions trafic pour la carte GNN.

    Args typés explicitement (pas *args/**kwargs) pour garantir le hashage
    correct des arguments par @st.cache_data (sinon UnhashableParamError si
    un caller passe un dict/list/df).
    """
    return dl.load_traffic_predictions_for_map(horizon_minutes=horizon_minutes, limit=limit)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_mlflow_models(force_mock: bool = False) -> list[dict]:
    return dl.load_mlflow_models(force_mock=force_mock)


@st.cache_data(ttl=TTL_SLOW, show_spinner=False)
def cached_mlflow_experiment_summary(force_mock: bool = False) -> dict:
    return dl.load_mlflow_experiment_summary(force_mock=force_mock)


def clear_all_caches() -> None:
    """Vide tous les caches Streamlit (utilisable depuis un bouton 'refresh')."""
    st.cache_data.clear()
