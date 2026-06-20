"""Page Pro TCL — Model Monitoring (MLflow Registry + drift + GNN map).

Lit les modeles depuis MLflow Tracking Server (live). Si le serveur
n'est pas joignable, leve DashboardDataError (fail loud, zero mock).

Activation :
1. Set ``LYONFLOW_DASHBOARD_MODEL_MONITORING=true`` dans .env
2. Demarrer le serveur MLflow (Docker compose : service ``mlflow``)
3. Reload cette page
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.pro_tcl import render_model_monitoring_page
from dashboard.components.widgets.pro_tcl.gnn_map import render_gnn_map_section
from src.ml.model_registry import is_model_monitoring_visible

st.set_page_config(
    page_title="Model Monitoring — Pro TCL · LyonFlowFull",
    page_icon="🧠",
    layout="wide",
)

apply_persona_guard(expected_persona="pro_tcl")
inject_theme()
render_sidebar_navigation()
setup_auto_refresh()

st.title("🧠 Model Monitoring")
render_data_status_banner()

# Bandeau si dashboard désactivé
if not is_model_monitoring_visible():
    st.markdown(
        """
        <div style="background:linear-gradient(135deg, #2A2D34 0%, #3F51B5 100%);
                    border:1px dashed #5C6BC0;border-radius:8px;padding:1rem;margin:0.5rem 0;">
            <div style="font-size:0.8rem;opacity:0.8;text-transform:uppercase;
                        letter-spacing:1px;">🟡 Sprint 9 — Dashboard préparé, non activé</div>
            <div class="lyf-label" style="margin:0.5rem 0;">
                Le dashboard Model Monitoring est <b>préparé</b> mais
                <b>désactivé</b> par défaut.
            </div>
            <div class="lyf-detail" style="opacity:0.7;">
                Pour l'activer : set <code>LYONFLOW_DASHBOARD_MODEL_MONITORING=true</code>
                dans .env, puis redémarrer Streamlit. Le dashboard bascule
                alors en mode live MLflow (registry + drift + GNN map).
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()  # Ne pas afficher le contenu détaillé du dashboard

st.caption(
    "Vue opérateur : registry MLflow · modèles XGBoost Speed/Velov + GNN staging · "
    "métriques MAE/RMSE/R² · drift detection. **Sprint 9** : branchement MLflow Tracking API live."
)

# Section 1 : Model Registry Status (toggle + status)
render_model_monitoring_page()

# Section 2 : GNN Map (Sprint 9 — préparée, désactivée par défaut)
st.markdown("---")
render_gnn_map_section()

st.caption(
    "Model Monitoring · Pour relancer un entraînement : `make logs` puis "
    "`airflow dags trigger retrain_xgboost_speed` (ou `retrain_gnn` quand activé)"
)
