"""Widget — Générateur PDF (bouton qui appelle src.reporting.pdf_renderer)."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from dashboard.components.error_display import show_error
from dashboard.components.loading_state import loading_wrapper
from src.reporting.pdf_renderer import generate_pdf, render_html_template


def render_pdf_generator(sections: dict) -> None:
    """Affiche un bouton de génération PDF avec download.

    Args:
        sections: dict passé à render_html_template (title, kpis, bottlenecks, etc.)
    """
    with loading_wrapper("Chargement Pdf generator…", "⏳"):
        if st.button("📥 Générer le PDF", type="primary", key="pdf_generator_btn"):
            sections.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
            html = render_html_template(sections)
            try:
                pdf_bytes = generate_pdf(html)
                st.download_button(
                    label="📄 Télécharger le PDF",
                    data=pdf_bytes,
                    file_name=f"lyonflow_rapport_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    key="pdf_download_btn",
                )
                st.success(f"✅ PDF généré ({len(pdf_bytes):,} octets)")
            except RuntimeError as e:
                show_error("generic", f"❌ Erreur génération PDF : {e}")
                st.info(
                    "💡 Installer weasyprint (recommandé) ou reportlab (fallback) :\n"
                    "```\npip install weasyprint reportlab --break-system-packages\n```"
                )
