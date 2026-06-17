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
    <style>
    @keyframes gradientFlow {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    .animated-title {
        font-size: 3.5rem;
        font-weight: 800;
        background: linear-gradient(to right, var(--primary), var(--accent), var(--primary));
        background-size: 200% auto;
        color: transparent;
        -webkit-background-clip: text;
        background-clip: text;
        animation: gradientFlow 4s ease infinite;
        letter-spacing: -1px;
    }
    .subtitle {
        font-size: 1.15rem;
        opacity: 0.85;
        margin-top: 0.5rem;
        font-weight: 500;
    }
    </style>
    <div style="text-align:center;padding:3rem 0 2rem 0;">
        <div class="animated-title">
            🚦 LyonFlowFull
        </div>
        <div class="subtitle">
            La plateforme MLOps qui prédit le trafic et les retards bus sur la Métropole de Lyon
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("---")


# -----------------------------------------------------------------------------
# Auto-redirection ou Splash Screen (Onboarding)
# -----------------------------------------------------------------------------
# Si l'utilisateur a explicitement un persona actif en session, on le redirige.
# L'Accueil devient uniquement une page d'Onboarding / Splash Screen.
from src.persona.manager import _SESSION_KEY  # noqa: E402

has_explicit_persona = _SESSION_KEY in st.session_state

if has_explicit_persona:
    persona_id = get_current_persona()
    persona_config = get_current_persona_config()
    landing_page = persona_config.get("landing_page", "")
    auth_required = persona_config.get("access", {}).get("auth_required", False)

    # Check auth before redirecting
    if auth_required and not is_authenticated():
        st.markdown("### 🔐 Authentification requise")
        st.caption(
            f"Le profil **{persona_config.get('icon', '')} {persona_config.get('label', persona_id)}** "
            f"est protégé. Saisis le mot de passe fourni par l'administrateur."
        )
        require_password()
        st.stop()

    # Si auth OK ou non requise, on redirige
    st.info(f"Redirection vers l'espace {persona_config.get('label', persona_id)}...")
    if landing_page:
        st.switch_page(f"pages/{landing_page}.py")
    else:
        st.warning("Landing page non configurée pour ce persona.")
    st.stop()


# -----------------------------------------------------------------------------
# Qui es-tu ? (Onboarding / Premier accès)
# -----------------------------------------------------------------------------
st.markdown("### 👋 Bienvenue sur LyonFlowFull")
st.caption("Choisis ton profil pour voir la version de l'application adaptée à ton usage.")

render_persona_switcher(layout="cards")

# -----------------------------------------------------------------------------
# Footer : stats globales (lisibles par tous)
# -----------------------------------------------------------------------------
st.markdown("---")
# Sprint 11+ (2026-06-17) — caption refactor : virer "mode démo" (politique
# zéro mock depuis Sprint 8, 2026-06-12). Distinguer explicitement les
# métriques LIVE (lues en DB PostgreSQL Gold, fail loud si indispo) des
# métriques de RÉFÉRENCE (chiffres Grand Lyon Open Data / capacité ML).
st.markdown("##### 📊 Lyon en ce moment — données live + références Grand Lyon")

stat_cols = st.columns(4)

# Imports en bas du bloc : nécessaire car Accueil.py a du code Streamlit avant.
from dashboard.components.data_cache import (  # noqa: E402
    cached_tcl_lines,
    cached_velov_stations,
)
from src.data.exceptions import DashboardDataError  # noqa: E402

n_lines = "—"
n_stations_velov = "—"
try:
    n_lines_raw = cached_tcl_lines(force_mock=False)
    n_lines = len(n_lines_raw) if n_lines_raw else 0
except DashboardDataError as e:
    st.error(f"⚠️ Lignes TCL : {e}")

try:
    n_stations_velov_raw = cached_velov_stations(force_mock=False)
    n_stations_velov = len(n_stations_velov_raw) if n_stations_velov_raw else 0
except DashboardDataError as e:
    st.error(f"⚠️ Stations Vélov : {e}")

with stat_cols[0]:
    st.metric("Capteurs trafic", "1 100", delta="référence Grand Lyon")
with stat_cols[1]:
    st.metric("Lignes TCL", f"{n_lines}", delta="live DB")
with stat_cols[2]:
    st.metric("Stations Vélov", f"{n_stations_velov}", delta="live DB")
with stat_cols[3]:
    st.metric("Prédictions/jour", "~26k", delta="capacité GNN + XGBoost")

st.caption(
    "**Live (DB PostgreSQL Gold)** : Lignes TCL + Stations Vélov actuellement chargées — "
    "fail loud (`DashboardDataError`) si la base est indisponible. "
    "**Référence (Grand Lyon Open Data)** : ~1 100 capteurs trafic historiques, "
    "~118 lignes TCL, ~458 stations Vélov. "
    "**Capacité ML** : ~26k prédictions/jour (GNN + XGBoost H+1h). "
    "Données temps réel mises à jour toutes les 5 min."
)
