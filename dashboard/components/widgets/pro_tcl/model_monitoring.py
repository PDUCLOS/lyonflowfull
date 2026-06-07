"""Widget — Model Monitoring (registry MLflow, métriques, drift).

Affiche :
- Registry des modèles (XGBoost Speed, XGBoost Velov, GNN)
- Versions actives + staging
- **Sprint 8** : Status du Model Registry (XGBoost vs GNN, toggle actif)
- Métriques par modèle (MAE, RMSE, R²)
- Historique entraînement (charts)
- Comparaison entraînement actuel vs précédent
- Drift detection status
"""

from __future__ import annotations

import streamlit as st

# Mock des modèles (en prod : mlflow.search_registered_models + search_runs)
MOCK_MODELS = [
    {
        "name": "xgboost_speed_h5",
        "version": "1.2.0",
        "stage": "Production",
        "metrics": {"mae": 1.96, "rmse": 2.45, "r2": 0.947},
        "trained_at": "2026-06-06 14:25:00",
        "n_training_samples": 1_245_000,
        "feature_count": 14,
        "drift_status": "ok",
    },
    {
        "name": "xgboost_speed_h60",
        "version": "1.2.0",
        "stage": "Production",
        "metrics": {"mae": 2.43, "rmse": 3.12, "r2": 0.929},
        "trained_at": "2026-06-06 14:25:00",
        "n_training_samples": 1_245_000,
        "feature_count": 14,
        "drift_status": "ok",
    },
    {
        "name": "xgboost_speed_h180",
        "version": "1.2.0",
        "stage": "Production",
        "metrics": {"mae": 2.42, "rmse": 3.08, "r2": 0.922},
        "trained_at": "2026-06-06 14:25:00",
        "n_training_samples": 1_245_000,
        "feature_count": 14,
        "drift_status": "ok",
    },
    {
        "name": "xgboost_speed_h360",
        "version": "1.2.0",
        "stage": "Production",
        "metrics": {"mae": 2.33, "rmse": 2.97, "r2": 0.917},
        "trained_at": "2026-06-06 14:25:00",
        "n_training_samples": 1_245_000,
        "feature_count": 14,
        "drift_status": "warning",
    },
    {
        "name": "xgboost_velov_h30",
        "version": "1.0.0",
        "stage": "Production",
        "metrics": {"mae": 4.20, "rmse": 5.31, "r2": 0.331},
        "trained_at": "2026-06-06 14:50:00",
        "n_training_samples": 13_824,
        "feature_count": 11,
        "drift_status": "ok",
    },
    {
        "name": "xgboost_velov_h60",
        "version": "1.0.0",
        "stage": "Production",
        "metrics": {"mae": 4.31, "rmse": 5.48, "r2": 0.299},
        "trained_at": "2026-06-06 14:50:00",
        "n_training_samples": 13_824,
        "feature_count": 11,
        "drift_status": "ok",
    },
    {
        "name": "stgcn_gnn_h60",
        "version": "0.3.0",
        "stage": "Staging",
        "metrics": {"mae": 2.78, "rmse": 3.45, "r2": 0.924},
        "trained_at": "2026-06-05 03:00:00",
        "n_training_samples": 245_000,
        "feature_count": 5,
        "drift_status": "ok",
        "note": "Modèle GNN en pré-prod, comparaison avec XGBoost H+60min en cours",
    },
]


def render_model_registry() -> None:
    """Affiche la liste des modèles dans le registry."""
    st.markdown("##### 📚 Model Registry")

    # Sprint 9 — charge les modèles depuis MLflow live (fallback mock si down)
    try:
        from src.data.data_loader import load_mlflow_experiment_summary, load_mlflow_models

        summary = load_mlflow_experiment_summary(force_mock=False)
        models = load_mlflow_models(force_mock=False)
    except Exception:
        models = MOCK_MODELS
        summary = {"available": False, "run_count": 0, "model_names": []}

    # Bandeau source (transparence MLflow)
    if summary.get("available"):
        st.success(
            f"🟢 **MLflow live** · {summary.get('run_count', 0)} runs · "
            f"{len(summary.get('model_names', []))} modèles"
        )
    else:
        st.warning(
            "🟡 **MLflow non accessible** — affichage fallback mock. "
            "Pour activer : démarrer le service `mlflow` (docker compose) "
            "et recharger cette page."
        )

    if not models:
        st.info("Aucun modèle tracké. Lance un training pour peupler le registry.")
        return

    # KPIs
    prod = sum(1 for m in models if m.get("stage") == "Production")
    staging = sum(1 for m in models if m.get("stage") == "Staging")
    n_drift = sum(1 for m in models if m.get("drift_status") != "ok")

    cols = st.columns(4)
    with cols[0]:
        st.metric("🟢 Production", prod)
    with cols[1]:
        st.metric("🟡 Staging", staging)
    with cols[2]:
        st.metric("Total modèles", len(models))
    with cols[3]:
        st.metric("🚨 Drift alertes", n_drift, delta_color="inverse")

    # Tableau (Sprint 9 — utilise la variable `models` MLflow ou mock)
    _render_model_registry_table(models)


