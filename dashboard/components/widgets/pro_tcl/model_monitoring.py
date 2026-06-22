"""Widget — Model Monitoring (registry MLflow, métriques, drift).

Affiche :
- Registry des modèles (XGBoost Speed, XGBoost Velov, GNN)
- Versions actives + staging
- **Sprint 8** : Status du Model Registry (XGBoost vs GNN, toggle actif)
- Métriques par modèle (MAE, RMSE, R²)
- Historique entraînement (charts) — Sprint 9+ : MLflow runs history
- Comparaison entraînement actuel vs précédent
- Drift detection status — Sprint 9+ : ``gold.model_drift_reports``

Sprint 9+ (2026-06-17) — politique "zéro mock" :
* MOCK_MODELS viré.
* ``render_drift_panel()`` lit ``get_latest_drift_report()`` (Sprint 10+).
* ``render_training_history()`` lit MLflow runs (à brancher Sprint 10+ — fallback
  explicite en attendant).
"""

from __future__ import annotations

import html

import streamlit as st

from dashboard.components.a11y import plotly_with_alt
from dashboard.components.colors import COLORS
from dashboard.components.error_display import show_error
from dashboard.components.plotly_theme import LYF_TEMPLATE


def render_model_registry() -> None:
    """Affiche la liste des modèles dans le registry."""
    st.markdown("##### 📚 Model Registry")

    from dashboard.components.data_cache import (
        cached_mlflow_experiment_summary,
        cached_mlflow_models,
    )
    from dashboard.components.loading_state import (
        data_error_to_message,
        empty_state,
        loading_wrapper,
    )
    from src.data.exceptions import DashboardDataError

    with loading_wrapper("Chargement registry MLflow…", "📊"):
        try:
            summary = cached_mlflow_experiment_summary()
            models = cached_mlflow_models()
        except DashboardDataError as e:
            empty_state(
                icon="🟡",
                title="MLflow indisponible",
                message=data_error_to_message(e),
            )
            return
        except Exception as e:
            empty_state(
                icon="🔴",
                title="MLflow a échoué",
                message=f"Registry modèles indisponible ({e}). Vérifie l'état du "
                "container `lyonflow-mlflow` (port 5000).",
            )
            return

    # Bandeau source (transparence MLflow)
    if summary.get("available"):
        st.success(
            f"🟢 **MLflow live** · {summary.get('run_count', 0)} runs · {len(summary.get('model_names', []))} modèles"
        )
    else:
        st.warning(
            "🟡 **MLflow non accessible** — aucun modèle à afficher. "
            "Pour activer en prod : démarrer le service `mlflow` (docker compose) "
            "et recharger cette page."
        )

    if not models:
        st.info("Aucun modèle tracké. Lance un training pour peupler le registry.")
        return

    # KPIs
    prod = sum(1 for m in models if m.get("stage") == "Production")
    staging = sum(1 for m in models if m.get("stage") == "Staging")

    # Sprint 10+ : drift réel depuis gold.model_drift_reports (PAS mock)
    # Lecture du dernier rapport de drift persisté par build_xgb_training_set.
    from src.data.db_query import get_latest_drift_report

    latest_drift = get_latest_drift_report()
    if latest_drift:
        n_drift = 1 if latest_drift.get("dataset_drift") else 0
        drift_share_pct = float(latest_drift.get("drift_share", 0.0)) * 100
        drift_status = "🔴 DRIFT" if latest_drift.get("dataset_drift") else "🟢 OK"
    else:
        n_drift = 0
        drift_share_pct = 0.0
        drift_status = "⚪ Pas de rapport"

    cols = st.columns(4)
    with cols[0]:
        st.metric("🟢 Production", prod)
    with cols[1]:
        st.metric("🟡 Staging", staging)
    with cols[2]:
        st.metric("Total modèles", len(models))
    with cols[3]:
        st.metric(f"🚨 Drift {drift_status}", f"{drift_share_pct:.0f}%", delta_color="inverse")

    # Détail drift (Sprint 10+ — affiche le dernier rapport PSI)
    if latest_drift:
        with st.expander("📊 Dernier rapport de drift (PSI)", expanded=False):
            st.markdown(
                f"""
                - **Dataset drift** : `{latest_drift.get("dataset_drift")}`
                - **Drift share** : `{drift_share_pct:.1f}%`
                - **N ref / current** : `{latest_drift.get("n_ref")}` / `{latest_drift.get("n_current")}`
                - **Période ref** : `{latest_drift.get("ref_from")}` → `{latest_drift.get("ref_to")}`
                - **Période current** : `{latest_drift.get("current_from")}` → `{latest_drift.get("current_to")}`
                - **Computed at** : `{latest_drift.get("computed_at")}`
                """
            )
            report = latest_drift.get("report", {})
            if report.get("per_column"):
                st.markdown("**Per-column drift** :")
                for col, stats in report["per_column"].items():
                    psi = stats.get("psi", 0)
                    status = stats.get("status", "?")
                    icon = {"stable": "🟢", "moderate": "🟡", "significant": "🔴"}.get(status, "⚪")
                    st.markdown(f"- {icon} **{col}** : PSI = {psi:.3f} ({status})")

    # Tableau (Sprint 9+ — utilise la variable `models` lue depuis MLflow live)
    _render_model_registry_table(models)


