"""Référentiels de libellés (Sprint 8, 2026-06-12).

Ce module contient les **référentiels statiques** : libellés FR,
codes couleur, libellés de modes. Ce ne sont PAS des mocks : ce sont
des conventions de présentation qui ne varient pas.

Avant Sprint 8, ces constantes étaient dans un module `mock`, ce qui
laissait penser que c'étaient des données mock. C'est une dette de
nomenclature qui a été corrigée : module neutre `labels.py` qui
regroupe tous les référentiels statiques. Les mocks (données
générées) sont relégués dans `tests/fixtures/mock_data/`.
"""

from __future__ import annotations

# Codes diagnostic infrastructure / trafic (cf. scripts/sql)
# Valeurs possibles dans gold.infrastructure_bottlenecks.diagnosis
DIAGNOSIS_LABELS: dict[str, str] = {
    "ok": "✅ OK",
    "infra": "🔴 Infrastructure",
    "operations": "🟡 Exploitation",
    "bus_lane_ok": "🔵 Voie bus OK",
}


# Codes couleur par mode de transport (cf. data viz)
MODE_COLORS: dict[str, str] = {
    "metro": "#E2001A",
    "tram": "#FFCD00",
    "bus": "#3498DB",
    "velov": "#00A88E",
    "car": "#7F8C8D",
    "walk": "#95A5A6",
}


# Niveaux OTP (On-Time Performance)
OTP_STATUS_LABELS: dict[str, str] = {
    "excellent": "🟢 Excellent",
    "bon": "🟡 Bon",
    "moyen": "🟠 Moyen",
    "mediocre": "🔴 Médiocre",
    "unknown": "⚪ N/D",
}


# Étiquettes de status Vélov (cf. referentiel.lieux_calendrier / smart routing)
VELOV_STATUS_LABELS: dict[str, str] = {
    "OK": "🟢 OK",
    "FAIBLE": "🟡 Faible",
    "VIDE": "🔴 Vide",
    "PLEINE": "🔴 Pleine",
    "UNKNOWN": "⚪ N/D",
}