def _render_model_registry_table(models: list[dict]) -> None:
    """Tableau des modèles trackés (MLflow ou mock)."""
    st.markdown("---")
    header_cols = st.columns([2.5, 1, 1, 1, 1.5, 1.2, 1])
    with header_cols[0]:
        st.markdown("**Modèle**")
    with header_cols[1]:
        st.markdown("**Version**")
    with header_cols[2]:
        st.markdown("**Stage**")
    with header_cols[3]:
        st.markdown("**MAE**")
    with header_cols[4]:
        st.markdown("**Entraîné le**")
    with header_cols[5]:
        st.markdown("**Samples**")
    with header_cols[6]:
        st.markdown("**Drift**")

    for m in models:
        cols = st.columns([2.5, 1, 1, 1, 1.5, 1.2, 1])
        with cols[0]:
            st.markdown(f"`{m.get('name', '—')}`")
            if m.get("note"):
                st.caption(m["note"])
        with cols[1]:
            st.code(m.get("version", "—"))
        with cols[2]:
            stage_color = {"Production": "#4CAF50", "Staging": "#FF9800"}.get(
                m.get("stage", ""), "#666"
            )
            st.markdown(
                f'<span style="background:{stage_color};color:white;padding:2px 8px;'
                f'border-radius:8px;font-size:0.75rem;">{m.get("stage", "—")}</span>',
                unsafe_allow_html=True,
            )
        with cols[3]:
            mae = m.get("metrics", {}).get("mae", 0.0)
            st.markdown(f"**{mae:.2f}**")
        with cols[4]:
            trained = str(m.get("trained_at", "—"))[:19]  # tronque
            st.markdown(trained)
        with cols[5]:
            st.markdown(f"{m.get('n_training_samples', 0):,}")
        with cols[6]:
            drift = m.get("drift_status", "ok")
            drift_emoji = {"ok": "✅", "warning": "⚠️", "critical": "🚨"}.get(drift, "—")
            st.markdown(f"{drift_emoji} {drift}")


