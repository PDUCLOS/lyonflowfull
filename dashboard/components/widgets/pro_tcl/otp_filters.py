"""Widget — Filtres OTP (période, jour, météo)."""

from __future__ import annotations

import streamlit as st


def render_otp_filters() -> dict:
    """Affiche les filtres OTP et retourne la config sélectionnée.

    Returns:
        Dict avec clés : period, day_type, weather, start_date, end_date
    """
    st.markdown("##### 🔍 Filtres")

    col1, col2, col3 = st.columns(3)
    with col1:
        period = st.selectbox(
            "Période",
            ["Aujourd'hui", "7 derniers jours", "30 derniers jours", "Personnalisé"],
            key="otp_filter_period",
        )
    with col2:
        day_type = st.multiselect(
            "Jours",
            ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"],
            default=["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"],
            key="otp_filter_days",
        )
    with col3:
        weather = st.multiselect(
            "Météo",
            ["☀️ Beau", "☁️ Couvert", "🌧 Pluie", "❄️ Neige"],
            default=["☀️ Beau", "☁️ Couvert", "🌧 Pluie"],
            key="otp_filter_weather",
        )

    return {
        "period": period,
        "day_type": day_type,
        "weather": weather,
    }
