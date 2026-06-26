"""Tests unitaires — dashboard/components/freshness_badge.py Axe F).

Couvre :
* REFRESH_INTERVALS_SEC : 3 personas avec les bons intervalles ).
* seconds_until_next_refresh : calcul correct du temps restant, fallback
  sur 0 pour persona inconnu/None.
"""

from __future__ import annotations

import pytest

from dashboard.components.freshness_badge import (
    REFRESH_INTERVALS_SEC,
    seconds_until_next_refresh,
)


class TestRefreshIntervals:
    """Intervalles d'auto-refresh par persona (+)."""

    def test_trois_personas(self) -> None:
        assert set(REFRESH_INTERVALS_SEC.keys()) == {"usager", "pro_tcl", "elu"}

    def test_pro_tcl_30s(self) -> None:
        """Pro TCL : 30s (rapide, l'analyste surveille en temps réel)."""
        assert REFRESH_INTERVALS_SEC["pro_tcl"] == 30

    def test_usager_60s(self) -> None:
        """Usager : 60s (équilibre réactivité/charge)."""
        assert REFRESH_INTERVALS_SEC["usager"] == 60

    def test_elu_300s(self) -> None:
        """Élu : 300s = 5min (synthèse, pas besoin de temps réel)."""
        assert REFRESH_INTERVALS_SEC["elu"] == 300


class TestSecondsUntilNextRefresh:
    """Calcul du temps restant avant la prochaine MAJ."""

    @pytest.mark.parametrize(
        "persona,expected_max",
        [
            ("usager", 60),
            ("pro_tcl", 30),
            ("elu", 300),
        ],
    )
    def test_entre_0_et_interval(self, persona: str, expected_max: int) -> None:
        """Le temps restant est toujours entre 0 et l'intervalle (inclus)."""
        s = seconds_until_next_refresh(persona)
        assert 0 <= s <= expected_max

    def test_persona_inconnu_retourne_0(self) -> None:
        assert seconds_until_next_refresh("unknown_persona") == 0

    def test_persona_none_retourne_0(self) -> None:
        assert seconds_until_next_refresh(None) == 0

    def test_changement_entre_appels(self) -> None:
        """Le temps restant peut varier entre 2 appels (time.time() avance)."""
        import time

        s1 = seconds_until_next_refresh("usager")
        time.sleep(0.01)
        s2 = seconds_until_next_refresh("usager")
        # s2 <= s1 (le temps a avancé) ou s2 = s1 (même seconde)
        assert s2 <= s1
