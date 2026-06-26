"""Widget — Calculateur ROI (valeur du temps × voyageurs × gain).

 Bottlenecks via data_loader.cached_bottlenecks_top().

 (2026-06-25) — Fix Bug 7 du SPEC_FIX_ELU2_BOTTLENECKS.md :
* Affichage du **diagnostic** du bottleneck sélectionné (info contextuelle).
* Cohérence avec le ROI du tableau ranking : les 2 utilisent désormais la
  même formule (voyageurs × gain × valeur_temps × 2 × jours_an / coût).
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_bottlenecks_top
from dashboard.components.loading_state import loading_wrapper

# Diagnostic → emoji + label FR (cohérent avec bottleneck_ranking.py)
_DIAGNOSIS_ROI = {
    "infra": ("🔴", "Infrastructure — travaux d'aménagement"),
    "operations": ("🟠", "Opérationnel — ajustement de service"),
    "bus_lane_ok": ("🟢", "Voie bus fonctionnelle — surveillance"),
    "ok": ("⚪", "Sous surveillance"),
}


def _format_diagnostic_for_roi(diagnosis: str) -> tuple[str, str]:
    return _DIAGNOSIS_ROI.get(diagnosis, _DIAGNOSIS_ROI["ok"])


def render_roi_calculator(line_id: str | None = None) -> None:
    with loading_wrapper("Chargement Roi calculator…", "⏳"):
        """Affiche un calculateur ROI interactif.

    Args:
        line_id: si fourni, focus sur le bottleneck de cette ligne.
    """
    st.markdown("##### 🧮 Calculateur ROI")

    bottlenecks = cached_bottlenecks_top()
    if not bottlenecks:
        st.info("Aucun bottleneck disponible.")
        return

    # Sélection d'un bottleneck (avec diagnostic dans le label pour aider l'élu)
    options = []
    for b in bottlenecks:
        rank = b.get("rank", "—")
        zone = b.get("zone") or "—"
        diagnosis = b.get("diagnosis", "ok")
        diag_emoji, _ = _format_diagnostic_for_roi(diagnosis)
        options.append(f"{diag_emoji} #{rank} {zone}")
    selected = st.selectbox(
        "Sélectionner un aménagement",
        options,
        key="roi_calc_select",
    )

    if not selected:
        return

    # Defensive : matching par préfixe emoji+rank+zone (le format a évolué).
    matching = [
        b
        for b in bottlenecks
        if any(opt.endswith(f"#{b.get('rank', '—')} {b.get('zone') or '—'}") for opt in [selected])
    ]
    if not matching:
        return
    b = matching[0]

    # Bug 7 fix : afficher le diagnostic du bottleneck sélectionné
    diagnosis = b.get("diagnosis", "ok")
    diag_emoji, diag_label = _format_diagnostic_for_roi(diagnosis)
    st.info(f"{diag_emoji} **Diagnostic :** {diag_label}")

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

    # Calculs (formule identique à load_bottlenecks_top, Bug 7 fix)
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
