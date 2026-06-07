"""Widget — Calculateur ROI (valeur du temps × voyageurs × gain).

Sprint 8 — Bottlenecks via data_loader.load_bottlenecks_top().
"""

from __future__ import annotations

import streamlit as st

from src.data.data_loader import load_bottlenecks_top


def render_roi_calculator(line_id: str | None = None) -> None:
    """Affiche un calculateur ROI interactif.

    Args:
        line_id: si fourni, focus sur le bottleneck de cette ligne.
    """
    st.markdown("##### 🧮 Calculateur ROI")

    bottlenecks = load_bottlenecks_top(force_mock=False)
    if not bottlenecks:
        st.info("Aucun bottleneck disponible.")
        return

    # Sélection d'un bottleneck
    options = [f"#{b.get('rank')} {b.get('zone')}" for b in bottlenecks]
    selected = st.selectbox(
        "Sélectionner un aménagement",
        options,
        key="roi_calc_select",
    )

    if not selected:
        return

    idx = options.index(selected)
    b = bottlenecks[idx]

    # Inputs ajustables
    col1, col2 = st.columns(2)
    with col1:
        valeur_temps = st.slider(
            "Valeur du temps (€/h)",
            min_value=8,
            max_value=30,
            value=15,
            step=1,
            key="roi_valeur_temps",
        )
    with col2:
        jours_an = st.slider(
            "Jours d'usage par an",
            min_value=200,
            max_value=350,
            value=250,
            step=10,
            key="roi_jours_an",
        )

    # Calculs
    voyageurs = b.get("voyageurs_jour", 0)
    gain_min = b.get("gain_min", 0)
    cout = b.get("cout_M_euros", 0) * 1_000_000

    gain_annuel = voyageurs * (gain_min / 60) * valeur_temps * 2 * jours_an
    roi_mois = (cout / gain_annuel * 12) if gain_annuel > 0 else 999
    benefice_5ans = gain_annuel * 5 - cout

    # Affichage
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Gain annuel estimé", f"{gain_annuel / 1_000_000:.2f} M€")
    with c2:
        st.metric(
            "ROI",
            f"{int(roi_mois)} mois",
            delta=f"~{12 / roi_mois:.1f}x en 1 an" if roi_mois > 0 else None,
            delta_color="normal",
        )
    with c3:
        st.metric(
            "Bénéfice net 5 ans",
            f"{benefice_5ans / 1_000_000:.1f} M€",
            delta="positif" if benefice_5ans > 0 else "négatif",
            delta_color="normal" if benefice_5ans > 0 else "inverse",
        )
