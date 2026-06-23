"""Tests unitaires Sprint 22+ — corrections audit méthodique.

Couvre les 4 bugs identifiés par Patrice lors de l'audit du 2026-06-23 :

1. ``_approx_lonlat_from_channel_id`` retiré (markers de bouchons au hasard)
2. ``get_traffic_bottlenecks`` retourne lat/lon réels (LATERAL JOIN)
3. ``recommend_mode`` fail loud si aucune durée fournie
4. ``_is_congested_from_speed`` réellement câblé dans Usager_1
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# Fix #2 : _approx_lonlat_from_channel_id retiré
# =============================================================================


def test_approx_lonlat_helper_removed():
    """Le helper de hash pseudo-aléatoire doit être viré (Sprint 22+)."""
    from src.data import data_loader

    assert not hasattr(data_loader, "_approx_lonlat_from_channel_id"), (
        "_approx_lonlat_from_channel_id doit être viré : remplacée par LATERAL "
        "JOIN dans get_traffic_bottlenecks qui ramène les vrais lat/lon."
    )


def test_get_traffic_bottlenecks_query_has_lat_lon():
    """La query SQL de get_traffic_bottlenecks doit ramener lat/lon."""
    from src.data import db_query

    src = inspect.getsource(db_query.get_traffic_bottlenecks)
    # Le SELECT final doit inclure lat, lon (via LATERAL JOIN)
    assert "f.lat" in src or "f.lon" in src, (
        "get_traffic_bottlenecks doit ramener lat/lon via LATERAL JOIN"
    )
    assert "LATERAL" in src, (
        "get_traffic_bottlenecks doit utiliser un LATERAL JOIN pour la dernière mesure"
    )


def test_load_traffic_uses_real_lat_lon_for_jams():
    """load_traffic() doit lire lat/lon depuis la query, pas via hash."""
    from src.data import data_loader

    src = inspect.getsource(data_loader.load_traffic)
    # Avant : _approx_lonlat_from_channel_id(row.get("channel_id"))
    # Après : row["lat"] / row["lon"] (directement depuis le DF)
    assert "_approx_lonlat_from_channel_id" not in src, (
        "load_traffic ne doit plus appeler _approx_lonlat_from_channel_id"
    )
    # Doit lire row["lat"] et row["lon"]
    assert 'row["lat"]' in src or "row['lat']" in src, (
        "load_traffic doit lire lat depuis la row de bottlenecks"
    )
    assert 'row["lon"]' in src or "row['lon']" in src, (
        "load_traffic doit lire lon depuis la row de bottlenecks"
    )


# =============================================================================
# Fix #3 : recommend_mode fail loud
# =============================================================================


def test_recommend_mode_fails_loud_without_durations():
    """recommend_mode doit lever ValueError si aucun mode n'a de durée."""
    from src.routing.eco_calculator import get_comparison, recommend_mode

    comparison = get_comparison(distance_km=3.0)
    # durations = {} : aucun mode n'a de durée, donc tous les scores = 9999
    with pytest.raises(ValueError, match="durations"):
        recommend_mode(comparison, critere="temps", durations={})


def test_recommend_mode_returns_velov_with_durations():
    """recommend_mode retourne bien un mode quand durations est fourni."""
    from src.routing.eco_calculator import get_comparison, recommend_mode

    comparison = get_comparison(distance_km=3.0)
    # Vélov est le plus rapide (15 min vs 8 min voiture, 12 min TC)
    # → winner = velov (le plus rapide en durée)
    rec = recommend_mode(
        comparison,
        critere="temps",
        durations={"voiture": 8, "tc": 12, "velov": 15},
    )
    assert rec["winner"] == "voiture", (
        f"Voiture (8 min) doit gagner, pas Vélov. Got: {rec['winner']}"
    )


# =============================================================================
# Fix #4 : _is_congested_from_speed câblé dans Usager_1
# =============================================================================


def test_is_congested_from_speed_threshold():
    """Le seuil de congestion doit être < 25 km/h (cf. ADEME)."""
    from src.routing.eco_calculator import _is_congested_from_speed

    assert _is_congested_from_speed(10) is True
    assert _is_congested_from_speed(20) is True
    assert _is_congested_from_speed(24.9) is True
    assert _is_congested_from_speed(25) is False
    assert _is_congested_from_speed(30) is False
    assert _is_congested_from_speed(50) is False
    # Edge case : vitesse 0 ou négative = pas de données
    assert _is_congested_from_speed(0) is False
    assert _is_congested_from_speed(-5) is False


def test_usager_uses_real_traffic_for_voiture_speed():
    """Usager_1 doit utiliser cached_traffic() pour la vitesse voiture, pas hardcodé 25."""
    with open("/Users/patriceduclos/Documents/Lyonfull/dashboard/pages/Usager_1_Mon_Trajet.py") as f:
        src = f.read()

    # Doit importer cached_traffic
    assert "cached_traffic" in src, (
        "Usager_1 doit importer cached_traffic pour la vitesse voiture live"
    )
    # Doit utiliser is_congested_from_speed (helper public Sprint 22+)
    assert "is_congested_from_speed" in src, (
        "Usager_1 doit utiliser is_congested_from_speed (helper public) pour la vraie détection"
    )
    # Ne doit plus avoir le proxy `is_congested=key == "voiture"` hardcodé
    assert 'is_congested=key == "voiture"' not in src, (
        "Le proxy is_congested=key==voiture doit être viré (toujours True = faux positif)"
    )
    # Le fallback 25.0 doit toujours être présent (au cas où DB indispo)
    assert "25.0" in src, (
        "Le fallback 25.0 km/h doit rester pour le cas DB indispo"
    )
