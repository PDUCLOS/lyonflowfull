"""Tests unitaires — widget source_health_monitor Axe B).

Couvre :
* Constante SOURCE_WEIGHTS : 8 sources (trafic_boucles=3, gold.trafic_predictions=2,
  TCL=2, vélov=2, reste=1).
* _global_score : DataFrame vide → 0, sources connues → score pondéré correct,
  source inconnue → poids par défaut 1.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dashboard.components.widgets.pro_tcl.source_health_monitor import (
    SOURCE_WEIGHTS,
    STATUS_COLORS,
    _global_score,
)

# -----------------------------------------------------------------------------
# Constantes
# -----------------------------------------------------------------------------


class TestSourceWeights:
    """Poids par source pour le score global pondéré 0-100."""

    EXPECTED_SOURCES = {
        "bronze.trafic_boucles",
        "bronze.tcl_vehicles",
        "bronze.velov",
        "bronze.meteo",
        "bronze.air_quality",
        "bronze.chantiers",
        "bronze.tomtom_traffic",
        "gold.trafic_predictions",
    }

    def test_couvre_8_sources(self) -> None:
        """8 sources (7 Bronze + 1 Gold)."""
        assert set(SOURCE_WEIGHTS.keys()) == self.EXPECTED_SOURCES
        assert len(SOURCE_WEIGHTS) == 8

    def test_trafic_boucles_a_le_poids_max(self) -> None:
        """Trafic routier = source principale, poids 3."""
        assert SOURCE_WEIGHTS["bronze.trafic_boucles"] == 3

    def test_tcl_et_velov_poids_2(self) -> None:
        """TCL et Vélov = sources importantes, poids 2."""
        assert SOURCE_WEIGHTS["bronze.tcl_vehicles"] == 2
        assert SOURCE_WEIGHTS["bronze.velov"] == 2
        assert SOURCE_WEIGHTS["gold.trafic_predictions"] == 2

    def test_sources_secondaires_poids_1(self) -> None:
        """Météo, air_quality, chantiers, tomtom = sources secondaires, poids 1."""
        assert SOURCE_WEIGHTS["bronze.meteo"] == 1
        assert SOURCE_WEIGHTS["bronze.air_quality"] == 1
        assert SOURCE_WEIGHTS["bronze.chantiers"] == 1
        assert SOURCE_WEIGHTS["bronze.tomtom_traffic"] == 1

    def test_tous_poids_positifs(self) -> None:
        for source, weight in SOURCE_WEIGHTS.items():
            assert weight > 0, f"poids négatif ou nul pour {source}"


class TestStatusColors:
    """Couleurs hex par statut source."""

    EXPECTED_STATUSES = {"healthy", "delayed", "stale", "dead"}

    def test_couvre_4_statuts(self) -> None:
        assert set(STATUS_COLORS.keys()) == self.EXPECTED_STATUSES

    def test_toutes_couleurs_hex(self) -> None:
        for _status, color in STATUS_COLORS.items():
            assert color.startswith("#") and len(color) == 7
            int(color[1:], 16)  # lève ValueError si pas hex valide


# -----------------------------------------------------------------------------
# _global_score
# -----------------------------------------------------------------------------


def _make_health_df(rows: list[tuple[str, float]]) -> pd.DataFrame:
    """Helper : DataFrame minimal (source, health_score)."""
    return pd.DataFrame(rows, columns=["source", "health_score"])


class TestGlobalScore:
    """Calcule le score global pondéré 0-100."""

    def test_df_vide_retourne_zero(self) -> None:
        """DataFrame vide → score = 0.0."""
        assert _global_score(pd.DataFrame()) == 0.0

    def test_score_parfait_toutes_sources_a_100(self) -> None:
        """Toutes sources à 100 → score = 100.0."""
        df = _make_health_df(
            [
                ("bronze.trafic_boucles", 100.0),
                ("bronze.tcl_vehicles", 100.0),
                ("bronze.velov", 100.0),
            ]
        )
        assert _global_score(df) == 100.0

    def test_score_zero_toutes_sources_a_zero(self) -> None:
        """Toutes sources à 0 → score = 0.0."""
        df = _make_health_df(
            [
                ("bronze.trafic_boucles", 0.0),
                ("bronze.tcl_vehicles", 0.0),
            ]
        )
        assert _global_score(df) == 0.0

    def test_pondération_trafic_plus_fort(self) -> None:
        """Trafic (poids 3) influence plus le score que vélov (poids 2)."""
        # Trafic à 100, vélov à 0
        # Score = (100*3 + 0*2) / (3+2) = 60
        df = _make_health_df(
            [
                ("bronze.trafic_boucles", 100.0),
                ("bronze.velov", 0.0),
            ]
        )
        assert _global_score(df) == pytest.approx(60.0, abs=0.1)

    def test_source_inconnue_poids_1(self) -> None:
        """Source hors SOURCE_WEIGHTS → poids par défaut 1."""
        # traf_pred 100 (poids 3) + inconnue 0 (poids 1) + inconnue 100 (poids 1)
        # = (100*3 + 0*1 + 100*1) / (3+1+1) = 400/5 = 80
        df = _make_health_df(
            [
                ("bronze.trafic_boucles", 100.0),
                ("unknown.source", 0.0),
                ("other.unknown", 100.0),
            ]
        )
        assert _global_score(df) == pytest.approx(80.0, abs=0.1)

    def test_score_arrondi_1_decimale(self) -> None:
        """Le score est arrondi à 1 décimale."""
        # 33.33 * 3 + 66.67 * 2 = 100 + 133.33 = 233.33 / 5 = 46.666 → 46.7
        df = _make_health_df(
            [
                ("bronze.trafic_boucles", 33.33),
                ("bronze.velov", 66.67),
            ]
        )
        score = _global_score(df)
        # Vérifier l'arrondi (1 décimale max)
        assert round(score, 1) == score
