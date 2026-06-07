"""Page Pro TCL — Export reporting."""

from __future__ import annotations

import streamlit as st

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
    if st.button("📤 Générer Excel", key="excel_export_btn"):
        # Simuler
        import io

        import pandas as pd

        from src.data.mock.pro_tcl import LINE_KPIS

        df = pd.DataFrame(
            [
                {
                    "Ligne": lid,
                    "OTP %": k.get("otp_pct"),
                    "Retard (min)": k.get("avg_delay_min"),
                    "Fréquence (min)": k.get("frequency_min"),
                    "Charge %": k.get("load_pct"),
                }
                for lid, k in LINE_KPIS.items()
            ]
        )
        buffer = io.BytesIO()
        try:
            df.to_excel(buffer, index=False, engine="openpyxl")
            st.download_button(
                "📥 Télécharger Excel",
                data=buffer.getvalue(),
                file_name=f"lyonflow_export_{report_config.get('start_date', '')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except ImportError:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Télécharger CSV (fallback openpyxl manquant)",
                data=csv,
                file_name=f"lyonflow_export_{report_config.get('start_date', '')}.csv",
                mime="text/csv",
            )
elif export_format == "pdf":
    st.markdown("##### 📄 Export PDF")
    if st.button("📤 Générer PDF", key="pdf_export_btn"):
        st.info("🚧 Export PDF — utilise WeasyPrint côté backend (Sprint 4 elu track).")
elif export_format == "hastus":
    st.markdown("##### ⏰ Export Hastus")
    if st.button("📤 Générer Hastus", key="hastus_btn"):
        st.success("✅ Scénario Hastus généré — voir Simulateur pour les détails.")
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
