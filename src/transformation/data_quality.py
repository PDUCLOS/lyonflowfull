"""Module — Validation qualité des données Gold/Silver (Sprint 17 Axe 6, 2026-06-21).

Port conceptuel de `PDUCLOS/Lyontraffic/src/transformation/data_quality.py`
adapté au schéma LyonFlow. Valide les données AVANT le feature
engineering, pour détecter en amont :

* Plages physiquement impossibles (speed > 130 km/h, delay > 1h, bikes < 0...)
* Taux de null excessif (≥ 30% sur colonnes critiques)
* Taux de doublons excessif (≥ 5% sur clé naturelle)
* Volume minimal (≥ 100 rows sur fenêtre d'analyse)

Architecture :

* ``QualityConfig`` : dataclass des seuils (tunable, défaut spec §7.1).
* ``QualityReport`` : résultat pour 1 table (overall_status + détails par check).
* ``CheckDetail`` : 1 sous-check (1 ligne dans QualityReport.details).
* 3 validators (traffic, tcl, velov) : prennent un DataFrame en entrée,
  retournent un QualityReport. **Pure Python**, testables en unitaire.
* ``run_all_validations()`` : appelle les 3 + log les résultats dans
  ``gold.data_quality_log`` (migration 025).

Intégration DAG :
* ``dags/maintenance/maintenance.py`` → ``_data_quality_check(check_name)``
  mappe les 6 task_ids legacy vers les 3 validators + sous-checks.

Dashboard :
* ``gold.data_quality_log`` lu par ``db_query.get_quality_report()``.
* Widget ``data_quality_detail.py`` affiche le détail des checks
  (distinct de ``data_quality_badge.py`` qui est sur source_health).

Politique "zéro mock" (Sprint 8+) :
* Pas de fallback silencieux. Si la DB indispo, ``load_X()`` lève
  ``DashboardDataError``. Les validators purs ne touchent pas la DB.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import pandas as pd

# =============================================================================
# Config + Report dataclasses
# =============================================================================


@dataclass
class QualityConfig:
    """Seuils de validation (Sprint 17 Axe 6, spec §7.1).

    Tous les seuils sont tunables. Les défauts correspondent à la spec
    d'origine (port LyonTraffic) :

    ============================  ===================================
    Seuil                          Valeur par défaut
    ============================  ===================================
    speed_min_kmh                  0.0
    speed_max_kmh                  130.0  (limite légale + capteurs urbains)
    temperature_min_c              -20.0  (records historiques Lyon)
    temperature_max_c              45.0
    precipitation_max_mm           100.0  (orage extrême)
    delay_max_seconds              3600   (1h max de retard)
    bikes_min                      0
    bikes_max                      60     (borne pratique station Vélov)
    docks_min                      0
    docks_max                      60
    max_null_ratio                 0.30   (au-delà, données inexploitables)
    max_duplicate_ratio            0.05   (source de biais)
    min_rows                       100    (pas assez de données → warning)
    ============================  ===================================
    """

    speed_min_kmh: float = 0.0
    speed_max_kmh: float = 130.0
    temperature_min_c: float = -20.0
    temperature_max_c: float = 45.0
    precipitation_max_mm: float = 100.0
    delay_max_seconds: int = 3600
    bikes_min: int = 0
    bikes_max: int = 60
    docks_min: int = 0
    docks_max: int = 60
    max_null_ratio: float = 0.30
    max_duplicate_ratio: float = 0.05
    min_rows: int = 100


# Status utilisés dans tout le module.
STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_CRITICAL = "critical"


def _now_iso() -> str:
    """Timestamp ISO UTC (helper testable)."""
    return datetime.now(UTC).isoformat()


@dataclass
class CheckDetail:
    """Détail d'un sous-check individuel.

    Attributes:
        check: nom du check (ex: "speed_range", "null_ratio_speed_kmh").
        status: 'ok' | 'warning' | 'critical'.
        metric_value: valeur observée de la métrique.
        threshold: valeur seuil de la config.
        details: description textuelle (pour logs + UI).
    """

    check: str
    status: str
    metric_value: float
    threshold: float
    details: str

    def to_dict(self) -> dict[str, Any]:
        """Sérialisation dict (pour DB insert + JSON UI)."""
        return asdict(self)


@dataclass
class QualityReport:
    """Rapport qualité pour 1 table.

    Attributes:
        table: nom complet 'schema.table' (ex: 'gold.traffic_features_live').
        timestamp: ISO UTC du moment d'évaluation.
        overall_status: 'ok' | 'warning' | 'critical' (pire des sous-checks).
        checks_passed: nb de sous-checks en 'ok'.
        checks_failed: nb de sous-checks en 'warning' + 'critical'.
        details: liste des sous-checks (1 par métrique évaluée).
    """

    table: str
    timestamp: str
    overall_status: str
    checks_passed: int
    checks_failed: int
    details: list[CheckDetail] = field(default_factory=list)

    @property
    def is_critical(self) -> bool:
        """True si au moins un sous-check est en critical."""
        return self.overall_status == STATUS_CRITICAL

    def to_dict(self) -> dict[str, Any]:
        """Sérialisation dict (pour DB insert + JSON UI)."""
        return {
            "table": self.table,
            "timestamp": self.timestamp,
            "overall_status": self.overall_status,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "details": [d.to_dict() for d in self.details],
        }


# =============================================================================
# Helpers internes (sub-checks unitaires, tous purs)
# =============================================================================


def _empty_report(table: str) -> QualityReport:
    """Rapport vide (quand df est vide ou None — tous checks skipped)."""
    details = [
        CheckDetail(
            check="dataframe_empty",
            status=STATUS_WARNING,
            metric_value=0.0,
            threshold=0.0,
            details="DataFrame vide — aucun check applicable",
        )
    ]
    overall, passed, failed = _aggregate_status(details)
    return QualityReport(
        table=table,
        timestamp=_now_iso(),
        overall_status=overall,
        checks_passed=passed,
        checks_failed=failed,
        details=details,
    )


def _check_range(
    df: pd.DataFrame,
    col: str,
    min_v: float,
    max_v: float,
) -> CheckDetail:
    """Vérifie que toutes les valeurs de ``col`` sont dans [min_v, max_v].

    Returns:
        CheckDetail avec status=ok si 0 violation, warning si 1-5%, critical
        si > 5% (sinon un seul outlier ne déclencherait pas l'alerte utile).
    """
    n_total = len(df)
    if n_total == 0 or col not in df.columns:
        return CheckDetail(
            check=f"range_{col}",
            status=STATUS_WARNING,
            metric_value=0.0,
            threshold=float(max_v - min_v),
            details=f"Colonne '{col}' absente ou DF vide",
        )
    s = pd.to_numeric(df[col], errors="coerce")
    n_violations = int(((s < min_v) | (s > max_v)).sum())
    ratio = n_violations / n_total
    if ratio == 0.0:
        status = STATUS_OK
        details = f"{col}: {n_total} valeurs dans [{min_v}, {max_v}]"
    elif ratio <= 0.05:
        status = STATUS_WARNING
        details = f"{col}: {n_violations}/{n_total} hors plage [{min_v}, {max_v}] ({ratio * 100:.1f}%)"
    else:
        status = STATUS_CRITICAL
        details = (
            f"{col}: {n_violations}/{n_total} hors plage "
            f"[{min_v}, {max_v}] ({ratio * 100:.1f}%) — au-delà du seuil critique 5%"
        )
    return CheckDetail(
        check=f"range_{col}",
        status=status,
        metric_value=float(n_violations),
        threshold=float(max_v - min_v),
        details=details,
    )


def _check_null_ratio(
    df: pd.DataFrame,
    col: str,
    max_null_ratio: float,
) -> CheckDetail:
    """Vérifie que le ratio de nulls sur ``col`` est < max_null_ratio.

    Returns:
        CheckDetail avec status=ok si null_ratio <= max_null_ratio,
        critical si > max_null_ratio (warning entre les deux n'est pas
        utilisé — la spec dit "au-delà, données inexploitables").
    """
    n_total = len(df)
    if n_total == 0 or col not in df.columns:
        return CheckDetail(
            check=f"null_ratio_{col}",
            status=STATUS_WARNING,
            metric_value=0.0,
            threshold=float(max_null_ratio),
            details=f"Colonne '{col}' absente ou DF vide",
        )
    n_null = int(df[col].isna().sum())
    ratio = n_null / n_total
    if ratio <= max_null_ratio:
        status = STATUS_OK
        details = f"{col}: {n_null}/{n_total} nulls ({ratio * 100:.1f}%)"
    else:
        status = STATUS_CRITICAL
        details = f"{col}: {n_null}/{n_total} nulls ({ratio * 100:.1f}%) — au-delà du seuil {max_null_ratio * 100:.0f}%"
    return CheckDetail(
        check=f"null_ratio_{col}",
        status=status,
        metric_value=ratio,
        threshold=float(max_null_ratio),
        details=details,
    )


def _check_duplicate_ratio(
    df: pd.DataFrame,
    subset: list[str],
    max_duplicate_ratio: float,
) -> CheckDetail:
    """Vérifie que le ratio de doublons (sur la clé naturelle ``subset``)
    est < max_duplicate_ratio.

    Returns:
        CheckDetail avec status=ok si dup_ratio <= max_duplicate_ratio,
        critical si > max_duplicate_ratio.
    """
    n_total = len(df)
    if n_total == 0:
        return CheckDetail(
            check="duplicate_ratio",
            status=STATUS_WARNING,
            metric_value=0.0,
            threshold=float(max_duplicate_ratio),
            details="DataFrame vide — pas de doublon à analyser",
        )
    missing = [c for c in subset if c not in df.columns]
    if missing:
        return CheckDetail(
            check="duplicate_ratio",
            status=STATUS_WARNING,
            metric_value=0.0,
            threshold=float(max_duplicate_ratio),
            details=f"Colonnes absentes pour clé naturelle : {missing}",
        )
    n_dup = int(df.duplicated(subset=subset).sum())
    ratio = n_dup / n_total
    if ratio <= max_duplicate_ratio:
        status = STATUS_OK
        details = f"Doublons sur {subset}: {n_dup}/{n_total} ({ratio * 100:.2f}%)"
    else:
        status = STATUS_CRITICAL
        details = (
            f"Doublons sur {subset}: {n_dup}/{n_total} ({ratio * 100:.2f}%) "
            f"— au-delà du seuil {max_duplicate_ratio * 100:.0f}%"
        )
    return CheckDetail(
        check="duplicate_ratio",
        status=status,
        metric_value=ratio,
        threshold=float(max_duplicate_ratio),
        details=details,
    )


def _check_min_rows(
    df: pd.DataFrame,
    min_rows: int,
) -> CheckDetail:
    """Vérifie que le DataFrame a au moins ``min_rows`` lignes.

    Returns:
        CheckDetail avec status=ok si >= min_rows, warning si 50% du seuil,
        critical si < 50% du seuil.
    """
    n = len(df)
    if n >= min_rows:
        status = STATUS_OK
        details = f"Volume OK : {n} rows (seuil {min_rows})"
    elif n >= min_rows * 0.5:
        status = STATUS_WARNING
        details = f"Volume bas : {n} rows (seuil {min_rows}, 50% du seuil = warning)"
    else:
        status = STATUS_CRITICAL
        details = f"Volume critique : {n} rows (seuil {min_rows}, < 50% du seuil)"
    return CheckDetail(
        check="min_rows",
        status=status,
        metric_value=float(n),
        threshold=float(min_rows),
        details=details,
    )


def _aggregate_status(details: list[CheckDetail]) -> tuple[str, int, int]:
    """Agrège les statuts d'une liste de CheckDetail.

    Returns:
        Tuple (overall_status, checks_passed, checks_failed).
    """
    if not details:
        return STATUS_WARNING, 0, 0
    passed = sum(1 for d in details if d.status == STATUS_OK)
    failed = len(details) - passed
    statuses = {d.status for d in details}
    if STATUS_CRITICAL in statuses:
        overall = STATUS_CRITICAL
    elif STATUS_WARNING in statuses:
        overall = STATUS_WARNING
    else:
        overall = STATUS_OK
    return overall, passed, failed


# =============================================================================
# Validators (1 par table, prennent un DataFrame en entrée)
# =============================================================================


def validate_traffic_features(
    df: pd.DataFrame,
    config: QualityConfig | None = None,
    table: str = "gold.traffic_features_live",
) -> QualityReport:
    """Valide ``gold.traffic_features_live``.

    Checks :
    * Plage speed_kmh [0, 130]
    * Plage temperature_2m [-20, 45] (si colonne présente)
    * Plage precipitation [0, 100] (si colonne présente)
    * Null ratio sur speed_kmh < 30%
    * Doublons sur (channel_id, fetched_at) < 5%
    * Volume ≥ 100 rows

    Args:
        df: DataFrame avec les colonnes traffic (subset du Gold).
        config: seuils (défaut = QualityConfig()).
        table: nom complet (pour le rapport).

    Returns:
        QualityReport avec 1 CheckDetail par sous-check.
    """
    if config is None:
        config = QualityConfig()
    if df is None or df.empty:
        return _empty_report(table)

    details: list[CheckDetail] = [
        _check_range(df, "speed_kmh", config.speed_min_kmh, config.speed_max_kmh),
        _check_null_ratio(df, "speed_kmh", config.max_null_ratio),
        _check_duplicate_ratio(df, ["channel_id", "fetched_at"], config.max_duplicate_ratio),
        _check_min_rows(df, config.min_rows),
    ]
    # Météo (colonnes optionnelles — pas critique si absentes)
    if "temperature_2m" in df.columns:
        details.append(
            _check_range(
                df,
                "temperature_2m",
                config.temperature_min_c,
                config.temperature_max_c,
            )
        )
    if "precipitation" in df.columns:
        details.append(_check_range(df, "precipitation", 0.0, config.precipitation_max_mm))

    overall, passed, failed = _aggregate_status(details)
    return QualityReport(
        table=table,
        timestamp=_now_iso(),
        overall_status=overall,
        checks_passed=passed,
        checks_failed=failed,
        details=details,
    )


def validate_tcl_realtime(
    df: pd.DataFrame,
    config: QualityConfig | None = None,
    table: str = "gold.tcl_vehicle_realtime",
) -> QualityReport:
    """Valide ``gold.tcl_vehicle_realtime``.

    Checks :
    * Plage delay_seconds [0, 3600]
    * Null ratio sur delay_seconds < 30%
    * Doublons sur (vehicle_ref, recorded_at) < 5%
    * Volume ≥ 100 rows

    Args:
        df: DataFrame avec les colonnes TCL.
        config: seuils (défaut = QualityConfig()).
        table: nom complet (pour le rapport).

    Returns:
        QualityReport avec 1 CheckDetail par sous-check.
    """
    if config is None:
        config = QualityConfig()
    if df is None or df.empty:
        return _empty_report(table)

    details: list[CheckDetail] = [
        _check_range(df, "delay_seconds", 0.0, float(config.delay_max_seconds)),
        _check_null_ratio(df, "delay_seconds", config.max_null_ratio),
        _check_duplicate_ratio(df, ["vehicle_ref", "recorded_at"], config.max_duplicate_ratio),
        _check_min_rows(df, config.min_rows),
    ]
    overall, passed, failed = _aggregate_status(details)
    return QualityReport(
        table=table,
        timestamp=_now_iso(),
        overall_status=overall,
        checks_passed=passed,
        checks_failed=failed,
        details=details,
    )


def validate_velov_clean(
    df: pd.DataFrame,
    config: QualityConfig | None = None,
    table: str = "silver.velov_clean",
) -> QualityReport:
    """Valide ``silver.velov_clean``.

    Checks :
    * Plage num_bikes_available [0, 60]
    * Plage num_docks_available [0, 60]
    * Null ratio sur num_bikes_available < 30%
    * Doublons sur (station_id, measurement_time) < 5%
    * Volume ≥ 100 rows

    Args:
        df: DataFrame avec les colonnes Vélov.
        config: seuils (défaut = QualityConfig()).
        table: nom complet (pour le rapport).

    Returns:
        QualityReport avec 1 CheckDetail par sous-check.
    """
    if config is None:
        config = QualityConfig()
    if df is None or df.empty:
        return _empty_report(table)

    details: list[CheckDetail] = [
        _check_range(df, "num_bikes_available", float(config.bikes_min), float(config.bikes_max)),
        _check_range(df, "num_docks_available", float(config.docks_min), float(config.docks_max)),
        _check_null_ratio(df, "num_bikes_available", config.max_null_ratio),
        _check_duplicate_ratio(df, ["station_id", "measurement_time"], config.max_duplicate_ratio),
        _check_min_rows(df, config.min_rows),
    ]
    overall, passed, failed = _aggregate_status(details)
    return QualityReport(
        table=table,
        timestamp=_now_iso(),
        overall_status=overall,
        checks_passed=passed,
        checks_failed=failed,
        details=details,
    )


# =============================================================================
# Orchestrateur
# =============================================================================


def run_all_validations(
    config: QualityConfig | None = None,
) -> list[QualityReport]:
    """Exécute les 3 validators (sans toucher la DB — pure orchestration).

    Pour brancher sur la DB, voir ``dags/maintenance/maintenance.py``
    ``_data_quality_check()`` qui :
    1. Charge le DataFrame depuis Postgres
    2. Appelle le validator correspondant
    3. INSERT le résultat dans ``gold.data_quality_log``
    4. Raise si critical (alerte Airflow)

    Args:
        config: seuils (partagé entre les 3 validators).

    Returns:
        Liste de 3 QualityReport (traffic, tcl, velov), dans l'ordre.
    """
    if config is None:
        config = QualityConfig()
    # NOTE : sans DB, on retourne 3 rapports "vides" — l'orchestration
    # réelle (load + insert) est dans le DAG.
    return [
        validate_traffic_features(pd.DataFrame(), config=config),
        validate_tcl_realtime(pd.DataFrame(), config=config),
        validate_velov_clean(pd.DataFrame(), config=config),
    ]
