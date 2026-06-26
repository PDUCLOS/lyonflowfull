"""Widget — Carte chaleur multimodale (Axe 1, , 2026-06-19).

Fusionne sur une seule carte Folium les 3 modes de transport temps réel
Lyon + la météo, agrégés sur une grille spatiale 0.01° (~1 km) :

* **Trafic routier** (``gold.traffic_features_live``) : vitesse moyenne,
  % congestion (speed_kmh < 25).
* **TCL bus/tram/métro** (``gold.tcl_vehicle_realtime``) : retard moyen
  par véhicule, % véhicules en retard (delay_seconds > 60).
* **Vélov** (``silver.velov_clean``) : vélos et docks disponibles par
  cellule (15 min de fraîcheur GBFS).
* **Météo** (``silver.meteo_hourly``) : température + précipitations
  (CROSS JOIN sur la dernière mesure horaire).

Score multimodal (0-10, plus haut = plus saturé) :

    score = clamp(0.5 × pct_congestion / 10
                + 0.5 × pct_delayed / 10
                - bonus_vélov)   ; bonus_vélov = 1.0 si vélos ≥ 5

Diagnostic dominant (5 états) :
    * saturated       : pct_congestion > 60 ET pct_delayed > 40
    * road_congested  : pct_congestion > 60
    * transit_delayed : pct_delayed > 40
    * velov_scarce    : vélos < 3 ET ≥ 1 station
    * ok              : reste

Affiche :
1. **Bandeau KPI** : compteurs par diagnostic (saturated / tendu / fluide)
2. **Carte Folium** : rectangles colorés par ``score_multimodal``, popup
   avec détail trafic + TCL + Vélov + météo pour chaque cellule.
3. **Tableau top 15 cellules saturées** : triées par score DESC.

Si PostgreSQL indispo → fail loud via DashboardDataError. Si vue vide
(DAG refresh pas encore passé) → message d'attente explicite.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.a11y import folium_with_alt
from dashboard.components.data_cache import (
    cached_multimodal_grid,
    cached_multimodal_grid_diagnosis_counts,
)
from dashboard.components.error_display import show_error
from dashboard.components.loading_state import loading_wrapper
from src.data.exceptions import DashboardDataError

# Libellés FR pour les diagnostics (cohérent avec labels.py)
DIAGNOSIS_LABELS = {
    "ok": "Fluide",
    "road_congested": "Tendu (route)",
    "transit_delayed": "Tendu (TC)",
    "saturated": "Saturé",
    "velov_scarce": "Vélov scarce",
}

# Couleurs par diagnostic (cohérent avec couleurs bottlenecks carte Folium)
DIAGNOSIS_COLORS = {
    "ok": "#4CAF50",  # vert
    "road_congested": "#FF9800",  # orange
    "transit_delayed": "#FFC107",  # ambre
    "saturated": "#F44336",  # rouge
    "velov_scarce": "#9C27B0",  # violet
}

# Seuils du score (cohérent avec spec section 2.4)
SCORE_THRESHOLDS = {
    "saturated": 7.0,
    "tendu": 4.0,
}


def _diagnosis_counts(diag_df: pd.DataFrame) -> dict[str, int]:
    """Compte les cellules par diagnostic dominant (0 si absent)."""
    counts = dict.fromkeys(DIAGNOSIS_LABELS, 0)
    if diag_df.empty or "diagnosis" not in diag_df.columns:
        return counts
    for d, n in diag_df["diagnosis"].value_counts().items():
        if d in counts:
            counts[d] = int(n)
    return counts


def _score_to_color(score: float) -> str:
    """Score 0-10 → couleur hex.

    Cohérent avec la sémantique du spec : saturé (rouge) / tendu (orange) /
    fluide (vert).
    """
    if pd.isna(score):
        return "#9E9E9E"  # gris (no data)
    if score >= SCORE_THRESHOLDS["saturated"]:
        return DIAGNOSIS_COLORS["saturated"]
    if score >= SCORE_THRESHOLDS["tendu"]:
        return DIAGNOSIS_COLORS["road_congested"]
    return DIAGNOSIS_COLORS["ok"]


def _popup_html(row: pd.Series) -> str:
    """HTML pour le popup Folium d'une cellule (détail multimodal)."""
    lat = float(row.get("lat", 0) or 0)
    lon = float(row.get("lon", 0) or 0)
    score = float(row.get("score_multimodal", 0) or 0)
    diagnosis = str(row.get("diagnosis", "ok"))
    diagnosis_label = DIAGNOSIS_LABELS.get(diagnosis, diagnosis)

    # Trafic
    avg_speed = float(row.get("avg_speed_kmh", 0) or 0)
    pct_cong = float(row.get("pct_congestion", 0) or 0)
    n_sensors = int(row.get("n_sensors", 0) or 0)

    # TCL
    avg_delay = float(row.get("avg_delay_sec", 0) or 0)
    pct_del = float(row.get("pct_delayed", 0) or 0)
    n_veh = int(row.get("n_vehicles", 0) or 0)

    # Vélov
    bikes = int(row.get("bikes_available", 0) or 0)
    docks = int(row.get("docks_available", 0) or 0)
    n_st = int(row.get("n_stations", 0) or 0)

    # Météo
    temp = row.get("temperature_c")
    rain = row.get("rain_mm")
    temp_str = f"{float(temp):.1f}°C" if pd.notna(temp) else "—"
    rain_str = f"{float(rain):.1f} mm" if pd.notna(rain) else "—"

    return (
        f"<div style='font-family:system-ui;min-width:220px;'>"
        f"<div style='font-weight:700;font-size:1.05rem;color:#1a1a1a;'>"
        f"({lat:.2f}, {lon:.2f})</div>"
        f"<div style='margin:0.3rem 0;color:{_score_to_color(score)};"
        f"font-weight:600;'>Score {score:.1f}/10 · {diagnosis_label}</div>"
        f"<hr style='margin:0.4rem 0;'>"
        f"<div style='font-size:0.85rem;'>"
        f"<b>🚗 Trafic</b> : {avg_speed:.0f} km/h ({pct_cong:.0f}% congestion, "
        f"{n_sensors} capteur{'s' if n_sensors > 1 else ''})<br/>"
        f"<b>🚌 TCL</b> : retard {avg_delay:.0f}s ({pct_del:.0f}% en retard, "
        f"{n_veh} véhicule{'s' if n_veh > 1 else ''})<br/>"
        f"<b>🚲 Vélov</b> : {bikes} vélos / {docks} docks "
        f"({n_st} station{'s' if n_st > 1 else ''})<br/>"
        f"<b>🌤 Météo</b> : {temp_str}, pluie {rain_str}"
        f"</div></div>"
    )


