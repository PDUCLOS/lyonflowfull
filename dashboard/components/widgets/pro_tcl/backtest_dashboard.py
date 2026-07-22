"""Widget — Backtest Dashboard (XGBoost vs TomTom oracle).

 Axe A (2026-06-20) — Validation modèle cross-source.
Compare les prédictions XGBoost H+1h (gold.trafic_predictions) avec les
observations TomTom Traffic Flow (GPS flottes, gold.v_tomtom_traffic_live).

Source : ``gold.mv_xgb_vs_tomtom`` (migration 020, matérialisée) +
``gold.v_xgb_accuracy_summary`` (vue simple, KPIs agrégés par heure).

Affiche :
1. **4 KPI cards** (bandeau) : MAE, MAPE, P90, paires validées (24h).
2. **Scatter plot** : TomTom (x) vs XGBoost (y), colorisé par accuracy_band.
3. **Courbe MAE temporelle** : MAE par heure sur 7 jours + bande seuil 10 km/h.
4. **Distribution accuracy** : bar chart accurate/acceptable/poor.
5. **Table top 10 pires prédictions** : trié par error_abs_kmh DESC.

Cible : Pro_7_Model_Monitoring (Pro TCL). À envelopper avec
``deferred_render()`` ) — coût élevé (3 Plotly + 1 MV refresh).

Si PostgreSQL indispo → fail loud via DashboardDataError.
Si MV vide (TomTom pas encore collecté ou pas de paires dans la fenêtre) →
message d'info, pas d'erreur (c'est un état valide en bootstrap).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.a11y import plotly_with_alt
from dashboard.components.data_cache import cached_xgb_accuracy_summary, cached_xgb_vs_tomtom
from dashboard.components.error_display import show_error
from dashboard.components.loading_state import loading_wrapper
from dashboard.components.plotly_theme import apply_lyf_theme
from src.data.exceptions import DashboardDataError

# Seuils d'accuracy (cf SPEC_SPRINT_16.md §A.1)
MAE_GREEN_THRESHOLD = 5.0  # km/h — accurate
MAE_YELLOW_THRESHOLD = 15.0  # km/h — acceptable au-delà
MAE_ALERT_THRESHOLD = 10.0  # km/h — bande grise sur la courbe temporelle

# Couleurs accuracy_band
_BAND_COLORS = {
    "accurate": "#4CAF50",  # vert
    "acceptable": "#FF9800",  # orange
    "poor": "#F44336",  # rouge
}


def _compute_kpis(pairs: pd.DataFrame) -> dict:
    """Calcule les 4 KPIs du bandeau depuis les paires XGBoost/TomTom.

    Returns:
        Dict avec mae_kmh, mape_pct, p90_kmh, n_pairs.
    """
    if pairs.empty:
        return {"mae_kmh": 0.0, "mape_pct": 0.0, "p90_kmh": 0.0, "n_pairs": 0}
    mae = float(pairs["error_abs_kmh"].mean())
    mape = (
        float(pairs["error_pct"].dropna().mean())
        if "error_pct" in pairs.columns and not pairs["error_pct"].dropna().empty
        else 0.0
    )
    p90 = float(pairs["error_abs_kmh"].quantile(0.9))
    return {
        "mae_kmh": round(mae, 2),
        "mape_pct": round(mape, 1),
        "p90_kmh": round(p90, 2),
        "n_pairs": len(pairs),
    }


def _scatter_xgb_vs_tomtom(pairs: pd.DataFrame) -> go.Figure:
    """Scatter Plotly TomTom (x) vs XGBoost (y), colorisé par accuracy_band."""
    fig = go.Figure()
    if pairs.empty:
        fig.add_annotation(
            text="Aucune paire (XGBoost, TomTom) à afficher",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    for band in ("accurate", "acceptable", "poor"):
        subset = pairs[pairs["accuracy_band"] == band]
        if subset.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=subset["tomtom_speed_kmh"],
                y=subset["xgb_speed_kmh"],
                mode="markers",
                name=f"{band} ({len(subset)})",
                marker={
                    "color": _BAND_COLORS[band],
                    "size": 6,
                    "opacity": 0.6,
                },
                customdata=subset[["axis_key", "error_abs_kmh", "tomtom_confidence"]].values,
                hovertemplate=(
                    "<b>axis_key</b>: %{customdata[0]}<br>"
                    "TomTom: %{x} km/h<br>"
                    "XGBoost: %{y} km/h<br>"
                    "|Δ|: %{customdata[1]} km/h<br>"
                    "TomTom confidence: %{customdata[2]:.2f}"
                    "<extra></extra>"
                ),
            )
        )

    # Ligne y=x (prédiction parfaite)
    if not pairs.empty:
        max_speed = max(
            float(pairs["tomtom_speed_kmh"].max()),
            float(pairs["xgb_speed_kmh"].max()),
        )
        fig.add_trace(
            go.Scatter(
                x=[0, max_speed],
                y=[0, max_speed],
                mode="lines",
                name="y=x (parfait)",
                line={"color": "#9E9E9E", "dash": "dash", "width": 1},
                hoverinfo="skip",
            )
        )

    fig.update_layout(
        title="XGBoost H+1h vs TomTom Flow (dernières 24h)",
        xaxis_title="TomTom speed (km/h) — oracle",
        yaxis_title="XGBoost speed (km/h) — prédiction",
        height=450,
        template=LYF_TEMPLATE,
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.25},
    )
    apply_lyf_theme(fig)
    return fig
    return fig


def _mae_temporal_chart(summary: pd.DataFrame) -> go.Figure:
    """Courbe MAE par heure sur 7 jours + bande seuil 10 km/h."""
    fig = go.Figure()
    if summary.empty:
        fig.add_annotation(
            text="Aucune donnée historique (7 derniers jours)",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        return fig

    # Trier par heure croissante pour la courbe
    s = summary.sort_values("hour_bucket", ascending=True)
    fig.add_trace(
        go.Scatter(
            x=s["hour_bucket"],
            y=s["mae_kmh"],
            mode="lines+markers",
            name="MAE (km/h)",
            line={"color": "#1976D2", "width": 2},
            marker={"size": 5},
            hovertemplate="<b>%{x}</b><br>MAE: %{y:.2f} km/h<extra></extra>",
        )
    )
    # Bande seuil "acceptable" (< 10 km/h)
    fig.add_hline(
        y=MAE_ALERT_THRESHOLD,
        line_dash="dash",
        line_color="#FF9800",
        annotation_text=f"Seuil alerte {MAE_ALERT_THRESHOLD:.0f} km/h",
        annotation_position="right",
    )
    fig.update_layout(
        title="MAE temporelle (7 derniers jours)",
        xaxis_title="Heure",
        yaxis_title="MAE (km/h)",
        height=350,
        template=LYF_TEMPLATE,
    )
    apply_lyf_theme(fig)
    return fig


def _accuracy_distribution(pairs: pd.DataFrame) -> go.Figure:
    """Bar chart distribution accuracy_band (accurate / acceptable / poor)."""
    counts = pairs["accuracy_band"].value_counts().reindex(["accurate", "acceptable", "poor"], fill_value=0)
    fig = go.Figure(
        go.Bar(
            x=counts.index.tolist(),
            y=counts.values.tolist(),
            marker_color=[_BAND_COLORS[b] for b in counts.index],
            text=counts.values.tolist(),
            textposition="auto",
        )
    )
    fig.update_layout(
        title="Distribution accuracy_band (24h)",
        xaxis_title="Bande",
        yaxis_title="Nombre de paires",
        height=300,
        template=LYF_TEMPLATE,
    )
    apply_lyf_theme(fig)
    return fig


def render_backtest_dashboard(hours_pairs: int = 24, hours_summary: int = 168) -> None:
    with st.popover("MAE vs MAPE ?"):
        st.markdown(
            "Le **MAE (Mean Absolute Error)** mesure l'erreur moyenne en km/h "
            "entre les prédictions XGBoost et l'oracle TomTom. Le **MAPE** "
            "exprime la même erreur en % relatif. **Plus c'est bas, plus le "
            "modèle colle à la réalité**. Référence cible : MAE < 8 km/h."
        )
    with loading_wrapper("Chargement Backtest dashboard…", "⏳"):
        """Render le dashboard complet de backtest XGBoost vs TomTom.

    Args:
        hours_pairs: fenêtre temporelle pour les paires (scatter + KPIs), défaut 24h.
        hours_summary: fenêtre temporelle pour le summary (courbe MAE), défaut 168h.
    """
    try:
        pairs = cached_xgb_vs_tomtom(hours=hours_pairs, limit=500)
        summary = cached_xgb_accuracy_summary(hours=hours_summary)
    except DashboardDataError as e:
        show_error("db_down", f"Backtest indisponible : {e}")
        return

    if pairs.empty:
        st.info(
            f"Aucune paire (XGBoost, TomTom) sur les dernières {hours_pairs}h. "
            "Vérifie que le DAG ``refresh_xgb_vs_tomtom`` tourne et que TomTom "
            "collecte bien (cf. ``gold.v_tomtom_traffic_live``)."
        )
        return

    # ── 1. KPIs (4 cards HTML inline) ──────────────────────────────────────
    k = _compute_kpis(pairs)
    kpi_mae_color = (
        "#4CAF50"
        if k["mae_kmh"] < MAE_GREEN_THRESHOLD
        else "#FF9800"
        if k["mae_kmh"] < MAE_YELLOW_THRESHOLD
        else "#F44336"
    )
    kpi_mape_color = "#4CAF50" if k["mape_pct"] < 15 else "#FF9800" if k["mape_pct"] < 30 else "#F44336"
    kpi_p90_color = (
        "#4CAF50"
        if k["p90_kmh"] < MAE_YELLOW_THRESHOLD
        else "#FF9800"
        if k["p90_kmh"] < MAE_YELLOW_THRESHOLD * 2
        else "#F44336"
    )
    kpi_n_color = "#4CAF50" if k["n_pairs"] >= 50 else "#FF9800" if k["n_pairs"] >= 10 else "#F44336"
    st.markdown(
        f"""
        <div style="display:flex;gap:0.8rem;margin-bottom:1rem;flex-wrap:wrap;">
            <div class="lyonflow-card" style="flex:1;min-width:180px;padding:0.8rem;border-left:4px solid {kpi_mae_color};">
                <div class="lyf-sublabel">MAE (km/h)</div>
                <div style="font-size:1.8rem;font-weight:700;color:{kpi_mae_color};">{k["mae_kmh"]:.2f}</div>
            </div>
            <div class="lyonflow-card" style="flex:1;min-width:180px;padding:0.8rem;border-left:4px solid {kpi_mape_color};">
                <div class="lyf-sublabel">MAPE (%)</div>
                <div style="font-size:1.8rem;font-weight:700;color:{kpi_mape_color};">{k["mape_pct"]:.1f}</div>
            </div>
            <div class="lyonflow-card" style="flex:1;min-width:180px;padding:0.8rem;border-left:4px solid {kpi_p90_color};">
                <div class="lyf-sublabel">P90 erreur (km/h)</div>
                <div style="font-size:1.8rem;font-weight:700;color:{kpi_p90_color};">{k["p90_kmh"]:.2f}</div>
            </div>
            <div class="lyonflow-card" style="flex:1;min-width:180px;padding:0.8rem;border-left:4px solid {kpi_n_color};">
                <div class="lyf-sublabel">Paires validées (n)</div>
                <div style="font-size:1.8rem;font-weight:700;color:{kpi_n_color};">{k["n_pairs"]}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── 2. Scatter XGBoost vs TomTom ────────────────────────────────────────
    plotly_with_alt(_scatter_xgb_vs_tomtom(pairs), use_container_width=True)

    st.markdown("---")

    # ── 3. Courbe MAE temporelle ────────────────────────────────────────────
    plotly_with_alt(_mae_temporal_chart(summary), use_container_width=True)

    st.markdown("---")

    # ── 4. Distribution accuracy + Top 10 ───────────────────────────────────
    col_pie, col_table = st.columns([1, 2])
    with col_pie:
        plotly_with_alt(_accuracy_distribution(pairs), use_container_width=True)
    with col_table:
        st.markdown("##### Top 10 pires prédictions")
        top10 = pairs.nlargest(10, "error_abs_kmh")[
            ["axis_key", "xgb_speed_kmh", "tomtom_speed_kmh", "error_abs_kmh", "accuracy_band", "calculated_at"]
        ].rename(
            columns={
                "axis_key": "Canal",
                "xgb_speed_kmh": "XGBoost (km/h)",
                "tomtom_speed_kmh": "TomTom (km/h)",
                "error_abs_kmh": "|Δ| (km/h)",
                "accuracy_band": "Bande",
                "calculated_at": "Date",
            }
        )
        st.dataframe(top10, use_container_width=True, hide_index=True)
