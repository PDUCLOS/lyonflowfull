"""Widget — Réglages des alertes (quelles alertes, quand, comment)."""

from __future__ import annotations

import streamlit as st


def render_alert_settings() -> None:
    """Affiche les réglages des alertes (checkboxes + sliders)."""
    st.markdown("##### ⚙️ Réglages des alertes")

    st.markdown("**Types d'alertes**")
    c1, c2 = st.columns(2)
    with c1:
        st.checkbox("🚊 Retards tram/bus", value=True, key="alert_setting_delay")
        st.checkbox("🚦 Saturation ligne", value=True, key="alert_setting_saturation")
        st.checkbox("🚧 Chantiers", value=False, key="alert_setting_chantiers")
    with c2:
        st.checkbox("🌧 Météo impactante", value=True, key="alert_setting_meteo")
        st.checkbox("🚲 Vélov vides", value=False, key="alert_setting_velov")
        st.checkbox("🎉 Événements", value=False, key="alert_setting_events")

    st.markdown("**Fenêtre d'alerte**")
    st.slider(
        "Recevoir les alertes dans la fenêtre suivante (min)",
        0,
        60,
        (5, 30),
        key="alert_setting_window",
    )

    st.markdown("**Mode**")
    st.radio(
        "Mode de notification",
        ["Push dans l'app", "Email (quotidien)", "Désactivé"],
        key="alert_setting_mode",
        horizontal=True,
    )
