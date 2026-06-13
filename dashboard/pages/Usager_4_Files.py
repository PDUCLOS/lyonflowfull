"""Page Usager — Files (file manager simple).

Upload/download de fichiers via Streamlit. Stockage local dans /uploads/.

Note : page accessible à tous les personas (pas dans la navigation YAML par
défaut, mais ouverte via /Usager_4_Files pour usage interne).

Sprint VPS-6 — Ajout de la "super carte" du trafic Lyon (style caro
Architect-IA-final-project) : pydeck scatterplot des prédictions gold.trafic_predictions
colorées par vitesse. Permet de visualiser l'état du réseau sans quitter la page.

Sprint 6+ : déplacer vers Pro TCL "Import données" si usage réel.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import streamlit as st

from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme

# Config — fallback tempdir si /app non writable (CI, dev local)
_default_upload = os.getenv("LYONFLOW_UPLOAD_DIR", "/app/uploads")
UPLOAD_DIR = Path(_default_upload)
try:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except (OSError, PermissionError):
    import tempfile

    UPLOAD_DIR = Path(tempfile.gettempdir()) / "lyonflow_uploads"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB

st.set_page_config(
    page_title="Files — LyonFlowFull",
    page_icon="📁",
    layout="wide",
)

# Guard (page accessible à tous les personas, mais on vérifie quand même)
apply_persona_guard(expected_persona="usager")
inject_theme()
render_sidebar_navigation()

st.title("📁 Files — Partage de fichiers")
render_data_status_banner()

st.caption("Espace de partage pour les documents, datasets, photos, etc. Upload et download en quelques clics.")

st.markdown("---")


# -----------------------------------------------------------------------------
# Upload zone
# -----------------------------------------------------------------------------
st.markdown("##### ⬆️ Upload")

uploaded_files = st.file_uploader(
    "Glisse-dépose tes fichiers ou clique pour parcourir",
    accept_multiple_files=True,
    type=None,  # tous types acceptés
    key="file_uploader",
)

if uploaded_files:
    n_uploaded = 0
    for uploaded_file in uploaded_files:
        # Check size
        if uploaded_file.size > MAX_FILE_SIZE:
            st.error(f"❌ {uploaded_file.name} est trop gros ({uploaded_file.size / 1_000_000:.1f} MB > 100 MB)")
            continue

        # Save
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize filename
        safe_name = "".join(c for c in uploaded_file.name if c.isalnum() or c in "._- ")
        dest = UPLOAD_DIR / f"{timestamp}_{safe_name}"
        try:
            with open(dest, "wb") as out_file:
                out_file.write(uploaded_file.getbuffer())
            n_uploaded += 1
            # Audit log
            from src.rgpd.service import log_audit

            log_audit(
                actor="streamlit_user",
                action="file_uploaded",
                resource_type="file",
                resource_id=str(dest.name),
                details={"size_bytes": uploaded_file.size, "type": uploaded_file.type},
            )
        except Exception as e:
            st.error(f"❌ Erreur upload {uploaded_file.name}: {e}")

    if n_uploaded > 0:
        st.success(f"✅ {n_uploaded} fichier(s) uploadé(s)")

st.markdown("---")


# -----------------------------------------------------------------------------
# Files list
# -----------------------------------------------------------------------------
st.markdown("##### 📂 Fichiers disponibles")

files = sorted(UPLOAD_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)

if not files:
    st.info("Aucun fichier uploadé. Sois le premier !")
else:
    st.caption(f"{len(files)} fichier(s)")

    # Table
    for f in files[:50]:  # max 50 affichés
        stat = f.stat()
        col1, col2, col3, col4, col5 = st.columns([4, 1.5, 1, 1, 1.5])

        with col1:
            icon = "📄"
            if f.suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                icon = "🖼"
            elif f.suffix in (".pdf",):
                icon = "📕"
            elif f.suffix in (".zip", ".tar", ".gz", ".7z"):
                icon = "🗜"
            elif f.suffix in (".csv", ".xlsx", ".json", ".parquet"):
                icon = "📊"
            st.markdown(f"{icon} **{f.name}**")

        with col2:
            st.caption(f"{f.stat().st_size / 1024:.1f} KB")

        with col3:
            st.caption(datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y"))

        with col4:
            st.caption(datetime.fromtimestamp(stat.st_mtime).strftime("%H:%M"))

        with col5, open(f, "rb") as fp:
            st.download_button(
                label="📥 DL",
                data=fp.read(),
                file_name=f.name,
                key=f"dl_{f.name}",
            )

st.markdown("---")

# -----------------------------------------------------------------------------
# Stats
# -----------------------------------------------------------------------------
st.markdown("##### 📊 Statistiques")
total_size = sum(f.stat().st_size for f in files)
st.metric("Espace utilisé", f"{total_size / 1_000_000:.2f} MB", delta=f"{len(files)} fichiers")

st.caption(
    f"Stockage local : `{UPLOAD_DIR}` · "
    f"Limite fichier : {MAX_FILE_SIZE // 1_000_000} MB · "
    f"Tous les uploads sont loggés (RGPD audit)"
)

st.markdown("---")


# -----------------------------------------------------------------------------
# Super carte trafic Lyon (Sprint VPS-6)
# -----------------------------------------------------------------------------
st.markdown("##### 🗺️ Carte du trafic Lyon — en direct")
st.caption(
    "Prédictions de vitesse par axe routier. Couleurs : 🟢 fluide (>35 km/h) · "
    "🟡 modéré (20-35) · 🟠 dense (10-20) · 🔴 bloqué (<10)."
)

try:
    import pandas as pd
    import pydeck as pdk

    from dashboard.components.data_cache import cached_spatial_mapping
    from src.data.data_loader import load_traffic_predictions_for_map

    with st.spinner("Chargement des prédictions…"):
        df_pred = load_traffic_predictions_for_map(horizon_minutes=60, limit=2000)  # Sprint 12+ H+1h
        df_geo = cached_spatial_mapping(force_mock=False)

    if df_pred.empty or df_geo.empty:
        st.info("Données de prédiction ou de géométrie indisponibles (DB down ou vide).")
    else:
        # Jointure : on prend lat/lon du dim_spatial_grid_mapping (properties_twgid == axis_key)
        # Note: Sprint VPS-5 — la jointure axis_key ↔ properties_twgid est un TODO Sprint 9+
        # (formats différents). En attendant, on prend les lat/lon de dim_spatial_grid_mapping
        # pour les nodes qui ont une geom.
        df_geo_clean = df_geo.dropna(subset=["lat", "lon"]).copy()
        df_geo_clean["axis_key"] = df_geo_clean["properties_twgid"].astype(str)

        # Merge predictions + geo. axis_key dans predictions = channel_id
        # On tente plusieurs jointures (axis_key = properties_twgid OU axis_key = node_idx)
        if "axis_key" in df_pred.columns and "speed_pred" in df_pred.columns:
            df_merged = df_pred.merge(
                df_geo_clean[["axis_key", "lat", "lon", "properties_twgid"]].rename(
                    columns={"properties_twgid": "axis_label"}
                ),
                on="axis_key",
                how="inner",
            )
        else:
            df_merged = pd.DataFrame()

        if df_merged.empty:
            st.info(
                f"Pas de jointure possible entre {len(df_pred)} prédictions et "
                f"{len(df_geo_clean)} nœuds geo. "
                f"(axis_key vs properties_twgid : mapping à faire en Sprint 9+)"
            )
        else:
            # Color par speed_pred
            def _speed_to_rgba(s: float) -> list:
                if pd.isna(s):
                    return [128, 128, 128, 180]
                if s < 10:
                    return [231, 76, 60, 220]  # red
                if s < 20:
                    return [255, 152, 0, 220]  # orange
                if s < 35:
                    return [255, 193, 7, 220]  # yellow
                return [76, 175, 80, 220]  # green

            df_merged[["r", "g", "b", "a"]] = df_merged["speed_pred"].apply(lambda s: pd.Series(_speed_to_rgba(s)))

            # Centrage sur Lyon
            view_state = pdk.ViewState(
                latitude=45.76,
                longitude=4.85,
                zoom=11,
                pitch=0,
            )

            layer = pdk.Layer(
                "ScatterplotLayer",
                data=df_merged,
                get_position=["lon", "lat"],
                get_color=["r", "g", "b", "a"],
                get_radius=80,
                pickable=True,
                opacity=0.7,
            )

            st.pydeck_chart(
                pdk.Deck(
                    layers=[layer],
                    initial_view_state=view_state,
                    map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                    tooltip={
                        "text": "{axis_label}\nVitesse: {speed_pred} km/h\nHorizon: H+{horizon_h}h\nÉtat: {etat_pred}"
                    },
                ),
                use_container_width=True,
            )

            c1, c2, c3, c4 = st.columns(4)
            avg_speed = df_merged["speed_pred"].mean()
            n_axes = df_merged["axis_key"].nunique()
            c1.metric("Vitesse moyenne", f"{avg_speed:.1f} km/h")
            c2.metric("Axes affichés", f"{n_axes}")
            c3.metric("Points total", f"{len(df_merged):,}")
            c4.metric("Source", "gold.trafic_predictions")

            st.caption(
                f"🟢 {(df_merged['speed_pred'] >= 35).sum()} axes fluides · "
                f"🟡 {((df_merged['speed_pred'] >= 20) & (df_merged['speed_pred'] < 35)).sum()} modérés · "
                f"🟠 {((df_merged['speed_pred'] >= 10) & (df_merged['speed_pred'] < 20)).sum()} denses · "
                f"🔴 {(df_merged['speed_pred'] < 10).sum()} bloqués"
            )

except Exception as e:
    st.caption(f"⚠️ Carte indisponible : {e}")
