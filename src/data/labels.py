"""Référentiels de libellés pour le tableau de bord (Juin 2026).

Ce module contient les **référentiels statiques** : libellés en français,
codes couleurs hexagonaux, et étiquettes des modes de transport. Ce ne sont PAS
des données simulées (mocks) : il s'agit de conventions d'interface utilisateur
immuables.

Historiquement, ces constantes se trouvaient dans un module lié aux mocks,
ce qui prêtait à confusion. Cette dette technique de nomenclature a été corrigée :
le module neutre `labels.py` regroupe désormais tous ces référentiels visuels.
Les véritables mocks (données générées pour tests) sont strictement confinés
dans le répertoire `tests/fixtures/mock_data/`.
"""

from __future__ import annotations

# Codes diagnostiques pour l'infrastructure et le trafic (cf. scripts SQL)
# Valeurs possibles observées dans la table gold.infrastructure_bottlenecks.diagnosis
DIAGNOSIS_LABELS: dict[str, str] = {
    "ok": "OK",
    "infra": "Infrastructure",
    "operations": "Exploitation",
    "bus_lane_ok": "Voie de bus fluide",
}


# Codes couleurs officiels par mode de transport (utilisés pour la data visualisation)
MODE_COLORS: dict[str, str] = {
    "metro": "#E2001A",
    "tram": "#FFCD00",
    "bus": "#3498DB",
    "velov": "#00A88E",
    "car": "#7F8C8D",
    "walk": "#95A5A6",
}


# Niveaux de performance horaire OTP (On-Time Performance)
OTP_STATUS_LABELS: dict[str, str] = {
    "excellent": "Excellent",
    "bon": "Bon",
    "moyen": "Moyen",
    "mediocre": "Médiocre",
    "unknown": "N/D",
}


# Étiquettes d'état des stations Vélo'v (utilisées dans referentiel.lieux_calendrier)
VELOV_STATUS_LABELS: dict[str, str] = {
    "OK": "OK",
    "FAIBLE": "Faible",
    "VIDE": "Vide",
    "PLEINE": "Pleine",
    "UNKNOWN": "N/D",
}
