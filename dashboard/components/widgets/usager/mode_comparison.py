"""Widget — Comparateur 3 modes + recommandation (Phase 2 Sprint 15+).

Affiche côte à côte les 3 modes (TC / voiture / Vélov) avec :
- Une **winner card** mise en avant (bordure colorée + badge 🏆 RECOMMANDÉ)
- 2 cards alternatives plus sobres
- Un insight contextuel ("Vélov économise Xg CO2 vs voiture")

L'usager clique ensuite sur le mode de son choix → la page Usager_1
appelle alors le widget détaillé correspondant (transit_trip, velov_trip,
itinerary).

Politique projet (Sprint 8+) — ZÉRO MOCK : si un mode est indisponible
(source="unavailable" ou DB error), la card est grisée avec message
explicite. Pas de fallback silencieux.

Sprint 15+ (2026-06-19) — Première version. S'inspire de la page
``Lyontraffic/dashboard/pages/9_Recommandation_Trajet.py`` (winner card
HTML lignes 1042-1057) en l'adaptant aux CSS variables du thème
LyonFlowFull (``--bg-card``, ``--primary-color``, etc.).
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.loading_state import loading_wrapper

# Couleurs winner/alternatives — cohérent avec colors.py + spec §5.4
_WINNER_ACCENT = "#4CAF50"  # vert (gagnant)
_ALT_ACCENT = "#9E9E9E"  # gris (alternatives)
_UNAVAILABLE_ACCENT = "#455A64"  # gris foncé (mode indispo)

_MODE_META = {
    "tc": {"icon": "🚌", "label": "Transport en commun", "color": "#1976D2"},
    "voiture": {"icon": "🚗", "label": "Voiture", "color": "#FF9800"},
    "velov": {"icon": "🚲", "label": "Vélov", "color": "#43A047"},
}


def render_mode_comparison(
    results: dict[str, dict],
    critere: str = "temps",
    origin: str = "",
    destination: str = "",
    recommendation: dict | None = None,
) -> str | None:
    """Affiche le comparatif 3 modes + winner card.

    Args:
        results: pour chaque mode (``"tc"`` / ``"voiture"`` / ``"velov"``),
            un dict avec :
            - ``duration_min`` (float)
            - ``distance_km`` (float)
            - ``impact`` (dict, sortie ``calculate_impact``)
            - ``feasible`` (bool)
            - ``source`` (str — "db" | "unavailable" | "demo" (jamais en prod))
        critere: ``"temps"`` | ``"cout"`` — critère de recommandation.
        origin: label O (affichage bannière).
        destination: label D (affichage bannière).
        recommendation: sortie optionnelle de ``recommend_mode()``
            (winner + scores + explanation). Si None, on calcule localement
            à partir de ``results``.

    Returns:
        Le mode sélectionné par l'usager (clic sur le bouton "Voir détail")
        ou ``None`` si l'usager n'a rien cliqué.

    Raises:
        N/A — affiche ``st.warning`` / ``st.error`` si un mode manque.
    """
    with loading_wrapper("Chargement Mode comparison…", "⏳"):
        # Bannière trajet
        if origin and destination:
            st.markdown(
                f"""
                <div class="lyf-label" style="background:var(--bg-card);padding:0.7rem 1rem;border-radius:8px;border-left:4px solid {_WINNER_ACCENT};display:flex;align-items:center;gap:0.6rem;margin-bottom:1rem;flex-wrap:wrap;">
                    <span class="lyf-sublabel" style="background:#4CAF50;color:white;padding:0.2rem 0.6rem;border-radius:12px;font-weight:600;">🟢 DÉPART</span>
                    <span style="font-weight:600;">{origin}</span>
                    <span style="opacity:0.4;margin:0 0.5rem;">→</span>
                    <span class="lyf-sublabel" style="background:#F44336;color:white;padding:0.2rem 0.6rem;border-radius:12px;font-weight:600;">🔴 ARRIVÉE</span>
                    <span style="font-weight:600;">{destination}</span>
                    <span style="margin-left:auto;opacity:0.7;font-size:0.8rem;">
                        Critère : <b>{"⏱️ Temps" if critere == "temps" else "💰 Coût"}</b>
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Calcul recommandation si pas fournie
        if recommendation is None:
            recommendation = _compute_recommendation(results, critere)

        winner = recommendation.get("winner", "")

        # Layout 3 colonnes : winner au centre si possible (TC par défaut),
        # sinon première colonne
        col_order = _order_columns_by_recommendation(results, winner)
        cols = st.columns(3)

        selected_mode: str | None = None
        for col, mode_key in zip(cols, col_order):
            with col:
                result = results.get(mode_key, {})
                is_winner = mode_key == winner
                chosen = _render_mode_card(
                    mode_key=mode_key,
                    result=result,
                    is_winner=is_winner,
                    score=recommendation.get("scores", {}).get(mode_key),
                )
                if chosen is not None:
                    selected_mode = chosen

        # Insight contextuel
        if winner and winner in results:
            _render_insight(results, winner)

        # Explication textuelle
        if recommendation.get("explanation"):
            st.caption(f"💡 {recommendation['explanation']}")

        return selected_mode


    # =============================================================================
    # Helpers privés
    # =============================================================================


