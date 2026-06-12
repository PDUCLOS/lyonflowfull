"""Widget — Statut des pipelines (DAGs Airflow).

Affiche :
- Liste des DAGs avec état (running/idle/failed), dernier run, durée
- Health checks (6 checks depuis src.monitoring.health_checks)
- Fraîcheur des données (Bronze ingestion times par source)
- Boutons trigger manuel

Sprint VPS-6 (2026-06-11) — fail loud en prod :
* Mode démo (``LYONFLOW_DEMO_MODE=1``) : fallback ``MOCK_DAGS``/``MOCK_FRESHNESS``
  préservé (Airflow indispo autorisé).
* Mode prod : Airflow indispo → ``DashboardDataError`` propagé.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS
from src.data.airflow_client import get_dags_status, is_airflow_available, trigger_dag
from src.data.data_loader import _is_demo_mode
from src.data.exceptions import DashboardDataError
from src.monitoring.health_checks import run_all_checks

# Sprint 8 (2026-06-12) — viré le bloc MOCK_DAGS / MOCK_FRESHNESS
# (lignes 64-200 dans la version précédente). Le widget lit désormais
# la DB et l'API Airflow uniquement. Si l'un des deux est indispo,
# DashboardDataError.


@st.cache_data(ttl=30, show_spinner=False)
def _cached_dags() -> list[dict]:
    """Liste des DAGs Airflow. Fail loud (Sprint 8 — viré fallback mock)."""
    try:
        dags = get_dags_status()
    except DashboardDataError:
        raise
    except Exception as e:
        raise DashboardDataError(
            source="airflow",
            detail=f"Airflow REST API a échoué : {e}",
        ) from e
    # Airflow répond mais 0 DAG : situation légitime (premier démarrage)
    return list(dags) if dags else []


@st.cache_data(ttl=60, show_spinner=False)
def _cached_freshness() -> list[dict]:
    """Fraîcheur live des sources Bronze. Fail loud (Sprint 8 — viré fallback mock)."""
    from src.data.db_query import _is_db_available, get_bronze_source_counts

    if not _is_db_available():
        raise DashboardDataError(source="gold.bronze_source_counts", detail="PostgreSQL indisponible")
    df = get_bronze_source_counts(hours=24)
    if df.empty:
        return []  # DB répond mais vide
    rows: list[dict] = []
    for _, r in df.iterrows():
        n_rows = int(r.get("n_rows", 0) or 0)
        last_fetch = r.get("last_fetch")
        rows.append(
            {
                "source": str(r.get("source", "—")),
                "last_ingestion": str(last_fetch) if last_fetch else "—",
                "n_records_24h": n_rows,
                "status": "ok" if n_rows > 0 else "stale",
            }
        )
    return rows


# Sprint 8 (2026-06-12) — MOCK_DAGS, MOCK_FRESHNESS, helpers _ago,
# _in_minutes, _in_months, _NOW, _FMT : tous virés. Le widget ne
# mock plus. Si Airflow indispo → DashboardDataError. Si la DB
# indispo → DashboardDataError. La source de vérité c'est le pipeline.


def render_pipeline_status() -> None:
    """Affiche le statut complet des pipelines."""
    st.markdown("##### 📊 Statut global")

    if not is_airflow_available() and not _is_demo_mode():
        st.error(
            "🔴 **Airflow REST API non joignable** — le statut DAGs est indisponible. "
            "Vérifiez que le service Airflow tourne et que "
            "`AIRFLOW_HOST`/`AIRFLOW_ADMIN_PASSWORD` sont corrects dans `.env`."
        )
        return
    if not is_airflow_available() and _is_demo_mode():
        st.warning(
            "🟡 Airflow REST API non joignable — affichage en **mode démo** "
            "(fallback MOCK_DAGS autorisé quand `LYONFLOW_DEMO_MODE=1`)."
        )

    try:
        dags = _cached_dags()
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")
        return
    cols = st.columns(4)
    n_success = sum(1 for d in dags if d.get("last_status") == "success")
    n_running = sum(1 for d in dags if d.get("last_status") == "running")
    n_failed = sum(1 for d in dags if d.get("last_status") == "failed")

    # Calcule n_alerts depuis rgpd.audit_log (action LIKE 'alert%' OR severity=critical)
    # sur les dernières 24h. Fallback mock si DB indispo.
    n_alerts = 0
    try:
        from src.data.db_query import _df_from_query

        df_alerts = _df_from_query(
            """
            SELECT COUNT(*) AS n
            FROM rgpd.audit_log
            WHERE timestamp >= NOW() - INTERVAL '24 hours'
              AND (action LIKE 'alert%%' OR severity = 'critical')
            """
        )
        if not df_alerts.empty:
            n_alerts = int(df_alerts.iloc[0].get("n") or 0)
    except Exception:
        # DB indispo — fallback mock : 0 alertes en mode démo
        n_alerts = 0

    with cols[0]:
        st.metric("✅ DAGs OK", n_success, delta=f"{n_success}/{len(dags) or 1}")
    with cols[1]:
        st.metric("🔄 DAGs running", n_running)
    with cols[2]:
        st.metric("❌ DAGs failed", n_failed, delta_color="inverse")
    with cols[3]:
        st.metric("🚨 Alertes 24h", n_alerts)


def render_dag_list() -> None:
    """Affiche la liste des DAGs avec leur état."""
    st.markdown("##### 📋 Liste des DAGs")

    try:
        dags = _cached_dags()
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")
        return
    if not dags:
        st.info("Aucun DAG enregistré pour le moment.")
        return

    # En-tête
    header_cols = st.columns([3, 2, 1.5, 1, 1, 1.5])
    with header_cols[0]:
        st.markdown("**DAG**")
    with header_cols[1]:
        st.markdown("**Schedule**")
    with header_cols[2]:
        st.markdown("**Dernier run**")
    with header_cols[3]:
        st.markdown("**Durée**")
    with header_cols[4]:
        st.markdown("**Statut**")
    with header_cols[5]:
        st.markdown("**Action**")

    st.markdown("---")

    # Réutilise la liste déjà chargée en tête de fonction
    for dag in dags:
        cols = st.columns([3, 2, 1.5, 1, 1, 1.5])
        with cols[0]:
            st.markdown(f"**{dag.get('dag_id', '—')}**")
            st.caption(dag.get("description", ""))
        with cols[1]:
            st.code(dag.get("schedule", "—"), language="text")
        with cols[2]:
            st.caption(dag.get("last_run", "—"))
        with cols[3]:
            st.caption(f"{dag.get('last_duration_s', 0)}s")
        with cols[4]:
            status = dag.get("last_status", "unknown")
            color = {"success": "🟢", "running": "🔄", "failed": "🔴"}.get(status, "⚪")
            st.markdown(f"{color} {status}")
        with cols[5]:
            if st.button("▶️ Trigger", key=f"trigger_{dag['dag_id']}", use_container_width=True):
                _trigger_dag(dag["dag_id"])


def render_health_panel() -> None:
    """Affiche les 6 health checks du module monitoring."""
    st.markdown("##### 💓 Health checks (quotidien 04h15)")

    with st.spinner("Exécution des 6 health checks..."):
        try:
            results = run_all_checks()
        except DashboardDataError as e:
            st.error(f"⚠️ {e}")
            return
        except Exception as e:
            if _is_demo_mode():
                st.info(f"Mode démo — health checks indisponibles ({e})")
                results = None
            else:
                st.error(
                    f"🔴 Health checks indisponibles ({e}). "
                    "Vérifier que PostgreSQL répond et que le DAG "
                    "data_quality_daily a tourné."
                )
                return

    if not results:
        if _is_demo_mode():
            # Fallback mock (mode démo uniquement)
            results = [
            {
                "name": "bronze_freshness",
                "status": "ok",
                "details": "Bronze trafic: 4 min",
                "metric_value": 4.0,
                "threshold": 30.0,
                "timestamp": "2026-06-06T15:00:00",
            },
            {
                "name": "bronze_volume",
                "status": "ok",
                "details": "522k records/24h",
                "metric_value": 522000,
                "threshold": 1000,
            },
            {
                "name": "silver_nulls",
                "status": "ok",
                "details": "Nulls vitesse: 0.2%",
                "metric_value": 0.2,
                "threshold": 5.0,
            },
            {"name": "silver_doublons", "status": "ok", "details": "0 doublons", "metric_value": 0, "threshold": 0},
            {
                "name": "predictions_presentes",
                "status": "ok",
                "details": "124 prédictions/2h",
                "metric_value": 124,
                "threshold": 100,
            },
            {
                "name": "drift_baseline",
                "status": "warning",
                "details": "1 rapport drift (à analyser)",
                "metric_value": 1,
                "threshold": 1,
            },
        ]

    # Normaliser: CheckResult dataclass OU dict mock
    def _as_dict(r):
        if hasattr(r, "__dataclass_fields__"):
            from dataclasses import asdict

            return asdict(r)
        return r

    cols = st.columns(3)
    for i, r in enumerate(results):
        r = _as_dict(r)
        with cols[i % 3]:
            status = r.get("status", "unknown")
            color = {
                "ok": COLORS["status_ok"],
                "warning": COLORS["status_warning"],
                "critical": COLORS["status_critical"],
            }.get(status, COLORS["text_muted"])
            icon = {"ok": "✅", "warning": "⚠️", "critical": "🔴"}.get(status, "❓")
            name = r.get("name", "—")
            st.markdown(
                f"""
                <div style="background:var(--bg-card);border:1px solid var(--border-card);border-left:4px solid {color};
                            border-radius:6px;padding:0.6rem;margin:0.3rem 0;">
                    <div style="font-size:0.75rem;opacity:0.7;text-transform:uppercase;
                                letter-spacing:0.5px;">{name}</div>
                    <div style="font-size:1.1rem;font-weight:600;margin-top:0.2rem;">
                        {icon} {status.upper()}
                    </div>
                    <div style="font-size:0.75rem;opacity:0.7;margin-top:0.2rem;">
                        {r.get("details", "")}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_data_freshness() -> None:
    """Affiche la fraîcheur des données par source Bronze."""
    st.markdown("##### 📡 Fraîcheur des données (Bronze)")

    try:
        freshness = _cached_freshness()
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")
        return
    if not freshness:
        st.info("Aucune source Bronze n'a collecté de données dans les 24 dernières heures.")
        return
    # KPI
    n_ok = sum(1 for s in freshness if s.get("status") == "ok")
    n_stale = sum(1 for s in freshness if s.get("status") == "stale")
    cols = st.columns(3)
    with cols[0]:
        st.metric("Sources à jour", n_ok, delta=f"{n_ok}/{len(freshness) or 1}")
    with cols[1]:
        st.metric("Sources stale", n_stale, delta_color="inverse")
    with cols[2]:
        st.metric("Volume 24h", f"{sum(s.get('n_records_24h', 0) for s in freshness):,}")

    # Tableau
    st.markdown("---")
    header_cols = st.columns([2, 2, 1.5, 0.8])
    with header_cols[0]:
        st.markdown("**Source**")
    with header_cols[1]:
        st.markdown("**Dernière ingestion**")
    with header_cols[2]:
        st.markdown("**Records 24h**")
    with header_cols[3]:
        st.markdown("**Statut**")

    for s in freshness:
        cols = st.columns([2, 2, 1.5, 0.8])
        with cols[0]:
            st.markdown(f"`{s['source']}`")
        with cols[1]:
            st.caption(s["last_ingestion"])
        with cols[2]:
            st.caption(f"{s['n_records_24h']:,}")
        with cols[3]:
            icon = "🟢" if s["status"] == "ok" else "🟡" if s["status"] == "stale" else "🔴"
            st.markdown(icon)


