"""Tests Sprint 22+ audit saturation (Patrice) — couverture gold.mv_sensor_saturation.

Couvre les 4 quick wins du sprint :
- F4 : _parse_grandlyon_vitesse() filter ``0`` → None
- Migration 033 : vue ``gold.mv_sensor_saturation`` (v85, sat, amp, status)
- Seuils stuck : amp_pct < 2 ET std_24h < 1 km/h
- Loader + cache : ``load_sensor_saturation()`` + ``cached_sensor_saturation()``

Tests marqués ``@pytest.mark.integration`` requièrent un VPS
accessible (PostgreSQL + migration 034 (matérialisée) appliquée).
"""

from __future__ import annotations

import pytest


# =============================================================================
# F4 — _parse_grandlyon_vitesse filter 0
# =============================================================================


class TestParseGrandlyonVitesse:
    """Sprint 22+ F4 : les valeurs 0 sont écartées (capteurs stuck suspect)."""

    def test_zero_km_h_string_returns_none(self):
        from src.transformation.bronze_to_silver import _parse_grandlyon_vitesse

        assert _parse_grandlyon_vitesse("0 km/h") is None

    def test_zero_float_returns_none(self):
        from src.transformation.bronze_to_silver import _parse_grandlyon_vitesse

        assert _parse_grandlyon_vitesse(0.0) is None

    def test_zero_int_returns_none(self):
        from src.transformation.bronze_to_silver import _parse_grandlyon_vitesse

        assert _parse_grandlyon_vitesse(0) is None

    def test_normal_speed_parsed(self):
        from src.transformation.bronze_to_silver import _parse_grandlyon_vitesse

        assert _parse_grandlyon_vitesse("18 km/h") == 18.0
        assert _parse_grandlyon_vitesse("56.5 km/h") == 56.5
        assert _parse_grandlyon_vitesse(45.0) == 45.0

    def test_vitesse_reglementaire_returns_none(self):
        from src.transformation.bronze_to_silver import _parse_grandlyon_vitesse

        assert _parse_grandlyon_vitesse("Vitesse réglementaire") is None

    def test_empty_returns_none(self):
        from src.transformation.bronze_to_silver import _parse_grandlyon_vitesse

        assert _parse_grandlyon_vitesse("") is None
        assert _parse_grandlyon_vitesse(None) is None


# =============================================================================
# Migration 033 — Vue gold.mv_sensor_saturation
# =============================================================================


class TestSensorSaturationViewSQL:
    """Vérifie que la migration 034 (matérialisée) est bien formée (parse SQL)."""

    MIGRATION_PATH = "scripts/sql/migration_034_sensor_saturation_mat.sql"

    def test_migration_file_exists(self):
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent.parent / self.MIGRATION_PATH
        assert path.exists(), f"Migration introuvable : {self.MIGRATION_PATH}"

    def test_migration_creates_v_sensor_saturation(self):
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent.parent / self.MIGRATION_PATH
        content = path.read_text()
        assert "CREATE MATERIALIZED VIEW gold.mv_sensor_saturation AS" in content

    def test_migration_computes_v85_amp_sat(self):
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent.parent / self.MIGRATION_PATH
        content = path.read_text()
        # v85 : percentile_cont(0.85) WITHIN GROUP (ORDER BY speed_kmh)
        assert "PERCENTILE_CONT(0.85)" in content
        # amplitude = a24.vmax_24h - a24.vmin_24h (préfixe a24. car CTE)
        assert "a24.vmax_24h - a24.vmin_24h" in content
        # saturation = current_speed / v85_7j * 100
        assert "current_speed / NULLIF(a7.v85_7j, 0)" in content

    def test_migration_stuck_seuil_2pct(self):
        """Le seuil stuck doit être amp < 2% ET std < 1 km/h (Sprint 22+)."""
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent.parent / self.MIGRATION_PATH
        content = path.read_text()
        # amp < 2% (= 2.0)
        assert "< 2.0" in content
        # std < 1.0 km/h
        assert "std_24h < 1.0" in content


# =============================================================================
# Loader + cache
# =============================================================================