def _render_model_registry_table(models: list[dict]) -> None:
    """Tableau des modèles trackés (MLflow live)."""
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
                f'<span class="lyf-sublabel" style="background:{stage_color};color:white;padding:2px 8px;'
                f'border-radius:8px;">{m.get("stage", "—")}</span>',
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
    """Sprint 8 — Affiche le statut live du Model Registry.

    Sprint 15+ (audit Pro TCL B-20) : le modèle GNN/STGCN est paused
    (DAG ``retrain_gnn`` désactivé, modèle pas réentraîné). On ne
    montre plus ses traces dans le dashboard pour éviter l'affichage
    ``GNN H+60min dispo = ❌`` trompeur. Le code ModelRegistry reste
    en place (rétro-compat) mais l'UI n'expose plus que XGBoost.

    Section ajoutée pour permettre à Patrice de visualiser en temps réel
    le statut du modèle XGBoost actif en prod.
    """
    st.markdown("##### 🎛️ Model Registry Status (live)")

    # Import paresseux pour ne pas casser en cas de modèle manquant
    try:
        from src.ml.model_registry import (
            ModelRegistry,
            is_xgboost_training_enabled,
        )
    except ImportError as e:
        st.warning(f"Model Registry indispo : {e}")
        return

    # Sprint 15+ (audit B-20) : XGBoost est désormais l'unique modèle
    # de trafic exposé. Le badge reflète l'état binaire (actif / paused).
    is_active = is_xgboost_training_enabled()
    if is_active:
        badge_color = COLORS["status_ok"]
        badge_text = "🟢 XGBOOST ACTIF (prod)"
    else:
        badge_color = COLORS["status_critical"]
        badge_text = "🔴 XGBOOST PAUSED — vérifier DAG ``dag_daily_speed_train``"

    st.markdown(
        f'<div style="background:{badge_color};color:white;padding:0.5rem 1rem;'
        f'border-radius:6px;margin-bottom:0.8rem;font-weight:600;">'
        f"{badge_text}</div>",
        unsafe_allow_html=True,
    )

    # Toggles status — Sprint 15+ : 2 colonnes (XGBoost retrain + dispo H+1h)
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            "XGBoost retrain",
            "ON" if is_active else "OFF",
            delta="nightly" if is_active else "paused",
            delta_color="normal" if is_active else "inverse",
        )
    with col2:
        # Show 1 horizon representative
        r60 = ModelRegistry.get(60)
        st.metric(
            "XGB H+60min dispo",
            "✅" if r60.xgboost and r60.xgboost.is_available() else "❌",
        )

    # Detail table
    st.markdown("---")
    st.markdown("**Status par horizon (Sprint 8+ : focus H+1h)**")
    # Sprint 8+ — seul H+1h (60 min) est entraîné. Les autres
    # horizons sont conservés dans la liste pour le monitoring
    # (compat ModelRegistry) mais marqués "non entraînés".
    horizons = [60]
    for h in horizons:
        reg = ModelRegistry.get(h)
        s = reg.status()
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown(f"**H+{h}min**")
        with col2:
            color = COLORS["status_ok"] if s["xgboost_available"] else COLORS["text_disabled"]
            st.markdown(
                f'<span style="color:{color};">●</span> XGBoost',
                unsafe_allow_html=True,
            )

    # Note Sprint 9+ : le tableau détaillé des modèles est rendu par
    # `render_model_registry()` (au-dessus), qui lit MLflow live.
    # On évite la duplication ici.


