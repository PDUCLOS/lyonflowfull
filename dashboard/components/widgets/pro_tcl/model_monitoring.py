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

from dashboard.components.colors import COLORS

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
        from dashboard.components.data_cache import cached_mlflow_experiment_summary, cached_mlflow_models

        summary = cached_mlflow_experiment_summary(force_mock=False)
        models = cached_mlflow_models(force_mock=False)
    except Exception:
        models = MOCK_MODELS
        summary = {"available": False, "run_count": 0, "model_names": []}

    # Bandeau source (transparence MLflow)
    if summary.get("available"):
        st.success(
            f"🟢 **MLflow live** · {summary.get('run_count', 0)} runs · {len(summary.get('model_names', []))} modèles"
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
            stage_color = {"Production": COLORS["status_ok"], "Staging": COLORS["status_warning"]}.get(
                m.get("stage", ""), COLORS["text_muted"]
            )
            st.markdown(
                f'<span style="background:{stage_color};color:white;padding:2px 8px;'
                f'border-radius:8px;font-size:0.75rem;">{m.get("stage", "—")}</span>',
                unsafe_allow_html=True,
            )
        with cols[3]:
            # mae None-safe (m["metrics"] peut être absent ou metrics.mae peut être None)
            mae_raw = m.get("metrics", {}).get("mae") if m.get("metrics") else None
            try:
                mae_str = f"{float(mae_raw):.2f}"
            except (TypeError, ValueError):
                mae_str = "—"
            st.markdown(f"**{mae_str}**")
        with cols[4]:
            trained = str(m.get("trained_at", "—"))[:19]  # tronque
            st.markdown(trained)
        with cols[5]:
            try:
                samples = int(m.get("n_training_samples", 0) or 0)
            except (TypeError, ValueError):
                samples = 0
            st.markdown(f"{samples:,}")
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
        badge_color = COLORS["status_warning"]
        badge_text = "🟡 COEXISTENCE (XGBoost=Champion, GNN=Challenger)"
    elif active == "xgboost":
        badge_color = COLORS["status_ok"]
        badge_text = "🟢 XGBOOST SEUL (prod)"
    elif active == "stgcn":
        badge_color = COLORS["chart_purple"]
        badge_text = "🟣 STGCN SEUL (GNN a pris le relais)"
    else:
        badge_color = COLORS["text_muted"]
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
            color = COLORS["status_ok"] if s["xgboost_available"] else COLORS["text_disabled"]
            st.markdown(
                f'<span style="color:{color};">●</span> XGBoost',
                unsafe_allow_html=True,
            )
        with col3:
            color = COLORS["chart_purple"] if s["stgcn_available"] else COLORS["text_disabled"]
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

    # Sources live MLflow (fallback mock auto via data_loader)
    try:
        from dashboard.components.data_cache import cached_mlflow_models

        models = cached_mlflow_models(force_mock=False) or MOCK_MODELS
    except Exception:
        models = MOCK_MODELS

    xgb_h60 = next((m for m in models if m.get("name") == "xgboost_speed_h60"), None)
    gnn_h60 = next((m for m in models if m.get("name") == "stgcn_gnn_h60"), None)

    if not xgb_h60 or not gnn_h60:
        return

    # Defensive : valeurs None-safe pour éviter crash si MLflow renvoie un dict partiel
    def _mae(m):
        try:
            return float(m.get("metrics", {}).get("mae", 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _r2(m):
        try:
            return float(m.get("metrics", {}).get("r2", 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _samples(m):
        try:
            return int(m.get("n_training_samples", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _features(m):
        try:
            return int(m.get("feature_count", 0) or 0)
        except (TypeError, ValueError):
            return 0

    cols = st.columns(2)
    with cols[0]:
        st.markdown("**XGBoost Speed H+60min**")
        st.metric("MAE", f"{_mae(xgb_h60):.2f} km/h")
        st.metric("R²", f"{_r2(xgb_h60):.3f}")
        st.metric("Samples", f"{_samples(xgb_h60):,}")
        st.metric("Features", _features(xgb_h60))

    with cols[1]:
        st.markdown("**ST-GCN GNN H+60min (Staging)**")
        st.metric(
            "MAE",
            f"{_mae(gnn_h60):.2f} km/h",
            delta=f"{_mae(gnn_h60) - _mae(xgb_h60):+.2f} vs XGBoost",
            delta_color="inverse",
        )
        st.metric(
            "R²",
            f"{_r2(gnn_h60):.3f}",
            delta=f"{_r2(gnn_h60) - _r2(xgb_h60):+.3f} vs XGBoost",
        )
        st.metric("Samples", f"{_samples(gnn_h60):,}")
        st.metric("Features", _features(gnn_h60))

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
        fig.add_trace(
            go.Scatter(
                x=days,
                y=mae_speed_h60,
                mode="lines+markers",
                name="XGBoost Speed H+60min",
                line={"color": COLORS["status_ok"], "width": 3},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=days,
                y=mae_velov_h30,
                mode="lines+markers",
                name="XGBoost Velov H+30min",
                line={"color": COLORS["status_warning"], "width": 3},
                yaxis="y2",
            )
        )
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
        color = {
            "ok": COLORS["status_ok"],
            "warning": COLORS["status_warning"],
            "critical": COLORS["status_critical"],
        }.get(status, COLORS["text_muted"])
        icon = {"ok": "🟢", "warning": "🟡", "critical": "🔴"}.get(status, "⚪")

        st.markdown(
            f"""
            <div style="background:var(--bg-card);border:1px solid var(--border-card);border-left:4px solid {color};
                        border-radius:6px;padding:0.7rem;margin:0.4rem 0;">
                <div style="display:flex;align-items:center;gap:0.6rem;">
                    <div style="font-size:1.3rem;">{icon}</div>
                    <div style="flex:1;">
                        <div style="font-weight:600;">{d["model"]}</div>
                        <div style="font-size:0.8rem;opacity:0.7;">
                            Drift score: {d["drift_score"]:.2f} / seuil {d["threshold"]} · {d["detected_at"]}
                        </div>
                        {('<div style="font-size:0.8rem;color:var(--status-warning);margin-top:0.2rem;">⚠️ ' + ", ".join(str(feat) for feat in d.get("features_drifted", [])) + "</div>") if d.get("features_drifted") else ""}
                        {('<div style="font-size:0.8rem;margin-top:0.2rem;">→ ' + str(d.get("action", "")) + "</div>") if d.get("action") else ""}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_velov_model_analysis() -> None:
    """Sprint 10 — Analyse modèle Vélo'v (freshness + distribution + backtest).

    Lit ``gold.velov_predictions`` directement et calcule :
    * Freshness (timestamp dernière prédiction)
    * Coverage (nb stations couvertes / total)
    * Distribution predicted_bikes par horizon
    * Confidence interval moyen (largeur)
    * Backtest MAE si ``gold.predictions_vs_actuals`` contient des vélov rows.
    """
    st.markdown("##### 🚲 Analyse modèle Vélo'v (XGBoost)")
    try:
        from dashboard.components.data_cache import cached_velov_predictions
        from src.data.db_query import get_velov_stations_geo
    except Exception as e:
        st.warning(f"Imports indisponibles : {e}")
        return

    pred_30 = cached_velov_predictions(horizon_minutes=30, force_mock=False)
    pred_60 = cached_velov_predictions(horizon_minutes=60, force_mock=False)
    stations = get_velov_stations_geo()
    n_stations_total = len(stations) if not stations.empty else 0

    if pred_30.empty and pred_60.empty:
        st.info(
            "Aucune prédiction Vélo'v dans `gold.velov_predictions`. "
            "Lancer le DAG `retrain_velov` puis `predict_velov`."
        )
        return

    cols = st.columns(4)
    last_30 = (
        pred_30["prediction_timestamp"].max()
        if not pred_30.empty and "prediction_timestamp" in pred_30.columns
        else None
    )
    coverage_30 = pred_30["station_id"].nunique() if "station_id" in pred_30.columns else 0
    coverage_pct = f"{coverage_30}/{n_stations_total}" if n_stations_total else f"{coverage_30}"

    cols[0].metric(
        "Dernière prédiction H+30",
        str(last_30)[:16] if last_30 is not None else "—",
    )
    cols[1].metric("Stations couvertes", coverage_pct)
    cols[2].metric("Lignes H+30", f"{len(pred_30):,}")
    cols[3].metric("Lignes H+1h", f"{len(pred_60):,}")

    # Distribution + confidence
    if not pred_30.empty and "predicted_bikes" in pred_30.columns:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Distribution predicted_bikes (H+30)**")
            try:
                import plotly.express as px

                fig = px.histogram(
                    pred_30,
                    x="predicted_bikes",
                    nbins=20,
                    template="plotly_dark",
                    height=240,
                )
                fig.update_layout(margin={"l": 0, "r": 0, "t": 10, "b": 0})
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                st.bar_chart(pred_30["predicted_bikes"].value_counts().sort_index())

        with col_b:
            if {"confidence_low", "confidence_high"}.issubset(pred_30.columns):
                width = (pred_30["confidence_high"] - pred_30["confidence_low"]).dropna()
                st.markdown("**Confidence interval width (H+30)**")
                if not width.empty:
                    st.metric("Moy", f"{width.mean():.2f} vélos")
                    st.metric("Médiane", f"{width.median():.2f} vélos")
                    st.metric("p95", f"{width.quantile(0.95):.2f} vélos")
                else:
                    st.caption("Pas d'intervalles de confiance disponibles.")
            else:
                st.caption("Colonnes confidence_* absentes — modèle sans CI.")

    # Backtest MAE si gold.predictions_vs_actuals existe avec vélov
    try:
        from src.data.db_query import _df_from_query  # type: ignore

        backtest = _df_from_query(
            """
            SELECT model_name, horizon_minutes,
                   AVG(ABS(predicted - actual)) AS mae,
                   COUNT(*) AS n_obs,
                   MAX(target_timestamp) AS last_obs
            FROM gold.predictions_vs_actuals
            WHERE model_name LIKE 'xgboost_velov%%'
              AND target_timestamp >= NOW() - INTERVAL '7 days'
            GROUP BY model_name, horizon_minutes
            ORDER BY model_name, horizon_minutes
            """
        )
        if not backtest.empty:
            st.markdown("**Backtest MAE 7j (Elementary-style)**")
            st.dataframe(backtest, use_container_width=True, hide_index=True)
        else:
            st.caption("Backtest vide — alimenter `gold.predictions_vs_actuals` (DAG `evaluate_velov`).")
    except Exception as e:
        st.caption(f"Backtest indisponible : {e}")


def render_data_quality_panel() -> None:
    """Sprint 10 — Panel data quality style Elementary.

    Lit health checks + freshness pour chaque table Gold/Silver clé.
    """
    st.markdown("##### 🩺 Data Quality — freshness + volume (Elementary-style)")
    try:
        from psycopg2 import sql

        from src.data.db_query import _df_from_query  # type: ignore
    except Exception as e:
        st.caption(f"Imports indisponibles : {e}")
        return

    tables = [
        ("silver", "trafic_boucles_clean", "measurement_time", "5 min"),
        ("silver", "velov_clean", "measurement_time", "5 min"),
        ("silver", "tcl_vehicles_clean", "recorded_at", "5 min"),
        ("silver", "meteo_hourly", "measurement_time", "1h"),
        ("gold", "traffic_features_live", "measurement_time", "5 min"),
        ("gold", "trafic_predictions", "prediction_timestamp", "1h"),
        ("gold", "velov_features", "measurement_time", "5 min"),
        ("gold", "velov_predictions", "prediction_timestamp", "1h"),
        ("gold", "bus_delay_segments", "computed_at", "1h"),
    ]

    rows = []
    for schema, table, ts_col, expected in tables:
        try:
            # psycopg2.sql.Identifier pour identifier (schema/table/colonne) — SQL injection-proof.
            # ts_col est hardcodé dans la liste ci-dessus, mais on utilise Identifier par cohérence
            # avec la règle "SQL paramétré partout" du AGENTS.md.
            query = sql.SQL(
                """
                SELECT COUNT(*) AS n_rows,
                       MAX({ts_col}) AS last_ts,
                       NOW() - MAX({ts_col}) AS lag
                FROM {schema}.{table}
                """
            ).format(
                ts_col=sql.Identifier(ts_col),
                schema=sql.Identifier(schema),
                table=sql.Identifier(table),
            )
            df = _df_from_query(query)
            if df.empty:
                rows.append(
                    {
                        "Table": f"{schema}.{table}",
                        "Rows": 0,
                        "Last": "—",
                        "Lag": "—",
                        "Expected": expected,
                        "Status": "🔴",
                    }
                )
                continue
            r = df.iloc[0]
            n_rows = int(r.get("n_rows") or 0)
            last_ts = r.get("last_ts")
            lag = r.get("lag")
            lag_str = str(lag).split(".")[0] if lag is not None else "—"
            status = "🟢" if n_rows > 0 and last_ts is not None else "🔴"
            rows.append(
                {
                    "Table": f"{schema}.{table}",
                    "Rows": f"{n_rows:,}",
                    "Last": str(last_ts)[:16] if last_ts else "—",
                    "Lag": lag_str,
                    "Expected": expected,
                    "Status": status,
                }
            )
        except Exception as e:
            rows.append(
                {
                    "Table": f"{schema}.{table}",
                    "Rows": "—",
                    "Last": "—",
                    "Lag": "—",
                    "Expected": expected,
                    "Status": f"⚠️ {str(e)[:40]}",
                }
            )

    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(
        "🟢 = données présentes · 🔴 = table vide · ⚠️ = erreur SQL. "
        "Lag = ⌚ écart entre NOW() et dernière insertion. "
        "Source : queries directes sur PostgreSQL Gold/Silver."
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
    # Sprint 10 — Sections complémentaires
    st.markdown("---")
    render_velov_model_analysis()
    st.markdown("---")
    render_data_quality_panel()
