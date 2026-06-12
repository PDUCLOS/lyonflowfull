"""Widget — 4 KPI cards avant/après avec deltas en %."""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS


def render_delta_kpis(avant: dict, apres: dict) -> None:
    """Affiche les KPI cards delta (avant / après).

    Args:
        avant: dict avec clés métriques → valeur avant.
        apres: dict avec clés métriques → valeur après.
    """
    cols = st.columns(len(avant))

    for col, (key, val_avant) in zip(cols, avant.items()):
        val_apres = apres.get(key, val_avant)
        if val_avant == 0:
            delta_pct = 0
        else:
            delta_pct = (val_apres - val_avant) / val_avant * 100

        delta_color = (
            COLORS["status_ok"]
            if delta_pct > 0
            else COLORS["status_critical"]
            if delta_pct < 0
            else COLORS["status_warning"]
        )

        # Format valeur
        if isinstance(val_apres, int) and val_apres > 1000:
            apres_str = f"{val_apres:,}"
        elif isinstance(val_apres, float):
            apres_str = f"{val_apres:.1f}"
        else:
            apres_str = str(val_apres)

        # Label humanisé
        label = key.replace("_", " ").title()

        with col:
            st.markdown(
                f"""
                <div style="background:var(--bg-card);border:1px solid var(--border-card);
                            border-radius:8px;padding:0.8rem;text-align:center;">
                    <div style="font-size:0.7rem;opacity:0.6;text-transform:uppercase;">
                        {label}
                    </div>
                    <div style="font-size:1.4rem;font-weight:700;margin:0.3rem 0;">
                        {apres_str}
                    </div>
                    <div style="font-size:0.85rem;font-weight:600;color:{delta_color};">
                        {delta_pct:+.1f}%
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