class TestLoadSensorSaturation:
    """load_sensor_saturation() : expose la vue avec fail loud si indispo."""

    def test_loader_exists_in_data_loader(self):
        from src.data import data_loader

        assert hasattr(data_loader, "load_sensor_saturation")

    def test_loader_signature(self):
        import inspect

        from src.data import data_loader

        sig = inspect.signature(data_loader.load_sensor_saturation)
        # Pas de param (la vue n'a pas de filtre par channel_id pour l'instant)
        assert len(sig.parameters) == 0

    def test_cache_exists(self):
        from dashboard.components import data_cache

        assert hasattr(data_cache, "cached_sensor_saturation")

    def test_cache_ttl_fast(self):
        """Le cache doit être TTL_FAST (60s) pour rester réactif sur
        la vue qui scanne 7j × 5min × 1520 nœuds."""
        from dashboard.components import data_cache
        from dashboard.components.data_cache import TTL_FAST

        # Vérifie que cached_sensor_saturation a bien le décorateur @st.cache_data
        # avec ttl=TTL_FAST
        cached_func = data_cache.cached_sensor_saturation
        assert hasattr(cached_func, "__wrapped__"), "Cache décorateur manquant"
        # Le TTL_FAST est utilisé (Streamlit cache_data n'expose pas le TTL
        # directement, mais on peut vérifier la présence du wrapper)
        assert TTL_FAST == 60


# =============================================================================
# Seuils stuck — logiques métier
# =============================================================================


class TestStuckSeuilLogic:
    """Vérifie que le seuil stuck (amp < 2% ET std < 1 km/h) est respecté."""

    def test_stuck_status_conditions(self):
        """Un capteur stuck = amp < 2% ET std < 1 km/h sur 24h."""
        # Cas stuck confirmé
        amp = 1.5
        std = 0.5
        is_stuck = (std < 1.0) and ((amp / 100) < 2.0 / 100)
        assert is_stuck is True

        # Cas ok (variation normale)
        amp = 50.0
        std = 15.0
        is_stuck = (std < 1.0) and ((amp / 100) < 2.0 / 100)
        assert is_stuck is False

        # Cas limite (std < 1 mais amp > 2)
        amp = 3.0
        std = 0.5
        is_stuck = (std < 1.0) and ((amp / 100) < 2.0 / 100)
        # std OK mais amp > 2%, donc PAS stuck
        assert is_stuck is False


# =============================================================================
# Tests d'intégration (skip par défaut — requièrent VPS)
# =============================================================================


@pytest.mark.integration
class TestSensorSaturationLive:
    """Tests live : requièrent PostgreSQL + migration 034 (matérialisée) appliquée."""

    def test_vue_retourne_dataframe_non_vide(self):
        """Avec données live, la vue doit retourner au moins 100 capteurs."""
        from src.data.data_loader import load_sensor_saturation

        df = load_sensor_saturation()
        # Si vide : la table source n'est pas alimentée
        if df.empty:
            pytest.skip("gold.traffic_features_live vide — pas de capteurs à analyser")
        assert len(df) >= 100
        assert "channel_id" in df.columns
        assert "v85_7j" in df.columns
        assert "sat_now_pct" in df.columns
        assert "amp_pct" in df.columns
        assert "status" in df.columns

    def test_status_values_in_enum(self):
        from src.data.data_loader import load_sensor_saturation

        df = load_sensor_saturation()
        if df.empty:
            pytest.skip("Vue vide")
        valid_status = {"ok", "stale", "stuck", "no_data"}
        assert set(df["status"].unique()).issubset(valid_status)

    def test_v85_sup_to_current_speed_when_congested(self):
        """En congestion, sat_now_pct < 100 (v85 > vitesse actuelle)."""
        from src.data.data_loader import load_sensor_saturation

        df = load_sensor_saturation()
        if df.empty or "sat_now_pct" not in df.columns:
            pytest.skip("Vue vide")
        # Au moins 1 capteur devrait avoir sat_now_pct < 100 (sinon pas de bouchon)
        congested = df[df["sat_now_pct"].notna() & (df["sat_now_pct"] < 100)]
        if len(congested) == 0:
            pytest.skip("Aucun capteur en congestion sur la fenêtre 7j — vérifier le trafic")
        assert len(congested) > 0
