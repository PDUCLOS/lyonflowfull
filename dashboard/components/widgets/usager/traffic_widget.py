"""Widget — Trafic routier résumé (vitesse moyenne, bouchons).

Sprint 8 — binding DB Gold via data_loader (zéro mock) :
* Si ``traffic=None`` → ``data_loader.cached_traffic()`` tente la DB
  Gold. Si DB down, lève ``DashboardDataError`` (fail loud).
* Le widget reste 100% compatible avec l'ancien contrat (accepte toujours
  un dict ``traffic`` en arg, utilisé en tests).
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_traffic
from dashboard.components.loading_state import loading_wrapper


def render_traffic_widget(traffic: dict | None = None) -> None:
    with loading_wrapper("Chargement Traffic widget…", "⏳"):
        """Affiche le résumé trafic routier.

    Args:
        traffic: dict de données. Si None, charge via DB Gold (fail loud si indispo).
    """
    if traffic is None:
        traffic = cached_traffic()

    avg = traffic.get("average_speed_kmh", 0)
    level = traffic.get("congestion_level", "—")
    level_color = traffic.get("congestion_color", COLORS["text_muted"])
    n_bottlenecks = traffic.get("bottlenecks_count", 0)
    data_source = traffic.get("data_source", "unknown")

    data_age = traffic.get("data_age_seconds", -1)
    if data_age >= 0 and data_age < 300:
        st.caption(f"🟢 Live · dernière mesure il y a {int(data_age / 60)} min")
    elif data_age >= 0 and data_age < 1800:
        st.caption(f"🟡 Stale · dernière mesure il y a {int(data_age / 60)} min")
    elif data_age >= 1800:
        st.caption(f"🔴 Figé · dernière mesure il y a {int(data_age / 3600)}h — vérifier DAG")
    elif data_source == "db_gold":
        st.caption("🟢 Données temps réel (DB Gold)")
    else:
        st.caption("🟡 Source inconnue — données potentiellement stales")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Vitesse moyenne", f"{avg} km/h")
    with col2:
        st.markdown(
            f"""
            <div style="padding:0.5rem 0;">
                <div class="lyf-sublabel" style="opacity:0.6;">État du trafic</div>
                <div class="lyf-value" style="font-weight:600;color:{level_color};">
                    {level}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.metric("Bouchons actifs", n_bottlenecks)

    # Prédictions (Sprint 8+ : focus H+1h, les autres horizons masqués)
    st.markdown("##### 🔮 Prédiction H+1h")
    preds = traffic.get("predictions", {})
    p = preds.get("h_plus_1h", {})
    if p:
        st.markdown(
            f"""
            <div class="lyonflow-card" style="text-align:center;padding:1rem;">
                <div class="lyf-detail" style="opacity:0.6;">H+1h</div>
                <div style="font-size:1.6rem;font-weight:600;">{p.get("average_speed_kmh", 0)} km/h</div>
                <div class="lyf-label">{p.get("congestion_level", "—")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("🔮 Pas de prédiction H+1h disponible (DB vide ou DAG en retard).")

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