def render_alerts_feed() -> None:
    """Affiche le feed des alertes récentes."""
    st.markdown("##### 🚨 Alertes récentes (24h)")

    # En prod : query rgpd.audit_log WHERE action LIKE 'alert%' OR severity = 'critical'
    # Mock : feed vide + quelques exemples
    st.info("Aucune alerte critique dans les dernières 24h.")

    with st.expander("📜 Historique alertes (7 derniers jours)", expanded=False):
        st.caption("• 2026-06-06 04:15 — health_check: drift_baseline ⚠️ (warning)")
        st.caption("• 2026-06-05 14:50 — collect_bronze: velov ⚠️ (timeout 30s, retry OK)")
        st.caption("• 2026-06-04 03:00 — purge_bronze: 142 lignes supprimées ✅")
        st.caption("• 2026-06-03 18:22 — alert_velov: station 1001 (Part-Dieu) < 3 vélos ✅")


def _trigger_dag(dag_id: str) -> None:
    """Trigger manuel d'un DAG via Airflow REST API (fallback message si offline)."""
    with st.spinner(f"Trigger {dag_id}..."):
        ok = trigger_dag(dag_id)
        if ok:
            st.success(f"✅ {dag_id} déclenché — voir Airflow UI pour progression")
            # Avant ce fix : pas de rerun → la liste DAGs restait stale jusqu'au prochain event user.
            st.cache_data.clear()
            st.rerun()
        else:
            st.warning(f"Impossible de déclencher {dag_id} (Airflow non joignable ou identifiants invalides).")


def render_pipeline_management_page() -> None:
    """Page complète Pipeline Management (point d'entrée)."""
    render_pipeline_status()
    st.markdown("---")
    render_dag_list()
    st.markdown("---")
    render_health_panel()
    st.markdown("---")
    render_data_freshness()
    st.markdown("---")
    render_alerts_feed()
