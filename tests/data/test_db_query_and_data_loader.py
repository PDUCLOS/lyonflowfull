"""Tests Sprint 8 (2026-06-12) — Fail loud en l'absence de DB.

Avant (Sprint VPS-6) : ``load_X()`` retournait un mock si la DB était
down, ce qui masquait les pannes. Maintenant (Sprint 8) : zéro mock,
donc ``load_X()`` lève ``DashboardDataError`` quand la DB est
indisponible.

Ce module valide :
1. ``_is_db_available()`` retourne False quand l'env ne pointe pas
   vers une DB.
2. ``load_X()`` lèvent ``DashboardDataError`` (pas de fallback mock).

Note : pour tester du code avec une vraie DB, marquer
``@pytest.mark.integration`` (voir ``tests/integration/``). Sprint 15+
(2026-06-19) — la fixture ``mock_db`` qui monkeypatchait
``src.db.connection`` a été virée d'un commun accord avec Patrice.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data import data_loader, db_query
from src.data.exceptions import DashboardDataError


@pytest.fixture(autouse=True)
def disable_db(monkeypatch):
    """Force ``_is_db_available = False`` pour ces tests (pas de DB locale).

    IMPORTANT : il faut patcher dans DEUX modules. ``data_loader`` importe
    ``_is_db_available`` via ``from src.data.db_query import _is_db_available``
    (cf. data_loader.py:39-40), ce qui crée une seconde référence dans
    l'espace de nom de ``data_loader``. Patch uniquement ``db_query`` ne
    suffit pas en CI où la Postgres service est UP — le test vérifie que
    ``load_X()`` lève ``DashboardDataError`` quand la DB est indispo, donc
    les DEUX références doivent retourner False.
    """
    monkeypatch.setattr(db_query, "_is_db_available", lambda: False)
    monkeypatch.setattr(data_loader, "_is_db_available", lambda: False)
    db_query.reset_db_cache()
    yield
    db_query.reset_db_cache()


# =============================================================================
# Helper : charge_X qui DOIT lever DashboardDataError en absence de DB
# =============================================================================

FAIL_LOUD_FUNCS = [
    "load_traffic",
    "load_velov_stations",
    "load_bus_delays",
    "load_infra_bottlenecks",
    "load_predictions_vs_actuals",
    "load_rgpd_audit",
    "load_rgpd_consents",
    "load_weather_hourly",
    "load_recent_alerts",
    "load_segments",
    "load_correlation_matrix",
    "load_buses_positions",
    "load_amenagements_passes",
]


@pytest.mark.parametrize("func_name", FAIL_LOUD_FUNCS)
def test_load_x_raises_when_no_db(func_name: str) -> None:
    """Sprint 8 : load_X() lève DashboardDataError si DB indispo.

    Avant : retournait un mock silencieux. Maintenant : fail loud.
    """
    func = getattr(data_loader, func_name)
    with pytest.raises(DashboardDataError):
        func()


def test_load_kpis_12_months_raises_when_no_db() -> None:
    """load_kpis_12_months doit aussi fail loud."""
    with pytest.raises(DashboardDataError):
        data_loader.load_kpis_12_months()


def test_load_elu_kpis_dict_raises_when_no_db() -> None:
    """load_elu_kpis_dict doit aussi fail loud."""
    with pytest.raises(DashboardDataError):
        data_loader.load_elu_kpis_dict()


def test_load_bottlenecks_top_raises_when_no_db() -> None:
    """load_bottlenecks_top doit aussi fail loud.

    Sprint 8 — bug connu : get_bottlenecks_summary n'est pas exporté
    par src.data.db_query. À fixer Sprint 9.
    """
    with pytest.raises((DashboardDataError, ImportError)):
        data_loader.load_bottlenecks_top()


def test_load_tcl_lines_raises_when_no_db() -> None:
    """load_tcl_lines lit gold.tcl_vehicle_realtime en DB, fail loud."""
    with pytest.raises(DashboardDataError):
        data_loader.load_tcl_lines()


def test_load_lyon_addresses_raises_when_no_db() -> None:
    """load_lyon_addresses : DB obligatoire (referentiel.lieux_lyon)."""
    with pytest.raises(DashboardDataError):
        data_loader.load_lyon_addresses()


# =============================================================================
# Tests fail-loud supplémentaires (sans mock — DB absente = exception)
# =============================================================================


def test_load_kpis_12_months_raises_explicit() -> None:
    """load_kpis_12_months : pas de fallback (Sprint 8)."""
    with pytest.raises(DashboardDataError) as exc_info:
        data_loader.load_kpis_12_months()
    assert "kpis" in str(exc_info.value).lower() or "month" in str(exc_info.value).lower()


# =============================================================================
# Tests Sprint 22+ (2026-06-25) — Fix 9 bugs Elu_2_Bottlenecks
# =============================================================================
# Vérifie :
# 1. SQL de get_bottlenecks_summary lit mv_bus_traffic_spatial (Bug 3/9)
# 2. load_bottlenecks_top retourne diagnosis + lat + lon + DB-driven values
#    (Bug 1/4/5/7) — plus aucune fonction linéaire de l'index ``i``
# =============================================================================


def test_get_bottlenecks_summary_reads_mv_bus_traffic_spatial() -> None:
    """Bug 3/9 fix : SQL lit mv_bus_traffic_spatial (spatial) et plus
    infrastructure_bottlenecks (global par heure).

    Vérifie le contenu du SQL dans le code source (pas d'exécution DB ici).
    On vérifie la requête SQL (string multi-ligne contenant ``FROM``) et
    pas la docstring qui peut légitimement mentionner l'ancienne source.
    """
    import inspect

    from src.data.db_query import get_bottlenecks_summary

    src = inspect.getsource(get_bottlenecks_summary)
    assert "gold.mv_bus_traffic_spatial" in src, (
        "get_bottlenecks_summary doit lire gold.mv_bus_traffic_spatial (vue matérialisée spatiale 0.001°)"
    )
    # Le SELECT doit finir par FROM gold.mv_bus_traffic_spatial (pas
    # infrastructure_bottlenecks). On cherche la sous-string SQL "FROM gold."
    # pour exclure la docstring.
    assert "FROM gold.mv_bus_traffic_spatial" in src, "FROM clause doit pointer sur gold.mv_bus_traffic_spatial"
    assert "FROM gold.infrastructure_bottlenecks" not in src, (
        "FROM clause ne doit PLUS pointer sur gold.infrastructure_bottlenecks"
    )
    assert "ROW_NUMBER() OVER" in src, "Le SELECT doit calculer le rank via ROW_NUMBER()"


def test_load_bottlenecks_top_dict_has_diagnosis_and_coords(monkeypatch) -> None:
    """Bug 1/4/6/7 fix : load_bottlenecks_top retourne un dict enrichi.

    Vérifie la présence des nouvelles clés ``diagnosis``, ``lat``, ``lon``,
    ``avg_delay_s``, ``traffic_speed_kmh`` et que les anciennes clés
    économiques sont désormais dérivées de la DB (pas hardcodées).
    """
    # Monkeypatch _is_db_available (sinon DB indispo → fail loud immédiat)
    monkeypatch.setattr(data_loader, "_is_db_available", lambda: True)
    monkeypatch.setattr(db_query, "_is_db_available", lambda: True)
    db_query.reset_db_cache()

    # Monkeypatch load_bottlenecks_summary pour retourner un DataFrame réaliste
    # provenant de mv_bus_traffic_spatial (colonnes bottleneck_id, road_name,
    # line_ref, diagnosis, avg_bus_delay_s, traffic_speed_kmh,
    # traffic_congestion, n_observations, lat, lng, computed_at).
    fake_df = pd.DataFrame(
        [
            {
                "bottleneck_id": 1,
                "road_name": "ActIV:Line::66:SYTRAL_h8",
                "road_label": "L66",
                "line_ref": "ActIV:Line::66:SYTRAL",
                "line_label": "L66",
                "diagnosis": "infra",
                "avg_bus_delay_s": 180.0,  # 3 min retard
                "avg_traffic_speed_kmh": 20.0,
                "traffic_congestion": 0.6,
                "n_observations": 500,
                "lat": 45.7589,
                "lng": 4.8414,
                "computed_at": pd.Timestamp("2026-06-25T08:00:00"),
            },
            {
                "bottleneck_id": 2,
                "road_name": "ActIV:Line::C13:SYTRAL_h17",
                "road_label": "C13",
                "line_ref": "ActIV:Line::C13:SYTRAL",
                "line_label": "C13",
                "diagnosis": "operations",
                "avg_bus_delay_s": 150.0,
                "avg_traffic_speed_kmh": 35.0,
                "traffic_congestion": 0.3,
                "n_observations": 800,
                "lat": 45.7720,
                "lng": 4.8550,
                "computed_at": pd.Timestamp("2026-06-25T08:00:00"),
            },
        ]
    )

    monkeypatch.setattr(data_loader, "load_bottlenecks_summary", lambda: fake_df)

    bottlenecks = data_loader.load_bottlenecks_top()

    assert len(bottlenecks) == 2
    b0, b1 = bottlenecks

    # Clés existantes (rétro-compat top_decisions.py)
    for key in (
        "rank",
        "zone",
        "lines_impacted",
        "voyageurs_jour",
        "gain_min",
        "cout_M_euros",
        "roi_mois",
        "delai_mois",
        "description",
    ):
        assert key in b0, f"Clé rétro-compat manquante : {key}"

    # Nouvelles clés (Bug 4 + Bug 6 lat/lon)
    assert "diagnosis" in b0
    assert b0["diagnosis"] == "infra"
    assert b1["diagnosis"] == "operations"

    assert b0["lat"] == 45.7589
    assert b0["lon"] == 4.8414
    assert "avg_delay_s" in b0
    assert b0["avg_delay_s"] == 180.0
    assert "traffic_speed_kmh" in b0
    assert b0["traffic_speed_kmh"] == 20.0  # lu depuis avg_traffic_speed_kmh (alias SQL)

    # Bug 1 fix : gain_min dérivé de avg_delay_s (pas hardcodé)
    # avg_delay_s = 180 → gain_min = 180/60 * 0.5 = 1.5 min
    assert b0["gain_min"] == 1.5, f"gain_min doit valoir 1.5 (180/60*0.5), got {b0['gain_min']}"
    # Bug 1 fix : cout_M_euros selon diagnosis
    assert b0["cout_M_euros"] == 3.0, "infra → 3.0 M€ (cf. COUT_PAR_DIAGNOSTIC)"
    assert b1["cout_M_euros"] == 0.8, "operations → 0.8 M€"

    # Bug 5 fix : voyageurs_jour = n_obs * 36 (pas l'alias trompeur)
    assert b0["voyageurs_jour"] == 500 * 36, f"500 obs × 36 = 18000, got {b0['voyageurs_jour']}"
    assert b1["voyageurs_jour"] == 800 * 36

    # Bug 7 fix : ROI calculé via formule (pas hardcodé 18 + i*3)
    # gain_annuel = voyageurs * (gain_min/60) * 15 * 2 * 250
    # b0 : 18000 * (1.5/60) * 15 * 2 * 250 = 18000 * 0.025 * 15 * 500 = 3_375_000
    # cout_euros = 3_000_000
    # roi_mois = 3_000_000 / 3_375_000 * 12 ≈ 10.67
    assert 10 < b0["roi_mois"] < 11, f"ROI b0 attendu ~10.67, got {b0['roi_mois']}"

    # Description lisible (pas le "Amélioration #N…" générique d'avant)
    assert "infrastructure" in b0["description"].lower()
    assert "opérationnel" in b1["description"].lower() or "operationnel" in b1["description"].lower()


def test_load_bottlenecks_top_empty_when_no_data(monkeypatch) -> None:
    """Si mv_bus_traffic_spatial vide → liste vide (pas de mock fallback)."""
    monkeypatch.setattr(data_loader, "_is_db_available", lambda: True)
    monkeypatch.setattr(db_query, "_is_db_available", lambda: True)
    db_query.reset_db_cache()
    monkeypatch.setattr(data_loader, "load_bottlenecks_summary", lambda: pd.DataFrame())

    assert data_loader.load_bottlenecks_top() == []