def render_model_registry_status() -> None:
    """Sprint 8 — Affiche le statut live du Model Registry (toggle XGBoost vs GNN).

    Section ajoutée pour permettre à Patrice de visualiser en temps réel
    quel modèle est actif en prod et basculer de l'un à l'autre.
    """
    st.markdown("##### 🎛️ Model Registry Status (live)")

    # Import paresseux pour ne pas casser en cas de modèle manquant
    try:
        from src.ml.model_registry import (
            ModelRegistry,
            get_active_models,
            is_stgcn_training_enabled,
            is_xgboost_training_enabled,
        )
    except ImportError as e:
        st.warning(f"Model Registry indispo : {e}")
        return

    active = get_active_models().value
    if active == "both":
        badge_color = "#FF9800"
        badge_text = "🟡 COEXISTENCE (XGBoost=Champion, GNN=Challenger)"
    elif active == "xgboost":
        badge_color = "#4CAF50"
        badge_text = "🟢 XGBOOST SEUL (prod)"
    elif active == "stgcn":
        badge_color = "#9C27B0"
        badge_text = "🟣 STGCN SEUL (GNN a pris le relais)"
    else:
        badge_color = "#666"
        badge_text = f"⚪ {active}"

    st.markdown(
        f'<div style="background:{badge_color};color:white;padding:0.5rem 1rem;'
        f'border-radius:6px;margin-bottom:0.8rem;font-weight:600;">'
        f"{badge_text}</div>",
        unsafe_allow_html=True,
    )

    # Toggles status
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "XGBoost retrain",
            "ON" if is_xgboost_training_enabled() else "OFF",
            delta="nightly" if is_xgboost_training_enabled() else "paused",
            delta_color="normal" if is_xgboost_training_enabled() else "inverse",
        )
    with col2:
        st.metric(
            "GNN retrain",
            "ON" if is_stgcn_training_enabled() else "OFF",
            delta="EC2 nightly" if is_stgcn_training_enabled() else "paused",
            delta_color="normal" if is_stgcn_training_enabled() else "inverse",
        )
    with col3:
        # Show 1 horizon representative
        r60 = ModelRegistry.get(60)
        st.metric("XGB H+60min dispo", "✅" if r60.xgboost and r60.xgboost.is_available() else "❌")
    with col4:
        st.metric("GNN H+60min dispo", "✅" if r60.stgcn and r60.stgcn.is_available() else "❌")

    # Detail table
    st.markdown("---")
    st.markdown("**Status par horizon**")
    horizons = [5, 15, 30, 60, 180, 360]
    for h in horizons:
        reg = ModelRegistry.get(h)
        s = reg.status()
        col1, col2, col3, col4 = st.columns([1, 2, 2, 2])
        with col1:
            st.markdown(f"**H+{h}min**")
        with col2:
            color = "#4CAF50" if s["xgboost_available"] else "#999"
            st.markdown(
                f'<span style="color:{color};">●</span> XGBoost',
                unsafe_allow_html=True,
            )
        with col3:
            color = "#9C27B0" if s["stgcn_available"] else "#999"
            st.markdown(
                f'<span style="color:{color};">●</span> STGCN',
                unsafe_allow_html=True,
            )
        with col4:
            champion = s.get("champion", "—")
            challenger = s.get("challenger", "—")
            st.caption(f"Champion: **{champion}** · Challenger: {challenger or '—'}")

    # Switch helper (admin)
    st.markdown("---")
    with st.expander("🔧 Basculer la solution active (admin)", expanded=False):
        st.markdown(
            """
            Pour basculer entre XGBoost / GNN / les deux, modifier la
            variable d'environnement ``LYONFLOW_MODELS_ACTIVE`` puis
            redémarrer les services :

            ```bash
            # Sur le VPS (ou dans .env)
            export LYONFLOW_MODELS_ACTIVE=xgboost   # XGBoost seul
            export LYONFLOW_MODELS_ACTIVE=stgcn     # GNN seul
            export LYONFLOW_MODELS_ACTIVE=both       # coexistence (défaut)

            # Pour stopper le retrain du modèle non-champion
            export LYONFLOW_XGBOOST_TRAINING=false
            export LYONFLOW_STGCN_TRAINING=false

            # Reload Airflow + API + Streamlit
            docker compose restart airflow-scheduler api streamlit
            ```

            Le dashboard "Model Monitoring" (Pro_7) reflète le toggle en
            moins de 30s grâce au cache de streamlit.
            """
        )

    # Note Sprint 9 : le tableau détaillé des modèles est rendu par
    # `render_model_registry()` (au-dessus), qui lit MLflow live + fallback mock.
    # On évite la duplication ici.


def render_metrics_comparison() -> None:
    """Affiche la comparaison des métriques entre modèles."""
    st.markdown("##### 📊 Comparaison métriques (XGBoost vs GNN)")

    # Filtrer modèles avec MAE comparable
    xgb_h60 = next((m for m in MOCK_MODELS if m["name"] == "xgboost_speed_h60"), None)
    gnn_h60 = next((m for m in MOCK_MODELS if m["name"] == "stgcn_gnn_h60"), None)

    if not xgb_h60 or not gnn_h60:
        return

    cols = st.columns(2)
    with cols[0]:
        st.markdown("**XGBoost Speed H+60min**")
        st.metric("MAE", f"{xgb_h60['metrics']['mae']:.2f} km/h")
        st.metric("R²", f"{xgb_h60['metrics']['r2']:.3f}")
        st.metric("Samples", f"{xgb_h60['n_training_samples']:,}")
        st.metric("Features", xgb_h60['feature_count'])

    with cols[1]:
        st.markdown("**ST-GCN GNN H+60min (Staging)**")
        st.metric(
            "MAE", f"{gnn_h60['metrics']['mae']:.2f} km/h",
            delta=f"{gnn_h60['metrics']['mae'] - xgb_h60['metrics']['mae']:+.2f} vs XGBoost",
            delta_color="inverse",
        )
        st.metric("R²", f"{gnn_h60['metrics']['r2']:.3f}",
                  delta=f"{gnn_h60['metrics']['r2'] - xgb_h60['metrics']['r2']:+.3f} vs XGBoost")
        st.metric("Samples", f"{gnn_h60['n_training_samples']:,}")
        st.metric("Features", gnn_h60['feature_count'])

    st.caption(
        "💡 Le GNN capture les dépendances spatiales entre segments. "
        "Promotion Production prévue si MAE reste < XGBoost pendant 7 jours consécutifs."
    )


