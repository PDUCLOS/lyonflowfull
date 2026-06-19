"""Tests Sprint 15+ (2026-06-19) — Helpers db_query + data_loader grille multimodale.

Vérifie que les nouveaux helpers ``get_multimodal_grid``,
``get_multimodal_grid_diagnosis_counts`` et leurs wrappers ``load_*``
respectent la politique zéro mock de Sprint 8 :

* Helpers bas-niveau (db_query) → DataFrame vide si DB indispo.
* Wrappers data_loader → lèvent ``DashboardDataError`` si DB indispo ou
  si la MV est vide (cas pathologique = DAG refresh pas passé).

Voir ``docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md`` (Axe 1, 2026-06-19)
pour le contexte fonctionnel.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data import data_loader, db_query
from src.data.exceptions import DashboardDataError


@pytest.fixture(autouse=True)
def disable_db(monkeypatch):
    """Force ``_is_db_available = False`` pour ces tests (pas de DB locale)."""
    monkeypatch.setattr(db_query, "_is_db_available", lambda: False)
    db_query.reset_db_cache()
    yield
    db_query.reset_db_cache()


# =============================================================================
# Helpers data_loader — fail loud quand DB indispo
# =============================================================================


def test_load_multimodal_grid_raises_when_no_db() -> None:
    """load_multimodal_grid doit lever DashboardDataError si DB indispo."""
    with pytest.raises(DashboardDataError):
        data_loader.load_multimodal_grid()


def test_load_multimodal_grid_diagnosis_counts_raises_when_no_db() -> None:
    """load_multimodal_grid_diagnosis_counts doit lever si DB indispo."""
    with pytest.raises(DashboardDataError):
        data_loader.load_multimodal_grid_diagnosis_counts()


# =============================================================================
# Helpers db_query — DataFrame vide si DB indispo
# =============================================================================


def test_get_multimodal_grid_returns_empty_when_no_db() -> None:
    """get_multimodal_grid (bas-niveau) : DataFrame vide si DB indispo."""
    df = db_query.get_multimodal_grid(limit=10)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_get_multimodal_grid_diagnosis_counts_returns_empty_when_no_db() -> None:
    """get_multimodal_grid_diagnosis_counts (bas-niveau) : DF vide si DB indispo."""
    df = db_query.get_multimodal_grid_diagnosis_counts()
    assert isinstance(df, pd.DataFrame)
    assert df.empty


# =============================================================================
# Cohérence des seuils de score (helper privé du widget)
# =============================================================================


def test_score_to_color_thresholds() -> None:
    """Vérifie la fonction _score_to_color du widget (seuils spec section 2.4).

    Score >= 7 → saturated (rouge)
    Score 4-7 → tendu (orange)
    Score < 4 → ok (vert)
    """
    from dashboard.components.widgets.pro_tcl.multimodal_heatmap import (
        DIAGNOSIS_COLORS,
        SCORE_THRESHOLDS,
        _score_to_color,
    )

    # Au-dessus du seuil saturé (>= 7 = saturé)
    assert _score_to_color(SCORE_THRESHOLDS["saturated"]) == DIAGNOSIS_COLORS["saturated"]
    assert _score_to_color(SCORE_THRESHOLDS["saturated"] + 1) == DIAGNOSIS_COLORS["saturated"]

    # Entre seuil saturé et seuil tendu
    mid = (SCORE_THRESHOLDS["saturated"] + SCORE_THRESHOLDS["tendu"]) / 2
    assert _score_to_color(mid) == DIAGNOSIS_COLORS["road_congested"]

    # À la frontière tendu (>= 4 = tendu, donc 4.0 → orange, 3.99 → vert)
    assert _score_to_color(SCORE_THRESHOLDS["tendu"]) == DIAGNOSIS_COLORS["road_congested"]
    assert _score_to_color(SCORE_THRESHOLDS["tendu"] - 0.01) == DIAGNOSIS_COLORS["ok"]
    assert _score_to_color(0.0) == DIAGNOSIS_COLORS["ok"]

    # NaN → gris (no data)
    assert _score_to_color(float("nan")) == "#9E9E9E"


def test_score_to_color_handles_none() -> None:
    """Score None / NaN doit retourner gris (couleur no-data cohérente)."""
    from dashboard.components.widgets.pro_tcl.multimodal_heatmap import (
        _score_to_color,
    )

    assert _score_to_color(None) == "#9E9E9E"  # type: ignore[arg-type]
    assert _score_to_color(float("nan")) == "#9E9E9E"


def test_diagnosis_counts_initializes_all_keys() -> None:
    """_diagnosis_counts doit renvoyer un dict avec les 5 diagnostics, défaut 0."""
    from dashboard.components.widgets.pro_tcl.multimodal_heatmap import (
        DIAGNOSIS_LABELS,
        _diagnosis_counts,
    )

    # DataFrame vide → tout à 0
    counts = _diagnosis_counts(pd.DataFrame())
    assert set(counts.keys()) == set(DIAGNOSIS_LABELS.keys())
    assert all(v == 0 for v in counts.values())

    # DataFrame avec un seul diagnostic
    df = pd.DataFrame({"diagnosis": ["saturated", "saturated", "ok"]})
    counts = _diagnosis_counts(df)
    assert counts["saturated"] == 2
    assert counts["ok"] == 1
    assert counts["road_congested"] == 0
