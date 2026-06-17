"""Widget — Export SAEIV (format SAEIV depuis données Gold live).

Sprint 9+ (2026-06-17) — plus de KPIs hardcodés ``{"line_id": "C3", "otp_pct":
78.4}``. Lit ``cached_line_kpis()`` (vue matérialisée
``gold.mv_line_kpis_live``) pour les KPIs et ``cached_bottlenecks_top()``
pour les bottlenecks.
"""

from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

from src.data.exceptions import DashboardDataError


def render_saeiv_export(report_config: dict | None = None) -> None:
    """Affiche le bouton d'export au format SAEIV.

    Args:
        report_config: dict du report_builder (période, lignes, sections).
    """
    st.markdown("##### 🔧 Export SAEIV")

    st.caption(
        "Format SAEIV : JSON structuré compatible avec le SAEIV TCL pour "
        "intégration au système d'information exploitation. "
        "Source : PostgreSQL Gold (`mv_line_kpis_live` + `infrastructure_bottlenecks`)."
    )

    if st.button("📤 Générer export SAEIV", type="primary", key="saeiv_export_btn"):
        # Sprint 9+ — données réelles uniquement, plus de KPIs hardcodés.
        from dashboard.components.data_cache import (
            cached_bottlenecks_top,
            cached_line_kpis,
        )

        # 1. KPIs par ligne (live via mv_line_kpis_live)
        line_ids = (report_config or {}).get("lines") or None
        try:
            kpis_dict = cached_line_kpis(
                line_ids=tuple(line_ids) if line_ids else None
            )
        except DashboardDataError as e:
            st.error(f"⚠️ KPIs lignes indisponibles — {e}")
            return

        kpis_payload = []
        for lid, k in (kpis_dict or {}).items():
            kpis_payload.append(
                {
                    "line_id": lid,
                    "otp_pct": k.get("otp_pct"),
                    "avg_delay_min": k.get("avg_delay_min"),
                    "frequency_min": k.get("frequency_min"),
                    "load_pct": k.get("load_pct"),
                    "n_obs_total": k.get("n_obs_total", 0),
                }
            )

        # 2. Bottlenecks (live via cached_bottlenecks_top)
        try:
            bottlenecks_top = cached_bottlenecks_top()
        except DashboardDataError as e:
            st.error(f"⚠️ Bottlenecks indisponibles — {e}")
            return
        bottlenecks_payload = [
            {
                "rank": b.get("rank"),
                "zone": b.get("zone"),
                "lines_impacted": b.get("lines_impacted") or [],
                "voyageurs_jour": b.get("voyageurs_jour", 0),
                "gain_min": b.get("gain_min", 0),
                "cout_M_euros": b.get("cout_M_euros", 0),
                "roi_mois": b.get("roi_mois", 0),
                "delai_mois": b.get("delai_mois", 0),
            }
            for b in bottlenecks_top
        ]

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
                "kpis": kpis_payload,
                "bottlenecks": bottlenecks_payload,
            },
        }
        json_str = json.dumps(saeiv_data, indent=2, ensure_ascii=False)

        st.download_button(
            label="📥 Télécharger SAEIV JSON",
            data=json_str,
            file_name=f"saeiv_export_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )
        st.success(
            f"✅ Export SAEIV généré ({len(json_str)} octets) — "
            f"{len(kpis_payload)} lignes KPI + {len(bottlenecks_payload)} bottlenecks"
        )
