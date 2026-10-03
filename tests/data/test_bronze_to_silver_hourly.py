"""Tests — météo / qualité de l'air horaires : la collecte la plus récente gagne."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

NEWER = datetime(2026, 10, 3, 16, 15, tzinfo=UTC)
OLDER = datetime(2026, 10, 3, 4, 15, tzinfo=UTC)


def _fake_connection(rows: list[tuple]):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows

    @contextmanager
    def _raw_connection():
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        yield conn

    return _raw_connection


def _meteo_payload(temp: float) -> dict:
    return {
        "hourly": {
            "time": ["2026-10-03T18:00", "2026-10-03T19:00"],
            "temperature_2m": [temp, temp + 1],
            "relative_humidity_2m": [70, 71],
            "precipitation": [0.0, 0.1],
            "wind_speed_10m": [6.5, 7.0],
            "weather_code": [3, 61],
        }
    }


def test_transform_meteo_keeps_most_recent_fetch_per_hour():
    """Bronze trié du plus récent au plus ancien : une seule ligne par heure, celle de la collecte la plus récente."""
    from src.transformation import bronze_to_silver

    rows = [(2, NEWER, _meteo_payload(15.0)), (1, OLDER, _meteo_payload(9.0))]
    with (
        patch.object(bronze_to_silver, "raw_connection", _fake_connection(rows)),
        patch.object(bronze_to_silver.psycopg2.extras, "execute_batch") as mock_batch,
    ):
        n = bronze_to_silver._transform_meteo()

    batch = mock_batch.call_args.args[2]
    assert n == 2
    assert [b[0] for b in batch] == ["2026-10-03T18:00", "2026-10-03T19:00"]
    assert [b[1] for b in batch] == [15.0, 16.0]
    assert all(b[6] == NEWER for b in batch)
    sql = mock_batch.call_args.args[1]
    assert "EXCLUDED.fetched_at >= silver.meteo_hourly.fetched_at" in sql
    # Heures Open-Meteo locales (Europe/Paris) converties en UTC à l'insertion
    assert "VALUES ((%s::timestamp AT TIME ZONE 'Europe/Paris')" in sql


def test_transform_air_quality_keeps_most_recent_fetch_per_hour():
    """Même règle pour silver.air_quality_clean, avec le fetched_at de la collecte (plus NOW())."""
    from src.transformation import bronze_to_silver

    def _payload(aqi: int) -> dict:
        return {"hourly": {"time": ["2026-10-03T18:00"], "european_aqi": [aqi]}}

    rows = [(2, NEWER, _payload(30)), (1, OLDER, _payload(80))]
    with (
        patch.object(bronze_to_silver, "raw_connection", _fake_connection(rows)),
        patch.object(bronze_to_silver.psycopg2.extras, "execute_batch") as mock_batch,
    ):
        n = bronze_to_silver._transform_air_quality()

    batch = mock_batch.call_args.args[2]
    assert n == 1
    assert batch[0][1] == 30
    assert batch[0][-1] == NEWER
    assert "NOW()" not in mock_batch.call_args.args[1]
    assert "VALUES ((%s::timestamp AT TIME ZONE 'Europe/Paris')" in mock_batch.call_args.args[1]


def test_silver_to_gold_uses_current_hour_weather_not_forecast():
    """latest_meteo : la dernière ligne de meteo_hourly est une prévision J+1 → borner à NOW()."""
    from src.transformation import silver_to_gold

    for sql in (silver_to_gold._TRAFFIC_SQL, silver_to_gold._VELOV_SQL):
        cte = sql.split("latest_meteo AS (", 1)[1].split("),", 1)[0]
        assert "WHERE measurement_time <= NOW()" in cte
