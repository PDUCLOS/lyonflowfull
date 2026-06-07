"""Widget — Météo compacte (impact sur Vélov, marche, vélo).

Sprint 8 — Migration data_loader. Si ``weather=None``, tente la DB
(Silver.meteo_hourly) via data_loader, fallback mock si DB down.
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import load_weather_hourly
from src.data.mock.usager import MOCK_WEATHER


def render_weather_widget(weather: dict | None = None) -> None:
    """Affiche la météo compacte avec impact mobilité.

    Args:
        weather: dict météo ou None pour charger via data_loader.
    """
    if weather is None:
        # Tente DB, fallback mock
        df = load_weather_hourly(force_mock=False)
        if not df.empty:
            current = df.iloc[0].to_dict()
            # Adapter le format dict → attendu par le widget
            weather = {
                "condition_icon": _weather_icon(current.get("condition_label", "")),
                "condition": current.get("condition_label", ""),
                "temp_c": current.get("temperature_c", 0),
                "rain_mm_h": current.get("rain_mm", 0),
                "wind_kmh": current.get("wind_kmh", 0),
                "next_3h": [],
            }
        else:
            weather = MOCK_WEATHER

    icon = weather.get("condition_icon", "☀️")
    cond = weather.get("condition", "")
    temp = weather.get("temp_c", 0)
    rain = weather.get("rain_mm_h", 0)
    wind = weather.get("wind_kmh", 0)

    # Score vélo basé sur pluie et vent
    cycling_score = weather.get("cycling_score", 1.0)
    if rain > 0.5 or wind > 35:
        cycling_advice = "❌ Vélov déconseillé"
        cycling_color = "#E74C3C"
    elif rain > 0.1 or wind > 25:
        cycling_advice = "⚠️ Vélov possible mais humide"
        cycling_color = "#FF9800"
    else:
        cycling_advice = "✅ Vélov recommandé"
        cycling_color = "#4CAF50"

    st.markdown(
        f"""
        <div class="lyonflow-card" style="display:flex;align-items:center;gap:1rem;">
            <div style="font-size:2.5rem;">{icon}</div>
            <div style="flex:1;">
                <div style="font-size:1.4rem;font-weight:600;">{temp}°C · {cond}</div>
                <div style="font-size:0.85rem;opacity:0.7;">
                    Pluie {rain}mm/h · Vent {wind} km/h
                </div>
            </div>
            <div style="text-align:right;color:{cycling_color};font-size:0.9rem;font-weight:600;">
                {cycling_advice}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Prévisions 3 prochaines heures
    next_3h = weather.get("next_3h", [])
    if next_3h:
        cols = st.columns(len(next_3h))
        for col, h in zip(cols, next_3h):
            with col:
                st.markdown(
                    f"""
                    <div class="lyonflow-card" style="text-align:center;padding:0.5rem;">
                        <div style="font-size:0.75rem;opacity:0.6;">{h.get('hour')}h</div>
                        <div style="font-size:1.5rem;">{h.get('icon', '')}</div>
                        <div style="font-size:0.9rem;font-weight:600;">{h.get('temp_c', 0)}°</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def _weather_icon(label: str) -> str:
    """Map libellé météo → emoji."""
    mapping = {
        "Ensoleillé": "☀️",
        "Nuageux": "☁️",
        "Pluvieux": "🌧️",
        "Brouillard": "🌫️",
        "Orageux": "⛈️",
        "Neige": "❄️",
    }
    return mapping.get(label, "☀️")
