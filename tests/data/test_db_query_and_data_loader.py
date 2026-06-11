"""Tests pour src.data.db_query et src.data.data_loader.

Ces tests ne nécessitent pas de DB active. Ils vérifient:

1. **Le pattern de fallback** : si la DB est down, les fonctions renvoient
   les mocks.
2. **Le contrat des DataFrames** : colonnes attendues, types cohérents.
3. **Le paramètre force_mock** : bypass la détection DB.
4. **Le cache de disponibilité** : ``reset_db_cache()`` permet de re-tester.

Pour tester avec une vraie DB, voir ``tests/integration/test_infrastructure.py``
qui démarre un PostgreSQL en container.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Permet l'import de `src` depuis la racine du repo
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data import data_loader, db_query
from src.data.mock import elu, pro_tcl, usager


@pytest.fixture(autouse=True)
def enable_demo_mode(monkeypatch):
    """Sprint VPS-6 (2026-06-11) — active ``LYONFLOW_DEMO_MODE=1`` pour
    ces tests, qui valident le **contrat des mocks** (donc en mode démo).

    Reset le cache DB + force ``_is_db_available=False`` pour exercer le
    chemin mock. Pour les tests d'intégration avec une vraie DB, voir
    ``tests/integration/test_infrastructure.py``.

    Le nouveau test ``test_no_mock_vps_policy.py`` valide au contraire
    le mode prod (fail loud).
    """
    monkeypatch.setenv("LYONFLOW_DEMO_MODE", "1")
    data_loader._demo_mode_cache = None  # reset AVANT chaque test
    db_query.reset_db_cache()
    monkeypatch.setattr(db_query, "_is_db_available", lambda: False)
    yield
    db_query.reset_db_cache()
    data_loader._demo_mode_cache = None  # reset APRÈS chaque test


# =============================================================================
# db_query : tests du fallback mock
# =============================================================================


class TestDbQueryFallback:
    """Vérifie que db_query retourne des mocks cohérents quand la DB est down."""

    def test_get_latest_traffic_returns_dataframe(self):
        df = db_query.get_latest_traffic(limit=10)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert "node_idx" in df.columns
        assert "speed_kmh" in df.columns

    def test_operational_error_triggers_fallback_in_data_loader(self, monkeypatch):
        """Sprint VPS-6 — mode démo : DB up signalée mais query crash →
        df vide → fallback mock servi (préserve comportement historique).

        En mode prod (test_no_mock_vps_policy.py), le même scénario lève
        ``DashboardDataError`` au lieu de servir un mock.
        """
        from src.data.data_loader import _is_demo_mode

        # Le fixture autouse active LYONFLOW_DEMO_MODE=1
        assert _is_demo_mode(), "Test doit tourner en mode démo"
        import psycopg2

        # Simuler un crash DB au moment de la connexion
        def mock_execute_query(*args, **kwargs):
            raise psycopg2.OperationalError("Simulated DB crash mid-flight")

        monkeypatch.setattr(db_query, "execute_query", mock_execute_query)
        # DB "up" au sens health check (sert à piéger _maybe_force_mock)
        # mais la query réelle crash — comme si la connexion lâchait mid-flight.
        monkeypatch.setattr(data_loader, "_is_db_available", lambda: True)
        monkeypatch.setattr(db_query, "_is_db_available", lambda: True)

        # En mode démo :
        #   _maybe_force_mock → False (DB dispo)
        #   _require_db_or_raise → OK
        #   get_latest_traffic → execute_query CRASH → df vide
        #   load_traffic → df.empty → fallback MOCK_TRAFFIC (préservé en démo)
        traffic = data_loader.load_traffic(force_mock=False)
        assert isinstance(traffic, dict)
        assert traffic.get("city") == "Lyon", "Doit basculer sur le mock (mode démo) car df vide suite au crash"

    def test_get_latest_traffic_respects_limit(self):
        df = db_query.get_latest_traffic(limit=5)
        assert len(df) == 5

    def test_get_traffic_for_node_returns_timeseries(self):
        df = db_query.get_traffic_for_node(node_idx=1, hours=1)
        assert isinstance(df, pd.DataFrame)

    def test_get_traffic_predictions_returns_dataframe(self):
        df = db_query.get_traffic_predictions(horizon_minutes=60, limit=20)
        assert isinstance(df, pd.DataFrame)
        assert "predicted_speed" in df.columns or df.empty

    def test_get_traffic_bottlenecks_returns_dataframe(self):
        df = db_query.get_traffic_bottlenecks(top=10)
        assert isinstance(df, pd.DataFrame)
        assert "node_idx" in df.columns

    def test_get_predictions_vs_actuals_returns_dataframe(self):
        df = db_query.get_predictions_vs_actuals(limit=50)
        assert isinstance(df, pd.DataFrame)
        assert "model_name" in df.columns

    def test_get_velov_stations_geo_returns_dataframe(self):
        df = db_query.get_velov_stations_geo()
        assert isinstance(df, pd.DataFrame)
        assert "lat" in df.columns
        assert "lng" in df.columns

    def test_get_velov_predictions_returns_dataframe(self):
        df = db_query.get_velov_predictions(horizon_minutes=30)
        assert isinstance(df, pd.DataFrame)

    def test_get_bus_delay_segments_returns_dataframe(self):
        df = db_query.get_bus_delay_segments(days=7)
        assert isinstance(df, pd.DataFrame)
        assert "line_ref" in df.columns

    def test_get_bus_delay_segments_with_line_filter(self):
        df = db_query.get_bus_delay_segments(line_ref="C3", days=7)
        assert isinstance(df, pd.DataFrame)

    def test_get_infrastructure_bottlenecks_returns_dataframe(self):
        df = db_query.get_infrastructure_bottlenecks(top=10)
        assert isinstance(df, pd.DataFrame)
        assert "diagnosis" in df.columns

    def test_get_spatial_mapping_returns_dataframe(self):
        df = db_query.get_spatial_mapping()
        assert isinstance(df, pd.DataFrame)
        assert "node_idx" in df.columns
        assert "channel_id" in df.columns

    def test_get_gnn_adjacency_returns_dataframe(self):
        df = db_query.get_gnn_adjacency()
        assert isinstance(df, pd.DataFrame)
        assert "node_u" in df.columns
        assert "node_v" in df.columns

    def test_get_rgpd_audit_log_returns_dataframe(self):
        df = db_query.get_rgpd_audit_log(limit=10)
        assert isinstance(df, pd.DataFrame)
        assert "action" in df.columns

    def test_get_rgpd_consents_summary_returns_dataframe(self):
        df = db_query.get_rgpd_consents_summary()
        assert isinstance(df, pd.DataFrame)
        assert "consent_type" in df.columns

    def test_get_rgpd_data_subject_requests_returns_dataframe(self):
        df = db_query.get_rgpd_data_subject_requests(limit=10)
        assert isinstance(df, pd.DataFrame)
        assert "request_type" in df.columns

    def test_get_rgpd_purge_history_returns_dataframe(self):
        df = db_query.get_rgpd_purge_history(limit=10)
        assert isinstance(df, pd.DataFrame)

    def test_get_bronze_source_counts_returns_dataframe(self):
        df = db_query.get_bronze_source_counts(hours=1)
        assert isinstance(df, pd.DataFrame)
        assert "source" in df.columns
        assert "n_rows" in df.columns

    def test_get_data_freshness_returns_none_for_unknown(self):
        # Schema/table non whitelisté → None
        result = db_query.get_data_freshness(schema="public", table="unknown")
        assert result is None

    def test_safe_dataframe_returns_placeholder_for_empty(self):
        empty_df = pd.DataFrame()
        result = db_query.safe_dataframe(empty_df, "Aucune donnée.")
        assert "info" in result.columns
        assert result.iloc[0]["info"] == "Aucune donnée."

    def test_safe_dataframe_returns_original_for_non_empty(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = db_query.safe_dataframe(df)
        assert result.equals(df)


# =============================================================================
# data_loader : tests de la couche "intelligente"
# =============================================================================


class TestDataLoader:
    """Vérifie que data_loader.load_X() renvoient les bonnes structures."""

    def test_load_traffic_returns_dict(self):
        traffic = data_loader.load_traffic(force_mock=True)
        assert isinstance(traffic, dict)
        assert "average_speed_kmh" in traffic
        assert "congestion_level" in traffic
        assert "predictions" in traffic
        assert traffic["data_source"] == "mock"

    def test_load_traffic_has_predictions(self):
        traffic = data_loader.load_traffic(force_mock=True)
        preds = traffic["predictions"]
        assert "h_plus_30min" in preds
        assert "h_plus_1h" in preds
        assert "h_plus_3h" in preds

    def test_load_traffic_main_jams_have_required_fields(self):
        traffic = data_loader.load_traffic(force_mock=True)
        jams = traffic["main_jams"]
        assert len(jams) > 0
        for jam in jams:
            assert "road" in jam
            assert "speed_kmh" in jam
            assert "severity" in jam

    def test_load_velov_stations_returns_list(self):
        stations = data_loader.load_velov_stations(force_mock=True)
        assert isinstance(stations, list)
        assert len(stations) > 0
        for s in stations:
            assert "bikes_available" in s
            assert "stands_available" in s

    def test_load_velov_predictions_returns_dataframe(self):
        df = data_loader.load_velov_predictions(horizon_minutes=30, force_mock=True)
        assert isinstance(df, pd.DataFrame)

    def test_load_bus_delays_returns_dataframe(self):
        df = data_loader.load_bus_delays(force_mock=True)
        assert isinstance(df, pd.DataFrame)
        assert "line_ref" in df.columns

    def test_load_bus_delays_filters_by_line(self):
        df = data_loader.load_bus_delays(line_ref="C3", force_mock=True)
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert (df["line_ref"] == "C3").all()

    def test_load_infra_bottlenecks_returns_dataframe(self):
        df = data_loader.load_infra_bottlenecks(force_mock=True)
        assert isinstance(df, pd.DataFrame)

    def test_load_predictions_vs_actuals_returns_dataframe(self):
        df = data_loader.load_predictions_vs_actuals(force_mock=True)
        assert isinstance(df, pd.DataFrame)
        assert "model_name" in df.columns

    def test_load_rgpd_audit_returns_dataframe(self):
        df = data_loader.load_rgpd_audit(force_mock=True)
        assert isinstance(df, pd.DataFrame)

    def test_load_rgpd_consents_returns_dataframe(self):
        df = data_loader.load_rgpd_consents(force_mock=True)
        assert isinstance(df, pd.DataFrame)
        assert "consent_type" in df.columns

    def test_load_line_kpis_returns_dict(self):
        kpis = data_loader.load_line_kpis(force_mock=True)
        assert isinstance(kpis, dict)
        assert "M_A" in kpis  # Au moins une ligne
        assert "otp_pct" in kpis["M_A"]

    def test_load_otp_heatmap_data_returns_dataframe(self):
        df = data_loader.load_otp_heatmap_data(force_mock=True)
        assert isinstance(df, pd.DataFrame)
        assert "line_id" in df.columns
        assert "hour" in df.columns
        assert "otp_pct" in df.columns
        assert len(df) > 0

    def test_load_city_synthesis_returns_dict(self):
        synth = data_loader.load_city_synthesis(force_mock=True)
        assert isinstance(synth, dict)
        assert "traffic" in synth
        assert "velov" in synth
        assert "bus" in synth

    def test_load_bottlenecks_summary_returns_dataframe(self):
        df = data_loader.load_bottlenecks_summary(force_mock=True)
        assert isinstance(df, pd.DataFrame)
        assert "segment_id" in df.columns


# =============================================================================
# Mocks : vérifie que les constantes existent et sont bien formées
# =============================================================================


class TestMockData:
    """Vérifie que les mocks ont la bonne shape."""

    def test_mock_traffic_features_has_required_fields(self):
        for entry in usager.MOCK_TRAFFIC_FEATURES:
            assert "measurement_time" in entry
            assert "node_idx" in entry
            assert "speed_kmh" in entry

    def test_mock_velov_stations_geo_has_required_fields(self):
        for s in usager.MOCK_VELOV_STATIONS_GEO:
            assert "station_id" in s
            assert "lat" in s
            assert "lng" in s

    def test_mock_trafic_predictions_has_required_fields(self):
        for p in usager.MOCK_TRAFIC_PREDICTIONS:
            assert "horizon_minutes" in p
            assert "predicted_speed" in p

    def test_mock_bus_delays_has_required_fields(self):
        for d in usager.MOCK_BUS_DELAYS:
            assert "line_ref" in d
            assert "avg_delay_seconds" in d

    def test_mock_synthesis_has_all_domains(self):
        s = elu.SYNTHESIS_DATA
        for domain in ("traffic", "velov", "bus", "meteo", "air_quality"):
            assert domain in s, f"Domain '{domain}' manquant dans SYNTHESIS_DATA"

    def test_mock_bottlenecks_list_has_required_fields(self):
        for b in elu.BOTTLENECKS_LIST:
            assert "segment_id" in b
            assert "congestion_level" in b
            assert "lat" in b
            assert "lng" in b
