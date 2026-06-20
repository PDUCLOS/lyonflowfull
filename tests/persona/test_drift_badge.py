"""Tests Sprint 16 Axe A — Drift status badge widget (smoke + states).

Vérifie que le widget drift_status_badge s'importe et que sa logique de
classification (couleur / icône / message) fonctionne pour les 4 états
possibles.
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))

from dashboard.components.widgets.elu import drift_status_badge


def test_drift_badge_module_importable():
    """Le module drift_status_badge doit s'importer et exposer render_drift_status_badge."""
    assert callable(drift_status_badge.render_drift_status_badge)


def test_drift_badge_exported_from_elu():
    """render_drift_status_badge doit être exporté par le package elu."""
    from dashboard.components.widgets.elu import render_drift_status_badge

    assert callable(render_drift_status_badge)


def test_drift_badge_classify_green_no_drift():
    """MAE < green + drift = 0 → vert, message 'Modèle stable'."""
    color, icon, msg = drift_status_badge._classify(mae_kmh=5.0, drift_share=0.0)
    assert color == "#4CAF50"
    assert icon == "🟢"
    assert "stable" in msg.lower()


def test_drift_badge_classify_green_with_drift():
    """MAE < green mais drift > 0 → orange (warning)."""
    color, icon, msg = drift_status_badge._classify(mae_kmh=5.0, drift_share=0.5)
    assert color == "#FF9800"
    assert icon == "🟡"


def test_drift_badge_classify_yellow():
    """MAE entre green et yellow → orange + 'Attention'."""
    color, icon, msg = drift_status_badge._classify(mae_kmh=10.0, drift_share=None)
    assert color == "#FF9800"
    assert icon == "🟡"
    assert "attention" in msg.lower()


def test_drift_badge_classify_red():
    """MAE >= yellow → rouge + 'Drift détecté'."""
    color, icon, msg = drift_status_badge._classify(mae_kmh=20.0, drift_share=0.8)
    assert color == "#F44336"
    assert icon == "🔴"
    assert "drift" in msg.lower()


def test_drift_badge_classify_no_mae():
    """mae_kmh=None → gris, message 'indisponibles'."""
    color, icon, msg = drift_status_badge._classify(mae_kmh=None, drift_share=None)
    assert color == "#9E9E9E"
    assert "indisponibles" in msg.lower()


def test_drift_badge_thresholds_consistent():
    """Seuils MAE_GREEN < MAE_YELLOW (cohérence)."""
    assert drift_status_badge.MAE_GREEN < drift_status_badge.MAE_YELLOW
    assert drift_status_badge.MAE_GREEN > 0
    assert drift_status_badge.MAE_YELLOW > drift_status_badge.MAE_GREEN
