"""Widget — Analyse causale (pourquoi un bus est en retard)."""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS


def render_cause_analysis(segment: dict | None = None) -> None:
    """Affiche l'analyse causale d'un retard.

    Args:
        segment: dict avec line_id, name, bus_state, traffic_state, diagnosis.
                 Si None, affiche un exemple.
    """
    if segment is None:
        st.info("Sélectionnez un segment pour voir l'analyse causale.")
        return

    line = segment.get("line_id", "—")
    seg_name = segment.get("name", "—")
    diagnosis = segment.get("diagnosis", "ok")
    delay = segment.get("delay_min", 0)

    # Diagnostic + recommandation
    # Sprint 15+ (audit Pro TCL B-10) : la recommandation est injectée
    # dans un template HTML (``unsafe_allow_html=True``). Le markdown
    # ``**...**`` et ``- `` ne sont PAS interprétés dans un bloc HTML.
    # On convertit ici en HTML (``<b>``, ``<br/>• ``) pour que le rendu
    # final soit correct.
    if diagnosis == "infra":
        cause = "🚗 Trafic congestionné sur le tronçon — la voirie est saturée"
        recommendation_html = (
            "<b>Action prioritaire :</b><br/>"
            "• Étude couloir bus dédié (ROI 18 mois sur cette ligne)<br/>"
            "• Coordination feux tricolores en faveur des bus<br/>"
            "• Plan de délestage VP sur axe parallèle"
        )
        color = COLORS["status_critical"]
    elif diagnosis == "operations":
        cause = "⏱ Le bus accumule du retard sans congestion — problème de fréquence ou de charge"
        recommendation_html = (
            "<b>Action prioritaire :</b><br/>"
            "• Augmenter fréquence aux heures de pointe<br/>"
            "• Vérifier rotation des chauffeurs<br/>"
            "• Ajuster temps de battement aux terminus"
        )
        color = COLORS["status_warning"]
    elif diagnosis == "bus_lane_ok":
        cause = "🚌 Couloir bus fonctionnel — trafic VP bouché mais bus protégé"
        recommendation_html = (
            "<b>Bonne pratique à généraliser :</b><br/>"
            "• Étendre le couloir bus aux tronçons adjacents<br/>"
            "• Documenter comme cas d'école pour d'autres lignes"
        )
        color = COLORS["status_info"]
    else:
        cause = "✅ Aucune anomalie détectée"
        recommendation_html = "RAS — fonctionnement normal."
        color = COLORS["status_ok"]

    st.markdown(
        f"""
        <div class="lyonflow-card" style="border-left:4px solid {color};">
            <div class="lyf-detail" style="opacity:0.7;">Analyse causale</div>
            <div style="font-size:1.1rem;font-weight:600;margin:0.3rem 0;">
                {line} — {seg_name} · {delay} min de retard
            </div>
            <div style="margin-top:0.6rem;font-size:0.9rem;">
                <b>Cause identifiée :</b> {cause}
            </div>
            <div class="lyf-detail" style="margin-top:0.6rem;padding:0.6rem;background:{color}22;border-radius:4px;">
                {recommendation_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
