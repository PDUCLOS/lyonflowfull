"""Tests unitaires — dashboard/components/error_display.py (Sprint 20 Axe D).

Couvre :
* get_error_message (fonction pure) : 3 personas × 3 types d'erreur, fallback
  sur "usager" si persona inconnu/None, fallback sur detail si type inconnu.
* _MESSAGES : couverture des 3 personas × 5 types (db_down, no_data,
  geocoding_fail, routing_fail, generic) — pas de trous.
"""

from __future__ import annotations

import pytest

from dashboard.components.error_display import _MESSAGES, get_error_message

# -----------------------------------------------------------------------------
# _MESSAGES : couverture par persona × type
# -----------------------------------------------------------------------------


class TestMessagesCoverage:
    """Chaque persona doit avoir les 5 types d'erreur définis."""

    EXPECTED_TYPES = {"db_down", "no_data", "geocoding_fail", "routing_fail", "generic"}
    EXPECTED_PERSONAS = {"usager", "pro_tcl", "elu"}

    def test_trois_personas(self) -> None:
        assert set(_MESSAGES.keys()) == self.EXPECTED_PERSONAS

    @pytest.mark.parametrize("persona", list(EXPECTED_PERSONAS))
    def test_persona_a_5_types(self, persona: str) -> None:
        assert set(_MESSAGES[persona].keys()) == self.EXPECTED_TYPES

    def test_messages_sont_non_vides(self) -> None:
        for persona, messages in _MESSAGES.items():
            for error_type, msg in messages.items():
                assert msg, f"message vide pour {persona}/{error_type}"
                assert isinstance(msg, str)


# -----------------------------------------------------------------------------
# get_error_message
# -----------------------------------------------------------------------------


class TestGetErrorMessage:
    """get_error_message retourne le bon message selon persona × error_type."""

    @pytest.mark.parametrize(
        ("persona", "error_type", "expected_substr"),
        [
            # Usager : messages simples, pas de terme technique
            ("usager", "db_down", "indisponibles"),
            ("usager", "no_data", "Pas encore de données"),
            ("usager", "geocoding_fail", "Adresse non reconnue"),
            # Pro TCL : termes techniques, mentionne les outils
            ("pro_tcl", "db_down", "Pipeline"),
            ("pro_tcl", "no_data", "filtre"),
            ("pro_tcl", "geocoding_fail", "Géocodage"),
            # Élu : sobre, factuel
            ("elu", "db_down", "inaccessible"),
            ("elu", "no_data", "non disponibles"),
            ("elu", "geocoding_fail", "non trouvé"),
        ],
    )
    def test_messages_par_persona(
        self, persona: str, error_type: str, expected_substr: str,
    ) -> None:
        msg = get_error_message(persona, error_type, "detail-xyz")
        assert expected_substr in msg, f"{persona}/{error_type}: {msg!r}"

    def test_persona_inconnu_fallback_sur_usager(self) -> None:
        """Persona inconnu (ou None) → fallback sur usager."""
        msg = get_error_message("unknown_persona", "db_down", "detail")
        assert "indisponibles" in msg  # message usager

    def test_persona_none_fallback_sur_usager(self) -> None:
        """Persona=None → fallback sur usager."""
        msg = get_error_message(None, "db_down", "detail")
        assert "indisponibles" in msg

    def test_type_inconnu_retourne_detail(self) -> None:
        """Type d'erreur inconnu → retourne le detail fourni."""
        msg = get_error_message("usager", "unknown_type", "fallback detail XYZ")
        assert msg == "fallback detail XYZ"

    def test_type_inconnu_sans_detail_retourne_generic(self) -> None:
        """Type inconnu + pas de detail → fallback sur message generic."""
        msg = get_error_message("usager", "unknown_type", "")
        # Doit retourner le message "generic" du persona usager
        assert msg == _MESSAGES["usager"]["generic"]

    def test_messages_differents_inter_personas(self) -> None:
        """Les 3 personas ont des messages différents pour le même type."""
        msg_usager = get_error_message("usager", "db_down", "")
        msg_pro = get_error_message("pro_tcl", "db_down", "")
        msg_elu = get_error_message("elu", "db_down", "")
        # Au moins 2 messages différents
        assert len({msg_usager, msg_pro, msg_elu}) >= 2

    def test_detail_pas_dans_message_final(self) -> None:
        """Le detail technique ne doit PAS apparaître dans le message usager."""
        msg = get_error_message("usager", "db_down", "[postgresql] Connection refused")
        assert "[postgresql]" not in msg
        assert "Connection refused" not in msg