def render_metrics_comparison() -> None:
    """Affiche les métriques du modèle XGBoost (focus H+1h).

    Sprint 15+ (audit Pro TCL B-20) : le modèle GNN/STGCN est paused
    et n'est plus affiché. Cette section montre les métriques du
    champion XGBoost uniquement.
    """
    st.markdown("##### 📊 Métriques XGBoost Speed H+60min")

    from dashboard.components.data_cache import cached_mlflow_models
    from src.data.exceptions import DashboardDataError

    try:
        models = cached_mlflow_models()
    except DashboardDataError as e:
        show_error("db_down", str(e))
        return
    except Exception as e:
        show_error("db_down", f"🔴 MLflow a échoué — métriques modèles indisponibles ({e}).")
        return

    if not models:
        st.info("Aucun modèle tracké dans MLflow pour le moment.")
        return

    xgb_h60 = next((m for m in models if m.get("name") == "xgboost_speed_h60"), None)

    if not xgb_h60:
        st.info("Modèle XGBoost H+60min non trouvé dans le registry.")
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

    st.markdown("**XGBoost Speed H+60min (Champion)**")
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("MAE", f"{_mae(xgb_h60):.2f} km/h")
        st.metric("Samples", f"{_samples(xgb_h60):,}")
    with col_b:
        st.metric("R²", f"{_r2(xgb_h60):.3f}")
        st.metric("Features", _features(xgb_h60))

    st.caption(
        "💡 Modèle focus H+1h, réentraîné nightly par "
        "``dag_daily_speed_train``. Sprint 15+ : GNN/STGCN paused, "
        "les traces ont été retirées du dashboard."
    )


def render_training_history() -> None:
    """Affiche l'historique des entraînements (charts).

    Sprint 9+ (2026-06-17) — viré le mock ``mae_speed_h60 = [...]`` etc.
    Lit MLflow runs history (DAG ``retrain_xgboost`` + ``retrain_velov``).
    Branchement Sprint 10+ — fallback explicite en attendant.
    """
    st.markdown("##### 📈 Historique entraînement (7 derniers jours)")

    # Sprint 9+ — placeholder explicite. Branchement MLflow runs history
    # prévu Sprint 10+ (nécessite ``mlflow.search_runs()`` côté widget).
    # Plus de données hardcodées : la règle "zéro mock" prime.
    try:
        from src.data.db_query import _df_from_query  # type: ignore

        history = _df_from_query(
            """
            SELECT
                DATE_TRUNC('day', start_time) AS day,
                run_name,
                metrics_mae_speed_h1 AS mae_speed,
                metrics_mae_velov_h30 AS mae_velov
            FROM mlflow.runs_history
            WHERE start_time >= NOW() - INTERVAL '7 days'
            ORDER BY start_time ASC
            """
        )
        if history.empty:
            st.info(
                "Historique entraînement vide — branche Sprint 10+. "
                "DAG `retrain_xgboost` (quotidien 03h00) et `retrain_velov` "
                "(horaire :50) alimentent `mlflow.runs_history`."
            )
            return
        try:
            import plotly.graph_objects as go

            fig = go.Figure()
            speed_rows = history.dropna(subset=["mae_speed"])
            velov_rows = history.dropna(subset=["mae_velov"])
            if not speed_rows.empty:
                fig.add_trace(
                    go.Scatter(
                        x=speed_rows["day"],
                        y=speed_rows["mae_speed"],
                        mode="lines+markers",
                        name="XGBoost Speed H+1h",
                        line={"color": COLORS["status_ok"], "width": 3},
                    )
                )
            if not velov_rows.empty:
                fig.add_trace(
                    go.Scatter(
                        x=velov_rows["day"],
                        y=velov_rows["mae_velov"],
                        mode="lines+markers",
                        name="XGBoost Velov H+30min",
                        line={"color": COLORS["status_warning"], "width": 3},
                        yaxis="y2",
                    )
                )
            fig.update_layout(
                title="MAE evolution (7 derniers jours)",
                xaxis_title="Jour",
                yaxis_title="MAE Speed (km/h)",
                yaxis2={"title": "MAE Velov (vélos)", "overlaying": "y", "side": "right"},
                template=LYF_TEMPLATE,
                height=350,
            )
            plotly_with_alt(fig, use_container_width=True)
        except ImportError:
            st.dataframe(history, use_container_width=True, hide_index=True)
    except Exception as e:
        st.info(f"Historique entraînement indisponible ({e}). Branchement MLflow runs history prévu Sprint 10+.")


