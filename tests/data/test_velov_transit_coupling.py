"""Tests Axe 4 (2026-06-20) — Vélov ↔ TC coupling helpers + widget.

Vérifie que les nouveaux helpers ``get_velov_transit_coupling``,
``get_velov_transit_coupling_summary`` et le widget ``modal_shift_alert``
respectent la politique zéro mock de 
* Helpers bas-niveau (db_query) → DataFrame vide si DB indispo.
* Widget helpers (``_count_anomalies``, ``_count_critical_lines``,
  ``_format_z_score``) → logique pure, testable hors-ligne.

Voir ``docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md`` (Axe 4, 2026-06-20)
pour le contexte fonctionnel, et ``docs/SPEC_SPRINT_17.md`` pour la
livraison """

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data import data_loader, db_query


@pytest.fixture(autouse=True)
def disable_db(monkeypatch):
    """Force ``_is_db_available = False`` pour ces tests (pas de DB locale).

    Patch dans DEUX modules (db_query + data_loader) — voir
    tests/data/test_db_query_and_data_loader.py pour l'explication
    (data_loader importe ``_is_db_available`` via ``from ... import``).
    """
    monkeypatch.setattr(db_query, "_is_db_available", lambda: False)
    monkeypatch.setattr(data_loader, "_is_db_available", lambda: False)
    db_query.reset_db_cache()
    yield
    db_query.reset_db_cache()


# =============================================================================
# Helpers db_query — DataFrame vide si DB indispo
# =============================================================================


def test_get_velov_transit_coupling_returns_empty_when_no_db() -> None:
    """get_velov_transit_coupling (bas-niveau) : DataFrame vide si DB indispo."""
    df = db_query.get_velov_transit_coupling()
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_get_velov_transit_coupling_anomalies_only_returns_empty_when_no_db() -> None:
    """get_velov_transit_coupling(anomalies_only=True) : vide aussi."""
    df = db_query.get_velov_transit_coupling(anomalies_only=True)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_get_velov_transit_coupling_summary_returns_empty_when_no_db() -> None:
    """get_velov_transit_coupling_summary : DataFrame vide si DB indispo."""
    df = db_query.get_velov_transit_coupling_summary()
    assert isinstance(df, pd.DataFrame)
    assert df.empty


# =============================================================================
# Widget helpers — logique pure, testable hors-ligne
# =============================================================================


def test_format_z_score_thresholds() -> None:
    """Format z-score : rouge si < -2, jaune si < 0, vert sinon."""
    from dashboard.components.widgets.pro_tcl.modal_shift_alert import (
        _format_z_score,
    )

    # < -2 (alarme) : rouge
    assert _format_z_score(-3.5).startswith("🔴")
    assert _format_z_score(-2.5).startswith("🔴")
    # < 0 (sous baseline, mais pas alarme) : jaune
    assert _format_z_score(-1.0).startswith("🟡")
    assert _format_z_score(-0.01).startswith("🟡")
    # >= 0 (au-dessus baseline) : vert
    assert _format_z_score(0.0).startswith("🟢")
    assert _format_z_score(2.5).startswith("🟢")
    # None / NaN : —
    assert _format_z_score(None) == "—"  # type: ignore[arg-type]
    assert _format_z_score(float("nan")) == "—"


def test_count_anomalies_empty_dataframe() -> None:
    """_count_anomalies : 0 si DataFrame vide."""
    from dashboard.components.widgets.pro_tcl.modal_shift_alert import (
        _count_anomalies,
    )

    assert _count_anomalies(pd.DataFrame()) == 0
    # DataFrame sans la colonne → 0
    assert _count_anomalies(pd.DataFrame({"other": [1, 2, 3]})) == 0


def test_count_anomalies_with_data() -> None:
    """_count_anomalies : compte les TRUE dans la colonne anomaly_detected."""
    from dashboard.components.widgets.pro_tcl.modal_shift_alert import (
        _count_anomalies,
    )

    df = pd.DataFrame(
        {
            "anomaly_detected": [True, True, False, True, False],
        }
    )
    assert _count_anomalies(df) == 3


def test_count_critical_lines_empty() -> None:
    """_count_critical_lines : (0, 0) si DataFrame vide."""
    from dashboard.components.widgets.pro_tcl.modal_shift_alert import (
        _count_critical_lines,
    )

    n_crit, n_warn = _count_critical_lines(pd.DataFrame())
    assert n_crit == 0
    assert n_warn == 0

    # DataFrame sans la colonne alert_level
    n_crit, n_warn = _count_critical_lines(pd.DataFrame({"other": [1, 2]}))
    assert n_crit == 0
    assert n_warn == 0


def test_count_critical_lines_with_data() -> None:
    """_count_critical_lines : compte les critical et warning."""
    from dashboard.components.widgets.pro_tcl.modal_shift_alert import (
        _count_critical_lines,
    )

    df = pd.DataFrame(
        {
            "alert_level": ["critical", "critical", "warning", "ok", "warning"],
        }
    )
    n_crit, n_warn = _count_critical_lines(df)
    assert n_crit == 2
    assert n_warn == 2


def test_alert_level_labels_has_3_levels() -> None:
    """ALERT_LEVEL_LABELS doit couvrir les 3 niveaux attendus."""
    from dashboard.components.widgets.pro_tcl.modal_shift_alert import (
        ALERT_LEVEL_COLORS,
        ALERT_LEVEL_LABELS,
    )

    expected = {"critical", "warning", "ok"}
    assert set(ALERT_LEVEL_LABELS.keys()) == expected
    # Couleurs alignées sur les labels (cohérence design)
    assert set(ALERT_LEVEL_COLORS.keys()) == expected


def test_render_kpi_banner_does_not_crash_on_empty() -> None:
    """_render_kpi_banner doit gérer un DataFrame vide (0 partout)."""
    # On monkeypatch st.metric pour qu'il ne tape pas sur le rendu Streamlit.
    import streamlit as st

    from dashboard.components.widgets.pro_tcl.modal_shift_alert import (
        _render_kpi_banner,
    )

    calls: list[dict] = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        st, "metric", lambda label, value, **kwargs: calls.append({"label": label, "value": value, **kwargs})
    )
    try:
        _render_kpi_banner(pd.DataFrame(), pd.DataFrame())
    finally:
        monkey.undo()

    # 4 metrics : stations, critical, warning, coverage
    assert len(calls) == 4
    labels = [c["label"] for c in calls]
    assert any("Stations" in lab for lab in labels)
    assert any("critiques" in lab for lab in labels)
    assert any("vigilance" in lab for lab in labels)
    assert any("Couverture" in lab for lab in labels)
    # Tout à 0
    assert all(c["value"] == 0 for c in calls[:3])
