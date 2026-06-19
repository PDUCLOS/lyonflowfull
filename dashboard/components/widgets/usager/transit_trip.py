"""Widget — Trajet transport en commun (TC) entre 2 lieux du référentiel.

Affiche (Sprint 14, 2026-06-19) :
- Bandeau itinéraire O → D avec pastille "Direct" ou "1 correspondance"
- 4 KPI cards : durée totale, marche totale, correspondances, retard cumulé
- Détail par segment (ligne + arrêts + fréquence + retard + confiance)
- Indicateurs marche d'accès aux arrêts
- Disclaimer permanent (fréquences estimées, pas horaires exacts GTFS)

Source : 100% pipeline (Sprint 8 fail loud) :
* referentiel.lieux_transports (dessertes N-N lieu ↔ ligne)
* referentiel.lieux_calendrier (cadences observées weekday/samedi/dimanche/vacances)
* gold.bus_delay_segments (retards SIRI 7j glissants)
* referentiel.lieux_lyon (coordonnées GPS pour résolution)

Limites affichées à l'usager :
- Fréquences estimées, pas d'horaires exacts (GTFS = Phase 2)
- 21 lieux du référentiel (couverture = 100% de la selectbox)
- 1 correspondance maximum (Raptor multi-transfers = Phase 2)
- Retards = moyenne 7j à la tranche horaire courante
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_cache import cached_transit_itinerary
from src.data.exceptions import DashboardDataError

# Couleur par mode TC (segment card)
_MODE_COLOR = {
    "metro": "#1976D2",       # bleu
    "tram": "#43A047",        # vert
    "bus": "#FB8C00",         # orange
    "funicular": "#8E24AA",   # violet
}


def render_transit_trip(origin: str, destination: str) -> None:
    """Affiche le trajet transport en commun entre 2 lieux du référentiel.

    Args:
        origin: label du lieu d'origine (peut être préfixé emoji).
        destination: label du lieu destination (idem).
    """
    with st.spinner("🚌 Recherche itinéraire transport en commun…"):
        try:
            itin = cached_transit_itinerary(origin=origin, destination=destination)
        except DashboardDataError as e:
            st.error(f"⚠️ {e}")
            return

    if itin is None:
        st.warning(
            f"⚠️ Impossible de calculer un itinéraire TC entre "
            f"**{origin}** et **{destination}**. "
            f"Vérifiez que les lieux sont dans le référentiel (21 lieux emblématiques)."
        )
        return

    segments = itin.get("segments") or []
    if not segments:
        # Aucun trajet trouvé : afficher les diagnostics
        st.warning(
            f"⚠️ Aucun itinéraire TC trouvé entre "
            f"**{itin.get('origin_label', origin)}** et "
            f"**{itin.get('destination_label', destination)}**."
        )
        for diag in itin.get("diagnostics", []):
            st.caption(f"ℹ️ {diag}")
        return

    _render_transit_banner(itin)
    _render_transit_kpis(itin)
    st.markdown("---")
    _render_transit_segments(itin)
    st.markdown("---")
    _render_transit_disclaimer()


def _render_transit_banner(itin: dict) -> None:
    """Bandeau itinéraire O → D avec pastille 'Direct' / '1 correspondance'."""
    n_transfers = int(itin.get("n_transfers", 0))
    if n_transfers == 0:
        mode_label = "✅ Direct"
        mode_color = "#4CAF50"
    else:
        hub = itin.get("transfer_hub") or "?"
        mode_label = f"🔄 1 correspondance · {hub}"
        mode_color = "#FF9800"

    st.markdown(
        f"""
        <div style="background:var(--bg-card);padding:0.8rem 1rem;border-radius:6px;
                    border-left:4px solid #4CAF50;display:flex;align-items:center;
                    gap:0.6rem;font-size:0.95rem;margin-bottom:1rem;flex-wrap:wrap;">
            <span style="background:#4CAF50;color:white;padding:0.2rem 0.6rem;
                         border-radius:12px;font-size:0.75rem;font-weight:600;">🚌 DÉPART</span>
            <span style="font-weight:600;">{itin['origin_label']}</span>
            <span style="opacity:0.4;margin:0 0.5rem;">→</span>
            <span style="background:#F44336;color:white;padding:0.2rem 0.6rem;
                         border-radius:12px;font-size:0.75rem;font-weight:600;">🔴 ARRIVÉE</span>
            <span style="font-weight:600;">{itin['destination_label']}</span>
            <span style="margin-left:auto;background:{mode_color};color:white;
                         padding:0.2rem 0.6rem;border-radius:12px;
                         font-size:0.7rem;font-weight:600;">{mode_label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_transit_kpis(itin: dict) -> None:
    """4 colonnes métriques : durée, marche, correspondances, retard."""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🕐 Durée totale", f"~{itin['total_duration_min']:.0f} min")
    with col2:
        st.metric("🚶 Marche totale", f"{int(itin.get('total_walk_m', 0))} m")
    with col3:
        n_t = int(itin.get("n_transfers", 0))
        st.metric(
            "🔄 Correspondances",
            "✅ Direct" if n_t == 0 else f"{n_t} · {itin.get('transfer_hub', '?')}",
        )
    with col4:
        delay = float(itin.get("total_delay_min", 0.0))
        st.metric(
            "⚠️ Retard cumulé",
            f"+{delay:.1f} min" if delay > 0 else "✅ Aucun",
        )
    # Confiance globale (ligne discrète)
    conf = float(itin.get("confidence", 0.0))
    st.caption(
        f"📊 Confiance globale : {int(conf * 100)}% "
        f"(basée sur le nombre d'observations des cadences)"
    )


