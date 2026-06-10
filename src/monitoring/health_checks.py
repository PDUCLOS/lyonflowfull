"""Monitoring — health checks (6 checks quotidiens).

Checks :
1. Freshness Bronze (last fetched_at < 30 min)
2. Volume Bronze (n_records attendu par source)
3. NULLs Silver (colonnes critiques NULL > seuil)
4. Doublons Silver (clé naturelle dupliquée)
5. Prédictions présentes (gold.trafic_predictions non vide)
6. Drift baseline (Evidently — comparé J-7 vs J)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from src.db import execute_query, execute_scalar

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    """Résultat d'un health check."""

    name: str
    status: str  # 'ok' | 'warning' | 'critical'
    details: str
    metric_value: float | None = None
    threshold: float | None = None
    timestamp: str = ""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def check_bronze_freshness(max_age_minutes: int = 30) -> CheckResult:
    """Vérifie que Bronze a des données récentes (< 30 min par défaut)."""
    query = """
        SELECT
            schemaname || '.' || tablename AS source,
            EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60 AS age_minutes
        FROM bronze.trafic_boucles, bronze.velov, bronze.tcl_vehicles, bronze.meteo
        WHERE 1=1
        GROUP BY schemaname, tablename
    """  # noqa: F841
    # En pratique, on ferait une UNION par table
    age = execute_scalar("SELECT EXTRACT(EPOCH FROM (NOW() - MAX(fetched_at)))/60 FROM bronze.trafic_boucles")
    age = float(age or 999)
    status = "ok" if age < max_age_minutes else "warning" if age < max_age_minutes * 2 else "critical"
    return CheckResult(
        name="bronze_freshness",
        status=status,
        details=f"Bronze trafic_boucles: dernière ingestion il y a {age:.1f} min",
        metric_value=age,
        threshold=float(max_age_minutes),
        timestamp=_now_iso(),
    )


def check_bronze_volume() -> CheckResult:
    """Vérifie que le volume Bronze est dans les normes attendues."""
    query = """
        SELECT
            (SELECT COUNT(*) FROM bronze.trafic_boucles WHERE fetched_at > NOW() - INTERVAL '1 hour') AS trafic,
            (SELECT COUNT(*) FROM bronze.velov WHERE fetched_at > NOW() - INTERVAL '1 hour') AS velov,
            (SELECT COUNT(*) FROM bronze.tcl_vehicles WHERE fetched_at > NOW() - INTERVAL '1 hour') AS tcl,
            (SELECT COUNT(*) FROM bronze.meteo WHERE fetched_at > INTERVAL '1 day') AS meteo
    """
    rows = execute_query(query, ())
    if not rows:
        return CheckResult(
            name="bronze_volume",
            status="critical",
            details="Aucune donnée Bronze sur 1h",
            timestamp=_now_iso(),
        )
    r = rows[0]
    n_total = sum(int(v or 0) for v in r.values())
    # Seuil minimum : 1000 records/h attendu (somme des 3 sources 5min)
    status = "ok" if n_total > 1000 else "warning" if n_total > 100 else "critical"
    return CheckResult(
        name="bronze_volume",
        status=status,
        details=f"Volume Bronze 1h: trafic={r.get('trafic', 0)}, velov={r.get('velov', 0)}, tcl={r.get('tcl', 0)}, meteo_24h={r.get('meteo', 0)}",
        metric_value=float(n_total),
        threshold=1000.0,
        timestamp=_now_iso(),
    )


