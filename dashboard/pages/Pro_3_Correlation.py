"""Page Pro TCL — Corrélation bus × trafic (USP technique)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.deferred_widget import deferred_render
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.pro_tcl import (
    render_bus_traffic_spatial,
    render_cause_analysis,
    render_coherence_scatter,
    render_correlation_matrix,
    render_line_selector,
    render_meteo_impact,
    render_modal_shift_alert,
    render_multimodal_heatmap,
    render_propagation_map,
    render_segment_table,
)

st.set_page_config(
    page_title="Corrélation bus × trafic — Pro TCL · LyonFlowFull",
    page_icon="🔗",
    layout="wide",
)

apply_persona_guard(expected_persona="pro_tcl")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

st.title("Corrélation bus × trafic routier")
render_data_status_banner()

st.caption("L'USP technique de LyonFlowFull — croise retards bus et congestion routière par segment.")

st.markdown("---")

# Sélecteur de ligne
selected_lines = render_line_selector(multiselect=True, key_suffix="corr")
target_line = selected_lines[0] if selected_lines else None

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "Bus × Trafic",
        "Spatial & TomTom",
        "Multimodal",
        "Propagation",
    ]
)


def _render_segments_and_cause(line_id: str | None) -> None:
    """Render grouped : table des segments + analyse causale."""
    from dashboard.components.data_cache import cached_infra_bottlenecks

    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown("##### Table des segments")
        render_segment_table(line_id=line_id, height=350)
    with col2:
        st.markdown("##### Analyse causale (1er segment problématique)")
        bn_df = cached_infra_bottlenecks(top=500)
        if not bn_df.empty:
            if line_id:
                bn_df = bn_df[bn_df["line_ref"] == line_id]
            infra_rows = bn_df[bn_df["diagnosis"] == "infra"] if "diagnosis" in bn_df.columns else bn_df.iloc[:0]
            if not infra_rows.empty:
                row = infra_rows.iloc[0]
                delay_s = row.get("bus_delay_seconds", 0) or 0
                render_cause_analysis(
                    {
                        "line_id": row.get("line_ref", "?"),
                        "name": row.get("segment_id", "—"),
                        "bus_state": "delayed" if delay_s > 120 else "on_time",
                        "traffic_state": "jammed" if (row.get("traffic_speed_kmh", 50) or 50) < 25 else "fluid",
                        "diagnosis": row.get("diagnosis", "ok"),
                        "delay_min": round(delay_s / 60, 1),
                    }
                )
            else:
                render_cause_analysis(None)
        else:
            render_cause_analysis(None)


with tab1:
  # P1 — Les 3 widgets de Tab1 (matrice corrélation +
    # segment_table + cause_analysis) sont en ``button-gate`` au lieu de
    # rendu systématique à l'ouverture. Le simple ``st.tabs`` ne différait
    # pas le calcul (cf. deferred_widget.py:3) — l'user devait attendre
    # 0.5-2s de cached_* lookups en pure perte s'il n'ouvrait pas le tab.
    # Maintenant : 3 boutons "Charger" explicites, comme les autres tabs.

    # 1) Matrice de corrélation
    deferred_render(
        "correlation_matrix",
        "Charger la matrice de corrélation bus × trafic",
        render_correlation_matrix,
        line_id=target_line,
        button_icon="📊",
    )

    st.markdown("---")

    # 2) Table des segments + 3) Analyse causale — groupés dans 1 seul
    # button-gate (les 2 partagent cached_infra_bottlenecks, factoriser
    # évite 2 hits DB).
    deferred_render(
        "segments_and_cause",
        "Charger la table des segments + analyse causale",
        _render_segments_and_cause,
        line_id=target_line,
        button_icon="🔍",
    )

with tab2:
  # (2026-06-19) — Axe 3 du SPEC_OPTIMISATION_INTERDEPENDANCES
    # Corrélation bus × trafic SPATIALISÉE (JOIN par zone 0.001° ≈ 100 m).
    # Coexiste avec la matrice globale (Option B, non-breaking).
  # audit (P0-1) : button-gate pour éviter re-render à chaque
    # auto-refresh 30s (coût estimé 0.5-2s par widget).
    deferred_render(
        "bus_traffic_spatial",
        "Charger la corrélation spatiale bus × trafic",
        render_bus_traffic_spatial,
        line_id=target_line,
        button_icon="🚌",
    )

    st.markdown("---")

  # (2026-06-18) — Cross-validation TomTom ↔ Grand Lyon
    # Détecte les capteurs HS (delta > 20 km/h vs source indépendante GPS flottes).
  # audit (P0-1) : button-gate, 2 requêtes PostGIS + 3 charts Plotly.
    deferred_render(
        "coherence_scatter",
        "Charger la cohérence TomTom × Grand Lyon",
        render_coherence_scatter,
        button_icon="🎯",
    )

with tab3:
  # (2026-06-19) — Axe 1 du SPEC_OPTIMISATION_INTERDEPENDANCES
    # Grille multimodale 0.01° (trafic + TCL + Vélov + météo fusionnés) — carte
    # chaleur avec score 0-10 et diagnostic dominant par cellule. Vue
    # gold.mv_multimodal_grid (migration 17), refresh DAG */10 min.
  # audit (P0-1) : button-gate, le widget le plus lourd (Folium HTML).
    deferred_render(
        "multimodal_heatmap",
        "Charger la vue multimodale grille 0.01°",
        render_multimodal_heatmap,
        button_icon="🌐",
    )

    st.markdown("---")

  # (2026-06-20) — Axe 7 du SPEC_OPTIMISATION_INTERDEPENDANCES
    # Météo comme variable d'interaction : tableau comparatif 5 bandes × 3 modes
    # avec delta vs baseline "beau temps". Vue gold.mv_meteo_impact (migration
    # 022), refresh quotidien 04h30 par dags/maintenance/refresh_meteo_impact.py.
    # Button-gate (cohérent avec les autres widgets de la page).
    deferred_render(
        "meteo_impact",
        "Charger l'impact météo sur les 3 modes",
        render_meteo_impact,
        button_icon="🌤",
    )

    st.markdown("---")

  # (2026-06-20) — Axe 4 du SPEC_OPTIMISATION_INTERDEPENDANCES
    # Vélov ↔ TC report modal : pour chaque station Vélov < 300m d'une zone
    # TC, calcule un z-score vélos dispos. z < -2 = alarme probable (incident
    # TC → usagers basculent vers Vélov). Vue gold.mv_velov_transit_coupling
    # (migration 023), refresh */15 min par dags/maintenance/refresh_velov_transit_coupling.py.
    deferred_render(
        "modal_shift_alert",
        "Charger l'alerte report modal Vélov ↔ TC",
        render_modal_shift_alert,
        button_icon="🔄",
    )

with tab4:
  # (2026-06-20) — Axe 2 du SPEC_OPTIMISATION_INTERDEPENDANCES
    # Propagation de congestion : carte Folium avec AntPath animées montrant
    # comment la congestion se propage entre capteurs adjacents (K=2 grid).
    # CORR cross-lagged calculée en Python depuis gold.traffic_features_live
    # (6h × 5min), direction = lag qui maximise |r|. Vue
    # gold.mv_congestion_propagation_pairs (migration 024 v3), refresh DAG
    # */30 min par dags/maintenance/refresh_congestion_propagation.py.
    # Button-gate (cohérent avec les autres widgets lourds de la page) car
    # le calcul CORR peut prendre 3-5s sur 5k paires.
    deferred_render(
        "propagation_map",
        "Charger la carte de propagation de congestion",
        render_propagation_map,
        button_icon="🌊",
    )

st.caption(
    "Corrélation bus × trafic · Données : SIRI Lite + boucles Grand Lyon. "
    "Corrélation spatialisée · JOIN zone 0.001° (~100 m) dans "
    "gold.mv_bus_traffic_spatial (migration 18, refresh */15). "
    "Cohérence TomTom × GL · TomTom Flow + jointure spatiale "
    "gold.channels_ref < 200 m (PostGIS ST_DWithin). "
    "Grille multimodale · fusion gold.traffic_features_live × "
    "gold.tcl_vehicle_realtime × silver.velov_clean × silver.meteo_hourly "
    "sur gold.mv_multimodal_grid (refresh */10). "
    "Impact météo · 5 bandes × 3 modes + delta vs fair weather dans "
    "gold.mv_meteo_impact (migration 022, refresh quotidien 04h30). "
    "Report modal Vélov ↔ TC · z-score vélos dispos par station < 300m "
    "d'une zone TC dans gold.mv_velov_transit_coupling (migration 023, "
    "refresh */15 min). "
    "Propagation de congestion · carte AntPath entre paires de capteurs "
    "adjacents K=2 grid, CORR cross-laggée Python sur 6h glissantes "
    "depuis gold.mv_congestion_propagation_pairs (migration 024 v3, "
    "refresh */30 min)."
)