def _render_mode_card(
    mode_key: str,
    result: dict,
    is_winner: bool,
    score: float | None,
) -> str | None:
    """Affiche une card mode (winner ou alternative) + bouton 'Voir détail'.

    Returns:
        Le mode si l'usager a cliqué 'Voir détail', sinon None.
    """
    meta = _MODE_META.get(mode_key, {"icon": "❓", "label": mode_key, "color": "#666"})
    icon, label, color = meta["icon"], meta["label"], meta["color"]

    # Mode indisponible → card grisée sans bouton
    if not result or not result.get("feasible", False) or result.get("source") == "unavailable":
        st.html(
            f"""
            <div class="lyonflow-card"
                 style="border-left:4px solid {_UNAVAILABLE_ACCENT};opacity:0.55;
                        min-height:200px;display:flex;flex-direction:column;justify-content:center;">
                <div class="lyf-value" style="font-weight:700;opacity:0.5;">
                    {icon} {label}
                </div>
                <div class="lyf-detail" style="opacity:0.6;margin-top:0.4rem;">
                    ⚠️ Indisponible pour ce trajet
                </div>
                <div class="lyf-sublabel" style="opacity:0.5;margin-top:0.3rem;font-style:italic;">
                    Source: {result.get("source", "?") if result else "aucune"}
                </div>
            </div>
            """
        )
        return None

    impact = result.get("impact", {})
    duration = float(result.get("duration_min", 0.0) or 0.0)
    distance = float(result.get("distance_km", 0.0) or 0.0)
    cost = float(impact.get("cost_eur", 0.0) or 0.0)
    co2 = float(impact.get("co2_g", 0.0) or 0.0)
    calories = int(impact.get("calories_kcal", 0) or 0)

    # Card HTML
    accent = _WINNER_ACCENT if is_winner else _ALT_ACCENT
    winner_badge = (
        f'<span class="lyf-sublabel" style="background:{_WINNER_ACCENT};color:white;padding:0.25rem 0.7rem;'
        f'border-radius:12px;font-weight:700;letter-spacing:0.5px;">'
        f"🏆 RECOMMANDÉ</span>"
        if is_winner
        else ""
    )
    score_html = f'<span class="lyf-sublabel" style="opacity:0.6;">score: {score:.1f}</span>' if score is not None else ""

    # Sprint 16 Axe C — Badge "estimé/calculé" selon result.source.
    # computed = durée réellement calculée par le widget trajet
    # estimated = fallback vitesse moyenne (avant que l'usager clique "Voir détail")
    source = result.get("source", "estimated")
    if source == "computed":
        source_badge = (
            '<div class="lyf-sublabel" style="color:#4CAF50;font-weight:600;'
            'margin-top:0.3rem;">✅ Durée calculée</div>'
        )
    else:
        source_badge = (
            '<div class="lyf-sublabel" style="color:#FF9800;font-weight:600;'
            'margin-top:0.3rem;">⏱️ Estimé (cliquez "Voir détail" pour la durée réelle)</div>'
        )

    calories_html = (
        f'<div class="lyf-detail" style="opacity:0.85;margin-top:0.3rem;">🔥 {calories} kcal</div>'
        if mode_key == "velov"
        else ""
    )

    congested_html = (
        f'<div class="lyf-sublabel" style="color:{_WINNER_ACCENT};font-weight:600;margin-top:0.3rem;">'
        f"⚠️ Trafic congestionné</div>"
        if mode_key == "voiture" and impact.get("is_congested")
        else ""
    )

    st.html(
        f"""
        <div class="lyonflow-card" style="border-left:4px solid {accent};
                    {"box-shadow:0 4px 16px rgba(76,175,80,0.25);" if is_winner else ""}">
            <div style="display:flex;justify-content:space-between;align-items:center;
                        gap:0.5rem;flex-wrap:wrap;">
                <span class="lyf-value" style="font-weight:700;color:{color};">
                    {icon} {label}
                </span>
                {winner_badge}
            </div>
            <div style="font-size:2rem;font-weight:700;margin:0.6rem 0 0.3rem 0;
                        color:{color};line-height:1.1;">
                {duration:.0f} <span style="font-size:1rem;font-weight:500;opacity:0.7;">min</span>
            </div>
            {source_badge}
            <div class="lyf-detail" style="display:flex;gap:1rem;flex-wrap:wrap;opacity:0.9;">
                <span>💰 {cost:.2f} €</span>
                <span>🌿 {int(co2)} g CO2</span>
                <span>📏 {distance:.2f} km</span>
            </div>
            {calories_html}
            {congested_html}
            <div style="margin-top:0.5rem;display:flex;justify-content:space-between;
                        align-items:center;">
                {score_html}
            </div>
        </div>
        """
    )

    # Bouton "Voir détail" — retourne mode_key si cliqué, None sinon
    btn_label = "👁️ Voir le détail"
    if st.button(
        btn_label,
        key=f"see_detail_{mode_key}",
        type="primary" if is_winner else "secondary",
        use_container_width=True,
    ):
        return mode_key
    return None


