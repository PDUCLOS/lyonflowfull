"""Page commune — À propos."""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.theme import inject_theme
from src.config import get_settings

st.set_page_config(
    page_title="À propos — LyonFlow",
    page_icon="ℹ️",
    layout="wide",
)

inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

st.title("ℹ️ À propos de LyonFlow")
render_data_status_banner()

st.markdown(
    """
    ### La plateforme

    **LyonFlow** est une plateforme MLOps de prédiction et d'analyse
    du trafic multimodal sur la Métropole de Lyon. Elle fusionne trois
    projets open source en une solution unifiée :

    - `caroheymes/Architect-IA-final-project` (architecture initiale)
    - `PDUCLOS/LyonFlow` (routing multimodal, ingestion ABC)
    - `PDUCLOS/lyontraffic` (production Medallion, XGBoost live)

    ### Les 4 piliers ML

    1. **Trafic routier** — XGBoost (réactif, H+1h)
    2. **Bus TCL** — analyse SIRI Lite + diagnostic infrastructure
    3. **Vélov** — prédiction disponibilité H+30min
    4. **Recommandation trajet** — scoring composite 50% temps + 30% coût + 20% CO₂

    ### Les 3 personas

    - **🌱 Usager** — vue simplifiée, recherche trajet, alertes
    - **🎛 Pro TCL** — control room, OTP, corrélation bus/trafic
    - **🏛 Élu** — synthèse exécutive, bottlenecks prioritaires, PDF

    ### Auteur

    **Patrice DUCLOS** — Senior Data Analyst, Jedha RNCP 38777
    (Architecte en IA)

    ### Stack

    Apache Airflow 2.9 · PostgreSQL 16 + PostGIS · MLflow 2.12 ·
    PyTorch Geometric · XGBoost · FastAPI · Streamlit · Evidently AI ·
    Docker Compose · Nginx

    ---
    """
)

st.caption(f"LyonFlow v{get_settings().app_version}")
