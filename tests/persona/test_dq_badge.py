"""Tests unitaires — widget data_quality_badge Axe B).

Couvre :
* _classify : 4 états selon (n_healthy, n_dead, n_stale, score).
  - n_dead > 0 → rouge ("Source en panne")
  - n_stale > 0 → orange ("X source(s) stale")
  - score >= 70 → vert ("Données OK")
  - sinon → gris (fallback)
* _global_score : wrapper identique à source_health_monitor._global_score.
  Testé ici pour cohérence inter-widgets.
"""

from __future__ import annotations

import pandas as pd
import pytest

from dashboard.components.widgets.elu.data_quality_badge import _classify, _global_score

# -----------------------------------------------------------------------------
# _classify
# -----------------------------------------------------------------------------


class TestClassify:
    """Détermine (couleur, icône, message) selon compteurs sources + score."""

    def test_n_dead_positive_retourne_rouge(self) -> None:
        """Au moins 1 source dead → rouge, message 'Source en panne'."""
        color, icon, msg = _classify(n_healthy=7, n_dead=1, n_stale=0, score=85.0)
        assert color == "#F44336"
        assert icon == "🔴"
        assert "Source en panne" in msg
        assert "1 morte" in msg
        assert "85" in msg

    def test_n_dead_priorite_sur_n_stale(self) -> None:
        """Si dead ET stale → dead prend priorité (rouge)."""
        color, icon, _ = _classify(n_healthy=6, n_dead=1, n_stale=2, score=80.0)
        assert color == "#F44336"
        assert icon == "🔴"

    def test_n_stale_positive_sans_dead_retourne_orange(self) -> None:
        """Stale sans dead → orange."""
        color, icon, msg = _classify(n_healthy=7, n_dead=0, n_stale=1, score=82.0)
        assert color == "#FF9800"
        assert icon == "🟡"
        assert "1 source(s) stale" in msg
        assert "82" in msg

    def test_score_70_et_plus_sans_dead_stale_retourne_vert(self) -> None:
        """Score >= 70, tout healthy → vert, 'Données OK'."""
        color, icon, msg = _classify(n_healthy=8, n_dead=0, n_stale=0, score=94.0)
        assert color == "#4CAF50"
        assert icon == "🟢"
        assert "Données OK" in msg
        assert "8 sources actives" in msg
        assert "94" in msg

    def test_score_sous_70_retourne_gris(self) -> None:
        """Score < 70, pas de dead/stale → gris (fallback)."""
        color, icon, msg = _classify(n_healthy=8, n_dead=0, n_stale=0, score=50.0)
        assert color == "#9E9E9E"
        assert icon == "⚪"
        assert "50" in msg

    def test_score_a_la_limite_70(self) -> None:
        """Score exactement 70 → vert (>= 70, pas strict)."""
        color, icon, _ = _classify(n_healthy=8, n_dead=0, n_stale=0, score=70.0)
        assert color == "#4CAF50"
        assert icon == "🟢"

    def test_n_stale_priorite_sur_score_bas(self) -> None:
        """Stale > 0 prend priorité même si score < 70 (orange, pas gris)."""
        color, icon, _ = _classify(n_healthy=7, n_dead=0, n_stale=1, score=50.0)
        assert color == "#FF9800"
        assert icon == "🟡"


# -----------------------------------------------------------------------------
# _global_score (wrapper)
# -----------------------------------------------------------------------------


class TestGlobalScoreWrapper:
    """Wrapper _global_score identique à source_health_monitor._global_score."""

    def test_df_vide_retourne_zero(self) -> None:
        assert _global_score(pd.DataFrame()) == 0.0

    def test_toutes_sources_a_100(self) -> None:
        df = pd.DataFrame(
            [
                ("bronze.trafic_boucles", 100.0),
                ("bronze.velov", 100.0),
            ],
            columns=["source", "health_score"],
        )
        assert _global_score(df) == 100.0

    def test_score_pondéré_cohérent_avec_autre_widget(self) -> None:
        """Doit retourner le même score que source_health_monitor._global_score."""
        from dashboard.components.widgets.pro_tcl.source_health_monitor import (
            _global_score as _other_global_score,
        )

        df = pd.DataFrame(
            [
                ("bronze.trafic_boucles", 80.0),  # poids 3
                ("bronze.tcl_vehicles", 60.0),  # poids 2
                ("bronze.velov", 40.0),  # poids 2
            ],
            columns=["source", "health_score"],
        )
        # Les 2 wrappers doivent retourner le même score
        assert _global_score(df) == _other_global_score(df)
