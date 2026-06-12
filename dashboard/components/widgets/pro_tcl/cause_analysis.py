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
        segment = {
            "line_id": "C3",
            "name": "Part-Dieu → Saxe",
            "bus_state": "delayed",
            "traffic_state": "jammed",
            "diagnosis": "infra",
            "delay_min": 7,
        }

    line = segment.get("line_id", "—")
    seg_name = segment.get("name", "—")
    diagnosis = segment.get("diagnosis", "ok")
    delay = segment.get("delay_min", 0)

    # Diagnostic + recommandation
    if diagnosis == "infra":
        cause = "🚗 Trafic congestionné sur le tronçon — la voirie est saturée"
        recommendation = (
            "**Action prioritaire :**\n"
            "- Étude couloir bus dédié (ROI 18 mois sur cette ligne)\n"
            "- Coordination feux tricolores en faveur des bus\n"
            "- Plan de délestage VP sur axe parallèle"
        )
        color = COLORS["status_critical"]
    elif diagnosis == "operations":
        cause = "⏱ Le bus accumule du retard sans congestion — problème de fréquence ou de charge"
        recommendation = (
            "**Action prioritaire :**\n"
            "- Augmenter fréquence aux heures de pointe\n"
            "- Vérifier rotation des chauffeurs\n"
            "- Ajuster temps de battement aux terminus"
        )
        color = COLORS["status_warning"]
    elif diagnosis == "bus_lane_ok":
        cause = "🚌 Couloir bus fonctionnel — trafic VP bouché mais bus protégé"
        recommendation = (
            "**Bonne pratique à généraliser :**\n"
            "- Étendre le couloir bus aux tronçons adjacents\n"
            "- Documenter comme cas d'école pour d'autres lignes"
        )
        color = COLORS["status_info"]
    else:
        cause = "✅ Aucune anomalie détectée"
        recommendation = "RAS — fonctionnement normal."
        color = COLORS["status_ok"]

    st.markdown(
        f"""
        <div class="lyonflow-card" style="border-left:4px solid {color};">
            <div style="font-size:0.85rem;opacity:0.7;">Analyse causale</div>
            <div style="font-size:1.1rem;font-weight:600;margin:0.3rem 0;">
                {line} — {seg_name} · {delay} min de retard
            </div>
            <div style="margin-top:0.6rem;font-size:0.9rem;">
                <b>Cause identifiée :</b> {cause}
            </div>
            <div style="margin-top:0.6rem;padding:0.6rem;background:{color}22;
                        border-radius:4px;font-size:0.85rem;">
                {recommendation}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