def render_drift_panel() -> None:
    """Affiche le statut de drift detection par modèle.

    Sprint 9+ (2026-06-17) — lit ``get_latest_drift_report()``
    (table ``gold.model_drift_reports``, persistée par
    ``build_xgb_training_set``). Plus de mock ``drifts = [...]``.
    """
    st.markdown("##### 🌊 Drift Detection")

    from src.data.db_query import get_latest_drift_report

    report = get_latest_drift_report()
    if not report:
        st.info(
            "Aucun rapport de drift disponible. "
            "Le DAG `build_xgb_training_set` (quotidien 02h30) génère un "
            "rapport Evidently dans `gold.model_drift_reports`."
        )
        return

    dataset_drift = bool(report.get("dataset_drift"))
    drift_share = float(report.get("drift_share", 0.0)) * 100
    status = "critical" if dataset_drift else ("warning" if drift_share > 10 else "ok")
    color = {
        "ok": COLORS["status_ok"],
        "warning": COLORS["status_warning"],
        "critical": COLORS["status_critical"],
    }.get(status, COLORS["text_muted"])
    icon = {"ok": "🟢", "warning": "🟡", "critical": "🔴"}.get(status, "⚪")

    # Sprint 15+ (audit Pro TCL B-15) : ``report.get(..., "—")`` retourne
    # ``"—"`` SEULEMENT si la clé est absente. Si la clé existe avec
    # valeur ``None``, Python renvoie ``None`` (pas le défaut). On utilise
    # ``or "—"`` pour gérer les deux cas.
    n_ref = report.get("n_ref") or "—"
    n_cur = report.get("n_current") or "—"
    ref_from = report.get("ref_from") or "—"
    ref_to = report.get("ref_to") or "—"
    cur_from = report.get("current_from") or "—"
    cur_to = report.get("current_to") or "—"
    computed_at = report.get("computed_at") or "—"

    per_column_html = ""
    report_payload = report.get("report", {})
    if report_payload.get("per_column"):
        for col, stats in report_payload["per_column"].items():
            try:
                psi = float(stats.get("psi", 0))
            except (TypeError, ValueError):
                psi = 0.0
            col_status = stats.get("status", "?")
            col_icon = {"stable": "🟢", "moderate": "🟡", "significant": "🔴"}.get(col_status, "⚪")
            # Sprint 15+ (audit Pro TCL B-08) : escape nom de colonne et
            # status pour éviter que des caractères spéciaux (`<`, `>`, `&`)
            # ne cassent le parsing HTML de Streamlit.
            safe_col = html.escape(str(col))
            safe_status = html.escape(str(col_status))
            per_column_html += (
                f'<div style="font-size:0.8rem;margin-top:0.2rem;">'
                f"{col_icon} <code>{safe_col}</code> : PSI = {psi:.3f} ({safe_status})</div>"
            )

    action_text = ""
    if dataset_drift:
        action_text = (
            '<div style="font-size:0.8rem;margin-top:0.4rem;color:var(--status-critical);">'
            "→ Drift dataset détecté — investigation requise, retrain à planifier"
            "</div>"
        )
    elif drift_share > 10:
        action_text = (
            '<div style="font-size:0.8rem;margin-top:0.4rem;color:var(--status-warning);">'
            "→ Drift modéré — surveiller l'évolution sur 24-48h"
            "</div>"
        )

    st.markdown(
        f"""
        <div style="background:var(--bg-card);border:1px solid var(--border-card);border-left:4px solid {color};
                    border-radius:6px;padding:0.7rem;margin:0.4rem 0;">
            <div style="display:flex;align-items:center;gap:0.6rem;">
                <div class="lyf-value">{icon}</div>
                <div style="flex:1;">
                    <div style="font-weight:600;">XGBoost Speed H+1h</div>
                    <div style="font-size:0.8rem;opacity:0.7;">
                        Drift score: {drift_share:.1f}% features drifteés
                        · N ref/cur: {n_ref}/{n_cur}
                        · {computed_at}
                    </div>
                    <div style="font-size:0.8rem;opacity:0.7;margin-top:0.2rem;">
                        Réf: {ref_from} → {ref_to} · Current: {cur_from} → {cur_to}
                    </div>
                    {per_column_html}
                    {action_text}
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

    pred_30 = cached_velov_predictions(horizon_minutes=30)
    pred_60 = cached_velov_predictions(horizon_minutes=60)
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
                    template=LYF_TEMPLATE,
                    height=240,
                )
                fig.update_layout(margin={"l": 0, "r": 0, "t": 10, "b": 0})
                plotly_with_alt(fig, use_container_width=True)
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
        ("gold", "trafic_predictions", "calculated_at", "1h"),
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
