"""Tests unitaires — widget meteo_impact (Axe 7, Sprint 17 v0.9.0).

Couvre :
* Constantes METEO_BAND_LABELS / METEO_BAND_COLORS (5 bandes météo).
* _format_delta_traffic / _format_delta_tcl / _format_delta_velov : NaN,
  zéro, valeurs positives et négatives.
* _find_worst_band : df vide, df sans non-fair, et pire bande par mode
  (trafic = min delta, TCL = max delta, Vélov = min delta).
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from dashboard.components.widgets.pro_tcl.meteo_impact import (
    METEO_BAND_COLORS,
    METEO_BAND_LABELS,
    _find_worst_band,
    _format_delta_tcl,
    _format_delta_traffic,
    _format_delta_velov,
)

# -----------------------------------------------------------------------------
# Constantes : couverture des 5 bandes météo
# -----------------------------------------------------------------------------


class TestConstants:
    """Les constantes module-level couvrent les 5 bandes définies migration_022."""

    EXPECTED_BANDS = {"fair", "light_rain", "heavy_rain", "frost", "heatwave"}

    def test_labels_couvre_5_bandes(self) -> None:
        assert set(METEO_BAND_LABELS.keys()) == self.EXPECTED_BANDS

    def test_colors_couvre_5_bandes(self) -> None:
        assert set(METEO_BAND_COLORS.keys()) == self.EXPECTED_BANDS

    def test_labels_contient_emoji(self) -> None:
        """Les labels doivent inclure un emoji pour l'affichage visuel.

        Couvre à la fois le bloc U+2600 (Misc Symbols : ☀) et U+1F300+
        (Misc Symbols and Pictographs : 🌧, 🔥, etc.).
        """
        for label in METEO_BAND_LABELS.values():
            assert any(ord(c) >= 0x2600 for c in label), f"label sans emoji: {label}"

    def test_colors_sont_hex(self) -> None:
        """Les couleurs doivent être des codes hex valides (#RRGGBB)."""
        for color in METEO_BAND_COLORS.values():
            assert color.startswith("#") and len(color) == 7
            int(color[1:], 16)  # lève ValueError si pas hex


# -----------------------------------------------------------------------------
# _format_delta_traffic
# -----------------------------------------------------------------------------


class TestFormatDeltaTraffic:
    """Delta vitesse (km/h) — négatif = congestion vs fair."""

    def test_nan_retourne_tiret(self) -> None:
        assert _format_delta_traffic(float("nan")) == "—"

    def test_nan_pandas_na(self) -> None:
        """Couvre aussi pd.NA / NaT / numpy NaN (via pd.isna)."""
        assert _format_delta_traffic(pd.NA) == "—"

    def test_zero_affiche_plus(self) -> None:
        """Zéro = pas de congestion, signe +."""
        assert _format_delta_traffic(0.0) == "+0.0 km/h"

    def test_negatif_affiche_moins(self) -> None:
        """Négatif = congestion, signe − (U+2212, pas ASCII -)."""
        out = _format_delta_traffic(-5.5)
        assert "−" in out  # U+2212
        assert "5.5" in out
        assert "km/h" in out

    def test_positif_affiche_plus(self) -> None:
        out = _format_delta_traffic(3.2)
        assert out.startswith("+")
        assert "3.2" in out
        assert "km/h" in out


# -----------------------------------------------------------------------------
# _format_delta_tcl
# -----------------------------------------------------------------------------


class TestFormatDeltaTcl:
    """Delta retard TCL (s) — positif = plus de retard."""

    def test_nan_retourne_tiret(self) -> None:
        assert _format_delta_tcl(float("nan")) == "—"

    def test_zero_affiche_plus(self) -> None:
        assert _format_delta_tcl(0.0) == "+0 s"

    def test_positif_affiche_plus(self) -> None:
        out = _format_delta_tcl(45.0)
        assert out.startswith("+")
        assert "45" in out
        assert "s" in out

    def test_negatif_affiche_moins(self) -> None:
        """Négatif = moins de retard (rare mais possible)."""
        out = _format_delta_tcl(-10.0)
        assert "−" in out  # U+2212
        assert "10" in out


# -----------------------------------------------------------------------------
# _format_delta_velov
# -----------------------------------------------------------------------------


class TestFormatDeltaVelov:
    """Delta vélos dispos — négatif = moins de vélos."""

    def test_nan_retourne_tiret(self) -> None:
        assert _format_delta_velov(float("nan")) == "—"

    def test_zero_affiche_plus(self) -> None:
        assert _format_delta_velov(0.0) == "+0.0 vélos"

    def test_positif_affiche_plus(self) -> None:
        out = _format_delta_velov(2.5)
        assert out.startswith("+")
        assert "2.5" in out
        assert "vélos" in out

    def test_negatif_affiche_moins(self) -> None:
        out = _format_delta_velov(-4.0)
        assert "−" in out
        assert "4.0" in out


# -----------------------------------------------------------------------------
# _find_worst_band
# -----------------------------------------------------------------------------


def _make_meteo_df() -> pd.DataFrame:
    """DataFrame synthétique : 5 bandes, deltas variés par mode.

    Logique métier (cf. migration_022) :
    * Trafic : heavy_rain = pire (delta le plus négatif, congestion)
    * TCL : heavy_rain = pire (delta le plus positif, retard++)
    * Vélov : heavy_rain = pire (delta le plus négatif, moins de vélos)
    """
    return pd.DataFrame(
        [
            # band, traffic_delta, tcl_delta, velov_delta
            {"meteo_band": "fair", "traffic_delta_kmh_vs_fair": 0.0, "tcl_delay_delta_sec_vs_fair": 0.0, "velov_delta_bikes_vs_fair": 0.0},
            {"meteo_band": "light_rain", "traffic_delta_kmh_vs_fair": -2.0, "tcl_delay_delta_sec_vs_fair": 15.0, "velov_delta_bikes_vs_fair": -1.5},
            {"meteo_band": "heavy_rain", "traffic_delta_kmh_vs_fair": -8.0, "tcl_delay_delta_sec_vs_fair": 60.0, "velov_delta_bikes_vs_fair": -6.0},
            {"meteo_band": "frost", "traffic_delta_kmh_vs_fair": -3.0, "tcl_delay_delta_sec_vs_fair": 25.0, "velov_delta_bikes_vs_fair": -2.0},
            {"meteo_band": "heatwave", "traffic_delta_kmh_vs_fair": 1.0, "tcl_delay_delta_sec_vs_fair": 5.0, "velov_delta_bikes_vs_fair": -0.5},
        ]
    )


class TestFindWorstBand:
    """Trouve la bande (hors fair) avec le delta le plus impactant par mode."""

    def test_df_vide_retourne_none(self) -> None:
        band, delta = _find_worst_band(pd.DataFrame(), "traffic_delta_kmh_vs_fair", "traffic")
        assert band is None
        assert math.isnan(delta)

    def test_colonne_manquante_retourne_none(self) -> None:
        df = _make_meteo_df().drop(columns=["traffic_delta_kmh_vs_fair"])
        band, delta = _find_worst_band(df, "traffic_delta_kmh_vs_fair", "traffic")
        assert band is None
        assert math.isnan(delta)

    def test_que_du_fair_retourne_none(self) -> None:
        df = pd.DataFrame([{"meteo_band": "fair", "traffic_delta_kmh_vs_fair": 0.0}])
        band, delta = _find_worst_band(df, "traffic_delta_kmh_vs_fair", "traffic")
        assert band is None
        assert math.isnan(delta)

    def test_traffic_pire_est_min_delta(self) -> None:
        """Trafic : on cherche le delta le plus négatif (= plus de congestion)."""
        band, delta = _find_worst_band(_make_meteo_df(), "traffic_delta_kmh_vs_fair", "traffic")
        assert band == "heavy_rain"
        assert delta == pytest.approx(-8.0)

    def test_tcl_pire_est_max_delta(self) -> None:
        """TCL : on cherche le delta le plus positif (= plus de retard)."""
        band, delta = _find_worst_band(_make_meteo_df(), "tcl_delay_delta_sec_vs_fair", "tcl")
        assert band == "heavy_rain"
        assert delta == pytest.approx(60.0)

    def test_velov_pire_est_min_delta(self) -> None:
        """Vélov : on cherche le delta le plus négatif (= moins de vélos)."""
        band, delta = _find_worst_band(_make_meteo_df(), "velov_delta_bikes_vs_fair", "velov")
        assert band == "heavy_rain"
        assert delta == pytest.approx(-6.0)
