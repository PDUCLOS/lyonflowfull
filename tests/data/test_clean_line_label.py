"""Tests — ``clean_line_label`` (helper TCL).

 le suffixe horaire ``_hNN`` est désormais supprimé
(``"ActIV:Line::66:SYTRAL_h20"`` → ``"L66"`` et non plus ``"L66 ; 20h"``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.db_query import clean_line_label

# =============================================================================
# Format SIRI Lite brut (ActIV:Line::...:SYTRAL)
# =============================================================================


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Cas nominal sans bucket horaire
        ("ActIV:Line::66:SYTRAL", "L66"),
        ("ActIV:Line::4252:SYTRAL", "L4252"),
    # Avec bucket horaire — suffixe _hNN supprimé )
        ("ActIV:Line::4252:SYTRAL_h16", "L4252"),
        ("ActIV:Line::66:SYTRAL_h20", "L66"),
        # Ligne métro (suffixe alphabétique)
        ("ActIV:Line::M_A:SYTRAL", "LM_A"),
        # Ligne C3 (bus) en format ActIV
        ("ActIV:Line::C3:SYTRAL", "LC3"),
    ],
)
def test_clean_line_label_activ_format(raw: str, expected: str) -> None:
    """Le format ActIV:Line::<num>:SYTRAL[_h<bucket>] est normalisé."""
    assert clean_line_label(raw) == expected


# =============================================================================
# Identifiants déjà lisibles (T1, M_A, C3...) — pas de transformation
# =============================================================================


@pytest.mark.parametrize(
    "raw",
    [
        "T1",
        "T2",
        "TB11",
        "M_A",
        "M_B",
        "M_D",
        "C3",
        "C13",
        "B22",
    ],
)
def test_clean_line_label_already_readable(raw: str) -> None:
    """Un identifiant déjà lisible passe inchangé (idempotence)."""
    assert clean_line_label(raw) == raw


# =============================================================================
# Cas None / vide / whitespace
# =============================================================================


@pytest.mark.parametrize("raw", [None, "", "   ", "\t\n"])
def test_clean_line_label_empty_or_none(raw: str | None) -> None:
    """``None`` et chaîne vide renvoient le placeholder ``—``."""
    assert clean_line_label(raw) == "—"


# =============================================================================
# Whitespace en début/fin — strip avant traitement
# =============================================================================


def test_clean_line_label_strips_whitespace() -> None:
    """Les espaces autour du ``line_ref`` sont strippés avant parsing."""
    assert clean_line_label("  T1  ") == "T1"
    assert clean_line_label("  ActIV:Line::66:SYTRAL  ") == "L66"


# =============================================================================
# Type non-string
# =============================================================================


@pytest.mark.parametrize("raw", [123, 12.5, ["T1"], {"line": "T1"}, True])
def test_clean_line_label_non_string_returns_placeholder(raw: object) -> None:
    """Un type non-string renvoie ``—`` (pas de crash, pas de ValueError)."""
    assert clean_line_label(raw) == "—"  # type: ignore[arg-type]


# =============================================================================
# Format inconnu — pas de transformation (on garde tel quel)
# =============================================================================


@pytest.mark.parametrize(
    "raw",
    [
        "WEIRD_FORMAT",
        "ActIV:Line::",
        "ActIV:Line::66",
        "ActIV:Line::66:SYTRAL_extra",
        "random string",
    ],
)
def test_clean_line_label_unknown_format_passthrough(raw: str) -> None:
    """Un format inconnu n'est pas transformé — on renvoie tel quel.

    C'est un choix ``safe by default`` : plutôt que de risquer un crash
    sur un format exotique (ex. ajout d'un nouveau collecteur TCL), on
    affiche la chaîne brute. Le widget pourra l'identifier et la
    corriger au cas par cas.
    """
    assert clean_line_label(raw) == raw
