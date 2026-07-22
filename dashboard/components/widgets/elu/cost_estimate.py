"""Widget — Estimation coût aménagement."""

from __future__ import annotations

import streamlit as st


def render_cost_estimate(zone: str | None = None) -> None:
    """Affiche l'estimation de coût d'un aménagement.

    Args:
        zone: nom de la zone (optionnel).
    """
    st.markdown("##### Estimation coût")

    if not zone:
        st.info("Sélectionnez une zone pour voir l'estimation.")
        return

    type_amenagement = st.selectbox(
        "Type d'aménagement",
        [
            "Couloir bus dédié",
            "Piste cyclable bidirectionnelle",
            "Piste cyclable + couloir bus",
            "Réaménagement carrefour",
            "Pôle d'échanges multimodal (PEM)",
        ],
        key="cost_estimate_type",
    )

    longueur_km = st.slider("Longueur (km)", 0.2, 5.0, 1.5, 0.1, key="cost_estimate_length")

    # Coût par type (€/m)
    cout_par_m = {
        "Couloir bus dédié": 800,
        "Piste cyclable bidirectionnelle": 350,
        "Piste cyclable + couloir bus": 1100,
        "Réaménagement carrefour": 1_500_000,  # forfait par carrefour
        "Pôle d'échanges multimodal (PEM)": 8_000_000,  # forfait PEM
    }

    # Forfaits : carrefour (par unité) ou PEM (par projet)
    is_forfait = "Pôle" in type_amenagement or "carrefour" in type_amenagement.lower()
    cout_unitaire = cout_par_m.get(type_amenagement)
    if cout_unitaire is None:
        st.warning(f"Type d'aménagement inconnu : « {type_amenagement} ». Coût par défaut appliqué (500€/m).")
        cout_unitaire = 500

    if is_forfait:
        cout_total = cout_unitaire
        cout_unite = "forfait"
    else:
        cout_total = longueur_km * 1000 * cout_unitaire
        cout_unite = f"{cout_unitaire}€/m × {longueur_km} km"

    st.markdown(
        f"""
        <div class="lyonflow-card" style="text-align:center;padding:1.5rem;">
            <div class="lyf-detail" style="opacity:0.6;">Coût estimé total</div>
            <div style="font-size:2.5rem;font-weight:700;color:var(--persona-elu);margin:0.3rem 0;">
                {cout_total / 1_000_000:.1f} M€
            </div>
            <div class="lyf-detail" style="opacity:0.7;">{cout_unite}</div>
            <div class="lyf-sublabel" style="opacity:0.5;margin-top:0.5rem;">
                Zone : {zone} · Type : {type_amenagement}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
