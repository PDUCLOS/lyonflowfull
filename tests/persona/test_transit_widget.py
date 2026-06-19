"""Tests Sprint 14/15+ — Widget transit_trip + segmented_control search_bar.

Couvre (sans mock — assertions sur le code source et la structure) :
- Widget `transit_trip.render_transit_trip` : import + présence fonctions
  internes + mentions disclaimer dans le source (3 tests)
- Segmented control `search_bar.render_search_bar` : contient 3 modes,
  default Transport en commun, retour `modes` en liste (3 tests)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


# =============================================================================
# 1. Widget transit_trip (3 tests — import + structure + disclaimer)
# =============================================================================


def test_transit_widget_module_importable():
    """Le module transit_trip.py doit s'importer sans erreur."""
    from dashboard.components.widgets.usager import transit_trip

    # La fonction principale doit exister
    assert hasattr(transit_trip, "render_transit_trip")
    assert callable(transit_trip.render_transit_trip)


def test_transit_widget_has_required_render_functions():
    """transit_trip.py expose les 4 fonctions de rendu attendues."""
    from dashboard.components.widgets.usager import transit_trip

    expected_functions = [
        "render_transit_trip",
        "_render_transit_banner",
        "_render_transit_kpis",
        "_render_transit_segments",
        "_render_transit_disclaimer",
    ]
    for fn_name in expected_functions:
        assert hasattr(transit_trip, fn_name), f"Fonction {fn_name} manquante"
        assert callable(getattr(transit_trip, fn_name))


def test_transit_widget_disclaimer_mentions_gtfs_phase1():
    """Le disclaimer doit mentionner GTFS (Phase 2) + Phase 1 (21 lieux, 1 corresp.).

    Lut directement dans le source pour ne pas dépendre du rendu Streamlit.
    """
    widget_path = (
        Path(__file__).resolve().parents[2]
        / "dashboard"
        / "components"
        / "widgets"
        / "usager"
        / "transit_trip.py"
    )
    source = widget_path.read_text(encoding="utf-8")

    assert "GTFS" in source, "Le disclaimer doit mentionner GTFS (données futures)"
    assert "Phase 1" in source, "Le disclaimer doit signaler les limites Phase 1"
    assert "21 lieux" in source, "Le disclaimer doit mentionner les 21 lieux"
    assert "1 correspondance" in source, "Le disclaimer doit mentionner la limite"


# =============================================================================
# 2. Multiselect search_bar (3 tests — contenu du source)
# =============================================================================


def test_search_bar_segmented_control_has_3_modes_no_marche():
    """Le segmented control affiche 3 options (TC, Vélov, Voiture), pas de Marche.

    Sprint 15+ : passage de ``st.multiselect`` à ``st.segmented_control``
    (boutons segmentés, 1 choix à la fois). On extrait l'appel du source pour
    ne pas matcher les éventuelles mentions "Marche" dans les commentaires.
    """
    search_bar_path = (
        Path(__file__).resolve().parents[2]
        / "dashboard"
        / "components"
        / "widgets"
        / "usager"
        / "search_bar.py"
    )
    source = search_bar_path.read_text(encoding="utf-8")

    # Extraire l'appel st.segmented_control(...) — bloc options=[...]
    m = re.search(r"st\.segmented_control\([^)]*options\s*=\s*\[([^\]]+)\]", source, re.DOTALL)
    assert m is not None, "Appel st.segmented_control(options=[...]) introuvable"
    segmented_content = m.group(1)

    # 3 modes présents dans la liste du segmented control
    assert '"🚌 Transport en commun"' in segmented_content
    assert '"🚲 Vélov"' in segmented_content
    assert '"🚗 Voiture"' in segmented_content

    # Marche ABSENT dans la liste
    assert "Marche" not in segmented_content, (
        "Mode Marche doit avoir été retiré de la liste (Sprint 14)"
    )


def test_search_bar_default_is_tc():
    """Default du segmented control = Transport en commun (Sprint 15+)."""
    search_bar_path = (
        Path(__file__).resolve().parents[2]
        / "dashboard"
        / "components"
        / "widgets"
        / "usager"
        / "search_bar.py"
    )
    source = search_bar_path.read_text(encoding="utf-8")

    # default doit être "🚌 Transport en commun"
    m = re.search(r"default\s*=\s*['\"]🚌\s*Transport en commun['\"]", source)
    assert m is not None, "Default du segmented control doit être '🚌 Transport en commun'"


def test_search_bar_returns_modes_in_dict():
    """render_search_bar retourne un dict avec la clé 'modes'."""
    # Test statique : la signature retourne un dict contenant 'modes'
    search_bar_path = (
        Path(__file__).resolve().parents[2]
        / "dashboard"
        / "components"
        / "widgets"
        / "usager"
        / "search_bar.py"
    )
    source = search_bar_path.read_text(encoding="utf-8")

    # Le return doit inclure 'modes'
    assert '"modes": modes' in source, "render_search_bar doit retourner modes"
