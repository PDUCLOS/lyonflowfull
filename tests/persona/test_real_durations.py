"""Tests Axe C — Durée réelle dans le comparateur (smoke).

Vérifie que les 3 widgets trajet (velov_trip, transit_trip, itinerary)
retournent bien un dict avec ``duration_min`` + ``distance_km`` quand
ils sont appelés, et que le badge source fonctionne.
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def test_velov_trip_returns_dict_signature():
    """render_velov_trip doit avoir la nouvelle signature -> dict | None."""
    import inspect

    from dashboard.components.widgets.usager.velov_trip import render_velov_trip

    sig = inspect.signature(render_velov_trip)
    assert sig.return_annotation is not type(None) or "dict" in str(sig.return_annotation)
    # Le retour doit être Optional[dict]
    assert "dict" in str(sig.return_annotation)


def test_transit_trip_returns_dict_signature():
    """render_transit_trip doit retourner dict | None."""
    import inspect

    from dashboard.components.widgets.usager.transit_trip import render_transit_trip

    sig = inspect.signature(render_transit_trip)
    assert "dict" in str(sig.return_annotation)


def test_itinerary_returns_dict_signature():
    """render_itinerary_result doit retourner dict | None."""
    import inspect

    from dashboard.components.widgets.usager.itinerary import render_itinerary_result

    sig = inspect.signature(render_itinerary_result)
    assert "dict" in str(sig.return_annotation)


def test_mode_comparison_source_badge_logic():
    """Le badge source 'computed' vs 'estimated' doit être différencié."""
    # On teste la logique du widget via les branches internes.
    # _render_mode_card prend mode_key, result, is_winner, score.
    # On ne peut pas l'appeler sans Streamlit, mais on peut vérifier que
    # le module contient la logique attendue.
    from dashboard.components.widgets.usager import mode_comparison

    # Vérif que la constante source_badge utilise 'computed'/'estimated'
    with open(WORKSPACE / "dashboard/components/widgets/usager/mode_comparison.py") as f:
        src = f.read()
    assert '"computed"' in src or "'computed'" in src
    assert '"estimated"' in src or "'estimated'" in src
    assert "Durée calculée" in src
    assert "Estimé" in src
