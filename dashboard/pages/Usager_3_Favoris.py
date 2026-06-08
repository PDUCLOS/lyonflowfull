"""Page Usager — Mes favoris (Sprint 2 complet)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.usager import (
    render_favorite_list,
    render_recurrent_trip_card,
)
from src.data.mock.usager import MOCK_FAVORITES

# Favoris persistes en session_state (demo) — futur: table user_favorites.
if "user_favorites" not in st.session_state:
    st.session_state["user_favorites"] = list(MOCK_FAVORITES)
favorites = st.session_state["user_favorites"]

st.set_page_config(
    page_title="Mes favoris — LyonFlowFull",
    page_icon="⭐",
    layout="wide",
)

apply_persona_guard(expected_persona="usager")
inject_theme()
render_sidebar_navigation()

st.title("⭐ Mes favoris")
render_data_status_banner()
st.caption(
    "ℹ️ Demo session — les favoris sont stockés dans la session Streamlit. "
    "Backend persistant (table user_favorites) prévu apres release auth."
)

# Compteurs
n_total = len(favorites)
n_alerts_on = sum(1 for f in favorites if f.get("alert_subscribed"))

cols = st.columns(3)
with cols[0]:
    st.metric("Trajets sauvegardés", n_total)
with cols[1]:
    st.metric("Avec alertes", n_alerts_on)
with cols[2]:
    st.metric("Économie temps/semaine", "~45 min", "estimé")

st.markdown("---")

# Liste des favoris
render_favorite_list(favorites)

st.markdown("---")

# Détail d'un favori (expandable)
st.markdown("##### 🔍 Détails d'un trajet favori")
selected = st.selectbox(
    "Choisir un trajet",
    [f.get("name", "—") for f in favorites],
    key="fav_detail_select",
)
if selected:
    fav = next((f for f in favorites if f.get("name") == selected), None)
    if fav:
        render_recurrent_trip_card(fav, expanded=True)

st.markdown("---")

# Bouton d'ajout (placeholder — Sprint 6+ : vraie UI)
col_btn = st.columns([1, 2, 1])
with col_btn[1]:
    if st.button("➕ Ajouter un trajet favori", use_container_width=True, disabled=True):
        st.info("🚧 À venir — Sprint 6+")

st.caption("LyonFlowFull · Favoris · Modifiables dans Réglages")
