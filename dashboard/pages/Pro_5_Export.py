"""Page Pro TCL — Export reporting."""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.theme import inject_theme
from dashboard.components.widgets.pro_tcl import (
    render_format_selector,
    render_report_builder,
    render_saeiv_export,
)

st.set_page_config(
    page_title="Export reporting — Pro TCL · LyonFlowFull",
    page_icon="📤",
    layout="wide",
)

apply_persona_guard(expected_persona="pro_tcl")
inject_theme()
render_sidebar_navigation()

st.title("📤 Export reporting")
render_data_status_banner()

st.caption("Exports vers les outils internes TCL (SAEIV, Hastus) et formats courants (Excel, PDF, API).")

st.markdown("---")

# Builder de rapport
report_config = render_report_builder()

st.markdown("---")

# Format
export_format = render_format_selector()

st.markdown("---")

# Génération
if export_format == "saeiv":
    render_saeiv_export(report_config)
elif export_format == "excel":
    st.markdown("##### 📊 Export Excel")
    # Init session_state pour les buffers
    if "excel_buffer_bytes" not in st.session_state:
        st.session_state["excel_buffer_bytes"] = None
        st.session_state["excel_buffer_name"] = None
        st.session_state["excel_buffer_mime"] = None
        st.session_state["excel_buffer_label"] = None

    if st.button("📤 Générer Excel", key="excel_export_btn"):
        with st.spinner("Génération du fichier Excel..."):
            import io

            import pandas as pd

            from dashboard.components.data_cache import cached_line_kpis

            line_kpis_dict = cached_line_kpis()
            df = pd.DataFrame(
                [
                    {
                        "Ligne": lid,
                        "OTP %": k.get("otp_pct"),
                        "Retard (min)": k.get("avg_delay_min"),
                        "Fréquence (min)": k.get("frequency_min"),
                        "Charge %": k.get("load_pct"),
                    }
                    for lid, k in line_kpis_dict.items()
                ]
            )
            base_name = f"lyonflow_export_{report_config.get('start_date', '')}"
            try:
                buffer = io.BytesIO()
                df.to_excel(buffer, index=False, engine="openpyxl")
                st.session_state["excel_buffer_bytes"] = buffer.getvalue()
                st.session_state["excel_buffer_name"] = f"{base_name}.xlsx"
                st.session_state["excel_buffer_mime"] = (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.session_state["excel_buffer_label"] = "📥 Télécharger Excel"
            except ImportError:
                csv = df.to_csv(index=False).encode("utf-8")
                st.session_state["excel_buffer_bytes"] = csv
                st.session_state["excel_buffer_name"] = f"{base_name}.csv"
                st.session_state["excel_buffer_mime"] = "text/csv"
                st.session_state["excel_buffer_label"] = "📥 Télécharger CSV (fallback openpyxl manquant)"

    # Le download_button reste HORS du if pour éviter StreamlitAPIException
    # (recréer un widget sans key= dans un if provoque un conflit de clés)
    if st.session_state["excel_buffer_bytes"] is not None:
        st.download_button(
            label=st.session_state["excel_buffer_label"],
            data=st.session_state["excel_buffer_bytes"],
            file_name=st.session_state["excel_buffer_name"],
            mime=st.session_state["excel_buffer_mime"],
            key="excel_dl_btn",  # clé stable et unique
        )
elif export_format == "pdf":
    st.markdown("##### 📄 Export PDF")
    if st.button("📤 Générer PDF", key="pdf_export_btn"):
        st.info("🚧 Export PDF — utilise WeasyPrint côté backend (Sprint 4 elu track).")
elif export_format == "hastus":
    st.markdown("##### ⏰ Export Hastus")
    st.caption(
        "Hastus = simulation d'horaires TCL. Le scénario se construit via le "
        "Simulateur Pro TCL (fréquence bus par ligne, projection OTP)."
    )
    if st.button("🚀 Ouvrir le Simulateur", key="hastus_btn", type="primary"):
        st.switch_page("pages/Pro_4_Simulateur.py")
elif export_format == "api":
    st.markdown("##### 📡 Export API")
    st.code(
        f"""
        POST /api/v1/reports
        Content-Type: application/json
        {{
          "start_date": "{report_config.get("start_date", "")}",
          "end_date": "{report_config.get("end_date", "")}",
          "lines": {report_config.get("lines", [])},
          "sections": {report_config.get("sections", [])}
        }}
        """,
        language="json",
    )

st.caption("Export reporting · Vers SAEIV / Hastus / Excel / PDF / API")
