"""Tests pour la sparkline 24h (Sprint 21 P4.3)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Path setup
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import UTC

from dashboard.components.sparkline import render_sparkline

# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_render_sparkline_empty_values() -> None:
    """render_sparkline([]) doit retourner un graphe avec placeholder."""
    fig = render_sparkline(values=[])
    assert fig is not None
    # Doit contenir une annotation "Historique bientôt disponible"
    annotations = fig.layout.annotations
    assert len(annotations) == 1
    assert "Historique bientôt disponible" in annotations[0].text


def test_render_sparkline_trend_up() -> None:
    """Trend haussière → couleur verte."""
    values = [50.0, 55.0, 60.0, 65.0, 70.0]
    fig = render_sparkline(values=values, height=100)
    assert fig is not None
    trace = fig.data[0]
    assert trace.line.color == "#10B981"  # vert


def test_render_sparkline_trend_down() -> None:
    """Trend baissière → couleur rouge."""
    values = [70.0, 65.0, 60.0, 55.0, 50.0]
    fig = render_sparkline(values=values, height=100)
    trace = fig.data[0]
    assert trace.line.color == "#EF4444"  # rouge


def test_render_sparkline_trend_flat() -> None:
    """Trend stable → couleur grise."""
    values = [50.0, 50.0, 50.0, 50.0, 50.0]
    fig = render_sparkline(values=values)
    trace = fig.data[0]
    assert trace.line.color == "#94A3B8"  # gris


def test_render_sparkline_custom_color() -> None:
    """line_color custom doit être respecté."""
    values = [50.0, 60.0]
    fig = render_sparkline(values=values, line_color="#FF00FF")
    trace = fig.data[0]
    assert trace.line.color == "#FF00FF"


def test_render_sparkline_with_timestamps() -> None:
    """timestamps doit être utilisé pour l'axe x si fourni."""
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC)
    timestamps = [base + timedelta(minutes=15 * i) for i in range(5)]
    values = [50.0, 55.0, 60.0, 65.0, 70.0]
    fig = render_sparkline(values=values, timestamps=timestamps)
    assert fig.data[0].x[0] == timestamps[0]


def test_render_sparkline_height() -> None:
    """height doit être respecté."""
    fig = render_sparkline(values=[1.0, 2.0, 3.0], height=200)
    assert fig.layout.height == 200
