"""Tests — requêtes SQL des health checks Bronze / Silver."""

from __future__ import annotations

from unittest.mock import patch


def test_check_bronze_volume_compares_timestamps_not_interval():
    """meteo: `fetched_at > NOW() - INTERVAL` (timestamptz > interval n'existe pas en SQL)."""
    from src.monitoring.health_checks import check_bronze_volume

    with patch(
        "src.monitoring.health_checks.execute_query",
        return_value=[{"trafic": 12, "velov": 12, "tcl": 11, "meteo": 288}],
    ) as mock_query:
        result = check_bronze_volume()

    sql = mock_query.call_args.args[0]
    assert "fetched_at > INTERVAL" not in sql
    assert "fetched_at > NOW() - INTERVAL '1 day'" in sql
    assert result.status == "ok"


def test_check_silver_nulls_uses_existing_geom_column():
    """silver.trafic_boucles_clean a `geom` (pas `geom_wgs84`)."""
    from src.monitoring.health_checks import check_silver_nulls

    with patch(
        "src.monitoring.health_checks.execute_query",
        return_value=[{"vitesse_null_pct": 1.0, "geom_null_pct": 0.0}],
    ) as mock_query:
        result = check_silver_nulls()

    sql = mock_query.call_args.args[0]
    assert "geom_wgs84" not in sql
    assert "geom IS NULL" in sql
    assert "speed_channels" in sql
    assert result.status == "ok"


def test_check_bronze_volume_flags_degraded_source():
    """Une source à moins de 6 appels/h = warning, une source à 0 = critical."""
    from src.monitoring.health_checks import check_bronze_volume

    with patch(
        "src.monitoring.health_checks.execute_query",
        return_value=[{"trafic": 12, "velov": 3, "tcl": 12, "meteo": 288}],
    ):
        assert check_bronze_volume().status == "warning"
    with patch(
        "src.monitoring.health_checks.execute_query",
        return_value=[{"trafic": 12, "velov": 12, "tcl": 0, "meteo": 288}],
    ):
        assert check_bronze_volume().status == "critical"
