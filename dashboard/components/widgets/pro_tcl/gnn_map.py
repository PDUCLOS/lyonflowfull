"""Widget — Carte trafic (prédictions GNN/XGBoost sur la grille H3).

Sprint 10 — réintégration multi-personas.

Trois entrées publiques :
* ``render_traffic_map(...)``       — carte plein-format (Pro_1, Pro_7).
* ``render_traffic_map_compact(...)`` — version réduite (Usager_1, Elu_1).
* ``render_gnn_map_section()``      — section dédiée Pro_7 avec bandeau status.

Toutes utilisent le même backend : jointure
``gold.dim_spatial_grid_mapping`` × ``gold.trafic_predictions`` rendue via
pydeck (fallback dataframe si pydeck absent).
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from dashboard.components.colors import COLORS
from dashboard.components.data_cache import cached_spatial_mapping
from src.data.data_loader import load_traffic_predictions_for_map as load_traffic_predictions
from src.ml.mlflow_integration import is_mlflow_available
from src.ml.model_registry import is_gnn_map_visible, is_stgcn_enabled
from src.models.stgcn_wrapper import STGCNWrapper

logger = logging.getLogger(__name__)

# Sprint 8+ (2026-06-12) — focus H+1h strict. Le widget n'expose
# que H+1h (60 min) dans l'interface. Les autres horizons restent
# entraînés en arrière-plan mais l'utilisateur ne les voit plus.
_DEFAULT_HORIZONS = (60,)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _speed_to_color(speed: float) -> list:
    if speed is None:
        return [128, 128, 128, 180]
    if speed < 10:
        return [231, 76, 60, 220]
    if speed < 20:
        return [255, 152, 0, 220]
    if speed < 35:
        return [255, 193, 7, 220]
    return [76, 175, 80, 220]


def _check_gnn_model(horizon: int) -> dict:
    """Vérifie disponibilité modèle GNN pour horizon donné."""
    try:
        wrapper = STGCNWrapper.get(horizon)
        if wrapper.load():
            return {"loaded": True, "reason": "OK", "fallback": "SpatioTemporalGCN"}
        return {
            "loaded": False,
            "reason": f"Modèle .pt absent pour H+{horizon}min (LYONFLOW_MODELS_DIR).",
            "fallback": "XGBoost (fallback — métriques uniquement)",
        }
    except Exception as e:  # pragma: no cover
        return {
            "loaded": False,
            "reason": f"Erreur chargement: {e}",
            "fallback": "XGBoost (fallback)",
        }


def _load_merged(horizon: int, limit: int = 500) -> pd.DataFrame | None:
    """Charge mapping H3 + prédictions et joint sur ``node_idx``.

    Returns:
        DataFrame mergée ou None si données absentes/erreur.
    """
    mapping_df = cached_spatial_mapping(force_mock=False)
    if mapping_df.empty:
        return None

    preds_df = load_traffic_predictions(horizon_minutes=horizon, limit=limit)
    if preds_df.empty or "node_idx" not in preds_df.columns:
        return None

    merged = mapping_df.merge(preds_df, on="node_idx", how="inner")
    return merged if not merged.empty else None


def _render_pydeck(merged: pd.DataFrame, height: int, zoom: float = 11.0) -> str:
    """Rendu pydeck. Retourne nom du modèle dominant pour affichage caller."""
    try:
        import pydeck as pdk
    except ImportError:
        st.warning("Pydeck non installé — fallback liste tabulaire.")
        st.dataframe(
            merged[["node_idx", "lat", "lng", "predicted_speed", "model_name"]].head(50),
            use_container_width=True,
            hide_index=True,
        )
        return "?"

    merged = merged.copy()
    merged["color"] = merged["predicted_speed"].apply(_speed_to_color)

    dominant_model = (
        merged["model_name"].mode().iloc[0]
        if "model_name" in merged.columns and not merged["model_name"].mode().empty
        else "?"
    )

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=merged,
        get_position=["lng", "lat"],
        get_color="color",
        get_radius=100,
        pickable=True,
    )
    view_state = pdk.ViewState(
        latitude=45.76,
        longitude=4.84,
        zoom=zoom,
        pitch=0,
    )
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip={
            "html": ("<b>Node {node_idx}</b><br/>Speed: <b>{predicted_speed} km/h</b><br/>Model: {model_name}"),
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


def _legend_inline() -> None:
    st.markdown("**Légende** : 🟢 Fluide (>35 km/h) · 🟡 Modéré (20-35) · 🟠 Dense (10-20) · 🔴 Bloqué (<10)")


# -----------------------------------------------------------------------------
# API publique : carte plein-format avec sélecteur horizon
# -----------------------------------------------------------------------------
def render_traffic_map(
    *,
    height: int = 450,
    horizon_default: int = 60,
    show_horizon_selector: bool = True,
    show_legend: bool = True,
    show_caption: bool = True,
    key_suffix: str = "",
) -> None:
    """Carte trafic plein format. Pré-requis : flag activé + données disponibles.

    Args:
        height: hauteur de la carte en pixels.
        horizon_default: horizon initial sélectionné (min).
        show_horizon_selector: affiche le selectbox horizon.
        show_legend: affiche la légende sous la carte.
        show_caption: affiche la caption modèle/source.
        key_suffix: suffixe pour les keys Streamlit (évite collisions multi-instances).
    """
    if not is_gnn_map_visible():
        st.info("Carte trafic désactivée. Set `LYONFLOW_DASHBOARD_GNN_MAP=true` dans .env pour l'afficher.")
        return

    horizon = horizon_default
    if show_horizon_selector:
        # Sprint 8+ (2026-06-12) — focus H+1h. Le selectbox propose
        # uniquement H+1h (60 min) — cf. _DEFAULT_HORIZONS.
        try:
            default_idx = _DEFAULT_HORIZONS.index(horizon_default)
        except ValueError:
            default_idx = 0
        horizon = st.selectbox(
            "Horizon de prédiction (focus H+1h)",
            _DEFAULT_HORIZONS,
            index=default_idx,
            key=f"traffic_map_horizon_{key_suffix}",
            format_func=lambda x: f"H+{x}min",
            help="Sprint 8+ : focus H+1h. Les autres horizons ne sont plus "
                 "entraînés (1 modèle au lieu de 4 = -75% compute).",
        )

    merged = _load_merged(horizon, limit=500)
    if merged is None:
        st.info(
            f"Pas de prédictions disponibles pour H+{horizon}min. "
            "Vérifie que `gold.trafic_predictions` est peuplée "
            "(DAG retrain XGBoost :25 / GNN 03h)."
        )
        return

    # Bandeau modèle (best effort)
    if is_stgcn_enabled() and is_mlflow_available():
        status = _check_gnn_model(horizon)
        if not status["loaded"]:
            st.caption(f"⚠️ GNN indisponible ({status['reason']}) — fallback XGBoost.")

    dominant = _render_pydeck(merged, height=height)
    if show_legend:
        _legend_inline()
    if show_caption:
        st.caption(
            f"Source : `gold.trafic_predictions` × `gold.dim_spatial_grid_mapping` · "
            f"Modèle : {dominant} · {len(merged)} nœuds · H+{horizon}min"
        )


# -----------------------------------------------------------------------------
# API publique : carte compacte (Usager / Elu)
# -----------------------------------------------------------------------------
def render_traffic_map_compact(
    *,
    height: int = 280,
    horizon_minutes: int = 30,
    key_suffix: str = "",
) -> None:
    """Carte trafic compacte sans sélecteur (Usager / Elu).

    Args:
        height: hauteur réduite.
        horizon_minutes: horizon fixe (pas de sélecteur).
        key_suffix: suffixe key Streamlit.
    """
    if not is_gnn_map_visible():
        return  # silence côté Usager/Elu, pas d'info bandeau intrusif

    merged = _load_merged(horizon_minutes, limit=400)
    if merged is None:
        st.caption(f"🟡 Carte trafic indisponible (pas de prédictions H+{horizon_minutes}min)")
        return

    _render_pydeck(merged, height=height, zoom=10.7)
    _legend_inline()


# -----------------------------------------------------------------------------
# API publique : section Pro_7 (bandeau status + carte)
# -----------------------------------------------------------------------------
def render_gnn_map_section() -> None:
    """Section dédiée Pro_7 Model Monitoring — bandeau status + carte.

    Wrapper rétro-compatible utilisé par Pro_7. Affiche un bandeau si le flag
    est désactivé. Sinon délègue à ``render_traffic_map()``.
    """
    st.markdown("##### 🗺️ Carte trafic — prédictions spatiales")

    if not is_gnn_map_visible():
        st.markdown(
            """
            <div style="background:linear-gradient(135deg, var(--border-card) 0%, var(--persona-elu) 100%);
                        border:1px dashed var(--persona-elu-accent);border-radius:8px;padding:1rem;margin:0.5rem 0;">
                <div style="font-size:0.8rem;opacity:0.8;text-transform:uppercase;
                            letter-spacing:1px;">🟡 Carte désactivée</div>
                <div style="font-size:0.95rem;margin:0.5rem 0;">
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

    render_traffic_map(
        height=450,
        horizon_default=60,
        show_horizon_selector=True,
        key_suffix="pro7",
    )
