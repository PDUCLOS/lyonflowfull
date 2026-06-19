"""Widget — Comparaison multi-lignes.

Sprint 8 — KPIs chargés via data_loader.cached_line_kpis().
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.data_cache import cached_line_kpis


def render_line_comparison(line_ids: list | None = None) -> None:
    """Affiche une comparaison multi-lignes en tableau + radar.

    Args:
        line_ids: lignes à comparer. Si None, toutes.
    """
    kpis_dict = cached_line_kpis()
    if line_ids is None:
        line_ids = list(kpis_dict.keys())

    if not line_ids:
        st.info("Sélectionnez au moins une ligne.")
        return

    data = []
    for lid in line_ids:
        k = kpis_dict.get(lid, {})
        data.append(
            {
                # Sprint 15+ : affichage du label lisible (L66) plutôt que
                # l'identifiant SYTRAL brut (ActIV:Line::66:SYTRAL_h20).
                "Ligne": k.get("line_label") or lid,
                "OTP %": k.get("otp_pct", 0),
                "Retard (min)": k.get("avg_delay_min", 0),
                "Fréquence (min)": k.get("frequency_min", 0),
                "Charge %": k.get("load_pct", 0),
                "Tendance": k.get("trend", "—"),
            }
        )

    df = pd.DataFrame(data)
    st.dataframe(
        df.style.background_gradient(subset=["OTP %"], cmap="RdYlGn", vmin=60, vmax=98).background_gradient(
            subset=["Charge %"], cmap="RdYlGn_r", vmin=30, vmax=100
        ),
        use_container_width=True,
    )
