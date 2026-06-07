"""LyonFlowFull — Page d'accueil.

Trois personas, un même moteur. Cette page :
1. Affiche le sélecteur de persona (3 cartes)
2. Si un persona protégé est sélectionné sans auth → formulaire mot de passe
3. Si auth OK → redirige vers la landing page du persona

Layout : pleine page, centré, 1 colonne principale.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_switcher import render_persona_switcher
from dashboard.components.theme import inject_theme
from src.persona.auth import is_authenticated, require_password
from src.persona.manager import (
    get_current_persona,
    get_current_persona_config,
)

st.set_page_config(
    page_title="LyonFlowFull",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()
render_sidebar_navigation()


# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div style="text-align:center;padding:2rem 0 1rem 0;">
        <div style="font-size:3rem;font-weight:700;color:#4CAF50;">
            🚦 LyonFlowFull
        </div>
        <div style="font-size:1.1rem;opacity:0.8;margin-top:0.5rem;">
            La plateforme MLOps qui prédit le trafic et les retards bus sur la Métropole de Lyon
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("---")


# -----------------------------------------------------------------------------
# Qui es-tu ?
# -----------------------------------------------------------------------------
st.markdown("### 👋 Qui es-tu ?")
st.caption("Choisis ton profil pour voir la version de LyonFlowFull adaptée à ton usage.")

render_persona_switcher(layout="cards")

st.markdown("---")


# -----------------------------------------------------------------------------
# Authentification si persona protégé
# -----------------------------------------------------------------------------
persona_id = get_current_persona()
persona_config = get_current_persona_config()
auth_required = persona_config.get("access", {}).get("auth_required", False)

if auth_required and not is_authenticated():
    st.markdown("### 🔐 Authentification requise")
    st.caption(
        f"Le profil **{persona_config.get('icon', '')} {persona_config.get('label', persona_id)}** "
        f"est protégé. Saisis le mot de passe fourni par l'administrateur."
    )
    require_password()
    st.stop()


# -----------------------------------------------------------------------------
# Accès à l'app
# -----------------------------------------------------------------------------
st.markdown("### 🚀 Prêt à démarrer ?")
landing_page = persona_config.get("landing_page", "")

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button(
        f"➡️ Entrer en mode {persona_config.get('label', persona_id)}",
        type="primary",
        use_container_width=True,
    ):
        if landing_page:
            st.switch_page(f"pages/{landing_page}.py")
        else:
            st.warning("Landing page non configurée pour ce persona.")

# -----------------------------------------------------------------------------
# Footer : stats globales (lisibles par tous)
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("##### 📊 Lyon en ce moment (aperçu — valeurs de référence, mode démo)")

stat_cols = st.columns(4)
# TODO Sprint 6+ : query DB pour vraies valeurs
# SELECT COUNT(*) FROM bronze.velov, etc.
with stat_cols[0]:
    st.metric("Capteurs trafic", "1 100", delta="📊 référence")
with stat_cols[1]:
    st.metric("Lignes TCL", "118", delta="📊 référence")
with stat_cols[2]:
    st.metric("Stations Vélov", "458", delta="📊 référence")
with stat_cols[3]:
    st.metric("Prédictions/jour", "~26k", delta="GNN + XGBoost")

st.caption("Données mises à jour toutes les 5 min · Source : Grand Lyon Open Data + Open-Meteo")
