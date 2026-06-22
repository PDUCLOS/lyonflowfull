"""Affichage des erreurs adapté au persona — Sprint 20 Axe D.

Le pattern actuel ``st.error(f"⚠️ {e}")`` expose le message technique brut
de l'exception (ex: ``[gold.trafic_predictions] Données pipeline indisponibles
— PostgreSQL ne répond pas. Vérifier POSTGRES_HOST/PORT/PASSWORD et
docker compose up postgres``) à l'usager final, qui ne sait pas ce qu'est
PostgreSQL.

``show_error`` adapte le message au persona courant :
- **usager** : message simple, sans terme technique
- **pro_tcl** : message + détail technique dans un expander repliable
- **elu** : message factuel et sobre

Cf. docs/SPEC_SPRINT_20_UX.md §5.
"""

from __future__ import annotations

import streamlit as st

from src.persona.manager import get_current_persona

# Messages par persona × type d'erreur.
# Type d'erreur = clé métier (db_down, no_data, geocoding_fail, etc.)
_MESSAGES: dict[str, dict[str, str]] = {
    "usager": {
        "db_down": "Les données sont temporairement indisponibles. Réessayez dans quelques minutes.",
        "no_data": "Pas encore de données pour cette période.",
        "geocoding_fail": "Adresse non reconnue. Essayez un lieu connu (Part-Dieu, Bellecour…).",
        "routing_fail": "Itinéraire indisponible. Réessayez ou choisissez un autre trajet.",
        "generic": "Une erreur est survenue. Réessayez dans quelques instants.",
    },
    "pro_tcl": {
        "db_down": "Pipeline indisponible — vérifier le statut dans Pipeline Management (Pro_6).",
        "no_data": "Aucune donnée pour ce filtre. Vérifier la fenêtre temporelle et les seuils.",
        "geocoding_fail": "Géocodage échoué. Adresse hors périmètre Lyon Métropole ?",
        "routing_fail": "Calcul itinéraire échoué — vérifier connectivité pgRouting et réseau OSM importé.",
        "generic": "Erreur inattendue. Consulter les logs Airflow pour le diagnostic complet.",
    },
    "elu": {
        "db_down": "Source de données temporairement inaccessible.",
        "no_data": "Données non disponibles pour la période sélectionnée.",
        "geocoding_fail": "Lieu non trouvé.",
        "routing_fail": "Service de calcul d'itinéraire temporairement indisponible.",
        "generic": "Données temporairement indisponibles.",
    },
}


def get_error_message(persona: str | None, error_type: str, detail: str = "") -> str:
    """Retourne le message d'erreur formaté pour un persona (fonction pure).

    Args:
        persona: identifiant persona ("usager", "pro_tcl", "elu", ou None).
        error_type: clé dans _MESSAGES (db_down, no_data, etc.).
        detail: info technique (retournée en fallback si error_type inconnu).

    Returns:
        Message formaté, vide si persona inconnu.
    """
    p = persona if persona in _MESSAGES else "usager"
    messages = _MESSAGES[p]
    if error_type in messages:
        return messages[error_type]
    return detail or messages.get("generic", "")


def show_error(error_type: str, detail: str = "") -> None:
    """Affiche un message d'erreur adapté au persona courant.

    Args:
        error_type: clé dans _MESSAGES (db_down, no_data, geocoding_fail, etc.).
        detail: info technique (affichée seulement pour pro_tcl).
    """
    persona = get_current_persona()
    msg = get_error_message(persona, error_type, detail)

    st.error(msg)
    if persona == "pro_tcl" and detail:
        with st.expander("🔧 Détail technique"):
            st.code(detail)
