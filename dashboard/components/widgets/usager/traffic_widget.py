"""Widget — Trafic routier résumé (vitesse moyenne, bouchons).

Sprint 6 — binding DB Gold via data_loader :
* Si ``traffic=None`` → ``data_loader.cached_traffic()`` tente la DB
  Gold, fallback mock si DB down.
* Le widget reste 100% compatible avec l'ancien contrat (accepte toujours
  un dict ``traffic`` en arg, utilisé en tests / mode démo forcé).
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_traffic


def render_traffic_widget(traffic: dict | None = None) -> None:
    """Affiche le résumé trafic routier.

    Args:
        traffic: dict de données. Si None, tente DB → fallback mock.
    """
    if traffic is None:
        traffic = cached_traffic(force_mock=False)

    avg = traffic.get("average_speed_kmh", 0)
    level = traffic.get("congestion_level", "—")
    level_color = traffic.get("congestion_color", COLORS["text_muted"])
    n_bottlenecks = traffic.get("bottlenecks_count", 0)
    data_source = traffic.get("data_source", "unknown")

    # Bandeau source (transparence)
    if data_source == "db_gold":
        st.caption("🟢 Données temps réel (DB Gold)")
    else:
        st.caption("🟡 Données démo (mock — DB non disponible)")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Vitesse moyenne", f"{avg} km/h")
    with col2:
        st.markdown(
            f"""
            <div style="padding:0.5rem 0;">
                <div style="font-size:0.75rem;opacity:0.6;">État du trafic</div>
                <div style="font-size:1.3rem;font-weight:600;color:{level_color};">
                    {level}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.metric("Bouchons actifs", n_bottlenecks)

    # Prédictions
    st.markdown("##### 🔮 Prédictions")
    preds = traffic.get("predictions", {})
    pred_cols = st.columns(3)
    pred_data = [
        ("H+30min", preds.get("h_plus_30min", {})),
        ("H+1h", preds.get("h_plus_1h", {})),
        ("H+3h", preds.get("h_plus_3h", {})),
    ]
    for col, (label, p) in zip(pred_cols, pred_data):
        if p:
            with col:
                st.markdown(
                    f"""
                    <div class="lyonflow-card" style="text-align:center;padding:0.6rem;">
                        <div style="font-size:0.75rem;opacity:0.6;">{label}</div>
                        <div style="font-size:1.3rem;font-weight:600;">{p.get("average_speed_kmh", 0)} km/h</div>
                        <div style="font-size:0.85rem;">{p.get("congestion_level", "—")}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # Top bouchons
    main_jams = traffic.get("main_jams", [])
    if main_jams:
        with st.expander(f"🚧 Top {len(main_jams)} bouchons", expanded=False):
            for jam in main_jams:
                sev = jam.get("severity", "low")
                color = {
                    "high": COLORS["status_critical"],
                    "medium": COLORS["status_warning"],
                    "low": COLORS["status_ok"],
                }.get(sev, COLORS["text_muted"])
                st.markdown(
                    f"<div style='border-left:3px solid {color};padding-left:8px;margin:4px 0;'>"
                    f"<b>{jam.get('road', '—')}</b> · {jam.get('speed_kmh', 0)} km/h · "
                    f"~{jam.get('delay_min', 0)} min de retard</div>",
                    unsafe_allow_html=True,
                )
