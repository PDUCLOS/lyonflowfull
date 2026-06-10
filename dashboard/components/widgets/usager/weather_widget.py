"""Widget — Météo compacte (impact sur Vélov, marche, vélo).

Sprint 8 — Migration data_loader. Si ``weather=None``, tente la DB
(Silver.meteo_hourly) via data_loader, fallback mock si DB down.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_weather_hourly
from src.data.mock.usager import MOCK_WEATHER


def render_weather_widget(weather: dict | None = None) -> None:
    """Affiche la météo compacte avec impact mobilité.

    Args:
        weather: dict météo ou None pour charger via data_loader.
    """
    if weather is None:
        # Tente DB, fallback mock
        df = cached_weather_hourly(force_mock=False)
        if not df.empty:
            current = df.iloc[0].to_dict()
            # Sprint 10 : weather_code est un int WMO (Open-Meteo). On le convertit
            # en label FR lisible + emoji via _wmo_to_label().
            raw_code = current.get("condition_label") or current.get("weather_code")
            label, icon_from_code = _wmo_to_label(raw_code)
            weather = {
                "condition_icon": icon_from_code,
                "condition": label,
                "temp_c": current.get("temperature_c", 0),
                "rain_mm_h": current.get("rain_mm", 0),
                "wind_kmh": current.get("wind_kmh", 0),
                "next_3h": [],
            }
        else:
            weather = MOCK_WEATHER

    icon = str(weather.get("condition_icon", "☀️"))
    cond = str(weather.get("condition", ""))
    # Sprint 10 : arrondi 1 décimale pour éviter les artefacts float32
    # ('16.700000762939453' → '16.7').
    temp = round(float(weather.get("temp_c", 0)), 1)
    rain = round(float(weather.get("rain_mm_h", 0)), 1)
    wind = round(float(weather.get("wind_kmh", 0)), 1)

    # Score vélo basé sur pluie et vent
    cycling_score = weather.get("cycling_score", 1.0)
    if rain > 0.5 or wind > 35:
        cycling_advice = "❌ Vélov déconseillé"
        cycling_color = COLORS["status_critical"]
    elif rain > 0.1 or wind > 25:
        cycling_advice = "⚠️ Vélov possible mais humide"
        cycling_color = COLORS["status_warning"]
    else:
        cycling_advice = "✅ Vélov recommandé"
        cycling_color = COLORS["status_ok"]

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
    next_3h = list(weather.get("next_3h", []))
    if next_3h:
        cols = st.columns(len(next_3h))
        for col, h in zip(cols, next_3h):
            with col:
                st.markdown(
                    f"""
                    <div class="lyonflow-card" style="text-align:center;padding:0.5rem;">
                        <div style="font-size:0.75rem;opacity:0.6;">{h.get("hour")}h</div>
                        <div style="font-size:1.5rem;">{h.get("icon", "")}</div>
                        <div style="font-size:0.9rem;font-weight:600;">{h.get("temp_c", 0)}°</div>
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


# WMO Weather interpretation codes (Open-Meteo / WMO 4677).
# https://open-meteo.com/en/docs (table "WMO Weather interpretation codes")
# Mappés vers un label FR lisible + emoji. Couvre les codes les plus courants
# observés sur Lyon (1xxx = pas de précip, 2xxx = stable, 3xxx = doux,
# 4xxx = brouillard, 5xxx = bruine, 6xxx = pluie, 7xxx = neige,
# 8xxx = averses, 9xxx = orage).
_WMO_CODE_MAP: dict[int, tuple[str, str]] = {
    0:  ("Ensoleillé", "☀️"),
    1:  ("Peu nuageux", "🌤️"),
    2:  ("Partiellement nuageux", "⛅"),
    3:  ("Couvert", "☁️"),
    45: ("Brouillard", "🌫️"),
    48: ("Brouillard givrant", "🌫️"),
    51: ("Bruine légère", "🌦️"),
    53: ("Bruine", "🌦️"),
    55: ("Bruine dense", "🌧️"),
    56: ("Bruine verglaçante", "🌧️"),
    57: ("Bruine verglaçante forte", "🌧️"),
    61: ("Pluie faible", "🌦️"),
    63: ("Pluie", "🌧️"),
    65: ("Pluie forte", "🌧️"),
    66: ("Pluie verglaçante", "🌧️"),
    67: ("Pluie verglaçante forte", "🌧️"),
    71: ("Neige faible", "🌨️"),
    73: ("Neige", "❄️"),
    75: ("Neige forte", "❄️"),
    77: ("Grains de neige", "❄️"),
    80: ("Averse faible", "🌦️"),
    81: ("Averse", "🌧️"),
    82: ("Averse forte", "⛈️"),
    85: ("Averse de neige", "🌨️"),
    86: ("Averse de neige forte", "❄️"),
    95: ("Orage", "⛈️"),
    96: ("Orage grêle", "⛈️"),
    99: ("Orage grêle fort", "⛈️"),
}


def _wmo_to_label(code: Any) -> tuple[str, str]:
    """Convertit un code météo WMO (int/str) en (label FR, emoji).

    Tolérant : accepte str (depuis JSONB), int, None, ou un label FR déjà
    valide (cas MOCK_WEATHER). Fallback "Couvert" si code inconnu.
    """
    if code is None:
        return "Couvert", "☁️"
    # Si c'est déjà un label FR (mock path), on garde
    if isinstance(code, str) and code in ("Ensoleillé", "Nuageux", "Pluvieux", "Brouillard", "Orageux", "Neige"):
        return code, _weather_icon(code)
    try:
        code_int = int(float(code))
    except (ValueError, TypeError):
        return "Couvert", "☁️"
    return _WMO_CODE_MAP.get(code_int, ("Couvert", "☁️"))
