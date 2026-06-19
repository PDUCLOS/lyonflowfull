"""Calculateur d'impact écologique et économique par mode de transport (Sprint 15+).

Adapté de ``PDUCLOS/Lyontraffic`` pour le pipeline LyonFlowFull :
- Sources données : ADEME 2024, Grille TCL SYTRAL 2026, Ville de Lyon 2025,
  MET tables ADEME/INSERM (calories).
- Le coût voiture **n'inclut pas le parking** (Phase 1) — voir
  ``scripts/sql/migration_016_tarifs_modes.sql`` pour le hook futur :
  ``_voiture_parking_cost(duration_min)`` pourra lire la table
  ``gold.tarifs_modes`` et appliquer la grille zone 1/2/3 Lyon.

Politique projet (Sprint 8) — ZÉRO MOCK : module pur Python, pas de DB.
Si un paramètre est invalide (mode inconnu, distance < 0), ``ValueError``.
La connexion DB / l'indispo de la DB est gérée en amont dans
``src.routing.pathfinder_multimodal._require_db_or_raise()``.

Usage::

    from src.routing.eco_calculator import (
        calculate_impact,
        get_comparison,
        recommend_mode,
    )

    impact = calculate_impact("voiture", distance_km=5.0, is_congested=True)
    # {"co2_g": 1351.0, "cost_eur": 1.30, "fuel_l": 0.525, ...}

    cmp = get_comparison(distance_km=3.0, durations={"voiture": 8, "tc": 15, "velov": 14})
    # {"voiture": {...}, "tc": {...}, "velov": {...}}

    reco = recommend_mode(cmp, critere="cout", durations=durations)
    # {"winner": "voiture", "scores": {...}, "explanation": "..."}

Sprint 15+ (2026-06-19) — Première version. Adapte le code LyonTraffic
lignes 270-314 (`calculate_impact` + `get_comparison`) en l'enrichissant
avec `duration_min` (pour calories) + scoring composite (cf. spec Annexe A).
"""

from __future__ import annotations

import logging
from typing import TypedDict

logger = logging.getLogger(__name__)


# =============================================================================
# Constantes — sources documentées
# =============================================================================

# Voiture — ADEME 2024, mix urbain France
VOITURE_CO2_G_PER_KM = 193.0  # g CO2/km (ADEME Base Carbone 2024, VP essence)
VOITURE_FUEL_L_PER_100KM = 7.5  # L/100km (ADEME, consommation VP moyenne urbaine)
VOITURE_FUEL_PRICE_EUR = 1.85  # €/L SP95 (prix moyen France 2026-05)
VOITURE_CONGESTION_PENALTY = 1.4  # +40% conso en bouchons (ADEME, étude impact trafic)

# Transport en commun — mix bus/tram/métro Lyon
TCL_CO2_G_PER_KM = 35.0  # g CO2/passager-km (SYTRAL/ADEME, mix métro-tram-bus)
TCL_TICKET_UNITAIRE_EUR = 2.05  # tarif TCL ticket unitaire (SYTRAL 2026)

# Vélov — mobilité douce
VELOV_CO2_G_PER_KM = 0.0  # g CO2/km (hors fabrication vélo, scope opérationnel)
VELOV_COST_EUR = 0.0  # € — gratuit < 30 min pour abonné annuel
VELOV_COST_JOUR_EUR = 1.50  # € — ticket 1 jour (cas non-abonné)

# Calories — MET tables ADEME/INSERM (kcal/km pour un adulte ~70 kg)
CALORIES_PER_KM = {"velov": 46.0, "marche": 50.0}

# Détection congestion voiture (< 25 km/h vitesse moyenne = bouchons)
_CONGESTION_SPEED_THRESHOLD_KMH = 25.0

# Scoring composite (cf. spec Annexe A) — 1 min vaut ~0.30 € pour l'usager
# Source : valeur du temps CEREMA 2023 (~18 €/h).
_TIME_VALUE_EUR_PER_MIN = 0.30  # € équivalent par minute gagnée


# =============================================================================
# Types — TypedDict pour auto-complétion IDE + sérialisabilité Streamlit
# =============================================================================


class ModeImpact(TypedDict):
    """Impact écologique + économique d'un trajet pour 1 mode.

    Attributes:
        co2_g: grammes CO2 émis (0 pour Vélov).
        cost_eur: coût en euros (0 pour Vélov < 30min abonné).
        fuel_l: litres de carburant brûlés (0 sauf voiture).
        calories_kcal: calories brûlées (Vélov/marche uniquement).
        is_congested: True si voiture en bouchons (détermine pénalité).
        congestion_penalty: facteur multiplicateur conso (1.0 ou 1.4).
    """

    co2_g: float
    cost_eur: float
    fuel_l: float
    calories_kcal: int
    is_congested: bool
    congestion_penalty: float