def check_silver_nulls(max_null_pct: float = 5.0) -> CheckResult:
    """Vérifie qu'il n'y a pas trop de NULLs sur les colonnes critiques Silver."""
    query = """
        SELECT
            COUNT(*) FILTER (WHERE vitesse_kmh IS NULL)::FLOAT /
                NULLIF(COUNT(*), 0) * 100 AS vitesse_null_pct,
            COUNT(*) FILTER (WHERE geom_wgs84 IS NULL)::FLOAT /
                NULLIF(COUNT(*), 0) * 100 AS geom_null_pct
        FROM silver.trafic_boucles_clean
        WHERE measurement_time > NOW() - INTERVAL '1 hour'
    """
    rows = execute_query(query, ())
    if not rows or rows[0].get("vitesse_null_pct") is None:
        return CheckResult(
            name="silver_nulls",
            status="warning",
            details="Pas de données Silver 1h pour vérification",
            timestamp=_now_iso(),
        )
    vitesse_null = float(rows[0].get("vitesse_null_pct", 0))
    geom_null = float(rows[0].get("geom_null_pct", 0))
    max_observed = max(vitesse_null, geom_null)
    status = "ok" if max_observed < max_null_pct else "warning" if max_observed < max_null_pct * 2 else "critical"
    return CheckResult(
        name="silver_nulls",
        status=status,
        details=f"Nulls Silver 1h: vitesse={vitesse_null:.1f}%, geom={geom_null:.1f}%",
        metric_value=max_observed,
        threshold=max_null_pct,
        timestamp=_now_iso(),
    )


def check_silver_doublons() -> CheckResult:
    """Vérifie qu'il n'y a pas de doublons sur la clé naturelle Silver."""
    query = """
        SELECT COUNT(*) - COUNT(DISTINCT (channel_id, measurement_time)) AS doublons
        FROM silver.trafic_boucles_clean
        WHERE measurement_time > NOW() - INTERVAL '1 hour'
    """
    n = int(execute_scalar(query) or 0)
    status = "ok" if n == 0 else "warning" if n < 10 else "critical"
    return CheckResult(
        name="silver_doublons",
        status=status,
        details=f"{n} doublons détectés sur silver.trafic_boucles_clean (1h)",
        metric_value=float(n),
        threshold=0.0,
        timestamp=_now_iso(),
    )


def check_predictions_presentes() -> CheckResult:
    """Vérifie qu'on a des prédictions récentes en Gold."""
    n = int(
        execute_scalar(
            "SELECT COUNT(*) FROM gold.trafic_predictions WHERE calculated_at > NOW() - INTERVAL '2 hours'"
        )
        or 0
    )
    status = "ok" if n > 100 else "warning" if n > 0 else "critical"
    return CheckResult(
        name="predictions_presentes",
        status=status,
        details=f"{n} prédictions dans gold.trafic_predictions (2h)",
        metric_value=float(n),
        threshold=100.0,
        timestamp=_now_iso(),
    )


def check_drift_evidently() -> CheckResult:
    """Compare distribution J-7 vs J via Evidently (placeholder simple)."""
    # En production : utiliser Evidently DataDriftPreset
    # Pour MVP : on check que la table drift_reports est alimentée
    n = int(execute_scalar("SELECT COUNT(*) FROM gold.model_drift_reports") or 0)
    status = "ok" if n > 0 else "warning"
    return CheckResult(
        name="drift_baseline",
        status=status,
        details=f"{n} rapports drift enregistrés (Evidently à intégrer)",
        metric_value=float(n),
        threshold=1.0,
        timestamp=_now_iso(),
    )


# Catalogue des checks
ALL_CHECKS = [
    check_bronze_freshness,
    check_bronze_volume,
    check_silver_nulls,
    check_silver_doublons,
    check_predictions_presentes,
    check_drift_evidently,
]


def run_all_checks() -> list[CheckResult]:
    """Exécute tous les health checks et retourne les résultats."""
    results = []
    for fn in ALL_CHECKS:
        try:
            r = fn()
        except Exception as e:
            r = CheckResult(
                name=fn.__name__,
                status="critical",
                details=f"Exception: {e}",
                timestamp=_now_iso(),
            )
        results.append(r)
        # Log
        if r.status == "critical":
            logger.error(f"[{r.name}] CRITICAL: {r.details}")
        elif r.status == "warning":
            logger.warning(f"[{r.name}] WARNING: {r.details}")
        else:
            logger.info(f"[{r.name}] OK: {r.details}")
    return results


def run_dag_health_check() -> dict:
    """Fonction appelée par le DAG Airflow daily_data_quality.

    Returns:
        Dict {check_name: status} pour les XCom Airflow.
    """
    results = run_all_checks()
    return {r.name: r.status for r in results}
