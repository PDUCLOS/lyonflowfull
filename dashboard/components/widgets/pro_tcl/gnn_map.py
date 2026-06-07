"""Widget — Carte GNN (visualisation géographique des prédictions).

Sprint 9 — Widget PRÉPARÉ mais DÉSACTIVÉ par défaut.

Affiche les prédictions du modèle SpatioTemporalGCN sur la carte
de Lyon (nœuds H3 res.13 → couleur par vitesse prédite). Permet
de voir la propagation de congestion entre segments adjacents.

**État** : préparé dans le code, masqué par ``is_gnn_map_visible()``.
Pour activer :
1. Set ``LYONFLOW_DASHBOARD_GNN_MAP=true`` dans .env
2. Le widget apparaît dans le dashboard Model Monitoring (Pro_7)
3. Un modèle .pt doit être présent dans ``LYONFLOW_MODELS_DIR``
4. Le serveur MLflow doit être joignable

Voir ``docs/SPRINT_9_GNN_DASHBOARD.md`` pour le détail.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from src.data.data_loader import load_spatial_mapping
from src.data.data_loader import load_traffic_predictions_for_map as load_traffic_predictions
from src.ml.mlflow_integration import is_mlflow_available
from src.ml.model_registry import is_gnn_map_visible, is_stgcn_enabled
from src.models.stgcn_wrapper import STGCNWrapper

logger = logging.getLogger(__name__)


def render_gnn_map_section() -> None:
    """Sprint 9 — Carte GNN géographique (préparée, désactivée par défaut).

    Affiche un bandeau "préparation" si le widget est désactivé, ou
    la carte des prédictions si activé.
    """
    st.markdown("##### 🗺️ Carte GNN (prédictions spatiales)")

    # Bandeau de transparence
    if not is_gnn_map_visible():
        st.markdown(
            """
            <div style="background:linear-gradient(135deg, #2A2D34 0%, #3F51B5 100%);
                        border:1px dashed #5C6BC0;border-radius:8px;padding:1rem;margin:0.5rem 0;">
                <div style="font-size:0.8rem;opacity:0.8;text-transform:uppercase;
                            letter-spacing:1px;">🟡 Sprint 9 — Préparé, non activé</div>
                <div style="font-size:0.95rem;margin:0.5rem 0;">
                    La carte GNN est <b>préparée mais désactivée</b> par défaut.
                </div>
                <div style="font-size:0.85rem;opacity:0.7;">
                    Pour l'activer : set <code>LYONFLOW_DASHBOARD_GNN_MAP=true</code> dans .env,
                    puis redémarrer Streamlit. Nécessite aussi un modèle .pt
                    entraîné (DAG <code>retrain_gnn</code>) et le serveur MLflow joignable.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Section activée
    if not is_stgcn_enabled():
        st.warning("STGCN désactivé dans LYONFLOW_MODELS_ACTIVE — carte non disponible.")
        return

    if not is_mlflow_available():
        st.warning("MLflow non disponible — les prédictions ne peuvent pas être récupérées.")
        return

    # 1. Charger le mapping spatial (nœuds H3)
    mapping_df = load_spatial_mapping(force_mock=False)
    if mapping_df.empty:
        st.info("Mapping spatial non disponible. Lance le DAG `build_spatial_mapping` d'abord.")
        return

    # 2. Charger les prédictions
    horizon = st.selectbox(
        "Horizon de prédiction",
        [5, 15, 30, 60, 180, 360],
        index=3,
        key="gnn_map_horizon",
    )
    preds_df = load_traffic_predictions(horizon_minutes=horizon, limit=500)
    if preds_df.empty:
        st.info(f"Pas de prédictions pour H+{horizon}min. Lance le training d'abord.")
        return

    # 3. Tenter de charger le modèle GNN
    model_status = _check_gnn_model(horizon)
    if not model_status["loaded"]:
        st.warning(
            f"Modèle STGCN H+{horizon}min non chargé : {model_status['reason']}. "
            "La carte affichera les prédictions XGBoost à la place."
        )
        # Fallback sur les prédictions sans info modèle
        model_source = model_status.get("fallback", "XGBoost (XGBoostSpeed)")

    # 4. Jointure mapping + predictions
    if "node_idx" in preds_df.columns:
        merged = mapping_df.merge(preds_df, on="node_idx", how="inner")
    else:
        st.warning("Colonne node_idx absente des prédictions.")
        return

    if merged.empty:
        st.info("Aucune correspondance entre mapping et prédictions.")
        return

    # 5. Rendu carte pydeck
    _render_pydeck_map(merged, horizon)


def _check_gnn_model(horizon: int) -> dict:
    """Vérifie la disponibilité du modèle GNN pour un horizon donné.

    Returns:
        Dict avec ``loaded`` (bool), ``reason`` (str), ``fallback`` (str).
    """
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


def _render_pydeck_map(merged: pd.DataFrame, horizon: int) -> None:
    """Rendu Pydeck de la carte GNN (scatterplot coloré par prédiction).

    Args:
        merged: DataFrame avec colonnes lat, lng, predicted_speed, model_name, model_version.
        horizon: horizon sélectionné (pour le titre).
    """
    try:
        import pydeck as pdk
    except ImportError:
        st.warning("Pydeck non installé — fallback liste tabulaire.")
        st.dataframe(
            merged[["node_idx", "channel_id", "lat", "lng", "predicted_speed", "model_name"]].head(50),
            use_container_width=True,
            hide_index=True,
        )
        return

    # Couleur selon predicted_speed (0-130 km/h)
    def _speed_to_color(speed: float) -> list:
        if speed < 10:
            return [231, 76, 60, 220]   # rouge (bouché)
        if speed < 20:
            return [255, 152, 0, 220]   # orange
        if speed < 35:
            return [255, 193, 7, 220]   # jaune
        return [76, 175, 80, 220]       # vert (fluide)

    merged = merged.copy()
    merged["color"] = merged["predicted_speed"].apply(_speed_to_color)

    # Modèle dominant dans le dataset
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
        zoom=11.0,
        pitch=0,
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip={
            "html": (
                "<b>Node {node_idx}</b><br/>"
                "Channel: {channel_id}<br/>"
                "Speed: <b>{predicted_speed} km/h</b><br/>"
                "Model: {model_name} v{model_version}"
            ),
            "style": {
                "backgroundColor": "#1A1D24",
                "color": "white",
                "padding": "8px",
                "borderRadius": "4px",
            },
        },
    )

    st.pydeck_chart(deck, use_container_width=True, height=450)

    # Légende
    st.markdown(
        """
        **Légende** : 🟢 Fluide (>35 km/h) · 🟡 Modéré (20-35) · 🟠 Dense (10-20) · 🔴 Bloqué (<10)
        """
    )
    st.caption(
        f"Carte alimentée par {dominant_model} (H+{horizon}min). "
        f"{len(merged)} nœuds affichés. "
        f"Données MLflow : voir Pro_7 → Model Registry."
    )

    # Toggle GNN vs XGBoost (debug)
    with st.expander("🔬 Détails techniques"):
        st.markdown(
            f"""
            - **Modèle** : `{dominant_model}`
            - **Horizon** : H+{horizon}min
            - **Nœuds affichés** : {len(merged)}
            - **Source** : `gold.trafic_predictions` (jointure `gold.dim_spatial_grid_mapping`)
            - **Backend carte** : pydeck + Carto Positron (gratuit, sans token)
            """
        )
