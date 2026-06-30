"""Tests Axe 7 (2026-06-20) — Météo impact helpers + widget.

Vérifie que le nouvel helper ``get_meteo_impact`` et le widget
``meteo_impact`` respectent la politique zéro mock de
* Helper bas-niveau (db_query) → DataFrame vide si DB indispo.
* Widget helpers (``_find_worst_band``, ``_format_delta_*``) → logique
  pure, testable hors-ligne.

Voir ``docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md`` (Axe 7, 2026-06-20)
pour le contexte fonctionnel, et ``docs/SPEC_SPRINT_17.md`` pour la
livraison"""

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


def test_get_meteo_impact_returns_empty_when_no_db() -> None:
    """get_meteo_impact (bas-niveau) : DataFrame vide si DB indispo."""
    df = db_query.get_meteo_impact()
    assert isinstance(df, pd.DataFrame)
    assert df.empty


# =============================================================================
# Widget helpers — logique pure, testable hors-ligne
# =============================================================================


def test_meteo_band_labels_has_5_bands() -> None:
    """Le référentiel METEO_BAND_LABELS doit couvrir les 5 bandes attendues."""
    from dashboard.components.widgets.pro_tcl.meteo_impact import (
        METEO_BAND_COLORS,
        METEO_BAND_LABELS,
    )

    expected = {"fair", "light_rain", "heavy_rain", "frost", "heatwave"}
    assert set(METEO_BAND_LABELS.keys()) == expected
    # Couleurs alignées sur les labels (cohérence design)
    assert set(METEO_BAND_COLORS.keys()) == expected


def test_format_delta_traffic_signs() -> None:
    """Format delta trafic : négatif avec '−', positif avec '+'."""
    from dashboard.components.widgets.pro_tcl.meteo_impact import (
        _format_delta_traffic,
    )

    assert _format_delta_traffic(-12.34) == "−12.3 km/h"
    assert _format_delta_traffic(5.5) == "+5.5 km/h"
    assert _format_delta_traffic(0.0) == "+0.0 km/h"
    assert _format_delta_traffic(float("nan")) == "—"
    assert _format_delta_traffic(None) == "—"  # type: ignore[arg-type]


def test_format_delta_tcl_signs() -> None:
    """Format delta TCL : positif avec '+', négatif avec '−'."""
    from dashboard.components.widgets.pro_tcl.meteo_impact import (
        _format_delta_tcl,
    )

    assert _format_delta_tcl(45.7) == "+46 s"
    assert _format_delta_tcl(-10.0) == "−10 s"
    assert _format_delta_tcl(0.0) == "+0 s"
    assert _format_delta_tcl(float("nan")) == "—"
    assert _format_delta_tcl(None) == "—"  # type: ignore[arg-type]


def test_format_delta_velov_signs() -> None:
    """Format delta Vélov : négatif avec '−' (moins de vélos = pire)."""
    from dashboard.components.widgets.pro_tcl.meteo_impact import (
        _format_delta_velov,
    )

    assert _format_delta_velov(-8.4) == "−8.4 vélos"
    assert _format_delta_velov(2.0) == "+2.0 vélos"
    assert _format_delta_velov(float("nan")) == "—"
    assert _format_delta_velov(None) == "—"  # type: ignore[arg-type]


def test_find_worst_band_traffic() -> None:
    """Pour le trafic : cherche le delta le plus négatif (plus de congestion)."""
    from dashboard.components.widgets.pro_tcl.meteo_impact import _find_worst_band

    df = pd.DataFrame(
        {
            "meteo_band": ["fair", "light_rain", "heavy_rain", "frost"],
            "traffic_delta_kmh_vs_fair": [0.0, -3.0, -12.0, -8.0],
        }
    )
    band, delta = _find_worst_band(df, "traffic_delta_kmh_vs_fair", "traffic")
    assert band == "heavy_rain"
    assert delta == -12.0


def test_find_worst_band_tcl() -> None:
    """Pour TCL : cherche le delta le plus positif (plus de retard)."""
    from dashboard.components.widgets.pro_tcl.meteo_impact import _find_worst_band

    df = pd.DataFrame(
        {
            "meteo_band": ["fair", "light_rain", "heavy_rain", "frost"],
            "tcl_delay_delta_sec_vs_fair": [0.0, 15.0, 45.0, 25.0],
        }
    )
    band, delta = _find_worst_band(df, "tcl_delay_delta_sec_vs_fair", "tcl")
    assert band == "heavy_rain"
    assert delta == 45.0


def test_find_worst_band_velov() -> None:
    """Pour Vélov : cherche le delta le plus négatif (moins de vélos)."""
    from dashboard.components.widgets.pro_tcl.meteo_impact import _find_worst_band

    df = pd.DataFrame(
        {
            "meteo_band": ["fair", "light_rain", "heavy_rain", "frost"],
            "velov_delta_bikes_vs_fair": [0.0, -4.0, -8.0, -12.0],
        }
    )
    band, delta = _find_worst_band(df, "velov_delta_bikes_vs_fair", "velov")
    assert band == "frost"
    assert delta == -12.0


def test_find_worst_band_empty_dataframe() -> None:
    """DataFrame vide : retourne (None, NaN)."""
    from dashboard.components.widgets.pro_tcl.meteo_impact import _find_worst_band

    band, delta = _find_worst_band(pd.DataFrame(), "traffic_delta_kmh_vs_fair", "traffic")
    assert band is None
    assert pd.isna(delta)


def test_find_worst_band_only_fair() -> None:
    """Si la seule ligne est 'fair' (baseline), pas de pire condition."""
    from dashboard.components.widgets.pro_tcl.meteo_impact import _find_worst_band

    df = pd.DataFrame(
        {
            "meteo_band": ["fair"],
            "traffic_delta_kmh_vs_fair": [0.0],
        }
    )
    band, delta = _find_worst_band(df, "traffic_delta_kmh_vs_fair", "traffic")
    assert band is None
    assert pd.isna(delta)


def test_find_worst_band_missing_column() -> None:
    """Colonne manquante : retourne (None, NaN) sans crash."""
    from dashboard.components.widgets.pro_tcl.meteo_impact import _find_worst_band

    df = pd.DataFrame(
        {
            "meteo_band": ["fair", "heavy_rain"],
            "other_col": [1, 2],
        }
    )
    band, delta = _find_worst_band(df, "traffic_delta_kmh_vs_fair", "traffic")
    assert band is None
    assert pd.isna(delta)


def test_render_kpi_banner_does_not_crash_on_empty() -> None:
    """_render_kpi_banner doit gérer un DataFrame vide (no data → 3 metrics '—')."""
    # Ne doit pas lever. Le rendu se fait dans Streamlit, mais la fonction
    # doit au moins être importable + appelable sur un DF vide.
    # On monkeypatch st.metric pour qu'il ne tape pas sur le rendu Streamlit.
    import streamlit as st

    from dashboard.components.widgets.pro_tcl.meteo_impact import (
        _render_kpi_banner,
    )

    calls: list[dict] = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        st,
        "metric",
        lambda label, value, delta=None, delta_color=None: calls.append(
            {"label": label, "value": value, "delta": delta}
        ),
    )
    try:
        _render_kpi_banner(pd.DataFrame())
    finally:
        monkey.undo()

    # 3 metrics : trafic, TCL, vélov
    assert len(calls) == 3
    labels = [c["label"] for c in calls]
    assert any("Trafic" in lab for lab in labels)
    assert any("TCL" in lab for lab in labels)
    assert any("Vélov" in lab for lab in labels)
