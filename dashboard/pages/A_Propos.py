"""Page commune — À propos."""

from __future__ import annotations

import streamlit as st

from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.theme import inject_theme

st.set_page_config(
    page_title="À propos — LyonFlowFull",
    page_icon="ℹ️",
    layout="wide",
)

inject_theme()
render_sidebar_navigation()

st.title("ℹ️ À propos de LyonFlowFull")

st.markdown(
    """
    ### La plateforme

    **LyonFlowFull** est une plateforme MLOps de prédiction et d'analyse
    du trafic multimodal sur la Métropole de Lyon. Elle fusionne trois
    projets open source en une solution unifiée :

    - `caroheymes/Architect-IA-final-project` (ST-GRU-GNN spatial)
    - `PDUCLOS/LyonFlow` (routing multimodal, ingestion ABC)
    - `PDUCLOS/lyontraffic` (production Medallion, XGBoost live)

    ### Les 4 piliers ML

    1. **Trafic routier** — tandem GNN (spatial) + XGBoost (réactif)
    2. **Bus TCL** — analyse SIRI Lite + diagnostic infrastructure
    3. **Vélov** — prédiction disponibilité H+30min et H+1h
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

    *LyonFlowFull v0.1.0 — 2026-06-05*
    """
)