def _render_insight(results: dict[str, dict], winner: str) -> None:
    """Affiche un insight contextuel (économie CO2 vs voiture, etc.)."""
    winner_result = results.get(winner, {})
    winner_impact = winner_result.get("impact", {})
    winner_co2 = float(winner_impact.get("co2_g", 0.0) or 0.0)
    voiture_result = results.get("voiture", {})
    voiture_impact = voiture_result.get("impact", {}) if voiture_result else {}
    voiture_co2 = float(voiture_impact.get("co2_g", 0.0) or 0.0)
    velov_result = results.get("velov", {})
    velov_impact = velov_result.get("impact", {}) if velov_result else {}

    insights: list[str] = []

    # Économie CO2 si le winner n'est pas la voiture et que la voiture est dispo
    if winner != "voiture" and voiture_result.get("feasible", False) and voiture_co2 > 0:
        saved_co2 = voiture_co2 - winner_co2
        if saved_co2 > 0:
            mode_label = _MODE_META.get(winner, {}).get("label", winner)
            voiture_label = _MODE_META.get("voiture", {}).get("label", "voiture")
            insights.append(
                f"🌿 **{mode_label}** économise **{int(saved_co2)} g de CO2** vs **{voiture_label}** sur ce trajet."
            )

    # Bonus calories Vélov
    if winner == "velov" and velov_impact.get("calories_kcal", 0) > 0:
        kcal = int(velov_impact["calories_kcal"])
        insights.append(f"🔥 **{kcal} kcal** brûlées en pédalant (≈ {kcal // 50} min de marche rapide).")

    if insights:
        for ins in insights:
            st.info(ins)


def _order_columns_by_recommendation(
    results: dict[str, dict],
    winner: str,
) -> list[str]:
    """Ordonne les colonnes : winner au centre, alternatives à gauche/droite."""
    available = [m for m in ("tc", "voiture", "velov") if m in results]
    others = [m for m in available if m != winner]

    if winner in available:
        # Place winner en colonne du milieu (index 1)
        if len(others) >= 2:
            return [others[0], winner, others[1]]
        elif len(others) == 1:
            return [winner, others[0], winner]  # fallback si 2 modes dispos
        else:
            return [winner]
    return available


def _compute_recommendation(results: dict[str, dict], critere: str) -> dict:
    """Calcule la recommandation localement (sans appeler recommend_mode).

    Évite la dépendance sur ``recommend_mode`` côté widget (le widget est
    lui-même testable sans la lib routing). Logique identique à
    ``src.routing.eco_calculator.recommend_mode``.
    """
    durations = {m: float(r.get("duration_min", 0.0) or 0.0) for m, r in results.items()}
    scores: dict[str, float] = {}
    for mode_key, result in results.items():
        if not result.get("feasible", False):
            scores[mode_key] = 9999.0
            continue
        duration = durations[mode_key]
        cost = float(result.get("impact", {}).get("cost_eur", 0.0) or 0.0)
        if critere == "temps":
            scores[mode_key] = duration if duration > 0 else 9999.0
        else:  # "cout"
            scores[mode_key] = duration + cost / 0.30  # 1 min ~ 0.30€

    feasible = {k: v for k, v in scores.items() if v < 9999.0}
    if feasible:
        winner = min(feasible, key=lambda k: feasible[k])
    else:
        winner = "tc"  # fallback par défaut

    mode_label = _MODE_META.get(winner, {}).get("label", winner)
    explanation = f"🏆 **{mode_label}** recommandé selon le critère {'⏱️ temps' if critere == 'temps' else '💰 coût'}."

    return {"winner": winner, "scores": scores, "explanation": explanation}
