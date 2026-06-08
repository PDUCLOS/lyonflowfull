"""Page Usager — Files (file manager simple).

Upload/download de fichiers via Streamlit. Stockage local dans /uploads/
(ou Google Drive si configuré — GDRIVE_FOLDER_ID_USER_FILES).

Note : page accessible à tous les personas (pas dans la navigation YAML par
défaut, mais ouverte via /Usager_4_Files pour usage interne).

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

st.caption(
    "Espace de partage pour les documents, datasets, photos, etc. "
    "Upload et download en quelques clics. Pour des fichiers > 100 MB, "
    "contacter l'admin pour configurer un stockage MinIO."
)

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
            with open(dest, "wb") as f:
                f.write(uploaded_file.getbuffer())
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
        st.rerun()

st.markdown("---")


# -----------------------------------------------------------------------------
# Files list
# -----------------------------------------------------------------------------
st.markdown("##### 📂 Fichiers disponibles")

files = sorted(UPLOAD_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)

if not files:
    st.info("Aucun fichier uploadé. Sois le premier !")
else:
    # Filtre
    search = st.text_input("🔍 Rechercher", placeholder="nom du fichier…", key="file_search")
    if search:
        files = [f for f in files if search.lower() in f.name.lower()]

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