def _render_transit_segments(itin: dict) -> None:
    """Cards détaillées par segment TC."""
    segments = itin.get("segments", [])
    st.markdown(
        f"##### 🛣️ Détail des {len(segments)} segment"
        f"{'s' if len(segments) > 1 else ''}"
    )

    for i, seg in enumerate(segments, 1):
        color = _MODE_COLOR.get(seg.get("line_mode", ""), "#666")
        walk_to_min = round((seg.get("distance_walk_to_m", 0) / 1000.0) / 4.5 * 60.0, 1)
        walk_from_min = round((seg.get("distance_walk_from_m", 0) / 1000.0) / 4.5 * 60.0, 1)
        confidence_pct = int(float(seg.get("confidence", 0.0)) * 100)
        delay_min = float(seg.get("delay_avg_min", 0.0))

        # Marche d'accès au premier arrêt
        if seg.get("distance_walk_to_m", 0) > 0:
            st.markdown(
                f"<div style='font-size:0.85rem;opacity:0.75;padding:0.2rem 0 0.2rem 2rem;'>"
                f"🚶 {walk_to_min:.0f} min à pied → arrêt "
                f"<b>{seg.get('stop_origin', '?')}</b> "
                f"({seg['distance_walk_to_m']}m)</div>",
                unsafe_allow_html=True,
            )

        # Carte segment
        delay_html = (
            f" · ⚠️ Retard moyen : +{delay_min:.1f} min"
            if delay_min > 0
            else " · ✅ Pas de retard notable"
        )
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:0.8rem;
                        padding:0.7rem;background:var(--bg-card);border-radius:4px;
                        margin:0.3rem 0;border-left:4px solid {color};">
                <div style="background:{color};color:white;width:34px;height:34px;
                            border-radius:50%;display:flex;align-items:center;
                            justify-content:center;font-weight:700;font-size:1rem;
                            flex-shrink:0;">
                    {i}
                </div>
                <div style="flex:1;">
                    <div style="font-weight:700;font-size:1.05rem;">
                        {seg.get('line_label', '?')}
                        <span style="opacity:0.5;font-weight:400;font-size:0.85rem;">
                            ~{seg.get('duration_estimate_min', 0):.0f} min
                        </span>
                    </div>
                    <div style="font-size:0.85rem;opacity:0.85;margin-top:0.1rem;">
                        <b>{seg.get('stop_origin', '?')}</b> → <b>{seg.get('stop_dest', '?')}</b>
                    </div>
                    <div style="font-size:0.75rem;opacity:0.65;margin-top:0.25rem;">
                        ⏱ Fréquence : ~{seg.get('cadence_min', 0):.0f} min
                        · ⏳ Attente : ~{seg.get('wait_estimate_min', 0):.0f} min
                        {delay_html}
                        · 📊 Confiance : {confidence_pct}%
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Indicateur correspondance (entre 2 segments)
        if i < len(segments):
            next_seg = segments[i]
            next_color = _MODE_COLOR.get(next_seg.get("line_mode", ""), "#666")
            st.markdown(
                f"<div style='text-align:center;font-size:0.85rem;"
                f"opacity:0.75;padding:0.4rem 0;'>"
                f"⬇ Correspondance à <b>{itin.get('transfer_hub', '?')}</b> "
                f"~3 min (marche inter-arrêts) — "
                f"<span style='color:{next_color};font-weight:600;'>"
                f"{next_seg.get('line_label', '?')}</span></div>",
                unsafe_allow_html=True,
            )

        # Marche d'arrivée après le dernier segment
        if i == len(segments) and seg.get("distance_walk_from_m", 0) > 0:
            st.markdown(
                f"<div style='font-size:0.85rem;opacity:0.75;padding:0.2rem 0 0.2rem 2rem;'>"
                f"🚶 {walk_from_min:.0f} min à pied → destination "
                f"({seg['distance_walk_from_m']}m)</div>",
                unsafe_allow_html=True,
            )


def _render_transit_disclaimer() -> None:
    """Disclaimer permanent (fréquences estimées, pas horaires exacts GTFS)."""
    st.info(
        "ℹ️ **Fréquences estimées** à partir des cadences observées. "
        "Pas d'horaires exacts (données GTFS non encore ingérées — Phase 2). "
        "Retards = moyenne sur 7 jours glissants à cette tranche horaire. "
        "**Limites Phase 1** : 21 lieux du référentiel, 1 correspondance maximum."
    )
