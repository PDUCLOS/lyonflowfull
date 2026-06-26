"""Widget — Carte trafic temps réel vs prédictions H+1h.

 refonte complète :
* Couleur **relative** : ratio vitesse / vitesse_limite (pas de seuils fixes).
  Un segment à 50% de sa limite est orange, qu'il soit limité à 30 ou 90 km/h.
* **Comparaison live ↔ H+1h** : tooltip affiche vitesse actuelle, prédite,
  et delta (flèche tendance). Couleur = ratio actuel.
* Source : ``get_traffic_live_vs_predicted()`` — JOIN live × predictions.
* Pro_7 Model Monitoring garde la source prédictions seules.

Trois entrées publiques :
* ``render_traffic_map(...)``        — carte plein-format (Pro_1).
* ``render_traffic_map_compact(...)`` — version réduite (Usager_1, Elu_1).
* ``render_gnn_map_section()``       — section dédiée Pro_7 (prédictions seules).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.loading_state import loading_wrapper
from src.ml.mlflow_integration import is_mlflow_available
from src.ml.model_registry import is_gnn_map_visible, is_stgcn_enabled
from src.models.stgcn_wrapper import STGCNWrapper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Color helpers — ratio-based (relative to speed limit)
# ---------------------------------------------------------------------------
def _ratio_to_rgb(ratio: float | None) -> list[int]:
    """Ratio vitesse/limite → couleur RGB.

    ratio ≈ 0.0 → rouge (bloqué)
    ratio ≈ 0.4 → orange (dense)
    ratio ≈ 0.65 → jaune (modéré)
    ratio ≈ 0.85+ → vert (fluide)
    """
    if ratio is None:
        return [128, 128, 128]
    if ratio < 0.3:
        return [231, 76, 60]
    if ratio < 0.5:
        return [255, 152, 0]
    if ratio < 0.75:
        return [255, 193, 7]
    return [76, 175, 80]


def _delta_arrow(delta: float | None) -> str:
    if delta is None:
        return "—"
    if delta > 3:
        return f"↗ +{delta:.0f}"
    if delta < -3:
        return f"↘ {delta:.0f}"
    return f"→ {delta:+.0f}"


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------
def _load_live_vs_predicted(limit: int = 2000) -> pd.DataFrame | None:
    from dashboard.components.data_cache import cached_traffic_live_vs_predicted

    df = cached_traffic_live_vs_predicted(limit=limit)
    if df.empty:
        return None
    valid = df.dropna(subset=["lat", "lon"])
    return valid if not valid.empty else None


def _load_predictions(horizon: int, limit: int = 1500) -> pd.DataFrame | None:
    from src.data.data_loader import load_traffic_predictions_for_map

    preds_df = load_traffic_predictions_for_map(horizon_minutes=horizon, limit=limit)
    if preds_df.empty:
        return None

    if "lat" in preds_df.columns and "lon" in preds_df.columns:
        valid = preds_df.dropna(subset=["lat", "lon"])
        return valid if not valid.empty else None

    from dashboard.components.data_cache import cached_spatial_mapping

    mapping_df = cached_spatial_mapping()
    if mapping_df.empty:
        return None

    if "axis_key" in preds_df.columns and "channel_id" in mapping_df.columns:
        mapping_df = mapping_df.copy()
        mapping_df["channel_id"] = mapping_df["channel_id"].astype(str)
        preds_df = preds_df.copy()
        preds_df["axis_key"] = preds_df["axis_key"].astype(str)
        merged = mapping_df.merge(preds_df, left_on="channel_id", right_on="axis_key", how="inner")
    elif "node_idx" in preds_df.columns:
        merged = mapping_df.merge(preds_df, on="node_idx", how="inner")
    else:
        return None

    return merged if not merged.empty else None


def _check_gnn_model(horizon: int) -> dict:
    try:
        wrapper = STGCNWrapper.get(horizon)
        if wrapper.load():
            return {"loaded": True, "reason": "OK", "fallback": "SpatioTemporalGCN"}
        return {
            "loaded": False,
            "reason": f"Modèle .pt absent pour H+{horizon}min.",
            "fallback": "XGBoost (fallback)",
        }
    except Exception as e:  # pragma: no cover
        return {"loaded": False, "reason": str(e), "fallback": "XGBoost (fallback)"}


# ---------------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------------
def _freshness_line(df: pd.DataFrame, ts_col: str = "live_at") -> None:
    if ts_col not in df.columns:
        for fallback in ("computed_at", "calculated_at"):
            if fallback in df.columns:
                ts_col = fallback
                break
        else:
            return
    latest = pd.to_datetime(df[ts_col]).max()
    if pd.isna(latest):
        return
    now = datetime.now(tz=timezone.utc)
    if latest.tzinfo is None:
        from zoneinfo import ZoneInfo
        latest = latest.replace(tzinfo=ZoneInfo("UTC"))
    age_s = (now - latest).total_seconds()
    if age_s < 300:
        st.caption(f"🟢 Live — dernière mesure il y a {int(age_s // 60)} min")
    elif age_s < 1800:
        st.caption(f"🟡 Récent — dernière mesure il y a {int(age_s // 60)} min")
    else:
        st.caption(f"🔴 Ancien — dernière mesure il y a {age_s / 3600:.1f}h — vérifier DAGs")


# ---------------------------------------------------------------------------
# Pydeck renderers
# ---------------------------------------------------------------------------
def _render_pydeck_live_vs_pred(df: pd.DataFrame, height: int, zoom: float = 11.0) -> None:
    """Carte avec couleur ratio + tooltip live vs prédit."""
    try:
        import pydeck as pdk
    except ImportError:
        st.warning("Pydeck non installé — fallback tableau.")
        cols = [c for c in ["channel_id", "speed_now", "speed_pred_1h", "ratio_now", "delta_kmh"] if c in df.columns]
        st.dataframe(df[cols].head(50), use_container_width=True, hide_index=True)
        return

    df = df.copy()
    df["color"] = df["ratio_now"].apply(lambda r: [*_ratio_to_rgb(r), 210])

    if "vitesse_limite_kmh" in df.columns:
        df["_radius"] = df["vitesse_limite_kmh"].fillna(50).clip(30, 130).astype(int)
    else:
        df["_radius"] = 90

    df["speed_now_fmt"] = df["speed_now"].round(0).astype(int, errors="ignore")
    df["speed_pred_fmt"] = df["speed_pred_1h"].round(0).astype(int, errors="ignore")
    df["ratio_pct"] = (df["ratio_now"].fillna(0) * 100).round(0).astype(int, errors="ignore")
    df["delta_arrow"] = df["delta_kmh"].apply(_delta_arrow)

    tooltip_html = (
        "<b>{channel_id}</b><br/>"
        "Maintenant : <b>{speed_now_fmt} km/h</b> ({ratio_pct}% de limite)<br/>"
        "Prédit H+1h : <b>{speed_pred_fmt} km/h</b><br/>"
        "Tendance : <b>{delta_arrow} km/h</b>"
    )

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position=["lon", "lat"],
        get_color="color",
        get_radius="_radius",
        pickable=True,
    )
    view_state = pdk.ViewState(latitude=45.76, longitude=4.84, zoom=zoom, pitch=0)
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip={
            "html": tooltip_html,
            "style": {
                "backgroundColor": COLORS["bg_card"],
                "color": "white",
                "padding": "8px",
                "borderRadius": "4px",
            },
        },
    )
    st.pydeck_chart(deck, use_container_width=True, height=height)


def _render_pydeck_predictions(df: pd.DataFrame, height: int, zoom: float = 11.0) -> str:
    """Rendu pydeck pour prédictions seules (Pro_7 Model Monitoring)."""
    try:
        import pydeck as pdk
    except ImportError:
        st.warning("Pydeck non installé — fallback tableau.")
        cols = [c for c in ["axis_key", "lat", "lon", "speed_pred", "model_version"] if c in df.columns]
        st.dataframe(df[cols].head(50), use_container_width=True, hide_index=True)
        return "?"

    df = df.copy()
    speed_col = "speed_pred" if "speed_pred" in df.columns else "predicted_speed"

    if "vitesse_limite_kmh" in df.columns:
        df["_ratio"] = (df[speed_col] / df["vitesse_limite_kmh"].replace(0, pd.NA)).fillna(0.5)
    else:
        df["_ratio"] = 0.5
    df["color"] = df["_ratio"].apply(lambda r: [*_ratio_to_rgb(r), 220])

    model_col = "model_version" if "model_version" in df.columns else "model_name"
    dominant_model = (
        df[model_col].mode().iloc[0] if model_col in df.columns and not df[model_col].mode().empty else "?"
    )

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position=["lon", "lat"],
        get_color="color",
        get_radius=100,
        pickable=True,
    )
    view_state = pdk.ViewState(latitude=45.76, longitude=4.84, zoom=zoom, pitch=0)
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip={
            "html": "<b>{axis_key}</b><br/>Prédit : <b>{speed_pred} km/h</b><br/>État: {etat_pred}",
            "style": {
                "backgroundColor": COLORS["bg_card"],
                "color": "white",
                "padding": "8px",
                "borderRadius": "4px",
            },
        },
    )
    st.pydeck_chart(deck, use_container_width=True, height=height)
    return dominant_model


def _legend_ratio() -> None:
    st.markdown(
        "**Légende** (% de la vitesse limite) : "
        "🟢 >75% · 🟡 50-75% · 🟠 30-50% · 🔴 <30%"
    )


def _stats_bar(df: pd.DataFrame) -> None:
    """KPI bar : ratio moyen, segments en dégradation, segments améliorés."""
    if "ratio_now" not in df.columns or "delta_kmh" not in df.columns:
        return
    valid = df.dropna(subset=["ratio_now"])
    if valid.empty:
        return
    ratio_mean = valid["ratio_now"].mean()
    n_degrade = (valid["delta_kmh"] < -5).sum()
    n_improve = (valid["delta_kmh"] > 5).sum()
    n_total = len(valid)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fluidité réseau", f"{ratio_mean:.0%}")
    c2.metric("Segments", n_total)
    c3.metric("↘ Dégradation H+1h", int(n_degrade))
    c4.metric("↗ Amélioration H+1h", int(n_improve))


# ---------------------------------------------------------------------------
# API publique : carte plein-format — live vs prédit
# ---------------------------------------------------------------------------
def render_traffic_map(
    *,
    height: int = 450,
    horizon_default: int = 60,
    show_horizon_selector: bool = True,
    show_legend: bool = True,
    show_caption: bool = True,
    key_suffix: str = "",
) -> None:
    with loading_wrapper("Chargement carte trafic…", "⏳"):
        if not is_gnn_map_visible():
            st.info("Carte trafic désactivée. Set `LYONFLOW_DASHBOARD_GNN_MAP=true` dans .env.")
            return

        df = _load_live_vs_predicted(limit=2000)
        if df is None:
            st.info(
                "Pas de données trafic. Vérifie que les capteurs live alimentent "
                "`gold.traffic_features_live` (DAG collecte */5 min)."
            )
            return

        _freshness_line(df)
        _stats_bar(df)
        _render_pydeck_live_vs_pred(df, height=height)
        if show_legend:
            _legend_ratio()


# ---------------------------------------------------------------------------
# API publique : carte compacte (Usager / Elu)
# ---------------------------------------------------------------------------
def render_traffic_map_compact(
    *,
    height: int = 280,
    horizon_minutes: int = 60,
    key_suffix: str = "",
) -> None:
    with loading_wrapper("Chargement carte trafic…", "⏳"):
        if not is_gnn_map_visible():
            return

        df = _load_live_vs_predicted(limit=1500)
        if df is None:
            st.caption("🟡 Carte trafic indisponible (aucune donnée capteur)")
            return

        _freshness_line(df)
        _render_pydeck_live_vs_pred(df, height=height, zoom=10.7)
        _legend_ratio()


# ---------------------------------------------------------------------------
# API publique : Pro_7 Model Monitoring — prédictions seules (ratio-based)
# ---------------------------------------------------------------------------
def render_gnn_map_section() -> None:
    with loading_wrapper("Chargement carte modèle…", "⏳"):
        st.markdown("##### 🗺️ Carte trafic — prédictions spatiales (modèle)")

        if not is_gnn_map_visible():
            st.markdown(
                """
                <div style="background:linear-gradient(135deg, var(--border-card) 0%, var(--persona-elu) 100%);
                            border:1px dashed var(--persona-elu-accent);border-radius:8px;padding:1rem;margin:0.5rem 0;">
                    <div style="font-size:0.8rem;opacity:0.8;text-transform:uppercase;
                                letter-spacing:1px;">🟡 Carte désactivée</div>
                    <div class="lyf-label" style="margin:0.5rem 0;">
                        Set <code>LYONFLOW_DASHBOARD_GNN_MAP=true</code> dans .env pour activer.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return

        if not is_stgcn_enabled():
            st.warning("STGCN désactivé dans LYONFLOW_MODELS_ACTIVE — carte non disponible.")
            return
        if not is_mlflow_available():
            st.warning("MLflow non disponible — prédictions non récupérables.")
            return

        horizon = 60
        if is_stgcn_enabled() and is_mlflow_available():
            status = _check_gnn_model(horizon)
            if not status["loaded"]:
                st.caption(f"⚠️ GNN indisponible ({status['reason']}) — fallback XGBoost.")

        merged = _load_predictions(horizon, limit=1500)
        if merged is None:
            st.info(
                "Pas de prédictions H+1h. Vérifie `gold.trafic_predictions` "
                "(DAG retrain XGBoost :25 / GNN 03h)."
            )
            return

        _freshness_line(merged, ts_col="calculated_at")
        dominant = _render_pydeck_predictions(merged, height=450)
        _legend_ratio()
        st.caption(
            f"Source : `gold.trafic_predictions` · "
            f"Modèle : {dominant} · {len(merged)} nœuds · H+1h"
        )
