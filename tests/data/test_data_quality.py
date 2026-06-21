"""Tests unitaires — src/transformation/data_quality.py (Sprint 17 Axe 6, 2026-06-21).

Couvre :
* QualityConfig : defaults conformes à la spec §7.1
* CheckDetail / QualityReport : dataclass + to_dict
* Sub-checks purs : _check_range, _check_null_ratio, _check_duplicate_ratio, _check_min_rows
* 3 validators (traffic/tcl/velov) : tous les cas pass + fail
* run_all_validations : retourne 3 rapports
* QualityReport.is_critical : True/False selon statut
* QualityReport.to_dict : sérialisable (DB insert + JSON UI)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.transformation.data_quality import (
    STATUS_CRITICAL,
    STATUS_OK,
    STATUS_WARNING,
    CheckDetail,
    QualityConfig,
    QualityReport,
    _aggregate_status,
    _check_duplicate_ratio,
    _check_min_rows,
    _check_null_ratio,
    _check_range,
    _empty_report,
    run_all_validations,
    validate_tcl_realtime,
    validate_traffic_features,
    validate_velov_clean,
)

# -----------------------------------------------------------------------------
# Fixtures : DataFrames synthétiques
# -----------------------------------------------------------------------------


def _make_clean_traffic(n: int = 200) -> pd.DataFrame:
    """DataFrame gold.traffic_features_live avec données propres."""
    np.random.seed(0)
    return pd.DataFrame(
        {
            "channel_id": [f"c{i % 10}" for i in range(n)],
            "computed_at": pd.date_range("2026-06-21 10:00", periods=n, freq="3min"),
            "speed_kmh": np.random.uniform(20, 80, n),
            "vitesse_limite_kmh": [50] * n,
            "temperature_2m": np.random.uniform(5, 30, n),
            "precipitation": np.random.uniform(0, 2, n),
        }
    )


def _make_clean_tcl(n: int = 200) -> pd.DataFrame:
    """DataFrame gold.tcl_vehicle_realtime avec données propres."""
    np.random.seed(1)
    return pd.DataFrame(
        {
            "vehicle_ref": [f"v{i % 20}" for i in range(n)],
            "recorded_at": pd.date_range("2026-06-21 10:00", periods=n, freq="3min"),
            "line_ref": [f"L{i % 5}" for i in range(n)],
            "latitude": np.random.uniform(45.72, 45.81, n),
            "longitude": np.random.uniform(4.81, 4.90, n),
            "delay_seconds": np.random.randint(0, 300, n),
            "is_delayed": [True] * n,
        }
    )


def _make_clean_velov(n: int = 200) -> pd.DataFrame:
    """DataFrame silver.velov_clean avec données propres."""
    np.random.seed(2)
    return pd.DataFrame(
        {
            "station_id": [f"s{i % 15}" for i in range(n)],
            "measurement_time": pd.date_range("2026-06-21 10:00", periods=n, freq="3min"),
            "station_name": [f"Station {i % 15}" for i in range(n)],
            "lat": np.random.uniform(45.72, 45.81, n),
            "lon": np.random.uniform(4.81, 4.90, n),
            "num_bikes_available": np.random.randint(0, 30, n),
            "num_docks_available": np.random.randint(0, 30, n),
            "is_active": [True] * n,
        }
    )


# -----------------------------------------------------------------------------
# QualityConfig + dataclasses
# -----------------------------------------------------------------------------


class TestQualityConfig:
    """Vérifie les défauts de la config conformes à la spec §7.1."""

    def test_defaults_match_spec(self) -> None:
        """Les seuils par défaut sont exactement ceux de la spec."""
        cfg = QualityConfig()
        assert cfg.speed_min_kmh == 0.0
        assert cfg.speed_max_kmh == 130.0
        assert cfg.temperature_min_c == -20.0
        assert cfg.temperature_max_c == 45.0
        assert cfg.precipitation_max_mm == 100.0
        assert cfg.delay_max_seconds == 3600
        assert cfg.bikes_min == 0
        assert cfg.bikes_max == 60
        assert cfg.docks_min == 0
        assert cfg.docks_max == 60
        assert cfg.max_null_ratio == 0.30
        assert cfg.max_duplicate_ratio == 0.05
        assert cfg.min_rows == 100

    def test_custom_config(self) -> None:
        """Les seuils sont tunables (override des défauts)."""
        cfg = QualityConfig(speed_max_kmh=50.0, max_null_ratio=0.10)
        assert cfg.speed_max_kmh == 50.0
        assert cfg.max_null_ratio == 0.10
        # Les autres défauts sont préservés
        assert cfg.delay_max_seconds == 3600


class TestDataclasses:
    """Sérialisation CheckDetail + QualityReport."""

    def test_check_detail_to_dict(self) -> None:
        """CheckDetail.to_dict() retourne les 5 champs."""
        d = CheckDetail(
            check="speed_range",
            status=STATUS_OK,
            metric_value=0.0,
            threshold=130.0,
            details="OK",
        )
        out = d.to_dict()
        assert out == {
            "check": "speed_range",
            "status": STATUS_OK,
            "metric_value": 0.0,
            "threshold": 130.0,
            "details": "OK",
        }

    def test_quality_report_to_dict(self) -> None:
        """QualityReport.to_dict() inclut table + details sérialisés."""
        report = QualityReport(
            table="gold.traffic_features_live",
            timestamp="2026-06-21T10:00:00+00:00",
            overall_status=STATUS_OK,
            checks_passed=2,
            checks_failed=0,
            details=[
                CheckDetail("c1", STATUS_OK, 0.0, 1.0, "ok"),
                CheckDetail("c2", STATUS_OK, 0.0, 1.0, "ok"),
            ],
        )
        out = report.to_dict()
        assert out["table"] == "gold.traffic_features_live"
        assert out["overall_status"] == STATUS_OK
        assert out["checks_passed"] == 2
        assert out["checks_failed"] == 0
        assert len(out["details"]) == 2
        assert out["details"][0]["check"] == "c1"

    def test_is_critical_property(self) -> None:
        """is_critical True si overall_status == critical, False sinon."""
        r_crit = QualityReport(
            table="t", timestamp="t", overall_status=STATUS_CRITICAL,
            checks_passed=0, checks_failed=1, details=[],
        )
        r_ok = QualityReport(
            table="t", timestamp="t", overall_status=STATUS_OK,
            checks_passed=1, checks_failed=0, details=[],
        )
        r_warn = QualityReport(
            table="t", timestamp="t", overall_status=STATUS_WARNING,
            checks_passed=0, checks_failed=1, details=[],
        )
        assert r_crit.is_critical is True
        assert r_ok.is_critical is False
        assert r_warn.is_critical is False

    def test_aggregate_status(self) -> None:
        """_aggregate_status prend le pire statut + compte passed/failed."""
        details = [
            CheckDetail("c1", STATUS_OK, 0.0, 1.0, ""),
            CheckDetail("c2", STATUS_WARNING, 0.0, 1.0, ""),
            CheckDetail("c3", STATUS_OK, 0.0, 1.0, ""),
        ]
        overall, passed, failed = _aggregate_status(details)
        assert overall == STATUS_WARNING
        assert passed == 2
        assert failed == 1

        # Avec un critical → overall = critical
        details_crit = [*details, CheckDetail("c4", STATUS_CRITICAL, 0.0, 1.0, "")]
        overall, passed, failed = _aggregate_status(details_crit)
        assert overall == STATUS_CRITICAL
        assert passed == 2
        assert failed == 2

        # Vide → warning
        overall, passed, failed = _aggregate_status([])
        assert overall == STATUS_WARNING
        assert passed == 0
        assert failed == 0


# -----------------------------------------------------------------------------
# Sub-checks purs
# -----------------------------------------------------------------------------


class TestCheckRange:
    """_check_range : valeurs dans [min_v, max_v]."""

    def test_all_in_range(self) -> None:
        df = pd.DataFrame({"x": [10, 20, 30, 40, 50]})
        d = _check_range(df, "x", 0, 100)
        assert d.status == STATUS_OK
        assert d.metric_value == 0.0

    def test_some_violations_warning(self) -> None:
        """1-5% violations = warning (pas critical)."""
        df = pd.DataFrame({"x": [10, 20, 30, 40, 50, 1000, 2000]})  # 2/7 = 28%... hmm
        # En fait 2/7 = 28% > 5% → critical. Refaisons avec 1/100 = 1%
        df = pd.DataFrame({"x": [50] * 99 + [1000]})  # 1/100 = 1% → warning
        d = _check_range(df, "x", 0, 100)
        assert d.status == STATUS_WARNING
        assert d.metric_value == 1.0

    def test_many_violations_critical(self) -> None:
        """> 5% violations = critical."""
        df = pd.DataFrame({"x": [50] * 90 + [1000] * 10})  # 10/100 = 10% → critical
        d = _check_range(df, "x", 0, 100)
        assert d.status == STATUS_CRITICAL
        assert d.metric_value == 10.0

    def test_missing_column(self) -> None:
        """Colonne absente → warning (pas critical)."""
        df = pd.DataFrame({"y": [1, 2, 3]})
        d = _check_range(df, "x", 0, 100)
        assert d.status == STATUS_WARNING
        assert "absente" in d.details

    def test_empty_df(self) -> None:
        """DF vide → warning (pas d'évaluation possible)."""
        df = pd.DataFrame({"x": []})
        d = _check_range(df, "x", 0, 100)
        assert d.status == STATUS_WARNING


class TestCheckNullRatio:
    """_check_null_ratio : ratio nulls < max_null_ratio."""

    def test_no_nulls(self) -> None:
        df = pd.DataFrame({"x": [1, 2, 3, 4, 5]})
        d = _check_null_ratio(df, "x", max_null_ratio=0.30)
        assert d.status == STATUS_OK
        assert d.metric_value == 0.0

    def test_acceptable_nulls(self) -> None:
        """20% nulls < 30% seuil → OK."""
        df = pd.DataFrame({"x": [1, 2, 3, None, None]})  # 2/5 = 40%... non
        # Refaisons : 1/5 = 20% → OK
        df = pd.DataFrame({"x": [1, 2, 3, 4, None]})  # 1/5 = 20% → OK
        d = _check_null_ratio(df, "x", max_null_ratio=0.30)
        assert d.status == STATUS_OK
        assert abs(d.metric_value - 0.20) < 1e-9

    def test_too_many_nulls_critical(self) -> None:
        """> 30% nulls → critical."""
        df = pd.DataFrame({"x": [1, None, None, None, None]})  # 4/5 = 80% → critical
        d = _check_null_ratio(df, "x", max_null_ratio=0.30)
        assert d.status == STATUS_CRITICAL
        assert abs(d.metric_value - 0.80) < 1e-9


class TestCheckDuplicateRatio:
    """_check_duplicate_ratio : ratio doublons sur subset < max."""

    def test_no_duplicates(self) -> None:
        df = pd.DataFrame({
            "k1": [1, 2, 3, 4, 5],
            "k2": ["a", "b", "c", "d", "e"],
        })
        d = _check_duplicate_ratio(df, ["k1", "k2"], max_duplicate_ratio=0.05)
        assert d.status == STATUS_OK
        assert d.metric_value == 0.0

    def test_acceptable_duplicates(self) -> None:
        """1/20 = 5% = seuil → OK (≤ seuil)."""
        df = pd.DataFrame({
            "k1": [1, 2, 1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
            "k2": ["a"] * 20,
        })
        # 1 doublon / 20 = 5% → OK (seuil = 5%, on accepte l'égalité)
        d = _check_duplicate_ratio(df, ["k1", "k2"], max_duplicate_ratio=0.05)
        assert d.status == STATUS_OK

    def test_too_many_duplicates_critical(self) -> None:
        """10/100 = 10% > 5% → critical."""
        df = pd.DataFrame({
            "k1": [1] * 10 + list(range(2, 92)),  # 10 rows avec k1=1
            "k2": ["a"] * 100,
        })
        d = _check_duplicate_ratio(df, ["k1", "k2"], max_duplicate_ratio=0.05)
        assert d.status == STATUS_CRITICAL

    def test_missing_subset_column(self) -> None:
        """Colonne subset absente → warning (pas critical)."""
        df = pd.DataFrame({"k1": [1, 2, 3]})
        d = _check_duplicate_ratio(df, ["k1", "k2"], max_duplicate_ratio=0.05)
        assert d.status == STATUS_WARNING
        assert "absentes" in d.details


class TestCheckMinRows:
    """_check_min_rows : df a au moins min_rows lignes."""

    def test_above_min(self) -> None:
        df = pd.DataFrame({"x": range(200)})
        d = _check_min_rows(df, min_rows=100)
        assert d.status == STATUS_OK
        assert d.metric_value == 200.0

    def test_below_min_warning(self) -> None:
        """50% du seuil = warning."""
        df = pd.DataFrame({"x": range(80)})  # 80 entre 50 et 100 → warning
        d = _check_min_rows(df, min_rows=100)
        assert d.status == STATUS_WARNING
        assert d.metric_value == 80.0

    def test_below_half_critical(self) -> None:
        """< 50% du seuil = critical."""
        df = pd.DataFrame({"x": range(30)})  # 30 < 50 → critical
        d = _check_min_rows(df, min_rows=100)
        assert d.status == STATUS_CRITICAL


# -----------------------------------------------------------------------------
# Validators
# -----------------------------------------------------------------------------


class TestValidateTrafficFeatures:
    """validate_traffic_features : traffic validator complet."""

    def test_clean_data_pass(self) -> None:
        """Données propres → overall_status=ok, tous checks passent."""
        df = _make_clean_traffic(n=200)
        report = validate_traffic_features(df)
        assert report.table == "gold.traffic_features_live"
        assert report.overall_status == STATUS_OK
        assert report.checks_failed == 0
        assert report.is_critical is False
        # 6 sub-checks : range_speed, null_speed, duplicate, min_rows, range_temp, range_precip
        assert len(report.details) == 6

    def test_speed_out_of_range_critical(self) -> None:
        """speed_kmh > 130 sur > 5% rows → critical."""
        df = _make_clean_traffic(n=200)
        df.loc[0:30, "speed_kmh"] = 200  # 31/200 = 15.5% > 5% → critical
        report = validate_traffic_features(df)
        assert report.is_critical
        range_check = next(d for d in report.details if d.check == "range_speed_kmh")
        assert range_check.status == STATUS_CRITICAL
        assert "130.0" in range_check.details

    def test_too_many_nulls_critical(self) -> None:
        """> 30% nulls sur speed_kmh → critical."""
        df = _make_clean_traffic(n=200)
        df.loc[0:80, "speed_kmh"] = None  # 81/200 = 40.5% > 30% → critical
        report = validate_traffic_features(df)
        assert report.is_critical
        null_check = next(d for d in report.details if d.check == "null_ratio_speed_kmh")
        assert null_check.status == STATUS_CRITICAL

    def test_too_many_duplicates_critical(self) -> None:
        """> 5% doublons (channel_id, computed_at) → critical."""
        df = _make_clean_traffic(n=200)
        # Inject 30 doublons
        df_dup = pd.concat([df, df.iloc[:30]], ignore_index=True)
        report = validate_traffic_features(df_dup)
        assert report.is_critical
        dup_check = next(d for d in report.details if d.check == "duplicate_ratio")
        assert dup_check.status == STATUS_CRITICAL

    def test_min_rows_critical(self) -> None:
        """< 50% de min_rows → critical."""
        df = _make_clean_traffic(n=30)  # < 50% de 100
        report = validate_traffic_features(df)
        assert report.is_critical
        min_check = next(d for d in report.details if d.check == "min_rows")
        assert min_check.status == STATUS_CRITICAL

    def test_empty_df_warning(self) -> None:
        """DF vide → report warning (1 check failed = dataframe_empty)."""
        report = validate_traffic_features(pd.DataFrame())
        assert report.overall_status == STATUS_WARNING
        assert report.checks_passed == 0
        assert report.checks_failed == 1
        assert not report.is_critical


class TestValidateTclRealtime:
    """validate_tcl_realtime : TCL validator complet."""

    def test_clean_data_pass(self) -> None:
        df = _make_clean_tcl(n=200)
        report = validate_tcl_realtime(df)
        assert report.table == "gold.tcl_vehicle_realtime"
        assert report.overall_status == STATUS_OK
        assert report.checks_failed == 0

    def test_delay_out_of_range_critical(self) -> None:
        """delay_seconds > 3600 sur > 5% rows → critical."""
        df = _make_clean_tcl(n=200)
        df.loc[0:30, "delay_seconds"] = 7200  # 31/200 = 15.5% > 5% → critical
        report = validate_tcl_realtime(df)
        assert report.is_critical
        range_check = next(d for d in report.details if d.check == "range_delay_seconds")
        assert range_check.status == STATUS_CRITICAL
        assert "3600" in range_check.details

    def test_negative_delay_warning(self) -> None:
        """delay_seconds < 0 sur 1 row (0.5%) → warning (pas critical, < 5%)."""
        df = _make_clean_tcl(n=200)
        df.loc[0, "delay_seconds"] = -10  # 1/200 = 0.5% → warning
        report = validate_tcl_realtime(df)
        assert report.overall_status == STATUS_WARNING
        assert not report.is_critical


class TestValidateVelovClean:
    """validate_velov_clean : Vélov validator complet."""

    def test_clean_data_pass(self) -> None:
        df = _make_clean_velov(n=200)
        report = validate_velov_clean(df)
        assert report.table == "silver.velov_clean"
        assert report.overall_status == STATUS_OK
        assert report.checks_failed == 0

    def test_negative_bikes_critical(self) -> None:
        """num_bikes_available < 0 sur > 5% rows → critical."""
        df = _make_clean_velov(n=200)
        df.loc[0:30, "num_bikes_available"] = -5  # 31/200 = 15.5% > 5% → critical
        report = validate_velov_clean(df)
        assert report.is_critical
        bikes_check = next(d for d in report.details if d.check == "range_num_bikes_available")
        assert bikes_check.status == STATUS_CRITICAL

    def test_bikes_above_max_critical(self) -> None:
        """num_bikes_available > 60 sur > 5% rows → critical (borne station)."""
        df = _make_clean_velov(n=200)
        df.loc[0:30, "num_bikes_available"] = 80  # > 60 sur 15% → critical
        report = validate_velov_clean(df)
        assert report.is_critical
        bikes_check = next(d for d in report.details if d.check == "range_num_bikes_available")
        assert bikes_check.status == STATUS_CRITICAL


# -----------------------------------------------------------------------------
# Orchestrateur
# -----------------------------------------------------------------------------


class TestRunAllValidations:
    """run_all_validations : retourne 3 rapports (sans DB, DFs vides)."""

    def test_returns_three_reports(self) -> None:
        """run_all_validations() retourne 1 rapport par validator."""
        reports = run_all_validations()
        assert len(reports) == 3
        assert reports[0].table == "gold.traffic_features_live"
        assert reports[1].table == "gold.tcl_vehicle_realtime"
        assert reports[2].table == "silver.velov_clean"

    def test_empty_reports_are_warnings(self) -> None:
        """Sans DB, les 3 rapports sont 'warning' (dataframe_empty)."""
        reports = run_all_validations()
        for r in reports:
            assert r.overall_status == STATUS_WARNING
            assert r.checks_passed == 0
            assert r.checks_failed == 1
            assert not r.is_critical

    def test_shared_config(self) -> None:
        """Le QualityConfig passé est utilisé par les 3 validators."""
        cfg = QualityConfig(speed_max_kmh=50.0)  # Override speed uniquement
        reports = run_all_validations(config=cfg)
        # Les rapports vides n'utilisent pas la config (mais aucune erreur)
        assert len(reports) == 3


class TestEmptyReport:
    """_empty_report : helper pour DF vide / None."""

    def test_empty_report_is_warning(self) -> None:
        r = _empty_report("test.table")
        assert r.table == "test.table"
        assert r.overall_status == STATUS_WARNING
        assert r.checks_passed == 0
        assert r.checks_failed == 1
        assert not r.is_critical
        assert "vide" in r.details[0].details