def _build_folium_map(df: pd.DataFrame) -> folium.Map:  # type: ignore[name-defined]
    """Construit la carte Folium avec rectangles colorés par cellule."""
    import folium
    from folium.vector_layers import Rectangle

    # Centre Lyon par défaut (Part-Dieu)
    m = folium.Map(
        location=[45.760, 4.835],
        zoom_start=12,
        tiles="CartoDB positron",
        control_scale=True,
    )

    # Rectangle par cellule (0.01° ≈ 1 km). On dessine un Rectangle avec
    # bounds = (lat - 0.005, lon - 0.005) → (lat + 0.005, lon + 0.005).
    half = 0.005
    for _, row in df.iterrows():
        lat = float(row.get("lat", 0) or 0)
        lon = float(row.get("lon", 0) or 0)
        if lat == 0 and lon == 0:
            continue  # skip cellules hors zone
        score = float(row.get("score_multimodal", 0) or 0)
        color = _score_to_color(score)
        popup = folium.Popup(_popup_html(row), max_width=320)
        Rectangle(
            bounds=[[lat - half, lon - half], [lat + half, lon + half]],
            color=color,
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.55,
            popup=popup,
        ).add_to(m)

    return m


def _render_kpi_banner(counts: dict[str, int], n_total: int) -> None:
    """Bandeau 4 KPI cards : Saturé / Tendu (route) / Tendu (TC) / OK."""
    n_saturated = counts.get("saturated", 0)
    n_road = counts.get("road_congested", 0)
    n_tc = counts.get("transit_delayed", 0)
    n_ok = counts.get("ok", 0)
    n_velov = counts.get("velov_scarce", 0)

    # Regroupe "tendu" = road_congested + transit_delayed (sémantique widget)
    n_tendu = n_road + n_tc

    cards = [
        ("Saturé", n_saturated, DIAGNOSIS_COLORS["saturated"], "Trafic + TC congestionnés"),
        ("Tendu", n_tendu, DIAGNOSIS_COLORS["road_congested"], f"Route {n_road} · TC {n_tc}"),
        ("Vélov scarce", n_velov, DIAGNOSIS_COLORS["velov_scarce"], "Bornes vides ou pleines"),
        ("Fluide", n_ok, DIAGNOSIS_COLORS["ok"], f"Sur {n_total} cellules Lyon"),
    ]

    cols = st.columns(4)
    for col, (label, n, color, sub) in zip(cols, cards):
        with col:
            pct = (n / max(n_total, 1)) * 100
            st.markdown(
                f"""
                <div style="background:var(--bg-card);border-left:4px solid {color};
                            border-radius:6px;padding:0.8rem;margin:0.4rem 0;">
                    <div class="lyf-detail" style="opacity:0.8;">{label}</div>
                    <div style="font-size:1.8rem;font-weight:700;margin:0.2rem 0;">
                        {n} <span style="font-size:0.8rem;font-weight:400;">
                        cellules</span>
                    </div>
                    <div class="lyf-sublabel" style="opacity:0.6;">
                        {pct:.0f}% · {sub}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_top_saturated(df: pd.DataFrame, top_n: int = 15) -> None:
    """Tableau top N cellules saturées (score DESC)."""
    if df.empty or "score_multimodal" not in df.columns:
        st.info("Aucune cellule à analyser.")
        return

    plot_df = df[df["score_multimodal"] >= SCORE_THRESHOLDS["tendu"]].copy()
    if plot_df.empty:
        st.info(
            f"Aucune cellule au-dessus du seuil 'tendu' "
            f"(score ≥ {SCORE_THRESHOLDS['tendu']:.0f}). "
            "Le réseau est globalement fluide."
        )
        return

    plot_df = plot_df.nlargest(top_n, "score_multimodal")

    rows = []
    for _, r in plot_df.iterrows():
        diagnosis = str(r.get("diagnosis", "ok"))
        rows.append(
            {
                "Lat": float(r.get("lat", 0)),
                "Lon": float(r.get("lon", 0)),
                "Score": float(r.get("score_multimodal", 0)),
                "Diagnostic": DIAGNOSIS_LABELS.get(diagnosis, diagnosis),
                "Vitesse (km/h)": float(r.get("avg_speed_kmh", 0) or 0),
                "% congestion": float(r.get("pct_congestion", 0) or 0),
                "Retard TCL (s)": float(r.get("avg_delay_sec", 0) or 0),
                "% TCL retard": float(r.get("pct_delayed", 0) or 0),
                "Vélov dispo": int(r.get("bikes_available", 0) or 0),
                "Capteurs": int(r.get("n_sensors", 0) or 0),
            }
        )
    df_disp = pd.DataFrame(rows)
    df_disp = df_disp.round(
        {"Score": 2, "Vitesse (km/h)": 1, "% congestion": 1, "Retard TCL (s)": 0, "% TCL retard": 1}
    )

    def _color_diag(val: str) -> str:
        # Reverse lookup label → diagnosis key
        for key, label in DIAGNOSIS_LABELS.items():
            if val == label:
                color = DIAGNOSIS_COLORS.get(key, "#9E9E9E")
                return f"background-color: {color}; color: white; font-weight: 600;"
        return ""

    st.dataframe(
        df_disp.style.map(_color_diag, subset=["Diagnostic"]),
        use_container_width=True,
        hide_index=True,
    )


def render_multimodal_heatmap(height: int = 500) -> None:
    with loading_wrapper("Chargement Multimodal heatmap…", "⏳"):
        """Affiche la carte chaleur multimodale (Axe 1).

  (2026-06-19). Si DB indispo → fail loud via DashboardDataError.
    Si vue matérialisée pas encore alimentée → message d'attente explicite.
    """
    # Charge données et diagnostics en parallèle (séquentiel ici, ~ rapide)
    try:
        df = cached_multimodal_grid(limit=5000)
        diag_df = cached_multimodal_grid_diagnosis_counts()
    except DashboardDataError as e:
        show_error("db_down", str(e))
        return

    if df.empty or diag_df.empty:
        st.info(
            "Grille multimodale pas encore alimentée. Le DAG "
            "`transform_silver_to_gold` doit tourner (tâche "
            "`refresh_mv_multimodal_grid`, toutes les 10 min). "
            "Causes possibles : (1) DAG en attente de son 1er cycle, "
            "(2) `migration_017_multimodal_grid.sql` non appliquée, "
            "(3) sources Bronze/Silver vides."
        )
        return

    # Bandeau KPI
    counts = _diagnosis_counts(diag_df)
    n_total = sum(counts.values())
    _render_kpi_banner(counts, n_total)

    st.markdown("---")

    # Carte Folium + tableau top saturées
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown(f"##### Carte multimodale Lyon — {n_total} cellules 0.01°")
        fmap = _build_folium_map(df)
        # Folium rendu via folium_with_alt (a11y sr-only + components.html)
        folium_with_alt(
            fmap,
            "Carte chaleur multimodale — score par cellule 1km",
            height=height,
        )
    with col2:
        st.markdown("##### Top cellules saturées / tendues")
        _render_top_saturated(df, top_n=15)

    st.caption(
        "Données : `gold.traffic_features_live` × `gold.tcl_vehicle_realtime` "
        "× `silver.velov_clean` × `silver.meteo_hourly` agrégées sur grille "
        "0.01° (~1 km) dans `gold.mv_multimodal_grid` (migration 17). "
        "Refresh DAG `transform_silver_to_gold` toutes les 10 min. "
        "Score 0-10 : plus haut = plus saturé. Diagnostic dominant : "
        "saturated | road_congested | transit_delayed | velov_scarce | ok."
    )
