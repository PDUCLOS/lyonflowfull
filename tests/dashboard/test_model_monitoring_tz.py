"""Tests — conversion UTC du panneau Data Quality (page Model Monitoring)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pandas as pd


def test_as_utc_accepts_naive_and_aware_timestamps():
    """timestamptz (avec fuseau) faisait planter pd.Timestamp(x, tz='UTC')."""
    from dashboard.components.widgets.pro_tcl.model_monitoring import _as_utc

    paris = timezone(timedelta(hours=2))
    aware = datetime(2026, 10, 3, 18, 0, tzinfo=paris)
    naive = datetime(2026, 10, 3, 16, 0)

    assert _as_utc(aware) == pd.Timestamp("2026-10-03 16:00", tz="UTC")
    assert _as_utc(naive) == pd.Timestamp("2026-10-03 16:00", tz="UTC")
    assert _as_utc(datetime(2026, 10, 3, 16, 0, tzinfo=UTC)).tzinfo is not None