class ModeRecommendation(TypedDict):
    """Résultat de ``recommend_mode``.

    Attributes:
        winner: mode recommandé ("voiture" | "tc" | "velov").
        scores: score composite par mode (le winner = plus bas score).
        explanation: texte lisible pour l'usager (1-2 phrases).
    """

    winner: str
    scores: dict[str, float]
    explanation: str


# =============================================================================
# API publique
# =============================================================================


def calculate_impact(
    mode: str,
    distance_km: float,
    is_congested: bool = False,
    duration_min: float | None = None,
) -> ModeImpact:
    """Calcule CO2, coût, carburant et calories pour un trajet mono-mode.

    Args:
        mode: ``"voiture"`` | ``"tc"`` | ``"velov"``.
        distance_km: distance du trajet en kilomètres (>= 0).
        is_congested: True si voiture en bouchons (augmente conso +40%).
            Ignoré pour TC et Vélov.
        duration_min: durée réelle du trajet (utilisée uniquement pour
            l'enrichissement, ex. affichage cohérent calories). Optionnel.

    Returns:
        ``ModeImpact`` avec toutes les composantes arrondies à 2 décimales.

    Raises:
        ValueError: si ``mode`` n'est pas dans ``{"voiture", "tc", "velov"}``
            ou si ``distance_km < 0``.
    """
    if mode not in ("voiture", "tc", "velov"):
        raise ValueError(
            f"Mode inconnu : {mode!r}. Attendus : 'voiture', 'tc', 'velov'."
        )
    if distance_km < 0:
        raise ValueError(f"distance_km négative : {distance_km}")

    impact: ModeImpact = {
        "co2_g": 0.0,
        "cost_eur": 0.0,
        "fuel_l": 0.0,
        "calories_kcal": 0,
        "is_congested": False,
        "congestion_penalty": 1.0,
    }

    if mode == "voiture":
        penalty = VOITURE_CONGESTION_PENALTY if is_congested else 1.0
        impact["is_congested"] = bool(is_congested)
        impact["congestion_penalty"] = penalty
        impact["fuel_l"] = round((VOITURE_FUEL_L_PER_100KM / 100.0) * distance_km * penalty, 2)
        impact["co2_g"] = round(VOITURE_CO2_G_PER_KM * distance_km * penalty, 2)
        impact["cost_eur"] = round(impact["fuel_l"] * VOITURE_FUEL_PRICE_EUR, 2)
        # Pas de calories (usager passager voiture, pas effort physique)
    elif mode == "tc":
        impact["co2_g"] = round(TCL_CO2_G_PER_KM * distance_km, 2)
        impact["cost_eur"] = round(TCL_TICKET_UNITAIRE_EUR, 2)  # ticket fixe
        # Pas de calories (passager assis) ni carburant (scope opérationnel TCL)
    elif mode == "velov":
        impact["co2_g"] = round(VELOV_CO2_G_PER_KM * distance_km, 2)
        impact["cost_eur"] = round(VELOV_COST_EUR, 2)  # gratuit abonné
        impact["calories_kcal"] = int(round(CALORIES_PER_KM["velov"] * distance_km))

    # duration_min est pour l'instant non utilisé (réservé pour extension —
    # ex. calories marcheurs en mode "marche" future, ou chaleur corporelle).
    _ = duration_min  # noqa: F841 — intentional placeholder

    return impact


def get_comparison(
    distance_km: float,
    is_congested: bool = False,
    durations: dict[str, float] | None = None,
) -> dict[str, ModeImpact]:
    """Calcule l'impact pour les 3 modes en une fois.

    Args:
        distance_km: distance en km (>= 0).
        is_congested: True si voiture en bouchons (impacte voiture uniquement).
        durations: optionnel, ``{"voiture": min, "tc": min, "velov": min}``.
            Passé à ``calculate_impact`` pour extension future.

    Returns:
        Dict ``{"voiture": ModeImpact, "tc": ModeImpact, "velov": ModeImpact}``.
        Si ``distance_km == 0``, tous les impacts sont nuls (mais valides).

    Raises:
        ValueError: si ``distance_km < 0``.
    """
    if distance_km < 0:
        raise ValueError(f"distance_km négative : {distance_km}")

    durations = durations or {}
    return {
        "voiture": calculate_impact(
            "voiture",
            distance_km,
            is_congested=is_congested,
            duration_min=durations.get("voiture"),
        ),
        "tc": calculate_impact(
            "tc",
            distance_km,
            duration_min=durations.get("tc"),
        ),
        "velov": calculate_impact(
            "velov",
            distance_km,
            duration_min=durations.get("velov"),
        ),
    }


