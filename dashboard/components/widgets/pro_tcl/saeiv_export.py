"""Widget — Export SAEIV (format SAEIV simulé)."""

from __future__ import annotations

import json
from datetime import datetime

import streamlit as st


def render_saeiv_export(report_config: dict | None = None) -> None:
    """Affiche le bouton d'export au format SAEIV.

    Args:
        report_config: dict du report_builder (période, lignes, sections).
    """
    st.markdown("##### 🔧 Export SAEIV")

    st.caption(
        "Format SAEIV : JSON structuré compatible avec le SAEIV TCL pour "
        "intégration au système d'information exploitation."
    )

    if st.button("📤 Générer export SAEIV", type="primary", key="saeiv_export_btn"):
        # Simuler génération
        saeiv_data = {
            "export_type": "SAEIV",
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "period": {
                "start": (report_config or {}).get("start_date", ""),
                "end": (report_config or {}).get("end_date", ""),
            },
            "lines": (report_config or {}).get("lines", []),
            "data": {
                "kpis": [
                    {"line_id": "C3", "otp_pct": 78.4, "avg_delay_min": 2.3},
                    {"line_id": "C13", "otp_pct": 81.2, "avg_delay_min": 1.8},
                ],
                "bottlenecks": [
                    {"zone": "Rue Garibaldi", "severity": "high", "impact_voyageurs": 120000},
                ],
            },
        }
        json_str = json.dumps(saeiv_data, indent=2, ensure_ascii=False)

        st.download_button(
            label="📥 Télécharger SAEIV JSON",
            data=json_str,
            file_name=f"saeiv_export_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )
        st.success(f"✅ Export SAEIV généré ({len(json_str)} octets)")