def render_training_history() -> None:
    """Affiche l'historique des entraînements (charts)."""
    st.markdown("##### 📈 Historique entraînement (7 derniers jours)")

    # Mock data pour charts
    days = ["J-6", "J-5", "J-4", "J-3", "J-2", "J-1", "J0"]
    mae_speed_h60 = [2.51, 2.48, 2.50, 2.45, 2.46, 2.44, 2.43]
    mae_velov_h30 = [4.31, 4.28, 4.25, 4.22, 4.20, 4.18, 4.20]

    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=days, y=mae_speed_h60, mode="lines+markers",
            name="XGBoost Speed H+60min", line={"color": "#4CAF50", "width": 3},
        ))
        fig.add_trace(go.Scatter(
            x=days, y=mae_velov_h30, mode="lines+markers",
            name="XGBoost Velov H+30min", line={"color": "#FF9800", "width": 3},
            yaxis="y2",
        ))
        fig.update_layout(
            title="MAE evolution",
            xaxis_title="Jour",
            yaxis_title="MAE Speed (km/h)",
            yaxis2={"title": "MAE Velov (vélos)", "overlaying": "y", "side": "right"},
            template="plotly_dark",
            height=350,
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        # Fallback ASCII
        st.code("J-6 → J0: MAE Speed 2.51 → 2.43 | MAE Velov 4.31 → 4.20")


def render_drift_panel() -> None:
    """Affiche le statut de drift detection par modèle."""
    st.markdown("##### 🌊 Drift Detection")

    # Mock : rapport drift
    drifts = [
        {
            "model": "xgboost_speed_h360",
            "drift_score": 0.42,
            "threshold": 0.5,
            "features_drifted": ["rain_mm", "is_vacances"],
            "status": "warning",
            "detected_at": "2026-06-06 06:00:00",
            "action": "À analyser — léger drift sur 2 features",
        },
        {
            "model": "xgboost_speed_h5",
            "drift_score": 0.18,
            "threshold": 0.5,
            "features_drifted": [],
            "status": "ok",
            "detected_at": "2026-06-06 06:00:00",
        },
    ]

    for d in drifts:
        status = d["status"]
        color = {"ok": "#4CAF50", "warning": "#FF9800", "critical": "#E74C3C"}.get(status, "#666")
        icon = {"ok": "🟢", "warning": "🟡", "critical": "🔴"}.get(status, "⚪")

        st.markdown(
            f"""
            <div style="background:#1A1D24;border:1px solid #2A2D34;border-left:4px solid {color};
                        border-radius:6px;padding:0.7rem;margin:0.4rem 0;">
                <div style="display:flex;align-items:center;gap:0.6rem;">
                    <div style="font-size:1.3rem;">{icon}</div>
                    <div style="flex:1;">
                        <div style="font-weight:600;">{d['model']}</div>
                        <div style="font-size:0.8rem;opacity:0.7;">
                            Drift score: {d['drift_score']:.2f} / seuil {d['threshold']} · {d['detected_at']}
                        </div>
                        {('<div style="font-size:0.8rem;color:#FF9800;margin-top:0.2rem;">⚠️ ' + ', '.join(d.get('features_drifted', [])) + '</div>') if d.get('features_drifted') else ''}
                        {('<div style="font-size:0.8rem;margin-top:0.2rem;">→ ' + d.get('action', '') + '</div>') if d.get('action') else ''}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_model_monitoring_page() -> None:
    """Page complète Model Monitoring (point d'entrée)."""
    # Sprint 8 — Status live du toggle XGBoost vs GNN (en haut)
    render_model_registry_status()
    st.markdown("---")
    render_model_registry()
    st.markdown("---")
    render_metrics_comparison()
    st.markdown("---")
    render_training_history()
    st.markdown("---")
    render_drift_panel()