def recommend_mode(
    comparison: dict[str, ModeImpact],
    critere: str = "temps",
    durations: dict[str, float] | None = None,
) -> ModeRecommendation:
    """Recommande le meilleur mode selon le critère + calcule les scores.

    Scoring composite (cf. spec Annexe A) :
    - ``critere == "temps"`` : ``score = duration_min`` (le plus bas gagne).
    - ``critere == "cout"``  : ``score = duration_min + cost_eur / 0.30``
      (équivalent : 1 minute gagnée = 0.30 €, CEREMA 2023).

    Args:
        comparison: sortie de ``get_comparison()``.
        critere: ``"temps"`` | ``"cout"``.
        durations: ``{"voiture": min, "tc": min, "velov": min}`` — obligatoire
            pour le scoring, sinon tous les modes = même score 9999.

    Returns:
        ``ModeRecommendation`` avec winner, scores par mode, explication.

    Raises:
        ValueError: si ``critere`` n'est pas ``"temps"`` ou ``"cout"``.
    """
    if critere not in ("temps", "cout"):
        raise ValueError(
            f"critere inconnu : {critere!r}. Attendus : 'temps', 'cout'."
        )
    if not comparison:
        raise ValueError("comparison vide")

    durations = durations or {}
    scores: dict[str, float] = {}

    for mode_key, impact in comparison.items():
        duration = float(durations.get(mode_key, 0.0) or 0.0)
        cost = float(impact.get("cost_eur", 0.0) or 0.0)

        if critere == "temps":
            scores[mode_key] = duration if duration > 0 else 9999.0
        else:  # "cout"
            # duration_min + cost_eur × (1 min / 0.30€) = duration + cost/0.30
            scores[mode_key] = duration + cost / _TIME_VALUE_EUR_PER_MIN

    # Winner = mode avec le score le plus bas (parmi ceux qui ont un score < 9999)
    feasible = {k: v for k, v in scores.items() if v < 9999.0}
    if feasible:
        winner = min(feasible, key=lambda k: feasible[k])
    else:
        # Aucune durée fournie : fallback sur le mode le moins coûteux
        winner = min(comparison, key=lambda k: comparison[k].get("cost_eur", 0.0))

    explanation = _build_explanation(winner, comparison, scores, critere, durations)

    return {
        "winner": winner,
        "scores": scores,
        "explanation": explanation,
    }


# =============================================================================
# Helpers privés
# =============================================================================


def _build_explanation(
    winner: str,
    comparison: dict[str, ModeImpact],
    scores: dict[str, float],
    critere: str,
    durations: dict[str, float],
) -> str:
    """Construit un texte d'explication lisible pour l'usager.

    Le texte est volontairement court (1-2 phrases) et adapté au critère.
    """
    mode_label = {"voiture": "voiture", "tc": "transports en commun", "velov": "Vélov"}
    duration_w = durations.get(winner, 0.0)
    cost_w = comparison.get(winner, {}).get("cost_eur", 0.0)
    co2_w = comparison.get(winner, {}).get("co2_g", 0.0)

    if critere == "temps":
        if duration_w <= 0:
            return f"🏆 Mode recommandé : {mode_label[winner]} (durée indisponible)."
        return (
            f"🏆 Mode le plus rapide : **{mode_label[winner]}** "
            f"(~{duration_w:.0f} min, {cost_w:.2f} €, {int(co2_w)} g CO2)."
        )

    # critere == "cout"
    return (
        f"🏆 Meilleur rapport temps/coût : **{mode_label[winner]}** "
        f"(score composite {scores[winner]:.1f}, "
        f"~{duration_w:.0f} min, {cost_w:.2f} €)."
    )


def _is_congested_from_speed(avg_speed_kmh: float) -> bool:
    """Détecte la congestion voiture depuis la vitesse moyenne.

    Seuil : < 25 km/h = bouchon (référence ADEME, étude impact trafic urbain).
    Utilisé par ``Usager_1_Mon_Trajet`` pour passer le flag à ``calculate_impact``
    sans dupliquer la logique.
    """
    return avg_speed_kmh > 0 and avg_speed_kmh < _CONGESTION_SPEED_THRESHOLD_KMH


def _voiture_parking_cost_placeholder(duration_min: float) -> float:
    """Hook Phase 2 — coût parking Lyon (non implémenté en Phase 1).

    Le parking voiture est volontairement exclu du scope Phase 1 (cf.
    spec §3.4 et §11.4). Cette fonction est un placeholder documenté :
    quand Phase 2 sera livrée, elle lira ``gold.tarifs_modes`` (cf.
    migration 016) et appliquera la grille 3 zones Lyon (cf. Annexe C
    spec LyonTraffic).

    Args:
        duration_min: durée du stationnement en minutes.

    Returns:
        0.0 par défaut. À surcharger.
    """
    return 0.0